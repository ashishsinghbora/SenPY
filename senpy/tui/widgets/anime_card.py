from typing import Optional
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Label, Static

from senpy.sources.base import AnimeSearchResult


class AnimeCard(Static):
    """Component to render rich anime metadata details."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.title_label = Label("Select an anime to view details", classes="detail-title")
        self.meta_label = Label("", classes="detail-meta")
        self.synopsis_label = Label("", classes="detail-synopsis")

    def compose(self) -> ComposeResult:
        with Vertical():
            yield self.title_label
            yield self.meta_label
            yield VerticalScroll(self.synopsis_label)

    def update_anime(self, anime: AnimeSearchResult, synopsis: str = "") -> None:
        """Updates the card view with anime details."""
        self.title_label.update(f"🎬 {anime.name}")
        meta_text = f"📅 Released: {anime.released}  |  🆔 ID: {anime.id}"
        self.meta_label.update(meta_text)
        plot = synopsis.strip() if synopsis else "Fetching metadata synopsis..."
        self.synopsis_label.update(plot)

    def clear_view(self) -> None:
        self.title_label.update("Select an anime to view details")
        self.meta_label.update("")
        self.synopsis_label.update("")
