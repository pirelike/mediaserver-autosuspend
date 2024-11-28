#!/bin/bash

# MediaServer AutoSuspend Installation Script
# This script handles the installation and setup of the MediaServer AutoSuspend system

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'  # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
if (( $(echo "$PYTHON_VERSION < 3.6" | bc -l) )); then
    log_error "Python 3.6 or higher is required (found $PYTHON_VERSION)"
    exit 1
fi

# Installation paths
INSTALL_DIR="/opt/mediaserver-autosuspend"
CONFIG_DIR="/etc/mediaserver-autosuspend"
LOG_DIR="/var/log/mediaserver-autosuspend"
SYSTEMD_DIR="/etc/systemd/system"
HOOKS_DIR="$CONFIG_DIR/hooks"

# Create directories
log_info "Creating directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR"
mkdir -p "$LOG_DIR"
mkdir -p "$HOOKS_DIR/pre-suspend.d"
mkdir -p "$HOOKS_DIR/post-suspend.d"

# Install Python dependencies
log_info "Installing Python dependencies..."
python3 -m pip install -r requirements.txt

# Copy files
log_info "Copying files..."
cp -r mediaserver_autosuspend/* "$INSTALL_DIR/"
cp config.example.json "$CONFIG_DIR/config.json"
cp scripts/set-wakeup.sh "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/set-wakeup.sh"

# Install systemd service
log_info "Installing systemd service..."
cat > "$SYSTEMD_DIR/mediaserver-autosuspend.service" << EOL
[Unit]
Description=MediaServer AutoSuspend Service
After=network.target

[Service]
Type=simple
User=root
Group=root
ExecStart=/usr/bin/python3 -m mediaserver_autosuspend
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
EOL

# Create wake-up script with rtcwake functionality
log_info "Creating wake-up script..."
cat > "$INSTALL_DIR/set-wakeup.sh" << 'EOL'
#!/bin/bash
# Script to set system wake-up time
WAKEUP_TIME=${1:-"07:00"}

# Convert time to seconds from now
SECONDS_UNTIL_WAKE=$(date -d "tomorrow $WAKEUP_TIME" +%s)
NOW=$(date +%s)
SLEEP_SECONDS=$((SECONDS_UNTIL_WAKE - NOW))

# Set RTC wake time
rtcwake -m no -s "$SLEEP_SECONDS"
EOL

chmod +x "$INSTALL_DIR/set-wakeup.sh"

# Set permissions
log_info "Setting permissions..."
chown -R root:root "$INSTALL_DIR"
chmod 755 "$INSTALL_DIR"
chown -R root:root "$CONFIG_DIR"
chmod 755 "$CONFIG_DIR"
chmod 644 "$CONFIG_DIR/config.json"
chown -R root:root "$LOG_DIR"
chmod 755 "$LOG_DIR"

# Enable and start service
log_info "Enabling and starting service..."
systemctl daemon-reload
systemctl enable mediaserver-autosuspend
systemctl start mediaserver-autosuspend

# Check service status
if systemctl is-active --quiet mediaserver-autosuspend; then
    log_info "Service started successfully!"
else
    log_error "Service failed to start. Check logs with: journalctl -u mediaserver-autosuspend"
    exit 1
fi

# Create uninstall script
log_info "Creating uninstall script..."
cat > "$INSTALL_DIR/uninstall.sh" << EOL
#!/bin/bash
# Uninstall MediaServer AutoSuspend

systemctl stop mediaserver-autosuspend
systemctl disable mediaserver-autosuspend
rm -f "$SYSTEMD_DIR/mediaserver-autosuspend.service"
rm -rf "$INSTALL_DIR"
rm -rf "$CONFIG_DIR"
rm -rf "$LOG_DIR"
systemctl daemon-reload
EOL

chmod +x "$INSTALL_DIR/uninstall.sh"

log_info "Installation completed successfully!"
log_info "Please edit $CONFIG_DIR/config.json to configure your services"
log_info "You can monitor the service with: journalctl -u mediaserver-autosuspend -f"
log_info "To uninstall, run: $INSTALL_DIR/uninstall.sh"

# Check if config.json exists and needs to be configured
if [ ! -f "$CONFIG_DIR/config.json" ]; then
    log_warn "Configuration file not found. Please create $CONFIG_DIR/config.json"
    log_warn "You can use config.example.json as a template"
fi

# Verify required commands
REQUIRED_COMMANDS="systemctl rtcwake who sync"
for cmd in $REQUIRED_COMMANDS; do
    if ! command -v "$cmd" &> /dev/null; then
        log_warn "Required command '$cmd' not found. Some features may not work."
    fi
done
