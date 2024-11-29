"""
MediaServer AutoSuspend Utilities Package
---------------------------------------

This package provides utility functions and helper classes used throughout the 
MediaServer AutoSuspend application. It includes process management utilities,
file system operations, and other shared functionality.

Available utilities:
- Process management (check_single_instance, get_process_info, etc.)
- System state monitoring
- File operations and path management

Example:
    >>> from mediaserver_autosuspend.utils import check_single_instance
    >>> if check_single_instance():
    ...     print("No other instances running")
"""

import logging
from typing import Dict, Any, Optional

# Import all process management utilities
from mediaserver_autosuspend.utils.process import (
    check_single_instance,
    get_process_info,
    is_process_running,
    find_processes_by_name,
    kill_process,
    get_script_pid,
    write_pid_file
)

# Set up package-level logger
logger = logging.getLogger(__name__)

# Define package exports
__all__ = [
    # Process management
    'check_single_instance',
    'get_process_info',
    'is_process_running',
    'find_processes_by_name',
    'kill_process',
    'get_script_pid',
    'write_pid_file',
]

def dump_system_state(manager: Any) -> Optional[str]:
    """
    Dump current system state for debugging purposes.
    
    Args:
        manager: SuspensionManager instance
        
    Returns:
        Optional[str]: Path to dump file if successful, None otherwise
    """
    try:
        from datetime import datetime
        import json
        import os
        
        # Create dump directory if needed
        dump_dir = os.path.expanduser('~/.local/share/mediaserver-autosuspend/dumps')
        os.makedirs(dump_dir, exist_ok=True)
        
        # Generate dump filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        dump_file = os.path.join(dump_dir, f'state_dump_{timestamp}.json')
        
        # Collect system state
        state = {
            'timestamp': timestamp,
            'service_status': manager.get_status_summary(),
            'uptime': manager._get_uptime(),
            'last_suspension': (
                manager.last_suspension.isoformat()
                if manager.last_suspension else None
            ),
            'suspension_count': manager.suspension_count,
            'process_info': get_process_info(get_script_pid())
        }
        
        # Write dump file
        with open(dump_file, 'w') as f:
            json.dump(state, f, indent=2)
            
        logger.info(f"System state dumped to {dump_file}")
        return dump_file
        
    except Exception as e:
        logger.error(f"Failed to dump system state: {e}")
        return None

def init_utils() -> None:
    """Initialize utilities package and verify dependencies."""
    logger.debug("Initializing utilities package")
    
    # Ensure required system commands are available
    required_commands = ['systemctl', 'who', 'pgrep']
    missing_commands = []
    
    import shutil
    for cmd in required_commands:
        if not shutil.which(cmd):
            missing_commands.append(cmd)
    
    if missing_commands:
        logger.warning(
            f"Missing required system commands: {', '.join(missing_commands)}"
        )

# Initialize package
init_utils()
