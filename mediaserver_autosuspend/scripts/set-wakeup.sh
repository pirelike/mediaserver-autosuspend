#!/bin/bash

# set-wakeup.sh - Configure system wake-up time using rtcwake
# This script sets the RTC alarm to wake the system at the next scheduled time

# Exit on error
set -e

# Source configuration if available
CONFIG_FILE="/etc/mediaserver-autosuspend/config.json"
if [ -f "$CONFIG_FILE" ]; then
    # Extract wake-up times from config using jq if available
    if command -v jq >/dev/null 2>&1; then
        WAKE_TIMES=$(jq -r '.WAKE_UP_TIMES[]' "$CONFIG_FILE" 2>/dev/null || echo "07:00")
    else
        WAKE_TIMES="02:00"  # Default if jq not available
    fi
else
    WAKE_TIMES="02:00"  # Default wake time
fi

# Function to calculate seconds until next wake time
calculate_wake_seconds() {
    local current_time=$(date +%s)
    local next_wake=999999999  # Large number for initial comparison
    
    # Check each wake time
    for wake_time in $WAKE_TIMES; do
        # Calculate wake time for today and tomorrow
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
    
    # Calculate seconds until wake time
    echo $((next_wake - current_time))
}

# Get seconds until next wake-up time
SECONDS_TO_WAKE=$(calculate_wake_seconds)

# Ensure we have a positive number of seconds
if [ $SECONDS_TO_WAKE -le 0 ]; then
    echo "Error: Could not calculate valid wake-up time"
    exit 1
fi

# Set RTC wake time
if ! rtcwake -m no -s $SECONDS_TO_WAKE; then
    echo "Error: Failed to set wake timer"
    exit 1
fi

# Log the wake-up time
WAKE_TIME=$(date -d "@$(($(date +%s) + SECONDS_TO_WAKE))" '+%Y-%m-%d %H:%M:%S')
echo "Wake timer set for: $WAKE_TIME (in $SECONDS_TO_WAKE seconds)"

exit 0
