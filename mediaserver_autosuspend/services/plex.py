"""
Plex service checker for MediaServer AutoSuspend.

This module implements the service checker for Plex Media Server,
monitoring active playback sessions and transcoding activities.
"""

import requests
from typing import Dict, Any
from mediaserver_autosuspend.services.base import ServiceChecker, ServiceConfigError

class PlexChecker(ServiceChecker):
    """Service checker for Plex Media Server."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Plex checker.
        
        Args:
            config: Configuration dictionary containing PLEX_TOKEN and PLEX_URL
            
        Raises:
            ServiceConfigError: If required configuration is missing
        """
        super().__init__(config)
        
        # Validate required configuration
        required_keys = ['PLEX_TOKEN', 'PLEX_URL']
        self.validate_config(required_keys)
        
        self.token = config['PLEX_TOKEN']
        self.url = config.get('PLEX_URL', 'http://localhost:32400')
        
        # Additional settings
        self.monitor_transcoding = config.get('PLEX_MONITOR_TRANSCODING', True)
        self.ignore_paused = config.get('PLEX_IGNORE_PAUSED', False)
    
    def check_activity(self) -> bool:
        """
        Check Plex for active playback sessions.
        
        Returns:
            bool: True if there are active sessions, False otherwise
        """
        try:
            # Get current sessions
            sessions = self._get_sessions()
            
            # Check each session for activity
            for session in sessions.get('MediaContainer', {}).get('Metadata', []):
                if self._is_session_active(session):
                    self._log_active_session(session)
                    return True
            
            # Check for active transcoding if enabled
            if self.monitor_transcoding and self._check_transcoding():
                return True
            
            self.logger.info("Plex: No active playback sessions")
            return False
            
        except Exception as e:
            self.logger.info(f"Plex: Error connecting to API - {str(e)}")
            return False
    
    def _get_sessions(self) -> Dict[str, Any]:
        """
        Get current Plex sessions.
        
        Returns:
            Dict containing session information
        """
        headers = {
            'X-Plex-Token': self.token,
            'Accept': 'application/json'
        }
        
        response = requests.get(
            f"{self.url}/status/sessions",
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        
        return response.json()
    
    def _is_session_active(self, session: Dict[str, Any]) -> bool:
        """
        Check if a session is considered active.
        
        Args:
            session: Session information dictionary
            
        Returns:
            bool: True if session is active
        """
        # Check if session is paused
        if self.ignore_paused and session.get('Player', {}).get('state') == 'paused':
            return False
        
        # Check for direct play or transcoding
        if session.get('Player', {}).get('state') in ['playing', 'buffering']:
            return True
        
        return False
    
    def _check_transcoding(self) -> bool:
        """
        Check for active transcoding sessions.
        
        Returns:
            bool: True if transcoding is active
        """
        try:
            headers = {
                'X-Plex-Token': self.token,
                'Accept': 'application/json'
            }
            
            response = requests.get(
                f"{self.url}/transcode/sessions",
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            
            sessions = response.json()
            if sessions.get('MediaContainer', {}).get('Metadata'):
                self.logger.info("Plex: Active transcoding detected")
                return True
            
            return False
            
        except Exception as e:
            self.logger.warning(f"Plex: Failed to check transcoding status - {e}")
            return False
    
    def _log_active_session(self, session: Dict[str, Any]) -> None:
        """Log details of active session."""
        title = session.get('title', 'Unknown')
        user = session.get('User', {}).get('title', 'Unknown User')
        player = session.get('Player', {}).get('title', 'Unknown Device')
        
        self.logger.info(
            f"Plex: Active session - {user} playing '{title}' on {player}"
        )
