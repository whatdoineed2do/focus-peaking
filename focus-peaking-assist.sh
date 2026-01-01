#!/bin/bash

# --- CONFIGURATION ---
CAMERA_NAME="Focus Peaking Assist Device"
PYTHON_SCRIPT="focus_peaking.py"
CONFIG_FILE="config.ini"
# Interval in milliseconds (100ms = 10 fps). Increase to 200ms for more battery saving.
STREAM_INTERVAL=200 

echo "--- $CAMERA_NAME Startup ---"

# 1. Check for v4l2loopback
if ! modinfo v4l2loopback >/dev/null 2>&1; then
    echo "Error: 'v4l2loopback' module not found."
    exit 1
fi

# 2. Find the video index
VIDEO_PATH=$(grep -l "$CAMERA_NAME" /sys/class/video4linux/video*/name 2>/dev/null | head -n 1)

if [ -z "$VIDEO_PATH" ]; then
    echo "Error: Virtual device '$CAMERA_NAME' not found."
    echo "Run: sudo modprobe v4l2loopback exclusive_caps=1 card_label=\"$CAMERA_NAME\""
    exit 1
fi

VIDEO_INDEX=$(echo "$VIDEO_PATH" | sed -e "s/video4linux//" | grep -o '[0-9]\+' | head -n 1)
echo "Found $CAMERA_NAME at /dev/video$VIDEO_INDEX"

# 3. Force Camera Settings (Save to Card & Unmount)
# Ensure camera isn't mounted by the OS
gio mount -s gphoto2 >/dev/null 2>&1 
# Set target to Memory Card (1) to ensure SIGUSR1 saves correctly
gphoto2 --set-config capturetarget=1 >/dev/null 2>&1

# 4. Start the Throttled Stream
# Adding --interval $STREAM_INTERVAL to save battery
echo "Starting throttled stream ($((1000 / STREAM_INTERVAL)) fps)..."
gphoto2 --capture-movie --stdout --interval $STREAM_INTERVAL | \
    ffmpeg -loglevel error -f mjpeg -i pipe:0 \
    -vf "pad=640:480:(ow-iw)/2:(oh-ih)/2,format=yuv420p" \
    -f v4l2 "/dev/video$VIDEO_INDEX" > /dev/null 2>&1 &

GPHOTO_FFMPEG_PID=$!

# 5. Wait & Launch Python
sleep 2
python3 "$PYTHON_SCRIPT" --index "$VIDEO_INDEX" --config "$CONFIG_FILE"

# 6. Aggressive Cleanup 
# We need to make sure the mirror drops immediately to save battery
echo "Shutting down and releasing camera..."
# Kill the whole process group started by the pipe
kill -SIGINT $GPHOTO_FFMPEG_PID 2>/dev/null
# Extra insurance: kill any stray gphoto2 movie processes
pkill -f "gphoto2 --capture-movie" 

echo "Done. Mirror should be down."
