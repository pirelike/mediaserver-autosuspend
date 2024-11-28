# MediaServer AutoSuspend

An intelligent system management script that automatically suspends your media server when idle. Monitors various services including Jellyfin/Plex, Sonarr, Radarr, and Nextcloud for activity.

## Features

- 🎬 Media server monitoring
  - Jellyfin support
  - Plex support (including transcoding detection)
  - Active session tracking
  - Configurable pause handling
- 📺 Download monitoring
  - Sonarr queue tracking
  - Radarr download monitoring
- ☁️ System monitoring
  - Nextcloud activity and CPU load
  - System user sessions
  - System load tracking
- ⚡ Power management
  - Configurable grace period
  - Automatic wake-up timer
  - Multiple wake-up times
  - Suspension cooldown
- 🛡️ Safety features
  - Single instance enforcement
  - Pre/Post suspension hooks
  - Minimum uptime checks
  - Service error handling
- 📝 Advanced logging
  - Detailed activity logs
  - JSON format support
  - Syslog integration
  - Log rotation

## Prerequisites

- Python 3.6 or higher
- Linux-based system with `systemctl` support
- `sudo` privileges for system suspension
- One of the following media servers:
  - Jellyfin
  - Plex Media Server
- Optional services:
  - Sonarr
  - Radarr
  - Nextcloud

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/pirelike/mediaserver-autosuspend.git
   cd mediaserver-autosuspend
   ```

2. Install using the installation script:
   ```bash
   sudo ./install.sh
   ```

   Or manually:
   ```bash
   # Install Python dependencies
   pip install -r requirements.txt
   
   # Create configuration
   sudo mkdir -p /etc/mediaserver-autosuspend
   sudo cp config.example.json /etc/mediaserver-autosuspend/config.json
   
   # Set up systemd service
   sudo cp systemd/mediaserver-autosuspend.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable mediaserver-autosuspend
   ```

## Configuration

### Media Server Setup

#### Jellyfin Configuration
1. Get your Jellyfin API key from Dashboard → Advanced → API Keys
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
1. Get your Plex token (see [Finding your Plex token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/))
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

### Download Services

#### Sonarr & Radarr Configuration
1. Get API keys from Settings → General
2. Update config.json with appropriate values:
   ```json
   {
     "SONARR_API_KEY": "your-sonarr-key",
     "SONARR_URL": "http://localhost:8989",
     "RADARR_API_KEY": "your-radarr-key",
     "RADARR_URL": "http://localhost:7878"
   }
   ```

### System Configuration

```json
{
  "GRACE_PERIOD": 600,        // Wait time before suspension (seconds)
  "CHECK_INTERVAL": 60,       // Time between checks (seconds)
  "MIN_UPTIME": 300,         // Minimum uptime before allowing suspension
  "WAKE_UP_TIMES": [         // Daily wake-up schedule
    "07:00",
    "13:00",
    "19:00"
  ]
}
```

## Advanced Features

### Suspension Hooks

Create custom scripts to run before/after suspension:

1. Create hook scripts in:
   - `/etc/mediaserver-autosuspend/hooks/pre-suspend.d/`
   - `/etc/mediaserver-autosuspend/hooks/post-suspend.d/`

2. Make scripts executable:
   ```bash
   chmod +x /etc/mediaserver-autosuspend/hooks/pre-suspend.d/my-script.sh
   ```

Example pre-suspend hook:
```bash
#!/bin/bash
# Stop services gracefully
systemctl stop transmission
```

### Logging Configuration

Configure logging behavior in config.json:
```json
{
  "LOG_LEVEL": "INFO",
  "LOG_FILE": "/var/log/mediaserver-autosuspend/service.log",
  "LOG_JSON": false,
  "USE_SYSLOG": false,
  "LOG_COLORS": true
}
```

## Troubleshooting

### Common Issues

1. **System won't suspend**
   - Check service logs: `journalctl -u mediaserver-autosuspend`
   - Verify service connectivity
   - Check API keys and URLs
   - Ensure proper permissions

2. **Wake-up not working**
   - Verify RTC wake support: `rtcwake --list-modes`
   - Check system logs: `journalctl -b -1 -n 100`
   - Verify wake-up times in config

3. **Service detection issues**
   - Check individual service connectivity
   - Verify API endpoints
   - Check network access

### Debug Mode

Enable debug logging in config.json:
```json
{
  "LOG_LEVEL": "DEBUG",
  "DEBUG_MODE": true
}
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Commit changes: `git commit -am 'Add feature'`
4. Push to branch: `git push origin feature-name`
5. Submit a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Original concept based on various media server management tools
- Thanks to the Jellyfin, Plex, Sonarr, Radarr, and Nextcloud communities
