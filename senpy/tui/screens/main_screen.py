import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Static

from senpy.downloader.aria2_rpc import DownloadItem
from senpy.metadata.nfo import write_nfo_file
from senpy.sources.base import AnimeSearchResult, EpisodeInfo
from senpy.tui.widgets.anime_panel import AnimePanel
from senpy.tui.widgets.download_bar import DownloadBar


class SearchResultItem(ListItem):
    """An individual anime entry in the search results list."""

    def __init__(self, anime: AnimeSearchResult, **kwargs) -> None:
        super().__init__(**kwargs)
        self.anime = anime

    def compose(self) -> ComposeResult:
        rel = f" [{self.anime.released}]" if self.anime.released else ""
        yield Label(f"🎬 {self.anime.name}{rel}", classes="search-item-label")


class MainScreen(Screen):
    """Dual-pane search & download queue screen."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.search_input = Input(placeholder="Search anime...", id="search-input")
        self.results_list = ListView(id="search-results")
        self.anime_panel = AnimePanel(id="anime-panel")
        self.downloads_scroll = VerticalScroll(id="downloads-scroll")
        self.transfer_header = Label("⬇️ Transfer Center & Download Queue (0 active)", id="transfer-header")

        self.current_anime: Optional[AnimeSearchResult] = None
        self.all_episodes: List[EpisodeInfo] = []
        self.active_bars: Dict[str, DownloadBar] = {}
        self._debounce_timer = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="main-screen-layout"):
            # Top Dual-Pane Container
            with Horizontal(id="browse-container"):
                # Left Pane: Search & Results
                with Vertical(id="left-pane"):
                    yield Label("🔍 Anime Search", classes="pane-header")
                    yield self.search_input
                    yield self.results_list

                # Right Pane: Selected Anime Details & Form
                with Vertical(id="right-pane"):
                    yield Label("📋 Details & Episode Selection", classes="pane-header")
                    yield self.anime_panel

            # Bottom Panel: Transfer Center
            with Vertical(id="transfer-center"):
                yield self.transfer_header
                yield self.downloads_scroll
        yield Footer()

    def on_mount(self) -> None:
        self.search_input.focus()
        self.set_interval(1.0, self.poll_active_downloads)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-input":
            query = event.value.strip()
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
            if len(query) >= 2:
                self._debounce_timer = self.set_timer(0.35, lambda: self.perform_search(query))
            elif not query:
                self.results_list.clear()

    @work(exclusive=True, thread=True)
    def perform_search(self, query: str) -> None:
        """Executes non-blocking anime search."""
        try:
            results = self.app.source.search(query)
        except Exception:
            results = []

        def _update_ui():
            self.results_list.clear()
            if not results:
                self.results_list.append(ListItem(Label("No results found.", classes="empty-msg")))
            else:
                for a in results:
                    self.results_list.append(SearchResultItem(a))

        self.app.call_from_thread(_update_ui)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, SearchResultItem):
            self.current_anime = event.item.anime
            self.load_anime_details(self.current_anime)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if isinstance(event.item, SearchResultItem):
            self.current_anime = event.item.anime
            self.load_anime_details(self.current_anime)

    @work(exclusive=True, thread=True)
    def load_anime_details(self, anime: AnimeSearchResult) -> None:
        """Asynchronously fetches metadata, synopsis, and episode count."""
        try:
            meta = self.app.resolver.resolve_metadata(anime.name)
        except Exception:
            meta = None

        try:
            eps = self.app.source.get_episodes(anime.id)
        except Exception:
            eps = []

        if not eps and meta and meta.total_episodes:
            eps = [
                EpisodeInfo(
                    number=i,
                    url=f"{self.app.config.CURRENT_URL}/{anime.id}-episode-{i}",
                )
                for i in range(1, meta.total_episodes + 1)
            ]

        self.all_episodes = eps
        self.app.call_from_thread(self.anime_panel.update_anime, anime, meta, len(eps))

    def on_button_pressed(self, event) -> None:
        if getattr(event.button, "id", None) == "btn-start-download":
            self.trigger_download_flow()

    @work(exclusive=True, thread=True)
    def trigger_download_flow(self) -> None:
        """Resolves target streams and queues downloads in Aria2 daemon non-blockingly."""
        anime = self.current_anime
        if not anime or not self.all_episodes:
            return

        self.app.call_from_thread(self.anime_panel.status_msg.update, "Planning target download paths...")

        ep_input_val = self.anime_panel.ep_input.value.strip()
        if not ep_input_val or ep_input_val.lower() == "all":
            targets = self.all_episodes
        else:
            try:
                wanted_nums = self.app.utils.string_to_sequence(ep_input_val)
                targets = [ep for ep in self.all_episodes if ep.number in wanted_nums]
            except Exception:
                targets = self.all_episodes

        if not targets:
            self.app.call_from_thread(self.anime_panel.status_msg.update, "❌ No matching episodes found.")
            return

        quality = str(self.anime_panel.quality_select.value or "1080p")
        write_nfo = self.anime_panel.nfo_checkbox.value
        base_dir = self.app.config.downloads_dir

        self.app.call_from_thread(
            self.anime_panel.status_msg.update,
            f"Resolving streams for {len(targets)} episode(s)...",
        )

        planned_items: List[DownloadItem] = []
        for ep in targets:
            plan = self.app.resolver.plan_media_destination(
                anime_title=anime.name,
                ep_num=ep.number,
                output_dir=base_dir,
            )

            try:
                stream_links = self.app.source.get_stream_links(ep.url)
            except Exception:
                stream_links = {}

            if not stream_links:
                stream_url = ep.url
            else:
                best_q = self.app.source.select_best_quality(stream_links, quality)
                stream_url = stream_links[best_q]

            if write_nfo:
                try:
                    write_nfo_file(
                        file_path=plan.target_nfo_path,
                        show_title=plan.anime_title,
                        episode_title=plan.episode_title,
                        season_num=plan.season_num,
                        episode_num=plan.ep_num,
                    )
                except Exception:
                    pass

            planned_items.append(
                DownloadItem(
                    url=stream_url,
                    download_dir=plan.target_video_path.parent,
                    filename=plan.video_filename,
                    label=f"{plan.anime_title} E{plan.ep_num}",
                    referer=self.app.config.CURRENT_URL,
                )
            )

        # Enqueue tasks into Aria2
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

            def _add_bar(g=gid, it=item):
                bar = DownloadBar(gid=g, filename=it.filename or "video.mp4", label=it.label)
                self.active_bars[g] = bar
                self.downloads_scroll.mount(bar)
                self.downloads_scroll.scroll_end(animate=False)

            self.app.call_from_thread(_add_bar)

        def _done():
            self.anime_panel.status_msg.update(f"✅ Queued {len(planned_items)} episode(s)!")
            self.transfer_header.update(f"⬇️ Transfer Center & Download Queue ({len(self.app.active_downloads)} active)")

        self.app.call_from_thread(_done)

    def poll_active_downloads(self) -> None:
        """Polls transmission metrics without blocking the UI thread."""
        if not self.app.active_downloads:
            return

        total_speed = 0
        active_count = 0

        for gid, data in list(self.app.active_downloads.items()):
            try:
                st = self.app.rpc_manager.tell_status(gid)
            except Exception:
                continue

            status = st.get("status", "waiting")
            completed_len = int(st.get("completedLength", 0))
            total_len = int(st.get("totalLength", 0))
            speed = int(st.get("downloadSpeed", 0))
            err_msg = st.get("errorMessage")

            data["completed"] = completed_len
            data["total"] = total_len
            data["speed"] = speed
            data["status"] = status
            total_speed += speed

            if status == "active":
                active_count += 1

            if gid in self.active_bars:
                bar = self.active_bars[gid]
                bar.update_progress(
                    completed=completed_len,
                    total=total_len,
                    speed=speed,
                    status=status,
                    error_msg=err_msg,
                )

        speed_mb = total_speed / (1024 * 1024)
        self.transfer_header.update(
            f"⬇️ Transfer Center & Download Queue ({len(self.app.active_downloads)} total, {active_count} active | {speed_mb:.2f} MB/s)"
        )
