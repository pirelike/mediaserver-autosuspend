"""
Sonarr service checker for MediaServer AutoSuspend.

This module implements the service checker for Sonarr, monitoring active downloads
and queue items through the Sonarr API.

Example:
    >>> checker = SonarrChecker({
    ...     'SONARR_URL': 'http://localhost:8989',
    ...     'SONARR_API_KEY': 'your-api-key'
    ... })
    >>> is_active = checker.check_activity()
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
import requests
from urllib.parse import urljoin

from mediaserver_autosuspend.services.base import (
    ServiceChecker,
    ServiceConfigError,
    ServiceConnectionError,
    ServiceCheckError
)

class SonarrChecker(ServiceChecker):
    """
    Service checker for Sonarr download queue.
    
    Monitors the Sonarr queue for active downloads and pending items.
    Can be configured to check specific queue statuses and handle
    different types of download activities.
    
    Attributes:
        url (str): Base URL of the Sonarr instance
        api_key (str): API key for authentication
        request_timeout (int): Timeout for API requests in seconds
    """
    
    # Define status types that indicate activity
    ACTIVE_STATUSES = {
        'downloading',
        'importPending',
        'pending',
        'queued'
    }
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Sonarr checker with configuration.
        
        Args:
            config: Configuration dictionary containing:
                - SONARR_API_KEY: API key for authentication
                - SONARR_URL: Server base URL
                - SONARR_TIMEOUT (optional): API timeout in seconds
                
        Raises:
            ServiceConfigError: If required configuration is missing
        """
        super().__init__(config)
        
        # Validate required configuration
        required_keys = ['SONARR_API_KEY', 'SONARR_URL']
        self.validate_config(required_keys)
        
        # Initialize configuration
        self.api_key = config['SONARR_API_KEY']
        self.url = config['SONARR_URL'].rstrip('/')
        self.request_timeout = int(config.get('SONARR_TIMEOUT', 10))
        
        self.logger.debug(f"Initialized Sonarr checker for {self.url}")
    
    def check_activity(self) -> bool:
        """
        Check Sonarr for active downloads and queue items.
        
        Returns:
            bool: True if there are active downloads or queue items
            
        Raises:
            ServiceConnectionError: If connection to server fails
            ServiceCheckError: If API request fails
        """
        try:
            # Check queue status
            active_items = self._get_active_queue_items()
            
            if active_items:
                item_details = [
                    f"{item.get('title', 'Unknown')} ({item.get('status', 'unknown status')})"
                    for item in active_items[:3]  # Limit to first 3 for log readability
                ]
                
                total_items = len(active_items)
                if total_items > 3:
                    item_details.append(f"and {total_items - 3} more")
                
                self.logger.info(
                    f"Active Sonarr downloads detected: {', '.join(item_details)}"
                )
                return True
            
            self.logger.debug("No active Sonarr queue items")
            return False
            
        except requests.exceptions.RequestException as e:
            raise ServiceConnectionError(f"Failed to connect to Sonarr: {e}")
        except Exception as e:
            raise ServiceCheckError(f"Error checking Sonarr activity: {e}")
    
    def _get_active_queue_items(self) -> List[Dict[str, Any]]:
        """
        Get list of active queue items from Sonarr.
        
        Returns:
            List of active queue items
            
        Raises:
            ServiceConnectionError: If API request fails
            ServiceCheckError: If response is invalid
        """
        try:
            response = self._make_request("/api/v3/queue")
            records = response.get('records', [])
            
            # Filter for active items
            active_items = [
                item for item in records
                if item.get('status', '').lower() in self.ACTIVE_STATUSES
            ]
            
            return active_items
            
        except requests.exceptions.RequestException as e:
            raise ServiceConnectionError(f"Failed to get Sonarr queue: {e}")
        except (KeyError, AttributeError) as e:
            raise ServiceCheckError(f"Invalid response format from Sonarr: {e}")
    
    def _make_request(self, endpoint: str) -> Dict[str, Any]:
        """
        Make authenticated request to Sonarr API.
        
        Args:
            endpoint: API endpoint path
            
        Returns:
            Dict containing API response data
            
        Raises:
            ServiceConnectionError: If request fails
            ServiceCheckError: If response is invalid
        """
        headers = {
            'X-Api-Key': self.api_key,
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
            raise ServiceConnectionError(f"Sonarr API request failed: {e}")
        except ValueError as e:
            raise ServiceCheckError(f"Invalid response from Sonarr API: {e}")
    
    def test_connection(self) -> Tuple[bool, Optional[str]]:
        """
        Test connection to Sonarr server.
        
        Returns:
            Tuple containing:
                - Boolean indicating if connection was successful
                - Optional error message if connection failed
        """
        try:
            # Test connection using system status endpoint
            self._make_request("/api/v3/system/status")
            return True, None
        except ServiceConnectionError as e:
            return False, f"Connection failed: {str(e)}"
        except ServiceCheckError as e:
            return False, f"API error: {str(e)}"
        except Exception as e:
            return False, f"Unexpected error: {str(e)}"
