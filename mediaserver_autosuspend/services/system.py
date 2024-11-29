"""
System service checker for MediaServer AutoSuspend.

This module implements the service checker for system-level activity by monitoring:
- Logged-in users (via 'who' command)
- 5-minute system load average (via /proc/loadavg)
"""

import subprocess
from typing import Dict, Any, List, Set
from mediaserver_autosuspend.services.base import (
    ServiceChecker,
    ServiceCheckError
)

class SystemChecker(ServiceChecker):
    """
    Service checker for system-level activity monitoring.
    
    Monitors system activity through logged-in users and the 5-minute load average.
    Can be configured to ignore specific users and set a custom load threshold.
    
    Attributes:
        ignore_users (Set[str]): Set of usernames to ignore when checking activity
        load_threshold (float): System load threshold (0.0-1.0)
        check_load (bool): Whether to monitor system load
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize system checker with configuration.
        
        Args:
            config: Configuration dictionary containing:
                - IGNORE_USERS (optional): List of users to ignore
                - SYSTEM_LOAD_THRESHOLD (optional): Load threshold (0.0-1.0)
                - CHECK_SYSTEM_LOAD (optional): Whether to check system load
        """
        super().__init__(config)
        
        # Configure which users to ignore
        self.ignore_users = set(config.get('IGNORE_USERS', []))
        
        # System load configuration
        self.load_threshold = float(config.get('SYSTEM_LOAD_THRESHOLD', 0.5))
        self.check_load = config.get('CHECK_SYSTEM_LOAD', True)
    
    def check_activity(self) -> bool:
        """
        Check for system activity by monitoring logged-in users and load average.
        
        Returns:
            bool: True if system shows activity, False otherwise
        """
        try:
            # Check logged-in users first
            active_users = self._get_logged_in_users()
            if active_users:
                self.logger.info(f"Active users detected: {', '.join(active_users)}")
                return True
            
            # Check system load if enabled
            if self.check_load and self._check_system_load():
                return True
            
            self.logger.debug("No significant system activity detected")
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking system activity: {e}")
            return False  # Err on the side of caution
    
    def _get_logged_in_users(self) -> List[str]:
        """
        Get list of currently logged-in users.
        
        Returns:
            List of active usernames (excluding ignored users)
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
        except Exception as e:
            self.logger.error(f"Error checking logged-in users: {e}")
            return []
    
    def _check_system_load(self) -> bool:
        """
        Check 5-minute system load average.
        
        Returns:
            bool: True if load is above threshold
        """
        try:
            with open('/proc/loadavg', 'r') as f:
                # Get 5-minute load average (second value)
                load_avg = float(f.read().split()[1])
                
                if load_avg > self.load_threshold:
                    self.logger.info(
                        f"High system load detected: {load_avg:.2f} "
                        f"(threshold: {self.load_threshold})"
                    )
                    return True
                
                return False
                
        except Exception as e:
            self.logger.error(f"Error checking system load: {e}")
            return False
    
    def get_load_average(self) -> float:
        """
        Get current 5-minute load average.
        
        Returns:
            float: 5-minute load average or 0.0 on error
        """
        try:
            with open('/proc/loadavg', 'r') as f:
                return float(f.read().split()[1])
        except Exception as e:
            self.logger.error(f"Error reading load average: {e}")
            return 0.0
