from typing import Optional
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Label, ProgressBar, Static


class DownloadCard(Static):
    """Component to render individual download progress with speed and status."""

    def __init__(self, gid: str, label: str, filename: str, **kwargs) -> None:
        super().__init__(classes="dl-card", **kwargs)
        self.gid = gid
        self.label_text = label
        self.filename_text = filename
        self.header_label = Label(f"⬇️  {self.label_text} ({self.filename_text})", classes="dl-label")
        self.stat_label = Label("Waiting in queue...", classes="dl-speed")
        self.progress_bar = ProgressBar(total=100, show_eta=False)

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal():
                yield self.header_label
                yield self.stat_label
            yield self.progress_bar

    def update_progress(
        self,
        completed_bytes: int,
        total_bytes: int,
        speed_bytes: int,
        status: str,
    ) -> None:
        """Updates progress bar and status text."""
        if total_bytes > 0:
            percentage = min(100.0, (completed_bytes / total_bytes) * 100)
            self.progress_bar.progress = percentage
            comp_mb = completed_bytes / (1024 * 1024)
            tot_mb = total_bytes / (1024 * 1024)
            speed_mb = speed_bytes / (1024 * 1024)
            self.stat_label.update(
                f"[{status.upper()}] {percentage:.1f}% ({comp_mb:.1f}/{tot_mb:.1f} MB) @ {speed_mb:.2f} MB/s"
            )
        else:
            if status == "complete":
                self.progress_bar.progress = 100
                self.stat_label.update("[COMPLETE] 100% finished")
            elif status == "error":
                self.stat_label.update("[ERROR] Download failed")
            else:
                self.stat_label.update(f"[{status.upper()}] Initializing connection...")
