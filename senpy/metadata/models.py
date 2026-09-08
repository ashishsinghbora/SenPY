import re
from pathlib import Path
from typing import Optional, Union
from pydantic import BaseModel, Field


def sanitize_filename(name: str) -> str:
    """Sanitizes strings to be safe cross-platform folder and file names."""
    # Replace illegal filesystem characters with safe alternatives
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "Unknown"


class AnimeMetadata(BaseModel):
    """Normalized metadata for a series."""
    title: str = Field(description="Canonical or main display title")
    english_title: Optional[str] = Field(default=None, description="Official English title")
    season_number: int = Field(default=1, description="Resolved season index")
    total_episodes: Optional[int] = Field(default=None, description="Total episode count if known")
    synopsis: Optional[str] = Field(default="", description="Synopsis or plot overview")
    year: Optional[int] = Field(default=None, description="Release year")


class FormattedMediaPlan(BaseModel):
    """Planned output directory, filename, and NFO file path for media servers."""
    anime_title: str
    season_num: int
    ep_num: Union[int, float]
    episode_title: str
    output_dir: Path
    video_filename: str
    nfo_filename: str

    @property
    def target_video_path(self) -> Path:
        """Full destination path: {Output_Dir}/{Anime_Title}/Season {season:02d}/{filename}"""
        safe_title = sanitize_filename(self.anime_title)
        season_dir = f"Season {self.season_num:02d}"
        return self.output_dir / safe_title / season_dir / self.video_filename

    @property
    def target_nfo_path(self) -> Path:
        """Full destination path for NFO metadata."""
        safe_title = sanitize_filename(self.anime_title)
        season_dir = f"Season {self.season_num:02d}"
        return self.output_dir / safe_title / season_dir / self.nfo_filename
