"""
Configuration management for MediaServer AutoSuspend.

This module handles loading, validation, and management of configuration settings
from multiple sources including files, environment variables, and defaults.
"""

import os
import json
import logging
import re
from pathlib import Path
from copy import deepcopy
from typing import Dict, Any, Optional, List, Set

logger = logging.getLogger(__name__)

# Default configuration values
DEFAULT_CONFIG = {
    # Service URLs with default localhost endpoints
    "JELLYFIN_URL": "http://localhost:8096",
    "PLEX_URL": "http://localhost:32400",
    "RADARR_URL": "http://localhost:7878",
    "SONARR_URL": "http://localhost:8989",
    "NEXTCLOUD_URL": "http://localhost:9000",
    
    # Service feature flags
    "PLEX_MONITOR_TRANSCODING": True,
    "PLEX_IGNORE_PAUSED": False,
    "NEXTCLOUD_CPU_THRESHOLD": 0.5,
    
    # Timing configurations
    "GRACE_PERIOD": 600,  # 10 minutes
    "CHECK_INTERVAL": 60,  # 1 minute
    "MIN_UPTIME": 300,    # 5 minutes minimum uptime
    "SUSPENSION_COOLDOWN": 1800,  # 30 minutes between suspension attempts
    
    # Wake-up schedule
    "WAKE_UP_TIMES": ["07:00", "13:00", "19:00"],
    "TIMEZONE": "UTC",
    
    # Service enablement flags
    "SERVICES": {
        "jellyfin": True,
        "plex": False,
        "sonarr": True,
        "radarr": True,
        "nextcloud": True,
        "system": True
    },
    
    # System monitoring settings
    "IGNORE_USERS": [],
    "SYSTEM_LOAD_THRESHOLD": 0.5,
    "CHECK_SYSTEM_LOAD": True,
    
    # Hooks and paths
    "HOOKS_DIR": "/etc/mediaserver-autosuspend/hooks",
    
    # Logging configuration
    "LOG_LEVEL": "INFO",
    "LOG_FILE": "/var/log/mediaserver-autosuspend/mediaserver-autosuspend.log",
    "MAX_LOG_SIZE": 10485760,    # 10MB
    "LOG_BACKUP_COUNT": 5,
    "LOG_JSON": False,
    "USE_SYSLOG": False,
    "LOG_COLORS": True,
    
    # Debug settings
    "MIN_CHECK_INTERVAL": 1,
    "AUTO_DUMP_ON_ERROR": False,
    "DEBUG_MODE": False
}

# Required API keys/tokens for each service
REQUIRED_KEYS = {
    "jellyfin": {"JELLYFIN_API_KEY"},
    "plex": {"PLEX_TOKEN"},
    "sonarr": {"SONARR_API_KEY"},
    "radarr": {"RADARR_API_KEY"},
    "nextcloud": {"NEXTCLOUD_TOKEN"}
}

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
        self._load_paths = self._get_config_paths()
    
    def load_config(self) -> Dict[str, Any]:
        """
        Load and validate configuration from all sources.
        
        Returns:
            Dict containing merged configuration
            
        Raises:
            ConfigurationError: If configuration cannot be loaded or validated
        """
        # Load from file if specified, otherwise try standard locations
        if self.config_path:
            self._load_from_file(self.config_path)
        else:
            self._load_from_first_available()
        
        # Load environment variables
        self._load_from_env()
        
        # Validate configuration
        self._validate_config()
        
        return self.config
    
    def _get_config_paths(self) -> List[Path]:
        """Get list of standard configuration file locations."""
        return [
            Path.cwd() / "config.json",
            Path.home() / ".config" / "mediaserver-autosuspend" / "config.json",
            Path("/etc/mediaserver-autosuspend/config.json")
        ]
    
    def _load_from_first_available(self) -> None:
        """Load configuration from first available standard location."""
        for path in self._load_paths:
            if path.is_file():
                try:
                    self._load_from_file(str(path))
                    logger.info(f"Loaded configuration from {path}")
                    return
                except Exception as e:
                    logger.warning(f"Failed to load config from {path}: {e}")
        
        logger.warning("No configuration file found in standard locations")
    
    def _load_from_file(self, path: str) -> None:
        """
        Load configuration from specified file.
        
        Args:
            path: Path to configuration file
            
        Raises:
            ConfigurationError: If file cannot be loaded
        """
        try:
            with open(path) as f:
                file_config = json.load(f)
                self.config.update(file_config)
        except FileNotFoundError:
            raise ConfigurationError(f"Configuration file not found: {path}")
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON in configuration file: {e}")
        except Exception as e:
            raise ConfigurationError(f"Error loading configuration file: {e}")
    
    def _load_from_env(self) -> None:
        """Load configuration from environment variables."""
        prefix = "AUTOSUSPEND_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix):]
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
        self._validate_services()
        self._validate_urls()
        self._validate_timing()
        self._validate_wake_times()
        self._validate_thresholds()
        self._validate_paths()
    
    def _validate_services(self) -> None:
        """Validate service configuration and required keys."""
        enabled_services = self.config.get('SERVICES', {})
        
        # Ensure only one media service is enabled
        if enabled_services.get('jellyfin', False) and enabled_services.get('plex', False):
            raise ConfigValidationError(
                "Only one media service (Jellyfin or Plex) should be enabled"
            )
        
        # Check required keys for enabled services
        missing_keys: Set[str] = set()
        for service, required in REQUIRED_KEYS.items():
            if enabled_services.get(service, False):
                missing = required - set(self.config.keys())
                if missing:
                    missing_keys.update(missing)
        
        if missing_keys:
            raise ConfigValidationError(
                f"Missing required configuration keys: {missing_keys}"
            )
    
    def _validate_urls(self) -> None:
        """Validate URL formats."""
        url_keys = [
            'JELLYFIN_URL', 'PLEX_URL', 'RADARR_URL',
            'SONARR_URL', 'NEXTCLOUD_URL'
        ]
        for key in url_keys:
            url = self.config.get(key, '')
            if url and not url.startswith(('http://', 'https://')):
                raise ConfigValidationError(f"Invalid URL format for {key}: {url}")
    
    def _validate_timing(self) -> None:
        """Validate timing-related configurations."""
        timing_checks = {
            'GRACE_PERIOD': (0, None),
            'CHECK_INTERVAL': (1, None),
            'MIN_UPTIME': (0, None),
            'SUSPENSION_COOLDOWN': (0, None),
            'MIN_CHECK_INTERVAL': (1, 60)
        }
        
        for key, (min_val, max_val) in timing_checks.items():
            value = self.config.get(key, 0)
            if not isinstance(value, (int, float)) or value < min_val:
                raise ConfigValidationError(
                    f"{key} must be a number >= {min_val}"
                )
            if max_val and value > max_val:
                raise ConfigValidationError(
                    f"{key} must be <= {max_val}"
                )
    
    def _validate_wake_times(self) -> None:
        """Validate wake-up time format."""
        wake_times = self.config.get('WAKE_UP_TIMES', [])
        if not isinstance(wake_times, list):
            raise ConfigValidationError("WAKE_UP_TIMES must be a list")
        
        time_pattern = re.compile(r'^([01]\d|2[0-3]):([0-5]\d)$')
        for time_str in wake_times:
            if not time_pattern.match(time_str):
                raise ConfigValidationError(
                    f"Invalid wake-up time format: {time_str}"
                )
    
    def _validate_thresholds(self) -> None:
        """Validate threshold values."""
        threshold_checks = {
            'NEXTCLOUD_CPU_THRESHOLD': (0.0, 1.0),
            'SYSTEM_LOAD_THRESHOLD': (0.0, 1.0)
        }
        
        for key, (min_val, max_val) in threshold_checks.items():
            value = self.config.get(key, 0)
            if not isinstance(value, (int, float)) or \
               not min_val <= value <= max_val:
                raise ConfigValidationError(
                    f"{key} must be between {min_val} and {max_val}"
                )
    
    def _validate_paths(self) -> None:
        """Validate and create required directories."""
        required_dirs = [
            os.path.dirname(self.config.get('LOG_FILE', '')),
            self.config.get('HOOKS_DIR', '')
        ]
        
        for dir_path in required_dirs:
            if dir_path:
                try:
                    os.makedirs(dir_path, exist_ok=True)
                except Exception as e:
                    raise ConfigValidationError(
                        f"Failed to create directory {dir_path}: {e}"
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
            'PLEX_TOKEN': 'your-plex-token',
            'RADARR_API_KEY': 'your-radarr-api-key',
            'SONARR_API_KEY': 'your-sonarr-api-key',
            'NEXTCLOUD_TOKEN': 'your-nextcloud-token'
        })
        
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w') as f:
                json.dump(example_config, f, indent=2)
            logger.info(f"Example configuration written to {output_path}")
        except Exception as e:
            raise ConfigurationError(f"Error writing example configuration: {e}")

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
