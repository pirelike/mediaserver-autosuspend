"""
MediaServer AutoSuspend
----------------------

A Python package for automatically managing media server power states based on service activity.
"""

from pathlib import Path
import json
import logging
from typing import Dict, Any
from .version import __version__

# Core components
from mediaserver_autosuspend.suspension_manager import SuspensionManager
from mediaserver_autosuspend.config import load_config, ConfigurationError, ConfigurationManager # --CHANGED-- import from config module

# Service checkers (more organized imports) --CHANGED--
from mediaserver_autosuspend.services import (
    ServiceChecker, JellyfinChecker, PlexChecker, SonarrChecker, 
    RadarrChecker, NextcloudChecker, SystemChecker, create_service_checkers
)


# Package metadata
__version__ = "1.0.0" # --CHANGED--  Manage version elsewhere (e.g., separate file)
__author__ = "Pirelike"
__license__ = "MIT"

# Set up package-level logger
logger = logging.getLogger(__name__)



# Define package exports  --CHANGED-- more comprehensive list
__all__ = [
    "SuspensionManager",
    "load_config",
    "create_service_checkers",
    "ConfigurationError", # --CHANGED--
    "ConfigurationManager", # --CHANGED--
    "ServiceChecker",
    "JellyfinChecker",
    "PlexChecker",  # --CHANGED-- Include PlexChecker
    "SonarrChecker",
    "RadarrChecker",
    "NextcloudChecker",
    "SystemChecker",
]
