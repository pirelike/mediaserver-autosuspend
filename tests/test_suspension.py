"""
Test suite for MediaServer AutoSuspend suspension manager.

This module provides comprehensive testing for the suspension manager functionality,
including service monitoring, grace periods, wake-up scheduling, and system commands.
"""

import pytest
import time
import subprocess
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, call
from typing import Dict, Any, List

from mediaserver_autosuspend.suspension_manager import SuspensionManager
from mediaserver_autosuspend.services.base import ServiceChecker
from mediaserver_autosuspend.services import (
    JellyfinChecker,
    PlexChecker,
    SonarrChecker,
    RadarrChecker,
    NextcloudChecker,
    SystemChecker
)

class MockServiceChecker(ServiceChecker):
    """Mock service checker for testing."""
    
    def __init__(self, config: Dict[str, Any], is_active: bool = False):
        """
        Initialize mock service checker.
        
        Args:
            config: Configuration dictionary
            is_active: Initial active state
        """
        super().__init__(config)
        self._is_active = is_active
        self.check_count = 0
    
    def check_activity(self) -> bool:
        """Mock activity check."""
        self.check_count += 1
        return self._is_active
    
    def set_active(self, state: bool) -> None:
        """Set service active state."""
        self._is_active = state

@pytest.fixture
def mock_services() -> Dict[str, MockServiceChecker]:
    """Fixture providing a set of mock services."""
    return {
        "jellyfin": MockServiceChecker({}, is_active=False),
        "sonarr": MockServiceChecker({}, is_active=False),
        "radarr": MockServiceChecker({}, is_active=False),
        "nextcloud": MockServiceChecker({}, is_active=False),
        "system": MockServiceChecker({}, is_active=False)
    }

@pytest.fixture
def test_config() -> Dict[str, Any]:
    """Fixture providing test configuration."""
    return {
        "GRACE_PERIOD": 10,
        "CHECK_INTERVAL": 1,
        "MIN_UPTIME": 300,
        "SUSPENSION_COOLDOWN": 1800,
        "WAKE_UP_TIMES": ["07:00", "13:00", "19:00"],
        "TIMEZONE": "UTC",
        "HOOKS_DIR": "/etc/mediaserver-autosuspend/hooks"
    }

@pytest.fixture
def suspension_manager(test_config: Dict[str, Any], mock_services: Dict[str, MockServiceChecker]) -> SuspensionManager:
    """Fixture providing configured SuspensionManager instance."""
    return SuspensionManager(test_config, mock_services)

class TestSuspensionManager:
    """Test suite for SuspensionManager class."""
    
    def test_initialization(self, test_config: Dict[str, Any], mock_services: Dict[str, MockServiceChecker]):
        """Test proper initialization of SuspensionManager."""
        manager = SuspensionManager(test_config, mock_services)
        
        assert manager.grace_period == test_config["GRACE_PERIOD"]
        assert manager.check_interval == test_config["CHECK_INTERVAL"]
        assert len(manager.services) == len(mock_services)
        assert manager.last_suspension is None
        assert manager.suspension_count == 0
        
        # Verify wake times parsing
        wake_times = manager.wake_times
        assert len(wake_times) == 3
        assert all(isinstance(t, datetime) for t in wake_times)
    
    def test_should_suspend_all_inactive(self, suspension_manager: SuspensionManager):
        """Test suspension check when all services are inactive."""
        with patch('time.time', return_value=suspension_manager.config['MIN_UPTIME'] + 1):
            assert suspension_manager.should_suspend() is True
    
    def test_should_suspend_service_active(self, suspension_manager: SuspensionManager, mock_services: Dict[str, MockServiceChecker]):
        """Test suspension prevention when one service is active."""
        mock_services["jellyfin"].set_active(True)
        assert suspension_manager.should_suspend() is False
    
    def test_should_suspend_multiple_active(self, suspension_manager: SuspensionManager, mock_services: Dict[str, MockServiceChecker]):
        """Test suspension prevention with multiple active services."""
        mock_services["jellyfin"].set_active(True)
        mock_services["sonarr"].set_active(True)
        assert suspension_manager.should_suspend() is False
    
    @patch('time.sleep')
    def test_grace_period_no_activity(self, mock_sleep: Mock, suspension_manager: SuspensionManager):
        """Test grace period completion with no activity."""
        assert suspension_manager.check_grace_period() is True
        assert mock_sleep.call_count > 0
    
    @patch('time.sleep')
    def test_grace_period_with_activity(self, mock_sleep: Mock, suspension_manager: SuspensionManager, mock_services: Dict[str, MockServiceChecker]):
        """Test grace period interruption when service becomes active."""
        def activate_service(*args):
            mock_services["jellyfin"].set_active(True)
        
        mock_sleep.side_effect = activate_service
        assert suspension_manager.check_grace_period() is False
    
    @patch('subprocess.run')
    def test_suspend_system_success(self, mock_run: Mock, suspension_manager: SuspensionManager):
        """Test successful system suspension."""
        mock_run.return_value.returncode = 0
        
        assert suspension_manager.suspend_system() is True
        assert mock_run.call_count >= 2  # wake timer + suspend
        
        calls = mock_run.call_args_list
        assert any('rtcwake' in str(call) for call in calls)
        assert any('systemctl suspend' in str(call) for call in calls)
    
    @patch('subprocess.run')
    def test_suspend_system_wake_timer_failure(self, mock_run: Mock, suspension_manager: SuspensionManager):
        """Test suspension process when wake timer fails."""
        mock_run.side_effect = [
            Mock(returncode=1),  # wake timer fails
            Mock(returncode=0)   # suspend would succeed
        ]
        
        assert suspension_manager.suspend_system() is False
        assert mock_run.call_count == 1  # Only wake timer attempted
    
    @patch('subprocess.run')
    def test_suspend_system_suspend_failure(self, mock_run: Mock, suspension_manager: SuspensionManager):
        """Test handling of failed suspension command."""
        mock_run.side_effect = [
            Mock(returncode=0),  # wake timer succeeds
            Mock(returncode=1)   # suspend fails
        ]
        
        assert suspension_manager.suspend_system() is False
        assert mock_run.call_count == 2
    
    def test_minimum_uptime_check(self, suspension_manager: SuspensionManager):
        """Test minimum uptime requirement."""
        with patch('time.time', return_value=0):
            assert suspension_manager.should_suspend() is False
        
        with patch('time.time', return_value=suspension_manager.config['MIN_UPTIME'] + 1):
            assert suspension_manager.should_suspend() is True
    
    def test_suspension_cooldown(self, suspension_manager: SuspensionManager):
        """Test suspension cooldown period."""
        # Simulate successful suspension
        with patch('subprocess.run', return_value=Mock(returncode=0)):
            suspension_manager.suspend_system()
        
        # Check cooldown period
        assert suspension_manager.should_suspend() is False
        
        # Advance time beyond cooldown
        suspension_manager.last_suspension = datetime.now() - timedelta(
            seconds=suspension_manager.config['SUSPENSION_COOLDOWN'] + 1
        )
        assert suspension_manager.should_suspend() is True
    
    def test_service_error_handling(self, suspension_manager: SuspensionManager, mock_services: Dict[str, MockServiceChecker]):
        """Test handling of service checker errors."""
        def raise_error():
            raise Exception("Service check failed")
        
        mock_services["jellyfin"].check_activity = raise_error
        assert suspension_manager.should_suspend() is False  # Err on the side of caution
    
    def test_get_status_summary(self, suspension_manager: SuspensionManager, mock_services: Dict[str, MockServiceChecker]):
        """Test service status summary generation."""
        mock_services["jellyfin"].set_active(True)
        mock_services["sonarr"].set_active(True)
        
        summary = suspension_manager.get_status_summary()
        assert isinstance(summary, dict)
        assert summary["jellyfin"] is True
        assert summary["sonarr"] is True
        assert summary["radarr"] is False
    
    @patch('subprocess.run')
    def test_pre_suspend_hooks(self, mock_run: Mock, suspension_manager: SuspensionManager, tmp_path):
        """Test execution of pre-suspension hooks."""
        hook_dir = tmp_path / "hooks/pre-suspend.d"
        hook_dir.mkdir(parents=True)
        (hook_dir / "test-hook.sh").write_text("#!/bin/bash\nexit 0")
        
        suspension_manager.config['HOOKS_DIR'] = str(tmp_path / "hooks")
        suspension_manager.suspend_system()
        assert any('hooks/pre-suspend.d' in str(call) for call in mock_run.call_args_list)
    
    def test_wake_time_calculation(self, suspension_manager: SuspensionManager):
        """Test wake-up time calculation."""
        next_wake = suspension_manager._get_next_wake_time()
        
        assert next_wake is not None
        assert isinstance(next_wake, datetime)
        # Ensure next wake time is in the future
        assert next_wake > datetime.now()
    
    @patch('subprocess.run')
    def test_filesystem_sync(self, mock_run: Mock, suspension_manager: SuspensionManager):
        """Test filesystem sync before suspension."""
        mock_run.return_value.returncode = 0
        
        suspension_manager.suspend_system()
        assert any('sync' in str(call) for call in mock_run.call_args_list)
    
    def test_uptime_calculation(self, suspension_manager: SuspensionManager):
        """Test uptime calculation."""
        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = "1234.56 789.01\n"
            uptime = suspension_manager._get_uptime()
            assert isinstance(uptime, float)
            assert uptime == 1234.56
