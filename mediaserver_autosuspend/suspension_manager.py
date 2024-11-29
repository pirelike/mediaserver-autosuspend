"""
SuspensionManager for MediaServer AutoSuspend.

This module handles the core suspension logic, including:
- Service activity monitoring
- Grace period management
- System suspension execution
- Wake-up timer configuration
- Pre/post suspension hook execution
"""

import os
import time
import logging
import subprocess
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

class SuspensionError(Exception):
    """Base exception for suspension-related errors."""
    pass

class WakeTimerError(SuspensionError):
    """Exception raised when setting wake timer fails."""
    pass

class HookExecutionError(SuspensionError):
    """Exception raised when a suspension hook fails."""
    pass

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
        
        # Core timing settings
        self.grace_period = config.get('GRACE_PERIOD', 600)
        self.check_interval = config.get('CHECK_INTERVAL', 60)
        self.min_uptime = config.get('MIN_UPTIME', 300)
        self.cooldown_period = config.get('SUSPENSION_COOLDOWN', 1800)
        
        # State tracking
        self.last_suspension: Optional[datetime] = None
        self.suspension_count = 0
        self.last_error: Optional[Exception] = None
        
        # Load wake-up schedule
        self.wake_times = self._parse_wake_times(
            config.get('WAKE_UP_TIMES', ["07:00"])
        )
        
        # Hook configuration
        self.hooks_dir = Path(config.get('HOOKS_DIR', '/etc/mediaserver-autosuspend/hooks'))
        self.hooks_enabled = config.get('ENABLE_HOOKS', True)
        
        # Create hook directories if enabled
        if self.hooks_enabled:
            self._ensure_hook_directories()
    
    def should_suspend(self) -> bool:
        """
        Check if system should be suspended.
        
        Returns:
            bool: True if system should be suspended
            
        Note:
            Checks minimum uptime, cooldown period, and service activity
        """
        # Check minimum uptime
        if self._get_uptime() < self.min_uptime:
            logger.debug(f"System uptime below minimum threshold: {self._get_uptime()}s")
            return False
        
        # Check cooldown period
        if self.last_suspension:
            elapsed = (datetime.now() - self.last_suspension).total_seconds()
            if elapsed < self.cooldown_period:
                logger.debug(f"System in suspension cooldown: {elapsed}s elapsed")
                return False
        
        # Check all services for activity
        active_services = []
        for service_name, checker in self.services.items():
            try:
                if checker.is_active():
                    active_services.append(service_name)
            except Exception as e:
                logger.error(f"Error checking {service_name}: {e}")
                return False  # Err on the side of caution
        
        if active_services:
            logger.info(f"Active services detected: {', '.join(active_services)}")
            return False
        
        logger.info("No active services detected")
        return True
    
    def check_grace_period(self) -> bool:
        """
        Wait through grace period, checking for activity.
        
        Returns:
            bool: True if system remained idle through grace period
            
        Note:
            Performs periodic checks during grace period to detect new activity
        """
        logger.info(f"Starting grace period of {self.grace_period} seconds")
        start_time = time.time()
        check_interval = min(60, self.grace_period / 10)  # At least 10 checks
        
        while time.time() - start_time < self.grace_period:
            # Check for new activity
            if not self.should_suspend():
                logger.info("Activity detected during grace period")
                return False
            
            # Wait before next check
            remaining = self.grace_period - (time.time() - start_time)
            sleep_time = min(check_interval, remaining)
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        logger.info("Grace period completed with no activity")
        return True
    
    def suspend_system(self) -> bool:
        """
        Execute system suspension with all safety checks.
        
        Returns:
            bool: True if suspension was successful
            
        Note:
            Handles wake timer setup, filesystem sync, and hook execution
        """
        try:
            # Run pre-suspension checks
            self._pre_suspension_checks()
            
            # Set wake-up timer
            if not self._set_wake_timer():
                raise WakeTimerError("Failed to set system wake timer")
            
            # Run pre-suspension hooks
            if self.hooks_enabled and not self._run_hooks('pre-suspend'):
                raise HookExecutionError("Pre-suspension hooks failed")
            
            # Sync filesystems
            logger.info("Syncing filesystems...")
            subprocess.run(['sync'], check=True, capture_output=True)
            
            # Execute suspension
            logger.info("Initiating system suspension...")
            result = subprocess.run(
                ['systemctl', 'suspend'],
                check=True,
                capture_output=True,
                text=True
            )
            
            # Update suspension state
            self.last_suspension = datetime.now()
            self.suspension_count += 1
            logger.info("System suspension successful")
            
            return True
            
        except Exception as e:
            self.last_error = e
            logger.error(f"Suspension failed: {str(e)}")
            return False
            
        finally:
            # Always run post-suspension hooks
            if self.hooks_enabled:
                self._run_hooks('post-suspend')
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get comprehensive status of suspension manager.
        
        Returns:
            Dict containing current status and statistics
        """
        return {
            'uptime': self._get_uptime(),
            'last_suspension': self.last_suspension.isoformat() if self.last_suspension else None,
            'suspension_count': self.suspension_count,
            'last_error': str(self.last_error) if self.last_error else None,
            'next_wake_time': self._get_next_wake_time(),
            'service_status': self.get_service_status(),
            'config': {
                'grace_period': self.grace_period,
                'check_interval': self.check_interval,
                'min_uptime': self.min_uptime,
                'cooldown_period': self.cooldown_period
            }
        }
    
    def get_service_status(self) -> Dict[str, bool]:
        """
        Get current status of all services.
        
        Returns:
            Dict mapping service names to their activity status
        """
        return {
            name: checker.is_active()
            for name, checker in self.services.items()
        }
    
    def _pre_suspension_checks(self) -> None:
        """
        Perform pre-suspension safety checks.
        
        Raises:
            SuspensionError: If any safety check fails
        """
        # Verify required commands exist
        for cmd in ['systemctl', 'rtcwake', 'sync']:
            if not self._command_exists(cmd):
                raise SuspensionError(f"Required command not found: {cmd}")
        
        # Check filesystem space
        if self._get_fs_usage('/') > 95:
            raise SuspensionError("Root filesystem usage above 95%")
    
    def _parse_wake_times(self, wake_times: List[str]) -> List[datetime]:
        """
        Parse wake-up time strings into datetime objects.
        
        Args:
            wake_times: List of time strings in HH:MM format
            
        Returns:
            List of parsed datetime objects
        """
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
        """
        Calculate next wake-up time based on schedule.
        
        Returns:
            Next scheduled wake time or None if no schedule
        """
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
        Set system wake-up timer using rtcwake.
        
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
        hook_dir = self.hooks_dir / f"{hook_type}.d"
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
    
    def _ensure_hook_directories(self) -> None:
        """Create hook directories if they don't exist."""
        for hook_type in ['pre-suspend', 'post-suspend']:
            hook_dir = self.hooks_dir / f"{hook_type}.d"
            hook_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_uptime(self) -> float:
        """
        Get system uptime in seconds.
        
        Returns:
            System uptime in seconds
        """
        try:
            with open('/proc/uptime', 'r') as f:
                return float(f.readline().split()[0])
        except Exception as e:
            logger.error(f"Error reading uptime: {e}")
            return float('inf')  # Prevent suspension on error
    
    def _command_exists(self, cmd: str) -> bool:
        """
        Check if a command exists in system PATH.
        
        Args:
            cmd: Command to check
            
        Returns:
            bool: True if command exists
        """
        try:
            subprocess.run(['which', cmd], capture_output=True, check=True)
            return True
        except subprocess.CalledProcessError:
            return False
    
    def _get_fs_usage(self, path: str) -> float:
        """
        Get filesystem usage percentage.
        
        Args:
            path: Path to check
            
        Returns:
            Usage percentage (0-100)
        """
        try:
            stat = os.statvfs(path)
            return 100 * (1 - stat.f_bavail / stat.f_blocks)
        except Exception as e:
            logger.error(f"Error checking filesystem usage: {e}")
            return 0.0  # Assume safe value on error
