"""
Test suite for MediaServer AutoSuspend suspension manager.
Tests suspension logic, grace periods, and system commands.
"""

import pytest
import time
from unittest.mock import Mock, patch, call
from datetime import datetime, timedelta

from mediaserver_autosuspend.suspension_manager import SuspensionManager
from mediaserver_autosuspend.services.base import ServiceChecker

class MockServiceChecker(ServiceChecker):
    """Mock service checker for testing."""
    
    def __init__(self, config, is_active=False):
        super().__init__(config)
        self._is_active = is_active
        self.check_count = 0
    
    def check_activity(self):
        self.check_count += 1
        return self._is_active
    
    def set_active(self, state):
        self._is_active = state

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

@pytest.fixture
def test_config():
    """Fixture providing test configuration."""
    return {
        "GRACE_PERIOD": 10,
        "CHECK_INTERVAL": 1,
        "MIN_UPTIME": 300,
        "SUSPENSION_COOLDOWN": 1800,
        "WAKE_UP_TIMES": ["07:00", "13:00", "19:00"]
    }

class TestSuspensionManager:
    """Test suite for SuspensionManager class."""
    
    def test_initialization(self, test_config, mock_services):
        """Test proper initialization of SuspensionManager."""
        manager = SuspensionManager(test_config, mock_services)
        assert manager.grace_period == test_config["GRACE_PERIOD"]
        assert manager.check_interval == test_config["CHECK_INTERVAL"]
        assert len(manager.services) == len(mock_services)
    
    def test_should_suspend_all_inactive(self, test_config, mock_services):
        """Test suspension check when all services are inactive."""
        manager = SuspensionManager(test_config, mock_services)
        
        with patch('time.time', return_value=test_config['MIN_UPTIME'] + 1):
            assert manager.should_suspend() is True
    
    def test_should_suspend_service_active(self, test_config, mock_services):
        """Test suspension prevention when one service is active."""
        mock_services["jellyfin"].set_active(True)
        manager = SuspensionManager(test_config, mock_services)
        assert manager.should_suspend() is False
    
    def test_should_suspend_multiple_active(self, test_config, mock_services):
        """Test suspension prevention with multiple active services."""
        mock_services["jellyfin"].set_active(True)
        mock_services["sonarr"].set_active(True)
        manager = SuspensionManager(test_config, mock_services)
        assert manager.should_suspend() is False
    
    @patch('time.sleep')
    def test_grace_period_no_activity(self, mock_sleep, test_config, mock_services):
        """Test grace period completion with no activity."""
        manager = SuspensionManager(test_config, mock_services)
        assert manager.check_grace_period() is True
        assert mock_sleep.call_count > 0
    
    @patch('time.sleep')
    def test_grace_period_with_activity(self, mock_sleep, test_config, mock_services):
        """Test grace period interruption when service becomes active."""
        manager = SuspensionManager(test_config, mock_services)
        
        def activate_service(*args):
            mock_services["jellyfin"].set_active(True)
        
        mock_sleep.side_effect = activate_service
        assert manager.check_grace_period() is False
    
    @patch('subprocess.run')
    def test_suspend_system_success(self, mock_run, test_config, mock_services):
        """Test successful system suspension."""
        mock_run.return_value.returncode = 0
        manager = SuspensionManager(test_config, mock_services)
        
        assert manager.suspend_system() is True
        assert mock_run.call_count >= 2  # wake timer + suspend
        
        calls = mock_run.call_args_list
        assert any('rtcwake' in str(call) for call in calls)
        assert any('systemctl suspend' in str(call) for call in calls)
    
    @patch('subprocess.run')
    def test_suspend_system_wake_timer_failure(self, mock_run, test_config, mock_services):
        """Test suspension process when wake timer fails."""
        mock_run.side_effect = [
            Mock(returncode=1),  # wake timer fails
            Mock(returncode=0)   # suspend would succeed
        ]
        
        manager = SuspensionManager(test_config, mock_services)
        assert manager.suspend_system() is False
        assert mock_run.call_count == 1  # Only wake timer attempted
    
    @patch('subprocess.run')
    def test_suspend_system_suspend_failure(self, mock_run, test_config, mock_services):
        """Test handling of failed suspension command."""
        mock_run.side_effect = [
            Mock(returncode=0),  # wake timer succeeds
            Mock(returncode=1)   # suspend fails
        ]
        
        manager = SuspensionManager(test_config, mock_services)
        assert manager.suspend_system() is False
        assert mock_run.call_count == 2
    
    def test_minimum_uptime_check(self, test_config, mock_services):
        """Test minimum uptime requirement."""
        manager = SuspensionManager(test_config, mock_services)
        
        with patch('time.time', return_value=0):
            assert manager.should_suspend() is False
        
        with patch('time.time', return_value=test_config['MIN_UPTIME'] + 1):
            assert manager.should_suspend() is True
    
    def test_suspension_cooldown(self, test_config, mock_services):
        """Test suspension cooldown period."""
        manager = SuspensionManager(test_config, mock_services)
        
        # Simulate successful suspension
        with patch('subprocess.run', return_value=Mock(returncode=0)):
            manager.suspend_system()
        
        # Check cooldown period
        assert manager.should_suspend() is False
        
        # Advance time beyond cooldown
        manager.last_suspension = datetime.now() - timedelta(
            seconds=test_config['SUSPENSION_COOLDOWN'] + 1
        )
        assert manager.should_suspend() is True
    
    def test_service_error_handling(self, test_config, mock_services):
        """Test handling of service checker errors."""
        def raise_error():
            raise Exception("Service check failed")
        
        mock_services["jellyfin"].check_activity = raise_error
        manager = SuspensionManager(test_config, mock_services)
        
        assert manager.should_suspend() is False  # Err on the side of caution
    
    def test_get_status_summary(self, test_config, mock_services):
        """Test service status summary generation."""
        mock_services["jellyfin"].set_active(True)
        mock_services["sonarr"].set_active(True)
        manager = SuspensionManager(test_config, mock_services)
        
        summary = manager.get_status_summary()
        assert isinstance(summary, dict)
        assert summary["jellyfin"] is True
        assert summary["sonarr"] is True
        assert summary["radarr"] is False
    
    @patch('subprocess.run')
    def test_pre_suspend_hooks(self, mock_run, test_config, mock_services, tmp_path):
        """Test execution of pre-suspension hooks."""
        hook_dir = tmp_path / "hooks/pre-suspend.d"
        hook_dir.mkdir(parents=True)
        (hook_dir / "test-hook.sh").write_text("#!/bin/bash\nexit 0")
        
        test_config['HOOKS_DIR'] = str(tmp_path / "hooks")
        manager = SuspensionManager(test_config, mock_services)
        
        manager.suspend_system()
        assert any('hooks/pre-suspend.d' in str(call) for call in mock_run.call_args_list)
    
    def test_wake_time_calculation(self, test_config, mock_services):
        """Test wake-up time calculation."""
        manager = SuspensionManager(test_config, mock_services)
        next_wake = manager._get_next_wake_time()
        
        assert next_wake is not None
        assert isinstance(next_wake, datetime)
        # Ensure next wake time is in the future
        assert next_wake > datetime.now()
