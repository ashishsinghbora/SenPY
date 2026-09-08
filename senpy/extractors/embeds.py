import logging
import re
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
from curl_cffi import requests
from urllib.parse import urljoin

from .m3u8 import M3U8Parser


class EmbedExtractor:
    """Extracts video streams from embedded third-party video players."""

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.logger = logging.getLogger(__name__)
        self.session = session or requests.Session(impersonate="chrome120", verify=False)
        self.session.headers["Accept-Encoding"] = "identity"

    def extract_embed_urls(self, html_content: str, base_url: str = "") -> List[str]:
        """Scrapes iframe and server embed URLs from an anime episode page."""
        soup = BeautifulSoup(html_content, "html.parser")
        embed_urls: List[str] = []

        # 1. Check anime_muti_link container
        for server_link in soup.select("div.anime_muti_link > ul > li > a"):
            data_video = server_link.get("data-video", "").strip()
            if data_video:
                if data_video.startswith("//"):
                    data_video = f"https:{data_video}"
                elif not data_video.startswith("http"):
                    data_video = urljoin(base_url, data_video)
                if data_video not in embed_urls:
                    embed_urls.append(data_video)

        # 2. Check main iframe
        iframe = soup.select_one("div.play-video > iframe, div.anime_video_body_watch > iframe")
        if iframe and iframe.get("src"):
            src = iframe["src"].strip()
            if src.startswith("//"):
                src = f"https:{src}"
            elif not src.startswith("http"):
                src = urljoin(base_url, src)
            if src not in embed_urls:
                embed_urls.insert(0, src)

        return embed_urls

    def resolve_embed_stream(self, embed_url: str) -> Dict[str, str]:
        """Fetches embed player page and resolves stream/m3u8 links."""
        try:
            resp = self.session.get(embed_url, timeout=10, headers={"Referer": embed_url})
            content = resp.text
        except Exception as e:
            self.logger.debug(f"Failed to fetch embed {embed_url}: {e}")
            return {}

        results: Dict[str, str] = {}

        # Search for direct .m3u8 URLs in javascript or source tags
        m3u8_matches = re.findall(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', content)
        for m3u8_url in m3u8_matches:
            # Clean escaped slashes
            clean_url = m3u8_url.replace(r"\/", "/")
            try:
                playlist_resp = self.session.get(clean_url, timeout=8, headers={"Referer": embed_url})
                if playlist_resp.status_code == 200:
                    parsed_streams = M3U8Parser.parse_master_playlist(playlist_resp.text, clean_url)
                    results.update(parsed_streams)
                    if results:
                        return results
            except Exception:
                pass
            results["auto"] = clean_url

        # Search for direct mp4 links
        mp4_matches = re.findall(r'["\'](https?://[^"\']+\.mp4[^"\']*)["\']', content)
        for mp4_url in mp4_matches:
            clean_mp4 = mp4_url.replace(r"\/", "/")
            results["default"] = clean_mp4
            break

        return results
