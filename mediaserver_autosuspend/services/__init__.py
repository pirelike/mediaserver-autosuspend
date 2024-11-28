"""
MediaServer AutoSuspend Services Package.

This package provides service checkers for various media server components.
Each service checker implements the base ServiceChecker interface and
provides specific functionality for checking service activity.
"""

from mediaserver_autosuspend.services.base import ServiceChecker
from mediaserver_autosuspend.services.jellyfin import JellyfinChecker
from mediaserver_autosuspend.services.plex import PlexChecker
from mediaserver_autosuspend.services.sonarr import SonarrChecker
from mediaserver_autosuspend.services.radarr import RadarrChecker
from mediaserver_autosuspend.services.nextcloud import NextcloudChecker
from mediaserver_autosuspend.services.system import SystemChecker
from typing import Dict, Type, Any

# Registry of available service checkers
SERVICE_REGISTRY: Dict[str, Type[ServiceChecker]] = {
    'jellyfin': JellyfinChecker,
    'plex': PlexChecker,
    'sonarr': SonarrChecker,
    'radarr': RadarrChecker,
    'nextcloud': NextcloudChecker,
    'system': SystemChecker
}

# Service type categories
MEDIA_SERVICES = ['jellyfin', 'plex']
DOWNLOAD_SERVICES = ['sonarr', 'radarr']
SYSTEM_SERVICES = ['nextcloud', 'system']

def get_service_checker(service_name: str) -> Type[ServiceChecker]:
    """
    Get service checker class by name.
    
    Args:
        service_name: Name of the service checker to retrieve
        
    Returns:
        ServiceChecker class for the requested service
        
    Raises:
        KeyError: If service checker is not found
    """
    if service_name not in SERVICE_REGISTRY:
        raise KeyError(f"Service checker not found: {service_name}")
    return SERVICE_REGISTRY[service_name]

def create_service_checkers(config: Dict[str, Any]) -> Dict[str, ServiceChecker]:
    """
    Create instances of all enabled service checkers.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Dict mapping service names to checker instances
        
    Note:
        For media services (Jellyfin/Plex), only one should be enabled at a time
    """
    enabled_services = config.get('SERVICES', {})
    checkers = {}
    
    # Ensure only one media service is enabled
    active_media_services = [
        service for service in MEDIA_SERVICES
        if enabled_services.get(service, False)
    ]
    if len(active_media_services) > 1:
        raise ValueError(
            "Only one media service (Jellyfin or Plex) should be enabled at a time"
        )
    
    # Create enabled service checkers
    for service_name, checker_class in SERVICE_REGISTRY.items():
        # Skip if service is explicitly disabled
        if not enabled_services.get(service_name, True):
            continue
            
        # Skip if required configuration is missing
        try:
            checkers[service_name] = checker_class(config)
        except Exception as e:
            # Log warning but continue with other services
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Could not initialize {service_name} checker: {str(e)}"
            )
    
    return checkers

def register_service_checker(name: str, checker_class: Type[ServiceChecker]) -> None:
    """
    Register a new service checker.
    
    Args:
        name: Name for the service checker
        checker_class: ServiceChecker class to register
        
    Raises:
        ValueError: If name is already registered
        TypeError: If checker_class is not a ServiceChecker subclass
    """
    if name in SERVICE_REGISTRY:
        raise ValueError(f"Service checker already registered: {name}")
        
    if not issubclass(checker_class, ServiceChecker):
        raise TypeError("Checker class must inherit from ServiceChecker")
        
    SERVICE_REGISTRY[name] = checker_class

def get_service_category(service_name: str) -> str:
    """
    Get the category of a service.
    
    Args:
        service_name: Name of the service
        
    Returns:
        Category name ('media', 'download', or 'system')
    """
    if service_name in MEDIA_SERVICES:
        return 'media'
    elif service_name in DOWNLOAD_SERVICES:
        return 'download'
    elif service_name in SYSTEM_SERVICES:
        return 'system'
    else:
        return 'unknown'

def list_available_services() -> Dict[str, Dict[str, str]]:
    """
    Get list of available service checkers and their information.
    
    Returns:
        Dict mapping service names to their information including:
        - description: Service description
        - category: Service category
    """
    return {
        name: {
            'description': checker.__doc__ or "No description available",
            'category': get_service_category(name)
        }
        for name, checker in SERVICE_REGISTRY.items()
    }

__all__ = [
    'ServiceChecker',
    'JellyfinChecker',
    'PlexChecker',
    'SonarrChecker',
    'RadarrChecker',
    'NextcloudChecker',
    'SystemChecker',
    'get_service_checker',
    'create_service_checkers',
    'register_service_checker',
    'list_available_services',
    'get_service_category',
    'SERVICE_REGISTRY',
    'MEDIA_SERVICES',
    'DOWNLOAD_SERVICES',
    'SYSTEM_SERVICES'
]
