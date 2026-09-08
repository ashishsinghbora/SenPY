import argparse
from pathlib import Path
import re
import sys
from typing import List, Optional

from colorama import Fore, init

from senpy import __version__
from senpy.config import GogoConfig
from senpy.downloader.aria2_rpc import Aria2RPCManager, DownloadItem
from senpy.metadata.nfo import write_nfo_file
from senpy.metadata.resolver import MetadataResolver
from senpy.sources.base import AnimeSearchResult, EpisodeInfo
from senpy.sources.gogo import GogoSource
from senpy.utils import GogoUtils

init(autoreset=True)


def build_parser() -> argparse.ArgumentParser:
    """Builds the argument parser for headless CLI execution."""
    parser = argparse.ArgumentParser(
        prog="senpy",
        description="SenPY: Modern, Hardened Anime Automation Engine & Downloader",
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Download subcommand
    dl_parser = subparsers.add_parser("download", help="Download anime episodes headlessly")
    dl_parser.add_argument("title", type=str, help="Anime title or search query")
    dl_parser.add_argument(
        "-e",
        "--episodes",
        type=str,
        default="all",
        help="Episode numbers/range to download (e.g., '1-12', '1,3,5', '12.5', 'all')",
    )
    dl_parser.add_argument(
        "-q",
        "--quality",
        type=str,
        default="1080p",
        help="Preferred download quality (e.g., '1080p', '720p', '480p', '360p')",
    )
    dl_parser.add_argument(
        "--dir",
        "--output-dir",
        dest="output_dir",
        type=str,
        default=None,
        help="Target downloads directory (defaults to config DOWNLOADS_DIR)",
    )
    dl_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Bypass interactive prompts and confirm actions",
    )
    dl_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution, resolve metadata and plan paths without downloading",
    )
    dl_parser.add_argument(
        "--write-nfo",
        action="store_true",
        help="Generate Kodi/Jellyfin compatible .nfo metadata alongside video files",
    )
    dl_parser.add_argument(
        "--season",
        type=int,
        default=None,
        help="Override season number for media server naming",
    )
    dl_parser.add_argument(
        "--rpc-port",
        type=int,
        default=None,
        help="Custom Aria2 JSON-RPC listen port",
    )

    return parser


def run_download_cli(args: argparse.Namespace) -> int:
    """Executes headless download flow."""
    config = GogoConfig()
    utils = GogoUtils()
    source = GogoSource(config=config)
    resolver = MetadataResolver(session=config.session)

    query = args.title
    print(f"{Fore.CYAN}>>> Searching anime matching: '{query}'...")
    search_results = source.search(query)

    if not search_results:
        if args.dry_run:
            meta = resolver.resolve_metadata(query)
            selected_name = meta.english_title or meta.title or query
            safe_slug = re.sub(r"[^a-zA-Z0-9]+", "-", selected_name.lower()).strip("-")
            total_eps = meta.total_episodes or 37
            print(f"{Fore.YELLOW}>>> Scraper returned 0 results; using metadata catalog for dry-run plan.")
            print(f"{Fore.GREEN}>>> Resolved Series: {Fore.WHITE}{selected_name} (Estimated eps: {total_eps})")
            selected = AnimeSearchResult(id=safe_slug, name=selected_name, released=str(meta.year or "Unknown"))
            all_episodes = [
                EpisodeInfo(number=i, url=f"{config.CURRENT_URL}/{safe_slug}-episode-{i}")
                for i in range(1, total_eps + 1)
            ]
        else:
            print(f"{Fore.RED}>>> Error: No anime found matching '{query}'.")
            return 1
    else:
        # Select best match
        selected = search_results[0]
        print(f"{Fore.GREEN}>>> Found: {Fore.WHITE}{selected.name} [Released: {selected.released}] (ID: {selected.id})")

        # Fetch available episodes
        print(f"{Fore.CYAN}>>> Fetching episodes list...")
        all_episodes = source.get_episodes(selected.id)
        if not all_episodes:
            if args.dry_run:
                meta = resolver.resolve_metadata(selected.name)
                total_eps = meta.total_episodes or 24
                all_episodes = [
                    EpisodeInfo(number=i, url=f"{config.CURRENT_URL}/{selected.id}-episode-{i}")
                    for i in range(1, total_eps + 1)
                ]
            else:
                print(f"{Fore.RED}>>> Error: No episodes found for anime '{selected.name}'.")
                return 1

    available_numbers = [ep.number for ep in all_episodes]

    # Resolve target episodes
    if args.episodes.lower() == "all":
        target_numbers = available_numbers
    else:
        target_numbers = utils.string_to_sequence(args.episodes)

    target_episodes = [ep for ep in all_episodes if ep.number in target_numbers]
    if not target_episodes:
        print(f"{Fore.RED}>>> Error: Requested episodes ({args.episodes}) not available.")
        return 1

    print(f"{Fore.GREEN}>>> Target episodes ({len(target_episodes)}): {[ep.number for ep in target_episodes]}")

    # Output directory
    base_out_dir = Path(args.output_dir) if args.output_dir else config.downloads_dir
    preferred_quality = args.quality.lower()
    if not preferred_quality.endswith("p"):
        preferred_quality = f"{preferred_quality}p"

    # Plan downloads
    planned_items: List[DownloadItem] = []
    print(f"{Fore.CYAN}>>> Resolving stream links & media server destinations (Preferred: {preferred_quality})...")

    for ep in target_episodes:
        # Plan path using standardizer
        plan = resolver.plan_media_destination(
            anime_title=selected.name,
            ep_num=ep.number,
            output_dir=base_out_dir,
            season_num=args.season,
        )

        if args.dry_run:
            print(f"  [DRY RUN] Episode {ep.number}:")
            print(f"    Target Video: {plan.target_video_path}")
            if args.write_nfo:
                print(f"    Target NFO:   {plan.target_nfo_path}")
            continue

        # Fetch stream links
        stream_links = source.get_stream_links(ep.url)
        if not stream_links:
            print(f"{Fore.YELLOW}  [!] Warning: No stream links found for Episode {ep.number}. Skipping.")
            continue

        chosen_quality = source.select_best_quality(stream_links, preferred_quality)
        stream_url = stream_links[chosen_quality]
        print(f"  [+] Ep {ep.number} -> Quality: {chosen_quality} | File: {plan.video_filename}")

        if args.write_nfo:
            write_nfo_file(
                file_path=plan.target_nfo_path,
                show_title=plan.anime_title,
                episode_title=plan.episode_title,
                season_num=plan.season_num,
                episode_num=plan.ep_num,
            )

        planned_items.append(
            DownloadItem(
                url=stream_url,
                download_dir=plan.target_video_path.parent,
                filename=plan.video_filename,
                label=f"{plan.anime_title} E{plan.ep_num}",
                referer=config.CURRENT_URL,
            )
        )

    if args.dry_run:
        print(f"{Fore.GREEN}>>> Dry run complete. {len(target_episodes)} episode(s) planned successfully.")
        return 0

    if not planned_items:
        print(f"{Fore.RED}>>> Error: No valid download links could be resolved.")
        return 1

    # Dispatch download via Aria2 RPC
    rpc_port = args.rpc_port or config.config_model.ARIA_RPC_PORT
    manager = Aria2RPCManager(
        aria2_bin=str(config.aria_2_path),
        port=rpc_port,
        secret=config.config_model.ARIA_RPC_SECRET,
        max_concurrent=config.max_concurrent_downloads,
        logger=config.logger,
    )

    try:
        print(f"{Fore.GREEN}>>> Dispatching {len(planned_items)} download(s) to Aria2 JSON-RPC daemon...")
        success = manager.download_with_progress(planned_items)
        if success:
            print(f"{Fore.GREEN}>>> All downloads completed successfully!")
            return 0
        else:
            print(f"{Fore.YELLOW}>>> Downloads stopped or interrupted.")
            return 1
    finally:
        manager.shutdown()


def run_cli(argv: Optional[List[str]] = None) -> int:
    """Entry point for command line arguments."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "download":
        return run_download_cli(args)
    else:
        parser.print_help()
        return 0
