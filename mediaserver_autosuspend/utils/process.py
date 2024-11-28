"""
Process management utilities for MediaServer AutoSuspend.

This module provides functions for process management, including:
- Single instance checking
- Process information retrieval
- Process status checking
"""

import os
import sys
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

def check_single_instance() -> bool:
    """
    Check if another instance of the script is running.
    
    Returns:
        bool: True if this is the only instance, False otherwise
    """
    script_name = Path(sys.argv[0]).name
    try:
        # Get list of matching processes
        result = subprocess.run(
            ['pgrep', '-f', script_name],
            capture_output=True,
            text=True,
            check=False  # Don't raise on non-zero exit
        )
        
        # Filter out our own PID and count remaining processes
        pids = [
            pid for pid in result.stdout.strip().split('\n')
            if pid and int(pid) != os.getpid()
        ]
        
        if pids:
            logger.warning(
                f"Another instance is running (PIDs: {', '.join(pids)})"
            )
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error checking for other instances: {e}")
        return False  # Assume another instance on error

def get_process_info(pid: int) -> Optional[Dict[str, Any]]:
    """
    Get detailed information about a process.
    
    Args:
        pid: Process ID to query
        
    Returns:
        Dictionary containing process information or None if process not found
    """
    try:
        # Check if process exists
        if not Path(f"/proc/{pid}").exists():
            return None
        
        # Get process command line
        with open(f"/proc/{pid}/cmdline", 'r') as f:
            cmdline = f.read().strip('\0').split('\0')
        
        # Get process status
        with open(f"/proc/{pid}/status", 'r') as f:
            status = dict(
                line.strip().split(':\t', 1)
                for line in f
                if ':\t' in line
            )
        
        # Get process environment
        try:
            with open(f"/proc/{pid}/environ", 'r') as f:
                environ = dict(
                    item.split('=', 1)
                    for item in f.read().split('\0')
                    if '=' in item
                )
        except PermissionError:
            environ = {}
        
        return {
            'pid': pid,
            'command': cmdline[0],
            'args': cmdline[1:],
            'name': status.get('Name', ''),
            'state': status.get('State', ''),
            'username': status.get('Uid', '').split()[0],
            'environment': environ
        }
        
    except Exception as e:
        logger.error(f"Error getting process info for PID {pid}: {e}")
        return None

def is_process_running(pid: int) -> bool:
    """
    Check if a process is still running.
    
    Args:
        pid: Process ID to check
        
    Returns:
        bool: True if process is running, False otherwise
    """
    try:
        # Check if process exists and is running
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we don't have permission to send signals
        return True

def find_processes_by_name(name: str) -> List[int]:
    """
    Find all processes matching a name pattern.
    
    Args:
        name: Process name or pattern to search for
        
    Returns:
        List of matching process IDs
    """
    try:
        result = subprocess.run(
            ['pgrep', '-f', name],
            capture_output=True,
            text=True,
            check=False
        )
        
        return [
            int(pid)
            for pid in result.stdout.strip().split('\n')
            if pid
        ]
        
    except Exception as e:
        logger.error(f"Error searching for processes: {e}")
        return []

def kill_process(pid: int, force: bool = False) -> bool:
    """
    Kill a process.
    
    Args:
        pid: Process ID to kill
        force: Use SIGKILL instead of SIGTERM
        
    Returns:
        bool: True if process was killed successfully
    """
    try:
        import signal
        os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
        return True
    except ProcessLookupError:
        return True  # Process already gone
    except Exception as e:
        logger.error(f"Error killing process {pid}: {e}")
        return False

def get_script_pid() -> int:
    """
    Get the current script's process ID.
    
    Returns:
        int: Current process ID
    """
    return os.getpid()

def write_pid_file(pid_file: str) -> bool:
    """
    Write current process ID to a file.
    
    Args:
        pid_file: Path to PID file
        
    Returns:
        bool: True if successful
    """
    try:
        pid = str(os.getpid())
        Path(pid_file).write_text(pid)
        return True
    except Exception as e:
        logger.error(f"Error writing PID file: {e}")
        return False
