from pathlib import Path
import json
import logging
import time
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup
from curl_cffi import requests
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .errors import InvalidCredentialsError


class SenpyConfig(BaseModel):
    """Pydantic model for application configuration."""
    EMAIL: str = "wihay47579@aregods.com"
    PASSWORD: str = "NeverGonnaGiveYouUp"
    DOWNLOADS_DIR: str = "downloads"
    ARIA_2_PATH: str = "aria2c"
    MAX_CONCURRENT_DOWNLOADS: int = 6
    ARIA_RPC_PORT: int = 6800
    ARIA_RPC_SECRET: Optional[str] = None
    CUSTOM_GOGO_URL: Optional[str] = None


class GogoConfig:
    """A configuration class for GoGoAnime, 
    which will be used to log in and get the required cookies for downloads,
    the csrf token and the current gogoanime url, and
    managing the config file.
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.setup_logger()
        self.cookie_path = Path.home() / ".senpy" / "cookies.json"
        self.config_path = self.get_config_path()
        self.loaded_config: Dict[str, Any] = json.load(open(self.config_path))
        self.config_model = SenpyConfig.model_validate(self.loaded_config)

        self.email: str = self.config_model.EMAIL
        self.password: str = self.config_model.PASSWORD
        self.downloads_dir: Path = Path(self.config_model.DOWNLOADS_DIR)
        self.aria_2_path: Path = Path(self.config_model.ARIA_2_PATH)
        self.max_concurrent_downloads: int = self.config_model.MAX_CONCURRENT_DOWNLOADS

        # Modernized session with curl_cffi for Cloudflare TLS fingerprint resistance
        self.session: requests.Session = requests.Session(impersonate="chrome120", verify=False)
        self.session.headers["Accept-Encoding"] = "identity"

        self.MAIN_URL: str = "https://raw.githubusercontent.com/FireHead90544/SenPY/main/CURRENT_URL.txt"
        self.CURRENT_URL: str = ""
        self.get_current_url()
        self.cookies: Dict[str, str] = {}
        self.config_updates: Dict[str, Any] = {}
        self.stylesheet = {
            "questionmark": "#16C60C bold",
            "answermark": "#e0af68",
            "answer": "#E5E512",
            "input": "#98c379",
            "question": "#E74856 bold",
            "answered_question": "",
            "instruction": "#a9b1d6",
            "long_instruction": "#a9b1d6",
            "pointer": "#3A96DD",
            "checkbox": "#9ece6a",
            "separator": "",
            "skipped": "#48444c",
            "validator": "",
            "marker": "#9ece6a",
            "fuzzy_prompt": "#bb9af7",
            "fuzzy_info": "#a9b1d6",
            "fuzzy_border": "#343740",
            "fuzzy_match": "#bb9af7",
            "spinner_pattern": "#9ece6a",
            "spinner_text": "",
        }

    def setup_logger(self) -> None:
        """Sets up the logger's configurations."""
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            formatter = logging.Formatter("[ %(asctime)s ] -  %(name)s | %(levelname)s | - %(message)s")
            file_handler = logging.FileHandler(Path.cwd() / "senpy.log", mode="a")
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

    def get_config_path(self) -> Path:
        """Returns the path to the config file."""
        start = time.perf_counter()
        local_cwd = Path.cwd() / "config.json"
        local_parent = Path.cwd().parent / "config.json"
        global_config = Path.home() / ".senpy" / "config.json"

        if local_cwd.exists():
            self.config_path = local_cwd
        elif local_parent.exists():
            self.config_path = local_parent
        elif global_config.exists():
            self.config_path = global_config
        else:
            self.logger.info(f'No config file found, creating one at "{global_config.resolve()}"')
            global_config.parent.mkdir(parents=True, exist_ok=True)
            default_config = {
                "EMAIL": "wihay47579@aregods.com",
                "PASSWORD": "NeverGonnaGiveYouUp",
                "DOWNLOADS_DIR": str(Path.cwd() / "downloads"),
                "ARIA_2_PATH": "aria2c",
                "MAX_CONCURRENT_DOWNLOADS": 6,
                "ARIA_RPC_PORT": 6800,
                "ARIA_RPC_SECRET": None,
            }
            with open(global_config, "w") as f:
                json.dump(default_config, f, indent=2, sort_keys=True)
            self.logger.warning("Make sure to update your config file before trying to download anything.")
            self.config_path = global_config

        self.logger.info(f'({round(time.perf_counter() - start, 2)}s) Config file found at "{self.config_path.resolve()}"')
        return self.config_path

    def request_with_retry(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        """Executes an HTTP request with exponential backoff retries for transient 5xx/429 errors."""
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=4),
            retry=retry_if_exception_type((requests.exceptions.RequestException, Exception)),
            reraise=True,
        )
        def _exec() -> requests.Response:
            resp = self.session.request(method, url, **kwargs)
            if resp.status_code in (429, 500, 502, 503, 504):
                self.logger.warning(f"Transient HTTP status {resp.status_code} for {url}, retrying...")
                raise requests.exceptions.RequestException(f"HTTP {resp.status_code}")
            return resp

        return _exec()

    def load_cached_cookies(self) -> Dict[str, str]:
        """Loads cached cookies from disk if available."""
        if not self.cookie_path.exists():
            return {}
        try:
            with open(self.cookie_path, "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    for k, v in data.items():
                        if v:
                            self.session.cookies.set(k, v)
                    return data
        except Exception as e:
            self.logger.warning(f"Failed to load cached cookies from {self.cookie_path}: {e}")
        return {}

    def save_cookies(self, cookies: Dict[str, str]) -> None:
        """Saves cookies to disk cache."""
        try:
            self.cookie_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cookie_path, "w") as f:
                json.dump(cookies, f, indent=2)
            self.logger.info(f"Cached cookies saved to {self.cookie_path}")
        except Exception as e:
            self.logger.warning(f"Failed to save cookies to {self.cookie_path}: {e}")

    def is_session_authenticated(self) -> bool:
        """Tests validity of session cookies against an authenticated endpoint."""
        if not self.session.cookies.get("auth"):
            return False
        try:
            test_url = f"{self.CURRENT_URL}/user/bookmark"
            resp = self.request_with_retry("GET", test_url, allow_redirects=False, timeout=8)
            if resp.status_code in (401, 403):
                return False
            if resp.status_code == 302 and "login" in resp.headers.get("location", "").lower():
                return False
            return True
        except Exception as e:
            self.logger.debug(f"Auth check encountered exception: {e}")
            return False

    def get_cookies(self) -> Dict[str, str]:
        """Returns the cookies for session, utilizing persistent cookie caching."""
        start = time.perf_counter()
        cached = self.load_cached_cookies()
        if cached and self.is_session_authenticated():
            self.cookies = cached
            self.logger.info(f"({round(time.perf_counter() - start, 2)}s) Reused cached session cookies.")
            return self.cookies

        try:
            csrf_token = self.get_csrf_token()
            login_resp = self.request_with_retry(
                "POST",
                f"{self.CURRENT_URL}/login.html",
                data={
                    "email": self.email,
                    "password": self.password,
                    "_csrf": csrf_token,
                },
                timeout=10,
            )

            if login_resp.status_code in (401, 403):
                self.logger.critical("Invalid credentials or access denied.")
                raise InvalidCredentialsError(
                    f'Invalid Credentials Provided, Please Correct Them !!! Config File at "{self.config_path.resolve()}"'
                )

            self.cookies["gogoanime"] = self.session.cookies.get("gogoanime") or ""
            self.cookies["auth"] = self.session.cookies.get("auth") or ""

            if not self.cookies["auth"]:
                self.logger.warning("Auth cookie missing after login attempt.")
            else:
                self.save_cookies(self.cookies)

            self.logger.info(f"({round(time.perf_counter() - start, 2)}s) Successfully fetched cookies for the session.")
            return self.cookies
        except InvalidCredentialsError:
            raise
        except Exception as e:
            self.logger.error(f"Error during login/fetching cookies: {e}")
            return self.cookies

    def get_current_url(self) -> str:
        """Returns the current gogoanime url with the current domain."""
        if hasattr(self, "config_model") and self.config_model.CUSTOM_GOGO_URL:
            self.CURRENT_URL = self.config_model.CUSTOM_GOGO_URL.rstrip("/")
            return self.CURRENT_URL

        try:
            resp = self.request_with_retry("GET", self.MAIN_URL, timeout=8)
            url_text = resp.text.split("\n")[0].strip()
            if url_text.startswith("http"):
                self.CURRENT_URL = url_text.rstrip("/")
                return self.CURRENT_URL
        except Exception as e:
            self.logger.warning(f"Could not fetch CURRENT_URL from remote: {e}")

        # Fallback to local CURRENT_URL.txt if remote fetch fails
        local_current_url = Path.cwd() / "CURRENT_URL.txt"
        if local_current_url.exists():
            content = local_current_url.read_text().split("\n")[0].strip()
            if content.startswith("http"):
                self.CURRENT_URL = content.rstrip("/")
                return self.CURRENT_URL

        self.CURRENT_URL = "https://anitaku.bz"
        return self.CURRENT_URL

    def get_csrf_token(self) -> str:
        """Returns the CSRF token for logging in."""
        try:
            resp = self.request_with_retry("GET", f"{self.CURRENT_URL}/login.html", timeout=10)
            soup = BeautifulSoup(resp.content, "html.parser")
            tags = soup.select("meta[name='csrf-token']")
            if tags and "content" in tags[0].attrs:
                return tags[0]["content"]
        except Exception as e:
            self.logger.error(f"Failed to fetch CSRF token: {e}")
        return ""

    def write_config(self, new: Dict[str, Any]) -> None:
        """Updates the config file with the new configuration."""
        self.loaded_config.update(new)
        with open(self.config_path, "w") as f:
            json.dump(self.loaded_config, f, indent=4, sort_keys=True)
        self.refresh_config()

    def refresh_config(self) -> None:
        """Refreshes the config variables from the loaded config."""
        self.config_model = SenpyConfig.model_validate(self.loaded_config)
        self.email = self.config_model.EMAIL
        self.password = self.config_model.PASSWORD
        self.downloads_dir = Path(self.config_model.DOWNLOADS_DIR)
        self.aria_2_path = Path(self.config_model.ARIA_2_PATH)
        self.max_concurrent_downloads = self.config_model.MAX_CONCURRENT_DOWNLOADS
