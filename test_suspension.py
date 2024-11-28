import pytest
import time
from unittest.mock import Mock, patch
from mediaserver_autosuspend.suspension_manager import SuspensionManager
from mediaserver_autosuspend.services.base import ServiceChecker

class MockServiceChecker(ServiceChecker):
    """Mock service checker for testing."""
    def __init__(self, config, is_active=False):
        super().__init__(config)
        self._is_active = is_active
        self.name = "MockService"
        
    def check_activity(self):
        return self._is_active
        
    def set_active(self, state):
        self._is_active = state

@pytest.fixture
def config():
    """Fixture providing test configuration."""
    return {
        "GRACE_PERIOD": 10,  # Short period for testing
        "CHECK_INTERVAL": 1,
        "LOG_LEVEL": "DEBUG"
    }

@pytest.fixture
def mock_services():
    """Fixture providing a set of mock services."""
    return {
        "jellyfin": MockServiceChecker({}, is_active=False),
        "sonarr": MockServiceChecker({}, is_active=False),
        "radarr": MockServiceChecker({}, is_active=False),
        "nextcloud": MockServiceChecker({}, is_active=False),
        "system": MockServiceChecker({}, is_active=False)
    }

class TestSuspensionManager:
    """Test suite for SuspensionManager class."""

    def test_initialization(self, config, mock_services):
        """Test proper initialization of SuspensionManager."""
        manager = SuspensionManager(config, mock_services)
        assert manager.grace_period == config["GRACE_PERIOD"]
        assert manager.check_interval == config["CHECK_INTERVAL"]
        assert len(manager.services) == len(mock_services)

    def test_all_services_inactive(self, config, mock_services):
        """Test suspension check when all services are inactive."""
        manager = SuspensionManager(config, mock_services)
        assert manager.should_suspend() is True
    
    def test_one_service_active(self, config, mock_services):
        """Test suspension prevention when one service is active."""
        mock_services["jellyfin"].set_active(True)
        manager = SuspensionManager(config, mock_services)
        assert manager.should_suspend() is False
    
    def test_multiple_services_active(self, config, mock_services):
        """Test suspension prevention with multiple active services."""
        mock_services["jellyfin"].set_active(True)
        mock_services["sonarr"].set_active(True)
        manager = SuspensionManager(config, mock_services)
        assert manager.should_suspend() is False

    @patch('mediaserver_autosuspend.suspension_manager.subprocess.run')
    def test_successful_suspension(self, mock_run, config, mock_services):
        """Test successful system suspension process."""
        mock_run.return_value.returncode = 0
        manager = SuspensionManager(config, mock_services)
        
        assert manager.suspend_system() is True
        assert mock_run.call_count == 2  # wake timer + suspend
        
        # Verify correct command execution order
        calls = mock_run.call_args_list
        assert 'set-wakeup.sh' in str(calls[0])  # First call sets wake timer
        assert 'systemctl suspend' in str(calls[1])  # Second call suspends
    
    @patch('mediaserver_autosuspend.suspension_manager.subprocess.run')
    def test_failed_wake_timer(self, mock_run, config, mock_services):
        """Test suspension process when wake timer fails."""
        mock_run.side_effect = [
            Mock(returncode=1),  # wake timer fails
            Mock(returncode=0)   # suspend would succeed
        ]
        manager = SuspensionManager(config, mock_services)
        
        assert manager.suspend_system() is False
        assert mock_run.call_count == 1  # Only wake timer attempted
    
    @patch('mediaserver_autosuspend.suspension_manager.subprocess.run')
    def test_failed_suspension(self, mock_run, config, mock_services):
        """Test handling of failed suspension command."""
        mock_run.side_effect = [
            Mock(returncode=0),  # wake timer succeeds
            Mock(returncode=1)   # suspend fails
        ]
        manager = SuspensionManager(config, mock_services)
        
        assert manager.suspend_system() is False
        assert mock_run.call_count == 2

    @patch('time.sleep', return_value=None)
    def test_grace_period_no_interruption(self, mock_sleep, config, mock_services):
        """Test grace period completion without service activation."""
        manager = SuspensionManager(config, mock_services)
        
        # Start grace period check
        result = manager.check_grace_period()
        assert result is True  # Should complete without interruption
        assert mock_sleep.call_count > 0

    @patch('time.sleep', return_value=None)
    def test_grace_period_with_interruption(self, mock_sleep, config, mock_services):
        """Test grace period interruption when service becomes active."""
        manager = SuspensionManager(config, mock_services)
        
        def activate_service(*args):
            mock_services["jellyfin"].set_active(True)
            return None
        
        # Make sleep activate a service
        mock_sleep.side_effect = activate_service
        
        result = manager.check_grace_period()
        assert result is False  # Should be interrupted
        assert mock_sleep.call_count == 1  # Should stop after first service activation

    def test_service_error_handling(self, config, mock_services):
        """Test handling of service checker errors."""
        def raise_error():
            raise Exception("Service check failed")
            
        mock_services["jellyfin"].check_activity = raise_error
        manager = SuspensionManager(config, mock_services)
        
        # Should handle error gracefully and assume service is inactive
        assert manager.should_suspend() is True

    @patch('mediaserver_autosuspend.suspension_manager.subprocess.run')
    def test_sync_before_suspend(self, mock_run, config, mock_services):
        """Test filesystem sync before suspension."""
        mock_run.return_value.returncode = 0
        manager = SuspensionManager(config, mock_services)
        
        manager.suspend_system()
        
        # Verify sync was called before suspend
        calls = mock_run.call_args_list
        assert any('sync' in str(call) for call in calls)

    def test_service_status_summary(self, config, mock_services):
        """Test generation of service status summary."""
        mock_services["jellyfin"].set_active(True)
        mock_services["sonarr"].set_active(True)
        manager = SuspensionManager(config, mock_services)
        
        summary = manager.get_status_summary()
        
        assert isinstance(summary, dict)
        assert len(summary) == len(mock_services)
        assert summary["jellyfin"] is True
        assert summary["sonarr"] is True
        assert summary["radarr"] is False
