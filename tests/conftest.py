"""
pytest configuration and fixtures for MediaServer AutoSuspend tests.

This module provides shared fixtures and configuration for the test suite,
including mock services, configuration templates, and filesystem setup.
"""

import os
import json
import pytest
import tempfile
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from unittest.mock import Mock

# Import necessary components
from mediaserver_autosuspend import (
    SuspensionManager,
    ServiceChecker,
    JellyfinChecker,
    PlexChecker,
    SonarrChecker,
    RadarrChecker,
    NextcloudChecker,
    SystemChecker
)

# Disable logging during tests unless explicitly enabled
logging.getLogger('mediaserver_autosuspend').setLevel(logging.WARNING)

# Test configuration template
TEST_CONFIG = {
    "SERVICES": {
        "jellyfin": True,
        "plex": False,
        "sonarr": True,
        "radarr": True,
        "nextcloud": True,
        "system": True
    },
    "JELLYFIN_API_KEY": "test-jellyfin-key",
    "JELLYFIN_URL": "http://localhost:8096",
    "PLEX_TOKEN": "test-plex-token",
    "PLEX_URL": "http://localhost:32400",
    "PLEX_MONITOR_TRANSCODING": True,
    "PLEX_IGNORE_PAUSED": False,
    "SONARR_API_KEY": "test-sonarr-key",
    "SONARR_URL": "http://localhost:8989",
    "RADARR_API_KEY": "test-radarr-key",
    "RADARR_URL": "http://localhost:7878",
    "NEXTCLOUD_URL": "http://localhost:9000",
    "NEXTCLOUD_TOKEN": "test-nextcloud-token",
    "NEXTCLOUD_CPU_THRESHOLD": 0.5,
    "GRACE_PERIOD": 10,
    "CHECK_INTERVAL": 1,
    "MIN_UPTIME": 300,
    "SUSPENSION_COOLDOWN": 1800,
    "WAKE_UP_TIMES": ["07:00", "13:00", "19:00"],
    "TIMEZONE": "UTC",
    "LOG_LEVEL": "DEBUG",
    "LOG_FILE": "/var/log/mediaserver-autosuspend/test.log",
    "HOOKS_DIR": "/etc/mediaserver-autosuspend/hooks"
}

# Mock service responses
MOCK_RESPONSES = {
    "jellyfin_session": {
        "NowPlayingItem": {"Name": "Test Movie"},
        "UserName": "TestUser",
        "PlayState": {"IsPaused": False, "IsPlaying": True}
    },
    "plex_session": {
        "MediaContainer": {
            "Metadata": [{
                "Player": {"state": "playing"},
                "User": {"title": "TestUser"},
                "title": "Test Movie"
            }]
        }
    },
    "sonarr_queue": {
        "records": [{
            "title": "Test Show",
            "status": "downloading"
        }]
    },
    "radarr_queue": {
        "records": [{
            "title": "Test Movie",
            "status": "downloading"
        }]
    },
    "nextcloud_info": {
        "ocs": {
            "data": {
                "system": {
                    "cpuload": [0.1, 0.5, 0.3]
                }
            }
        }
    }
}

class MockServiceChecker(ServiceChecker):
    """Mock service checker for testing."""
    
    def __init__(self, config: Dict[str, Any], is_active: bool = False):
        super().__init__(config)
        self._is_active = is_active
        self.check_count = 0
    
    def check_activity(self) -> bool:
        self.check_count += 1
        return self._is_active
    
    def set_active(self, state: bool) -> None:
        self._is_active = state

@pytest.fixture
def config() -> Dict[str, Any]:
    """Fixture providing test configuration."""
    return TEST_CONFIG.copy()

@pytest.fixture
def mock_responses() -> Dict[str, Any]:
    """Fixture providing mock API responses."""
    return MOCK_RESPONSES.copy()

@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Fixture providing temporary directory."""
    return tmp_path

@pytest.fixture
def temp_config_file(temp_dir: Path, config: Dict[str, Any]) -> Path:
    """Fixture providing temporary configuration file."""
    config_file = temp_dir / "config.json"
    config_file.write_text(json.dumps(config))
    return config_file

@pytest.fixture
def mock_services() -> Dict[str, MockServiceChecker]:
    """Fixture providing mock service checkers."""
    return {
        "jellyfin": MockServiceChecker(TEST_CONFIG, False),
        "sonarr": MockServiceChecker(TEST_CONFIG, False),
        "radarr": MockServiceChecker(TEST_CONFIG, False),
        "nextcloud": MockServiceChecker(TEST_CONFIG, False),
        "system": MockServiceChecker(TEST_CONFIG, False)
    }

@pytest.fixture
def suspension_manager(config: Dict[str, Any], mock_services: Dict[str, MockServiceChecker]) -> SuspensionManager:
    """Fixture providing configured SuspensionManager."""
    return SuspensionManager(config, mock_services)

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

@pytest.fixture
def mock_process():
    """Fixture providing mock process utilities."""
    class MockProcess:
        def __init__(self):
            self.pid = 12345
            self.returncode = 0
        
        def kill(self):
            pass
        
        def terminate(self):
            pass
        
        def wait(self, timeout=None):
            pass
    
    return MockProcess()

@pytest.fixture
def mock_subprocess(monkeypatch):
    """Fixture providing mock subprocess functionality."""
    class MockSubprocess:
        def __init__(self):
            self.commands = []
            self.returncode = 0
        
        def run(self, cmd, *args, **kwargs):
            self.commands.append(cmd)
            mock = Mock()
            mock.returncode = self.returncode
            return mock
        
        def check_output(self, cmd, *args, **kwargs):
            self.commands.append(cmd)
            return b""
    
    mock_subprocess = MockSubprocess()
    monkeypatch.setattr("subprocess.run", mock_subprocess.run)
    monkeypatch.setattr("subprocess.check_output", mock_subprocess.check_output)
    return mock_subprocess

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers",
        "requires_root: mark test as requiring root privileges"
    )
    config.addinivalue_line(
        "markers",
        "slow: mark test as slow running"
    )

@pytest.fixture(autouse=True)
def _setup_testing_environment(monkeypatch):
    """Automatically set up testing environment for all tests."""
    # Set testing environment variables
    monkeypatch.setenv("TESTING", "true")
    
    # Ensure predictable timezone
    monkeypatch.setenv("TZ", "UTC")
    
    # Disable actual system commands
    monkeypatch.setattr("os.system", lambda x: 0)
    
    yield
