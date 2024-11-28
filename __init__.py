"""
MediaServer AutoSuspend
----------------------

A Python package for automatically managing media server power states based on service activity.
"""

from mediaserver_autosuspend.services.base import ServiceChecker
from mediaserver_autosuspend.services.jellyfin import JellyfinChecker
from mediaserver_autosuspend.services.sonarr import SonarrChecker
from mediaserver_autosuspend.services.radarr import RadarrChecker
from mediaserver_autosuspend.services.nextcloud import NextcloudChecker
from mediaserver_autosuspend.services.system import SystemChecker

__version__ = "1.0.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

__all__ = [
    "ServiceChecker",
    "JellyfinChecker",
    "SonarrChecker",
    "RadarrChecker",
    "NextcloudChecker",
    "SystemChecker",
]
