import re
import time
from typing import Any, Dict, List, Optional, Union
from bs4 import BeautifulSoup

from .config import GogoConfig
from .utils import GogoUtils
from .extractors.stream_resolver import StreamResolver, extract_video_url


def parse_episode_number(href: str) -> Union[int, float]:
    """Extracts episode index safely from a link without dynamic code evaluation.
    Handles formats like:
      - '-episode-1' -> 1
      - '-episode-12.5' -> 12.5
      - '-episode-12-5' -> 12.5
    """
    match = re.search(r"-episode-([\d\.\-]+)", href)
    if not match:
        raise ValueError(f"Unable to parse episode number from: {href}")
    num_str = match.group(1).replace("-", ".").rstrip(".")
    val = float(num_str)
    return int(val) if val.is_integer() else val


class GogoClient:
    """The GogoAnimeClient which interacts with the servers
    and its endpoints and does some highly intellectual stuffs
    which makes anime available to you, without you caring 
    about doing stuffs manually.
    """
    def __init__(self) -> None:
        self.url_ajax: Optional[str] = None
        self.config = GogoConfig()
        self.utils = GogoUtils()
        self.session = self.config.session

    def anime_search(self, query: str) -> List[Dict[str, Any]]:
        """Searches for anime with given query.

        Args:
            query (str): The query to search for.

        Returns:
            anime_list (list(dict)): The list of animes found.
        """
        start = time.perf_counter()
        search_url = f"{self.config.CURRENT_URL}/search.html?keyword={query}"
        try:
            resp = self.config.request_with_retry("GET", search_url, timeout=12)
            soup = BeautifulSoup(resp.content, 'html.parser')
        except Exception as e:
            self.config.logger.error(f"Failed to fetch search results for query '{query}': {e}")
            return []

        animes = soup.select("#wrapper_bg > section > section.content_left > div > div.last_episodes > ul > li")
        anime_list: List[Dict[str, Any]] = []
        for anime in animes:
            try:
                name_elem = anime.find("p", {"class": "name"})
                released_elem = anime.find("p", {"class": "released"})
                img_elem = anime.div.a.img if anime.div and anime.div.a and anime.div.a.img else None

                if name_elem and name_elem.a:
                    anime_list.append({
                        "name": name_elem.a.getText().strip(),
                        "id": name_elem.a["href"].strip().split("/")[-1].replace("/", ""),
                        "released": released_elem.getText().strip().split("Released:")[1].strip() if released_elem else "Unknown",
                        "image": img_elem["src"] if img_elem and "src" in img_elem.attrs else ""
                    })
            except Exception as e:
                self.config.logger.error(f"An error occurred while parsing search result | {e}")

        if not anime_list:
            try:
                from .metadata.resolver import MetadataResolver
                resolver = MetadataResolver(session=self.session)
                meta = resolver.resolve_metadata(query)
                if meta and meta.title:
                    name = meta.english_title or meta.title
                    safe_slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.lower()).strip("-")
                    anime_list.append({
                        "name": name,
                        "id": safe_slug,
                        "released": str(meta.year or "Unknown"),
                        "image": "",
                    })
            except Exception as e:
                self.config.logger.debug(f"Search fallback failed: {e}")

        self.config.logger.info(f"({round(time.perf_counter() - start, 2)}s) Fetched animes with query: \"{query}\", Found \"{len(anime_list)}\" results.")
        return anime_list

    def get_all_episode_numbers(self, animeid: str) -> List[Union[int, float]]:
        """Returns all the episodes of the anime (including bonus episodes like 17.5, 13.5, etc.).

        Args:
            animeid (str): The id of anime whose all episodes to fetch.

        Returns:
            eps (list): The list of all available episodes of the anime.
        """
        start = time.perf_counter()
        try:
            resp = self.config.request_with_retry("GET", f"{self.config.CURRENT_URL}/category/{animeid}", timeout=12)
            soup = BeautifulSoup(resp.content, 'html.parser')
        except Exception as e:
            self.config.logger.error(f"Failed to fetch category page for {animeid}: {e}")
            return []

        movie_id_elem = soup.find("input", {"id": "movie_id"})
        if not movie_id_elem or "value" not in movie_id_elem.attrs:
            self.config.logger.warning(f"Could not locate movie_id for anime {animeid}")
            return []
        anime_id = movie_id_elem['value']

        ep_pages = soup.select("#episode_page")
        if not ep_pages:
            return []
        last_item = list(ep_pages[0])[-2]
        last = int(last_item.a['ep_end'])

        url_meta = soup.find("meta", property="og:image")
        if url_meta and "content" in url_meta.attrs:
            self.url_ajax = url_meta["content"].split("/")[2]
        else:
            self.url_ajax = "gogoanime.to"

        try:
            ajax_url = f"https://ajax.{self.url_ajax}/ajax/load-list-episode?ep_start=0&ep_end={last}&id={anime_id}"
            ajax_resp = self.config.request_with_retry("GET", ajax_url, timeout=12)
            ajax_soup = BeautifulSoup(ajax_resp.content, 'html.parser')
        except Exception as e:
            self.config.logger.error(f"Failed to load episode list via ajax for {animeid}: {e}")
            return []

        all_eps: List[Union[int, float]] = []
        for ep in ajax_soup.select("ul#episode_related > li > a"):
            href = ep.get('href', '').strip()
            try:
                all_eps.append(parse_episode_number(href))
            except ValueError:
                continue

        all_eps.sort()
        self.config.logger.info(f"({round(time.perf_counter() - start, 2)}s) Fetched all episodes for anime id: \"{animeid}\"")
        return all_eps

    def get_episode_pages_links(self, animeid: str, eps: List[Union[int, float]]) -> List[str]:
        """Returns the list to the episode pages of anime with given id.

        Args:
            animeid (str): The id of anime whose episode links to fetch.
            eps (list(Union[int, float])): The list of episode numbers to fetch.

        Returns:
            links (list): The list containing links to the episode pages of anime.
        """
        start = time.perf_counter()
        try:
            resp = self.config.request_with_retry("GET", f"{self.config.CURRENT_URL}/category/{animeid}", timeout=12)
            soup = BeautifulSoup(resp.content, 'html.parser')
        except Exception as e:
            self.config.logger.error(f"Failed to fetch category page for {animeid}: {e}")
            return []

        movie_id_elem = soup.find("input", {"id": "movie_id"})
        if not movie_id_elem or "value" not in movie_id_elem.attrs:
            return []
        anime_id = movie_id_elem['value']

        if not self.url_ajax:
            url_meta = soup.find("meta", property="og:image")
            if url_meta and "content" in url_meta.attrs:
                self.url_ajax = url_meta["content"].split("/")[2]
            else:
                self.url_ajax = "gogoanime.to"

        ep_start = int(min(eps)) if eps else 0
        ep_end = int(max(eps)) if eps else 0
        try:
            ajax_url = f"https://ajax.{self.url_ajax}/ajax/load-list-episode?ep_start={ep_start}&ep_end={ep_end}&id={anime_id}"
            ajax_resp = self.config.request_with_retry("GET", ajax_url, timeout=12)
            ajax_soup = BeautifulSoup(ajax_resp.content, 'html.parser')
        except Exception as e:
            self.config.logger.error(f"Failed to load episode links via ajax for {animeid}: {e}")
            return []

        links: List[str] = []
        for ep in ajax_soup.select("ul#episode_related > li > a"):
            href = ep.get('href', '').strip()
            try:
                num = parse_episode_number(href)
                if num in eps:
                    links.append(f"{self.config.CURRENT_URL}{href}")
            except ValueError:
                continue

        links = links[::-1]
        self.config.logger.info(f"({round(time.perf_counter() - start, 2)}s) Fetched episodes' links for anime id: \"{animeid}\"")
        return links

    def get_episode_quality_download_links(self, url: str) -> Dict[str, str]:
        """Returns the download links to the various qualities available for the episode.
        Uses StreamResolver to ensure only verified direct media streams are returned,
        preventing saving of HTML landing pages or anti-bot interstitials.

        Args:
            url (str): The url to episode of the anime.

        Returns:
            links (dict): Dictionary containing quality:link pairs.
        """
        start = time.perf_counter()
        try:
            resolver = StreamResolver(session=self.session)
            links = resolver.resolve_streams(episode_url=url)
        except Exception as e:
            self.config.logger.error(f"Unable to retrieve links for the url \"{url}\": {e}")
            links = {}

        match = re.search(r"-episode-([\d\.-]+)", url)
        ep_label = match.group(1) if match else url.split('-')[-1].replace('/', '')
        self.config.logger.info(f"({round(time.perf_counter() - start, 2)}s) Fetched links for qualities available for episode #{ep_label}")
        return links
