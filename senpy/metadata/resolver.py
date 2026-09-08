import logging
import re
from pathlib import Path
from typing import Dict, Optional, Union
from curl_cffi import requests

from .models import AnimeMetadata, FormattedMediaPlan, sanitize_filename


class MetadataResolver:
    """Resolves anime metadata (titles, seasons, episode names) from public APIs (AniList, Kitsu, Jikan)."""

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.logger = logging.getLogger(__name__)
        self.session = session or requests.Session(impersonate="chrome120", verify=False)
        self.session.headers["Accept-Encoding"] = "identity"

    def _detect_season(self, title: str) -> int:
        """Extracts season number from title string if present (e.g. 'Season 2', '2nd Season')."""
        match = re.search(r"(?:season\s*|s)(\d+)", title, re.IGNORECASE)
        if match:
            return int(match.group(1))
        match2 = re.search(r"(\d+)(?:nd|rd|th)\s+season", title, re.IGNORECASE)
        if match2:
            return int(match2.group(1))
        return 1

    def resolve_from_anilist(self, title: str) -> Optional[AnimeMetadata]:
        """Queries AniList GraphQL endpoint."""
        query = """
        query ($search: String) {
          Media (search: $search, type: ANIME) {
            id
            title {
              romaji
              english
            }
            seasonYear
            episodes
            description
          }
        }
        """
        try:
            resp = self.session.post(
                "https://graphql.anilist.co",
                json={"query": query, "variables": {"search": title}},
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {}).get("Media")
                if data:
                    t_obj = data.get("title", {})
                    canonical = t_obj.get("english") or t_obj.get("romaji") or title
                    return AnimeMetadata(
                        title=canonical,
                        english_title=t_obj.get("english"),
                        season_number=self._detect_season(title),
                        total_episodes=data.get("episodes"),
                        synopsis=data.get("description") or "",
                        year=data.get("seasonYear"),
                    )
        except Exception as e:
            self.logger.debug(f"AniList query failed: {e}")
        return None

    def resolve_from_kitsu(self, title: str) -> Optional[AnimeMetadata]:
        """Queries Kitsu API endpoint."""
        try:
            resp = self.session.get(
                f"https://kitsu.io/api/edge/anime?filter[text]={title}&page[limit]=1",
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json().get("data")
                if data and len(data) > 0:
                    attr = data[0].get("attributes", {})
                    canonical = attr.get("canonicalTitle") or title
                    titles = attr.get("titles", {})
                    en_title = titles.get("en") or titles.get("en_us") or canonical
                    year_val = None
                    start_date = attr.get("startDate")
                    if start_date and len(start_date) >= 4 and start_date[:4].isdigit():
                        year_val = int(start_date[:4])

                    return AnimeMetadata(
                        title=canonical,
                        english_title=en_title,
                        season_number=self._detect_season(title),
                        total_episodes=attr.get("episodeCount"),
                        synopsis=attr.get("synopsis") or "",
                        year=year_val,
                    )
        except Exception as e:
            self.logger.debug(f"Kitsu query failed: {e}")
        return None

    def resolve_from_jikan(self, title: str) -> Optional[AnimeMetadata]:
        """Queries Jikan (MyAnimeList) API endpoint."""
        try:
            resp = self.session.get(
                f"https://api.jikan.moe/v4/anime?q={title}&limit=1",
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json().get("data")
                if data and len(data) > 0:
                    item = data[0]
                    canonical = item.get("title") or title
                    return AnimeMetadata(
                        title=canonical,
                        english_title=item.get("title_english"),
                        season_number=self._detect_season(title),
                        total_episodes=item.get("episodes"),
                        synopsis=item.get("synopsis") or "",
                        year=item.get("year"),
                    )
        except Exception as e:
            self.logger.debug(f"Jikan query failed: {e}")
        return None

    def resolve_metadata(self, title: str) -> AnimeMetadata:
        """Resolves series metadata with multi-tier fallback."""
        clean_search = re.sub(r"\(TV\)|\(Dub\)|\(Sub\)", "", title, flags=re.IGNORECASE).strip()

        # 1. Try AniList
        res = self.resolve_from_anilist(clean_search)
        if res:
            return res

        # 2. Try Kitsu
        res = self.resolve_from_kitsu(clean_search)
        if res:
            return res

        # 3. Try Jikan
        res = self.resolve_from_jikan(clean_search)
        if res:
            return res

        # 4. Fallback to clean search title
        return AnimeMetadata(
            title=clean_search,
            season_number=self._detect_season(clean_search),
        )

    def plan_media_destination(
        self,
        anime_title: str,
        ep_num: Union[int, float],
        output_dir: Path,
        season_num: Optional[int] = None,
        episode_title: Optional[str] = None,
    ) -> FormattedMediaPlan:
        """Generates standard Plex / Jellyfin media destination paths."""
        meta = self.resolve_metadata(anime_title)
        resolved_title = sanitize_filename(meta.english_title or meta.title)
        resolved_season = season_num if season_num is not None else meta.season_number

        ep_str = f"{int(ep_num):02d}" if isinstance(ep_num, int) or (isinstance(ep_num, float) and ep_num.is_integer()) else f"{ep_num}"
        safe_ep_title = sanitize_filename(episode_title or f"Episode {ep_str}")

        base_name = f"{resolved_title} - S{resolved_season:02d}E{ep_str} - {safe_ep_title}"
        video_filename = f"{base_name}.mp4"
        nfo_filename = f"{base_name}.nfo"

        return FormattedMediaPlan(
            anime_title=resolved_title,
            season_num=resolved_season,
            ep_num=ep_num,
            episode_title=safe_ep_title,
            output_dir=output_dir,
            video_filename=video_filename,
            nfo_filename=nfo_filename,
        )
