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

# Get absolute path of script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root"
    exit 1
fi

# Function to check Python version
check_python() {
    local min_version="3.7"
    local python_cmd=""
    
    # Try different Python commands
    for cmd in python3 python; do
        if command -v $cmd &> /dev/null; then
            python_cmd=$cmd
            break
        fi
    done
    
    if [ -z "$python_cmd" ]; then
        log_error "Python 3.7 or higher is required but no Python installation found"
        exit 1
    fi
    
    # Get Python version
    PYTHON_VERSION=$($python_cmd -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    
    # Compare versions
    if [ "$(printf '%s\n' "$min_version" "$PYTHON_VERSION" | sort -V | head -n1)" != "$min_version" ]; then
        log_error "Python 3.7 or higher is required (found Python $PYTHON_VERSION)"
        exit 1
    fi
    
    return 0
}

# Function to check and install pip if needed
check_pip() {
    local python_cmd=$1
    
    # Try to find pip
    if ! command -v pip3 &> /dev/null && ! command -v pip &> /dev/null; then
        log_warn "pip not found. Attempting to install..."
        
        if command -v apt-get &> /dev/null; then
            apt-get update
            apt-get install -y python3-pip
        elif command -v dnf &> /dev/null; then
            dnf install -y python3-pip
        elif command -v yum &> /dev/null; then
            yum install -y python3-pip
        elif command -v zypper &> /dev/null; then
            zypper install -y python3-pip
        elif command -v pacman &> /dev/null; then
            pacman -S --noconfirm python-pip
        else
            log_error "Could not find package manager to install pip. Please install python3-pip manually."
            exit 1
        fi
    fi
    
    # Verify pip installation
    if ! command -v pip3 &> /dev/null && ! command -v pip &> /dev/null; then
        log_error "Failed to install pip. Please install python3-pip manually."
        exit 1
    fi
}

# Check required commands
check_required_commands() {
    local missing=0
    
    for cmd in systemctl rtcwake who sync; do
        if ! command -v "$cmd" &> /dev/null; then
            log_error "Required command not found: $cmd"
            missing=1
        fi
    done
    
    return $missing
}

# Installation paths
INSTALL_DIR="/opt/mediaserver-autosuspend"
CONFIG_DIR="/etc/mediaserver-autosuspend"
LOG_DIR="/var/log/mediaserver-autosuspend"
SYSTEMD_DIR="/etc/systemd/system"
VENV_DIR="$INSTALL_DIR/venv"
HOOKS_DIR="$CONFIG_DIR/hooks"

# Check system requirements
log_info "Checking system requirements..."
check_python
check_pip python3
check_required_commands || exit 1

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
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install wheel
"$VENV_DIR/bin/pip" install -r "$PROJECT_ROOT/requirements.txt"

# Install the package in development mode
log_info "Installing mediaserver-autosuspend package..."
"$VENV_DIR/bin/pip" install -e "$PROJECT_ROOT"

# Copy configuration files
log_info "Copying configuration files..."
if [ ! -f "$CONFIG_DIR/config.json" ]; then
    cp "$PROJECT_ROOT/config.example.json" "$CONFIG_DIR/config.json"
    log_info "Created initial configuration file"
else
    log_warn "Configuration file already exists, skipping..."
fi

# Copy files
log_info "Copying files..."
cp -r "$PROJECT_ROOT/mediaserver_autosuspend" "$INSTALL_DIR/"
cp "$PROJECT_ROOT/scripts/set-wakeup.sh" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/set-wakeup.sh"

# Install systemd service
log_info "Installing systemd service..."
cp "$PROJECT_ROOT/systemd/mediaserver-autosuspend.service" "$SYSTEMD_DIR/"

# Update systemd service file to use virtual environment
sed -i "s|ExecStart=.*|ExecStart=$VENV_DIR/bin/python -m mediaserver_autosuspend.main|" \
    "$SYSTEMD_DIR/mediaserver-autosuspend.service"

# Set permissions
log_info "Setting permissions..."
chown -R root:root "$INSTALL_DIR"
chmod 755 "$INSTALL_DIR"
chown -R root:root "$CONFIG_DIR"
chmod 755 "$CONFIG_DIR"
chmod 644 "$CONFIG_DIR/config.json"
chown -R root:root "$LOG_DIR"
chmod 755 "$LOG_DIR"

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

# Configuration reminder
log_warn "Remember to update your configuration in $CONFIG_DIR/config.json"
log_warn "At minimum, you need to:"
log_warn "1. Enable either Jellyfin or Plex in the SERVICES section"
log_warn "2. Set the appropriate API key/token"
log_warn "3. Verify the service URLs"

log_info "Installation completed successfully!"
log_info "You can monitor the service with: journalctl -u mediaserver-autosuspend -f"
log_info "To uninstall, run: $INSTALL_DIR/uninstall.sh"

# Deactivate virtual environment
deactivate
