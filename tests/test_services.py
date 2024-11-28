"""
Test suite for MediaServer AutoSuspend service checkers.
Tests all service checker implementations for proper functionality.
"""

import pytest
import responses
from unittest.mock import patch, Mock
from mediaserver_autosuspend.services import (
    JellyfinChecker,
    PlexChecker,
    SonarrChecker,
    RadarrChecker,
    NextcloudChecker,
    SystemChecker
)

@pytest.fixture
def config():
    """Fixture providing base test configuration."""
    return {
        # Jellyfin settings
        "JELLYFIN_API_KEY": "test-jellyfin-key",
        "JELLYFIN_URL": "http://localhost:8096",
        
        # Plex settings
        "PLEX_TOKEN": "test-plex-token",
        "PLEX_URL": "http://localhost:32400",
        "PLEX_MONITOR_TRANSCODING": True,
        
        # Sonarr settings
        "SONARR_API_KEY": "test-sonarr-key",
        "SONARR_URL": "http://localhost:8989",
        
        # Radarr settings
        "RADARR_API_KEY": "test-radarr-key",
        "RADARR_URL": "http://localhost:7878",
        
        # Nextcloud settings
        "NEXTCLOUD_URL": "http://localhost:9000",
        "NEXTCLOUD_TOKEN": "test-nextcloud-token"
    }

class TestJellyfinChecker:
    """Test suite for Jellyfin service checker."""
    
    def test_init_missing_config(self):
        """Test initialization with missing configuration."""
        with pytest.raises(Exception):
            JellyfinChecker({})
    
    @responses.activate
    def test_active_session(self, config):
        """Test detection of active Jellyfin session."""
        responses.add(
            responses.GET,
            f"{config['JELLYFIN_URL']}/Sessions",
            json=[{"NowPlayingItem": {"Name": "Test Movie"}}],
            status=200
        )
        
        checker = JellyfinChecker(config)
        assert checker.check_activity() is True
    
    @responses.activate
    def test_no_active_sessions(self, config):
        """Test when no active Jellyfin sessions exist."""
        responses.add(
            responses.GET,
            f"{config['JELLYFIN_URL']}/Sessions",
            json=[{"NowPlayingItem": None}],
            status=200
        )
        
        checker = JellyfinChecker(config)
        assert checker.check_activity() is False
    
    @responses.activate
    def test_connection_error(self, config):
        """Test handling of connection errors."""
        responses.add(
            responses.GET,
            f"{config['JELLYFIN_URL']}/Sessions",
            status=500
        )
        
        checker = JellyfinChecker(config)
        assert checker.check_activity() is False

class TestPlexChecker:
    """Test suite for Plex service checker."""
    
    def test_init_missing_config(self):
        """Test initialization with missing configuration."""
        with pytest.raises(Exception):
            PlexChecker({})
    
    @responses.activate
    def test_active_session(self, config):
        """Test detection of active Plex session."""
        responses.add(
            responses.GET,
            f"{config['PLEX_URL']}/status/sessions",
            json={
                "MediaContainer": {
                    "Metadata": [{
                        "title": "Test Movie",
                        "Player": {"state": "playing"}
                    }]
                }
            },
            status=200
        )
        
        checker = PlexChecker(config)
        assert checker.check_activity() is True
    
    @responses.activate
    def test_active_transcoding(self, config):
        """Test detection of active transcoding."""
        responses.add(
            responses.GET,
            f"{config['PLEX_URL']}/status/sessions",
            json={"MediaContainer": {"Metadata": []}},
            status=200
        )
        responses.add(
            responses.GET,
            f"{config['PLEX_URL']}/transcode/sessions",
            json={"MediaContainer": {"Metadata": [{"title": "Test"}]}},
            status=200
        )
        
        checker = PlexChecker(config)
        assert checker.check_activity() is True

class TestSonarrChecker:
    """Test suite for Sonarr service checker."""
    
    def test_init_missing_config(self):
        """Test initialization with missing configuration."""
        with pytest.raises(Exception):
            SonarrChecker({})
    
    @responses.activate
    def test_active_downloads(self, config):
        """Test detection of active Sonarr downloads."""
        responses.add(
            responses.GET,
            f"{config['SONARR_URL']}/api/v3/queue",
            json={"totalRecords": 1},
            status=200
        )
        
        checker = SonarrChecker(config)
        assert checker.check_activity() is True
    
    @responses.activate
    def test_no_downloads(self, config):
        """Test when no active Sonarr downloads exist."""
        responses.add(
            responses.GET,
            f"{config['SONARR_URL']}/api/v3/queue",
            json={"totalRecords": 0},
            status=200
        )
        
        checker = SonarrChecker(config)
        assert checker.check_activity() is False

class TestRadarrChecker:
    """Test suite for Radarr service checker."""
    
    def test_init_missing_config(self):
        """Test initialization with missing configuration."""
        with pytest.raises(Exception):
            RadarrChecker({})
    
    @responses.activate
    def test_active_downloads(self, config):
        """Test detection of active Radarr downloads."""
        responses.add(
            responses.GET,
            f"{config['RADARR_URL']}/api/v3/queue",
            json={"totalRecords": 1},
            status=200
        )
        
        checker = RadarrChecker(config)
        assert checker.check_activity() is True
    
    @responses.activate
    def test_no_downloads(self, config):
        """Test when no active Radarr downloads exist."""
        responses.add(
            responses.GET,
            f"{config['RADARR_URL']}/api/v3/queue",
            json={"totalRecords": 0},
            status=200
        )
        
        checker = RadarrChecker(config)
        assert checker.check_activity() is False

class TestNextcloudChecker:
    """Test suite for Nextcloud service checker."""
    
    def test_init_missing_config(self):
        """Test initialization with missing configuration."""
        with pytest.raises(Exception):
            NextcloudChecker({})
    
    @responses.activate
    def test_active_users(self, config):
        """Test detection of active Nextcloud users."""
        responses.add(
            responses.GET,
            f"{config['NEXTCLOUD_URL']}/ocs/v2.php/apps/serverinfo/api/v1/info",
            json={
                "ocs": {
                    "data": {
                        "activeUsers": {"last5minutes": 1},
                        "system": {"cpuload": [0.1, 0.2, 0.3]}
                    }
                }
            },
            status=200
        )
        
        checker = NextcloudChecker(config)
        assert checker.check_activity() is True

class TestSystemChecker:
    """Test suite for System service checker."""
    
    @patch('subprocess.check_output')
    def test_active_users(self, mock_check_output, config):
        """Test detection of logged-in users."""
        mock_check_output.return_value = b"user1 pts/0\nuser2 pts/1\n"
        
        checker = SystemChecker(config)
        assert checker.check_activity() is True
    
    @patch('subprocess.check_output')
    def test_no_users(self, mock_check_output, config):
        """Test when no users are logged in."""
        mock_check_output.return_value = b""
        
        checker = SystemChecker(config)
        assert checker.check_activity() is False
    
    @patch('subprocess.check_output')
    def test_command_error(self, mock_check_output, config):
        """Test handling of command execution errors."""
        mock_check_output.side_effect = Exception("Command failed")
        
        checker = SystemChecker(config)
        assert checker.check_activity() is False
