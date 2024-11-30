"""
MediaServer AutoSuspend Utilities Package
---------------------------------------

This package provides utility functions and helper classes used throughout the 
MediaServer AutoSuspend application. It includes comprehensive process management utilities,
system monitoring, and state management functionality.

Features:
- Process management and monitoring
- Single instance enforcement
- PID file handling
- Memory usage tracking
- Process tree management

Example:
    >>> from mediaserver_autosuspend.utils import check_single_instance, get_process_info
    >>> if check_single_instance():
    ...     print("No other instances running")
    ...     info = get_process_info(get_script_pid())
    ...     print(f"Current process info: {info}")
"""

import logging
import shutil
from typing import Dict, Any, Optional, List, Union
from pathlib import Path

# Import all process management utilities
from .process import (
    ProcessError,
    check_single_instance,
    get_process_info,
    get_process_environment,
    is_process_running,
    find_processes_by_name,
    kill_process,
    get_script_pid,
    write_pid_file,
    remove_pid_file,
    get_child_processes,
    kill_process_tree,
    get_process_memory_usage
)

# Set up package-level logger
logger = logging.getLogger(__name__)

# Define package exports
__all__ = [
    # Exceptions
    'ProcessError',

    # Process Management
    'check_single_instance',
    'get_process_info',
    'get_process_environment',
    'is_process_running',
    'find_processes_by_name',
    'kill_process',
    'get_script_pid',
    'write_pid_file',
    'remove_pid_file',

    # Process Tree Management
    'get_child_processes',
    'kill_process_tree',

    # Memory Management
    'get_process_memory_usage',
]

def init_utils() -> Dict[str, bool]:
    """
    Initialize utilities package and verify dependencies.
    
    Returns:
        Dict[str, bool]: Status of required system commands
    """
    logger.debug("Initializing utilities package")
    
    # Check required system commands
    required_commands = {
        'systemctl': False,
        'who': False,
        'pgrep': False,
        'rtcwake': False
    }
    
    for cmd in required_commands:
        if shutil.which(cmd):
            required_commands[cmd] = True
        else:
            logger.warning(f"Required system command not found: {cmd}")
    
    # Check psutil availability
    try:
        import psutil
        required_commands['psutil'] = True
    except ImportError:
        logger.error("psutil package not found - process management will be limited")
        required_commands['psutil'] = False
    
    return required_commands

# Initialize package
SYSTEM_STATUS = init_utils()
