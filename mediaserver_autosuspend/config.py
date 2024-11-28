"""
Configuration management for MediaServer AutoSuspend.

This module handles loading, validation, and management of configuration settings.
It provides defaults, schema validation, and environment variable overrides.
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from copy import deepcopy

logger = logging.getLogger(__name__)

# Default configuration values
DEFAULT_CONFIG = {
    "JELLYFIN_URL": "http://localhost:8096",
    "RADARR_URL": "http://localhost:7878",
    "SONARR_URL": "http://localhost:8989",
    "NEXTCLOUD_URL": "http://localhost:9000",
    
    "GRACE_PERIOD": 600,  # 10 minutes
    "CHECK_INTERVAL": 60,  # 1 minute
    "LOG_LEVEL": "INFO",
    "LOG_FILE": "/var/log/mediaserver-autosuspend.log",
    "MAX_LOG_SIZE": 10485760,  # 10MB
    "LOG_BACKUP_COUNT": 5,
    
    "SERVICES": {
        "jellyfin": True,
        "sonarr": True,
        "radarr": True,
        "nextcloud": True,
        "system": True
    },
    
    "NEXTCLOUD_CPU_THRESHOLD": 0.5,
    "WAKE_UP_TIMES": ["07:00", "13:00", "19:00"],
    "TIMEZONE": "UTC",
    
    "AUTO_DUMP_ON_ERROR": False,
    "DEBUG_MODE": False
}

# Required configuration keys that must be provided
REQUIRED_KEYS = {
    "JELLYFIN_API_KEY",
    "RADARR_API_KEY",
    "SONARR_API_KEY",
    "NEXTCLOUD_TOKEN"
}

# Environment variable prefix for configuration overrides
ENV_PREFIX = "AUTOSUSPEND_"

class ConfigurationError(Exception):
    """Base exception for configuration-related errors."""
    pass

class ConfigValidationError(ConfigurationError):
    """Exception raised when configuration validation fails."""
    pass

class ConfigurationManager:
    """Manages loading and validation of configuration settings."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration manager.
        
        Args:
            config_path: Optional path to configuration file
        """
        self.config_path = config_path
        self.config: Dict[str, Any] = deepcopy(DEFAULT_CONFIG)
    
    def load_config(self) -> Dict[str, Any]:
        """
        Load and validate configuration from all sources.
        
        Returns:
            Dict containing merged configuration
        
        Raises:
            ConfigurationError: If configuration loading fails
            ConfigValidationError: If configuration validation fails
        """
        # Load configuration file if specified
        if self.config_path:
            self._load_from_file()
        
        # Load environment variables
        self._load_from_env()
        
        # Validate configuration
        self._validate_config()
        
        return self.config
    
    def _load_from_file(self) -> None:
        """Load configuration from file."""
        try:
            with open(self.config_path) as f:
                file_config = json.load(f)
                self.config.update(file_config)
        except FileNotFoundError:
            raise ConfigurationError(f"Configuration file not found: {self.config_path}")
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON in configuration file: {e}")
        except Exception as e:
            raise ConfigurationError(f"Error loading configuration file: {e}")
    
    def _load_from_env(self) -> None:
        """Load configuration from environment variables."""
        for key, value in os.environ.items():
            if key.startswith(ENV_PREFIX):
                config_key = key[len(ENV_PREFIX):]
                try:
                    # Try to parse as JSON for complex values
                    self.config[config_key] = json.loads(value)
                except json.JSONDecodeError:
                    # Use string value if not valid JSON
                    self.config[config_key] = value
    
    def _validate_config(self) -> None:
        """
        Validate configuration settings.
        
        Raises:
            ConfigValidationError: If validation fails
        """
        # Check required keys
        missing_keys = REQUIRED_KEYS - set(self.config.keys())
        if missing_keys:
            raise ConfigValidationError(
                f"Missing required configuration keys: {missing_keys}"
            )
        
        # Validate URLs
        self._validate_urls()
        
        # Validate numeric values
        self._validate_numeric_values()
        
        # Validate service configuration
        self._validate_services()
        
        # Validate wake-up times
        self._validate_wake_times()
    
    def _validate_urls(self) -> None:
        """Validate URL configurations."""
        for key in ['JELLYFIN_URL', 'RADARR_URL', 'SONARR_URL', 'NEXTCLOUD_URL']:
            url = self.config.get(key, '')
            if not url.startswith(('http://', 'https://')):
                raise ConfigValidationError(
                    f"Invalid URL format for {key}: {url}"
                )
    
    def _validate_numeric_values(self) -> None:
        """Validate numeric configuration values."""
        # Check grace period
        grace_period = self.config.get('GRACE_PERIOD', 0)
        if not isinstance(grace_period, (int, float)) or grace_period < 0:
            raise ConfigValidationError(
                f"Invalid GRACE_PERIOD value: {grace_period}"
            )
        
        # Check check interval
        check_interval = self.config.get('CHECK_INTERVAL', 0)
        if not isinstance(check_interval, (int, float)) or check_interval < 1:
            raise ConfigValidationError(
                f"Invalid CHECK_INTERVAL value: {check_interval}"
            )
    
    def _validate_services(self) -> None:
        """Validate service configuration."""
        services = self.config.get('SERVICES', {})
        if not isinstance(services, dict):
            raise ConfigValidationError("SERVICES must be a dictionary")
        
        for service, enabled in services.items():
            if not isinstance(enabled, bool):
                raise ConfigValidationError(
                    f"Service {service} enabled status must be boolean"
                )
    
    def _validate_wake_times(self) -> None:
        """Validate wake-up time configuration."""
        wake_times = self.config.get('WAKE_UP_TIMES', [])
        if not isinstance(wake_times, list):
            raise ConfigValidationError("WAKE_UP_TIMES must be a list")
        
        import re
        time_pattern = re.compile(r'^([01]\d|2[0-3]):([0-5]\d)$')
        
        for time_str in wake_times:
            if not time_pattern.match(time_str):
                raise ConfigValidationError(
                    f"Invalid wake-up time format: {time_str}"
                )
    
    def generate_example_config(self, output_path: str) -> None:
        """
        Generate example configuration file.
        
        Args:
            output_path: Path to write example configuration
        """
        example_config = deepcopy(DEFAULT_CONFIG)
        example_config.update({
            'JELLYFIN_API_KEY': 'your-jellyfin-api-key',
            'RADARR_API_KEY': 'your-radarr-api-key',
            'SONARR_API_KEY': 'your-sonarr-api-key',
            'NEXTCLOUD_TOKEN': 'your-nextcloud-token'
        })
        
        try:
            with open(output_path, 'w') as f:
                json.dump(example_config, f, indent=4)
            logger.info(f"Example configuration written to {output_path}")
        except Exception as e:
            raise ConfigurationError(f"Error writing example configuration: {e}")
    
    def get_config_locations(self) -> list:
        """
        Get list of standard configuration file locations.
        
        Returns:
            List of potential configuration file paths
        """
        return [
            Path.cwd() / "config.json",
            Path.home() / ".config" / "mediaserver-autosuspend" / "config.json",
            Path("/etc/mediaserver-autosuspend/config.json")
        ]

def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration from specified path or search standard locations.
    
    Args:
        config_path: Optional path to configuration file
    
    Returns:
        Dict containing configuration settings
    
    Raises:
        ConfigurationError: If configuration cannot be loaded
    """
    manager = ConfigurationManager(config_path)
    return manager.load_config()
