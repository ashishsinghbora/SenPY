from pathlib import Path
from typing import Optional, Union
import xml.etree.ElementTree as ET


def generate_episode_nfo(
    show_title: str,
    episode_title: str,
    season_num: int,
    episode_num: Union[int, float],
    plot: Optional[str] = None,
) -> str:
    """Generates standard Kodi/Jellyfin/Plex compatible XML NFO metadata content."""
    root = ET.Element("episodedetails")

    title_elem = ET.SubElement(root, "title")
    title_elem.text = episode_title

    show_elem = ET.SubElement(root, "showtitle")
    show_elem.text = show_title

    season_elem = ET.SubElement(root, "season")
    season_elem.text = str(season_num)

    ep_elem = ET.SubElement(root, "episode")
    ep_elem.text = str(episode_num)

    plot_elem = ET.SubElement(root, "plot")
    plot_elem.text = plot or f"{show_title} Episode {episode_num}"

    # Pretty print XML
    raw_xml = ET.tostring(root, encoding="utf-8", method="xml").decode("utf-8")
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n{raw_xml}'


def write_nfo_file(
    file_path: Path,
    show_title: str,
    episode_title: str,
    season_num: int,
    episode_num: Union[int, float],
    plot: Optional[str] = None,
) -> None:
    """Writes the generated XML NFO to the destination file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    content = generate_episode_nfo(
        show_title=show_title,
        episode_title=episode_title,
        season_num=season_num,
        episode_num=episode_num,
        plot=plot,
    )
    file_path.write_text(content, encoding="utf-8")
