from typing import Optional
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Label, ProgressBar, Static


class DownloadBar(Static):
    """Real-time progress item showing filename, speed, ETA, and status badge."""

    def __init__(
        self,
        gid: str,
        filename: str,
        label: str = "",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.gid = gid
        self.filename = filename
        self.item_label = label or filename
        self.status = "Queued"

        self.title_widget = Label(self.item_label, classes="dl-title")
        self.badge_widget = Label("Queued", classes="dl-badge badge-queued")
        self.progress_bar = ProgressBar(total=100, show_eta=False, classes="dl-bar")
        self.stats_widget = Label("0 MB / 0 MB | 0.00 MB/s | ETA: --", classes="dl-stats")

    def compose(self) -> ComposeResult:
        with Vertical(classes="download-card"):
            with Horizontal(classes="dl-header"):
                yield self.title_widget
                yield self.badge_widget
            yield self.progress_bar
            yield self.stats_widget

    def update_progress(
        self,
        completed: int,
        total: int,
        speed: int,
        status: str,
        error_msg: Optional[str] = None,
    ) -> None:
        """Updates UI elements with live transmission statistics."""
        self.status = status

        # Format sizes
        completed_mb = completed / (1024 * 1024)
        total_mb = total / (1024 * 1024) if total > 0 else 0
        speed_mb = speed / (1024 * 1024)

        # Calculate progress percent & ETA
        if total > 0:
            pct = min(100.0, (completed / total) * 100)
            self.progress_bar.progress = pct
            if speed > 0:
                remaining_bytes = total - completed
                eta_sec = int(remaining_bytes / speed)
                m, s = divmod(eta_sec, 60)
                eta_str = f"{m}m {s}s" if m > 0 else f"{s}s"
            else:
                eta_str = "--"
            stats_text = f"{completed_mb:.1f} MB / {total_mb:.1f} MB ({pct:.1f}%) | {speed_mb:.2f} MB/s | ETA: {eta_str}"
        else:
            self.progress_bar.progress = 0
            stats_text = f"{completed_mb:.1f} MB | {speed_mb:.2f} MB/s | ETA: --"

        if error_msg:
            stats_text = f"Error: {error_msg}"

        self.stats_widget.update(stats_text)

        # Update badge class and text
        self.badge_widget.remove_class("badge-queued", "badge-downloading", "badge-finished", "badge-error")
        clean_status = status.lower()
        if clean_status in ["active", "downloading"]:
            self.badge_widget.update("Downloading")
            self.badge_widget.add_class("badge-downloading")
        elif clean_status in ["complete", "finished"]:
            self.progress_bar.progress = 100
            self.badge_widget.update("Finished")
            self.badge_widget.add_class("badge-finished")
            self.stats_widget.update(f"{total_mb:.1f} MB / {total_mb:.1f} MB (100%) | Complete")
        elif clean_status in ["error", "failed"]:
            self.badge_widget.update("Error")
            self.badge_widget.add_class("badge-error")
        else:
            self.badge_widget.update("Queued")
            self.badge_widget.add_class("badge-queued")
