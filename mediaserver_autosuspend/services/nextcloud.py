"""
Nextcloud service checker for MediaServer AutoSuspend.

This module implements the service checker for Nextcloud, monitoring the 5-minute
CPU load average through the system info API.

Example:
    >>> checker = NextcloudChecker({
    ...     'NEXTCLOUD_URL': 'http://nextcloud.local',
    ...     'NEXTCLOUD_TOKEN': 'your-token',
    ...     'NEXTCLOUD_CPU_THRESHOLD': 0.5
    ... })
    >>> is_active = checker.check_activity()
"""

import logging
from typing import Dict, Any, Tuple, Optional
import requests
from urllib.parse import urljoin

from mediaserver_autosuspend.services.base import (
    ServiceChecker,
    ServiceConfigError,
    ServiceConnectionError,
    ServiceCheckError
)

class NextcloudChecker(ServiceChecker):
    """
    Service checker for Nextcloud server activity.
    
    Monitors the 5-minute CPU load average through Nextcloud's system info API.
    Activity is determined by comparing the load against a configurable threshold.
    
    Attributes:
        url (str): Base URL of the Nextcloud instance
        token (str): API token for authentication
        cpu_threshold (float): CPU load threshold to consider as activity
        request_timeout (int): Timeout for API requests in seconds
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Nextcloud checker with configuration.
        
        Args:
            config: Configuration dictionary containing:
                - NEXTCLOUD_URL: Base URL of Nextcloud instance
                - NEXTCLOUD_TOKEN: API token for authentication
                - NEXTCLOUD_CPU_THRESHOLD (optional): CPU threshold (0.0-1.0)
                - NEXTCLOUD_TIMEOUT (optional): API timeout in seconds
                
        Raises:
            ServiceConfigError: If required configuration is missing
        """
        super().__init__(config)
        
        # Validate required configuration
        required_keys = ['NEXTCLOUD_URL', 'NEXTCLOUD_TOKEN']
        self.validate_config(required_keys)
        
        # Initialize configuration
        self.url = config['NEXTCLOUD_URL'].rstrip('/')
        self.token = config['NEXTCLOUD_TOKEN']
        self.cpu_threshold = float(config.get('NEXTCLOUD_CPU_THRESHOLD', 0.5))
        self.request_timeout = int(config.get('NEXTCLOUD_TIMEOUT', 10))
        
        # Validate CPU threshold
        if not 0.0 <= self.cpu_threshold <= 1.0:
            raise ServiceConfigError(
                "NEXTCLOUD_CPU_THRESHOLD must be between 0.0 and 1.0"
            )
        
        self.logger.debug(
            f"Initialized Nextcloud checker for {self.url} "
            f"(CPU threshold: {self.cpu_threshold})"
        )
    
    def check_activity(self) -> bool:
        """
        Check Nextcloud 5-minute CPU load average.
        
        Returns:
            bool: True if 5-minute CPU load is above threshold
            
        Raises:
            ServiceConnectionError: If connection to Nextcloud fails
            ServiceCheckError: If API request fails or returns invalid data
        """
        try:
            # Get 5-minute CPU load from system info
            load_5min = self._get_5min_load()
            
            # Check if CPU load indicates activity
            if load_5min > self.cpu_threshold:
                self.logger.info(
                    f"High Nextcloud 5-minute load detected: {load_5min:.2f} "
                    f"(threshold: {self.cpu_threshold})"
                )
                return True
            
            self.logger.debug(f"Nextcloud 5-minute load normal: {load_5min:.2f}")
            return False
            
        except requests.exceptions.RequestException as e:
            raise ServiceConnectionError(f"Failed to connect to Nextcloud: {e}")
        except Exception as e:
            raise ServiceCheckError(f"Error checking Nextcloud activity: {e}")
    
    def _get_5min_load(self) -> float:
        """
        Get 5-minute CPU load average from Nextcloud API.
        
        Returns:
            5-minute CPU load average (0.0-1.0)
            
        Raises:
            ServiceConnectionError: If API request fails
            ServiceCheckError: If response data is invalid
        """
        headers = {
            'NC-Token': self.token,
            'OCS-APIRequest': 'true',
            'Accept': 'application/json'
        }
        
        api_url = urljoin(self.url, '/ocs/v2.php/apps/serverinfo/api/v1/info')
        
        try:
            response = requests.get(
                api_url,
                headers=headers,
                params={'format': 'json'},
                timeout=self.request_timeout
            )
            response.raise_for_status()
            
            data = response.json()
            if not isinstance(data, dict):
                raise ServiceCheckError("Invalid response format from Nextcloud API")
            
            # Extract 5-minute load average
            try:
                load_5min = float(
                    data.get('ocs', {})
                    .get('data', {})
                    .get('system', {})
                    .get('cpuload', [0.0, 0.0, 0.0])[1]  # Index 1 is 5-minute average
                )
                # Normalize to 0-1 scale if needed
                return load_5min / 100.0 if load_5min > 1.0 else load_5min
                
            except (IndexError, TypeError, ValueError) as e:
                raise ServiceCheckError(f"Invalid CPU load data format: {e}")
            
        except requests.exceptions.RequestException as e:
            raise ServiceConnectionError(f"Nextcloud API request failed: {e}")
        except Exception as e:
            raise ServiceCheckError(f"Error parsing Nextcloud CPU load data: {e}")
    
    def test_connection(self) -> Tuple[bool, Optional[str]]:
        """
        Test connection to Nextcloud server.
        
        Returns:
            Tuple containing:
                - Boolean indicating if connection was successful
                - Optional error message if connection failed
        """
        try:
            self._get_5min_load()
            return True, None
        except ServiceConnectionError as e:
            return False, f"Connection failed: {str(e)}"
        except ServiceCheckError as e:
            return False, f"API error: {str(e)}"
        except Exception as e:
            return False, f"Unexpected error: {str(e)}"
