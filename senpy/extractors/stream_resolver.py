import logging
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from yt_dlp import YoutubeDL

from .embeds import EmbedExtractor

logger = logging.getLogger(__name__)


def is_direct_media_url(url: str, session: Optional[Any] = None, timeout: int = 8) -> bool:
    """Verifies whether a given URL points directly to a video/stream resource
    rather than an HTML landing page, anti-bot interstitial, or player shell."""
    if not url or not url.startswith("http"):
        return False

    clean_url = url.split("?")[0].lower()
    media_extensions = (".mp4", ".mkv", ".webm", ".m3u8", ".ts")

    # If session is provided, perform live HTTP inspection
    if session is not None:
        try:
            # Try HEAD request first
            resp = session.head(url, timeout=timeout, allow_redirects=True)
            ct = resp.headers.get("Content-Type", "").lower()
            if any(t in ct for t in ["video/", "application/x-mpegurl", "application/vnd.apple.mpegurl"]):
                return True
            if "application/octet-stream" in ct and any(clean_url.endswith(ext) for ext in media_extensions):
                return True
            if "text/html" in ct:
                return False
        except Exception:
            pass

        try:
            # Fallback to GET with stream=True so entire video payload is not downloaded
            resp = session.get(url, timeout=timeout, allow_redirects=True, stream=True)
            ct = resp.headers.get("Content-Type", "").lower()
            if any(t in ct for t in ["video/", "application/x-mpegurl", "application/vnd.apple.mpegurl"]):
                return True
            if "application/octet-stream" in ct and any(clean_url.endswith(ext) for ext in media_extensions):
                return True
            if "text/html" in ct:
                return False
        except Exception:
            pass

    return any(clean_url.endswith(ext) for ext in media_extensions)


def extract_streams_with_ytdlp(url: str, referer: Optional[str] = None) -> Dict[str, str]:
    """Uses yt-dlp programmatically to resolve direct media stream URLs (.mp4, .m3u8)
    and maps them to available quality labels (1080p, 720p, etc.)."""
    ydl_opts: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
        "nocheckcertificate": True,
    }
    if referer:
        ydl_opts["http_headers"] = {"Referer": referer}

    resolved: Dict[str, str] = {}
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return {}

            formats = info.get("formats", [])
            for f in formats:
                f_url = f.get("url")
                if not f_url:
                    continue
                height = f.get("height")
                note = str(f.get("format_note", "")).lower()
                fid = str(f.get("format_id", "")).lower()

                # Map to standard quality keys
                if height and isinstance(height, (int, float)) and height > 0:
                    quality_key = f"{int(height)}p"
                elif "1080" in note or "1080" in fid:
                    quality_key = "1080p"
                elif "720" in note or "720" in fid:
                    quality_key = "720p"
                elif "480" in note or "480" in fid:
                    quality_key = "480p"
                elif "360" in note or "360" in fid:
                    quality_key = "360p"
                else:
                    quality_key = f.get("format_id") or "default"

                resolved[quality_key] = f_url

            if not resolved and info.get("url"):
                h = info.get("height")
                q_key = f"{int(h)}p" if h else "default"
                resolved[q_key] = info["url"]
    except Exception as e:
        logger.debug(f"yt-dlp stream extraction failed for '{url}': {e}")

    return resolved


def extract_from_download_portal(html: str, base_url: str = "") -> Dict[str, str]:
    """Parses download portal HTML pages (e.g. anihdplay / gogo-stream)
    for direct video download anchor tags."""
    soup = BeautifulSoup(html, "html.parser")
    found: Dict[str, str] = {}
    for a in soup.select("div.dowload a, div.download a, div.list_dowload a, a[download]"):
        href = a.get("href", "").strip()
        if not href or href.startswith("javascript:"):
            continue
        full_url = urljoin(base_url, href)
        text = a.getText().strip()

        match = re.search(r"(\d{3,4})[pP]", text)
        if match:
            q = f"{match.group(1)}p"
        elif "x" in text and re.search(r"\d+x(\d+)", text):
            match_x = re.search(r"\d+x(\d+)", text)
            q = f"{match_x.group(1)}p" if match_x else "default"
        else:
            q = "default"

        found[q] = full_url
    return found


class StreamResolver:
    """Unified video stream resolver combining direct scraping, download portal inspection,
    yt-dlp extraction, and embed player fallbacks."""

    def __init__(self, session: Optional[Any] = None) -> None:
        self.session = session
        self.embed_extractor = EmbedExtractor(session=self.session)

    def resolve_streams(self, episode_url: str, html_content: Optional[str] = None) -> Dict[str, str]:
        """Resolves direct stream links for an episode, guaranteeing no raw HTML pages are returned."""
        start = time.perf_counter()
        if html_content is None:
            if not self.session:
                raise ValueError("Session required when html_content is not provided.")
            resp = self.session.get(episode_url, timeout=12)
            html_content = resp.text

        soup = BeautifulSoup(html_content, "html.parser")
        streams: Dict[str, str] = {}

        # 1. Inspect direct download container on GoGo episode page
        qualities_container = soup.select(
            "div.anime_video_body div.list_dowload div > a, div.list_dowload div > a, div.list_dowload a"
        )
        for link in qualities_container:
            raw_text = link.getText().strip()
            q_match = re.search(r"(\d{3,4})[pP]", raw_text)
            if q_match:
                q_key = f"{q_match.group(1)}p"
            elif "x" in raw_text:
                q_key = f"{raw_text.split('x')[1]}p"
            else:
                q_key = raw_text

            href = link.get("href", "").strip()
            if not href:
                continue

            try:
                # Follow redirect to see where it lands
                redirected = self.session.get(href, allow_redirects=True, timeout=10, stream=True)
                final_url = getattr(redirected, "url", href) or href
                hdrs = getattr(redirected, "headers", {})
                ct = (hdrs.get("Content-Type") or hdrs.get("content-type") or "").lower()

                if any(t in ct for t in ["video/", "application/octet-stream", "application/x-mpegurl", "application/vnd.apple.mpegurl"]):
                    streams[q_key] = final_url
                elif "text/html" in ct:
                    # Landing page / download portal; parse inner download links
                    portal_resp = self.session.get(final_url, timeout=10)
                    portal_links = extract_from_download_portal(portal_resp.text, base_url=final_url)
                    for pq, p_url in portal_links.items():
                        if is_direct_media_url(p_url, session=self.session):
                            streams[pq] = p_url

                    # Also try yt-dlp on the download portal page
                    if not streams:
                        ytdlp_portal = extract_streams_with_ytdlp(final_url, referer=episode_url)
                        if ytdlp_portal:
                            streams.update(ytdlp_portal)
            except Exception as e:
                logger.debug(f"Direct download resolution check failed for '{raw_text}': {e}")

        # 2. If no valid video streams yet, resolve via Embed player extraction (Vidstreaming, MegaCloud, etc.)
        if not streams:
            logger.info(f"Direct download links empty/HTML for '{episode_url}', falling back to embed extraction...")
            embed_urls = self.embed_extractor.extract_embed_urls(html_content, base_url=episode_url)
            for embed_url in embed_urls:
                logger.debug(f"Attempting yt-dlp stream extraction on embed: {embed_url}")
                embed_streams = extract_streams_with_ytdlp(embed_url, referer=episode_url)
                if embed_streams:
                    streams.update(embed_streams)
                    break

                # Fallback to internal regex embed parser
                parsed_embed = self.embed_extractor.resolve_embed_stream(embed_url)
                if parsed_embed:
                    streams.update(parsed_embed)
                    break

        # 3. Fallback: try yt-dlp on the episode page directly
        if not streams:
            logger.debug(f"Attempting yt-dlp on episode page: {episode_url}")
            page_streams = extract_streams_with_ytdlp(episode_url, referer=episode_url)
            if page_streams:
                streams.update(page_streams)

        # 4. Final filter: eliminate any links that are plain HTML
        validated_streams: Dict[str, str] = {}
        for q, link_url in streams.items():
            if link_url.endswith(".html") or link_url.endswith(".htm"):
                continue
            validated_streams[q] = link_url

        logger.info(
            f"({round(time.perf_counter() - start, 2)}s) Resolved {len(validated_streams)} valid video stream(s) for '{episode_url}'."
        )
        return validated_streams
