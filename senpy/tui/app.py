from pathlib import Path
from typing import Any, Dict, Optional
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Button, Footer, Header

from senpy import __version__
from senpy.config import GogoConfig
from senpy.downloader.aria2_rpc import Aria2RPCManager
from senpy.metadata.resolver import MetadataResolver
from senpy.sources.base import AnimeSearchResult
from senpy.sources.gogo import GogoSource
from senpy.tui.screens.downloads import DownloadsScreen
from senpy.tui.screens.episodes import EpisodesScreen
from senpy.tui.screens.search import SearchScreen
from senpy.tui.screens.settings import SettingsScreen
from senpy.utils import GogoUtils


class SenpyApp(App):
    """SenPY Modern Terminal User Interface."""

    CSS_PATH = "style.tcss"
    TITLE = f"SenPY v{__version__} — Anime Automation Engine"
    SUB_TITLE = "Modern & Resilient Anime Downloader"

    BINDINGS = [
        Binding("s", "switch_screen('search')", "Search", priority=True),
        Binding("d", "switch_screen('downloads')", "Downloads", priority=True),
        Binding("c", "switch_screen('settings')", "Settings", priority=True),
        Binding("q", "quit", "Quit", priority=True),
    ]

    SCREENS = {
        "search": SearchScreen,
        "episodes": EpisodesScreen,
        "downloads": DownloadsScreen,
        "settings": SettingsScreen,
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

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="nav-bar"):
            yield Button("🔍 Search", id="nav-search", classes="nav-btn")
            yield Button("⬇️ Downloads", id="nav-downloads", classes="nav-btn")
            yield Button("⚙️ Settings", id="nav-settings", classes="nav-btn")
        yield Footer()

    def on_mount(self) -> None:
        self.push_screen("search")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "nav-search":
            self.switch_screen("search")
        elif event.button.id == "nav-downloads":
            self.switch_screen("downloads")
        elif event.button.id == "nav-settings":
            self.switch_screen("settings")

    def on_unmount(self) -> None:
        """Clean up the Aria2 daemon on exit."""
        self.rpc_manager.shutdown()


def run_tui() -> None:
    """Entry point to launch the SenPY Textual application."""
    app = SenpyApp()
    app.run()
