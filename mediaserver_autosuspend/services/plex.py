"""
Plex service checker for MediaServer AutoSuspend.

This module implements the service checker for Plex Media Server,
monitoring active playback sessions, transcoding activities, and server tasks.

Example:
    >>> checker = PlexChecker({
    ...     'PLEX_URL': 'http://localhost:32400',
    ...     'PLEX_TOKEN': 'your-token',
    ...     'PLEX_MONITOR_TRANSCODING': True,
    ...     'PLEX_IGNORE_PAUSED': False
    ... })
    >>> is_active = checker.check_activity()
"""

import requests
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin

from mediaserver_autosuspend.services.base import (
    ServiceChecker,
    ServiceConfigError,
    ServiceConnectionError,
    ServiceCheckError
)

class PlexChecker(ServiceChecker):
    """
    Service checker for Plex Media Server.
    
    Monitors active playback sessions, transcoding activities, and server tasks.
    Can be configured to ignore paused sessions and monitor transcoding separately.
    
    Attributes:
        url (str): Base URL of the Plex server
        token (str): X-Plex-Token for authentication
        monitor_transcoding (bool): Whether to check transcoding sessions
        ignore_paused (bool): Whether to ignore paused sessions
        request_timeout (int): Timeout for API requests in seconds
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Plex checker with configuration.
        
        Args:
            config: Configuration dictionary containing:
                - PLEX_TOKEN: X-Plex-Token for authentication
                - PLEX_URL: Server base URL
                - PLEX_MONITOR_TRANSCODING (optional): Monitor transcoding sessions
                - PLEX_IGNORE_PAUSED (optional): Ignore paused sessions
                - PLEX_TIMEOUT (optional): API timeout in seconds
                
        Raises:
            ServiceConfigError: If required configuration is missing
        """
        super().__init__(config)
        
        # Validate required configuration
        required_keys = ['PLEX_TOKEN', 'PLEX_URL']
        self.validate_config(required_keys)
        
        # Initialize configuration
        self.url = config['PLEX_URL'].rstrip('/')
        self.token = config['PLEX_TOKEN']
        self.monitor_transcoding = config.get('PLEX_MONITOR_TRANSCODING', True)
        self.ignore_paused = config.get('PLEX_IGNORE_PAUSED', False)
        self.request_timeout = int(config.get('PLEX_TIMEOUT', 10))
        
        # Client identification
        self.client_identifier = 'mediaserver-autosuspend'
        self.app_name = 'MediaServerAutoSuspend'
        
        self.logger.debug(
            f"Initialized Plex checker for {self.url} "
            f"(monitor_transcoding: {self.monitor_transcoding}, "
            f"ignore_paused: {self.ignore_paused})"
        )
    
    def check_activity(self) -> bool:
        """
        Check Plex for active playback sessions and transcoding.
        
        Returns:
            bool: True if there is active playback or transcoding
            
        Raises:
            ServiceConnectionError: If connection to server fails
            ServiceCheckError: If API request fails
        """
        try:
            # Check for active playback first
            if self._check_playback():
                return True
                
            # Check transcoding if enabled
            if self.monitor_transcoding and self._check_transcoding():
                return True
                
            # Check for active server tasks
            if self._check_tasks():
                return True
            
            self.logger.debug("No active Plex sessions or tasks")
            return False
            
        except requests.exceptions.RequestException as e:
            raise ServiceConnectionError(f"Failed to connect to Plex: {e}")
        except Exception as e:
            raise ServiceCheckError(f"Error checking Plex activity: {e}")
    
    def _check_playback(self) -> bool:
        """
        Check for active playback sessions.
        
        Returns:
            bool: True if there are active playback sessions
        """
        response = self._make_request("/status/sessions")
        sessions = response.get('MediaContainer', {}).get('Metadata', [])
        
        for session in sessions:
            # Get session details
            state = session.get('Player', {}).get('state', '')
            user = session.get('User', {}).get('title', 'Unknown')
            title = session.get('title', 'Unknown')
            player = session.get('Player', {}).get('title', 'Unknown Device')
            
            # Skip paused sessions if configured
            if self.ignore_paused and state == 'paused':
                continue
                
            # Check for active playback
            if state in ['playing', 'buffering']:
                self.logger.info(
                    f"Active Plex session detected: "
                    f"{user} playing '{title}' on {player}"
                )
                return True
        
        return False
    
    def _check_transcoding(self) -> bool:
        """
        Check for active transcoding sessions.
        
        Returns:
            bool: True if there are active transcoding sessions
        """
        response = self._make_request("/transcode/sessions")
        sessions = response.get('MediaContainer', {}).get('Metadata', [])
        
        if sessions:
            self.logger.info(
                f"Active Plex transcoding detected: {len(sessions)} session(s)"
            )
            return True
            
        return False
    
    def _check_tasks(self) -> bool:
        """
        Check for active server tasks.
        
        Returns:
            bool: True if there are active server tasks
        """
        response = self._make_request("/butler")
        tasks = response.get('MediaContainer', {}).get('ButlerTasks', [])
        
        active_tasks = [
            task for task in tasks
            if task.get('status') == 'running'
        ]
        
        if active_tasks:
            task_names = [task.get('name', 'Unknown Task') for task in active_tasks]
            self.logger.info(f"Active Plex tasks: {', '.join(task_names)}")
            return True
            
        return False
    
    def _make_request(self, endpoint: str) -> Dict[str, Any]:
        """
        Make authenticated request to Plex API.
        
        Args:
            endpoint: API endpoint path
            
        Returns:
            Dict containing API response data
            
        Raises:
            ServiceConnectionError: If request fails
            ServiceCheckError: If response is invalid
        """
        headers = {
            'X-Plex-Token': self.token,
            'X-Plex-Client-Identifier': self.client_identifier,
            'X-Plex-Product': self.app_name,
            'X-Plex-Version': '1.0.0',
            'Accept': 'application/json'
        }
        
        try:
            response = requests.get(
                urljoin(self.url, endpoint),
                headers=headers,
                timeout=self.request_timeout
            )
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            raise ServiceConnectionError(f"Plex API request failed: {e}")
        except ValueError as e:
            raise ServiceCheckError(f"Invalid response from Plex API: {e}")
    
    def test_connection(self) -> bool:
        """
        Test connection to Plex server.
        
        Returns:
            bool: True if connection successful
            
        Raises:
            ServiceConnectionError: If connection fails
        """
        try:
            response = self._make_request("/")
            return 'MediaContainer' in response
        except Exception as e:
            raise ServiceConnectionError(f"Plex connection test failed: {e}")
