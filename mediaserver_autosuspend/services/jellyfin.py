"""
Jellyfin service checker for MediaServer AutoSuspend.

This module implements the service checker for Jellyfin media server,
monitoring active playback sessions.
"""

import requests
from typing import Dict, Any
from mediaserver_autosuspend.services.base import ServiceChecker, ServiceConfigError

class JellyfinChecker(ServiceChecker):
    """Service checker for Jellyfin media server."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Jellyfin checker.
        
        Args:
            config: Configuration dictionary containing JELLYFIN_API_KEY and JELLYFIN_URL
            
        Raises:
            ServiceConfigError: If required configuration is missing
        """
        super().__init__(config)
        
        # Validate required configuration
        required_keys = ['JELLYFIN_API_KEY', 'JELLYFIN_URL']
        self.validate_config(required_keys)
        
        self.api_key = config['JELLYFIN_API_KEY']
        self.url = config['JELLYFIN_URL']
    
    def check_activity(self) -> bool:
        """
        Check Jellyfin for active playback sessions.
        
        Returns:
            bool: True if there are active playback sessions, False otherwise
        """
        try:
            headers = {
                'X-Emby-Authorization': (
                    f'MediaBrowser ClientId="JellyfinWeb", '
                    f'DeviceId="", Device="", Version="", '
                    f'Token="{self.api_key}"'
                )
            }
            
            response = requests.get(
                f"{self.url}/Sessions",
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            sessions = response.json()
            
            # Check if any session has active playback
            for session in sessions:
                if session.get('NowPlayingItem') is not None:
                    self.logger.info("Jellyfin: Active playback session detected")
                    return True
            
            self.logger.info("Jellyfin: No active playback sessions")
            return False
            
        except requests.exceptions.RequestException as e:
            self.logger.info(f"Jellyfin: Error connecting to API - {str(e)}")
            return False
