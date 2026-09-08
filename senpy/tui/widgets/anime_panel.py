from typing import Optional
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Checkbox, Input, Label, Select, Static

from senpy.metadata.models import AnimeMetadata
from senpy.sources.base import AnimeSearchResult


class AnimePanel(Static):
    """Right pane: Details, synopsis, and episode selection."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.current_anime: Optional[AnimeSearchResult] = None

        self.title_label = Label("Select an anime from search results", classes="panel-title")
        self.meta_label = Label("", classes="panel-meta")
        self.synopsis_label = Label("", classes="panel-synopsis")
        self.episodes_info = Label("", classes="panel-subinfo")

        self.ep_input = Input(
            placeholder="e.g. 1-12 or 1,3,5 (Leave empty for All)",
            id="ep-range-input",
            classes="form-input",
        )
        self.quality_select = Select(
            [
                ("1080p (Full HD)", "1080p"),
                ("720p (HD)", "720p"),
                ("480p (SD)", "480p"),
                ("360p", "360p"),
            ],
            value="1080p",
            allow_blank=False,
            id="quality-select",
            classes="form-select",
        )
        self.nfo_checkbox = Checkbox(
            "Generate Kodi / Jellyfin .nfo metadata",
            value=True,
            id="nfo-check",
            classes="form-checkbox",
        )
        self.status_msg = Label("", id="panel-status-msg")
        self.download_button = Button(
            "🚀 Start Download",
            variant="primary",
            id="btn-start-download",
            disabled=True,
            classes="action-button",
        )

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="anime-panel-container"):
            yield self.title_label
            yield self.meta_label
            yield self.episodes_info
            yield Label("Synopsis:", classes="section-heading")
            yield self.synopsis_label
            yield Label("Episode Range / Numbers:", classes="section-heading")
            yield self.ep_input
            yield Label("Preferred Video Quality:", classes="section-heading")
            yield self.quality_select
            yield Label("Media Server Integration:", classes="section-heading")
            yield self.nfo_checkbox
            yield self.status_msg
            yield self.download_button

    def update_anime(
        self,
        anime: AnimeSearchResult,
        metadata: Optional[AnimeMetadata] = None,
        ep_count: Optional[int] = None,
    ) -> None:
        """Populates the panel with chosen anime details and metadata."""
        self.current_anime = anime
        self.title_label.update(f"🎬 {anime.name}")

        release_text = f"Released: {anime.released}" if anime.released else ""
        genres_text = f" | Genres: {', '.join(metadata.genres)}" if metadata and metadata.genres else ""
        self.meta_label.update(f"{release_text}{genres_text}")

        if metadata and metadata.synopsis:
            self.synopsis_label.update(metadata.synopsis)
        else:
            self.synopsis_label.update("No synopsis available for this title.")

        if ep_count is not None and ep_count > 0:
            self.episodes_info.update(f"📺 Total Episodes: {ep_count}")
        elif metadata and metadata.total_episodes:
            self.episodes_info.update(f"📺 Estimated Episodes: {metadata.total_episodes}")
        else:
            self.episodes_info.update("📺 Episodes: Available")

        self.download_button.disabled = False
        self.status_msg.update("")
