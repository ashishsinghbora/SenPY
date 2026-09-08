from pathlib import Path
from typing import Any, Dict, Optional
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Input

from senpy import __version__
from senpy.config import GogoConfig
from senpy.downloader.aria2_rpc import Aria2RPCManager
from senpy.metadata.resolver import MetadataResolver
from senpy.sources.base import AnimeSearchResult
from senpy.sources.gogo import GogoSource
from senpy.tui.screens.main_screen import MainScreen
from senpy.tui.screens.settings import SettingsModal
from senpy.utils import GogoUtils


class SenPyApp(App):
    """SenPY Modern Dual-Pane Terminal User Interface."""

    CSS_PATH = "style.tcss"
    TITLE = f"SenPY v{__version__} — Anime Automation Engine"
    SUB_TITLE = "Modern, Resilient Anime Downloader & TUI"

    BINDINGS = [
        Binding("s", "focus_search", "Search", priority=True),
        Binding("d", "jump_downloads", "Downloads", priority=True),
        Binding("c", "open_settings", "Settings", priority=True),
        Binding("q", "quit", "Quit", priority=True),
    ]

    SCREENS = {
        "main": MainScreen,
        "settings": SettingsModal,
    }

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.config = GogoConfig()
        self.utils = GogoUtils()
        self.source = GogoSource(config=self.config)
        self.resolver = MetadataResolver(session=self.config.session)
        self.rpc_manager = Aria2RPCManager(
            aria2_bin=str(self.config.aria_2_path),
            port=self.config.config_model.ARIA_RPC_PORT,
            secret=self.config.config_model.ARIA_RPC_SECRET,
            max_concurrent=self.config.max_concurrent_downloads,
            logger=self.config.logger,
        )
        self.selected_anime: Optional[AnimeSearchResult] = None
        self.active_downloads: Dict[str, Any] = {}

    def on_mount(self) -> None:
        self.push_screen(MainScreen())

    def action_focus_search(self) -> None:
        """Shortcut 's': Focuses the anime search bar."""
        try:
            inp = self.screen.query_one("#search-input", Input)
            inp.focus()
        except Exception:
            pass

    def action_jump_downloads(self) -> None:
        """Shortcut 'd': Scrolls and focuses the transfer center queue."""
        try:
            scroll = self.screen.query_one("#downloads-scroll")
            scroll.focus()
            scroll.scroll_end(animate=True)
        except Exception:
            pass

    def action_open_settings(self) -> None:
        """Shortcut 'c': Opens the settings configuration modal."""
        self.push_screen(SettingsModal())

    def action_quit(self) -> None:
        """Shortcut 'q': Shuts down the application and background daemon."""
        self.exit()

    def on_unmount(self) -> None:
        """Clean up the Aria2 daemon on exit."""
        self.rpc_manager.shutdown()


# Alias for backward compatibility
SenpyApp = SenPyApp


def run_tui() -> None:
    """Entry point to launch the SenPY Textual application."""
    app = SenPyApp()
    app.run()
