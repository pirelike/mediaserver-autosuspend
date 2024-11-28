#!/usr/bin/env python3

"""
MediaServer AutoSuspend - Main Entry Point
----------------------------------------

This module serves as the main entry point for the MediaServer AutoSuspend application.
It handles command-line arguments, logging setup, and the main monitoring loop.
"""

import os
import sys
import time
import signal
import argparse
import logging
import psutil
import shutil
from datetime import datetime
from pathlib import Path
from typing import NoReturn, Dict, Any, List

from mediaserver_autosuspend import (
    load_config,
    create_service_checkers,
    SuspensionManager,
    __version__
)

def setup_logging(config: dict, log_rotation: bool = True) -> None:
    """Configure logging based on configuration settings."""
    log_file = config.get('LOG_FILE', '/var/log/mediaserver-autosuspend.log')
    log_level = getattr(logging, config.get('LOG_LEVEL', 'INFO').upper())
    max_log_size = config.get('MAX_LOG_SIZE', 10 * 1024 * 1024)  # 10MB default
    backup_count = config.get('LOG_BACKUP_COUNT', 5)
    
    # Create log directory if it doesn't exist
    log_path = Path(log_file).parent
    if not log_path.exists():
        log_path.mkdir(parents=True, exist_ok=True)
    
    handlers = [logging.StreamHandler(sys.stdout)]
    
    if log_rotation:
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_log_size,
            backupCount=backup_count
        )
    else:
        file_handler = logging.FileHandler(log_file)
    
    handlers.append(file_handler)
    
    # Custom formatter with thread ID and process ID
    formatter = logging.Formatter(
        '%(asctime)s - [%(process)d:%(thread)d] - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=handlers
    )
    
    for handler in handlers:
        handler.setFormatter(formatter)

def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='MediaServer AutoSuspend - Automatic server power management'
    )
    
    # Configuration options
    config_group = parser.add_argument_group('Configuration')
    config_group.add_argument(
        '-c', '--config',
        help='Path to configuration file',
        type=str,
        default=None
    )
    config_group.add_argument(
        '--generate-config',
        help='Generate example configuration file',
        action='store_true'
    )
    
    # Operation modes
    mode_group = parser.add_argument_group('Operation Modes')
    mode_group.add_argument(
        '--check-only',
        help='Check service status and exit',
        action='store_true'
    )
    mode_group.add_argument(
        '--monitor',
        help='Run in monitoring mode (default)',
        action='store_true'
    )
    mode_group.add_argument(
        '--force-suspend',
        help='Force system suspension (requires root)',
        action='store_true'
    )
    mode_group.add_argument(
        '--service-test',
        help='Test connectivity to all configured services',
        action='store_true'
    )
    
    # Debug options
    debug_group = parser.add_argument_group('Debugging')
    debug_group.add_argument(
        '--debug',
        help='Enable debug logging',
        action='store_true'
    )
    debug_group.add_argument(
        '--trace',
        help='Enable trace-level logging (very verbose)',
        action='store_true'
    )
    debug_group.add_argument(
        '--no-log-rotation',
        help='Disable log rotation',
        action='store_true'
    )
    debug_group.add_argument(
        '--dump-state',
        help='Dump current system state to file',
        action='store_true'
    )
    
    # Misc options
    misc_group = parser.add_argument_group('Miscellaneous')
    misc_group.add_argument(
        '--version',
        help='Show version information',
        action='store_true'
    )
    misc_group.add_argument(
        '--stats',
        help='Show runtime statistics',
        action='store_true'
    )
    
    return parser.parse_args()

class SystemStats:
    """Collect and manage system statistics."""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.suspend_count = 0
        self.check_count = 0
        self.last_active_services: Dict[str, datetime] = {}
    
    def update_service_activity(self, service_name: str, is_active: bool) -> None:
        """Update service activity timestamp."""
        if is_active:
            self.last_active_services[service_name] = datetime.now()
    
    def get_summary(self) -> Dict[str, Any]:
        """Get statistics summary."""
        runtime = datetime.now() - self.start_time
        return {
            'runtime': str(runtime),
            'suspend_count': self.suspend_count,
            'checks_performed': self.check_count,
            'last_active_services': {
                name: str(timestamp)
                for name, timestamp in self.last_active_services.items()
            }
        }

class GracefulExit:
    """Context manager for handling graceful shutdown."""
    
    def __init__(self):
        self.should_exit = False
        self.force_exit = False
        signal.signal(signal.SIGINT, self._exit_gracefully)
        signal.signal(signal.SIGTERM, self._exit_gracefully)
        signal.signal(signal.SIGUSR1, self._force_exit)
    
    def _exit_gracefully(self, signo, frame) -> None:
        """Signal handler for graceful shutdown."""
        if self.should_exit:  # Second signal received
            logging.warning("Forced shutdown initiated")
            self.force_exit = True
        else:
            self.should_exit = True
            logging.info(f"Received signal {signo}. Starting graceful shutdown...")
    
    def _force_exit(self, signo, frame) -> None:
        """Signal handler for forced exit."""
        self.force_exit = True
        logging.warning("Forced exit requested via SIGUSR1")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            logging.error(f"Error during execution: {exc_val}")
        logging.info("Shutdown complete")

def check_system_requirements() -> List[str]:
    """
    Verify system requirements and return any warnings.
    
    Returns:
        List[str]: List of warning messages
    """
    warnings = []
    
    # Check Python version
    if sys.version_info < (3, 6):
        warnings.append("Python 3.6 or higher is required")
    
    # Check available disk space
    disk_usage = shutil.disk_usage('/')
    if disk_usage.free < 1_000_000_000:  # 1GB
        warnings.append("Less than 1GB of free disk space available")
    
    # Check system memory
    mem = psutil.virtual_memory()
    if mem.available < 500_000_000:  # 500MB
        warnings.append("Less than 500MB of available memory")
    
    # Check CPU load
    load = psutil.getloadavg()[0]
    if load > psutil.cpu_count() * 0.8:
        warnings.append(f"High CPU load detected: {load}")
    
    # Check required commands
    required_commands = ['systemctl', 'rtcwake', 'sync']
    for cmd in required_commands:
        if not shutil.which(cmd):
            warnings.append(f"Required command '{cmd}' not found")
    
    return warnings

def dump_system_state(manager: SuspensionManager, stats: SystemStats) -> None:
    """Dump current system state to a file for debugging."""
    state = {
        'timestamp': datetime.now().isoformat(),
        'stats': stats.get_summary(),
        'services': manager.get_status_summary(),
        'system': {
            'cpu_load': psutil.getloadavg(),
            'memory': dict(psutil.virtual_memory()._asdict()),
            'disk': dict(psutil.disk_usage('/')._asdict()),
            'uptime': time.time() - psutil.boot_time()
        }
    }
    
    dump_file = f"autosuspend_state_{int(time.time())}.json"
    import json
    with open(dump_file, 'w') as f:
        json.dump(state, f, indent=2)
    logging.info(f"System state dumped to {dump_file}")

def test_services(manager: SuspensionManager) -> bool:
    """
    Test connectivity to all configured services.
    
    Returns:
        bool: True if all services are reachable
    """
    print("\nTesting service connectivity...")
    all_ok = True
    
    for name, service in manager.services.items():
        print(f"\nTesting {name}...")
        try:
            is_active = service.check_activity()
            print(f"✓ {name}: Connection successful (Active: {is_active})")
        except Exception as e:
            print(f"✗ {name}: Connection failed - {str(e)}")
            all_ok = False
    
    return all_ok

def monitor_loop(manager: SuspensionManager, stats: SystemStats, exit_handler: GracefulExit) -> None:
    """Enhanced monitoring loop with additional checks and statistics."""
    logger = logging.getLogger(__name__)
    check_interval = manager.config.get('CHECK_INTERVAL', 60)
    
    # Track consecutive failures
    failed_checks = 0
    MAX_FAILURES = 3
    
    while not exit_handler.should_exit:
        try:
            # Update statistics
            stats.check_count += 1
            
            # Get service status and update statistics
            service_status = manager.get_status_summary()
            for service, is_active in service_status.items():
                stats.update_service_activity(service, is_active)
            
            # Log detailed system state in debug mode
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Memory usage: {psutil.virtual_memory().percent}%")
                logger.debug(f"CPU load: {psutil.getloadavg()}")
                logger.debug(f"Service status: {service_status}")
            
            if manager.should_suspend():
                logger.info("System is idle. Starting grace period...")
                
                # Wait through grace period
                if manager.check_grace_period():
                    logger.info("Grace period complete. Preparing for suspension...")
                    
                    # Verify system state before suspension
                    warnings = check_system_requirements()
                    if warnings:
                        logger.warning("System warnings detected:")
                        for warning in warnings:
                            logger.warning(f"- {warning}")
                    
                    # Attempt system suspension
                    if manager.suspend_system():
                        logger.info("System successfully suspended")
                        stats.suspend_count += 1
                        break
                    else:
                        logger.error("Failed to suspend system")
                        failed_checks += 1
            else:
                failed_checks = 0  # Reset failure counter on successful check
            
            # Check for too many consecutive failures
            if failed_checks >= MAX_FAILURES:
                logger.error(f"Too many consecutive failures ({MAX_FAILURES}). Exiting.")
                break
            
            # Handle forced exit
            if exit_handler.force_exit:
                logger.warning("Forced exit requested. Shutting down immediately.")
                break
            
            # Wait before next check
            time.sleep(check_interval)
            
        except Exception as e:
            logger.exception("Error in monitoring loop")
            failed_checks += 1
        
        # Dump state if requested
        if manager.config.get('AUTO_DUMP_ON_ERROR') and failed_checks > 0:
            dump_system_state(manager, stats)

def main() -> NoReturn:
    """Main entry point for the application."""
    args = parse_arguments()
    
    if args.version:
        print(f"MediaServer AutoSuspend v{__version__}")
        sys.exit(0)
    
    # Load configuration
    try:
        config = load_config(args.config)
    except Exception as e:
        print(f"Error loading configuration: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Override log level
    if args.trace:
        config['LOG_LEVEL'] = 'TRACE'
    elif args.debug:
        config['LOG_LEVEL'] = 'DEBUG'
    
    # Set up logging
    setup_logging(config, not args.no_log_rotation)
    logger = logging.getLogger(__name__)
    
    # Initialize statistics
    stats = SystemStats()
    
    # Check system requirements
    warnings = check_system_requirements()
    for warning in warnings:
        logger.warning(warning)
    
    try:
        # Initialize services
        services = create_service_checkers(config)
        
        # Create suspension manager
        manager = SuspensionManager(config, services)
        
        # Handle different operation modes
        if args.generate_config:
            manager.generate_example_config()
            sys.exit(0)
        
        if args.check_only:
            single_check_mode(manager)
        
        if args.service_test:
            success = test_services(manager)
            sys.exit(0 if success else 1)
        
        if args.force_suspend:
            if os.geteuid() != 0:
                logger.error("Root privileges required for forced suspension")
                sys.exit(1)
            manager.suspend_system()
            sys.exit(0)
        
        if args.stats:
            print("\nRuntime Statistics:")
            print("-" * 20)
            for key, value in stats.get_summary().items():
                print(f"{key}: {value}")
            sys.exit(0)
        
        if args.dump_state:
            dump_system_state(manager, stats)
            sys.exit(0)
        
        # Main monitoring loop
        with GracefulExit() as exit_handler:
            logger.info("Starting MediaServer AutoSuspend monitoring...")
            monitor_loop(manager, stats, exit_handler)
    
    except Exception as e:
        logger.exception("Unexpected error occurred")
        if args.dump_state or config.get('AUTO_DUMP_ON_ERROR'):
            dump_system_state(manager, stats)
        sys.exit(1)

if __name__ == "__main__":
    main()
