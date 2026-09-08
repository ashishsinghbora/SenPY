import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from senpy.extractors.stream_resolver import (
    StreamResolver,
    extract_from_download_portal,
    extract_streams_with_ytdlp,
    is_direct_media_url,
)
from senpy.downloader.aria2_rpc import (
    Aria2RPCManager,
    DownloadItem,
    DEFAULT_USER_AGENT,
    download_hls_stream,
)
from senpy.sources.gogo import GogoSource
from senpy.utils import GogoUtils
from senpy.client import parse_episode_number


class TestStreamResolver(unittest.TestCase):
    def test_is_direct_media_url(self):
        self.assertTrue(is_direct_media_url("https://cdn.example.com/video.mp4"))
        self.assertTrue(is_direct_media_url("https://cdn.example.com/stream.m3u8?token=123"))
        self.assertFalse(is_direct_media_url("https://example.com/watch.html"))
        self.assertFalse(is_direct_media_url("https://example.com/landing?id=5"))

    def test_extract_from_download_portal(self):
        sample_html = """
        <html>
            <body>
                <div class="dowload">
                    <a href="https://cdn.net/ep1_1080p.mp4" download>Download (1080P - mp4)</a>
                    <a href="https://cdn.net/ep1_720p.mp4" download>Download (720P - mp4)</a>
                </div>
            </body>
        </html>
        """
        links = extract_from_download_portal(sample_html, base_url="https://anihdplay.com")
        self.assertEqual(links.get("1080p"), "https://cdn.net/ep1_1080p.mp4")
        self.assertEqual(links.get("720p"), "https://cdn.net/ep1_720p.mp4")

    @patch("senpy.extractors.stream_resolver.YoutubeDL")
    def test_extract_streams_with_ytdlp(self, mock_ydl_cls):
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = {
            "formats": [
                {"format_id": "18", "height": 360, "url": "https://cdn.com/360.mp4"},
                {"format_id": "22", "height": 720, "url": "https://cdn.com/720.mp4"},
                {"format_id": "37", "height": 1080, "url": "https://cdn.com/1080.mp4"},
            ]
        }
        res = extract_streams_with_ytdlp("https://embtuku.pro/streaming.php?id=123")
        self.assertIn("1080p", res)
        self.assertIn("720p", res)
        self.assertEqual(res["1080p"], "https://cdn.com/1080.mp4")

    def test_parse_episode_number(self):
        self.assertEqual(parse_episode_number("/category/naruto-episode-1"), 1)
        self.assertEqual(parse_episode_number("naruto-shippuden-episode-12.5"), 12.5)
        self.assertEqual(parse_episode_number("bleach-episode-16-5"), 16.5)

    def test_fix_episode_download_names(self):
        utils = GogoUtils()
        links = [
            "https://cdn.com/file.mp4?key=abc&title=naruto-episode-1-1080p",
            "https://cdn.com/video-episode-2.mp4",
        ]
        fixed = utils.fix_episode_download_names(links)
        self.assertIn("title=EP.1", fixed[0])
        self.assertIn("title=EP.2", fixed[1])

    def test_aria2_header_hardening(self):
        manager = Aria2RPCManager(port=6999, secret="test")
        manager.call = MagicMock(return_value="mock_gid")
        item = DownloadItem(
            url="https://cdn.stream.com/video.mp4",
            download_dir=Path("/tmp/senpy_test"),
            filename="test.mp4",
            referer="https://anitaku.to/",
        )
        gid = manager.add_download(item)
        self.assertEqual(gid, "mock_gid")
        call_args = manager.call.call_args[0]
        self.assertEqual(call_args[0], "aria2.addUri")
        options = call_args[1][1]
        headers = options.get("header", [])
        self.assertTrue(any(f"User-Agent: {DEFAULT_USER_AGENT}" in h for h in headers))
        self.assertTrue(any("Referer: https://anitaku.to/" in h for h in headers))

    def test_select_best_quality(self):
        links = {
            "360p": "https://cdn.com/360.mp4",
            "720p": "https://cdn.com/720.mp4",
        }
        self.assertEqual(GogoSource.select_best_quality(links, "720p"), "720p")
        # 1080p requested, higher not available, falls back to 720p
        self.assertEqual(GogoSource.select_best_quality(links, "1080p"), "720p")
        # 480p requested, steps up to 720p
        self.assertEqual(GogoSource.select_best_quality(links, "480p"), "720p")

    def test_stream_resolver_direct_container(self):
        mock_session = MagicMock()
        resolver = StreamResolver(session=mock_session)

        # Mock direct video response
        mock_resp = MagicMock()
        mock_resp.url = "https://cdn.com/direct_1080p.mp4"
        mock_resp.headers = {"Content-Type": "video/mp4"}
        mock_session.get.return_value = mock_resp

        sample_page = """
        <div class="anime_video_body">
            <div class="list_dowload">
                <div><a href="https://gogo-stream.cc/download?id=123">Download (1080P - mp4)</a></div>
            </div>
        </div>
        """
        streams = resolver.resolve_streams("https://gogoanime.to/ep-1", html_content=sample_page)
        self.assertIn("1080p", streams)
        self.assertEqual(streams["1080p"], "https://cdn.com/direct_1080p.mp4")


if __name__ == "__main__":
    unittest.main()
