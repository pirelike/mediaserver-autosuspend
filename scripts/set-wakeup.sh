#!/bin/bash

# MediaServer AutoSuspend Wake-up Script
# Configures system wake-up time using rtcwake based on configuration

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

# Configuration paths
CONFIG_FILE="/etc/mediaserver-autosuspend/config.json"
DEFAULT_WAKE_TIME="02:00"

# Check for required commands
if ! command -v rtcwake &> /dev/null; then
    log_error "rtcwake command not found. Please install util-linux package."
    exit 1
fi

if ! command -v jq &> /dev/null; then
    log_warn "jq not found. Installing minimal JSON parser..."
    # Minimal JSON parser for wake times if jq is not available
    parse_wake_times() {
        local json="$1"
        echo "$json" | grep -o '"[0-9]\{2\}:[0-9]\{2\}"' | tr -d '"'
    }
else
    # Use jq if available
    parse_wake_times() {
        local json="$1"
        echo "$json" | jq -r '.WAKE_UP_TIMES[]' 2>/dev/null
    }
fi

# Function to validate time format
validate_time() {
    local time="$1"
    if [[ ! "$time" =~ ^([0-1][0-9]|2[0-3]):[0-5][0-9]$ ]]; then
        return 1
    fi
    return 0
}

# Function to convert time to seconds since midnight
time_to_seconds() {
    local time="$1"
    local hours=$(echo "$time" | cut -d: -f1)
    local minutes=$(echo "$time" | cut -d: -f2)
    echo $((hours * 3600 + minutes * 60))
}

# Function to get timezone from config
get_timezone() {
    if command -v jq &> /dev/null; then
        local tz=$(jq -r '.TIMEZONE // "UTC"' "$CONFIG_FILE" 2>/dev/null)
        echo "${tz:-UTC}"
    else
        echo "UTC"
    fi
}

# Function to check if timezone is valid
validate_timezone() {
    local tz="$1"
    if [ -f "/usr/share/zoneinfo/$tz" ]; then
        return 0
    fi
    return 1
}

# Function to calculate wake time
calculate_wake_time() {
    local current_time=$(date +%s)
    local next_wake=999999999  # Large initial value
    local timezone=$(get_timezone)
    
    if ! validate_timezone "$timezone"; then
        log_warn "Invalid timezone in config, falling back to UTC"
        timezone="UTC"
    }
    
    # Set timezone for calculations
    export TZ="$timezone"
    
    # Read wake times from config
    if [ -f "$CONFIG_FILE" ]; then
        local config_content=$(cat "$CONFIG_FILE")
        WAKE_TIMES=$(parse_wake_times "$config_content")
    fi
    
    # Fall back to default if no valid wake times found
    if [ -z "$WAKE_TIMES" ]; then
        log_warn "No valid wake times found in config, using default: $DEFAULT_WAKE_TIME"
        WAKE_TIMES="$DEFAULT_WAKE_TIME"
    fi
    
    # Process each wake time
    local found_valid_time=false
    for wake_time in $WAKE_TIMES; do
        if ! validate_time "$wake_time"; then
            log_warn "Invalid time format: $wake_time"
            continue
        fi
        
        found_valid_time=true
        
        # Calculate wake timestamp for today and tomorrow
        local today_wake=$(date -d "today $wake_time" +%s)
        local tomorrow_wake=$(date -d "tomorrow $wake_time" +%s)
        
        # If wake time today is in the future, consider it
        if [ $today_wake -gt $current_time ]; then
            if [ $today_wake -lt $next_wake ]; then
                next_wake=$today_wake
            fi
        fi
        
        # Always consider tomorrow's wake time
        if [ $tomorrow_wake -lt $next_wake ]; then
            next_wake=$tomorrow_wake
        fi
    done
    
    if [ "$found_valid_time" = false ]; then
        log_error "No valid wake times found"
        exit 1
    fi
    
    echo $((next_wake - current_time))
}

# Main execution
log_info "Calculating next wake-up time..."

# Calculate seconds until next wake-up
SECONDS_TO_WAKE=$(calculate_wake_time)

if [ $SECONDS_TO_WAKE -le 0 ]; then
    log_error "Could not calculate valid wake-up time"
    exit 1
fi

# Set RTC wake timer
log_info "Setting RTC wake timer..."
if ! rtcwake -m no -s $SECONDS_TO_WAKE; then
    log_error "Failed to set wake timer"
    exit 1
fi

# Calculate and display wake-up time
WAKE_TIME=$(date -d "@$(($(date +%s) + SECONDS_TO_WAKE))" '+%Y-%m-%d %H:%M:%S %Z')
log_info "Wake timer set for: $WAKE_TIME (in $SECONDS_TO_WAKE seconds)"

exit 0
