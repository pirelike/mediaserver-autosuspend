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
from typing import Dict, Any, List, Optional
import xml.etree.ElementTree as ET
import functools
from enum import Enum
from dataclasses import dataclass, field
import signal

# Constants
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
DEFAULT_TIMEOUT = 5
MAX_RETRIES = 3
RETRY_DELAY = 5

# System command paths for security
SYSTEM_COMMANDS = {
    'who': '/usr/bin/who',
    'sync': '/bin/sync',
    'systemctl': '/bin/systemctl',
    'set_wakeup': '/usr/local/bin/set-wakeup.sh'
}

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
        self.history: List[ActivityCheckResult] = []
        self.max_entries = max_entries

    def add_entry(self, result: ActivityCheckResult) -> None:
        """Adds an entry to the activity history.

        Args:
            result (ActivityCheckResult): The result of the activity check.
        """
        self.history.append(result)
        if len(self.history) > self.max_entries:
            self.history.pop(0)

class Config:
    """Configuration handler for autosuspend."""

    def __init__(self, config_path: str = '/home/mediaserver/scripts/autosuspend_config.yaml') -> None:
        """Initializes the Config object.

        Args:
            config_path (str): Path to the configuration file.
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.activity_history = ActivityHistory()
        self._validate_config()

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

    def _validate_config(self) -> None:
        """Validates the configuration for required sections and fields."""
        required_sections = {
            'monitoring': ['check_interval', 'grace_period', 'max_retries', 'retry_delay'],
            'logging': ['file', 'max_lines']
        }

        for section, fields in required_sections.items():
            if section not in self.config:
                raise ValueError(f"Missing required section: {section}")
            for field in fields:
                if field not in self.config[section]:
                    raise ValueError(f"Missing required field '{field}' in section '{section}'")

        # Validate enabled services
        services = ['jellyfin', 'sonarr', 'radarr', 'plex', 'emby', 'nextcloud', 'raspberry_pi', 'system_users']
        for service in services:
            if self.config.get(service, {}).get('enabled', False):
                if service == 'nextcloud':
                    required_fields = ['url', 'token', 'timeout']
                elif service == 'system_users':
                    continue
                elif service == 'raspberry_pi':
                    required_fields = ['url', 'timeout']
                else:
                    required_fields = ['url', 'api_key', 'timeout']
                for field in required_fields:
                    if not self.config.get(service, {}).get(field):
                        raise ValueError(f"Missing required field '{field}' for enabled service '{service}'")

    def reload_config(self) -> None:
        """Reload configuration file without restart."""
        try:
            new_config = self._load_config()
            self._validate_config()
            self.config = new_config
            logging.getLogger('autosuspend').info("Configuration reloaded successfully.")
        except Exception as e:
            logging.getLogger('autosuspend').error(f"Failed to reload configuration: {e}")

    def check_service_health(self) -> Dict[str, bool]:
        """Checks the basic HTTP/HTTPS connectivity to each enabled service.

        Returns:
            Dict[str, bool]: A dictionary where keys are service names and values are
                             True if the service is reachable, False otherwise.
        """
        health_status = {}
        services = ['jellyfin', 'sonarr', 'radarr', 'plex', 'emby', 'nextcloud', 'raspberry_pi']
        for service in services:
            if getattr(self, f'{service}_enabled'):
                try:
                    url = getattr(self, f'{service}_url')
                    if url:
                        response = requests.head(url, timeout=5, verify=False)
                        response.raise_for_status()  # Raise an exception for bad status codes
                        health_status[service] = True
                    else:
                        logger.warning(f"URL not defined for {service}, skipping health check.")
                        health_status[service] = False
                except requests.exceptions.RequestException as e:
                    logger.error(f"Health check failed for {service}: {e}")
                    health_status[service] = False
        return health_status

    @property
    def jellyfin_enabled(self) -> bool:
        return self.config.get('jellyfin', {}).get('enabled', False)

    @property
    def jellyfin_url(self) -> str:
        return self.config.get('jellyfin', {}).get('url')

    @property
    def jellyfin_api_key(self) -> str:
        return self.config.get('jellyfin', {}).get('api_key')

    @property
    def jellyfin_timeout(self) -> int:
        return self.config.get('jellyfin', {}).get('timeout', DEFAULT_TIMEOUT)

    @property
    def radarr_enabled(self) -> bool:
        return self.config.get('radarr', {}).get('enabled', False)

    @property
    def radarr_url(self) -> str:
        return self.config.get('radarr', {}).get('url')

    @property
    def radarr_api_key(self) -> str:
        return self.config.get('radarr', {}).get('api_key')

    @property
    def radarr_timeout(self) -> int:
        return self.config.get('radarr', {}).get('timeout', DEFAULT_TIMEOUT)

    @property
    def sonarr_enabled(self) -> bool:
        return self.config.get('sonarr', {}).get('enabled', False)

    @property
    def sonarr_url(self) -> str:
        return self.config.get('sonarr', {}).get('url')

    @property
    def sonarr_api_key(self) -> str:
        return self.config.get('sonarr', {}).get('api_key')

    @property
    def sonarr_timeout(self) -> int:
        return self.config.get('sonarr', {}).get('timeout', DEFAULT_TIMEOUT)

    @property
    def nextcloud_enabled(self) -> bool:
        return self.config.get('nextcloud', {}).get('enabled', False)

    @property
    def nextcloud_url(self) -> str:
        return self.config.get('nextcloud', {}).get('url')

    @property
    def nextcloud_token(self) -> str:
        return self.config.get('nextcloud', {}).get('token')

    @property
    def nextcloud_timeout(self) -> int:
        return self.config.get('nextcloud', {}).get('timeout', DEFAULT_TIMEOUT)

    @property
    def raspberry_pi_enabled(self) -> bool:
        return self.config.get('raspberry_pi', {}).get('enabled', False)

    @property
    def raspberry_pi_url(self) -> str:
        return self.config.get('raspberry_pi', {}).get('url')

    @property
    def raspberry_pi_timeout(self) -> int:
        return self.config.get('raspberry_pi', {}).get('timeout', DEFAULT_TIMEOUT)

    @property
    def system_users_enabled(self) -> bool:
        return self.config.get('system_users', {}).get('enabled', False)

    @property
    def plex_enabled(self) -> bool:
        return self.config.get('plex', {}).get('enabled', False)

    @property
    def plex_url(self) -> str:
        return self.config.get('plex', {}).get('url')

    @property
    def plex_token(self) -> str:
        return self.config.get('plex', {}).get('token')

    @property
    def plex_timeout(self) -> int:
        return self.config.get('plex', {}).get('timeout', DEFAULT_TIMEOUT)

    @property
    def emby_enabled(self) -> bool:
        return self.config.get('emby', {}).get('enabled', False)

    @property
    def emby_url(self) -> str:
        return self.config.get('emby', {}).get('url')

    @property
    def emby_api_key(self) -> str:
        return self.config.get('emby', {}).get('api_key')

    @property
    def emby_timeout(self) -> int:
        return self.config.get('emby', {}).get('timeout', DEFAULT_TIMEOUT)

    @property
    def check_interval(self) -> int:
        return self.config['monitoring']['check_interval']

    @property
    def grace_period(self) -> int:
        return self.config['monitoring']['grace_period']
    
    @property
    def grace_period_check_interval(self) -> int:
        """Returns the grace period (in seconds) before the system is suspended."""
        return self.config['monitoring'].get('grace_period_check_interval', 60)

    @property
    def max_retries(self) -> int:
        return self.config['monitoring'].get('max_retries', MAX_RETRIES)

    @property
    def retry_delay(self) -> int:
        return self.config['monitoring'].get('retry_delay', RETRY_DELAY)

    @property
    def log_file(self) -> str:
        return self.config['logging']['file']

    @property
    def max_log_lines(self) -> int:
        return self.config['logging']['max_lines']

class LineBasedRotatingHandler(logging.Handler):
    """Custom logging handler that maintains a fixed number of lines in the log file."""

    def __init__(self, filename: str, max_lines: int = 500) -> None:
        """Initializes the LineBasedRotatingHandler.

        Args:
            filename (str): The path to the log file.
            max_lines (int): The maximum number of lines to keep in the log file.
        """
        super().__init__()
        self.filename = filename
        self.max_lines = max_lines
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        """Emits a log record to the log file, ensuring that the log file does not exceed the maximum number of lines.

        Args:
            record (logging.LogRecord): The log record to emit.
        """
        try:
            msg = self.format(record) + '\n'

            with self._lock:
                # Efficiently rotate logs, keeping only the last 'max_lines'
                temp_filename = self.filename + ".tmp"

                with open(self.filename, 'r') as f_in, open(temp_filename, 'w') as f_out:
                    lines = f_in.readlines()
                    lines_to_keep = lines[-max(0, self.max_lines - 1):]  # Keep last 'max_lines - 1' lines
                    f_out.writelines(lines_to_keep)
                    f_out.write(msg)  # Write the new log message

                os.replace(temp_filename, self.filename)  # Atomic operation

        except Exception:
            self.handleError(record)

def setup_logging(config: Config) -> logging.Logger:
    """Sets up the logger with a line-based rotating file handler.

    Args:
        config (Config): The configuration object.

    Returns:
        logging.Logger: The configured logger.
    """
    log_path = Path(config.log_file)

    # Create directory if it doesn't exist
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Create file if it doesn't exist
    if not log_path.exists():
        log_path.touch()
        os.chmod(log_path, 0o666)

    handler = LineBasedRotatingHandler(str(log_path), max_lines=config.max_log_lines)
    formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt=DATE_FORMAT)
    handler.setFormatter(formatter)

    logger = logging.getLogger('autosuspend')
    logger.setLevel(logging.INFO)

    # Remove any existing handlers
    for hdlr in logger.handlers[:]:
        logger.removeHandler(hdlr)

    logger.addHandler(handler)

    return logger

def check_single_instance() -> None:
    """Ensures that only one instance of the script is running.

    Exits with an error message if another instance is detected.
    """
    script_name = Path(__file__).name
    result = subprocess.run(['pgrep', '-f', script_name], capture_output=True, text=True)
    pids = result.stdout.strip().split('\n')
    if len([pid for pid in pids if pid and int(pid) != os.getpid()]) > 0:
        print(f"Another instance of {script_name} is already running. Exiting.")
        sys.exit(0)

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
        return False

    headers = {
        'X-Emby-Authorization': f'MediaBrowser ClientId="JellyfinWeb", DeviceId="", Device="", Version="", Token="{config.jellyfin_api_key}"'
    }
    response = requests.get(f"{config.jellyfin_url}/Sessions", headers=headers, timeout=config.jellyfin_timeout)
    response.raise_for_status()
    sessions = response.json()

    if not isinstance(sessions, list):
        logger.error(f"{service_name}: Unexpected response format (not a list)")
        return False

    for session in sessions:
        if session.get('NowPlayingItem') is not None:
            logger.info(f"{service_name}: Active playback session detected")
            config.activity_history.add_entry(ActivityCheckResult(service_name=service_name, status=ServiceStatus.ACTIVE))
            return True

    logger.info(f"{service_name}: No active playback sessions")
    config.activity_history.add_entry(ActivityCheckResult(service_name=service_name, status=ServiceStatus.IDLE))
    return False

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
        return False

    headers = {'X-Api-Key': config.sonarr_api_key}
    response = requests.get(f'{config.sonarr_url}/api/v3/queue', headers=headers, timeout=config.sonarr_timeout)
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, dict):
        logger.error(f"{service_name}: Unexpected response format (not a dictionary)")
        return False

    total_records = data.get('totalRecords', 0)

    if total_records > 0:
        logger.info(f"{service_name}: Active queue items found: {total_records}")
        config.activity_history.add_entry(ActivityCheckResult(service_name=service_name, status=ServiceStatus.ACTIVE))
        return True

    logger.info(f"{service_name}: No active queue items")
    config.activity_history.add_entry(ActivityCheckResult(service_name=service_name, status=ServiceStatus.IDLE))
    return False

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
        return False

    headers = {'X-Api-Key': config.radarr_api_key}
    response = requests.get(f'{config.radarr_url}/api/v3/queue', headers=headers, timeout=config.radarr_timeout)
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, dict):
        logger.error(f"{service_name}: Unexpected response format (not a dictionary)")
        return False

    total_records = data.get('totalRecords', 0)

    if total_records > 0:
        logger.info(f"{service_name}: Active queue items found: {total_records}")
        config.activity_history.add_entry(ActivityCheckResult(service_name=service_name, status=ServiceStatus.ACTIVE))
        return True

    logger.info(f"{service_name}: No active queue items")
    config.activity_history.add_entry(ActivityCheckResult(service_name=service_name, status=ServiceStatus.IDLE))
    return False

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
        return False

    headers = {
        'NC-Token': config.nextcloud_token,
        'OCS-APIRequest': 'true'
    }
    response = requests.get(
        f"{config.nextcloud_url}/ocs/v2.php/apps/serverinfo/api/v1/info?format=json",
        headers=headers,
        timeout=config.nextcloud_timeout
    )
    response.raise_for_status()
    data = response.json()

    # Validate response structure
    if not (isinstance(data, dict) and 'ocs' in data and isinstance(data['ocs'], dict) and
            'data' in data['ocs'] and isinstance(data['ocs']['data'], dict) and
            'system' in data['ocs']['data'] and isinstance(data['ocs']['data']['system'], dict) and
            'cpuload' in data['ocs']['data']['system'] and isinstance(data['ocs']['data']['system']['cpuload'], list)):
        logger.error(f"{service_name}: Unexpected response format")
        return False

    cpu_load = float(data['ocs']['data']['system']['cpuload'][1])

    if cpu_load > 0.5:
        logger.info(f"{service_name}: High CPU load detected (Load average: {cpu_load})")
        config.activity_history.add_entry(ActivityCheckResult(service_name=service_name, status=ServiceStatus.ACTIVE))
        return True

    logger.info(f"{service_name}: No high CPU load detected (Load average: {cpu_load})")
    config.activity_history.add_entry(ActivityCheckResult(service_name=service_name, status=ServiceStatus.IDLE))
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
        return False

    try:
        who_output = subprocess.check_output([SYSTEM_COMMANDS['who']]).decode().strip()
        logged_in_count = len(who_output.split('\n')) if who_output else 0

        if logged_in_count > 0:
            logger.info(f"{service_name}: Active users found: {logged_in_count}")
            config.activity_history.add_entry(ActivityCheckResult(service_name=service_name, status=ServiceStatus.ACTIVE))
            return True
        logger.info(f"{service_name}: No active users")
        config.activity_history.add_entry(ActivityCheckResult(service_name=service_name, status=ServiceStatus.IDLE))
        return False
    except Exception as e:
        logger.error(f"{service_name}: Error checking logged-in users - {str(e)}")
        config.activity_history.add_entry(ActivityCheckResult(service_name=service_name, status=ServiceStatus.ERROR, details=str(e)))
        return False

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
        return False

    response = requests.get(f'{config.raspberry_pi_url}/check-activity', timeout=config.raspberry_pi_timeout)
    response.raise_for_status()

    activity_data = response.json()
    if not isinstance(activity_data, dict):
        logger.error(f"{service_name}: Unexpected response format (not a dictionary)")
        return False

    if activity_data.get('active', False):
        logger.info(f"Recent activity detected on {service_name}")
        config.activity_history.add_entry(ActivityCheckResult(service_name=service_name, status=ServiceStatus.ACTIVE))
        return True

    logger.info(f"No recent activity on {service_name}")
    config.activity_history.add_entry(ActivityCheckResult(service_name=service_name, status=ServiceStatus.IDLE))
    return False

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
        return False

    headers = {'X-Plex-Token': config.plex_token}
    response = requests.get(
        f"{config.plex_url}/status/sessions",
        headers=headers,
        timeout=config.plex_timeout
    )
    response.raise_for_status()

    root = ET.fromstring(response.content)
    if int(root.attrib.get('size', 0)) > 0:
        # Assuming any session means active playback.
        logger.info(f"{service_name}: Active playback session detected")
        config.activity_history.add_entry(ActivityCheckResult(service_name=service_name, status=ServiceStatus.ACTIVE))
        return True

    logger.info(f"{service_name}: No active playback sessions")
    config.activity_history.add_entry(ActivityCheckResult(service_name=service_name, status=ServiceStatus.IDLE))
    return False

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
        return False

    headers = {
        'X-Emby-Token': config.emby_api_key
    }
    response = requests.get(f"{config.emby_url}/emby/Sessions", headers=headers, timeout=config.emby_timeout)
    response.raise_for_status()
    sessions = response.json()

    if not isinstance(sessions, list):
        logger.error(f"{service_name}: Unexpected response format (not a list)")
        return False

    for session in sessions:
        if session.get('NowPlayingItem') is not None:
            logger.info(f"{service_name}: Active playback session detected")
            config.activity_history.add_entry(ActivityCheckResult(service_name=service_name, status=ServiceStatus.ACTIVE))
            return True

    logger.info(f"{service_name}: No active playback sessions")
    config.activity_history.add_entry(ActivityCheckResult(service_name=service_name, status=ServiceStatus.IDLE))
    return False

def log_status_summary(activities: Dict[str, bool], logger: logging.Logger) -> None:
    """Logs a summary of the activity status of all monitored services.

    Args:
        activities (Dict[str, bool]): A dictionary where keys are service names and values are activity status (True/False).
        logger (logging.Logger): The logger object.
    """
    logger.info("System active - Status Summary:")
    for service, is_active in activities.items():
        status = "Active" if is_active else "Idle"
        logger.info(f"- {service}: {status}")

def suspend_system(config: Config, logger: logging.Logger) -> bool:
    """Suspends the system and sets a wake-up timer.

    Args:
        config (Config): The configuration object.
        logger (logging.Logger): The logger object.

    Returns:
        bool: True if the system was suspended successfully, False otherwise.
    """
    try:
        # Final quick check with Pi before suspending
        if check_raspberry_pi_activity(config, logger):
            logger.info("Last-minute activity detected from Pi, aborting suspend")
            return False

        # Check if set-wakeup.sh exists
        if not os.path.exists(SYSTEM_COMMANDS['set_wakeup']):
            logger.error("Error: {} not found.".format(SYSTEM_COMMANDS['set_wakeup']))
            return False

        # Set wake timer
        max_retries = config.max_retries
        retry_delay = config.retry_delay
        for attempt in range(1, max_retries + 1):
            try:
                result = subprocess.run(['sudo', SYSTEM_COMMANDS['set_wakeup']], check=True, capture_output=True, text=True)
                if result.returncode == 0:
                    logger.info("Successfully set wake-up timer")
                    break
                else:
                    logger.error(f"Error setting wake-up timer (Attempt {attempt}/{max_retries}). Return code: {result.returncode}")
                    if result.stderr:
                        logger.error(f"Error output: {result.stderr}")
                    if attempt < max_retries:
                        logger.info(f"Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                    else:
                        logger.error("Max retries exceeded for setting wake-up timer. Giving up.")
                        return False
            except subprocess.CalledProcessError as e:
                logger.error(f"Error setting wake-up timer (Attempt {attempt}/{max_retries}) - {e}")
                if attempt < max_retries:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error("Max retries exceeded for setting wake-up timer. Giving up.")
                    return False

        # Sync filesystem
        subprocess.run([SYSTEM_COMMANDS['sync']], check=True)

        # Suspend system
        result = subprocess.run(['sudo', SYSTEM_COMMANDS['systemctl'], 'suspend'], check=True)
        if result.returncode != 0:
            logger.error("Error: Failed to suspend system")
            return False

        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error during system suspend: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred during system suspend: {e}")
        return False

def setup_signal_handlers(logger: logging.Logger) -> None:
    """Sets up signal handlers for graceful shutdown."""
    def handle_shutdown(signum, frame):
        logger.info("Received shutdown signal. Cleaning up...")
        # Perform cleanup tasks here (if any)
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

def main() -> None:
    """Main function to monitor system activity and manage suspension."""
    check_single_instance()

    config = Config()
    logger = setup_logging(config)
    setup_signal_handlers(logger)

    logger.info("Starting system monitoring...")

    while True:
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

        # Log status summary
        log_status_summary(activities, logger)

        # If system is completely idle
        if not any(activities.values()):
            logger.info(f"All systems idle. Starting {config.grace_period}-second grace period...")

            # Grace period loop
            grace_period_end_time = time.time() + config.grace_period
            while time.time() < grace_period_end_time:
                # Check for activity more frequently during the grace period
                if check_raspberry_pi_activity(config, logger):
                    logger.info("Activity detected from Pi during grace period. Aborting suspend.")
                    break  # Exit the grace period loop
                
                time.sleep(config.grace_period_check_interval)

            else:  # This 'else' corresponds to the 'while' loop
                # If the loop completed without breaking (no activity)
                
                # Recheck all services
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

                if not any(activities.values()):
                    logger.info("System still idle after grace period. Setting wake timer and initiating suspend...")
                    if suspend_system(config, logger):
                        logger.info("System suspended successfully.")
                        time.sleep(60)  # Wait a minute before resuming monitoring
                    else:
                        logger.error("Failed to suspend system.")
                else:
                    logger.info("New activity detected during grace period. Aborting suspend.")

        # Wait before next check
        time.sleep(config.check_interval)

if __name__ == "__main__":
    main()
