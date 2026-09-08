from pathlib import Path
from typing import List, Union
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Input, Label, RadioButton, RadioSet, Select

from senpy.downloader.aria2_rpc import DownloadItem
from senpy.metadata.nfo import write_nfo_file
from senpy.sources.base import AnimeSearchResult, EpisodeInfo


class EpisodesScreen(Screen):
    """Episode range, quality selection, and download dispatch screen."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.title_label = Label("Episode Selection", classes="detail-title")
        self.episodes_info = Label("Fetching episode list...", classes="detail-meta")
        self.episodes_input = Input(placeholder="e.g. 1-12, 14.5, 16 (Leave empty for All)", id="ep-input")
        self.quality_select = Select(
            [("1080p (Full HD)", "1080p"), ("720p (HD)", "720p"), ("480p (SD)", "480p"), ("360p", "360p")],
            value="1080p",
            allow_blank=False,
            id="quality-select",
        )
        self.nfo_checkbox = Checkbox("Generate Kodi / Jellyfin .nfo metadata", value=True, id="nfo-check")
        self.status_label = Label("", id="ep-status")
        self.download_btn = Button("🚀 Start Download", classes="action-btn", id="start-btn")
        self.back_btn = Button("⬅️ Back to Search", classes="nav-btn", id="back-btn")
        self.all_episodes: List[EpisodeInfo] = []

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="episodes-container"):
            with Vertical(classes="panel-card"):
                yield self.title_label
                yield self.episodes_info
                yield Label("Episode Range / Numbers:", classes="form-label")
                yield self.episodes_input
                yield Label("Preferred Video Quality:", classes="form-label")
                yield self.quality_select
                yield Label("Media Server Integration:", classes="form-label")
                yield self.nfo_checkbox
                yield self.status_label
                with Horizontal():
                    yield self.download_btn
                    yield self.back_btn

    def on_screen_resume(self) -> None:
        anime = getattr(self.app, "selected_anime", None)
        if anime:
            self.title_label.update(f"🎬 {anime.name}")
            self.load_episodes(anime)

    @work(exclusive=True, thread=True)
    def load_episodes(self, anime: AnimeSearchResult) -> None:
        """Loads available episodes asynchronously."""
        self.app.call_from_thread(self.episodes_info.update, "Fetching available episodes from source...")
        eps = self.app.source.get_episodes(anime.id)
        if not eps:
            meta = self.app.resolver.resolve_metadata(anime.name)
            total = meta.total_episodes or 24
            eps = [EpisodeInfo(number=i, url=f"{self.app.config.CURRENT_URL}/{anime.id}-episode-{i}") for i in range(1, total + 1)]

        self.all_episodes = eps
        self.app.call_from_thread(
            self.episodes_info.update,
            f"Found {len(self.all_episodes)} episode(s) (1 to {self.all_episodes[-1].number if self.all_episodes else 0})"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.switch_screen("search")
        elif event.button.id == "start-btn":
            self.prepare_and_start_downloads()

    @work(exclusive=True, thread=True)
    def prepare_and_start_downloads(self) -> None:
        """Resolves target stream URLs and dispatches downloads non-blockingly."""
        anime = getattr(self.app, "selected_anime", None)
        if not anime or not self.all_episodes:
            return

        self.app.call_from_thread(self.status_label.update, "Planning target download paths...")
        ep_input_val = self.episodes_input.value.strip()

        if not ep_input_val or ep_input_val.lower() == "all":
            targets = self.all_episodes
        else:
            try:
                wanted_nums = self.app.utils.string_to_sequence(ep_input_val)
                targets = [ep for ep in self.all_episodes if ep.number in wanted_nums]
            except Exception:
                targets = self.all_episodes

        if not targets:
            self.app.call_from_thread(self.status_label.update, "No matching episodes to download.")
            return

        quality = str(self.quality_select.value or "1080p")
        write_nfo = self.nfo_checkbox.value
        base_dir = self.app.config.downloads_dir

        planned_items: List[DownloadItem] = []
        for ep in targets:
            plan = self.app.resolver.plan_media_destination(
                anime_title=anime.name,
                ep_num=ep.number,
                output_dir=base_dir,
            )

            stream_links = self.app.source.get_stream_links(ep.url)
            if not stream_links:
                # Simulated stream for test or fallback
                stream_url = ep.url
            else:
                best_q = self.app.source.select_best_quality(stream_links, quality)
                stream_url = stream_links[best_q]

            if write_nfo:
                write_nfo_file(
                    file_path=plan.target_nfo_path,
                    show_title=plan.anime_title,
                    episode_title=plan.episode_title,
                    season_num=plan.season_num,
                    episode_num=plan.ep_num,
                )

            planned_items.append(
                DownloadItem(
                    url=stream_url,
                    download_dir=plan.target_video_path.parent,
                    filename=plan.video_filename,
                    label=f"{plan.anime_title} E{plan.ep_num}",
                    referer=self.app.config.CURRENT_URL,
                )
            )

        # Enqueue into Aria2 daemon
        self.app.call_from_thread(self.status_label.update, "Enqueuing tasks into Aria2 RPC daemon...")
        self.app.rpc_manager.ensure_daemon()

        for item in planned_items:
            gid = self.app.rpc_manager.add_download(item)
            self.app.active_downloads[gid] = {
                "item": item,
                "status": "waiting",
                "completed": 0,
                "total": 0,
                "speed": 0,
            }

        # Switch to downloads screen
        def _to_downloads():
            self.app.switch_screen("downloads")

        self.app.call_from_thread(_to_downloads)
