# MediaServer AutoSuspend

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.7%2B-blue)
[![GitHub Issues](https://img.shields.io/github/issues/pirelike/mediaserver-autosuspend.svg)](https://github.com/pirelike/mediaserver-autosuspend/issues)

An intelligent power management system for media servers that automatically suspends your server during periods of inactivity while ensuring all services are properly monitored and managed.

## 🌟 Features

### Core Functionality
- **Intelligent Service Monitoring**
  - Real-time activity detection
  - Configurable grace periods
  - Multiple service support
  - Reliable state tracking

### Media Server Integration
- **Jellyfin Support**
  - Active session monitoring
  - Playback state detection
  - Background task tracking
  - API-based integration

- **Plex Support**
  - Session tracking
  - Transcoding detection
  - Pause state handling
  - Queue monitoring

### Download Management
- **Sonarr Integration**
  - Queue monitoring
  - Download tracking
  - Status updates

- **Radarr Integration**
  - Active download detection
  - Queue management
  - Status monitoring

### System Management
- **Advanced Power Controls**
  - Configurable grace periods
  - Scheduled wake-up times
  - System load monitoring
  - Safe suspension handling

- **Nextcloud Integration**
  - CPU load monitoring
  - Activity tracking
  - Resource usage detection

### Safety Features
- **Robust Error Handling**
  - Service connectivity checks
  - Graceful degradation
  - Error recovery
  - Activity verification

- **System Protection**
  - Minimum uptime enforcement
  - Suspension cooldown
  - Pre/Post suspension hooks
  - Safe state verification

### Monitoring & Logging
- **Comprehensive Logging**
  - Detailed activity logs
  - JSON format support
  - Log rotation
  - Syslog integration

- **Status Reporting**
  - Service state tracking
  - Activity statistics
  - Error reporting
  - Performance metrics

## 📋 Prerequisites

### System Requirements
- Linux-based operating system with `systemd` support
- Python 3.7 or higher
- `sudo` privileges for system suspension
- `rtcwake` utility for scheduled wake-ups

### Required Services (At least one)
- Jellyfin Media Server
- Plex Media Server

### Optional Services
- Sonarr
- Radarr
- Nextcloud

### Python Dependencies
Core dependencies are automatically installed during setup. For development, additional packages may be required. See [Development Setup](#-development-setup) for details.

## 🚀 Installation

### Quick Install (Recommended)
```bash
# Clone the repository
git clone https://github.com/pirelike/mediaserver-autosuspend.git
cd mediaserver-autosuspend

# Run installation script
sudo ./install.sh
```

### Manual Installation
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create configuration directory
sudo mkdir -p /etc/mediaserver-autosuspend
sudo cp config.example.json /etc/mediaserver-autosuspend/config.json

# Install systemd service
sudo cp systemd/mediaserver-autosuspend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mediaserver-autosuspend
```

## ⚙️ Configuration

### Basic Configuration
1. Copy the example configuration:
   ```bash
   sudo cp config.example.json /etc/mediaserver-autosuspend/config.json
   ```

2. Edit the configuration file:
   ```bash
   sudo nano /etc/mediaserver-autosuspend/config.json
   ```

### Media Server Setup

#### Jellyfin Configuration
1. Get your API key:
   - Go to Jellyfin Dashboard → Advanced → API Keys
   - Create a new API key
2. Update config.json:
   ```json
   {
     "SERVICES": {
       "jellyfin": true,
       "plex": false
     },
     "JELLYFIN_API_KEY": "your-api-key",
     "JELLYFIN_URL": "http://localhost:8096"
   }
   ```

#### Plex Configuration
1. Get your Plex token ([Finding your Plex token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/))
2. Update config.json:
   ```json
   {
     "SERVICES": {
       "jellyfin": false,
       "plex": true
     },
     "PLEX_TOKEN": "your-plex-token",
     "PLEX_URL": "http://localhost:32400",
     "PLEX_MONITOR_TRANSCODING": true,
     "PLEX_IGNORE_PAUSED": false
   }
   ```

### Additional Services

#### Sonarr Configuration
1. Get your API key from Sonarr:
   - Settings → General → API Key
2. Update config.json:
   ```json
   {
     "SONARR_API_KEY": "your-api-key",
     "SONARR_URL": "http://localhost:8989"
   }
   ```

#### Radarr Configuration
1. Get your API key from Radarr:
   - Settings → General → API Key
2. Update config.json:
   ```json
   {
     "RADARR_API_KEY": "your-api-key",
     "RADARR_URL": "http://localhost:7878"
   }
   ```

#### Nextcloud Configuration
1. Create an app password:
   - Settings → Security → App passwords
2. Update config.json:
   ```json
   {
     "NEXTCLOUD_URL": "http://your-nextcloud-server",
     "NEXTCLOUD_TOKEN": "your-app-password",
     "NEXTCLOUD_CPU_THRESHOLD": 0.5
   }
   ```

### System Configuration

#### Timing Settings
```json
{
  "GRACE_PERIOD": 600,        // Wait time before suspension (seconds)
  "CHECK_INTERVAL": 60,       // Time between checks (seconds)
  "MIN_UPTIME": 300,         // Minimum uptime before allowing suspension
  "SUSPENSION_COOLDOWN": 1800 // Time between suspension attempts (seconds)
}
```

#### Wake-up Schedule
```json
{
  "WAKE_UP_TIMES": [
    "07:00",
    "13:00",
    "19:00"
  ],
  "TIMEZONE": "UTC"
}
```

## 🛠️ Advanced Features

### Custom Hooks
Create scripts to run before/after suspension:

1. Create hook directories:
   ```bash
   sudo mkdir -p /etc/mediaserver-autosuspend/hooks/pre-suspend.d
   sudo mkdir -p /etc/mediaserver-autosuspend/hooks/post-suspend.d
   ```

2. Create your scripts:
   ```bash
   sudo nano /etc/mediaserver-autosuspend/hooks/pre-suspend.d/stop-services.sh
   ```
   ```bash
   #!/bin/bash
   # Example: Stop services before suspension
   systemctl stop transmission
   ```

3. Make scripts executable:
   ```bash
   sudo chmod +x /etc/mediaserver-autosuspend/hooks/pre-suspend.d/stop-services.sh
   ```

### Logging Configuration
Configure logging behavior in config.json:
```json
{
  "LOG_LEVEL": "INFO",
  "LOG_FILE": "/var/log/mediaserver-autosuspend/service.log",
  "MAX_LOG_SIZE": 10485760,    // 10MB
  "LOG_BACKUP_COUNT": 5,
  "LOG_JSON": false,
  "USE_SYSLOG": false,
  "LOG_COLORS": true
}
```

## 🔧 Troubleshooting

### Common Issues

#### System Won't Suspend
1. Check service logs:
   ```bash
   journalctl -u mediaserver-autosuspend -f
   ```
2. Verify service connectivity:
   ```bash
   mediaserver-autosuspend --service-test
   ```
3. Check configuration:
   ```bash
   mediaserver-autosuspend --check-only
   ```

#### Wake-up Not Working
1. Verify RTC support:
   ```bash
   sudo rtcwake --list-modes
   ```
2. Check system logs:
   ```bash
   journalctl -b -1 -n 100
   ```
3. Verify wake-up times in config

#### Service Detection Issues
1. Test individual services:
   ```bash
   curl -H "X-Api-Key: your-key" http://localhost:8989/api/v3/system/status
   ```
2. Check network access:
   ```bash
   ping localhost
   telnet localhost 8096
   ```

### Debug Mode
Enable debug logging in config.json:
```json
{
  "LOG_LEVEL": "DEBUG",
  "DEBUG_MODE": true
}
```

## 👩‍💻 Development Setup

### Setting Up Development Environment
```bash
# Clone repository
git clone https://github.com/pirelike/mediaserver-autosuspend.git
cd mediaserver-autosuspend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install development dependencies
pip install -r requirements.txt

# Install pre-commit hooks
pre-commit install
```

### Running Tests
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_services.py

# Run with coverage report
pytest --cov=mediaserver_autosuspend
```

### Code Style
The project follows PEP 8 guidelines. Use provided tools to maintain consistency:
```bash
# Format code
black .

# Sort imports
isort .

# Run linter
flake8
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes:
   - Follow the code style guidelines
   - Add tests for new features
   - Update documentation as needed
4. Run tests: `pytest`
5. Commit changes: `git commit -am 'Add feature'`
6. Push to branch: `git push origin feature-name`
7. Submit a Pull Request

## 🙏 Acknowledgments

- Original concept inspired by various media server management tools
- Thanks to the Jellyfin, Plex, Sonarr, Radarr, and Nextcloud communities
- Special thanks to all contributors and users providing feedback

## 📱 Support

- Submit issues on [GitHub Issues](https://github.com/pirelike/mediaserver-autosuspend/issues)
- Join discussions in [GitHub Discussions](https://github.com/pirelike/mediaserver-autosuspend/discussions)
- Check [Wiki](https://github.com/pirelike/mediaserver-autosuspend/wiki) for additional documentation

---

**Note**: Replace placeholder URLs, usernames, and paths with your actual project information.
