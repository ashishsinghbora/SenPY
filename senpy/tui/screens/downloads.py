from typing import Dict
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Label

from senpy.tui.widgets.download_item import DownloadCard


class DownloadsScreen(Screen):
    """Live Aria2 download dashboard with progress tracking."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.summary_label = Label("Total Speed: 0.00 MB/s | Active: 0 | Completed: 0", id="dl-summary")
        self.pause_btn = Button("⏸️ Pause All", classes="nav-btn", id="pause-btn")
        self.resume_btn = Button("▶️ Resume All", classes="nav-btn", id="resume-btn")
        self.cards_container = VerticalScroll(id="downloads-list")
        self.cards: Dict[str, DownloadCard] = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="downloads-container"):
            with Horizontal(id="downloads-header"):
                yield self.summary_label
                yield self.pause_btn
                yield self.resume_btn
            yield self.cards_container

    def on_mount(self) -> None:
        self.set_interval(1.0, self.refresh_download_stats)

    def on_screen_resume(self) -> None:
        self.sync_cards()

    def sync_cards(self) -> None:
        """Mounts UI cards for newly enqueued download items."""
        for gid, data in self.app.active_downloads.items():
            if gid not in self.cards:
                item = data["item"]
                card = DownloadCard(gid=gid, label=item.label, filename=item.filename or "video.mp4")
                self.cards[gid] = card
                self.cards_container.mount(card)

    def refresh_download_stats(self) -> None:
        """Polls Aria2 status non-blockingly."""
        self.sync_cards()
        if self.cards:
            self.poll_aria2_worker()

    @work(exclusive=True, thread=True)
    def poll_aria2_worker(self) -> None:
        """Worker thread to query Aria2 JSON-RPC without locking the UI."""
        total_speed = 0
        active_count = 0
        completed_count = 0

        updates = []
        for gid, card in list(self.cards.items()):
            try:
                st = self.app.rpc_manager.tell_status(gid)
                status = st.get("status", "waiting")
                completed = int(st.get("completedLength", 0))
                total = int(st.get("totalLength", 0))
                speed = int(st.get("downloadSpeed", 0))

                total_speed += speed
                if status == "active":
                    active_count += 1
                elif status == "complete":
                    completed_count += 1

                updates.append((card, completed, total, speed, status))
            except Exception:
                continue

        def _apply_updates():
            for card, completed, total, speed, status in updates:
                card.update_progress(completed, total, speed, status)

            speed_mb = total_speed / (1024 * 1024)
            self.summary_label.update(
                f"⚡ Total Speed: {speed_mb:.2f} MB/s | Active: {active_count} | Completed: {completed_count}"
            )

        self.app.call_from_thread(_apply_updates)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "pause-btn":
            self.pause_all()
        elif event.button.id == "resume-btn":
            self.resume_all()

    @work(exclusive=True, thread=True)
    def pause_all(self) -> None:
        for gid in self.cards.keys():
            try:
                self.app.rpc_manager.pause(gid)
            except Exception:
                pass

    @work(exclusive=True, thread=True)
    def resume_all(self) -> None:
        for gid in self.cards.keys():
            try:
                self.app.rpc_manager.unpause(gid)
            except Exception:
                pass
