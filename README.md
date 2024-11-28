# MediaServer AutoSuspend

An intelligent system management script that automatically suspends your media server when idle while monitoring various services including Jellyfin, Sonarr, Radarr, and Nextcloud for activity.

## Features

- 🎬 Monitors Jellyfin for active streaming sessions
- 📺 Checks Sonarr and Radarr download queues
- ☁️ Monitors Nextcloud activity and CPU load
- 👥 Tracks system user sessions
- ⏰ Configurable grace period before suspension
- 🔄 Automatic wake-up timer setting
- 🛡️ Single instance enforcement
- 📝 Detailed activity logging

## Prerequisites

- Python 3.6 or higher
- Linux-based system with `systemctl` support
- `sudo` privileges for system suspension
- Running instances of monitored services (Jellyfin, Sonarr, Radarr, Nextcloud)
- Python packages: `requests`, `python-logging`

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/pirelike/mediaserver-autosuspend.git
   cd mediaserver-autosuspend
   ```

2. Install required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

3. Copy and modify the configuration file:
   ```bash
   cp config.example.json config.json
   nano config.json
   ```

4. Set up the systemd service:
   ```bash
   sudo cp systemd/mediaserver-autosuspend.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable mediaserver-autosuspend
   sudo systemctl start mediaserver-autosuspend
   ```

## Configuration

### Basic Configuration
Create a `config.json` file with your service configurations:

```json
{
    "JELLYFIN_API_KEY": "your-jellyfin-api-key",
    "JELLYFIN_URL": "http://your-server:8096",
    "RADARR_API_KEY": "your-radarr-api-key",
    "SONARR_API_KEY": "your-sonarr-api-key",
    "NEXTCLOUD_URL": "http://your-server:9000",
    "NEXTCLOUD_TOKEN": "your-nextcloud-token",
    "GRACE_PERIOD": 600
}
```

### Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `JELLYFIN_API_KEY` | Your Jellyfin API key | Required |
| `JELLYFIN_URL` | URL to your Jellyfin server | Required |
| `RADARR_API_KEY` | Your Radarr API key | Required |
| `SONARR_API_KEY` | Your Sonarr API key | Required |
| `NEXTCLOUD_URL` | URL to your Nextcloud instance | Required |
| `NEXTCLOUD_TOKEN` | Your Nextcloud admin token | Required |
| `GRACE_PERIOD` | Wait time in seconds before suspension | 600 |

## Customization

### Adding New Services

To monitor additional services, create a new service checker class in `services/`:

```python
from .base import ServiceChecker

class CustomServiceChecker(ServiceChecker):
    def __init__(self, config):
        super().__init__(config)
        self.name = "CustomService"

    def check_activity(self):
        # Implement your service checking logic here
        return False  # Return True if service is active
```

### Modifying Suspension Conditions

You can customize the suspension logic by modifying the `suspension_manager.py` file:

```python
def should_suspend(self):
    # Add your custom conditions here
    return all([
        not self.system_checker.is_active(),
        not self.media_checker.is_active(),
        # Add more conditions
    ])
```

### Wake-up Configuration

To customize wake-up times, modify the `scripts/set-wakeup.sh` script:

```bash
# Example: Wake up at specific times
WAKE_HOURS="07:00,13:00,19:00"
```

## Logging

Logs are written to `/var/log/mediaserver-autosuspend.log` by default. The log level can be configured in `config.json`:

```json
{
    "LOG_LEVEL": "INFO",
    "LOG_FILE": "/var/log/mediaserver-autosuspend.log"
}
```

## Troubleshooting

### Common Issues

1. **System won't suspend**
   - Check service logs: `journalctl -u mediaserver-autosuspend`
   - Verify sudo permissions for suspension
   - Check service connectivity

2. **Service detection issues**
   - Verify API keys and URLs in config.json
   - Check network connectivity to services
   - Ensure services are running

### Debug Mode

Enable debug logging by setting `LOG_LEVEL` to "DEBUG" in config.json:

```json
{
    "LOG_LEVEL": "DEBUG"
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

- Original script by Pirelike
- Inspired by various media server management tools
- Thanks to the Jellyfin, Sonarr, Radarr, and Nextcloud communities
