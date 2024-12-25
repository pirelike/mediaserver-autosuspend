# MediaServer AutoSuspend

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.7%2B-blue)
[![GitHub Issues](https://img.shields.io/github/issues/pirelike/mediaserver-autosuspend.svg)](https://github.com/pirelike/mediaserver-autosuspend/issues)

Mediaserver-autosuspend is a Python-based system that monitors various services (Jellyfin, Sonarr, Radarr, Nextcloud) and automatically manages server power state. It works in conjunction with a Wake-on-LAN monitor (like [Autowake](link-to-autowake)) to create an efficient power management system for home servers.

## Features

- Monitors multiple services:
  - Jellyfin media sessions
  - Sonarr/Radarr download queues
  - Nextcloud activity
  - System user sessions
  - External activity (via Pi monitor)
- Configurable grace period before suspend
- Automatic system updates before suspend
- Support for scheduled wake-ups
- Systemd service integration
- YAML configuration
- Line-based log rotation

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

1. Clone the repository:
```bash
git clone https://github.com/yourusername/autosuspend.git
cd autosuspend
```

2. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install required packages:
```bash
pip install -r requirements.txt
```

4. Copy configuration and scripts:
```bash
sudo mkdir -p /home/mediaserver/scripts
sudo cp autosuspend.py /home/mediaserver/scripts/
sudo cp autosuspend_config.yaml /home/mediaserver/scripts/
sudo cp daily_maintenance.sh /usr/local/bin/
```

5. Edit the configuration file:
```bash
sudo nano /home/mediaserver/scripts/autosuspend_config.yaml
```

Adjust the settings:
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

6. Create the service files:

Main service:
```bash
sudo nano /etc/systemd/system/autosuspend.service
```

Add:
```ini
[Unit]
Description=Autosuspend Service
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

Daily maintenance timer:
```bash
sudo nano /etc/systemd/system/daily-maintenance.timer
```

Add:
```ini
[Unit]
Description=Run Daily System Maintenance after Wake-up

[Timer]
OnCalendar=*-*-* 01:57:00
AccuracySec=1min
Persistent=true

[Install]
WantedBy=timers.target
```

Daily maintenance service:
```bash
sudo nano /etc/systemd/system/daily-maintenance.service
```

Add:
```ini
[Unit]
Description=Daily System Maintenance
After=network.target suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/daily_maintenance.sh
User=root

[Install]
WantedBy=multi-user.target
```

7. Set proper permissions:
```bash
sudo chown -R mediaserver:mediaserver /home/mediaserver/scripts
sudo chmod +x /home/mediaserver/scripts/autosuspend.py
sudo chmod +x /usr/local/bin/daily_maintenance.sh
```

8. Enable and start services:
```bash
sudo systemctl daemon-reload
sudo systemctl enable autosuspend
sudo systemctl start autosuspend
sudo systemctl enable daily-maintenance.timer
sudo systemctl start daily-maintenance.timer
```

## Usage

### Checking Service Status

Check autosuspend service:
```bash
systemctl status autosuspend
```

View logs:
```bash
tail -f /home/mediaserver/scripts/autosuspend.log
```

Check maintenance timer:
```bash
systemctl list-timers daily-maintenance.timer
```

### Service States

The script monitors multiple states:
- Jellyfin: Active when streaming
- Sonarr/Radarr: Active when downloading
- Nextcloud: Active with high CPU usage
- System: Active with logged-in users
- Pi Monitor: Active with recent web traffic

### Power Management Sequence

1. System wakes up (via WoL or schedule)
2. Services are checked every 30 seconds
3. If all inactive, 10-minute grace period starts
4. If still inactive after grace period, system suspends
5. Daily maintenance runs at 1:57 AM after scheduled wake-up

### Configuration Options

Key options in `autosuspend_config.yaml`:

```yaml
monitoring:
  check_interval: 30   # How often to check services
  grace_period: 600    # Wait time before suspend

logging:
  max_lines: 500      # Log rotation line limit
```

## Daily Maintenance

The daily maintenance script:
1. Updates package lists
2. Installs security updates
3. Cleans package cache
4. Performs Docker cleanup
5. Clears old logs
6. Restarts the system

## Troubleshooting

1. Service won't start:
   - Check logs: `journalctl -u autosuspend -n 50`
   - Verify Python dependencies
   - Check file permissions

2. System won't suspend:
   - Check service status in logs
   - Verify all monitored services
   - Check Pi monitor connection

3. Maintenance issues:
   - Check timer status
   - Verify script permissions
   - Check maintenance logs

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

## Security Considerations

- API keys stored in YAML config
- Service runs with limited privileges
- Logs are rotated
- Maintenance requires root for updates

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Inspired by the need for efficient server power management
- Works with Autowake for complete power management solution
- Built for home server environments
