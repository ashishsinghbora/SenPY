import json
import logging
import os
import secrets
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class DownloadItem(BaseModel):
    """Metadata for an individual download task."""
    url: str
    download_dir: Path
    filename: Optional[str] = None
    label: str = Field(default="")
    headers: Optional[List[str]] = None
    referer: Optional[str] = None


def download_hls_stream(item: DownloadItem, logger: Optional[logging.Logger] = None) -> bool:
    """Downloads an HLS (.m3u8) video stream using yt-dlp and re-assembles it into an MP4 container."""
    item.download_dir.mkdir(parents=True, exist_ok=True)
    out_file = item.download_dir / (item.filename or "video.mp4")

    headers_dict: Dict[str, str] = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Referer": item.referer or "https://gogoanime.to/",
    }
    if item.headers:
        for h in item.headers:
            if ": " in h:
                k, v = h.split(": ", 1)
                headers_dict[k.strip()] = v.strip()

    ydl_opts = {
        "outtmpl": str(out_file),
        "quiet": False,
        "no_warnings": True,
        "nocheckcertificate": True,
        "http_headers": headers_dict,
    }
    try:
        from yt_dlp import YoutubeDL
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([item.url])
        return out_file.exists() and out_file.stat().st_size > 0
    except Exception as e:
        if logger:
            logger.error(f"HLS download failed for {item.label or item.url}: {e}")
        return False


class Aria2RPCManager:
    """Manages aria2c daemon process and JSON-RPC communication."""

    def __init__(
        self,
        aria2_bin: Optional[str] = None,
        port: int = 6800,
        secret: Optional[str] = None,
        max_concurrent: int = 6,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.logger = logger or logging.getLogger(__name__)
        self.port = port
        self.secret = secret or secrets.token_hex(16)
        self.max_concurrent = max_concurrent
        self.aria2_bin = self._resolve_aria2_bin(aria2_bin)
        self.process: Optional[subprocess.Popen] = None
        self.rpc_url = f"http://localhost:{self.port}/jsonrpc"
        self._spawned_by_us = False

    def _resolve_aria2_bin(self, configured_path: Optional[str]) -> str:
        """Finds the aria2c executable in system path or standard directories."""
        if configured_path and Path(configured_path).is_file():
            return str(Path(configured_path).resolve())

        which_path = shutil.which("aria2c")
        if which_path:
            return which_path

        local_bin = Path.home() / ".local" / "bin" / "aria2c"
        if local_bin.is_file():
            return str(local_bin)

        return "aria2c"

    def is_daemon_alive(self) -> bool:
        """Checks if an aria2 RPC server is responding on the target port."""
        try:
            res = self.call("aria2.getVersion")
            return "version" in res
        except Exception:
            return False

    def ensure_daemon(self) -> None:
        """Starts the aria2c daemon if not already running."""
        if self.is_daemon_alive():
            self.logger.info(f"Existing Aria2 RPC server detected on port {self.port}")
            return

        cmd = [
            self.aria2_bin,
            "--enable-rpc=true",
            f"--rpc-listen-port={self.port}",
            f"--rpc-secret={self.secret}",
            f"--max-concurrent-downloads={self.max_concurrent}",
            "--rpc-allow-origin-all=true",
            "--daemon=false",
            "--quiet=true",
            "--no-conf=true",
            "--check-certificate=false",
            "--split=8",
            "--max-connection-per-server=8",
            "--min-split-size=1M",
        ]

        self.logger.info(f"Spawning local aria2c daemon on port {self.port}...")
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid if os.name != "nt" else None,
            )
            self._spawned_by_us = True
        except Exception as e:
            self.logger.error(f"Failed to spawn aria2c daemon ({cmd}): {e}")
            raise RuntimeError(f"Could not spawn aria2 daemon: {e}")

        # Wait for daemon to become ready
        for _ in range(30):
            time.sleep(0.2)
            if self.is_daemon_alive():
                self.logger.info("Aria2c RPC daemon successfully initialized.")
                return

        raise TimeoutError("Aria2 RPC daemon failed to start within timeout.")

    def call(self, method: str, params: Optional[List[Any]] = None) -> Any:
        """Executes a JSON-RPC method call over HTTP."""
        if params is None:
            params = []

        full_params: List[Any] = []
        if self.secret:
            full_params.append(f"token:{self.secret}")
        full_params.extend(params)

        payload = {
            "jsonrpc": "2.0",
            "id": "senpy",
            "method": method,
            "params": full_params,
        }

        req = Request(
            self.rpc_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        try:
            with urlopen(req, timeout=5) as response:
                result = json.loads(response.read().decode("utf-8"))
                if "error" in result:
                    raise RuntimeError(f"Aria2 RPC error: {result['error']}")
                return result.get("result")
        except URLError as e:
            raise ConnectionError(f"Failed to connect to Aria2 RPC at {self.rpc_url}: {e}")

    def add_download(self, item: DownloadItem) -> str:
        """Safely dispatches a download via RPC payload avoiding shell injection."""
        item.download_dir.mkdir(parents=True, exist_ok=True)
        options: Dict[str, Any] = {
            "dir": str(item.download_dir.resolve()),
        }
        if item.filename:
            options["out"] = item.filename

        # Always attach resilient User-Agent and Referer headers
        headers = list(item.headers) if item.headers else []
        if not any(h.lower().startswith("user-agent:") for h in headers):
            headers.append(f"User-Agent: {DEFAULT_USER_AGENT}")
        if not any(h.lower().startswith("referer:") for h in headers):
            ref = item.referer or "https://gogoanime.to/"
            headers.append(f"Referer: {ref}")
        options["header"] = headers

        gid = self.call("aria2.addUri", [[item.url], options])
        return str(gid)

    def tell_status(self, gid: str) -> Dict[str, Any]:
        """Gets detailed status of a specific download GID."""
        return self.call("aria2.tellStatus", [gid])

    def pause(self, gid: str) -> None:
        """Pauses a download task."""
        self.call("aria2.pause", [gid])

    def unpause(self, gid: str) -> None:
        """Resumes a paused download task."""
        self.call("aria2.unpause", [gid])

    def remove(self, gid: str) -> None:
        """Removes a download task."""
        self.call("aria2.remove", [gid])

    def shutdown(self) -> None:
        """Cleans up the daemon if we spawned it."""
        if self._spawned_by_us:
            try:
                self.call("aria2.shutdown")
            except Exception:
                pass
            if self.process:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=2)
                except Exception:
                    try:
                        self.process.kill()
                    except Exception:
                        pass
                self.process = None

    def download_with_progress(self, items: List[DownloadItem]) -> bool:
        """Dispatches download items and tracks live progress in the terminal."""
        if not items:
            return True

        # Process any HLS (.m3u8) streams via yt-dlp first
        hls_items = [it for it in items if ".m3u8" in it.url.lower()]
        aria_items = [it for it in items if ".m3u8" not in it.url.lower()]

        for hls_item in hls_items:
            print(f"\n>>> Downloading HLS stream for '{hls_item.label or hls_item.filename}' via yt-dlp...")
            download_hls_stream(hls_item, logger=self.logger)

        if not aria_items:
            return True

        self.ensure_daemon()

        # Setup GID map
        tasks: Dict[str, Dict[str, Any]] = {}
        for item in aria_items:
            gid = self.add_download(item)
            tasks[gid] = {
                "item": item,
                "retries": 0,
                "status": "waiting",
                "completed": 0,
                "total": 0,
                "speed": 0,
            }

        interrupted = False

        def sigint_handler(signum, frame):
            nonlocal interrupted
            interrupted = True
            print("\n>>> Pause/Cancel requested! Pausing active downloads...")
            for g in tasks.keys():
                try:
                    self.pause(g)
                except Exception:
                    pass

        prev_sigint = signal.signal(signal.SIGINT, sigint_handler)

        try:
            while tasks and not interrupted:
                completed_count = 0
                total_speed = 0

                for gid, data in list(tasks.items()):
                    try:
                        st = self.tell_status(gid)
                    except Exception as e:
                        continue

                    status = st.get("status")
                    completed_len = int(st.get("completedLength", 0))
                    total_len = int(st.get("totalLength", 0))
                    speed = int(st.get("downloadSpeed", 0))
                    connections = int(st.get("connections", 0))
                    total_speed += speed

                    data["completed"] = completed_len
                    data["total"] = total_len
                    data["speed"] = speed

                    if status == "complete":
                        completed_count += 1
                        tasks.pop(gid, None)
                    elif status == "error":
                        if data["retries"] < 2:
                            data["retries"] += 1
                            self.logger.warning(f"Download failed for {data['item'].label}, retrying ({data['retries']}/2)...")
                            new_gid = self.add_download(data["item"])
                            tasks[new_gid] = data
                            tasks.pop(gid, None)
                        else:
                            self.logger.error(f"Download failed permanently for {data['item'].label}: {st.get('errorMessage')}")
                            tasks.pop(gid, None)

                # Format terminal display
                active_count = len(tasks)
                speed_mb = total_speed / (1024 * 1024)
                status_line = (
                    f"\r\x1b[K>>> Downloading: {active_count} remaining | "
                    f"Speed: {speed_mb:.2f} MB/s"
                )
                sys.stdout.write(status_line)
                sys.stdout.flush()

                if not tasks:
                    break

                time.sleep(1)

            sys.stdout.write("\n")
            sys.stdout.flush()
            return not interrupted

        finally:
            signal.signal(signal.SIGINT, prev_sigint)
            if interrupted:
                print(">>> Downloads canceled by user.")
