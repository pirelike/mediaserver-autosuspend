"""
MediaServer AutoSuspend Services Package
--------------------------------------

This package provides service checkers for various media server and related services.
It includes a plugin system for easy addition of new service checkers.

Available service checkers:
- JellyfinChecker: Monitors Jellyfin media server activity
- PlexChecker: Monitors Plex media server activity
- SonarrChecker: Monitors Sonarr download queue
- RadarrChecker: Monitors Radarr download queue
- NextcloudChecker: Monitors Nextcloud activity
- SystemChecker: Monitors system-level activity
"""

import logging
from typing import Dict, Any, Type, Optional

# Import base service checker
from mediaserver_autosuspend.services.base import (
    ServiceChecker,
    ServiceCheckError,
    ServiceConfigError,
    ServiceConnectionError
)

# Import individual service checkers
from mediaserver_autosuspend.services.jellyfin import JellyfinChecker
from mediaserver_autosuspend.services.plex import PlexChecker
from mediaserver_autosuspend.services.sonarr import SonarrChecker
from mediaserver_autosuspend.services.radarr import RadarrChecker
from mediaserver_autosuspend.services.nextcloud import NextcloudChecker
from mediaserver_autosuspend.services.system import SystemChecker

logger = logging.getLogger(__name__)

# Registry of available service checkers
SERVICE_CHECKERS: Dict[str, Type[ServiceChecker]] = {
    'jellyfin': JellyfinChecker,
    'plex': PlexChecker,
    'sonarr': SonarrChecker,
    'radarr': RadarrChecker,
    'nextcloud': NextcloudChecker,
    'system': SystemChecker
}

def register_service_checker(name: str, checker_class: Type[ServiceChecker]) -> None:
    """
    Register a new service checker.
    
    Args:
        name: Service identifier
        checker_class: ServiceChecker subclass to register
        
    Raises:
        ValueError: If checker_class is not a ServiceChecker subclass
    """
    if not issubclass(checker_class, ServiceChecker):
        raise ValueError("Checker class must inherit from ServiceChecker")
        
    SERVICE_CHECKERS[name] = checker_class
    logger.debug(f"Registered service checker: {name}")

def get_service_checker(name: str) -> Optional[Type[ServiceChecker]]:
    """
    Get a service checker class by name.
    
    Args:
        name: Service identifier
        
    Returns:
        ServiceChecker subclass if found, None otherwise
    """
    return SERVICE_CHECKERS.get(name)

def list_available_services() -> Dict[str, str]:
    """
    Get list of available service checkers.
    
    Returns:
        Dict mapping service names to their descriptions
    """
    return {
        name: checker.__doc__ or "No description available"
        for name, checker in SERVICE_CHECKERS.items()
    }

def create_service_checkers(config: Dict[str, Any]) -> Dict[str, ServiceChecker]:
    """
    Create service checker instances based on configuration.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Dict mapping service names to checker instances
        
    Raises:
        ServiceConfigError: If service configuration is invalid
    """
    enabled_services = config.get('SERVICES', {})
    checkers = {}
    
    for service_name, enabled in enabled_services.items():
        if not enabled:
            continue
            
        checker_class = get_service_checker(service_name)
        if not checker_class:
            logger.warning(f"Unknown service: {service_name}")
            continue
            
        try:
            checker = checker_class(config)
            checkers[service_name] = checker
            logger.info(f"Initialized {service_name} checker")
        except Exception as e:
            logger.error(f"Failed to initialize {service_name} checker: {e}")
            if config.get('DEBUG_MODE'):
                raise
    
    return checkers

# Package exports
__all__ = [
    # Base classes and exceptions
    'ServiceChecker',
    'ServiceCheckError',
    'ServiceConfigError',
    'ServiceConnectionError',
    
    # Service checkers
    'JellyfinChecker',
    'PlexChecker',
    'SonarrChecker',
    'RadarrChecker',
    'NextcloudChecker',
    'SystemChecker',
    
    # Service management functions
    'create_service_checkers',
    'register_service_checker',
    'get_service_checker',
    'list_available_services',
    
    # Service registry
    'SERVICE_CHECKERS'
]
