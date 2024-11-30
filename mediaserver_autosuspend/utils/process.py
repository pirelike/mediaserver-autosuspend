"""
Process management utilities for MediaServer AutoSuspend.

This module provides utilities for process management and monitoring, including:
- Single instance enforcement
- Process information retrieval
- Process status checking
- Process discovery and management
- PID file handling
"""

import os
import sys
import signal
import logging
import subprocess
import psutil
from pathlib import Path
from typing import Optional, Dict, Any, List, Set, Union
from datetime import datetime

logger = logging.getLogger(__name__)

class ProcessError(Exception):
    """Base exception for process-related errors."""
    pass

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
            check=False
        )
        
        # Filter out our own PID and count remaining processes
        current_pid = os.getpid()
        other_pids = [
            pid for pid in result.stdout.strip().split('\n')
            if pid and int(pid) != current_pid
        ]
        
        if other_pids:
            logger.warning(
                f"Another instance is running (PIDs: {', '.join(other_pids)})"
            )
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error checking for other instances: {e}")
        return False

def get_process_info(pid: int) -> Optional[Dict[str, Any]]:
    """
    Get detailed information about a process.
    
    Args:
        pid: Process ID to query
        
    Returns:
        Dict containing process information or None if process not found
    """
    try:
        process = psutil.Process(pid)
        
        return {
            'pid': pid,
            'name': process.name(),
            'status': process.status(),
            'create_time': datetime.fromtimestamp(process.create_time()).isoformat(),
            'cpu_percent': process.cpu_percent(),
            'memory_percent': process.memory_percent(),
            'cmdline': process.cmdline(),
            'username': process.username(),
            'num_threads': process.num_threads(),
            'open_files': len(process.open_files()),
            'connections': len(process.connections()),
            'nice': process.nice(),
            'ppid': process.ppid(),
            'io_counters': process.io_counters()._asdict() if hasattr(process, 'io_counters') else None,
            'num_ctx_switches': process.num_ctx_switches()._asdict(),
            'memory_info': process.memory_info()._asdict(),
            'environment': get_process_environment(pid)
        }
        
    except psutil.NoSuchProcess:
        logger.debug(f"Process {pid} not found")
        return None
    except psutil.AccessDenied:
        logger.warning(f"Access denied when querying process {pid}")
        return None
    except Exception as e:
        logger.error(f"Error getting process info for PID {pid}: {e}")
        return None

def get_process_environment(pid: int) -> Dict[str, str]:
    """
    Get environment variables for a process.
    
    Args:
        pid: Process ID to query
        
    Returns:
        Dict of environment variables
    """
    try:
        with open(f"/proc/{pid}/environ", 'rb') as f:
            environ_data = f.read().decode('utf-8', errors='replace')
            return dict(
                item.split('=', 1)
                for item in environ_data.split('\0')
                if '=' in item
            )
    except (FileNotFoundError, PermissionError):
        return {}

def is_process_running(pid: int) -> bool:
    """
    Check if a process is still running.
    
    Args:
        pid: Process ID to check
        
    Returns:
        bool: True if process is running, False otherwise
    """
    try:
        process = psutil.Process(pid)
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
    except Exception as e:
        logger.error(f"Error checking process {pid}: {e}")
        return False

def find_processes_by_name(
    name: str,
    exact_match: bool = False
) -> List[Dict[str, Any]]:
    """
    Find all processes matching a name pattern.
    
    Args:
        name: Process name or pattern to search for
        exact_match: Whether to require exact name match
        
    Returns:
        List of matching process information dictionaries
    """
    matching_processes = []
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                pinfo = proc.info
                if exact_match:
                    if pinfo['name'] == name:
                        matching_processes.append(get_process_info(pinfo['pid']))
                else:
                    if name.lower() in pinfo['name'].lower():
                        matching_processes.append(get_process_info(pinfo['pid']))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
                
        return [p for p in matching_processes if p is not None]
        
    except Exception as e:
        logger.error(f"Error searching for processes: {e}")
        return []

def kill_process(
    pid: int,
    timeout: float = 5.0,
    force: bool = False
) -> bool:
    """
    Kill a process with optional timeout and force.
    
    Args:
        pid: Process ID to kill
        timeout: Seconds to wait for graceful termination
        force: Use SIGKILL instead of SIGTERM
        
    Returns:
        bool: True if process was killed successfully
    """
    try:
        process = psutil.Process(pid)
        
        if force:
            process.kill()  # SIGKILL
        else:
            process.terminate()  # SIGTERM
            
            try:
                process.wait(timeout=timeout)
            except psutil.TimeoutExpired:
                logger.warning(f"Process {pid} did not terminate within {timeout}s, using SIGKILL")
                process.kill()
        
        return True
        
    except psutil.NoSuchProcess:
        return True  # Process already gone
    except psutil.AccessDenied as e:
        logger.error(f"Permission denied killing process {pid}: {e}")
        return False
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

def write_pid_file(pid_file: Union[str, Path]) -> bool:
    """
    Write current process ID to a file.
    
    Args:
        pid_file: Path to PID file
        
    Returns:
        bool: True if successful
    """
    try:
        pid_path = Path(pid_file)
        pid_path.parent.mkdir(parents=True, exist_ok=True)
        
        pid = str(os.getpid())
        pid_path.write_text(pid)
        
        # Set appropriate permissions
        pid_path.chmod(0o644)
        
        return True
        
    except Exception as e:
        logger.error(f"Error writing PID file: {e}")
        return False

def remove_pid_file(pid_file: Union[str, Path]) -> bool:
    """
    Remove a PID file.
    
    Args:
        pid_file: Path to PID file
        
    Returns:
        bool: True if successful
    """
    try:
        pid_path = Path(pid_file)
        if pid_path.exists():
            pid_path.unlink()
        return True
    except Exception as e:
        logger.error(f"Error removing PID file: {e}")
        return False

def get_child_processes(pid: int) -> List[int]:
    """
    Get list of child process IDs for a given parent PID.
    
    Args:
        pid: Parent process ID
        
    Returns:
        List of child process IDs
    """
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        return [child.pid for child in children]
    except Exception as e:
        logger.error(f"Error getting child processes for {pid}: {e}")
        return []

def kill_process_tree(
    pid: int,
    timeout: float = 5.0,
    force: bool = False
) -> bool:
    """
    Kill a process and all its children.
    
    Args:
        pid: Parent process ID to kill
        timeout: Seconds to wait for graceful termination
        force: Use SIGKILL instead of SIGTERM
        
    Returns:
        bool: True if all processes were killed successfully
    """
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        
        # Kill children first
        for child in children:
            kill_process(child.pid, timeout, force)
            
        # Kill parent
        return kill_process(pid, timeout, force)
        
    except Exception as e:
        logger.error(f"Error killing process tree for {pid}: {e}")
        return False

def get_process_memory_usage(pid: int) -> Optional[Dict[str, int]]:
    """
    Get detailed memory usage information for a process.
    
    Args:
        pid: Process ID to query
        
    Returns:
        Dict containing memory usage details or None if process not found
    """
    try:
        process = psutil.Process(pid)
        memory_info = process.memory_info()
        
        return {
            'rss': memory_info.rss,  # Resident Set Size
            'vms': memory_info.vms,  # Virtual Memory Size
            'shared': memory_info.shared if hasattr(memory_info, 'shared') else None,
            'text': memory_info.text if hasattr(memory_info, 'text') else None,
            'lib': memory_info.lib if hasattr(memory_info, 'lib') else None,
            'data': memory_info.data if hasattr(memory_info, 'data') else None,
            'dirty': memory_info.dirty if hasattr(memory_info, 'dirty') else None
        }
        
    except Exception as e:
        logger.error(f"Error getting memory usage for process {pid}: {e}")
        return None
