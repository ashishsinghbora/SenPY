import asyncio
import unittest
from unittest.mock import MagicMock, patch

from senpy.tui.app import SenPyApp
from senpy.tui.screens.main_screen import MainScreen
from senpy.tui.screens.settings import SettingsModal
from senpy.tui.widgets.download_bar import DownloadBar
from senpy.extractors.stream_resolver import extract_video_url
from textual.widgets import Input


class TestTUI(unittest.IsolatedAsyncioTestCase):
    async def test_tui_lifecycle_and_navigation(self):
        app = SenPyApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertTrue(app.is_running)

            # Test search input focus
            app.action_focus_search()
            await pilot.pause()
            inp = app.screen.query_one("#search-input", Input)
            self.assertTrue(inp.has_focus)

            # Test open settings modal
            app.action_open_settings()
            await pilot.pause()
            self.assertIsInstance(app.screen, SettingsModal)

            # Test close modal
            await pilot.click("#btn-close-settings")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, SettingsModal)

    def test_download_bar_updates(self):
        bar = DownloadBar(gid="test_gid", filename="ep1.mp4", label="Naruto EP 1")
        bar.update_progress(completed=10485760, total=20971520, speed=1048576, status="active")
        self.assertEqual(bar.status, "active")
        self.assertIn("10.0 MB / 20.0 MB", str(bar.stats_widget.render()))

    @patch("senpy.extractors.stream_resolver.extract_streams_with_ytdlp")
    def test_extract_video_url(self, mock_ytdlp):
        # Direct URL
        direct = extract_video_url("https://cdn.example.com/video.mp4")
        self.assertEqual(direct, "https://cdn.example.com/video.mp4")

        # HTML landing page with ytdlp fallback
        mock_ytdlp.return_value = {"720p": "https://cdn.example.com/resolved_720p.mp4"}
        resolved = extract_video_url("https://anihdplay.com/download?id=456")
        self.assertEqual(resolved, "https://cdn.example.com/resolved_720p.mp4")


if __name__ == "__main__":
    unittest.main()
