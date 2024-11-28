"""
MediaServer AutoSuspend Services Package.

This package provides service checkers for various media server components.
Each service checker implements the base ServiceChecker interface and
provides specific functionality for checking service activity.
"""

from mediaserver_autosuspend.services.base import ServiceChecker
from mediaserver_autosuspend.services.jellyfin import JellyfinChecker
from mediaserver_autosuspend.services.sonarr import SonarrChecker
from mediaserver_autosuspend.services.radarr import RadarrChecker
from mediaserver_autosuspend.services.nextcloud import NextcloudChecker
from mediaserver_autosuspend.services.system import SystemChecker
from typing import Dict, Type, Any

# Registry of available service checkers
SERVICE_REGISTRY: Dict[str, Type[ServiceChecker]] = {
    'jellyfin': JellyfinChecker,
    'sonarr': SonarrChecker,
    'radarr': RadarrChecker,
    'nextcloud': NextcloudChecker,
    'system': SystemChecker
}

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
    """
    enabled_services = config.get('SERVICES', {})
    checkers = {}
    
    for service_name, checker_class in SERVICE_REGISTRY.items():
        if enabled_services.get(service_name, True):  # Enable by default
            checkers[service_name] = checker_class(config)
    
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

def list_available_services() -> Dict[str, str]:
    """
    Get list of available service checkers and their descriptions.
    
    Returns:
        Dict mapping service names to their descriptions
    """
    return {
        name: checker.__doc__ or "No description available"
        for name, checker in SERVICE_REGISTRY.items()
    }

__all__ = [
    'ServiceChecker',
    'JellyfinChecker',
    'SonarrChecker',
    'RadarrChecker',
    'NextcloudChecker',
    'SystemChecker',
    'get_service_checker',
    'create_service_checkers',
    'register_service_checker',
    'list_available_services',
    'SERVICE_REGISTRY'
]
