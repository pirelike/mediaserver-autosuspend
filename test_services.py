import pytest
import responses
from mediaserver_autosuspend.services.jellyfin import JellyfinChecker
from mediaserver_autosuspend.services.sonarr import SonarrChecker
from mediaserver_autosuspend.services.radarr import RadarrChecker
from mediaserver_autosuppend.services.nextcloud import NextcloudChecker

@pytest.fixture
def config():
    return {
        "JELLYFIN_API_KEY": "test-key",
        "JELLYFIN_URL": "http://localhost:8096",
        "RADARR_API_KEY": "test-key",
        "RADARR_URL": "http://localhost:7878",
        "SONARR_API_KEY": "test-key",
        "SONARR_URL": "http://localhost:8989",
        "NEXTCLOUD_URL": "http://localhost:9000",
        "NEXTCLOUD_TOKEN": "test-token"
    }

@pytest.fixture
def jellyfin_checker(config):
    return JellyfinChecker(config)

@pytest.fixture
def sonarr_checker(config):
    return SonarrChecker(config)

@pytest.fixture
def radarr_checker(config):
    return RadarrChecker(config)

@pytest.fixture
def nextcloud_checker(config):
    return NextcloudChecker(config)

class TestJellyfinChecker:
    @responses.activate
    def test_active_session(self, jellyfin_checker):
        # Mock Jellyfin API response with active session
        responses.add(
            responses.GET,
            f"{jellyfin_checker.url}/Sessions",
            json=[{"NowPlayingItem": {"Name": "Test Movie"}}],
            status=200
        )
        
        assert jellyfin_checker.check_activity() is True

    @responses.activate
    def test_no_active_session(self, jellyfin_checker):
        # Mock Jellyfin API response with no active sessions
        responses.add(
            responses.GET,
            f"{jellyfin_checker.url}/Sessions",
            json=[{"NowPlayingItem": None}],
            status=200
        )
        
        assert jellyfin_checker.check_activity() is False

    @responses.activate
    def test_api_error(self, jellyfin_checker):
        # Mock Jellyfin API error response
        responses.add(
            responses.GET,
            f"{jellyfin_checker.url}/Sessions",
            status=500
        )
        
        assert jellyfin_checker.is_active() is False

class TestSonarrChecker:
    @responses.activate
    def test_active_downloads(self, sonarr_checker):
        # Mock Sonarr API response with active downloads
        responses.add(
            responses.GET,
            f"{sonarr_checker.url}/api/v3/queue",
            json={"totalRecords": 2},
            status=200
        )
        
        assert sonarr_checker.check_activity() is True

    @responses.activate
    def test_no_downloads(self, sonarr_checker):
        # Mock Sonarr API response with no downloads
        responses.add(
            responses.GET,
            f"{sonarr_checker.url}/api/v3/queue",
            json={"totalRecords": 0},
            status=200
        )
        
        assert sonarr_checker.check_activity() is False

class TestRadarrChecker:
    @responses.activate
    def test_active_downloads(self, radarr_checker):
        # Mock Radarr API response with active downloads
        responses.add(
            responses.GET,
            f"{radarr_checker.url}/api/v3/queue",
            json={"totalRecords": 1},
            status=200
        )
        
        assert radarr_checker.check_activity() is True

    @responses.activate
    def test_no_downloads(self, radarr_checker):
        # Mock Radarr API response with no downloads
        responses.add(
            responses.GET,
            f"{radarr_checker.url}/api/v3/queue",
            json={"totalRecords": 0},
            status=200
        )
        
        assert radarr_checker.check_activity() is False

class TestNextcloudChecker:
    @responses.activate
    def test_active_users(self, nextcloud_checker):
        # Mock Nextcloud API response with active users
        responses.add(
            responses.GET,
            f"{nextcloud_checker.url}/ocs/v2.php/apps/serverinfo/api/v1/info",
            json={
                "ocs": {
                    "data": {
                        "activeUsers": {"last5minutes": 2},
                        "system": {"cpuload": [0.2, 0.3, 0.4]}
                    }
                }
            },
            status=200
        )
        
        assert nextcloud_checker.check_activity() is True

    @responses.activate
    def test_high_cpu_load(self, nextcloud_checker):
        # Mock Nextcloud API response with high CPU load
        responses.add(
            responses.GET,
            f"{nextcloud_checker.url}/ocs/v2.php/apps/serverinfo/api/v1/info",
            json={
                "ocs": {
                    "data": {
                        "activeUsers": {"last5minutes": 0},
                        "system": {"cpuload": [0.4, 0.6, 0.5]}
                    }
                }
            },
            status=200
        )
        
        assert nextcloud_checker.check_activity() is True

    @responses.activate
    def test_inactive_system(self, nextcloud_checker):
        # Mock Nextcloud API response with no activity
        responses.add(
            responses.GET,
            f"{nextcloud_checker.url}/ocs/v2.php/apps/serverinfo/api/v1/info",
            json={
                "ocs": {
                    "data": {
                        "activeUsers": {"last5minutes": 0},
                        "system": {"cpuload": [0.1, 0.2, 0.1]}
                    }
                }
            },
            status=200
        )
        
        assert nextcloud_checker.check_activity() is False
