#!/usr/bin/env python3

"""
MediaServer AutoSuspend - Main Entry Point
----------------------------------------

This module serves as the main entry point for the MediaServer AutoSuspend application.
It handles command-line arguments, sets up logging, and manages the main monitoring loop.
"""

import os
import sys
import time
import signal
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import NoReturn, Dict, Any

from mediaserver_autosuspend import (
    load_config,
    create_service_checkers,
    SuspensionManager,
    __version__
)
from mediaserver_autosuspend.utils.process import (
    check_single_instance,
    dump_system_state
)
from mediaserver_autosuspend.logger import setup_logging
from mediaserver_autosuspend.config import ConfigurationManager

class GracefulExit:
    """Context manager for handling graceful shutdown."""
    
    def __init__(self):
        """Initialize shutdown flags and set up signal handlers."""
        self.should_exit = False
        self.force_exit = False
        signal.signal(signal.SIGINT, self._exit_gracefully)
        signal.signal(signal.SIGTERM, self._exit_gracefully)
        signal.signal(signal.SIGUSR1, self._force_exit)
    
    def _exit_gracefully(self, signo: int, frame) -> None:
        """Handle graceful shutdown signal."""
        if self.should_exit:  # Second signal received
            logging.warning("Forced shutdown initiated")
            self.force_exit = True
        else:
            self.should_exit = True
            logging.info(f"Received signal {signo}. Starting graceful shutdown...")
    
    def _force_exit(self, signo: int, frame) -> None:
        """Handle forced exit signal."""
        self.force_exit = True
        logging.warning("Forced exit requested via SIGUSR1")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            logging.error(f"Error during execution: {exc_val}")
        logging.info("Shutdown complete")

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
    
    return parser.parse_args()

def monitor_loop(manager: SuspensionManager, exit_handler: GracefulExit) -> None:
    """
    Main monitoring loop for checking service activity and managing suspension.
    
    Args:
        manager: Initialized SuspensionManager instance
        exit_handler: GracefulExit instance for handling shutdown
    """
    logger = logging.getLogger(__name__)
    check_interval = manager.config.get('CHECK_INTERVAL', 60)
    
    # Track consecutive failures
    failed_checks = 0
    MAX_FAILURES = 3
    
    while not exit_handler.should_exit:
        try:
            # Check if system should suspend
            if manager.should_suspend():
                logger.info("System is idle. Starting grace period...")
                
                # Wait through grace period
                if manager.check_grace_period():
                    logger.info("Grace period complete. Preparing for suspension...")
                    
                    # Attempt system suspension
                    if manager.suspend_system():
                        logger.info("System successfully suspended")
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
            
            # Dump state on error if configured
            if manager.config.get('AUTO_DUMP_ON_ERROR'):
                dump_system_state(manager)

def test_services(manager: SuspensionManager) -> bool:
    """
    Test connectivity to all configured services.
    
    Args:
        manager: Initialized SuspensionManager instance
        
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

def main() -> NoReturn:
    """Main entry point for the application."""
    args = parse_arguments()
    
    if args.version:
        print(f"MediaServer AutoSuspend v{__version__}")
        sys.exit(0)
    
    # Ensure single instance
    if not check_single_instance():
        sys.exit(1)
    
    # Load configuration
    try:
        config = load_config(args.config)
        if args.debug:
            config['LOG_LEVEL'] = 'DEBUG'
    except Exception as e:
        print(f"Error loading configuration: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Set up logging
    logger = setup_logging(config)
    
    try:
        # Initialize services
        services = create_service_checkers(config)
        
        # Create suspension manager
        manager = SuspensionManager(config, services)
        
        # Handle different operation modes
        if args.generate_config:
            config_manager = ConfigurationManager()
            config_manager.generate_example_config('config.example.json')
            sys.exit(0)
        
        if args.service_test:
            success = test_services(manager)
            sys.exit(0 if success else 1)
        
        if args.force_suspend:
            if os.geteuid() != 0:
                logger.error("Root privileges required for forced suspension")
                sys.exit(1)
            manager.suspend_system()
            sys.exit(0)
        
        if args.dump_state:
            dump_system_state(manager)
            sys.exit(0)
        
        # Main monitoring loop
        with GracefulExit() as exit_handler:
            logger.info("Starting MediaServer AutoSuspend monitoring...")
            monitor_loop(manager, exit_handler)
    
    except Exception as e:
        logger.exception("Unexpected error occurred")
        if args.dump_state or config.get('AUTO_DUMP_ON_ERROR'):
            dump_system_state(manager)
        sys.exit(1)

if __name__ == "__main__":
    main()
