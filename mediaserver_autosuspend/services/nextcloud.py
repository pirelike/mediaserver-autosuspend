"""
Nextcloud service checker for MediaServer AutoSuspend.

This module implements the service checker for Nextcloud,
monitoring active users and CPU load.
"""

import requests
from typing import Dict, Any, Tuple
from mediaserver_autosuspend.services.base import ServiceChecker, ServiceConfigError

class NextcloudChecker(ServiceChecker):
    """Service checker for Nextcloud server activity."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Nextcloud checker.
        
        Args:
            config: Configuration dictionary containing NEXTCLOUD_URL and NEXTCLOUD_TOKEN
            
        Raises:
            ServiceConfigError: If required configuration is missing
        """
        super().__init__(config)
        
        # Validate required configuration
        required_keys = ['NEXTCLOUD_URL', 'NEXTCLOUD_TOKEN']
        self.validate_config(required_keys)
        
        self.url = config['NEXTCLOUD_URL']
        self.token = config['NEXTCLOUD_TOKEN']
        self.cpu_threshold = config.get('NEXTCLOUD_CPU_THRESHOLD', 0.5)
    
    def check_activity(self) -> bool:
        """
        Check Nextcloud for active users and CPU load.
        
        Returns:
            bool: True if there is activity or high CPU load, False otherwise
        """
        try:
            headers = {
                'NC-Token': self.token,
                'OCS-APIRequest': 'true'
            }
            
            response = requests.get(
                f"{self.url}/ocs/v2.php/apps/serverinfo/api/v1/info",
                headers=headers,
                params={'format': 'json'},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            # Extract metrics
            active_users, cpu_load = self._extract_metrics(data)
            
            # Check CPU load
            if cpu_load > self.cpu_threshold:
                self.logger.info(
                    f"Nextcloud: High CPU load detected (Load average: {cpu_load})"
                )
                return True
            
            # Check active users
            if active_users > 0:
                self.logger.info(
                    f"Nextcloud: Active users in last 5 minutes: {active_users}"
                )
                return True
            
            self.logger.info(
                f"Nextcloud: No activity detected "
                f"(Load average: {cpu_load}, Active users: {active_users})"
            )
            return False
            
        except Exception as e:
            self.logger.info(f"Nextcloud: Error connecting to API - {str(e)}")
            return False
    
    def _extract_metrics(self, data: Dict[str, Any]) -> Tuple[int, float]:
        """
        Extract active users and CPU load from API response.
        
        Args:
            data: API response data
            
        Returns:
            Tuple containing active users count and CPU load average
        """
        # Get active users in last 5 minutes
        active_users = int(
            data.get('ocs', {})
            .get('data', {})
            .get('activeUsers', {})
            .get('last5minutes', 0)
        )
        
        # Get 5-minute CPU load average
        cpu_load = float(
            data.get('ocs', {})
            .get('data', {})
            .get('system', {})
            .get('cpuload', [0, 0, 0])[1]  # Use 5-minute average
        )
        
        return active_users, cpu_load
