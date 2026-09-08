from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Union
from pydantic import BaseModel, Field


class AnimeSearchResult(BaseModel):
    """Normalized anime search result."""
    id: str = Field(description="Unique anime identifier or slug")
    name: str = Field(description="Display title of the anime")
    released: Optional[str] = Field(default="Unknown", description="Release year or date")
    image: Optional[str] = Field(default="", description="Poster / thumbnail URL")
    url: Optional[str] = Field(default="", description="Full URL to category page")
    source: str = Field(default="gogo", description="Source provider identifier")


class EpisodeInfo(BaseModel):
    """Normalized episode metadata."""
    number: Union[int, float] = Field(description="Episode number (supports floats like 12.5)")
    url: str = Field(description="URL to the episode playback page")
    id: Optional[str] = Field(default=None, description="Optional episode identifier")
    title: Optional[str] = Field(default=None, description="Optional episode title")


class BaseSource(ABC):
    """Abstract Base Class for Anime Data & Stream Providers."""

    @abstractmethod
    def search(self, query: str) -> List[AnimeSearchResult]:
        """Searches for anime matching the query string.

        Args:
            query: The anime title to search.

        Returns:
            A list of AnimeSearchResult objects.
        """
        pass

    @abstractmethod
    def get_episodes(self, anime_id: str) -> List[EpisodeInfo]:
        """Fetches the list of all available episodes for the given anime ID.

        Args:
            anime_id: Identifier or slug of the anime.

        Returns:
            A list of EpisodeInfo objects sorted in ascending order.
        """
        pass

    @abstractmethod
    def get_stream_links(self, episode_url: str) -> Dict[str, str]:
        """Resolves stream and download URLs for an episode mapped by quality.

        Args:
            episode_url: Web page URL of the specific episode.

        Returns:
            A dictionary mapping quality labels (e.g., '1080p', '720p') to URLs.
        """
        pass
