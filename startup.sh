#!/bin/bash

# Church Timer Startup Script
cd /home/russel/church-timer

# Wait for system to be fully ready
sleep 10

# Set display environment
export DISPLAY=:0
export XAUTHORITY=/home/russel/.Xauthority

# Activate virtual environment
source /home/russel/church-timer/church-timer-env/bin/activate

# Start the application
echo "$(date): Starting Church Timer Application" >> /home/russel/church-timer/app.log
exec python /home/russel/church-timer/app.py >> /home/russel/church-timer/app.log 2>&1