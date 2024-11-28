"""
System service checker for MediaServer AutoSuspend.

This module implements the service checker for system-level activity,
monitoring logged-in users and system load.
"""

import subprocess
from typing import Dict, Any, List
from mediaserver_autosuspend.services.base import ServiceChecker

class SystemChecker(ServiceChecker):
    """Service checker for system-level activity."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize system checker.
        
        Args:
            config: Configuration dictionary
        """
        super().__init__(config)
        
        # Configure which users to ignore
        self.ignore_users = set(config.get('IGNORE_USERS', []))
        
        # Configure minimum load threshold
        self.load_threshold = config.get('SYSTEM_LOAD_THRESHOLD', 0.5)
        
        # Configure whether to check system load
        self.check_load = config.get('CHECK_SYSTEM_LOAD', True)
    
    def check_activity(self) -> bool:
        """
        Check for logged-in users and system activity.
        
        Returns:
            bool: True if there is system activity, False otherwise
        """
        try:
            # Check logged-in users
            active_users = self._get_logged_in_users()
            if active_users:
                self.logger.info(
                    f"System: Active users found: {', '.join(active_users)}"
                )
                return True
            
            # Check system load if enabled
            if self.check_load and self._check_system_load():
                return True
            
            self.logger.info("System: No active users or significant system load")
            return False
            
        except Exception as e:
            self.logger.error(f"System: Error checking system activity - {str(e)}")
            return False
    
    def _get_logged_in_users(self) -> List[str]:
        """
        Get list of currently logged-in users.
        
        Returns:
            List of usernames who are currently logged in
        """
        try:
            who_output = subprocess.check_output(
                ['who'],
                text=True,
                stderr=subprocess.PIPE
            ).strip()
            
            if not who_output:
                return []
            
            # Process who output and filter ignored users
            active_users = set()
            for line in who_output.split('\n'):
                if line:
                    username = line.split()[0]
                    if username not in self.ignore_users:
                        active_users.add(username)
            
            return sorted(list(active_users))
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error running 'who' command: {e.stderr}")
            return []
    
    def _check_system_load(self) -> bool:
        """
        Check system load average.
        
        Returns:
            bool: True if system load is above threshold
        """
        try:
            with open('/proc/loadavg', 'r') as f:
                # Get 5-minute load average
                load_avg = float(f.read().split()[1])
                
                if load_avg > self.load_threshold:
                    self.logger.info(
                        f"System: High load detected (Load average: {load_avg})"
                    )
                    return True
                
                return False
                
        except Exception as e:
            self.logger.error(f"Error checking system load: {e}")
            return False
    
    def get_load_average(self) -> Dict[str, float]:
        """
        Get system load averages.
        
        Returns:
            Dictionary containing 1, 5, and 15-minute load averages
        """
        try:
            with open('/proc/loadavg', 'r') as f:
                loads = f.read().split()[:3]
                return {
                    '1min': float(loads[0]),
                    '5min': float(loads[1]),
                    '15min': float(loads[2])
                }
        except Exception as e:
            self.logger.error(f"Error reading load averages: {e}")
            return {'1min': 0.0, '5min': 0.0, '15min': 0.0}
