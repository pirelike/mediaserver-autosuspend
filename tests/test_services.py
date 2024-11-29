"""
Test suite for MediaServer AutoSuspend service checkers.

This module provides comprehensive testing for all service checker implementations,
including Jellyfin, Plex, Sonarr, Radarr, Nextcloud, and System checkers.
"""

import pytest
import responses
import subprocess
from unittest.mock import patch, Mock
from datetime import datetime

from mediaserver_autosuspend.services import (
    ServiceChecker,
    ServiceCheckError,
    ServiceConfigError,
    ServiceConnectionError,
    JellyfinChecker,
    PlexChecker,
    SonarrChecker,
    RadarrChecker,
    NextcloudChecker,
    SystemChecker
)

# Base test class for common functionality
class BaseServiceTest:
    """Base class for service checker tests."""
    
    def test_init_missing_config(self, config):
        """Test initialization with missing configuration."""
        with pytest.raises(ServiceConfigError):
            self.checker_class({})

    def test_statistics_tracking(self, config):
        """Test service statistics tracking functionality."""
        checker = self.checker_class(config)
        
        # Initial state
        assert checker.total_checks == 0
        assert checker.active_checks == 0
        assert checker.error_count == 0
        
        # Simulate successful check
        with patch.object(checker, 'check_activity', return_value=True):
            assert checker.is_active() is True
            assert checker.total_checks == 1
            assert checker.active_checks == 1
            assert checker.error_count == 0
        
        # Simulate failed check
        with patch.object(checker, 'check_activity', side_effect=Exception("Test error")):
            assert checker.is_active() is False
            assert checker.total_checks == 2
            assert checker.active_checks == 1
            assert checker.error_count == 1

    def test_rate_limiting(self, config):
        """Test service check rate limiting."""
        checker = self.checker_class(config)
        checker._min_check_interval = 1  # 1 second interval
        
        # First check should always proceed
        with patch.object(checker, 'check_activity', return_value=True):
            assert checker.is_active() is True
        
        # Immediate second check should use cached result
        with patch.object(checker, 'check_activity', return_value=False):
            assert checker.is_active() is True

class TestJellyfinChecker(BaseServiceTest):
    """Test suite for Jellyfin service checker."""
    
    checker_class = JellyfinChecker

    @responses.activate
    def test_active_session(self, config):
        """Test detection of active Jellyfin session."""
        responses.add(
            responses.GET,
            f"{config['JELLYFIN_URL']}/Sessions",
            json=[{
                "NowPlayingItem": {"Name": "Test Movie"},
                "PlayState": {
                    "IsPaused": False,
                    "IsPlaying": True
                }
            }],
            status=200
        )
        
        checker = JellyfinChecker(config)
        assert checker.check_activity() is True

    @responses.activate
    def test_paused_session(self, config):
        """Test handling of paused Jellyfin session."""
        responses.add(
            responses.GET,
            f"{config['JELLYFIN_URL']}/Sessions",
            json=[{
                "NowPlayingItem": {"Name": "Test Movie"},
                "PlayState": {
                    "IsPaused": True,
                    "IsPlaying": False
                }
            }],
            status=200
        )
        
        checker = JellyfinChecker(config)
        assert checker.check_activity() is False

    @responses.activate
    def test_active_tasks(self, config):
        """Test detection of active Jellyfin tasks."""
        # Mock empty sessions
        responses.add(
            responses.GET,
            f"{config['JELLYFIN_URL']}/Sessions",
            json=[],
            status=200
        )
        
        # Mock active tasks
        responses.add(
            responses.GET,
            f"{config['JELLYFIN_URL']}/ScheduledTasks/Running",
            json=[{"Name": "Test Task"}],
            status=200
        )
        
        checker = JellyfinChecker(config)
        assert checker.check_activity() is True

class TestPlexChecker(BaseServiceTest):
    """Test suite for Plex service checker."""
    
    checker_class = PlexChecker

    @responses.activate
    def test_active_session(self, config):
        """Test detection of active Plex session."""
        responses.add(
            responses.GET,
            f"{config['PLEX_URL']}/status/sessions",
            json={
                "MediaContainer": {
                    "Metadata": [{
                        "Player": {"state": "playing"},
                        "User": {"title": "TestUser"},
                        "title": "Test Movie"
                    }]
                }
            },
            status=200
        )
        
        checker = PlexChecker(config)
        assert checker.check_activity() is True

    @responses.activate
    def test_transcoding_session(self, config):
        """Test detection of active Plex transcoding."""
        # Mock empty playback sessions
        responses.add(
            responses.GET,
            f"{config['PLEX_URL']}/status/sessions",
            json={"MediaContainer": {"Metadata": []}},
            status=200
        )
        
        # Mock active transcoding
        responses.add(
            responses.GET,
            f"{config['PLEX_URL']}/transcode/sessions",
            json={
                "MediaContainer": {
                    "Metadata": [{"title": "Test Transcode"}]
                }
            },
            status=200
        )
        
        checker = PlexChecker(config)
        checker.monitor_transcoding = True
        assert checker.check_activity() is True

class TestSonarrChecker(BaseServiceTest):
    """Test suite for Sonarr service checker."""
    
    checker_class = SonarrChecker

    @responses.activate
    def test_active_downloads(self, config):
        """Test detection of active Sonarr downloads."""
        responses.add(
            responses.GET,
            f"{config['SONARR_URL']}/api/v3/queue",
            json={
                "records": [{
                    "title": "Test Show",
                    "status": "downloading"
                }]
            },
            status=200
        )
        
        checker = SonarrChecker(config)
        assert checker.check_activity() is True

    @responses.activate
    def test_multiple_queue_items(self, config):
        """Test handling of multiple Sonarr queue items."""
        responses.add(
            responses.GET,
            f"{config['SONARR_URL']}/api/v3/queue",
            json={
                "records": [
                    {"title": "Show 1", "status": "downloading"},
                    {"title": "Show 2", "status": "queued"},
                    {"title": "Show 3", "status": "completed"}
                ]
            },
            status=200
        )
        
        checker = SonarrChecker(config)
        assert checker.check_activity() is True

class TestRadarrChecker(BaseServiceTest):
    """Test suite for Radarr service checker."""
    
    checker_class = RadarrChecker

    @responses.activate
    def test_active_downloads(self, config):
        """Test detection of active Radarr downloads."""
        responses.add(
            responses.GET,
            f"{config['RADARR_URL']}/api/v3/queue",
            json={
                "records": [{
                    "title": "Test Movie",
                    "status": "downloading"
                }]
            },
            status=200
        )
        
        checker = RadarrChecker(config)
        assert checker.check_activity() is True

    @responses.activate
    def test_multiple_queue_items(self, config):
        """Test handling of multiple Radarr queue items."""
        responses.add(
            responses.GET,
            f"{config['RADARR_URL']}/api/v3/queue",
            json={
                "records": [
                    {"title": "Movie 1", "status": "downloading"},
                    {"title": "Movie 2", "status": "queued"},
                    {"title": "Movie 3", "status": "completed"}
                ]
            },
            status=200
        )
        
        checker = RadarrChecker(config)
        assert checker.check_activity() is True

class TestNextcloudChecker(BaseServiceTest):
    """Test suite for Nextcloud service checker."""
    
    checker_class = NextcloudChecker

    @responses.activate
    def test_high_cpu_load(self, config):
        """Test detection of high Nextcloud CPU load."""
        responses.add(
            responses.GET,
            f"{config['NEXTCLOUD_URL']}/ocs/v2.php/apps/serverinfo/api/v1/info",
            json={
                "ocs": {
                    "data": {
                        "system": {
                            "cpuload": [0.2, 0.8, 0.5]
                        }
                    }
                }
            },
            status=200
        )
        
        checker = NextcloudChecker(config)
        checker.cpu_threshold = 0.5
        assert checker.check_activity() is True

    @responses.activate
    def test_low_cpu_load(self, config):
        """Test handling of low Nextcloud CPU load."""
        responses.add(
            responses.GET,
            f"{config['NEXTCLOUD_URL']}/ocs/v2.php/apps/serverinfo/api/v1/info",
            json={
                "ocs": {
                    "data": {
                        "system": {
                            "cpuload": [0.1, 0.2, 0.3]
                        }
                    }
                }
            },
            status=200
        )
        
        checker = NextcloudChecker(config)
        checker.cpu_threshold = 0.5
        assert checker.check_activity() is False

class TestSystemChecker(BaseServiceTest):
    """Test suite for System service checker."""
    
    checker_class = SystemChecker

    @patch('subprocess.check_output')
    def test_active_users(self, mock_check_output, config):
        """Test detection of logged-in users."""
        mock_check_output.return_value = b"user1 pts/0\nuser2 pts/1\n"
        
        checker = SystemChecker(config)
        checker.ignore_users = set()
        assert checker.check_activity() is True

    @patch('subprocess.check_output')
    def test_ignored_users(self, mock_check_output, config):
        """Test handling of ignored users."""
        mock_check_output.return_value = b"ignored_user pts/0\n"
        
        checker = SystemChecker(config)
        checker.ignore_users = {"ignored_user"}
        assert checker.check_activity() is False

    def test_high_system_load(self, config):
        """Test detection of high system load."""
        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = "0.1 0.8 0.6\n"
            
            checker = SystemChecker(config)
            checker.load_threshold = 0.5
            checker.check_load = True
            assert checker.check_activity() is True

    def test_low_system_load(self, config):
        """Test handling of low system load."""
        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = "0.1 0.2 0.3\n"
            
            checker = SystemChecker(config)
            checker.load_threshold = 0.5
            checker.check_load = True
            assert checker.check_activity() is False
