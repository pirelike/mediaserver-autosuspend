#!/bin/bash

# MediaServer AutoSuspend Installation Script
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

# Determine the directory of the script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(sys.version_info[0]*10 + sys.version_info[1])')
if [ "$PYTHON_VERSION" -lt 36 ]; then
    log_error "Python 3.6 or higher is required (found $(python3 --version))"
    exit 1
fi

# Check required commands
REQUIRED_COMMANDS="systemctl rtcwake who sync python3 pip3"
MISSING_COMMANDS=""
for cmd in $REQUIRED_COMMANDS; do
    if ! command -v "$cmd" &> /dev/null; then
        MISSING_COMMANDS="$MISSING_COMMANDS $cmd"
    fi
done

if [ ! -z "$MISSING_COMMANDS" ]; then
    log_error "Required commands not found:$MISSING_COMMANDS"
    exit 1
fi

# Installation paths
INSTALL_DIR="/opt/mediaserver-autosuspend"
CONFIG_DIR="/etc/mediaserver-autosuspend"
LOG_DIR="/var/log/mediaserver-autosuspend"
SYSTEMD_DIR="/etc/systemd/system"
VENV_DIR="$INSTALL_DIR/venv"
HOOKS_DIR="$CONFIG_DIR/hooks"

# Create directories
log_info "Creating directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR"
mkdir -p "$LOG_DIR"
mkdir -p "$HOOKS_DIR/pre-suspend.d"
mkdir -p "$HOOKS_DIR/post-suspend.d"

# Create and activate virtual environment
log_info "Creating virtual environment..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

# Install Python dependencies
log_info "Installing Python dependencies..."
pip install -r "$PROJECT_DIR/requirements.txt"

# Deactivate virtual environment
deactivate

# Copy files
log_info "Copying files..."
cp -r "$PROJECT_DIR/mediaserver_autosuspend" "$INSTALL_DIR/"
cp "$PROJECT_DIR/config.example.json" "$CONFIG_DIR/"
cp "$PROJECT_DIR/scripts/set-wakeup.sh" "$INSTALL_DIR/"

# Create config if it doesn't exist
if [ ! -f "$CONFIG_DIR/config.json" ]; then
    log_info "Creating initial configuration..."
    cp "$CONFIG_DIR/config.example.json" "$CONFIG_DIR/config.json"
else
    log_info "Configuration file already exists, skipping..."
fi

# Install wake-up script
log_info "Installing wake-up script..."
chmod +x "$INSTALL_DIR/set-wakeup.sh"

# Install systemd service
log_info "Installing systemd service..."
cp "$PROJECT_DIR/systemd/mediaserver-autosuspend.service" "$SYSTEMD_DIR/"

# Modify systemd service file to use the virtual environment
sed -i "s|ExecStart=/usr/bin/python3|ExecStart=$VENV_DIR/bin/python|" "$SYSTEMD_DIR/mediaserver-autosuspend.service"

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

echo "MediaServer AutoSuspend has been uninstalled."
EOL

chmod +x "$INSTALL_DIR/uninstall.sh"

# Final status and instructions
log_info "Installation completed successfully!"
log_info "Please edit $CONFIG_DIR/config.json to configure your services"
log_info "You can monitor the service with: journalctl -u mediaserver-autosuspend -f"
log_info "To uninstall, run: $INSTALL_DIR/uninstall.sh"

# Configuration reminder
if [ -f "$CONFIG_DIR/config.json" ]; then
    log_warn "Remember to update your configuration in $CONFIG_DIR/config.json"
    log_warn "At minimum, you need to:"
    log_warn "1. Enable either Jellyfin or Plex in the SERVICES section"
    log_warn "2. Set the appropriate API key/token"
    log_warn "3. Verify the service URLs"
fi

# Check if running in a virtual environment
if [ -n "$VIRTUAL_ENV" ]; then
    log_warn "Installation was performed within a virtual environment ($VIRTUAL_ENV)"
    log_warn "Make sure required packages are also available system-wide"
fi
