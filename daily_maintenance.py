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
from typing import Dict, Any, List, Optional, DefaultDict
import signal
from jsonschema import validate, ValidationError
import dataclasses
from enum import Enum
import contextlib
import asyncio
import aiofiles
import aioshutil
import json
from collections import defaultdict

# Constants
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
CONFIG_SCHEMA = {
    "type": "object",
    "required": ["logging", "maintenance"],
    "properties": {
        "logging": {
            "type": "object",
            "required": ["file", "max_lines"],
            "properties": {
                "file": {"type": "string"},
                "max_lines": {"type": "integer", "minimum": 1}
            }
        },
        "maintenance": {
            "type": "object",
            "required": ["grace_period", "docker_prune", "log_retention_days", "restart_delay"],
            "properties": {
                "grace_period": {"type": "integer", "minimum": 0},
                "docker_prune": {"type": "boolean"},
                "log_retention_days": {"type": "integer", "minimum": 1},
                "restart_delay": {"type": "integer", "minimum": 0}
            }
        },
        "resource_limits": {
            "type": "object",
            "properties": {
                "cpu_percent": {"type": "number", "minimum": 0, "maximum": 100},
                "memory_limit_mb": {"type": "integer", "minimum": 0}
            }
        },
        "network": {
            "type": "object",
            "properties": {
                "allowed_interfaces": {"type": "array", "items": {"type": "string"}},
                "max_bandwidth_mbps": {"type": "number", "minimum": 0}
            }
        },
        "backups": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"},
                "directory": {"type": "string"}
            }
        },
        "metrics": {
            "type": "object",
            "properties": {
                "export_enabled": {"type": "boolean"},
                "export_path": {"type": "string"}
            }
        },
        "database": {
            "type": "object",
            "properties":{
                "host": {"type": "string"},
                "port": {"type": "integer"},
                "user": {"type": "string"},
                "password": {"type": "string"},
                "name": {"type": "string"}
            }
        }
    }
}

# Add command whitelist for security
ALLOWED_COMMANDS = {
    'apt_update': '/usr/bin/apt-get update',
    'apt_upgrade': '/usr/bin/unattended-upgrades',
    'apt_clean': '/usr/bin/apt-get clean',
    'docker': '/usr/bin/docker',
    'journalctl': '/usr/bin/journalctl',
    'sync': '/bin/sync',
    'shutdown': '/sbin/shutdown',
    'fsck': '/sbin/fsck'
}

# Custom Exception Types
class NetworkError(Exception):
    pass

class TimeoutError(Exception):
    pass

class ConfigurationError(Exception):
    pass

class SecurityError(Exception):
    pass

class ResourceLimitError(Exception):
    pass

class DatabaseError(Exception):
    pass

# Status Reporting
class TaskStatus(Enum):
    SUCCESS = "Success"
    FAILED = "Failed"
    SKIPPED = "Skipped"

@dataclasses.dataclass
class MaintenanceStatus:
    packages_updated: TaskStatus
    docker_cleaned: TaskStatus
    logs_cleaned: TaskStatus
    filesystem_synced: TaskStatus

# Improved Error Handling
class MaintenanceError(Exception):
    """Base exception for maintenance errors."""
    pass

class PackageUpdateError(MaintenanceError):
    """Exception raised for package update failures."""
    pass

# System Metrics
@dataclasses.dataclass
class SystemMetrics:
    disk_usage_percent: float
    memory_usage_percent: float
    load_average: float
    start_time: datetime
    end_time: datetime
    duration: float

# Job Results Tracker
@dataclasses.dataclass
class JobResult:
    name: str
    status: TaskStatus
    start_time: datetime
    end_time: datetime
    duration: float
    details: str = ""
    error: Optional[str] = None

class MaintenanceJobTracker:
    def __init__(self, logger: logging.Logger):
        self.jobs: List[JobResult] = []
        self.logger = logger

    def track_job(self, name: str) -> contextlib.ContextDecorator:
        @contextlib.contextmanager
        def job_context():
            start_time = datetime.now()
            job_result = JobResult(
                name=name,
                status=TaskStatus.FAILED,
                start_time=start_time,
                end_time=start_time,
                duration=0
            )
            try:
                yield job_result
                job_result.status = TaskStatus.SUCCESS
            except Exception as e:
                job_result.error = str(e)
                raise
            finally:
                job_result.end_time = datetime.now()
                job_result.duration = (job_result.end_time - job_result.start_time).total_seconds()
                self.jobs.append(job_result)

        return job_context()

    def generate_report(self) -> str:
        report = ["Maintenance Job Results:"]
        for job in self.jobs:
            report.append(f"\n{job.name}:")
            report.append(f"  Status: {job.status.value}")
            report.append(f"  Duration: {job.duration:.2f}s")
            if job.details:
                report.append(f"  Details: {job.details}")
            if job.error:
                report.append(f"  Error: {job.error}")
        return "\n".join(report)

# --- Resource Management ---
class ResourceManager:
    def __init__(self, limits: Dict[str, Any]):
        self.limits = limits
        self.current_usage: DefaultDict[str, float] = defaultdict(float)
        self.lock = asyncio.Lock()

    async def allocate_resources(self, task: "MaintenanceTask") -> bool:
        async with self.lock:
            # Check if enough resources are available
            if task.resource_limits:
                for resource, amount in task.resource_limits.items():
                    if resource in self.limits and self.current_usage[resource] + amount > self.limits[resource]:
                        print(f"Resource allocation failed for task {task.name}: {resource} limit exceeded.")
                        return False
            # Allocate resources
            if task.resource_limits:
                for resource, amount in task.resource_limits.items():
                    self.current_usage[resource] += amount
            print(f"Resources allocated for task {task.name}: {task.resource_limits}")
            return True

    async def release_resources(self, task: "MaintenanceTask"):
        async with self.lock:
            if task.resource_limits:
                for resource, amount in task.resource_limits.items():
                    self.current_usage[resource] -= amount
                print(f"Resources released for task {task.name}: {task.resource_limits}")

# --- Backup Management ---
class BackupManager:
    def __init__(self, logger: logging.Logger, backup_dir: Optional[str] = None):
        self.backup_dir = Path(backup_dir) if backup_dir else None
        self.logger = logger

    async def create_backup(self, path: Path) -> bool:
        if not self.backup_dir:
            self.logger.warning("Backup directory not configured. Skipping backup.")
            return False
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = self.backup_dir / path.name.with_suffix('.bak')
            await aioshutil.copy2(path, backup_path)
            self.logger.info(f"Backup created: {backup_path}")
            return True
        except Exception as e:
            self.logger.error(f"Backup failed: {e}")
            return False

    async def restore_backup(self, path: Path) -> bool:
        if not self.backup_dir:
            self.logger.warning("Backup directory not configured. Cannot restore backup.")
            return False
        try:
            backup_path = self.backup_dir / path.name.with_suffix('.bak')
            if await aiofiles.os.path.exists(backup_path):
                await aioshutil.move(backup_path, path)
                self.logger.info(f"Backup restored: {path}")
                return True
            self.logger.warning(f"Backup file not found: {backup_path}")
            return False
        except Exception as e:
            self.logger.error(f"Restore failed: {e}")
            return False

# --- Metrics Export ---
class MetricsExporter:
    def __init__(self, export_path: Optional[str], logger: logging.Logger):
        self.export_path = Path(export_path) if export_path else None
        self.logger = logger

    async def export_metrics(self, metrics: Dict[str, Any]) -> None:
        if not self.export_path:
            self.logger.warning("Metrics export path not configured. Skipping export.")
            return

        try:
            async with aiofiles.open(self.export_path, 'a') as f:
                await f.write(json.dumps({
                    'timestamp': datetime.now().isoformat(),
                    'metrics': metrics
                }) + '\n')
            self.logger.info(f"Metrics exported to {self.export_path}")
        except Exception as e:
            self.logger.error(f"Failed to export metrics: {e}")

# --- Enhanced Health Checks ---
class HealthChecker:
    def __init__(self, config: "Config", logger: logging.Logger):
        self.config = config
        self.logger = logger

    async def check_health(self) -> Dict[str, Any]:
        health_data = {
            'system': await self._check_system_health(),
            'tasks': await self._check_task_health(),
            'resources': await self._check_resource_health(),
            'network': await self._check_network_health(),
            'database': await self._check_database_health() if self.config.database else "Not Configured"
        }
        
        self.logger.info(f"Health Check Results: {health_data}")
        return health_data
    
    async def _check_system_health(self) -> Dict[str, bool]:
        return {
            "disk_space": check_disk_space(self.logger),
            "system_load": check_system_load(self.logger),
            "critical_services": check_critical_services(self.logger),
            "memory_usage": check_memory_usage(self.logger),
            "filesystem_health": check_filesystem_health(self.logger),
            "system_temperature": check_system_temperature(self.logger)
        }

    async def _check_task_health(self) -> Dict[str, str]:
        # Placeholder for task-specific health checks (e.g., last successful run)
        return {}

    async def _check_resource_health(self) -> Dict[str, str]:
        # Placeholder for resource-specific health checks (e.g., current usage vs. limits)
        return {}
    
    async def _check_interface(self, interface: str) -> bool:
        """Checks if a network interface is up and has an IP address."""
        try:
            # Check if interface is up
            result = await asyncio.create_subprocess_exec(
                'ip', 'link', 'show', interface,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()
            if result.returncode != 0 or "state UP" not in stdout.decode():
                self.logger.warning(f"Interface {interface} is not up.")
                return False

            # Check if interface has an IP address
            result = await asyncio.create_subprocess_exec(
                'ip', 'addr', 'show', interface,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()
            if result.returncode != 0 or not any(line.strip().startswith("inet ") for line in stdout.decode().splitlines()):
                self.logger.warning(f"Interface {interface} has no IP address.")
                return False

            self.logger.info(f"Interface {interface} check passed.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to check interface {interface}: {e}")
            return False

    async def _check_network_health(self) -> Dict[str, bool]:
        results = {}
        if self.config.network_settings:
            for interface in self.config.network_settings.get('allowed_interfaces', []):
                results[interface] = await self._check_interface(interface)
        else:
            self.logger.warning("Network settings not configured. Skipping network health check.")
        return results
    
    async def _check_database_health(self) -> Dict[str, str]:
        """Checks the health of the configured database."""
        try:
            db_config = self.config.database
            if not db_config:
                return {"status": "Not Configured"}
            
            # Example using a simple ping-like command for PostgreSQL.
            # Adjust the command and dependencies according to your database.
            proc = await asyncio.create_subprocess_exec(
                'pg_isready',
                '-h', db_config['host'],
                '-p', str(db_config['port']),
                '-U', db_config['user'],
                '-d', db_config['name'],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode == 0:
                return {"status": "OK", "message": stdout.decode().strip()}
            else:
                return {"status": "Error", "message": stderr.decode().strip()}
        except Exception as e:
            self.logger.error(f"Failed to check database health: {e}")
            return {"status": "Error", "message": str(e)}

# --- Graceful Shutdown Handler ---
class ShutdownHandler:
    def __init__(self, logger: logging.Logger):
        self.is_shutting_down = False
        self.logger = logger
        self.loop = asyncio.get_event_loop()
        
    def request_shutdown(self):
        self.logger.info("Shutdown requested.")
        self.is_shutting_down = True
        
        for task in asyncio.all_tasks(self.loop):
            if task is not asyncio.current_task():
                task.cancel()
        
    def handle_signal(self, signum, frame):
        self.logger.warning(f"Received signal {signal.Signals(signum).name}. Initiating graceful shutdown.")
        self.request_shutdown()
        

# Dependency Management
@dataclasses.dataclass
class MaintenanceTask:
    name: str
    function: callable
    dependencies: List[str] = dataclasses.field(default_factory=list)
    timeout: int = 300
    max_retries: int = 3
    retry_delay: int = 5
    resource_limits: Optional[Dict[str, Any]] = None
    priority: int = 10  # Default priority

# Task Retry Logic
@dataclasses.dataclass
class TaskRetryConfig:
    max_retries: int = 3
    retry_delay: int = 5
    
# Circuit Breaker
class CircuitBreaker:
    def __init__(self, threshold: int = 3, recovery_timeout: int = 30):
        self.threshold = threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.lock = asyncio.Lock()

    async def is_open(self) -> bool:
        async with self.lock:
            if self.failure_count >= self.threshold:
                if self.last_failure_time:
                    time_since_last_failure = (datetime.now() - self.last_failure_time).total_seconds()
                    if time_since_last_failure < self.recovery_timeout:
                        return True
                    else:
                        self.failure_count = 0
                        self.last_failure_time = None
            return False
            
    async def record_failure(self):
        async with self.lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()
            
    async def record_success(self):
        async with self.lock:
            self.failure_count = 0
            self.last_failure_time = None

async def run_with_timeout(task: MaintenanceTask, logger: logging.Logger) -> bool:
    """Run a task with timeout handling."""
    try:
        return await asyncio.wait_for(task.function(logger), timeout=task.timeout)
    except asyncio.TimeoutError:
        logger.error(f"Task {task.name} timed out after {task.timeout} seconds")
        raise TimeoutError(f"Task {task.name} timed out")
    
async def run_with_retry(task: MaintenanceTask, logger: logging.Logger, circuit_breaker: CircuitBreaker) -> bool:
    """Run a task with retry logic and circuit breaker."""
    if await circuit_breaker.is_open():
        logger.warning(f"Circuit breaker open for task {task.name}. Skipping execution.")
        return False

    for attempt in range(task.max_retries):
        try:
            # --- Structured Error Handling ---
            if await run_with_timeout(task, logger):
                await circuit_breaker.record_success()
                return True
            if attempt < task.max_retries - 1:
                logger.info(f"Retrying task {task.name} in {task.retry_delay} seconds...")
                await asyncio.sleep(task.retry_delay * (2**attempt))
        except NetworkError as e:
            logger.warning(f"Network error in task {task.name}: {e}. Retrying...")
            await circuit_breaker.record_failure()
            await asyncio.sleep(task.retry_delay * (2**attempt))
        except TimeoutError as e:
            logger.error(f"Timeout error in task {task.name}: {e}.")
            await circuit_breaker.record_failure()
            if attempt < task.max_retries -1:
                await asyncio.sleep(task.retry_delay * (2**attempt))
        except ConfigurationError as e:
            logger.error(f"Non-retryable configuration error in task {task.name}: {e}. Aborting retries.")
            return False
        except SecurityError as e:
            logger.error(f"Non-retryable security error in task {task.name}: {e}. Aborting retries.")
            return False
        except Exception as e:
            logger.error(f"Task {task.name} failed on attempt {attempt + 1}: {e}")
            await circuit_breaker.record_failure()
            if attempt < task.max_retries - 1:
                logger.info(f"Retrying...")
                await asyncio.sleep(task.retry_delay * (2**attempt))
    return False

# Task Progress Tracking
@dataclasses.dataclass
class TaskProgress:
    total_tasks: int
    completed_tasks: int
    current_task: Optional[str] = None
    started_at: Optional[datetime] = None
    
    def get_progress_percentage(self) -> float:
        """Calculate the percentage of completed tasks."""
        if self.total_tasks == 0:
            return 0.0
        return (self.completed_tasks / self.total_tasks) * 100

class TaskScheduler:
    def __init__(self, logger: logging.Logger, resource_manager: ResourceManager):
        self.tasks: Dict[str, MaintenanceTask] = {}
        self.logger = logger
        self.progress = TaskProgress(0, 0)
        self.circuit_breaker = CircuitBreaker()
        self.task_group_timeout: Optional[int] = None
        self.resource_manager = resource_manager
        
    def add_task(self, task: MaintenanceTask) -> None:
        self.tasks[task.name] = task

    async def _run_task_async(self, task: MaintenanceTask, tracker: MaintenanceJobTracker) -> bool:
        """Runs a task asynchronously."""
        self.progress.current_task = task.name
        progress_percent = self.progress.get_progress_percentage()
        self.logger.info(f"Progress: {self.progress.completed_tasks}/{self.progress.total_tasks} "
                         f"({progress_percent:.1f}%) - Running {task.name}")
        
        # --- Resource Allocation ---
        if not await self.resource_manager.allocate_resources(task):
            self.logger.error(f"Failed to allocate resources for task {task.name}. Skipping task.")
            return False

        with tracker.track_job(task.name) as job:
            try:
                if await run_with_retry(task, self.logger, self.circuit_breaker):
                    self.progress.completed_tasks += 1
                    return True
                else:
                    return False
            except Exception as e:
                self.logger.error(f"Task {task.name} failed: {e}")
                return False
            finally:
                await self.resource_manager.release_resources(task)

    async def run_tasks(self, tracker: MaintenanceJobTracker) -> bool:
        """Runs tasks with dependencies and concurrency."""
        self.progress = TaskProgress(
            total_tasks=len(self.tasks),
            completed_tasks=0,
            started_at=datetime.now()
        )
        completed = set()
        failed = set()
        
        # --- Task Prioritization ---
        sorted_tasks = sorted(self.tasks.items(), key=lambda item: item[1].priority)

        def can_run(task: MaintenanceTask) -> bool:
            return all(dep in completed for dep in task.dependencies)

        async def run_task_group():
            pending_tasks = [
                asyncio.create_task(self._run_task_async(task, tracker))
                for name, task in sorted_tasks
                if can_run(task) and name not in completed and name not in failed
            ]

            for task in asyncio.as_completed(pending_tasks):
                try:
                    success = await task
                    task_name = next((name for name, t in sorted_tasks if t.function == task.get_coro().cr_code.co_consts[0]), None) # Get task name
                    if success:
                        completed.add(task_name)
                    else:
                        failed.add(task_name)
                except Exception as e:
                    self.logger.error(f"Error during task execution: {e}")
                    failed.add(task.get_name())

        try:
            if self.task_group_timeout:
                await asyncio.wait_for(run_task_group(), timeout=self.task_group_timeout)
            else:
                await run_task_group()
        except asyncio.TimeoutError:
            self.logger.error(f"Task group timed out after {self.task_group_timeout} seconds.")
            return False

        return len(failed) == 0

class Config:
    """Configuration handler"""

    def __init__(self, config_path: Optional[str] = None) -> None:
        # Consider using environment variables for the path
        self.config_path = Path(config_path or os.environ.get('MAINTENANCE_CONFIG_PATH', '/home/mediaserver/scripts/maintenance_config.yaml'))
        self.config = self._load_config()
        self._validate_config(self.config)
        self._validate_paths()

    def _load_config(self) -> Dict[str, Any]:
        """Load and validate configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
                if config is None:
                    raise ValueError("Configuration file is empty")
                return config
        except FileNotFoundError:
            print(f"Error: Configuration file not found at {self.config_path}")
            sys.exit(1)
        except Exception as e:
            print(f"Error loading config: {e}")
            sys.exit(1)
            
    def _validate_resource_limits(self, resource_limits: Dict[str, Any]) -> None:
        """Validate resource limit settings."""
        if not isinstance(resource_limits, dict):
            raise ValidationError("resource_limits must be a dictionary.")
        
        for resource, limit in resource_limits.items():
            if resource == "cpu_percent":
                if not (0 <= limit <= 100):
                    raise ValidationError("cpu_percent must be between 0 and 100.")
            elif resource == "memory_limit_mb":
                if limit < 0:
                    raise ValidationError("memory_limit_mb must be non-negative.")
            else:
                raise ValidationError(f"Unknown resource limit: {resource}")

    def _validate_network_settings(self, network_settings: Dict[str, Any]) -> None:
        """Validate network settings."""
        if not isinstance(network_settings, dict):
            raise ValidationError("network must be a dictionary.")

        for setting, value in network_settings.items():
            if setting == "allowed_interfaces":
                if not isinstance(value, list):
                    raise ValidationError("allowed_interfaces must be a list.")
            elif setting == "max_bandwidth_mbps":
                if value < 0:
                    raise ValidationError("max_bandwidth_mbps must be non-negative.")
            else:
                raise ValidationError(f"Unknown network setting: {setting}")
    
    def _validate_backup_settings(self, backup_settings: Dict[str, Any]) -> None:
        """Validates the backup settings in the configuration."""
        if not isinstance(backup_settings, dict):
            raise ValidationError("backups must be a dictionary.")

        for setting, value in backup_settings.items():
            if setting == "enabled":
                if not isinstance(value, bool):
                    raise ValidationError("backup enabled setting must be a boolean.")
            elif setting == "directory":
                if not isinstance(value, str):
                    raise ValidationError("backup directory must be a string.")
                backup_dir = Path(value)
                if not backup_dir.is_dir():
                    raise ValidationError(f"Backup directory does not exist or is not a directory: {backup_dir}")
                if not os.access(backup_dir, os.W_OK):
                    raise ValidationError(f"Backup directory is not writable: {backup_dir}")
            else:
                raise ValidationError(f"Unknown backup setting: {setting}")
                
    def _validate_metrics_settings(self, metrics_settings: Dict[str, Any]) -> None:
        """Validates the metrics settings."""
        if not isinstance(metrics_settings, dict):
            raise ValidationError("metrics must be a dictionary.")
            
        for setting, value in metrics_settings.items():
            if setting == "export_enabled":
                if not isinstance(value, bool):
                    raise ValidationError("metrics export_enabled setting must be a boolean.")
            elif setting == "export_path":
                if not isinstance(value, str):
                    raise ValidationError("metrics export_path must be a string.")
                export_path = Path(value)
                if not export_path.parent.exists():
                    raise ValidationError(f"Metrics export path directory does not exist: {export_path.parent}")
                if not os.access(export_path.parent, os.W_OK):
                    raise ValidationError(f"Metrics export path directory is not writable: {export_path.parent}")
            else:
                raise ValidationError(f"Unknown metrics setting: {setting}")
                
    def _validate_database_settings(self, database_settings: Dict[str, Any]) -> None:
        """Validate database settings."""
        if not isinstance(database_settings, dict):
            raise ValidationError("database must be a dictionary.")
            
        required_keys = ["host", "port", "user", "name"]
        for key in required_keys:
            if key not in database_settings or not database_settings[key]:
                raise ValidationError(f"Database setting '{key}' is missing or empty.")
        
        if not isinstance(database_settings["port"], int):
            raise ValidationError("Database port must be an integer.")

    def _validate_config(self, config: Dict[str, Any]) -> None:
        """Validate the loaded configuration against the schema and additional checks."""
        try:
            validate(instance=config, schema=CONFIG_SCHEMA)
        except ValidationError as e:
            print(f"Error: Invalid configuration: {e}")
            sys.exit(1)
            
        # Add custom validators for specific fields
        if not isinstance(config['logging']['file'], str) or not config['logging']['file']:
            raise ValidationError("Logging file path must be a non-empty string.")
            
        # Add environment-specific validation
        if os.name == 'nt': # Example: Windows-specific validation
            if not config['maintenance']['docker_prune']:
                print("Warning: Docker pruning is recommended on Windows.")
                
        # --- Add validation for resource limits ---
        if 'resource_limits' in config:
            self._validate_resource_limits(config['resource_limits'])
            
        # --- Add validation for network settings ---
        if 'network' in config:
            self._validate_network_settings(config['network'])
            
        # --- Add validation for backup settings ---
        if 'backups' in config:
            self._validate_backup_settings(config['backups'])
            
        # --- Add validation for metrics settings ---
        if 'metrics' in config:
            self._validate_metrics_settings(config['metrics'])
            
        # --- Add validation for database settings ---
        if 'database' in config:
            self._validate_database_settings(config['database'])

    def _validate_paths(self) -> None:
        """Validate all required paths exist and are accessible."""
        required_paths = [
            Path(self.log_file).parent,
        ]
        if self.docker_prune:
            required_paths.append(Path(ALLOWED_COMMANDS['docker']))

        for path in required_paths:
            if not path.exists():
                raise ValueError(f"Required path does not exist: {path}")
            if not os.access(path, os.R_OK):
                raise ValueError(f"Required path is not readable: {path}")

        # Check for executables separately
        for cmd in ['apt_update', 'apt_upgrade', 'apt_clean', 'journalctl', 'sync', 'shutdown', 'fsck']:
            if not os.access(ALLOWED_COMMANDS[cmd], os.X_OK):
                raise ValueError(f"Required executable is not executable: {ALLOWED_COMMANDS[cmd]}")

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
        
    @property
    def resource_limits(self) -> Optional[Dict[str, Any]]:
        return self.config.get('resource_limits')
    
    @property
    def network_settings(self) -> Optional[Dict[str, Any]]:
        return self.config.get('network')
        
    @property
    def backup_settings(self) -> Optional[Dict[str, Any]]:
        return self.config.get('backups')
    
    @property
    def metrics_settings(self) -> Optional[Dict[str, Any]]:
        return self.config.get('metrics')

    @property
    def database(self) -> Optional[Dict[str, Any]]:
        return self.config.get('database')

    def _check_config_health(self) -> bool:
        """Checks the validity of the configuration file."""
        try:
            self._load_config()
            return True
        except Exception as e:
            print(f"Config health check failed: {e}")
            return False
            
    def _check_filesystem_health(self) -> bool:
        """Performs a basic filesystem health check."""
        try:
            return os.path.exists("/") and os.access("/", os.R_OK | os.W_OK)
        except Exception as e:
            print(f"Filesystem health check failed: {e}")
            return False
                   
    def _check_resource_health(self) -> bool:
        """Checks for basic resource availability."""
        try:
            return check_disk_space(logging.getLogger('dummy')) and check_memory_usage(logging.getLogger('dummy')) # Use a dummy logger
        except Exception as e:
            print(f"Resource health check failed: {e}")
            return False
            
    def health_check(self) -> Dict[str, bool]:
        """Comprehensive health check of all components."""
        return {
            "config": self._check_config_health(),
            "filesystem": self._check_filesystem_health(),
            "resources": self._check_resource_health(),
        }

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

def run_command(command: str, logger: logging.Logger, timeout: int = 300) -> bool:
    """Run a whitelisted shell command with timeout."""
    if not any(command.startswith(cmd) for cmd in ALLOWED_COMMANDS.values()):
        logger.error(f"Command not whitelisted: {command}")
        raise SecurityError(f"Command not whitelisted: {command}")
        
    try:
        result = subprocess.run(
            command,
            shell=True,
            text=True,
            capture_output=True,
            check=True,
            timeout=timeout
        )
        logger.info(f"Command succeeded: {command}")
        if result.stdout.strip():
            logger.info(f"Output: {result.stdout.strip()}")
        return True
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out after {timeout} seconds: {command}")
        raise TimeoutError(f"Command timed out: {command}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {command}")
        if e.stdout:
            logger.error(f"Output: {e.stdout}")
        if e.stderr:
            logger.error(f"Error: {e.stderr}")
        raise
    
def check_single_instance() -> None:
    """Check if another instance of the script is running."""
    script_name = Path(__file__).name
    result = subprocess.run(['pgrep', '-f', script_name], capture_output=True, text=True)
    pids = result.stdout.strip().split('\n')
    if len([pid for pid in pids if pid and int(pid) != os.getpid()]) > 0:
        print(f"Another instance of {script_name} is already running. Exiting.")
        sys.exit(0)

async def update_packages(logger: logging.Logger) -> bool:
    """Update package lists and install updates."""
    try:
        if not run_command(ALLOWED_COMMANDS['apt_update'], logger):
            raise PackageUpdateError("Failed to update package lists")
            
        if not run_command(ALLOWED_COMMANDS['apt_upgrade'], logger):
            raise PackageUpdateError("Failed to install security updates")

        if not run_command(ALLOWED_COMMANDS['apt_clean'], logger):
            logger.warning("Failed to clean package cache")

        return True
    except PackageUpdateError as e:
        logger.error(f"Package update error: {e}")
        # Attempt cleanup
        if not run_command(ALLOWED_COMMANDS['apt_clean'], logger):
            logger.warning("Failed to clean package cache during error recovery")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during package updates: {e}")
        # Attempt cleanup
        if not run_command(ALLOWED_COMMANDS['apt_clean'], logger):
            logger.warning("Failed to clean package cache during error recovery")
        raise

async def cleanup_docker(logger: logging.Logger) -> bool:
    """Clean up Docker system."""
    if not os.path.exists(ALLOWED_COMMANDS['docker']):
        logger.info("Docker not installed, skipping cleanup")
        return True
        
    logger.info("Cleaning up Docker system...")
    return run_command(f"{ALLOWED_COMMANDS['docker']} system prune -f --volumes", logger)

async def cleanup_logs(logger: logging.Logger, retention_days: int) -> bool:
    """Clean up system logs."""
    logger.info(f"Clearing logs older than {retention_days} days...")
    return run_command(f"{ALLOWED_COMMANDS['journalctl']} --vacuum-time={retention_days}d", logger)

async def sync_filesystem(logger: logging.Logger) -> bool:
    """Sync filesystem to disk."""
    logger.info("Syncing filesystem...")
    return run_command(ALLOWED_COMMANDS['sync'], logger)

def restart_system(logger: logging.Logger, delay: int = 5) -> None:
    """Restart the system after a delay with proper signal handling."""
    shutdown_handler = ShutdownHandler(logger)

    def handle_signal(signum, frame):
        shutdown_handler.handle_signal(signum, frame)

    # Register signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    logger.info(f"Scheduling system restart in {delay} seconds...")
    try:
        time.sleep(delay)
        logger.info("Executing restart command...")
        run_command(ALLOWED_COMMANDS['shutdown'] + " -r now", logger)
    except Exception as e:
        logger.error(f"Failed to restart system: {e}")
        sys.exit(1)

# Resource Management
def check_disk_space(logger: logging.Logger, min_free_space_gb: int = 5) -> bool:
    """Check if there's enough free disk space."""
    try:
        stats = os.statvfs('/')
        free_gb = (stats.f_bavail * stats.f_frsize) / (1024**3)
        if free_gb < min_free_space_gb:
            logger.error(f"Low disk space: {free_gb:.2f}GB free")
            return False
        logger.info(f"Disk space check passed: {free_gb:.2f}GB free")
        return True
    except Exception as e:
        logger.error(f"Failed to check disk space: {e}")
        return False
        
def check_system_load(logger: logging.Logger, max_load_avg: float = 1.0) -> bool:
    """Check if system load average is within acceptable limits."""
    try:
        load_avg = os.getloadavg()[0]  # Get 1-minute load average
        if load_avg > max_load_avg:
            logger.error(f"High system load: {load_avg:.2f}")
            return False
        logger.info(f"System load check passed: {load_avg:.2f}")
        return True
    except Exception as e:
        logger.error(f"Failed to check system load: {e}")
        return False
        
def check_critical_services(logger: logging.Logger, services: List[str] = ["ssh", "systemd-journald"]) -> bool:
    """Check if critical system services are running."""
    all_services_running = True
    for service in services:
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', service],
                capture_output=True,
                text=True,
                check=True
            )
            if result.stdout.strip() != "active":
                logger.error(f"Service {service} is not active")
                all_services_running = False
            else:
                logger.info(f"Service check passed: {service} is active")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to check service {service}: {e}")
            all_services_running = False
    return all_services_running
    
def check_memory_usage(logger: logging.Logger, max_usage_percent: float = 90.0) -> bool:
    """Check if memory usage is within acceptable limits."""
    try:
        with open('/proc/meminfo', 'r') as f:
            lines = f.readlines()
            
        mem_info = {}
        for line in lines:
            key, value = line.split(':')
            value = int(''.join(filter(str.isdigit, value)))
            mem_info[key.strip()] = value
            
        used_percent = (1 - (mem_info['MemAvailable'] / mem_info['MemTotal'])) * 100
        
        if used_percent > max_usage_percent:
            logger.error(f"High memory usage: {used_percent:.1f}%")
            return False
            
        logger.info(f"Memory check passed: {used_percent:.1f}% used")
        return True
    except Exception as e:
        logger.error(f"Failed to check memory usage: {e}")
        return False

def check_filesystem_health(logger: logging.Logger) -> bool:
    """Check filesystem for errors using fsck in read-only mode."""
    try:
        result = subprocess.run(
            [ALLOWED_COMMANDS['fsck'], '-n', '/'],
            capture_output=True,
            text=True
        )
        if result.returncode > 0:
            logger.error("Filesystem errors detected")
            logger.error(result.stderr)
            return False
        logger.info("Filesystem check passed")
        return True
    except Exception as e:
        logger.error(f"Failed to check filesystem: {e}")
        return False

# Pre and Post Maintenance Hooks
class MaintenanceHooks:
    def __init__(self):
        self.pre_hooks: List[callable] = []
        self.post_hooks: List[callable] = []
        
    def add_pre_hook(self, hook: callable) -> None:
        self.pre_hooks.append(hook)
        
    def add_post_hook(self, hook: callable) -> None:
        self.post_hooks.append(hook)
        
    def run_pre_hooks(self, logger: logging.Logger) -> bool:
        success = True
        for hook in self.pre_hooks:
            try:
                if not hook(logger):
                    success = False
            except Exception as e:
                logger.error(f"Pre-hook failed: {e}")
                success = False
        return success
        
    def run_post_hooks(self, logger: logging.Logger, status: MaintenanceStatus) -> None:
        for hook in self.post_hooks:
            try:
                hook(logger, status)
            except Exception as e:
                logger.error(f"Post-hook failed: {e}")

# System Monitoring
@dataclasses.dataclass
class IOStats:
    read_bytes: int
    write_bytes: int
    read_time: int
    write_time: int

def get_disk_io_stats(device: str = "sda") -> IOStats:
    """Get disk I/O statistics."""
    try:
        with open(f"/sys/block/{device}/stat", "r") as f:
            stats = f.read().strip().split()
            return IOStats(
                read_bytes=int(stats[2]) * 512,  # Sectors to bytes
                write_bytes=int(stats[6]) * 512,
                read_time=int(stats[3]),
                write_time=int(stats[7])
            )
    except Exception as e:
        print(f"Failed to get disk I/O stats: {e}")
        return IOStats(0, 0, 0, 0)

@dataclasses.dataclass
class NetworkStats:
    bytes_sent: int
    bytes_recv: int
    packets_sent: int
    packets_recv: int

def get_network_stats(interface: str = "eth0") -> NetworkStats:
    """Get network activity statistics."""
    try:
        with open(f"/sys/class/net/{interface}/statistics/tx_bytes", 'r') as f:
            tx_bytes = int(f.read())
        with open(f"/sys/class/net/{interface}/statistics/rx_bytes", 'r') as f:
            rx_bytes = int(f.read())
        with open(f"/sys/class/net/{interface}/statistics/tx_packets", 'r') as f:
            tx_packets = int(f.read())
        with open(f"/sys/class/net/{interface}/statistics/rx_packets", 'r') as f:
            rx_packets = int(f.read())
        return NetworkStats(tx_bytes, rx_bytes, tx_packets, rx_packets)
    except Exception as e:
        print(f"Failed to get network stats: {e}")
        return NetworkStats(0, 0, 0, 0)

@dataclasses.dataclass
class ProcessStats:
    cpu_percent: float
    memory_percent: float
    open_files: int
    threads: int

def get_process_stats(pid: int = None) -> ProcessStats:
    """Get resource usage statistics for the current process."""
    try:
        if pid is None:
            pid = os.getpid()
        with open(f"/proc/{pid}/stat", 'r') as f:
            stats = f.read().split()
        with open(f"/proc/{pid}/status", 'r') as f:
            status = {line.split(':', 1)[0]: line.split(':', 1)[1].strip() for line in f}
            
        # Get CPU time (utime + stime)
        utime = int(stats[13])
        stime = int(stats[14])
        
        # Convert jiffies to seconds
        cpu_time = (utime + stime) / os.sysconf(os.sysconf_names['SC_CLK_TCK'])
        
        # Get memory usage
        mem_bytes = int(status['VmRSS'].split()[0]) * 1024
        
        # Get total memory (to calculate percentage)
        with open('/proc/meminfo', 'r') as f:
            mem_total_line = f.readline().split()
            mem_total = int(mem_total_line[1]) * 1024
            
        mem_percent = (mem_bytes / mem_total) * 100
            
        return ProcessStats(
            cpu_percent=cpu_time,
            memory_percent=mem_percent,
            open_files=len(os.listdir(f"/proc/{pid}/fd")),
            threads=int(status["Threads"])
        )
    except Exception as e:
        print(f"Failed to get process stats: {e}")
        return ProcessStats(0, 0, 0, 0)

def check_system_temperature(logger: logging.Logger, max_temp: float = 80.0) -> bool:
    """Check system temperature."""
    try:
        temps = []
        for sensor in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
            with open(sensor) as f:
                temps.append(int(f.read()) / 1000.0)  # Convert to Celsius
        if temps:
            max_temp_found = max(temps)
            if max_temp_found > max_temp:
                logger.error(f"High system temperature: {max_temp_found:.1f}°C")
                return False
            logger.info(f"Temperature check passed: {max_temp_found:.1f}°C")
            return True
        return True
    except Exception as e:
        logger.error(f"Failed to check system temperature: {e}")
        return False

# Backup Verification (System State Verification)
def verify_system_state(logger: logging.Logger) -> bool:
    """Verify system is in a good state for maintenance."""
    checks = {
        "Disk Space": check_disk_space(logger),
        "System Load": check_system_load(logger),
        "Critical Services": check_critical_services(logger),
        "Memory Usage": check_memory_usage(logger),
        "Filesystem Health": check_filesystem_health(logger),
        "System Temperature": check_system_temperature(logger)
    }
    
    failed_checks = [check for check, status in checks.items() if not status]
    if failed_checks:
        logger.error(f"System checks failed: {', '.join(failed_checks)}")
        return False
    logger.info("System state verification passed")
    return True
    
async def collect_metrics_async(logger: logging.Logger) -> SystemMetrics:
    """Collect system metrics before and after maintenance."""
    start_time = datetime.now()
    
    # Get disk usage
    stats = await asyncio.to_thread(os.statvfs, '/')
    disk_usage = (1 - (stats.f_bavail / stats.f_blocks)) * 100
    
    # Get memory usage asynchronously
    async with aiofiles.open('/proc/meminfo', 'r') as f:
        lines = await f.readlines()
    mem_info = {}
    for line in lines:
        key, value = line.split(':')
        value = int(''.join(filter(str.isdigit, value)))
        mem_info[key.strip()] = value
    memory_usage = (1 - (mem_info['MemAvailable'] / mem_info['MemTotal'])) * 100
    
    # Get load average
    load_avg = os.getloadavg()[0]
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    metrics = SystemMetrics(
        disk_usage_percent=disk_usage,
        memory_usage_percent=memory_usage,
        load_average=load_avg,
        start_time=start_time,
        end_time=end_time,
        duration=duration
    )
    
    logger.info(f"System Metrics: Disk Usage={metrics.disk_usage_percent:.1f}%, "
                f"Memory Usage={metrics.memory_usage_percent:.1f}%, "
                f"Load Average={metrics.load_average:.2f}, "
                f"Duration={metrics.duration:.2f}s")
    
    return metrics

# Metric Comparison
def compare_metrics(before: SystemMetrics, after: SystemMetrics, logger: logging.Logger) -> None:
    """Compare system metrics before and after maintenance."""
    changes = {
        "Disk Usage": after.disk_usage_percent - before.disk_usage_percent,
        "Memory Usage": after.memory_usage_percent - before.memory_usage_percent,
        "Load Average": after.load_average - before.load_average
    }
    
    logger.info("System Metrics Changes:")
    for metric, change in changes.items():
        direction = "increased" if change > 0 else "decreased"
        logger.info(f"  {metric} {direction} by {abs(change):.2f}{'%' if metric != 'Load Average' else ''}")

def collect_extended_metrics(logger: logging.Logger) -> Dict[str, Any]:
    """Collect additional system metrics."""
    return {
        "process": get_process_stats(),
        "network": get_network_stats(),
        "io": get_disk_io_stats(),
    }

async def main() -> None:
    check_single_instance()

    config = Config()
    logger = setup_logging(config)
    
    # --- Initialize Shutdown Handler ---
    shutdown_handler = ShutdownHandler(logger)
    
    # --- Register Signal Handlers ---
    loop = asyncio.get_event_loop()
    for signame in ('SIGINT', 'SIGTERM'):
        loop.add_signal_handler(
            getattr(signal, signame),
            shutdown_handler.handle_signal,
            getattr(signal, signame),
            None
        )
        
    tracker = MaintenanceJobTracker(logger)
    resource_manager = ResourceManager(config.resource_limits or {})
    scheduler = TaskScheduler(logger, resource_manager)
    scheduler.task_group_timeout = 900
    
    # --- Initialize Backup Manager if enabled ---
    backup_manager = None
    if config.backup_settings and config.backup_settings.get('enabled'):
            backup_manager = BackupManager(logger, config.backup_settings.get('directory'))

    # --- Initialize Metrics Exporter if enabled ---
    metrics_exporter = None
    if config.metrics_settings and config.metrics_settings.get('export_enabled'):
        metrics_exporter = MetricsExporter(config.metrics_settings.get('export_path'), logger)

    # --- Perform initial health check ---
    health_checker = HealthChecker(config, logger)
    initial_health = await health_checker.check_health()

    if not all(all(v for v in status.values()) if isinstance(status, dict) else status for status in initial_health.values()):
        logger.error("Initial health check failed. Aborting maintenance.")
        return
    
    # --- Define tasks with dependencies ---
    # --- Example of backing up the config file before maintenance ---
    async def backup_config(logger: logging.Logger) -> bool:
        if backup_manager:
            return await backup_manager.create_backup(config.config_path)
        return True

    if backup_manager:
        scheduler.add_task(MaintenanceTask(
            name="backup_config",
            function=backup_config,
            dependencies=[],
            priority=20  # Higher priority
        ))
    
    scheduler.add_task(MaintenanceTask(
        name="system_check",
        function=lambda l: asyncio.to_thread(verify_system_state, l),
        dependencies=["backup_config"] if backup_manager else [],
        max_retries=1,
        priority=10
    ))
    
    scheduler.add_task(MaintenanceTask(
        name="package_update",
        function=update_packages,
        dependencies=["system_check"],
        priority=5
    ))
    
    scheduler.add_task(MaintenanceTask(
        name="docker_cleanup",
        function=cleanup_docker if config.docker_prune else (lambda l: asyncio.sleep(0)), # No-op if docker_prune is False
        dependencies=["system_check"],
        priority=7
    ))
    
    scheduler.add_task(MaintenanceTask(
        name="log_cleanup",
        function=lambda l: cleanup_logs(l, config.log_retention),
        dependencies=["system_check"],
        priority=8
    ))

    scheduler.add_task(MaintenanceTask(
        name="sync_filesystem",
        function=sync_filesystem,
        dependencies=["package_update", "docker_cleanup", "log_cleanup"],  # Sync after other tasks
        priority=3
    ))
    
    logger.info("Starting daily maintenance tasks...")
    metrics_before = await collect_metrics_async(logger)
    extended_metrics_before = collect_extended_metrics(logger)
    logger.info(f"Extended Metrics (Before): {extended_metrics_before}")
    
    try:
        if not await scheduler.run_tasks(tracker):
            logger.error("Some maintenance tasks failed")
        
        metrics_after = await collect_metrics_async(logger)
        extended_metrics_after = collect_extended_metrics(logger)
        logger.info(f"Extended Metrics (After): {extended_metrics_after}")
        compare_metrics(metrics_before, metrics_after, logger)
        logger.info(tracker.generate_report())
        
        # --- Export metrics if enabled ---
        if metrics_exporter:
            await metrics_exporter.export_metrics({
                "system_metrics_before": dataclasses.asdict(metrics_before),
                "system_metrics_after": dataclasses.asdict(metrics_after),
                "extended_metrics_before": extended_metrics_before,
                "extended_metrics_after": extended_metrics_after,
                "job_results": [dataclasses.asdict(job) for job in tracker.jobs]
            })
        
    except Exception as e:
        logger.error(f"Critical error during maintenance: {e}")
        sys.exit(1)
    finally:
        logger.info(f"Maintenance completed. "
                    f"Tasks completed: {scheduler.progress.completed_tasks}/"
                    f"{scheduler.progress.total_tasks}")
        
    if verify_system_state(logger):
        restart_system(logger, config.restart_delay)
    else:
        logger.error("System state verification failed after maintenance")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
