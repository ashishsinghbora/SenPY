from pathlib import Path
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Input, Label


class SettingsScreen(Screen):
    """Configuration viewer and editor screen."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.email_input = Input(id="set-email")
        self.pass_input = Input(password=True, id="set-pass")
        self.dir_input = Input(id="set-dir")
        self.aria_input = Input(id="set-aria")
        self.concurrent_input = Input(id="set-concurrent")
        self.status_label = Label("", id="set-status")
        self.save_btn = Button("💾 Save Configuration", classes="action-btn", id="save-btn")

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="settings-container"):
            with Vertical(classes="panel-card"):
                yield Label("⚙️ Application Settings", classes="detail-title")
                yield Label("GoGoAnime Registered Email:", classes="form-label")
                yield self.email_input
                yield Label("GoGoAnime Password:", classes="form-label")
                yield self.pass_input
                yield Label("Anime Downloads Directory:", classes="form-label")
                yield self.dir_input
                yield Label("Aria2 Executable Binary Path:", classes="form-label")
                yield self.aria_input
                yield Label("Max Concurrent Downloads (1-16):", classes="form-label")
                yield self.concurrent_input
                yield self.status_label
                yield self.save_btn

    def on_screen_resume(self) -> None:
        cfg = self.app.config
        self.email_input.value = cfg.email
        self.pass_input.value = cfg.password
        self.dir_input.value = str(cfg.downloads_dir.resolve())
        self.aria_input.value = str(cfg.aria_2_path)
        self.concurrent_input.value = str(cfg.max_concurrent_downloads)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            self.save_config()

    def save_config(self) -> None:
        try:
            updates = {
                "EMAIL": self.email_input.value.strip(),
                "PASSWORD": self.pass_input.value.strip(),
                "DOWNLOADS_DIR": self.dir_input.value.strip(),
                "ARIA_2_PATH": self.aria_input.value.strip(),
                "MAX_CONCURRENT_DOWNLOADS": int(self.concurrent_input.value.strip() or 6),
            }
            self.app.config.write_config(updates)
            self.status_label.update("✅ Configuration saved successfully!")
        except Exception as e:
            self.status_label.update(f"❌ Error saving settings: {e}")
