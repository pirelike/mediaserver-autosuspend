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
from typing import Dict, Any, List

# Constants
DEFAULT_TIMEOUT = 5
MAX_RETRIES = 3
RETRY_DELAY = 5
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

class Config:
    """Configuration handler"""

    def __init__(self, config_path: str = '/home/mediaserver/scripts/autosuspend_config.yaml') -> None:
        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            sys.exit(1)

    @property
    def jellyfin_enabled(self) -> bool:
        return self.config['jellyfin'].get('enabled', False)

    @property
    def jellyfin_url(self) -> str:
        return self.config['jellyfin']['url']

    @property
    def jellyfin_api_key(self) -> str:
        return self.config['jellyfin']['api_key']

    @property
    def jellyfin_timeout(self) -> int:
        return self.config['jellyfin'].get('timeout', DEFAULT_TIMEOUT)

    @property
    def radarr_enabled(self) -> bool:
        return self.config['radarr'].get('enabled', False)

    @property
    def radarr_url(self) -> str:
        return self.config['radarr']['url']

    @property
    def radarr_api_key(self) -> str:
        return self.config['radarr']['api_key']

    @property
    def radarr_timeout(self) -> int:
        return self.config['radarr'].get('timeout', DEFAULT_TIMEOUT)

    @property
    def sonarr_enabled(self) -> bool:
        return self.config['sonarr'].get('enabled', False)

    @property
    def sonarr_url(self) -> str:
        return self.config['sonarr']['url']

    @property
    def sonarr_api_key(self) -> str:
        return self.config['sonarr']['api_key']

    @property
    def sonarr_timeout(self) -> int:
        return self.config['sonarr'].get('timeout', DEFAULT_TIMEOUT)

    @property
    def nextcloud_enabled(self) -> bool:
        return self.config['nextcloud'].get('enabled', False)

    @property
    def nextcloud_url(self) -> str:
        return self.config['nextcloud']['url']

    @property
    def nextcloud_token(self) -> str:
        return self.config['nextcloud']['token']

    @property
    def nextcloud_timeout(self) -> int:
        return self.config['nextcloud'].get('timeout', DEFAULT_TIMEOUT)

    @property
    def raspberry_pi_enabled(self) -> bool:
        return self.config['raspberry_pi'].get('enabled', False)

    @property
    def raspberry_pi_url(self) -> str:
        return self.config['raspberry_pi']['url']

    @property
    def raspberry_pi_timeout(self) -> int:
        return self.config['raspberry_pi'].get('timeout', DEFAULT_TIMEOUT)

    @property
    def system_users_enabled(self) -> bool:
        return self.config.get('system_users', {}).get('enabled', False)

    @property
    def check_interval(self) -> int:
        return self.config['monitoring']['check_interval']

    @property
    def grace_period(self) -> int:
        return self.config['monitoring']['grace_period']

    @property
    def log_file(self) -> str:
        return self.config['logging']['file']

    @property
    def max_log_lines(self) -> int:
        return self.config['logging']['max_lines']

class LineBasedRotatingHandler(logging.Handler):
    """Custom handler that maintains a fixed number of lines in the log file."""

    def __init__(self, filename: str, max_lines: int = 500) -> None:
        super().__init__()
        self.filename = filename
        self.max_lines = max_lines
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record) + '\n'

            with self._lock:
                lines = []
                if os.path.exists(self.filename):
                    with open(self.filename, 'r') as f:
                        lines = f.readlines()

                lines.append(msg)
                if len(lines) > self.max_lines:
                    lines = lines[-self.max_lines:]

                with open(self.filename, 'w') as f:
                    f.writelines(lines)

        except Exception:
            self.handleError(record)

def setup_logging(config: Config) -> logging.Logger:
    """Setup logging with line-based rotation."""
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
    """Check if another instance of the script is running."""
    script_name = Path(__file__).name
    result = subprocess.run(['pgrep', '-f', script_name], capture_output=True, text=True)
    pids = result.stdout.strip().split('\n')
    if len([pid for pid in pids if pid and int(pid) != os.getpid()]) > 0:
        print(f"Another instance of {script_name} is already running. Exiting.")
        sys.exit(0)

def check_jellyfin(config: Config, logger: logging.Logger) -> bool:
    """Check Jellyfin for active playback sessions."""
    if not config.jellyfin_enabled:
        logger.info("Jellyfin: Service disabled. Skipping check.")
        return False

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            headers = {
                'X-Emby-Authorization': f'MediaBrowser ClientId="JellyfinWeb", DeviceId="", Device="", Version="", Token="{config.jellyfin_api_key}"'
            }
            response = requests.get(f"{config.jellyfin_url}/Sessions", headers=headers, timeout=config.jellyfin_timeout)
            response.raise_for_status()
            sessions = response.json()

            if not isinstance(sessions, list):
                logger.error("Jellyfin: Unexpected response format (not a list)")
                return False

            for session in sessions:
                if session.get('NowPlayingItem') is not None:
                    logger.info("Jellyfin: Active playback session detected")
                    return True

            logger.info("Jellyfin: No active playback sessions")
            return False

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Jellyfin: Connection error (Attempt {attempt}/{MAX_RETRIES}) - {e}")
            if attempt < MAX_RETRIES:
                logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                logger.error("Jellyfin: Max retries exceeded. Giving up.")
                return False
        except requests.exceptions.Timeout as e:
            logger.error(f"Jellyfin: Request timed out - {e}")
            return False
        except requests.exceptions.HTTPError as e:
            logger.error(f"Jellyfin: HTTP error ({response.status_code}) - {e}")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Jellyfin: Error connecting to API - {e}")
            return False
        except ValueError as e:
            logger.error(f"Jellyfin: Invalid JSON response - {e}")
            return False

def check_sonarr(config: Config, logger: logging.Logger) -> bool:
    """Check Sonarr for active queue items."""
    if not config.sonarr_enabled:
        logger.info("Sonarr: Service disabled. Skipping check.")
        return False

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            headers = {'X-Api-Key': config.sonarr_api_key}
            response = requests.get(f'{config.sonarr_url}/api/v3/queue', headers=headers, timeout=config.sonarr_timeout)
            response.raise_for_status()

            data = response.json()
            if not isinstance(data, dict):
                logger.error("Sonarr: Unexpected response format (not a dictionary)")
                return False

            total_records = data.get('totalRecords', 0)

            if total_records > 0:
                logger.info(f"Sonarr: Active queue items found: {total_records}")
                return True

            logger.info("Sonarr: No active queue items")
            return False

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Sonarr: Connection error (Attempt {attempt}/{MAX_RETRIES}) - {e}")
            if attempt < MAX_RETRIES:
                logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                logger.error("Sonarr: Max retries exceeded. Giving up.")
                return False
        except requests.exceptions.Timeout as e:
            logger.error(f"Sonarr: Request timed out - {e}")
            return False
        except requests.exceptions.HTTPError as e:
            logger.error(f"Sonarr: HTTP error ({response.status_code}) - {e}")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Sonarr: Error connecting to API - {str(e)}")
            return False
        except ValueError as e:
            logger.error(f"Sonarr: Invalid JSON response - {e}")
            return False

def check_radarr(config: Config, logger: logging.Logger) -> bool:
    """Check Radarr for active queue items."""
    if not config.radarr_enabled:
        logger.info("Radarr: Service disabled. Skipping check.")
        return False

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            headers = {'X-Api-Key': config.radarr_api_key}
            response = requests.get(f'{config.radarr_url}/api/v3/queue', headers=headers, timeout=config.radarr_timeout)
            response.raise_for_status()

            data = response.json()
            if not isinstance(data, dict):
                logger.error("Radarr: Unexpected response format (not a dictionary)")
                return False

            total_records = data.get('totalRecords', 0)

            if total_records > 0:
                logger.info(f"Radarr: Active queue items found: {total_records}")
                return True

            logger.info("Radarr: No active queue items")
            return False

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Radarr: Connection error (Attempt {attempt}/{MAX_RETRIES}) - {e}")
            if attempt < MAX_RETRIES:
                logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                logger.error("Radarr: Max retries exceeded. Giving up.")
                return False
        except requests.exceptions.Timeout as e:
            logger.error(f"Radarr: Request timed out - {e}")
            return False
        except requests.exceptions.HTTPError as e:
            logger.error(f"Radarr: HTTP error ({response.status_code}) - {e}")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Radarr: Error connecting to API - {str(e)}")
            return False
        except ValueError as e:
            logger.error(f"Radarr: Invalid JSON response - {e}")
            return False

def check_nextcloud(config: Config, logger: logging.Logger) -> bool:
    """Check Nextcloud for CPU load."""
    if not config.nextcloud_enabled:
        logger.info("Nextcloud: Service disabled. Skipping check.")
        return False

    for attempt in range(1, MAX_RETRIES + 1):
        try:
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
                logger.error("Nextcloud: Unexpected response format")
                return False

            cpu_load = float(data['ocs']['data']['system']['cpuload'][1])

            if cpu_load > 0.5:
                logger.info(f"Nextcloud: High CPU load detected (Load average: {cpu_load})")
                return True

            logger.info(f"Nextcloud: No high CPU load detected (Load average: {cpu_load})")
            return False

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Nextcloud: Connection error (Attempt {attempt}/{MAX_RETRIES}) - {e}")
            if attempt < MAX_RETRIES:
                logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                logger.error("Nextcloud: Max retries exceeded. Giving up.")
                return False
        except requests.exceptions.Timeout as e:
            logger.error(f"Nextcloud: Request timed out - {e}")
            return False
        except requests.exceptions.HTTPError as e:
            logger.error(f"Nextcloud: HTTP error ({response.status_code}) - {e}")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Nextcloud: Error connecting to API - {str(e)}")
            return False
        except (ValueError, TypeError) as e:
            logger.error(f"Nextcloud: Invalid response or data type - {e}")
            return False

def check_system_activity(config: Config, logger: logging.Logger) -> bool:
    """Check for logged-in users."""
    if not config.system_users_enabled:
        logger.info("System Users: Service disabled. Skipping check.")
        return False

    try:
        who_output = subprocess.check_output(['who']).decode().strip()
        logged_in_count = len(who_output.split('\n')) if who_output else 0

        if logged_in_count > 0:
            logger.info(f"System: Active users found: {logged_in_count}")
            return True
        logger.info("System: No active users")
        return False
    except Exception as e:
        logger.error(f"System: Error checking logged-in users - {str(e)}")
        return False

def check_raspberry_pi_activity(config: Config, logger: logging.Logger) -> bool:
    """Check if there's recent activity on the Raspberry Pi."""
    if not config.raspberry_pi_enabled:
        logger.info("Raspberry Pi: Service disabled. Skipping check.")
        return False

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(f'{config.raspberry_pi_url}/check-activity', timeout=config.raspberry_pi_timeout)
            response.raise_for_status()

            activity_data = response.json()
            if not isinstance(activity_data, dict):
                logger.error("Raspberry Pi: Unexpected response format (not a dictionary)")
                return False

            if activity_data.get('active', False):
                logger.info("Recent activity detected on Raspberry Pi")
                return True

            logger.info("No recent activity on Raspberry Pi")
            return False

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Raspberry Pi: Connection error (Attempt {attempt}/{MAX_RETRIES}) - {e}")
            if attempt < MAX_RETRIES:
                logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                logger.error("Raspberry Pi: Max retries exceeded. Giving up.")
                return False
        except requests.exceptions.Timeout as e:
            logger.error(f"Raspberry Pi: Request timed out - {e}")
            return False
        except requests.exceptions.HTTPError as e:
            logger.error(f"Raspberry Pi: HTTP error ({response.status_code}) - {e}")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Error checking Raspberry Pi activity: {str(e)}")
            return False
        except ValueError as e:
            logger.error(f"Raspberry Pi: Invalid JSON response - {e}")
            return False

def log_status_summary(activities: Dict[str, bool], logger: logging.Logger) -> None:
    """Log a summary of all system activities."""
    logger.info("System active - Status Summary:")
    for service, is_active in activities.items():
        status = "Active" if is_active else "Idle"
        logger.info(f"- {service}: {status}")

def suspend_system(config: Config, logger: logging.Logger) -> bool:
    """Set wake timer and suspend the system."""
    try:
        # Final quick check with Pi before suspending
        if check_raspberry_pi_activity(config, logger):
            logger.info("Last-minute activity detected from Pi, aborting suspend")
            return False

        # Check if set-wakeup.sh exists
        if not os.path.exists('/usr/local/bin/set-wakeup.sh'):
            logger.error("Error: /usr/local/bin/set-wakeup.sh not found.")
            return False

        # Set wake timer
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                result = subprocess.run(['sudo', '/usr/local/bin/set-wakeup.sh'], check=True, capture_output=True, text=True)
                if result.returncode == 0:
                    logger.info("Successfully set wake-up timer")
                    break
                else:
                    logger.error(f"Error setting wake-up timer (Attempt {attempt}/{MAX_RETRIES}). Return code: {result.returncode}")
                    if result.stderr:
                        logger.error(f"Error output: {result.stderr}")
                    if attempt < MAX_RETRIES:
                        logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                        time.sleep(RETRY_DELAY)
                    else:
                        logger.error("Max retries exceeded for setting wake-up timer. Giving up.")
                        return False
            except subprocess.CalledProcessError as e:
                logger.error(f"Error setting wake-up timer (Attempt {attempt}/{MAX_RETRIES}) - {e}")
                if attempt < MAX_RETRIES:
                    logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                    time.sleep(RETRY_DELAY)
                else:
                    logger.error("Max retries exceeded for setting wake-up timer. Giving up.")
                    return False

        # Sync filesystem
        subprocess.run(['sync'], check=True)

        # Suspend system
        result = subprocess.run(['sudo', 'systemctl', 'suspend'], check=True)
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

def main() -> None:
    """Main function to monitor system activity and manage suspension."""
    check_single_instance()

    config = Config()
    logger = setup_logging(config)

    logger.info("Starting system monitoring...")

    while True:
        # Check all services
        activities = {
            "System Users": check_system_activity(config, logger),
            "Jellyfin": check_jellyfin(config, logger),
            "Sonarr": check_sonarr(config, logger),
            "Radarr": check_radarr(config, logger),
            "Nextcloud": check_nextcloud(config, logger),
            "Raspberry Pi": check_raspberry_pi_activity(config, logger)
        }

        # Log status summary
        log_status_summary(activities, logger)

        # If system is completely idle
        if not any(activities.values()):
            logger.info("All systems idle. Starting 10-minute grace period...")
            time.sleep(300)  # First 5 minutes

            # Check Pi status more frequently in the middle of grace period
            for _ in range(5):  # Check every minute for 5 minutes
                if check_raspberry_pi_activity(config, logger):
                    logger.info("Activity detected from Pi during grace period")
                    break
                time.sleep(60)

            # Recheck all services
            activities = {
                "System Users": check_system_activity(config, logger),
                "Jellyfin": check_jellyfin(config, logger),
                "Sonarr": check_sonarr(config, logger),
                "Radarr": check_radarr(config, logger),
                "Nextcloud": check_nextcloud(config, logger),
                "Raspberry Pi": check_raspberry_pi_activity(config, logger)
            }

            # If still idle after grace period
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
