__version__ = "1.4.0"
__author__ = "</Rudransh Joshi> (FireHead90544)"

from .config import GogoConfig
from .utils import GogoUtils
from .client import GogoClient
from .errors import *
from .sources import BaseSource, GogoSource, AnimeSearchResult, EpisodeInfo
from .extractors import M3U8Parser, EmbedExtractor
from .tui import SenpyApp, run_tui


