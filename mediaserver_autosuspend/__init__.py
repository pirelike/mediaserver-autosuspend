"""
MediaServer AutoSuspend
----------------------

A Python package for automatically managing media server power states based on service activity.

This module serves as the main entry point for the package, exposing key functionality
and components while managing internal imports and version information.

Example:
    >>> from mediaserver_autosuspend import SuspensionManager, load_config
    >>> config = load_config()
    >>> services = create_service_checkers(config)
    >>> manager = SuspensionManager(config, services)
"""

import logging
from pathlib import Path
from typing import Dict, Any

# Import core components
from mediaserver_autosuspend.suspension_manager import SuspensionManager
from mediaserver_autosuspend.config import (
    load_config,
    ConfigurationError,
    ConfigurationManager,
    DEFAULT_CONFIG
)
from mediaserver_autosuspend.logger import setup_logging, LogManager

# Import service-related components
from mediaserver_autosuspend.services import (
    ServiceChecker,
    JellyfinChecker,
    PlexChecker,
    SonarrChecker,
    RadarrChecker,
    NextcloudChecker,
    SystemChecker,
    create_service_checkers,
    get_service_checker,
    register_service_checker,
    list_available_services
)

# Import utility functions
from mediaserver_autosuspend.utils.process import (
    check_single_instance,
    get_process_info,
    is_process_running,
    write_pid_file
)

# Import version information
from mediaserver_autosuspend.version import __version__

# Package metadata
__title__ = "mediaserver-autosuspend"
__author__ = "Your Name"
__license__ = "MIT"
__copyright__ = "Copyright 2024 Your Name"

# Set up package-level logger
logger = logging.getLogger(__name__)

# Define package exports
__all__ = [
    # Core components
    "SuspensionManager",
    "load_config",
    "setup_logging",
    "ConfigurationManager",
    "ConfigurationError",
    "DEFAULT_CONFIG",
    "LogManager",
    
    # Service components
    "ServiceChecker",
    "JellyfinChecker",
    "PlexChecker",
    "SonarrChecker",
    "RadarrChecker",
    "NextcloudChecker",
    "SystemChecker",
    "create_service_checkers",
    "get_service_checker",
    "register_service_checker",
    "list_available_services",
    
    # Utility functions
    "check_single_instance",
    "get_process_info",
    "is_process_running",
    "write_pid_file",
    
    # Version and metadata
    "__version__",
    "__title__",
    "__author__",
    "__license__",
    "__copyright__"
]

def get_package_root() -> Path:
    """
    Get the root directory of the package installation.
    
    Returns:
        Path: Package root directory
    """
    return Path(__file__).parent

def get_config_paths() -> Dict[str, Path]:
    """
    Get standard configuration file paths.
    
    Returns:
        Dict mapping location names to Path objects
    """
    return {
        'system': Path('/etc/mediaserver-autosuspend/config.json'),
        'user': Path.home() / '.config/mediaserver-autosuspend/config.json',
        'local': get_package_root() / 'config.json'
    }

# Initialize package
def initialize_package() -> None:
    """
    Perform any necessary package initialization.
    
    This function is called automatically when the package is imported.
    It sets up basic logging and performs any required initialization.
    """
    # Set up basic console logging (can be overridden by setup_logging)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.debug("MediaServer AutoSuspend package initialized")

# Run initialization
initialize_package()
