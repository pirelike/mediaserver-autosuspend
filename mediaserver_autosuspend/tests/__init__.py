"""
MediaServer AutoSuspend Test Suite.

This package contains all tests for the MediaServer AutoSuspend application.
It provides common fixtures and configuration for testing.
"""

import os
import pytest
import logging
from typing import Dict, Any

# Disable logging during tests unless explicitly enabled
logging.getLogger('mediaserver_autosuspend').setLevel(logging.WARNING)

# Test configuration
TEST_CONFIG = {
    "JELLYFIN_API_KEY": "test-jellyfin-key",
    "JELLYFIN_URL": "http://localhost:8096",
    "RADARR_API_KEY": "test-radarr-key",
    "RADARR_URL": "http://localhost:7878",
    "SONARR_API_KEY": "test-sonarr-key",
    "SONARR_URL": "http://localhost:8989",
    "NEXTCLOUD_URL": "http://localhost:9000",
    "NEXTCLOUD_TOKEN": "test-nextcloud-token",
    "GRACE_PERIOD": 10,
    "CHECK_INTERVAL": 1,
    "LOG_LEVEL": "DEBUG",
    "SERVICES": {
        "jellyfin": True,
        "sonarr": True,
        "radarr": True,
        "nextcloud": True,
        "system": True
    }
}

@pytest.fixture
def config() -> Dict[str, Any]:
    """Fixture providing test configuration."""
    return TEST_CONFIG.copy()

@pytest.fixture
def temp_config_file(tmp_path):
    """Fixture providing temporary configuration file."""
    import json
    config_path = tmp_path / "config.json"
    with open(config_path, 'w') as f:
        json.dump(TEST_CONFIG, f)
    return str(config_path)

@pytest.fixture
def mock_responses():
    """Fixture for mocking HTTP responses."""
    import responses
    with responses.RequestsMock() as rsps:
        yield rsps

@pytest.fixture
def mock_filesystem(tmp_path):
    """Fixture providing temporary filesystem structure."""
    # Create standard directories
    (tmp_path / "etc/mediaserver-autosuspend").mkdir(parents=True)
    (tmp_path / "var/log/mediaserver-autosuspend").mkdir(parents=True)
    
    # Set up environment
    os.environ['TEST_ROOT'] = str(tmp_path)
    
    yield tmp_path
    
    # Clean up
    try:
        del os.environ['TEST_ROOT']
    except KeyError:
        pass

# Common test data
@pytest.fixture
def jellyfin_session():
    """Fixture providing sample Jellyfin session data."""
    return {
        "Id": "test-session",
        "UserName": "TestUser",
        "Client": "TestClient",
        "NowPlayingItem": {
            "Name": "Test Movie",
            "Type": "Movie"
        }
    }

@pytest.fixture
def sonarr_queue():
    """Fixture providing sample Sonarr queue data."""
    return {
        "totalRecords": 1,
        "records": [{
            "title": "Test Show",
            "status": "downloading"
        }]
    }

@pytest.fixture
def radarr_queue():
    """Fixture providing sample Radarr queue data."""
    return {
        "totalRecords": 1,
        "records": [{
            "title": "Test Movie",
            "status": "downloading"
        }]
    }

@pytest.fixture
def nextcloud_info():
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
        "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers",
        "requires_root: mark test as requiring root privileges"
    )
