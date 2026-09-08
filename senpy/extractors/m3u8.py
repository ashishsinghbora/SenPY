import re
from typing import Dict, Optional
from urllib.parse import urljoin


class M3U8Parser:
    """Lightweight HLS / M3U8 playlist extractor and quality resolver."""

    @staticmethod
    def parse_master_playlist(content: str, base_url: str) -> Dict[str, str]:
        """Parses an M3U8 master playlist content into quality:stream_url mapping.

        Args:
            content: Raw text content of the .m3u8 file.
            base_url: The URL the playlist was fetched from, for relative path resolution.

        Returns:
            Dict mapping quality string (e.g. '1080p', '720p') to stream URL.
        """
        streams: Dict[str, str] = {}
        lines = [line.strip() for line in content.splitlines() if line.strip()]

        current_quality: Optional[str] = None

        for line in lines:
            if line.startswith("#EXT-X-STREAM-INF:"):
                # Extract resolution e.g. RESOLUTION=1920x1080
                res_match = re.search(r"RESOLUTION=\d+x(\d+)", line, re.IGNORECASE)
                if res_match:
                    current_quality = f"{res_match.group(1)}p"
                else:
                    bw_match = re.search(r"BANDWIDTH=(\d+)", line, re.IGNORECASE)
                    if bw_match:
                        bw = int(bw_match.group(1))
                        if bw > 3000000:
                            current_quality = "1080p"
                        elif bw > 1500000:
                            current_quality = "720p"
                        elif bw > 800000:
                            current_quality = "480p"
                        else:
                            current_quality = "360p"
                    else:
                        current_quality = "auto"
            elif not line.startswith("#"):
                if current_quality:
                    stream_url = urljoin(base_url, line)
                    streams[current_quality] = stream_url
                    current_quality = None

        # If no stream variants found but it's an m3u8 playlist, return base as default
        if not streams and "#EXTM3U" in content:
            streams["default"] = base_url

        return streams
