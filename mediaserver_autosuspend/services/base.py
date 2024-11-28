"""
Base service checker interface for MediaServer AutoSuspend.

This module provides the abstract base class for all service checkers.
Each service checker must implement this interface to provide consistent
activity checking functionality.
"""

from abc import ABC, abstractmethod
import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

class ServiceCheckError(Exception):
    """Base exception for service checker errors."""
    pass

class ServiceConnectionError(ServiceCheckError):
    """Exception raised when service connection fails."""
    pass

class ServiceConfigError(ServiceCheckError):
    """Exception raised when service configuration is invalid."""
    pass

class ServiceChecker(ABC):
    """Abstract base class for service checkers."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize service checker.
        
        Args:
            config: Configuration dictionary
            
        Raises:
            ServiceConfigError: If required configuration is missing
        """
        self.config = config
        self.logger = logging.getLogger(f"autosuspend.services.{self.__class__.__name__}")
        self.name = self.__class__.__name__.replace('Checker', '')
        
        # Statistics tracking
        self.last_check: Optional[datetime] = None
        self.last_active: Optional[datetime] = None
        self.total_checks: int = 0
        self.active_checks: int = 0
        self.error_count: int = 0
        self.last_error: Optional[Exception] = None
        self.last_error_time: Optional[datetime] = None
        
        # Rate limiting
        self._min_check_interval = timedelta(
            seconds=config.get('MIN_CHECK_INTERVAL', 1)
        )
    
    @abstractmethod
    def check_activity(self) -> bool:
        """
        Check if service has any active tasks or sessions.
        
        Returns:
            bool: True if service is active, False otherwise
            
        Raises:
            ServiceCheckError: If check fails
        """
        pass
    
    def is_active(self) -> bool:
        """
        Check service activity with error handling and statistics.
        
        Returns:
            bool: True if service is active, False if inactive or error
        """
        try:
            # Enforce minimum check interval
            if self.last_check and \
               datetime.now() - self.last_check < self._min_check_interval:
                self.logger.debug("Check throttled by minimum interval")
                return self.was_recently_active()
            
            # Update statistics
            self.total_checks += 1
            self.last_check = datetime.now()
            
            # Perform activity check
            is_active = self.check_activity()
            
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
            self.logger.error(f"Error checking {self.name}: {str(e)}")
            return False  # Assume inactive on error
    
    def was_recently_active(self, threshold: Optional[int] = None) -> bool:
        """
        Check if service was active recently.
        
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
            Dict containing service statistics
        """
        return {
            'name': self.name,
            'total_checks': self.total_checks,
            'active_checks': self.active_checks,
            'error_count': self.error_count,
            'last_check': self.last_check.isoformat() if self.last_check else None,
            'last_active': self.last_active.isoformat() if self.last_active else None,
            'last_error': str(self.last_error) if self.last_error else None,
            'last_error_time': self.last_error_time.isoformat() if self.last_error_time else None,
            'activity_rate': (
                self.active_checks / self.total_checks
                if self.total_checks > 0 else 0
            )
        }
    
    def validate_config(self, required_keys: list) -> None:
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
                f"Missing required configuration keys: {missing_keys}"
            )
    
    def reset_statistics(self) -> None:
        """Reset all service statistics."""
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
