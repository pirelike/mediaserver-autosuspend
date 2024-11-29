"""
Jellyfin service checker for MediaServer AutoSuspend.

This module implements the service checker for Jellyfin media server,
monitoring active playback sessions and server tasks.
"""

import requests
from typing import Dict, Any, List
from mediaserver_autosuspend.services.base import (
    ServiceChecker,
    ServiceConfigError,
    ServiceConnectionError,
    ServiceCheckError
)

class JellyfinChecker(ServiceChecker):
    """Service checker for Jellyfin media server."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Jellyfin checker.
        
        Args:
            config: Configuration dictionary containing:
                - JELLYFIN_API_KEY: API key for authentication
                - JELLYFIN_URL: Server base URL
                - JELLYFIN_TIMEOUT (optional): API timeout in seconds
                
        Raises:
            ServiceConfigError: If required configuration is missing
        """
        super().__init__(config)
        
        # Validate required configuration
        required_keys = ['JELLYFIN_API_KEY', 'JELLYFIN_URL']
        self.validate_config(required_keys)
        
        # Initialize configuration
        self.api_key = config['JELLYFIN_API_KEY']
        self.url = config['JELLYFIN_URL'].rstrip('/')
        self.timeout = config.get('JELLYFIN_TIMEOUT', 10)
        
        # Client identification
        self.device_id = 'mediaserver-autosuspend'
        self.client_name = 'MediaServerAutoSuspend'
    
    def check_activity(self) -> bool:
        """
        Check Jellyfin for active playback sessions and server tasks.
        
        Returns:
            bool: True if there are active playback sessions or tasks
            
        Raises:
            ServiceConnectionError: If connection to server fails
            ServiceCheckError: If API request fails
        """
        try:
            # Check for active playback first
            if self._check_playback():
                return True
                
            # If no playback, check for active server tasks
            if self._check_tasks():
                return True
            
            self.logger.debug("No active Jellyfin playback or tasks")
            return False
            
        except requests.exceptions.RequestException as e:
            raise ServiceConnectionError(f"Failed to connect to Jellyfin: {e}")
        except Exception as e:
            raise ServiceCheckError(f"Error checking Jellyfin activity: {e}")
    
    def _check_playback(self) -> bool:
        """
        Check for active playback sessions.
        
        Returns:
            bool: True if there are active playback sessions
        """
        response = requests.get(
            f"{self.url}/Sessions",
            headers=self._get_auth_headers(),
            timeout=self.timeout
        )
        response.raise_for_status()
        sessions = response.json()
        
        # Check each session for active playback
        for session in sessions:
            # Verify this is an actual playback session with a current media item
            if not session.get('NowPlayingItem'):
                continue
                
            playstate = session.get('PlayState', {})
            
            # Check if something is actually playing (not paused/stopped)
            if playstate.get('IsPaused', True):
                continue
                
            if not playstate.get('IsPlaying', False):
                continue
            
            # We found an active playback session
            self.logger.info(
                f"Active Jellyfin playback detected: "
                f"{session.get('UserName', 'Unknown')} playing "
                f"'{session.get('NowPlayingItem', {}).get('Name', 'Unknown')}'"
            )
            return True
        
        return False
    
    def _check_tasks(self) -> bool:
        """
        Check for active server tasks.
        
        Returns:
            bool: True if there are active tasks
        """
        # First check scheduled tasks
        response = requests.get(
            f"{self.url}/ScheduledTasks/Running",
            headers=self._get_auth_headers(),
            timeout=self.timeout
        )
        response.raise_for_status()
        running_tasks = response.json()
        
        if running_tasks:
            task_names = [task.get('Name', 'Unknown Task') for task in running_tasks]
            self.logger.info(f"Active Jellyfin tasks: {', '.join(task_names)}")
            return True
            
        # Then check library operations
        response = requests.get(
            f"{self.url}/Library/RefreshQueue",
            headers=self._get_auth_headers(),
            timeout=self.timeout
        )
        response.raise_for_status()
        queue = response.json()
        
        if queue.get('Items', []):
            self.logger.info("Active Jellyfin library operations detected")
            return True
        
        return False
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """
        Get headers for authenticated API requests.
        
        Returns:
            Dict containing required headers
        """
        return {
            'X-Emby-Authorization': (
                f'MediaBrowser '
                f'Client="{self.client_name}", '
                f'Device="{self.device_id}", '
                f'DeviceId="{self.device_id}", '
                f'Version="1.0.0", '
                f'Token="{self.api_key}"'
            ),
            'Accept': 'application/json'
        }
