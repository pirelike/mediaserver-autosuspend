"""
SuspensionManager for MediaServer AutoSuspend.

This module handles the core suspension logic, including:
- Service activity monitoring
- Grace period management
- System suspension execution
- Wake-up timer configuration
"""

import os
import time
import logging
import subprocess
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class SuspensionManager:
    """Manages system suspension based on service activity."""
    
    def __init__(self, config: Dict[str, Any], services: Dict[str, Any]):
        """
        Initialize the suspension manager.
        
        Args:
            config: Configuration dictionary
            services: Dictionary of service checker instances
        """
        self.config = config
        self.services = services
        self.grace_period = config.get('GRACE_PERIOD', 600)
        self.check_interval = config.get('CHECK_INTERVAL', 60)
        self.last_suspension = None
        self.suspension_count = 0
        
        # Load wake-up schedule
        self.wake_times = self._parse_wake_times(
            config.get('WAKE_UP_TIMES', ["07:00"])
        )
    
    def should_suspend(self) -> bool:
        """
        Check if system should be suspended.
        
        Returns:
            bool: True if system should be suspended
        """
        # Check minimum uptime
        min_uptime = self.config.get('MIN_UPTIME', 300)  # 5 minutes default
        if self._get_uptime() < min_uptime:
            logger.debug("System uptime below minimum threshold")
            return False
        
        # Check cooldown period
        cooldown = self.config.get('SUSPENSION_COOLDOWN', 1800)  # 30 minutes default
        if self.last_suspension and \
           (datetime.now() - self.last_suspension).total_seconds() < cooldown:
            logger.debug("System in suspension cooldown period")
            return False
        
        # Check all services
        for service_name, checker in self.services.items():
            try:
                if checker.is_active():
                    logger.info(f"Service {service_name} is active")
                    return False
            except Exception as e:
                logger.error(f"Error checking {service_name}: {e}")
                return False  # Err on the side of caution
        
        return True
    
    def check_grace_period(self) -> bool:
        """
        Wait through grace period, checking for activity.
        
        Returns:
            bool: True if system remained idle through grace period
        """
        logger.info(f"Starting grace period of {self.grace_period} seconds")
        start_time = time.time()
        check_interval = min(60, self.grace_period / 10)  # Check at least 10 times
        
        while time.time() - start_time < self.grace_period:
            # Check for new activity
            if not self.should_suspend():
                logger.info("Activity detected during grace period")
                return False
            
            # Wait before next check
            time.sleep(check_interval)
        
        logger.info("Grace period completed with no activity")
        return True
    
    def suspend_system(self) -> bool:
        """
        Execute system suspension.
        
        Returns:
            bool: True if suspension was successful
        """
        try:
            # Set wake-up timer
            if not self._set_wake_timer():
                return False
            
            # Sync filesystems
            logger.info("Syncing filesystems...")
            subprocess.run(['sync'], check=True)
            
            # Run pre-suspension hooks
            if not self._run_hooks('pre-suspend'):
                return False
            
            # Execute suspension
            logger.info("Initiating system suspension...")
            result = subprocess.run(
                ['systemctl', 'suspend'],
                check=True,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                self.last_suspension = datetime.now()
                self.suspension_count += 1
                logger.info("System suspension successful")
                return True
            else:
                logger.error(f"Suspension failed: {result.stderr}")
                return False
                
        except subprocess.CalledProcessError as e:
            logger.error(f"Error during suspension: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during suspension: {e}")
            return False
        finally:
            # Always run post-suspension hooks
            self._run_hooks('post-suspend')
    
    def get_status_summary(self) -> Dict[str, bool]:
        """
        Get current status of all services.
        
        Returns:
            Dict mapping service names to their activity status
        """
        return {
            name: checker.is_active()
            for name, checker in self.services.items()
        }
    
    def _parse_wake_times(self, wake_times: List[str]) -> List[datetime]:
        """Parse wake-up time strings into datetime objects."""
        parsed_times = []
        current_date = datetime.now().date()
        
        for time_str in wake_times:
            try:
                hour, minute = map(int, time_str.split(':'))
                wake_time = datetime.combine(
                    current_date,
                    datetime.min.time().replace(hour=hour, minute=minute)
                )
                parsed_times.append(wake_time)
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid wake time format '{time_str}': {e}")
        
        return sorted(parsed_times)
    
    def _get_next_wake_time(self) -> Optional[datetime]:
        """Calculate next wake-up time based on schedule."""
        if not self.wake_times:
            return None
            
        now = datetime.now()
        tomorrow = now.date() + timedelta(days=1)
        
        # Check today's remaining wake times
        for wake_time in self.wake_times:
            candidate = datetime.combine(now.date(), wake_time.time())
            if candidate > now:
                return candidate
        
        # If no more times today, use first time tomorrow
        return datetime.combine(tomorrow, self.wake_times[0].time())
    
    def _set_wake_timer(self) -> bool:
        """
        Set system wake-up timer.
        
        Returns:
            bool: True if wake timer was set successfully
        """
        next_wake = self._get_next_wake_time()
        if not next_wake:
            logger.warning("No wake-up times configured")
            return True  # Not a critical error
        
        try:
            wake_seconds = int((next_wake - datetime.now()).total_seconds())
            logger.info(f"Setting wake timer for {next_wake}")
            
            result = subprocess.run(
                ['rtcwake', '-m', 'no', '-s', str(wake_seconds)],
                check=True,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                logger.info(f"Wake timer set for {next_wake}")
                return True
            else:
                logger.error(f"Failed to set wake timer: {result.stderr}")
                return False
                
        except subprocess.CalledProcessError as e:
            logger.error(f"Error setting wake timer: {e}")
            return False
    
    def _run_hooks(self, hook_type: str) -> bool:
        """
        Run pre/post suspension hook scripts.
        
        Args:
            hook_type: Type of hook to run ('pre-suspend' or 'post-suspend')
            
        Returns:
            bool: True if all hooks ran successfully
        """
        hook_dir = Path(f"/etc/mediaserver-autosuspend/hooks/{hook_type}.d")
        if not hook_dir.exists():
            return True
        
        success = True
        for hook in sorted(hook_dir.glob('*.sh')):
            try:
                logger.info(f"Running {hook_type} hook: {hook.name}")
                result = subprocess.run(
                    [str(hook)],
                    check=True,
                    capture_output=True,
                    text=True
                )
                
                if result.returncode != 0:
                    logger.error(f"Hook {hook.name} failed: {result.stderr}")
                    success = False
                    
            except Exception as e:
                logger.error(f"Error running hook {hook.name}: {e}")
                success = False
        
        return success
    
    def _get_uptime(self) -> float:
        """
        Get system uptime in seconds.
        
        Returns:
            float: System uptime in seconds
        """
        try:
            with open('/proc/uptime', 'r') as f:
                return float(f.readline().split()[0])
        except Exception as e:
            logger.error(f"Error reading uptime: {e}")
            return float('inf')  # Prevent suspension on error
