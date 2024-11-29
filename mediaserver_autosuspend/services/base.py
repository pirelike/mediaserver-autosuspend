"""
Base service checker interface for MediaServer AutoSuspend.

This module defines the abstract base class that all service checkers must implement.
It provides common functionality for service status checking, error handling,
and statistics tracking.

Example:
    class MyServiceChecker(ServiceChecker):
        def __init__(self, config):
            super().__init__(config)
            self.api_key = config['MY_SERVICE_API_KEY']
            
        def check_activity(self):
            # Implement service-specific activity check
            return False
"""

from abc import ABC, abstractmethod
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

class ServiceCheckError(Exception):
    """Base exception class for service checker errors."""
    pass

class ServiceConnectionError(ServiceCheckError):
    """Raised when a service connection fails."""
    pass

class ServiceConfigError(ServiceCheckError):
    """Raised when service configuration is invalid."""
    pass

class ServiceChecker(ABC):
    """
    Abstract base class for service activity checkers.
    
    Each service checker must inherit from this class and implement
    the check_activity method to provide service-specific functionality.
    
    Attributes:
        config (Dict[str, Any]): Configuration dictionary
        logger (logging.Logger): Logger instance for this checker
        name (str): Service name derived from class name
        last_check (Optional[datetime]): Timestamp of last activity check
        last_active (Optional[datetime]): Timestamp when service was last active
        total_checks (int): Total number of activity checks performed
        active_checks (int): Number of checks that found activity
        error_count (int): Number of errors encountered
        last_error (Optional[Exception]): Most recent error encountered
        last_error_time (Optional[datetime]): Timestamp of most recent error
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize service checker with configuration.
        
        Args:
            config: Configuration dictionary containing service settings
            
        Raises:
            ServiceConfigError: If required configuration is missing
        """
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.name = self.__class__.__name__.replace('Checker', '')
        
        # Initialize tracking attributes
        self.last_check: Optional[datetime] = None
        self.last_active: Optional[datetime] = None
        self.total_checks: int = 0
        self.active_checks: int = 0
        self.error_count: int = 0
        self.last_error: Optional[Exception] = None
        self.last_error_time: Optional[datetime] = None
        
        # Configure minimum check interval
        self._min_check_interval = timedelta(
            seconds=config.get('MIN_CHECK_INTERVAL', 1)
        )
    
    @abstractmethod
    def check_activity(self) -> bool:
        """
        Check if service has any active tasks or sessions.
        
        This method must be implemented by each service checker to provide
        service-specific activity detection logic.
        
        Returns:
            bool: True if service is active, False otherwise
            
        Raises:
            ServiceCheckError: If check fails
        """
        pass
    
    def is_active(self) -> bool:
        """
        Check service activity with error handling and statistics tracking.
        
        This method wraps the service-specific check_activity method with
        common error handling, rate limiting, and statistics tracking.
        
        Returns:
            bool: True if service is active, False if inactive or error
        """
        try:
            # Enforce rate limiting
            if self.last_check and \
               datetime.now() - self.last_check < self._min_check_interval:
                self.logger.debug(
                    f"Check throttled by minimum interval "
                    f"({self._min_check_interval.total_seconds()}s)"
                )
                return self.was_recently_active()
            
            # Update check statistics
            self.total_checks += 1
            self.last_check = datetime.now()
            
            # Perform service check
            is_active = self.check_activity()
            
            # Update activity statistics
            if is_active:
                self.active_checks += 1
                self.last_active = datetime.now()
                self.logger.info(f"{self.name} is active")
            else:
                self.logger.debug(f"{self.name} is inactive")
            
            return is_active
            
        except Exception as e:
            self.error_count += 1
            self.last_error = e
            self.last_error_time = datetime.now()
            self.logger.error(
                f"Error checking {self.name}: {str(e)}",
                exc_info=self.config.get('DEBUG_MODE', False)
            )
            return False  # Assume inactive on error
    
    def was_recently_active(self, threshold: Optional[int] = None) -> bool:
        """
        Check if service was active within the specified time threshold.
        
        Args:
            threshold: Time threshold in seconds (default: MIN_CHECK_INTERVAL)
            
        Returns:
            bool: True if service was active within threshold
        """
        if not self.last_active:
            return False
            
        if threshold is None:
            threshold = self._min_check_interval.total_seconds()
            
        return (datetime.now() - self.last_active).total_seconds() < threshold
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get service checker statistics.
        
        Returns:
            Dict containing service statistics and metrics
        """
        return {
            'name': self.name,
            'total_checks': self.total_checks,
            'active_checks': self.active_checks,
            'error_count': self.error_count,
            'last_check': self.last_check.isoformat() if self.last_check else None,
            'last_active': self.last_active.isoformat() if self.last_active else None,
            'last_error': str(self.last_error) if self.last_error else None,
            'last_error_time': (
                self.last_error_time.isoformat()
                if self.last_error_time else None
            ),
            'activity_rate': (
                self.active_checks / self.total_checks
                if self.total_checks > 0 else 0
            ),
            'error_rate': (
                self.error_count / self.total_checks
                if self.total_checks > 0 else 0
            )
        }
    
    def validate_config(self, required_keys: List[str]) -> None:
        """
        Validate service configuration.
        
        Args:
            required_keys: List of required configuration keys
            
        Raises:
            ServiceConfigError: If required keys are missing
        """
        missing_keys = [
            key for key in required_keys
            if key not in self.config
        ]
        
        if missing_keys:
            raise ServiceConfigError(
                f"Missing required configuration for {self.name}: {missing_keys}"
            )
    
    def reset_statistics(self) -> None:
        """Reset all service statistics to initial values."""
        self.total_checks = 0
        self.active_checks = 0
        self.error_count = 0
        self.last_check = None
        self.last_active = None
        self.last_error = None
        self.last_error_time = None
    
    def __str__(self) -> str:
        """Get string representation of service checker."""
        return f"{self.name} ServiceChecker"
    
    def __repr__(self) -> str:
        """Get detailed string representation of service checker."""
        return (
            f"{self.__class__.__name__}("
            f"total_checks={self.total_checks}, "
            f"active_checks={self.active_checks}, "
            f"error_count={self.error_count})"
        )
