# MediaServer AutoSuspend

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.7%2B-blue)
[![GitHub Issues](https://img.shields.io/github/issues/pirelike/mediaserver-autosuspend.svg)](https://github.com/pirelike/mediaserver-autosuspend/issues)

A comprehensive power management solution for home media servers. This system automatically manages server power states based on service activity, performs scheduled maintenance, and integrates with a Wake-on-LAN monitor ([Autowake](link-to-autowake)) for complete power management.

## Components

1. **AutoSuspend Service**: Monitors server activity and manages power state
2. **Daily Maintenance**: Handles system updates and cleanup with scheduled restarts
3. **Integration**: Works with [Autowake](link-to-autowake) for remote wake-up

## Features

### AutoSuspend Service
- Monitors multiple services:
  - Jellyfin media sessions
  - Sonarr/Radarr download queues
  - Nextcloud activity
  - System user sessions
  - External activity (via Pi monitor)
- Configurable grace period before suspend
- YAML configuration
- Line-based log rotation

### Daily Maintenance
- Automated system updates
- Docker cleanup
- Log rotation
- Scheduled restarts
- YAML configuration
- Progress tracking and reporting

## Prerequisites

- Python 3.8 or higher
- Linux system (tested on Ubuntu Server)
- Systemd
- Services to monitor:
  - Jellyfin
  - Sonarr
  - Radarr
  - Nextcloud
- Wake-on-LAN capability

## Installation

### 1. Create Directory Structure
```bash
sudo mkdir -p /home/mediaserver/scripts
sudo mkdir -p /home/mediaserver/scripts/venv
```

### 2. Set Up Virtual Environment
```bash
python3 -m venv /home/mediaserver/scripts/venv
source /home/mediaserver/scripts/venv/bin/activate
pip install -r requirements.txt
```

### 3. Install Scripts
```bash
sudo cp autosuspend.py /home/mediaserver/scripts/
sudo cp daily_maintenance.py /usr/local/bin/
sudo cp maintenance_config.yaml /home/mediaserver/scripts/
sudo cp autosuspend_config.yaml /home/mediaserver/scripts/
```

### 4. Configure AutoSuspend
Edit `/home/mediaserver/scripts/autosuspend_config.yaml`:
```yaml
# API Keys and URLs
jellyfin:
  api_key: "your-jellyfin-api-key"
  url: "http://localhost:8096"

radarr:
  api_key: "your-radarr-api-key"
  url: "http://localhost:7878"

sonarr:
  api_key: "your-sonarr-api-key"
  url: "http://localhost:8989"

nextcloud:
  url: "http://localhost:9000"
  token: "your-nextcloud-token"

raspberry_pi:
  url: "http://your-pi-ip:5005"

# Monitoring Configuration
monitoring:
  check_interval: 30  # seconds
  grace_period: 600   # seconds (10 minutes)

# Logging Configuration
logging:
  file: "/home/mediaserver/scripts/autosuspend.log"
  max_lines: 500
```

### 5. Configure Daily Maintenance
Edit `/home/mediaserver/scripts/maintenance_config.yaml`:
```yaml
# Logging Configuration
logging:
  file: "/home/mediaserver/scripts/daily_maintenance.log"
  max_lines: 500

# Maintenance Settings
maintenance:
  grace_period: 60        # Wait time after start (seconds)
  docker_prune: true      # Whether to clean Docker
  log_retention_days: 7   # System log retention
  restart_delay: 5        # Seconds to wait before restart
```

### 6. Create Service Files

AutoSuspend Service:
```bash
sudo nano /etc/systemd/system/autosuspend.service
```

Add:
```ini
[Unit]
Description=MediaServer AutoSuspend Service
After=network.target

[Service]
Type=simple
User=mediaserver
Group=mediaserver
WorkingDirectory=/home/mediaserver/scripts
Environment=PATH=/home/mediaserver/scripts/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=/home/mediaserver/scripts/venv/bin/python3 /home/mediaserver/scripts/autosuspend.py
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
```

Daily Maintenance Service:
```bash
sudo nano /etc/systemd/system/daily-maintenance.service
```

Add:
```ini
[Unit]
Description=MediaServer Daily Maintenance
After=network.target suspend.target hibernate.target

[Service]
Type=oneshot
Environment=PATH=/home/mediaserver/scripts/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=/usr/local/bin/daily_maintenance.py
User=root

[Install]
WantedBy=multi-user.target
```

Maintenance Timer:
```bash
sudo nano /etc/systemd/system/daily-maintenance.timer
```

Add:
```ini
[Unit]
Description=MediaServer Daily Maintenance Timer

[Timer]
OnCalendar=*-*-* 01:57:00
AccuracySec=1min
Persistent=true

[Install]
WantedBy=timers.target
```

### 7. Set Permissions
```bash
sudo chown -R mediaserver:mediaserver /home/mediaserver/scripts
sudo chmod +x /home/mediaserver/scripts/autosuspend.py
sudo chmod +x /usr/local/bin/daily_maintenance.py
```

### 8. Enable Services
```bash
sudo systemctl daemon-reload
sudo systemctl enable autosuspend
sudo systemctl start autosuspend
sudo systemctl enable daily-maintenance.timer
sudo systemctl start daily-maintenance.timer
```

## Daily Operation

### Power Management Sequence

1. System wakes up (via WoL or schedule) at 1:55 AM
2. Daily maintenance runs at 1:57 AM
   - System updates
   - Cleanup tasks
   - Restart
3. Regular operation (AutoSuspend):
   - Services checked every 30 seconds
   - 10-minute grace period if inactive
   - System suspends if still inactive
4. Wake-on-LAN:
   - [Autowake](link-to-autowake) monitors web traffic
   - Sends WoL packet when access detected
   - Cycle repeats

### Monitoring Services

Check AutoSuspend:
```bash
systemctl status autosuspend
tail -f /home/mediaserver/scripts/autosuspend.log
```

Check Maintenance:
```bash
systemctl list-timers daily-maintenance.timer
tail -f /home/mediaserver/scripts/daily_maintenance.log
```

## Troubleshooting

### AutoSuspend Issues
1. Check service status:
   ```bash
   journalctl -u autosuspend -n 50
   ```
2. Verify configuration:
   ```bash
   cat /home/mediaserver/scripts/autosuspend_config.yaml
   ```
3. Check service states in log

### Maintenance Issues
1. Check timer status:
   ```bash
   systemctl status daily-maintenance.timer
   ```
2. View maintenance logs:
   ```bash
   tail -f /home/mediaserver/scripts/daily_maintenance.log
   ```
3. Try manual run:
   ```bash
   sudo /usr/local/bin/daily_maintenance.py
   ```

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

## Security

- API keys stored in YAML config
- Limited service privileges
- Rotated logs
- Root access only for maintenance
- Safe shutdown sequences

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Related Projects

- [Autowake](link-to-autowake) - Wake-on-LAN monitor for remote access
