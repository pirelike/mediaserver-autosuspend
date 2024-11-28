"""
Radarr service checker for MediaServer AutoSuspend.

This module implements the service checker for Radarr,
monitoring active downloads and queue items.
"""

import requests
from typing import Dict, Any
from mediaserver_autosuspend.services.base import ServiceChecker, ServiceConfigError

class RadarrChecker(ServiceChecker):
    """Service checker for Radarr download queue."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Radarr checker.
        
        Args:
            config: Configuration dictionary containing RADARR_API_KEY
            
        Raises:
            ServiceConfigError: If required configuration is missing
        """
        super().__init__(config)
        
        # Validate required configuration
        required_keys = ['RADARR_API_KEY']
        self.validate_config(required_keys)
        
        self.api_key = config['RADARR_API_KEY']
        self.url = config.get('RADARR_URL', 'http://localhost:7878')
    
    def check_activity(self) -> bool:
        """
        Check Radarr for active queue items.
        
        Returns:
            bool: True if there are active downloads, False otherwise
        """
        try:
            headers = {'X-Api-Key': self.api_key}
            response = requests.get(
                f'{self.url}/api/v3/queue',
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            
            total_records = response.json().get('totalRecords', 0)
            if total_records > 0:
                self.logger.info(f"Radarr: Active queue items found: {total_records}")
                return True
            
            self.logger.info("Radarr: No active queue items")
            return False
            
        except Exception as e:
            self.logger.info(f"Radarr: Error connecting to API - {str(e)}")
            return False
