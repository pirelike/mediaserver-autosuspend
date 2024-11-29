"""
MediaServer AutoSuspend Test Suite
--------------------------------

This package contains the test suite for the MediaServer AutoSuspend application.
It provides test configuration, fixtures, and utilities used across all test modules.
"""

import os
import sys
import json
import pytest
import logging
from pathlib import Path
from typing import Dict, Any, Generator, Optional
from unittest.mock import MagicMock

# Ensure mediaserver_autosuspend package is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure test logging
logging.getLogger('mediaserver_autosuspend').setLevel(logging.WARNING)

# Base test configuration matching user's config structure
BASE_TEST_CONFIG = {
    "SERVICES": {
        "jellyfin": True,
        "plex": False,
        "sonarr": True,
        "radarr": True,
        "nextcloud": True,
        "system": True
    },

    "JELLYFIN": {
        "API_KEY": "test-jellyfin-api-key",
        "URL": "http://localhost:8096",
        "TIMEOUT": 10
    },

    "PLEX": {
        "TOKEN": "test-plex-token",
        "URL": "http://localhost:32400",
        "MONITOR_TRANSCODING": True,
        "IGNORE_PAUSED": False,
        "TIMEOUT": 10
    },

    "SONARR": {
        "API_KEY": "test-sonarr-api-key",
        "URL": "http://localhost:8989",
        "TIMEOUT": 10
    },

    "RADARR": {
        "API_KEY": "test-radarr-api-key",
        "URL": "http://localhost:7878",
        "TIMEOUT": 10
    },

    "NEXTCLOUD": {
        "URL": "http://localhost:9000",
        "TOKEN": "test-nextcloud-token",
        "CPU_THRESHOLD": 0.5,
        "TIMEOUT": 10
    },

    "SYSTEM": {
        "IGNORE_USERS": [],
        "LOAD_THRESHOLD": 0.5,
        "CHECK_LOAD": True
    },

    "TIMING": {
        "GRACE_PERIOD": 2,  # Shortened for testing
        "CHECK_INTERVAL": 1,
        "MIN_UPTIME": 1,
        "SUSPENSION_COOLDOWN": 5,
        "MIN_CHECK_INTERVAL": 1
    },

    "SCHEDULE": {
        "WAKE_UP_TIMES": [
            "07:00",
            "13:00",
            "19:00"
        ],
        "TIMEZONE": "UTC"
    },

    "HOOKS": {
        "DIR": "/etc/mediaserver-autosuspend/hooks"
    },

    "LOGGING": {
        "LEVEL": "DEBUG",
        "FILE": "/var/log/mediaserver-autosuspend/mediaserver-autosuspend.log",
        "MAX_SIZE": 10485760,
        "BACKUP_COUNT": 5,
        "JSON": False,
        "USE_SYSLOG": False,
        "COLORS": True
    },

    "DEBUG": {
        "MODE": True,
        "AUTO_DUMP_ON_ERROR": False
    }
}

@pytest.fixture
def config() -> Dict[str, Any]:
    """Fixture providing base test configuration."""
    return BASE_TEST_CONFIG.copy()

@pytest.fixture
def temp_dir(tmp_path) -> Path:
    """Fixture providing temporary directory for test files."""
    return tmp_path

@pytest.fixture
def config_file(temp_dir: Path, config: Dict[str, Any]) -> Path:
    """Fixture providing temporary configuration file."""
    config_path = temp_dir / "config.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    return config_path

@pytest.fixture
def mock_filesystem(temp_dir: Path) -> Path:
    """Fixture providing mock filesystem structure."""
    # Create standard directories
    (temp_dir / "etc/mediaserver-autosuspend/hooks").mkdir(parents=True)
    (temp_dir / "var/log/mediaserver-autosuspend").mkdir(parents=True)
    
    # Create hook directories
    hooks_dir = temp_dir / "etc/mediaserver-autosuspend/hooks"
    (hooks_dir / "pre-suspend.d").mkdir()
    (hooks_dir / "post-suspend.d").mkdir()
    
    return temp_dir

# Service test data fixtures
@pytest.fixture
def jellyfin_session() -> Dict[str, Any]:
    """Fixture providing sample Jellyfin session data."""
    return {
        "Id": "test-session",
        "UserName": "TestUser",
        "Client": "TestClient",
        "DeviceName": "TestDevice",
        "NowPlayingItem": {
            "Name": "Test Movie",
            "Type": "Movie",
            "Id": "test-item"
        },
        "PlayState": {
            "PositionTicks": 0,
            "IsPaused": False,
            "IsPlaying": True
        }
    }

@pytest.fixture
def sonarr_queue() -> Dict[str, Any]:
    """Fixture providing sample Sonarr queue data."""
    return {
        "totalRecords": 1,
        "records": [{
            "id": 1,
            "title": "Test Show",
            "status": "downloading",
            "progress": 50.0,
            "estimatedCompletionTime": "2024-01-01T00:00:00Z"
        }]
    }

@pytest.fixture
def radarr_queue() -> Dict[str, Any]:
    """Fixture providing sample Radarr queue data."""
    return {
        "totalRecords": 1,
        "records": [{
            "id": 1,
            "title": "Test Movie",
            "status": "downloading",
            "progress": 50.0,
            "estimatedCompletionTime": "2024-01-01T00:00:00Z"
        }]
    }

@pytest.fixture
def nextcloud_info() -> Dict[str, Any]:
    """Fixture providing sample Nextcloud system info."""
    return {
        "ocs": {
            "data": {
                "activeUsers": {
                    "last5minutes": 1
                },
                "system": {
                    "cpuload": [0.1, 0.2, 0.3]
                }
            }
        }
    }

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration test requiring service endpoints"
    )
    config.addinivalue_line(
        "markers",
        "requires_root: mark test as requiring root privileges"
    )
    config.addinivalue_line(
        "markers",
        "slow: mark test as slow running"
    )
