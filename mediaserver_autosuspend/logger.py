"""
Logging configuration for MediaServer AutoSuspend.

This module provides advanced logging functionality including:
- Log rotation
- Multiple output formats
- Different handlers for different log levels
- Colored console output
- JSON formatting option
"""

import os
import sys
import json
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Union
from logging.handlers import RotatingFileHandler, SysLogHandler

# Custom log level for service status
SERVICE_STATUS = 25
logging.addLevelName(SERVICE_STATUS, 'SERVICE')

# ANSI color codes for console output
COLORS = {
    'DEBUG': '\033[36m',     # Cyan
    'INFO': '\033[32m',      # Green
    'SERVICE': '\033[35m',   # Magenta
    'WARNING': '\033[33m',   # Yellow
    'ERROR': '\033[31m',     # Red
    'CRITICAL': '\033[41m',  # Red background
    'RESET': '\033[0m'       # Reset
}

class ColoredFormatter(logging.Formatter):
    """Custom formatter for colored console output."""
    
    def __init__(self, fmt: str = None, datefmt: str = None, use_colors: bool = True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and sys.stderr.isatty()
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with optional color."""
        if self.use_colors and record.levelname in COLORS:
            record.levelname = (
                f"{COLORS[record.levelname]}"
                f"{record.levelname}"
                f"{COLORS['RESET']}"
            )
            if record.message:
                record.message = (
                    f"{COLORS[record.levelname.strip()]}"
                    f"{record.message}"
                    f"{COLORS['RESET']}"
                )
        return super().format(record)

class JsonFormatter(logging.Formatter):
    """Format log records as JSON."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Convert log record to JSON string."""
        log_data = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'message': record.getMessage(),
            'logger': record.name,
            'path': record.pathname,
            'line': record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        # Add extra fields if present
        if hasattr(record, 'extra_fields'):
            log_data.update(record.extra_fields)
        
        return json.dumps(log_data)

class LogManager:
    """Manage logging configuration and setup."""
    
    def __init__(
        self,
        config: Dict[str, Any],
        app_name: str = "autosuspend"
    ):
        """
        Initialize log manager.
        
        Args:
            config: Configuration dictionary
            app_name: Application name for logger
        """
        self.config = config
        self.app_name = app_name
        self.logger = logging.getLogger(app_name)
        
        # Get configuration values
        self.log_level = getattr(
            logging,
            config.get('LOG_LEVEL', 'INFO').upper()
        )
        self.log_file = config.get(
            'LOG_FILE',
            f"/var/log/{app_name}/{app_name}.log"
        )
        self.max_bytes = config.get('MAX_LOG_SIZE', 10 * 1024 * 1024)  # 10MB
        self.backup_count = config.get('LOG_BACKUP_COUNT', 5)
        self.use_json = config.get('LOG_JSON', False)
        self.use_syslog = config.get('USE_SYSLOG', False)
        self.use_colors = config.get('LOG_COLORS', True)
        
    def setup(self) -> None:
        """Set up logging configuration."""
        # Set base logging level
        self.logger.setLevel(self.log_level)
        
        # Remove any existing handlers
        self.logger.handlers = []
        
        # Add handlers
        self._setup_console_handler()
        self._setup_file_handler()
        
        if self.use_syslog:
            self._setup_syslog_handler()
        
        # Add service status logging method
        def service_status(
            self,
            msg: str,
            *args,
            **kwargs
        ) -> None:
            """Log service status messages."""
            self.log(SERVICE_STATUS, msg, *args, **kwargs)
        
        logging.Logger.service_status = service_status
    
    def _setup_console_handler(self) -> None:
        """Set up console (stderr) logging handler."""
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(self.log_level)
        
        # Use colored output for console
        formatter = ColoredFormatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            use_colors=self.use_colors
        )
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
    
    def _setup_file_handler(self) -> None:
        """Set up file logging handler with rotation."""
        # Create log directory if needed
        log_path = Path(self.log_file).parent
        log_path.mkdir(parents=True, exist_ok=True)
        
        file_handler = RotatingFileHandler(
            self.log_file,
            maxBytes=self.max_bytes,
            backupCount=self.backup_count
        )
        file_handler.setLevel(self.log_level)
        
        # Use JSON formatter if configured
        if self.use_json:
            formatter = JsonFormatter()
        else:
            formatter = logging.Formatter(
                fmt='%(asctime)s - [%(process)d] - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
    
    def _setup_syslog_handler(self) -> None:
        """Set up syslog logging handler."""
        try:
            syslog_handler = SysLogHandler(address='/dev/log')
            syslog_handler.setLevel(self.log_level)
            
            # Use basic formatter for syslog
            formatter = logging.Formatter(
                fmt='%(name)s[%(process)d]: %(levelname)s - %(message)s'
            )
            syslog_handler.setFormatter(formatter)
            self.logger.addHandler(syslog_handler)
        except Exception as e:
            sys.stderr.write(f"Warning: Could not set up syslog handler: {e}\n")
    
    def add_file_handler(
        self,
        filepath: str,
        level: Union[str, int] = 'DEBUG'
    ) -> None:
        """
        Add additional file handler.
        
        Args:
            filepath: Path to log file
            level: Logging level
        """
        handler = logging.FileHandler(filepath)
        handler.setLevel(level if isinstance(level, int) else getattr(logging, level))
        
        formatter = JsonFormatter() if self.use_json else logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
    
    def get_current_log_file(self) -> Optional[str]:
        """
        Get path of current log file.
        
        Returns:
            Path to current log file or None
        """
        for handler in self.logger.handlers:
            if isinstance(handler, (logging.FileHandler, RotatingFileHandler)):
                return handler.baseFilename
        return None

def setup_logging(
    config: Dict[str, Any],
    app_name: str = "autosuspend"
) -> logging.Logger:
    """
    Set up logging configuration.
    
    Args:
        config: Configuration dictionary
        app_name: Application name for logger
    
    Returns:
        Configured logger instance
    """
    manager = LogManager(config, app_name)
    manager.setup()
    return manager.logger
