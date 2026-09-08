import logging
import re
import time
from typing import Dict, List, Optional, Union
from bs4 import BeautifulSoup

from senpy.config import GogoConfig
from senpy.extractors.embeds import EmbedExtractor
from senpy.client import parse_episode_number
from .base import AnimeSearchResult, BaseSource, EpisodeInfo


class GogoSource(BaseSource):
    """GoGoAnime Source provider with direct download scraping and embed fallbacks."""

    def __init__(self, config: Optional[GogoConfig] = None) -> None:
        self.config = config or GogoConfig()
        self.logger = self.config.logger
        self.session = self.config.session
        self.embed_extractor = EmbedExtractor(session=self.session)
        self.url_ajax: Optional[str] = None

    def search(self, query: str) -> List[AnimeSearchResult]:
        """Searches for anime with the given query on GoGoAnime."""
        start = time.perf_counter()
        search_url = f"{self.config.CURRENT_URL}/search.html?keyword={query}"
        try:
            resp = self.config.request_with_retry("GET", search_url, timeout=12)
            soup = BeautifulSoup(resp.content, "html.parser")
        except Exception as e:
            self.logger.error(f"Error fetching search for '{query}': {e}")
            return []

        animes = soup.select("#wrapper_bg > section > section.content_left > div > div.last_episodes > ul > li")
        results: List[AnimeSearchResult] = []

        for anime in animes:
            try:
                name_elem = anime.find("p", {"class": "name"})
                released_elem = anime.find("p", {"class": "released"})
                img_elem = anime.div.a.img if anime.div and anime.div.a and anime.div.a.img else None

                if name_elem and name_elem.a:
                    anime_name = name_elem.a.getText().strip()
                    anime_href = name_elem.a["href"].strip()
                    anime_id = anime_href.split("/")[-1].replace("/", "")
                    released = (
                        released_elem.getText().strip().split("Released:")[1].strip()
                        if released_elem and "Released:" in released_elem.getText()
                        else "Unknown"
                    )
                    img_src = img_elem["src"] if img_elem and "src" in img_elem.attrs else ""
                    category_url = f"{self.config.CURRENT_URL}/category/{anime_id}"

                    results.append(
                        AnimeSearchResult(
                            id=anime_id,
                            name=anime_name,
                            released=released,
                            image=img_src,
                            url=category_url,
                            source="gogo",
                        )
                    )
            except Exception as e:
                self.logger.error(f"Error parsing anime search result item: {e}")

        self.logger.info(f"({round(time.perf_counter() - start, 2)}s) Searched '{query}', found {len(results)} results.")
        return results

    def get_episodes(self, anime_id: str) -> List[EpisodeInfo]:
        """Fetches all episodes available for the given anime ID."""
        start = time.perf_counter()
        category_url = f"{self.config.CURRENT_URL}/category/{anime_id}"
        try:
            resp = self.config.request_with_retry("GET", category_url, timeout=12)
            soup = BeautifulSoup(resp.content, "html.parser")
        except Exception as e:
            self.logger.error(f"Error fetching anime category for {anime_id}: {e}")
            return []

        movie_id_elem = soup.find("input", {"id": "movie_id"})
        if not movie_id_elem or "value" not in movie_id_elem.attrs:
            self.logger.warning(f"movie_id element not found for {anime_id}")
            return []
        movie_id = movie_id_elem["value"]

        ep_pages = soup.select("#episode_page")
        if not ep_pages:
            return []
        last_item = list(ep_pages[0])[-2]
        last_ep = int(last_item.a["ep_end"])

        url_meta = soup.find("meta", property="og:image")
        if url_meta and "content" in url_meta.attrs:
            self.url_ajax = url_meta["content"].split("/")[2]
        else:
            self.url_ajax = "gogoanime.to"

        try:
            ajax_url = f"https://ajax.{self.url_ajax}/ajax/load-list-episode?ep_start=0&ep_end={last_ep}&id={movie_id}"
            ajax_resp = self.config.request_with_retry("GET", ajax_url, timeout=12)
            ajax_soup = BeautifulSoup(ajax_resp.content, "html.parser")
        except Exception as e:
            self.logger.error(f"Error loading ajax episodes for {anime_id}: {e}")
            return []

        episodes: List[EpisodeInfo] = []
        for ep_tag in ajax_soup.select("ul#episode_related > li > a"):
            href = ep_tag.get("href", "").strip()
            try:
                ep_num = parse_episode_number(href)
                full_ep_url = f"{self.config.CURRENT_URL}{href}" if href.startswith("/") else href
                episodes.append(EpisodeInfo(number=ep_num, url=full_ep_url, id=f"{anime_id}-episode-{ep_num}"))
            except ValueError:
                continue

        episodes.sort(key=lambda x: x.number)
        self.logger.info(f"({round(time.perf_counter() - start, 2)}s) Retrieved {len(episodes)} episodes for {anime_id}.")
        return episodes

    def get_stream_links(self, episode_url: str) -> Dict[str, str]:
        """Resolves direct download links with embed fallback for an episode."""
        start = time.perf_counter()
        try:
            resp = self.config.request_with_retry("GET", episode_url, timeout=12)
            soup = BeautifulSoup(resp.content, "html.parser")
        except Exception as e:
            self.logger.error(f"Failed to fetch episode page {episode_url}: {e}")
            return {}

        links: Dict[str, str] = {}

        # 1. Primary extraction: direct download container
        qualities_container = soup.select(
            "#wrapper_bg > section > section.content_left > div > div.anime_video_body > div.list_dowload > div > a"
        )
        for link in qualities_container:
            try:
                redirected = self.session.get(link["href"], allow_redirects=False, timeout=10)
                quality_raw = link.getText().strip()
                quality_key = f"{quality_raw.split('x')[1]}p" if "x" in quality_raw else quality_raw
                loc = redirected.headers.get("location", "").strip()
                if loc:
                    links[quality_key] = loc
            except Exception as e:
                self.logger.debug(f"Direct download link check failed for {link.getText().strip()}: {e}")

        # 2. Fallback extraction: embed players (Vidstreaming, MegaCloud, etc.)
        if not links:
            self.logger.info(f"Direct download links empty for {episode_url}, attempting embed fallback...")
            embed_urls = self.embed_extractor.extract_embed_urls(resp.text, base_url=self.config.CURRENT_URL)
            for embed_url in embed_urls:
                self.logger.info(f"Trying embed source: {embed_url}")
                embed_streams = self.embed_extractor.resolve_embed_stream(embed_url)
                if embed_streams:
                    links.update(embed_streams)
                    break

        links = {k: v for k, v in links.items() if v}
        self.logger.info(f"({round(time.perf_counter() - start, 2)}s) Resolved {len(links)} stream links for {episode_url}.")
        return links

    @staticmethod
    def select_best_quality(available_links: Dict[str, str], requested_quality: Union[int, str]) -> str:
        """Helper to resolve nearest quality gracefully if exact quality is not available."""
        if not available_links:
            raise ValueError("No stream links available to select from.")

        req_int = int(str(requested_quality).replace("p", ""))
        int_qualities: Dict[int, str] = {}
        for k in available_links.keys():
            k_clean = k.replace("p", "")
            if k_clean.isdigit():
                int_qualities[int(k_clean)] = k

        if not int_qualities:
            # Fallback to any available key
            return next(iter(available_links.keys()))

        if req_int in int_qualities:
            return int_qualities[req_int]

        # Try next higher quality
        higher = sorted([q for q in int_qualities.keys() if q > req_int])
        if higher:
            return int_qualities[higher[0]]

        # Fallback to nearest lower quality
        lower = sorted([q for q in int_qualities.keys() if q < req_int])
        if lower:
            return int_qualities[lower[-1]]

        return next(iter(available_links.keys()))
