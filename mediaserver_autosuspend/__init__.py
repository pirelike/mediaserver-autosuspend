"""
MediaServer AutoSuspend
----------------------

A Python package for automatically managing media server power states based on service activity.

This module provides a flexible framework for monitoring various media server services
(Jellyfin, Sonarr, Radarr, Nextcloud) and automatically suspending the system when idle.

Example usage:
    >>> from mediaserver_autosuspend import SuspensionManager, load_config
    >>> config = load_config('config.json')
    >>> manager = SuspensionManager(config)
    >>> manager.start_monitoring()
"""

from pathlib import Path
import json
import logging
from typing import Dict, Any

# Service checkers
from mediaserver_autosuspend.services.base import ServiceChecker
from mediaserver_autosuspend.services.jellyfin import JellyfinChecker
from mediaserver_autosuspend.services.sonarr import SonarrChecker
from mediaserver_autosuspend.services.radarr import RadarrChecker
from mediaserver_autosuspend.services.nextcloud import NextcloudChecker
from mediaserver_autosuspend.services.system import SystemChecker

# Core components
from mediaserver_autosuspend.suspension_manager import SuspensionManager

# Package metadata
__version__ = "1.0.0"
__author__ = "Pirelike"
__license__ = "MIT"

# Set up package-level logger
logger = logging.getLogger(__name__)

def load_config(config_path: str = None) -> Dict[str, Any]:
    """
    Load configuration from a JSON file.
    
    Args:
        config_path (str, optional): Path to config file. Defaults to searching standard locations.
    
    Returns:
        Dict[str, Any]: Configuration dictionary
        
    Raises:
        FileNotFoundError: If no config file is found
        json.JSONDecodeError: If config file is invalid JSON
    """
    if config_path is None:
        # Search standard locations
        search_paths = [
            Path.cwd() / "config.json",
            Path.home() / ".config" / "mediaserver-autosuspend" / "config.json",
            Path("/etc/mediaserver-autosuspend/config.json")
        ]
        
        for path in search_paths:
            if path.exists():
                config_path = path
                break
        else:
            raise FileNotFoundError("No configuration file found in standard locations")
    
    with open(config_path) as f:
        config = json.load(f)
    
    return config

def create_service_checkers(config: Dict[str, Any]) -> Dict[str, ServiceChecker]:
    """
    Create service checker instances based on configuration.
    
    Args:
        config (Dict[str, Any]): Configuration dictionary
    
    Returns:
        Dict[str, ServiceChecker]: Dictionary of service checker instances
    """
    services = {}
    service_map = {
        "jellyfin": JellyfinChecker,
        "sonarr": SonarrChecker,
        "radarr": RadarrChecker,
        "nextcloud": NextcloudChecker,
        "system": SystemChecker
    }
    
    enabled_services = config.get("SERVICES", {})
    
    for service_name, checker_class in service_map.items():
        if enabled_services.get(service_name, True):  # Enable by default
            services[service_name] = checker_class(config)
    
    return services

# Define package exports
__all__ = [
    "ServiceChecker",
    "JellyfinChecker",
    "SonarrChecker",
    "RadarrChecker",
    "NextcloudChecker",
    "SystemChecker",
    "SuspensionManager",
    "load_config",
    "create_service_checkers",
]
