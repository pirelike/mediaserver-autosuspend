#!/usr/bin/env python3

import os
import sys
import time
import yaml
import subprocess
import logging
import requests
from datetime import datetime
from pathlib import Path
import threading
from typing import Dict, Any, List, Optional, Tuple
import xml.etree.ElementTree as ET
import functools
from enum import Enum
from dataclasses import dataclass, field
import signal
import jsonschema
import atexit

# Constants
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
DEFAULT_TIMEOUT = 5
MAX_RETRIES = 3
RETRY_DELAY = 5
STARTUP_DELAY = 60  # Default startup delay in seconds

# System command paths for security
SYSTEM_COMMANDS = {
    'who': '/usr/bin/who',
    'sync': '/bin/sync',
    'systemctl': '/bin/systemctl',
    'set_wakeup': '/usr/local/bin/set-wakeup.sh'
}

# Configuration schema for validation
CONFIG_SCHEMA = {
    "type": "object",
    "required": ["monitoring", "logging"],
    "properties": {
        "monitoring": {
            "type": "object",
            "required": ["check_interval", "grace_period", "grace_period_check_interval"],
            "properties": {
                "check_interval": {"type": "integer", "minimum": 1},
                "grace_period": {"type": "integer", "minimum": 1},
                "grace_period_check_interval": {"type": "integer", "minimum": 1},
                "max_retries": {"type": "integer", "minimum": 1},
                "retry_delay": {"type": "integer", "minimum": 1}
            }
        },
        "logging": {
            "type": "object",
            "required": ["file", "max_lines"],
            "properties": {
                "file": {"type": "string"},
                "max_lines": {"type": "integer", "minimum": 1}
            }
        },
        "jellyfin": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"},
                "url": {"type": "string", "format": "uri"},
                "api_key": {"type": "string"},
                "timeout": {"type": "integer", "minimum": 1}
            }
        },
        "sonarr": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"},
                "url": {"type": "string", "format": "uri"},
                "api_key": {"type": "string"},
                "timeout": {"type": "integer", "minimum": 1}
            }
        },
        "radarr": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"},
                "url": {"type": "string", "format": "uri"},
                "api_key": {"type": "string"},
                "timeout": {"type": "integer", "minimum": 1}
            }
        },
        "plex": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"},
                "url": {"type": "string", "format": "uri"},
                "token": {"type": "string"},
                "timeout": {"type": "integer", "minimum": 1}
            }
        },
        "emby": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"},
                "url": {"type": "string", "format": "uri"},
                "api_key": {"type": "string"},
                "timeout": {"type": "integer", "minimum": 1}
            }
        },
        "nextcloud": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"},
                "url": {"type": "string", "format": "uri"},
                "token": {"type": "string"},
                "timeout": {"type": "integer", "minimum": 1}
            }
        },
        "raspberry_pi": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"},
                "url": {"type": "string", "format": "uri"},
                "timeout": {"type": "integer", "minimum": 1}
            }
        },
        "system_users": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"}
            }
        }
    }
}

class APICache:
    """Cache for API results to reduce redundant calls."""
    
    def __init__(self, cache_ttl: int = 30):
        """Initialize the API cache.
        
        Args:
            cache_ttl (int): Time to live for cache entries in seconds.
        """
        self._cache = {}
        self._cache_ttl = cache_ttl
        self._lock = threading.Lock()
        
    def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache if it exists and hasn't expired.
        
        Args:
            key (str): Cache key to look up.
            
        Returns:
            Optional[Any]: Cached value if valid, None if expired or missing.
        """
        with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                if time.time() - timestamp <= self._cache_ttl:
                    return value
                del self._cache[key]
            return None
            
    def set(self, key: str, value: Any) -> None:
        """Set a value in the cache with current timestamp.
        
        Args:
            key (str): Cache key to set.
            value (Any): Value to cache.
        """
        with self._lock:
            self._cache[key] = (value, time.time())
            
    def clear(self) -> None:
        """Clear all cached values."""
        with self._lock:
            self._cache.clear()


def cached_api_request(cache_key: str, cache_ttl: int = 30):
    """Decorator to cache API request results.
    
    Args:
        cache_key (str): Base key for the cache entry.
        cache_ttl (int): Time to live for cache entries in seconds.
    """
    def decorator(func):
        # Create a cache instance specific to this function
        cache = APICache(cache_ttl=cache_ttl)
        
        @functools.wraps(func)
        def wrapper(config: Config, logger: logging.Logger, *args, **kwargs):
            # Generate a unique cache key including any relevant args
            full_cache_key = f"{cache_key}:{hash(str(args))}{hash(str(kwargs))}"
            
            # Try to get from cache first
            cached_result = cache.get(full_cache_key)
            if cached_result is not None:
                logger.debug(f"Using cached result for {func.__name__}")
                return cached_result
                
            # If not in cache, call the function and cache the result
            result = func(config, logger, *args, **kwargs)
            cache.set(full_cache_key, result)
            return result
            
        # Add method to clear cache
        wrapper.clear_cache = cache.clear
        return wrapper
    return decorator


class ServiceStatus(Enum):
    """Represents the status of a service."""
    DISABLED = "Disabled"
    ACTIVE = "Active"
    IDLE = "Idle"
    ERROR = "Error"


@dataclass
class ActivityCheckResult:
    """Represents the result of an activity check for a service."""
    service_name: str
    status: ServiceStatus
    details: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


class ActivityHistory:
    """Maintains a history of activity check results."""
    def __init__(self, max_entries: int = 100):
        """Initialize the activity history.
        
        Args:
            max_entries (int): Maximum number of entries to keep in history.
        """
        self.history: List[ActivityCheckResult] = []
        self.max_entries = max_entries
        self._lock = threading.Lock()  # Added thread safety

    def add_entry(self, result: ActivityCheckResult) -> None:
        """Adds an entry to the activity history.

        Args:
            result (ActivityCheckResult): The result of the activity check.
        """
        with self._lock:  # Ensure thread safety
            self.history.append(result)
            if len(self.history) > self.max_entries:
                self.history.pop(0)

    def get_latest_entry(self, service_name: str) -> Optional[ActivityCheckResult]:
        """Get the most recent entry for a specific service.
        
        Args:
            service_name (str): Name of the service to look up.
            
        Returns:
            Optional[ActivityCheckResult]: Most recent entry for the service, if any.
        """
        with self._lock:
            for entry in reversed(self.history):
                if entry.service_name == service_name:
                    return entry
        return None


@dataclass
class SystemStatus:
    """Represents the overall system status."""
    activity_summary: Dict[str, bool]
    last_check_time: datetime
    uptime: float
    grace_period_active: bool
    grace_period_remaining: Optional[float] = None
    active_services: List[str] = field(default_factory=list)

class LineBasedRotatingHandler(logging.Handler):
    """Custom logging handler that maintains a fixed number of lines in the log file using efficient chunked reading."""

    def __init__(self, filename: str, max_lines: int = 500, chunk_size: int = 8192) -> None:
        """Initializes the LineBasedRotatingHandler.

        Args:
            filename (str): The path to the log file.
            max_lines (int): The maximum number of lines to keep in the log file.
            chunk_size (int): Size of chunks to read at a time (in bytes).
        """
        super().__init__()
        self.filename = filename
        self.max_lines = max_lines
        self.chunk_size = chunk_size
        self._lock = threading.Lock()

    def _count_lines_from_end(self, file_obj, num_lines: int) -> List[str]:
        """Efficiently count lines from end of file without loading entire file into memory.
        
        Args:
            file_obj: File object to read from
            num_lines: Number of lines to read from end
            
        Returns:
            List of last num_lines from file
        """
        file_obj.seek(0, os.SEEK_END)
        file_size = remaining_size = file_obj.tell()
        lines = []
        chunk_size = min(self.chunk_size, file_size)
        
        while remaining_size > 0 and len(lines) < num_lines:
            chunk_pos = max(0, remaining_size - chunk_size)
            file_obj.seek(chunk_pos)
            chunk = file_obj.read(min(chunk_size, remaining_size))
            lines.extend(chunk.splitlines())
            remaining_size = chunk_pos
            
        return lines[-num_lines:] if len(lines) > num_lines else lines

    def emit(self, record: logging.LogRecord) -> None:
        """Emits a log record to the log file using efficient chunked reading/writing.

        Args:
            record (logging.LogRecord): The log record to emit.
        """
        try:
            msg = self.format(record) + '\n'

            with self._lock:
                if not os.path.exists(self.filename):
                    # If file doesn't exist, create it with the new message
                    with open(self.filename, 'w') as f:
                        f.write(msg)
                    return

                # Create temporary file for atomic operation
                temp_filename = f"{self.filename}.tmp"
                
                try:
                    with open(self.filename, 'r') as f_in:
                        # Get last max_lines-1 lines (to make room for new line)
                        last_lines = self._count_lines_from_end(f_in, self.max_lines - 1)
                        
                    # Write to temporary file
                    with open(temp_filename, 'w') as f_out:
                        f_out.write('\n'.join(last_lines))
                        if last_lines:  # Add newline only if there are existing lines
                            f_out.write('\n')
                        f_out.write(msg)
                    
                    # Atomic replace
                    os.replace(temp_filename, self.filename)
                    
                finally:
                    # Clean up temp file if it still exists
                    if os.path.exists(temp_filename):
                        os.remove(temp_filename)
                        
        except Exception:
            self.handleError(record)


class Config:
    """Configuration handler for autosuspend."""

    def __init__(self, config_path: str = '/home/mediaserver/scripts/autosuspend_config.yaml') -> None:
        """Initializes the Config object.

        Args:
            config_path (str): Path to the configuration file.
        """
        self.config_path = Path(config_path)
        self.config = self._load_and_validate_config()
        self.activity_history = ActivityHistory()
        self._cache = {}  # Cache for config values
        self._cache_lock = threading.Lock()

    def _load_config(self) -> Dict[str, Any]:
        """Loads the configuration from the YAML file.

        Returns:
            Dict[str, Any]: The configuration data.

        Raises:
            SystemExit: If there is an error loading the config file.
        """
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            sys.exit(1)

    def _validate_config(self, config_data: Dict[str, Any]) -> None:
        """Validates the configuration data against the schema.

        Args:
            config_data: The configuration data to validate.

        Raises:
            ValueError: If the configuration data is invalid.
        """
        try:
            jsonschema.validate(instance=config_data, schema=CONFIG_SCHEMA)
        except jsonschema.exceptions.ValidationError as e:
            raise ValueError(f"Invalid configuration: {e}")

    def _load_and_validate_config(self) -> Dict[str, Any]:
        """Loads and validates the configuration data.

        Returns:
            The validated configuration data.
        """
        config_data = self._load_config()
        self._validate_config(config_data)
        with self._cache_lock:
            self._cache.clear()  # Clear cache when config is reloaded
        return config_data

    def reload_config(self) -> None:
        """Reload configuration file without restart."""
        try:
            new_config = self._load_and_validate_config()
            self.config = new_config
            logging.getLogger('autosuspend').info("Configuration reloaded successfully.")
        except Exception as e:
            logging.getLogger('autosuspend').error(f"Failed to reload configuration: {e}")

    def _get_cached_value(self, key: str, getter_func: callable) -> Any:
        """Get a cached configuration value or compute and cache it.
        
        Args:
            key (str): Cache key
            getter_func (callable): Function to compute value if not cached
            
        Returns:
            Any: The cached or computed value
        """
        with self._cache_lock:
            if key not in self._cache:
                self._cache[key] = getter_func()
            return self._cache[key]
        
def api_request(func):
    """Decorator to handle API request retries and common exceptions."""
    @functools.wraps(func)
    def wrapper(config: Config, logger: logging.Logger, *args, **kwargs):
        max_retries = config.max_retries
        retry_delay = config.retry_delay
        for attempt in range(1, max_retries + 1):
            try:
                return func(config, logger, *args, **kwargs)
            except requests.exceptions.ConnectionError as e:
                logger.error(f"{func.__name__}: Connection error (Attempt {attempt}/{max_retries}) - {e}")
                if attempt < max_retries:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"{func.__name__}: Max retries exceeded. Giving up.")
                    return False
            except requests.exceptions.Timeout as e:
                logger.error(f"{func.__name__}: Request timed out - {e}")
                return False
            except requests.exceptions.HTTPError as e:
                logger.error(f"{func.__name__}: HTTP error ({e.response.status_code}) - {e}")
                return False
            except requests.exceptions.RequestException as e:
                logger.error(f"{func.__name__}: Error connecting to API - {e}")
                return False
            except (ValueError, TypeError) as e:
                logger.error(f"{func.__name__}: Invalid response or data type - {e}")
                return False
            except ET.ParseError as e:
                logger.error(f"{func.__name__}: Failed to parse XML response - {e}")
                return False
    return wrapper


@cached_api_request("jellyfin", cache_ttl=30)
@api_request
def check_jellyfin(config: Config, logger: logging.Logger) -> bool:
    """Check Jellyfin for active playback sessions.

    Args:
        config (Config): The configuration object.
        logger (logging.Logger): The logger object.

    Returns:
        bool: True if an active session is detected, False otherwise.
    """
    service_name = "Jellyfin"
    if not config.jellyfin_enabled:
        logger.info(f"{service_name}: Service disabled. Skipping check.")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.DISABLED
        ))
        return False

    headers = {
        'X-Emby-Authorization': f'MediaBrowser ClientId="JellyfinWeb", DeviceId="", Device="", Version="", Token="{config.jellyfin_api_key}"'
    }
    response = requests.get(
        f"{config.jellyfin_url}/Sessions",
        headers=headers,
        timeout=config.jellyfin_timeout,
        verify=True  # Enable SSL verification
    )
    response.raise_for_status()
    sessions = response.json()

    if not isinstance(sessions, list):
        logger.error(f"{service_name}: Unexpected response format (not a list)")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.ERROR,
            details="Invalid response format"
        ))
        return False

    for session in sessions:
        if session.get('NowPlayingItem') is not None:
            logger.info(f"{service_name}: Active playback session detected")
            config.activity_history.add_entry(ActivityCheckResult(
                service_name=service_name,
                status=ServiceStatus.ACTIVE
            ))
            return True

    logger.info(f"{service_name}: No active playback sessions")
    config.activity_history.add_entry(ActivityCheckResult(
        service_name=service_name,
        status=ServiceStatus.IDLE
    ))
    return False


@cached_api_request("sonarr", cache_ttl=30)
@api_request
def check_sonarr(config: Config, logger: logging.Logger) -> bool:
    """Check Sonarr for active queue items.

    Args:
        config (Config): The configuration object.
        logger (logging.Logger): The logger object.

    Returns:
        bool: True if active downloads are found, False otherwise.
    """
    service_name = "Sonarr"
    if not config.sonarr_enabled:
        logger.info(f"{service_name}: Service disabled. Skipping check.")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.DISABLED
        ))
        return False

    headers = {'X-Api-Key': config.sonarr_api_key}
    response = requests.get(
        f'{config.sonarr_url}/api/v3/queue',
        headers=headers,
        timeout=config.sonarr_timeout,
        verify=config.sonarr_ssl_verify  # Use the correct SSL verification setting from config
    )
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, dict):
        logger.error(f"{service_name}: Unexpected response format (not a dictionary)")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.ERROR,
            details="Invalid response format"
        ))
        return False

    total_records = data.get('totalRecords', 0)

    if total_records > 0:
        logger.info(f"{service_name}: Active queue items found: {total_records}")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.ACTIVE,
            details=f"Active queue items: {total_records}"
        ))
        return True

    logger.info(f"{service_name}: No active queue items")
    config.activity_history.add_entry(ActivityCheckResult(
        service_name=service_name,
        status=ServiceStatus.IDLE
    ))
    return False

@cached_api_request("radarr", cache_ttl=30)
@api_request
def check_radarr(config: Config, logger: logging.Logger) -> bool:
    """Check Radarr for active queue items.

    Args:
        config (Config): The configuration object.
        logger (logging.Logger): The logger object.

    Returns:
        bool: True if active downloads are found, False otherwise.
    """
    service_name = "Radarr"
    if not config.radarr_enabled:
        logger.info(f"{service_name}: Service disabled. Skipping check.")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.DISABLED
        ))
        return False

    headers = {'X-Api-Key': config.radarr_api_key}
    response = requests.get(
        f'{config.radarr_url}/api/v3/queue',
        headers=headers,
        timeout=config.radarr_timeout,
        verify=True
    )
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, dict):
        logger.error(f"{service_name}: Unexpected response format (not a dictionary)")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.ERROR,
            details="Invalid response format"
        ))
        return False

    total_records = data.get('totalRecords', 0)

    if total_records > 0:
        logger.info(f"{service_name}: Active queue items found: {total_records}")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.ACTIVE,
            details=f"Active queue items: {total_records}"
        ))
        return True

    logger.info(f"{service_name}: No active queue items")
    config.activity_history.add_entry(ActivityCheckResult(
        service_name=service_name,
        status=ServiceStatus.IDLE
    ))
    return False


@cached_api_request("nextcloud", cache_ttl=30)
@api_request
def check_nextcloud(config: Config, logger: logging.Logger) -> bool:
    """Check Nextcloud for high CPU load, indicating activity.

    Args:
        config (Config): The configuration object.
        logger (logging.Logger): The logger object.

    Returns:
        bool: True if high CPU load is detected, False otherwise.
    """
    service_name = "Nextcloud"
    if not config.nextcloud_enabled:
        logger.info(f"{service_name}: Service disabled. Skipping check.")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.DISABLED
        ))
        return False

    headers = {
        'NC-Token': config.nextcloud_token,
        'OCS-APIRequest': 'true'
    }
    response = requests.get(
        f"{config.nextcloud_url}/ocs/v2.php/apps/serverinfo/api/v1/info?format=json",
        headers=headers,
        timeout=config.nextcloud_timeout,
        verify=True
    )
    response.raise_for_status()
    data = response.json()

    # Validate response structure using a more robust approach
    try:
        cpu_load = float(data['ocs']['data']['system']['cpuload'][1])
    except (KeyError, IndexError, TypeError, ValueError) as e:
        logger.error(f"{service_name}: Failed to parse response - {str(e)}")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.ERROR,
            details=f"Failed to parse response: {str(e)}"
        ))
        return False

    # Configure threshold through config if needed
    cpu_threshold = 0.5  # Could be made configurable
    if cpu_load > cpu_threshold:
        logger.info(f"{service_name}: High CPU load detected (Load average: {cpu_load:.2f})")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.ACTIVE,
            details=f"CPU Load: {cpu_load:.2f}"
        ))
        return True

    logger.info(f"{service_name}: No high CPU load detected (Load average: {cpu_load:.2f})")
    config.activity_history.add_entry(ActivityCheckResult(
        service_name=service_name,
        status=ServiceStatus.IDLE,
        details=f"CPU Load: {cpu_load:.2f}"
    ))
    return False


@cached_api_request("raspberry_pi", cache_ttl=30)
@api_request
def check_raspberry_pi_activity(config: Config, logger: logging.Logger) -> bool:
    """Check if there's recent activity on the Raspberry Pi (Autowake).

    Args:
        config (Config): The configuration object.
        logger (logging.Logger): The logger object.

    Returns:
        bool: True if recent activity is detected, False otherwise.
    """
    service_name = "Raspberry Pi"
    if not config.raspberry_pi_enabled:
        logger.info(f"{service_name}: Service disabled. Skipping check.")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.DISABLED
        ))
        return False

    response = requests.get(
        f'{config.raspberry_pi_url}/check-activity',
        timeout=config.raspberry_pi_timeout,
        verify=True
    )
    response.raise_for_status()

    try:
        activity_data = response.json()
        if not isinstance(activity_data, dict):
            raise ValueError("Response is not a dictionary")
            
        is_active = activity_data.get('active', False)
        last_activity = activity_data.get('last_activity')
        
        if is_active:
            details = f"Last activity: {last_activity}" if last_activity else "Active"
            logger.info(f"{service_name}: Recent activity detected. {details}")
            config.activity_history.add_entry(ActivityCheckResult(
                service_name=service_name,
                status=ServiceStatus.ACTIVE,
                details=details
            ))
            return True
            
        details = f"Last activity: {last_activity}" if last_activity else "No recent activity"
        logger.info(f"{service_name}: {details}")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.IDLE,
            details=details
        ))
        return False
        
    except (ValueError, TypeError) as e:
        logger.error(f"{service_name}: Failed to parse response - {str(e)}")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.ERROR,
            details=f"Failed to parse response: {str(e)}"
        ))
        return False

@cached_api_request("plex", cache_ttl=30)
@api_request
def check_plex(config: Config, logger: logging.Logger) -> bool:
    """Check Plex for active playback sessions.

    Args:
        config (Config): The configuration object.
        logger (logging.Logger): The logger object.

    Returns:
        bool: True if an active session is detected, False otherwise.
    """
    service_name = "Plex"
    if not config.plex_enabled:
        logger.info(f"{service_name}: Service disabled. Skipping check.")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.DISABLED
        ))
        return False

    headers = {'X-Plex-Token': config.plex_token}
    response = requests.get(
        f"{config.plex_url}/status/sessions",
        headers=headers,
        timeout=config.plex_timeout,
        verify=True
    )
    response.raise_for_status()

    try:
        # Using defusedxml would be better, but staying consistent with imports
        root = ET.fromstring(response.content)
        session_count = int(root.attrib.get('size', 0))
        
        # Get more detailed session information
        active_sessions = []
        for session in root.findall('.//Video'):
            try:
                state = session.attrib.get('state', '')
                title = session.attrib.get('title', 'Unknown')
                user = session.find('.//User')
                username = user.attrib.get('title', 'Unknown') if user is not None else 'Unknown'
                
                if state == 'playing':
                    active_sessions.append(f"{username} - {title}")
            except (AttributeError, KeyError) as e:
                logger.warning(f"Failed to parse session details: {e}")
                continue

        if active_sessions:
            details = f"Active sessions: {'; '.join(active_sessions)}"
            logger.info(f"{service_name}: {details}")
            config.activity_history.add_entry(ActivityCheckResult(
                service_name=service_name,
                status=ServiceStatus.ACTIVE,
                details=details
            ))
            return True

        logger.info(f"{service_name}: No active playback sessions")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.IDLE
        ))
        return False

    except ET.ParseError as e:
        logger.error(f"{service_name}: Failed to parse XML response - {e}")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.ERROR,
            details=f"XML Parse Error: {str(e)}"
        ))
        return False


@cached_api_request("emby", cache_ttl=30)
@api_request
def check_emby(config: Config, logger: logging.Logger) -> bool:
    """Check Emby for active sessions.

    Args:
        config (Config): The configuration object.
        logger (logging.Logger): The logger object.

    Returns:
        bool: True if an active session is detected, False otherwise.
    """
    service_name = "Emby"
    if not config.emby_enabled:
        logger.info(f"{service_name}: Service disabled. Skipping check.")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.DISABLED
        ))
        return False

    headers = {'X-Emby-Token': config.emby_api_key}
    response = requests.get(
        f"{config.emby_url}/emby/Sessions",
        headers=headers,
        timeout=config.emby_timeout,
        verify=True
    )
    response.raise_for_status()
    
    try:
        sessions = response.json()
        if not isinstance(sessions, list):
            raise ValueError("Unexpected response format (not a list)")

        active_sessions = []
        for session in sessions:
            try:
                now_playing = session.get('NowPlayingItem')
                if now_playing:
                    username = session.get('UserName', 'Unknown')
                    title = now_playing.get('Name', 'Unknown')
                    active_sessions.append(f"{username} - {title}")
            except (AttributeError, KeyError) as e:
                logger.warning(f"Failed to parse session details: {e}")
                continue

        if active_sessions:
            details = f"Active sessions: {'; '.join(active_sessions)}"
            logger.info(f"{service_name}: {details}")
            config.activity_history.add_entry(ActivityCheckResult(
                service_name=service_name,
                status=ServiceStatus.ACTIVE,
                details=details
            ))
            return True

        logger.info(f"{service_name}: No active playback sessions")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.IDLE
        ))
        return False

    except (ValueError, TypeError) as e:
        logger.error(f"{service_name}: Failed to parse response - {str(e)}")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.ERROR,
            details=f"Parse Error: {str(e)}"
        ))
        return False


def check_system_activity(config: Config, logger: logging.Logger) -> bool:
    """Check for logged-in users on the system.

    Args:
        config (Config): The configuration object.
        logger (logging.Logger): The logger object.

    Returns:
        bool: True if there are logged-in users, False otherwise.
    """
    service_name = "System Users"
    if not config.system_users_enabled:
        logger.info(f"{service_name}: Service disabled. Skipping check.")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.DISABLED
        ))
        return False

    try:
        # Use subprocess.run instead of check_output for better control
        result = subprocess.run(
            [SYSTEM_COMMANDS['who']],
            capture_output=True,
            text=True,
            timeout=5,  # Add timeout for safety
            check=True
        )
        
        who_output = result.stdout.strip()
        users = [line.split()[0] for line in who_output.split('\n') if line.strip()]
        unique_users = list(set(users))  # Get unique users
        
        if unique_users:
            details = f"Active users: {', '.join(unique_users)}"
            logger.info(f"{service_name}: {details}")
            config.activity_history.add_entry(ActivityCheckResult(
                service_name=service_name,
                status=ServiceStatus.ACTIVE,
                details=details
            ))
            return True
            
        logger.info(f"{service_name}: No active users")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.IDLE
        ))
        return False
        
    except subprocess.TimeoutExpired:
        logger.error(f"{service_name}: Command timed out")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.ERROR,
            details="Command timed out"
        ))
        return False
    except subprocess.CalledProcessError as e:
        logger.error(f"{service_name}: Command failed with return code {e.returncode}")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.ERROR,
            details=f"Command failed: {e.stderr}"
        ))
        return False
    except Exception as e:
        logger.error(f"{service_name}: Unexpected error - {str(e)}")
        config.activity_history.add_entry(ActivityCheckResult(
            service_name=service_name,
            status=ServiceStatus.ERROR,
            details=f"Unexpected error: {str(e)}"
        ))
        return False
    
def get_system_status(activities: Dict[str, bool], grace_period_end_time: Optional[float] = None) -> SystemStatus:
    """Returns the current system status.

    Args:
        activities: A dictionary containing the activity status of each service.
        grace_period_end_time: The time when the grace period ends.

    Returns:
        A SystemStatus object containing the current system status.
    """
    active_services = [service for service, is_active in activities.items() if is_active]
    try:
        with open('/proc/uptime', 'r') as f:
            uptime = float(f.read().split()[0])
    except (IOError, ValueError) as e:
        logging.getLogger('autosuspend').error(f"Failed to read uptime: {e}")
        uptime = 0.0

    return SystemStatus(
        activity_summary=activities,
        last_check_time=datetime.now(),
        uptime=uptime,
        grace_period_active=grace_period_end_time is not None,
        grace_period_remaining=grace_period_end_time - time.time() if grace_period_end_time else None,
        active_services=active_services
    )


def log_status_summary(activities: Dict[str, bool], logger: logging.Logger) -> None:
    """Logs a summary of the activity status of all monitored services.

    Args:
        activities (Dict[str, bool]): A dictionary where keys are service names and values are activity status.
        logger (logging.Logger): The logger object.
    """
    active_services = [service for service, is_active in activities.items() if is_active]
    idle_services = [service for service, is_active in activities.items() if not is_active]
    
    if active_services:
        logger.info("Active Services:")
        for service in active_services:
            logger.info(f"  - {service}")
    
    if idle_services:
        logger.info("Idle Services:")
        for service in idle_services:
            logger.info(f"  - {service}")


def wait_for_services(config: Config, logger: logging.Logger, timeout: int = 300) -> bool:
    """Wait for all enabled services to become available.

    Args:
        config: The configuration object.
        logger: The logger object.
        timeout: The maximum time to wait for services to become available.

    Returns:
        True if all services become available within the timeout, False otherwise.
    """
    logger.info(f"Waiting for enabled services to become available (timeout: {timeout} seconds)...")
    start_time = time.time()
    unavailable_services = set()

    while time.time() - start_time < timeout:
        health_status = config.check_service_health()
        currently_unavailable = {s for s, h in health_status.items() if not h}

        # If no unavailable services, we're done
        if not currently_unavailable:
            logger.info("All enabled services are available.")
            return True

        # Log only newly unavailable services
        new_unavailable = currently_unavailable - unavailable_services
        if new_unavailable:
            logger.warning(f"Services not available: {', '.join(new_unavailable)}")

        # Update our tracking set
        unavailable_services = currently_unavailable

        # Wait before next check
        time.sleep(10)

    logger.error(f"Timeout reached. Services still unavailable: {', '.join(unavailable_services)}")
    return False


def suspend_system(config: Config, logger: logging.Logger) -> bool:
    """Suspends the system and sets a wake-up timer.

    Args:
        config (Config): The configuration object.
        logger (logging.Logger): The logger object.

    Returns:
        bool: True if the system was suspended successfully, False otherwise.
    """
    try:
        # Final safety checks
        if not os.path.exists(SYSTEM_COMMANDS['set_wakeup']):
            logger.error(f"Required script not found: {SYSTEM_COMMANDS['set_wakeup']}")
            return False

        # Double-check Pi activity one last time
        if check_raspberry_pi_activity(config, logger):
            logger.info("Last-minute activity detected from Pi, aborting suspend")
            return False

        # Verify system state before suspend
        if os.path.exists('/sys/power/state'):
            with open('/sys/power/state', 'r') as f:
                if 'mem' not in f.read():
                    logger.error("System does not support suspend to RAM")
                    return False

        # Set wake timer with retries
        wake_timer_set = False
        for attempt in range(1, config.max_retries + 1):
            try:
                result = subprocess.run(
                    ['sudo', SYSTEM_COMMANDS['set_wakeup']],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=True
                )
                wake_timer_set = True
                logger.info("Successfully set wake-up timer")
                break
            except subprocess.TimeoutExpired:
                logger.error(f"Wake timer setup timed out (Attempt {attempt}/{config.max_retries})")
            except subprocess.CalledProcessError as e:
                logger.error(f"Wake timer setup failed (Attempt {attempt}/{config.max_retries}): {e.stderr}")
            
            if attempt < config.max_retries:
                logger.info(f"Retrying wake timer setup in {config.retry_delay} seconds...")
                time.sleep(config.retry_delay)

        if not wake_timer_set:
            logger.error("Failed to set wake-up timer after all attempts")
            return False

        # Sync filesystems
        try:
            logger.info("Syncing filesystems...")
            subprocess.run([SYSTEM_COMMANDS['sync']], timeout=30, check=True)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
            logger.error(f"Failed to sync filesystems: {e}")
            return False

        # Final check for last-minute activity
        activities = {
            "System Users": check_system_activity(config, logger),
            "Raspberry Pi": check_raspberry_pi_activity(config, logger)
        }
        if any(activities.values()):
            logger.info("Activity detected during final check, aborting suspend")
            return False

        # Attempt to suspend
        try:
            logger.info("Initiating system suspend...")
            result = subprocess.run(
                ['sudo', SYSTEM_COMMANDS['systemctl'], 'suspend'],
                capture_output=True,
                text=True,
                timeout=30,
                check=True
            )
            logger.info("System suspend command executed successfully")
            return True
        except subprocess.TimeoutExpired:
            logger.error("System suspend command timed out")
            return False
        except subprocess.CalledProcessError as e:
            logger.error(f"System suspend failed: {e.stderr}")
            return False

    except Exception as e:
        logger.error(f"Unexpected error during system suspend: {e}")
        logger.exception("Suspend error details:")
        return False
    
def check_single_instance() -> Optional[int]:
    """Ensures that only one instance of the script is running.

    Returns:
        Optional[int]: File descriptor of lock file if successful, None if already running.
    """
    lock_file = Path("/var/run/autosuspend.lock")
    try:
        # Open with exclusive creation flag
        fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_RDWR)
        # Write PID to lock file
        os.write(fd, str(os.getpid()).encode())
        return fd
    except OSError:
        try:
            # Check if the process in the lock file is still running
            with open(lock_file, 'r') as f:
                pid = int(f.read().strip())
                if os.path.exists(f"/proc/{pid}"):
                    print(f"Another instance is already running (PID: {pid}). Exiting.")
                    sys.exit(0)
                else:
                    # Process is dead, remove stale lock file and retry
                    os.remove(lock_file)
                    return check_single_instance()
        except (ValueError, IOError, OSError):
            # If any error occurs while checking, assume it's safe to remove and retry
            try:
                os.remove(lock_file)
                return check_single_instance()
            except OSError:
                print("Failed to acquire lock. Exiting.")
                sys.exit(1)

def setup_signal_handlers(config: Config, logger: logging.Logger, lock_fd: Optional[int]) -> None:
    """Sets up signal handlers for graceful shutdown.
    
    Args:
        config (Config): The configuration object.
        logger (logging.Logger): The logger object.
        lock_fd (Optional[int]): File descriptor of the lock file.
    """
    def cleanup_and_exit():
        """Cleanup function to be called on shutdown."""
        logger.info("Cleaning up before exit...")
        if lock_fd is not None:
            try:
                os.close(lock_fd)
                os.remove("/var/run/autosuspend.lock")
                logger.info("Removed lock file")
            except OSError as e:
                logger.error(f"Failed to cleanup lock file: {e}")

    def handle_shutdown(signum, frame):
        """Signal handler for shutdown signals."""
        sig_name = signal.Signals(signum).name
        logger.info(f"Received {sig_name} signal. Initiating graceful shutdown...")
        cleanup_and_exit()
        sys.exit(0)

    def handle_reload(signum, frame):
        """Signal handler for reload signal (SIGHUP)."""
        logger.info("Received SIGHUP signal. Reloading configuration...")
        try:
            config.reload_config()
            logger.info("Configuration reloaded successfully")
        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}")

    # Register the signal handlers
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGHUP, handle_reload)

    # Ensure cleanup runs on normal exit
    atexit.register(cleanup_and_exit)

def setup_logging(config: Config) -> logging.Logger:
    """Sets up logging configuration.
    
    Args:
        config (Config): The configuration object containing logging settings.
        
    Returns:
        logging.Logger: Configured logger instance.
    """
    logger = logging.getLogger('autosuspend')
    
    # Set the logging level from config
    log_level = getattr(logging, config.config['logging'].get('level', 'INFO').upper())
    logger.setLevel(log_level)
    
    # Create formatters and handlers
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt=DATE_FORMAT
    )
    
    # Create and configure the rotating file handler
    file_handler = LineBasedRotatingHandler(
        filename=config.config['logging']['file'],
        max_lines=config.config['logging']['max_lines']
    )
    file_handler.setFormatter(formatter)
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

def main() -> None:
    """Main function to monitor system activity and manage suspension."""
    # Initialize lock file
    lock_fd = check_single_instance()
    
    # Initialize configuration and logging
    config = Config()
    logger = setup_logging(config)
    
    # Setup signal handlers
    setup_signal_handlers(config, logger, lock_fd)

    logger.info("Starting system monitoring...")

    # Wait for services to become available at startup
    if not wait_for_services(config, logger, timeout=STARTUP_DELAY):
        logger.warning("Not all services became available within the startup delay. Continuing with monitoring...")

    current_status = None
    grace_period_end_time = None
    last_health_check = 0
    health_check_interval = 300  # 5 minutes

    while True:
        try:
            current_time = time.time()

            # Periodic health check
            if current_time - last_health_check >= health_check_interval:
                logger.debug("Performing periodic health check...")
                health_status = config.check_service_health()
                if not all(health_status.values()):
                    unhealthy = [s for s, h in health_status.items() if not h]
                    logger.warning(f"Services potentially unhealthy: {', '.join(unhealthy)}")
                last_health_check = current_time

            # Check all services
            activities = {
                "System Users": check_system_activity(config, logger),
                "Jellyfin": check_jellyfin(config, logger),
                "Sonarr": check_sonarr(config, logger),
                "Radarr": check_radarr(config, logger),
                "Nextcloud": check_nextcloud(config, logger),
                "Raspberry Pi": check_raspberry_pi_activity(config, logger),
                "Plex": check_plex(config, logger),
                "Emby": check_emby(config, logger)
            }

            log_status_summary(activities, logger)
            
            # Update system status
            current_status = get_system_status(activities, grace_period_end_time)

            # If system is idle
            if not any(activities.values()):
                if grace_period_end_time is None:
                    # Start grace period
                    grace_period_end_time = time.time() + config.grace_period
                    logger.info(f"All services idle. Starting {config.grace_period}s grace period.")
                elif time.time() >= grace_period_end_time:
                    logger.info("Grace period expired. Performing final activity check...")
                    
                    # Final activity check with reduced scope
                    final_check_activities = {
                        "System Users": check_system_activity(config, logger),
                        "Raspberry Pi": check_raspberry_pi_activity(config, logger)
                    }

                    if not any(final_check_activities.values()):
                        logger.info("System still idle after grace period. Initiating suspend...")
                        if suspend_system(config, logger):
                            logger.info("System suspended successfully.")
                            # Reset grace period and clear all API caches
                            grace_period_end_time = None
                            for func in [check_jellyfin, check_sonarr, check_radarr, 
                                       check_nextcloud, check_raspberry_pi_activity,
                                       check_plex, check_emby]:
                                if hasattr(func, 'clear_cache'):
                                    func.clear_cache()
                            # Wait a bit longer after suspend
                            time.sleep(60)
                            continue
                        else:
                            logger.error("Failed to suspend system.")
                            grace_period_end_time = None  # Reset grace period on failure
                    else:
                        logger.info("Activity detected during final check. Aborting suspend.")
                        grace_period_end_time = None
                else:
                    # Still in grace period, check Raspberry Pi more frequently
                    remaining = int(grace_period_end_time - time.time())
                    logger.info(f"Grace period active: {remaining}s remaining")
                    
                    # Quick check for Pi activity
                    if check_raspberry_pi_activity(config, logger):
                        logger.info("Activity detected from Pi during grace period. Aborting suspend.")
                        grace_period_end_time = None
                    else:
                        time.sleep(min(config.grace_period_check_interval, remaining))
                        continue
            else:
                # System is active, reset grace period
                if grace_period_end_time is not None:
                    logger.info("Activity detected. Resetting grace period.")
                    grace_period_end_time = None

            # Regular check interval
            time.sleep(config.check_interval)

        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt. Shutting down...")
            break
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {str(e)}")
            logger.exception("Error details:")
            time.sleep(config.check_interval)

if __name__ == "__main__":
    main()
