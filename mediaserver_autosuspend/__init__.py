"""
MediaServer AutoSuspend
----------------------

A Python package for automatically managing media server power states based on service activity.
"""

from pathlib import Path
import json
import logging
from typing import Dict, Any


# Core components
from mediaserver_autosuspend.suspension_manager import SuspensionManager
from mediaserver_autosuspend.config import load_config, ConfigurationError, ConfigurationManager

# Service checkers
from mediaserver_autosuspend.services import (
    ServiceChecker, JellyfinChecker, PlexChecker, SonarrChecker,
    RadarrChecker, NextcloudChecker, SystemChecker, create_service_checkers
)

from .version import __version__

__author__ = "Pirelike"
__license__ = "MIT"

# Set up package-level logger
logger = logging.getLogger(__name__)



# Define package exports
__all__ = [
    "SuspensionManager",
    "load_config",
    "create_service_checkers",
    "ConfigurationError",
    "ConfigurationManager",
    "ServiceChecker",
    "JellyfinChecker",
    "PlexChecker",
    "SonarrChecker",
    "RadarrChecker",
    "NextcloudChecker",
    "SystemChecker",
]
