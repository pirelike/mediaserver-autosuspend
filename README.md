# MediaServer AutoSuspend

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.7%2B-blue)
[![GitHub Issues](https://img.shields.io/github/issues/pirelike/mediaserver-autosuspend.svg)](https://github.com/pirelike/mediaserver-autosuspend/issues)

## What is this?

MediaServer AutoSuspend is a power-saving system for your home server. It automatically:
- Puts your server to sleep when it's not being used
- Wakes it up when someone needs it
- Keeps your server updated and maintained

Think of it like having a smart assistant that turns off your server when no one's using it and turns it back on when needed!

## Why would I want this?

- **Save Power**: Your server only runs when it's actually needed
- **Automatic Updates**: System stays updated without manual work
- **Smart Management**: Monitors your services (Jellyfin, downloads, etc.) and only sleeps when everything is idle
- **Convenience**: Everything is automatic - no need to manually manage your server

## What do I need?

Before installing, make sure you have:

1. A Linux server (Ubuntu Server recommended) running:
   - Jellyfin
   - Sonarr
   - Radarr
   - Nextcloud
   
2. A Raspberry Pi (any model) on your network
3. Basic knowledge of Linux commands
4. Wake-on-LAN enabled on your server

Not sure about these requirements? Check our [documentation](https://github.com/pirelike/mediaserver-autosuspend/wiki).

## How does it work?

The system has three main parts:

1. **AutoSuspend** (runs on your server)
   - Watches if anyone is:
     - Watching media
     - Downloading files
     - Using Nextcloud
     - Logged into the server
   - Puts server to sleep if no activity for 10 minutes

2. **Daily Maintenance** (runs on your server)
   - Wakes up server at 1:55 AM
   - Updates system
   - Cleans up old files
   - Restarts server

3. **Autowake** (runs on Raspberry Pi)
   - Watches for anyone trying to access your server
   - Automatically wakes up server when needed

## Step-by-Step Installation

### 1. Prepare Your System

First, make sure you have Python 3 and required tools:
```bash
# Update your system
sudo apt update
sudo apt upgrade

# Install required packages
sudo apt install python3 python3-venv python3-pip git
```

### 2. Create Directories
```bash
# Create main directory
sudo mkdir -p /home/mediaserver/scripts

# Set ownership (replace 'yourusername' with your actual username)
sudo chown -R yourusername:yourusername /home/mediaserver/scripts
```

### 3. Get the Code
```bash
# Clone the repository
git clone https://github.com/pirelike/mediaserver-autosuspend.git
cd mediaserver-autosuspend
```

### 4. Set Up Python Environment
```bash
# Create virtual environment
python3 -m venv /home/mediaserver/scripts/venv

# Activate it
source /home/mediaserver/scripts/venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 5. Configure Your Settings

Copy and edit the configuration files:
```bash
# Copy config files
sudo cp config/autosuspend_config.yaml.example /home/mediaserver/scripts/autosuspend_config.yaml
sudo cp config/maintenance_config.yaml.example /home/mediaserver/scripts/maintenance_config.yaml
```

Edit your settings:
```bash
# Edit AutoSuspend settings
sudo nano /home/mediaserver/scripts/autosuspend_config.yaml
```

You'll need to add:
- Your Jellyfin API key (find this in Jellyfin → Dashboard → Advanced)
- Your Sonarr API key (find this in Sonarr → Settings → General)
- Your Radarr API key (find this in Radarr → Settings → General)
- Your Nextcloud token
- Your Raspberry Pi's IP address

### 6. Install Services

```bash
# Copy scripts
sudo cp scripts/autosuspend.py /home/mediaserver/scripts/
sudo cp scripts/daily_maintenance.py /usr/local/bin/

# Make scripts executable
sudo chmod +x /home/mediaserver/scripts/autosuspend.py
sudo chmod +x /usr/local/bin/daily_maintenance.py

# Copy service files
sudo cp services/* /etc/systemd/system/

# Enable services
sudo systemctl daemon-reload
sudo systemctl enable autosuspend
sudo systemctl enable daily-maintenance.timer
sudo systemctl start autosuspend
sudo systemctl start daily-maintenance.timer
```

## Checking If It's Working

### Check AutoSuspend
```bash
# Check service status
systemctl status autosuspend

# View logs
tail -f /home/mediaserver/scripts/autosuspend.log
```

You should see messages about checking your services.

### Check Daily Maintenance
```bash
# Check when maintenance will run
systemctl list-timers daily-maintenance.timer
```

## Common Problems and Solutions

### Server won't go to sleep?
1. Check if anything is active:
   ```bash
   tail -f /home/mediaserver/scripts/autosuspend.log
   ```
2. Make sure no one is:
   - Watching media
   - Downloading files
   - Using Nextcloud
   - Logged into the server

### Server won't wake up?
1. Check if Wake-on-LAN is enabled in your BIOS
2. Verify your server's MAC address in the config
3. Make sure your Raspberry Pi is running
4. Check Raspberry Pi logs:
   ```bash
   tail -f /home/YOUR_PI_USER/Autowake/traffic_monitor.log
   ```

### Need More Help?

- Check our [Wiki](https://github.com/pirelike/mediaserver-autosuspend/wiki)
- Open an [Issue on GitHub](https://github.com/pirelike/mediaserver-autosuspend/issues)
- See [Discussions](https://github.com/pirelike/mediaserver-autosuspend/discussions)

## Want to Help?

We welcome contributions! Here's how you can help:
1. Fork the repository
2. Make your changes
3. Submit a pull request
4. Report bugs
5. Suggest new features

Check our [Contributing Guidelines](https://github.com/pirelike/mediaserver-autosuspend/blob/main/CONTRIBUTING.md) for more details.

## License

This project is licensed under the MIT License - see the [LICENSE](https://github.com/pirelike/mediaserver-autosuspend/blob/main/LICENSE) file for details.

## Safety Notes

- All passwords and API keys are stored locally on your server
- The system runs with minimum required permissions
- All changes are logged for debugging
- System updates are done safely
- No remote access required

## Related Projects

- [Autowake](https://github.com/pirelike/autowake) - The Raspberry Pi component for waking up your server
