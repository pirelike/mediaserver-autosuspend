#!/usr/bin/env python3

import os
import sys
import subprocess
import logging
import yaml
from datetime import datetime
from pathlib import Path
import threading
import time
from typing import Dict, Any, List

# Constants
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

class Config:
    """Configuration handler"""
    def __init__(self, config_path: str = '/home/mediaserver/scripts/maintenance_config.yaml') -> None:
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
    def log_file(self) -> str:
        return self.config['logging']['file']

    @property
    def max_log_lines(self) -> int:
        return self.config['logging']['max_lines']

    @property
    def grace_period(self) -> int:
        return self.config['maintenance']['grace_period']

    @property
    def docker_prune(self) -> bool:
        return self.config['maintenance']['docker_prune']

    @property
    def log_retention(self) -> int:
        return self.config['maintenance']['log_retention_days']

    @property
    def restart_delay(self) -> int:
        return self.config['maintenance']['restart_delay']

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
    
    logger = logging.getLogger('daily_maintenance')
    logger.setLevel(logging.INFO)
    
    # Remove any existing handlers
    for hdlr in logger.handlers[:]:
        logger.removeHandler(hdlr)
    
    logger.addHandler(handler)
    
    return logger

def run_command(command: str, logger: logging.Logger) -> bool:
    """Run a shell command and log output."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            text=True,
            capture_output=True,
            check=True
        )
        logger.info(f"Command succeeded: {command}")
        if result.stdout.strip():
            logger.info(f"Output: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {command}")
        if e.stdout:
            logger.error(f"Output: {e.stdout}")
        if e.stderr:
            logger.error(f"Error: {e.stderr}")
        return False

def check_single_instance() -> None:
    """Check if another instance of the script is running."""
    script_name = Path(__file__).name
    result = subprocess.run(['pgrep', '-f', script_name], capture_output=True, text=True)
    pids = result.stdout.strip().split('\n')
    if len([pid for pid in pids if pid and int(pid) != os.getpid()]) > 0:
        print(f"Another instance of {script_name} is already running. Exiting.")
        sys.exit(0)

def update_packages(logger: logging.Logger) -> bool:
    """Update package lists and install updates."""
    logger.info("Updating package lists...")
    if not run_command("apt-get update", logger):
        return False
        
    logger.info("Installing security updates...")
    if not run_command("unattended-upgrades", logger):
        return False
        
    logger.info("Cleaning package cache...")
    if not run_command("apt-get clean", logger):
        return False
        
    return True

def cleanup_docker(logger: logging.Logger) -> bool:
    """Clean up Docker system."""
    if not os.path.exists('/usr/bin/docker'):
        logger.info("Docker not installed, skipping cleanup")
        return True
        
    logger.info("Cleaning up Docker system...")
    return run_command("docker system prune -f --volumes", logger)

def cleanup_logs(logger: logging.Logger, retention_days: int) -> bool:
    """Clean up system logs."""
    logger.info(f"Clearing logs older than {retention_days} days...")
    return run_command(f"journalctl --vacuum-time={retention_days}d", logger)

def sync_filesystem(logger: logging.Logger) -> bool:
    """Sync filesystem to disk."""
    logger.info("Syncing filesystem...")
    return run_command("sync", logger)

def restart_system(logger: logging.Logger, delay: int = 5) -> None:
    """Restart the system after a delay."""
    logger.info(f"Scheduling system restart in {delay} seconds...")
    time.sleep(delay)
    run_command("shutdown -r now", logger)

def main() -> None:
    """Main function to run maintenance tasks."""
    check_single_instance()

    config = Config()
    logger = setup_logging(config)
    
    logger.info("Starting daily maintenance tasks...")
    
    # Wait for grace period
    logger.info(f"Waiting {config.grace_period} seconds for system to stabilize...")
    time.sleep(config.grace_period)
    
    # Update packages
    if not update_packages(logger):
        logger.error("Package updates failed")
        sys.exit(1)
    
    # Docker cleanup if enabled
    if config.docker_prune:
        if not cleanup_docker(logger):
            logger.error("Docker cleanup failed")
    
    # Cleanup logs
    if not cleanup_logs(logger, config.log_retention):
        logger.error("Log cleanup failed")
    
    # Final sync
    if not sync_filesystem(logger):
        logger.error("Filesystem sync failed")
        sys.exit(1)
    
    logger.info("Daily maintenance completed successfully")
    
    # Restart system
    restart_system(logger, config.restart_delay)

if __name__ == "__main__":
    main()
