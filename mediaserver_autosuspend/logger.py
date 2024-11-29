"""
Logging configuration for MediaServer AutoSuspend.

This module provides a flexible logging system with features including:
- File logging with rotation
- Console output with optional colors
- Syslog integration
- JSON formatting
- Custom log levels for service status
"""

import os
import sys
import json
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Union

# Define custom log level for service status
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
    
    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None, use_colors: bool = True):
        """
        Initialize the colored formatter.
        
        Args:
            fmt: Log message format string
            datefmt: Date format string
            use_colors: Whether to enable colored output
        """
        super().__init__(fmt, datefmt)
        # Only use colors if output is to a terminal
        self.use_colors = use_colors and sys.stderr.isatty()
    
    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with optional color."""
        if self.use_colors and record.levelname in COLORS:
            # Add color to level name
            color = COLORS[record.levelname]
            reset = COLORS['RESET']
            record.levelname = f"{color}{record.levelname}{reset}"
            
            # Add color to message for easier visual scanning
            if hasattr(record, 'msg'):
                record.msg = f"{color}{record.msg}{reset}"
        
        return super().format(record)

class JsonFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""
    
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
        
        # Include exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        # Include any extra fields
        if hasattr(record, 'extra_fields'):
            log_data.update(record.extra_fields)
        
        return json.dumps(log_data)

class LogManager:
    """Manages logging configuration and setup."""
    
    def __init__(
        self,
        config: Dict[str, Any],
        app_name: str = "mediaserver-autosuspend"
    ):
        """
        Initialize the log manager.
        
        Args:
            config: Configuration dictionary with logging settings
            app_name: Application name for logger identification
        """
        self.config = config
        self.app_name = app_name
        self.logger = logging.getLogger(app_name)
        
        # Extract configuration values
        self.log_level = getattr(logging, config.get('LOG_LEVEL', 'INFO').upper())
        self.log_file = config.get('LOG_FILE', f"/var/log/{app_name}/{app_name}.log")
        self.max_bytes = config.get('MAX_LOG_SIZE', 10 * 1024 * 1024)  # 10MB default
        self.backup_count = config.get('LOG_BACKUP_COUNT', 5)
        self.use_json = config.get('LOG_JSON', False)
        self.use_syslog = config.get('USE_SYSLOG', False)
        self.use_colors = config.get('LOG_COLORS', True)
    
    def setup(self) -> None:
        """Set up logging configuration with all configured handlers."""
        # Set base logging level
        self.logger.setLevel(self.log_level)
        
        # Remove any existing handlers
        self.logger.handlers = []
        
        # Add configured handlers
        self._setup_console_handler()
        self._setup_file_handler()
        
        if self.use_syslog:
            self._setup_syslog_handler()
        
        # Add service status logging method
        def service_status(
            self: logging.Logger,
            msg: str,
            *args: Any,
            **kwargs: Any
        ) -> None:
            """Log service status messages at custom level."""
            self.log(SERVICE_STATUS, msg, *args, **kwargs)
        
        # Add method to Logger class
        logging.Logger.service_status = service_status  # type: ignore
    
    def _setup_console_handler(self) -> None:
        """Set up console (stderr) logging handler."""
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(self.log_level)
        
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
        
        file_handler = logging.handlers.RotatingFileHandler(
            self.log_file,
            maxBytes=self.max_bytes,
            backupCount=self.backup_count
        )
        file_handler.setLevel(self.log_level)
        
        # Use JSON formatter if configured, otherwise standard formatter
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
            syslog_handler = logging.handlers.SysLogHandler(address='/dev/log')
            syslog_handler.setLevel(self.log_level)
            
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
        Add an additional file handler.
        
        Args:
            filepath: Path to log file
            level: Logging level (name or number)
        """
        handler = logging.FileHandler(filepath)
        handler.setLevel(
            level if isinstance(level, int) else getattr(logging, level)
        )
        
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
            Path to current log file or None if no file handler
        """
        for handler in self.logger.handlers:
            if isinstance(handler, (logging.FileHandler, logging.handlers.RotatingFileHandler)):
                return handler.baseFilename
        return None

def setup_logging(
    config: Dict[str, Any],
    app_name: str = "mediaserver-autosuspend"
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
