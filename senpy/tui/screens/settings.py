from pathlib import Path
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label


class SettingsModal(ModalScreen):
    """Configuration modal screen for adjusting downloads directory, Aria2 path, and concurrency."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.dir_input = Input(id="set-dir", classes="modal-input")
        self.aria_input = Input(id="set-aria", classes="modal-input")
        self.concurrent_input = Input(id="set-concurrent", classes="modal-input")
        self.email_input = Input(id="set-email", classes="modal-input")
        self.pass_input = Input(password=True, id="set-pass", classes="modal-input")
        self.status_label = Label("", id="set-status")
        self.save_btn = Button("💾 Save Settings", variant="primary", id="btn-save-settings")
        self.close_btn = Button("✖️ Close", id="btn-close-settings")

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-modal-dialog"):
            yield Label("⚙️ Application Settings", classes="modal-title")
            with VerticalScroll(classes="modal-scroll"):
                yield Label("Anime Downloads Directory:", classes="form-label")
                yield self.dir_input
                yield Label("Aria2 Executable Binary Path:", classes="form-label")
                yield self.aria_input
                yield Label("Max Concurrent Downloads (1-16):", classes="form-label")
                yield self.concurrent_input
                yield Label("GoGoAnime Registered Email (Optional):", classes="form-label")
                yield self.email_input
                yield Label("GoGoAnime Password (Optional):", classes="form-label")
                yield self.pass_input
                yield self.status_label
            with Horizontal(classes="modal-buttons"):
                yield self.save_btn
                yield self.close_btn

    def on_mount(self) -> None:
        cfg = self.app.config
        self.dir_input.value = str(cfg.downloads_dir.resolve())
        self.aria_input.value = str(cfg.aria_2_path)
        self.concurrent_input.value = str(cfg.max_concurrent_downloads)
        self.email_input.value = cfg.email or ""
        self.pass_input.value = cfg.password or ""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save-settings":
            self.save_config()
        elif event.button.id == "btn-close-settings":
            self.app.pop_screen()

    def save_config(self) -> None:
        try:
            concurrent_val = int(self.concurrent_input.value.strip() or 6)
            updates = {
                "DOWNLOADS_DIR": self.dir_input.value.strip(),
                "ARIA_2_PATH": self.aria_input.value.strip(),
                "MAX_CONCURRENT_DOWNLOADS": min(16, max(1, concurrent_val)),
                "EMAIL": self.email_input.value.strip(),
                "PASSWORD": self.pass_input.value.strip(),
            }
            self.app.config.write_config(updates)
            self.status_label.update("✅ Configuration saved successfully!")
            self.set_timer(1.2, self.app.pop_screen)
        except Exception as e:
            self.status_label.update(f"❌ Error saving settings: {e}")


SettingsScreen = SettingsModal
