#!/bin/bash

# Church Timer Kiosk Startup
# Wait for the church timer service to start
sleep 20

# Hide cursor
unclutter -idle 0.1 -root &

# Disable screen blanking and power management
xset s off
xset -dpms
xset s noblank

# Wait for the Flask app to be fully started
until curl -f http://localhost:5000/ > /dev/null 2>&1; do
    sleep 5
done

# Start Chromium in kiosk mode
chromium-browser \
    --noerrdialogs \
    --disable-infobars \
    --disable-features=TranslateUI \
    --disable-session-crashed-bubble \
    --disable-pinch \
    --kiosk \
    --incognito \
    http://localhost:5000/ &

echo "Kiosk mode started at $(date)" >> /home/russel/church-timer/kiosk.log
