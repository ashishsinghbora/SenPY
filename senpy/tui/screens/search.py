import re
from typing import List
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Input, Label, OptionList
from textual.widgets.option_list import Option

from senpy.sources.base import AnimeSearchResult
from senpy.tui.widgets.anime_card import AnimeCard


class SearchScreen(Screen):
    """Interactive anime search and preview screen."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.search_results: List[AnimeSearchResult] = []
        self.selected_anime: AnimeSearchResult = None
        self.search_input = Input(placeholder="🔍 Type anime title & press Enter to search...", id="search-input")
        self.results_list = OptionList(id="results-list")
        self.detail_card = AnimeCard(id="detail-pane")
        self.status_label = Label("Ready to search", id="search-status")

    def compose(self) -> ComposeResult:
        with Vertical(id="search-container"):
            yield self.search_input
            yield self.status_label
            with Horizontal(id="search-body"):
                yield self.results_list
                yield self.detail_card

    def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if query:
            self.perform_search(query)

    @work(exclusive=True, thread=True)
    def perform_search(self, query: str) -> None:
        """Asynchronous non-blocking worker for searching anime."""
        self.app.call_from_thread(self.status_label.update, f"Searching for '{query}'...")
        source = self.app.source
        results = source.search(query)

        # Fallback to metadata catalog if mirror returns 0 results
        if not results:
            meta = self.app.resolver.resolve_metadata(query)
            clean_title = meta.english_title or meta.title or query
            slug = re.sub(r"[^a-zA-Z0-9]+", "-", clean_title.lower()).strip("-")
            results = [
                AnimeSearchResult(
                    id=slug,
                    name=clean_title,
                    released=str(meta.year or "Unknown"),
                    source="catalog",
                )
            ]

        self.search_results = results

        def _update_ui() -> None:
            self.results_list.clear_options()
            for r in self.search_results:
                self.results_list.add_option(Option(f"🎬 {r.name} ({r.released})", id=r.id))
            self.status_label.update(f"Found {len(self.search_results)} result(s). Select an anime below.")
            if self.search_results:
                self.on_anime_highlighted(self.search_results[0])

        self.app.call_from_thread(_update_ui)

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        idx = event.option_index
        if 0 <= idx < len(self.search_results):
            self.on_anime_highlighted(self.search_results[idx])

    def on_anime_highlighted(self, anime: AnimeSearchResult) -> None:
        self.selected_anime = anime
        self.fetch_synopsis(anime)

    @work(exclusive=True, thread=True)
    def fetch_synopsis(self, anime: AnimeSearchResult) -> None:
        """Fetches metadata synopsis in background worker."""
        meta = self.app.resolver.resolve_metadata(anime.name)
        plot = meta.synopsis or "No synopsis available."
        self.app.call_from_thread(self.detail_card.update_anime, anime, plot)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        idx = event.option_index
        if 0 <= idx < len(self.search_results):
            anime = self.search_results[idx]
            self.app.selected_anime = anime
            self.app.switch_screen("episodes")
