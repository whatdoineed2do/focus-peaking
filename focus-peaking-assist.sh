#!/bin/bash

# --- CONFIGURATION ---
# This name is used both for the UI and the kernel device label
CAMERA_NAME="Focus Peaking Assist Device"
PYTHON_SCRIPT="focus_peaking.py"
CONFIG_FILE="config.ini"

echo "--- $CAMERA_NAME Startup ---"

# 1. Check if v4l2loopback module is even installed/available
if ! modinfo v4l2loopback >/dev/null 2>&1; then
    echo "Error: 'v4l2loopback' kernel module is not installed."
    echo "Please install it (e.g., sudo apt install v4l2loopback-dkms)"
    exit 1
fi

# 2. Determine the correct /dev/video* index by searching for our specific label
VIDEO_PATH=$(grep -l "$CAMERA_NAME" /sys/class/video4linux/video*/name 2>/dev/null | head -n 1)

if [ -z "$VIDEO_PATH" ]; then
    echo "Error: Virtual device '$CAMERA_NAME' not found."
    echo ""
    echo "To fix this, please load the module with the following command:"
    echo "  sudo modprobe v4l2loopback exclusive_caps=1 card_label=\"$CAMERA_NAME\""
    echo ""
    echo "If you want it on a specific number (e.g. /dev/video4):"
    echo "  sudo modprobe v4l2loopback exclusive_caps=1 card_label=\"$CAMERA_NAME\" video_nr=4"
    exit 1
fi

# Extract the number (e.g., /dev/video4 -> 4)
VIDEO_INDEX=$(echo "$VIDEO_PATH" | sed -e "s/video4linux//" | grep -o '[0-9]\+' | head -n 1)
echo "Found $CAMERA_NAME at /dev/video$VIDEO_INDEX"

# 3. Check if any process is already using the camera (Cleanup)
# This prevents 'Device or resource busy' errors
EXISTING_FFMPEG=$(pgrep -f "ffmpeg.*video$VIDEO_INDEX")
if [ -z "$EXISTING_FFMPEG" ]; then
    echo "Starting new video stream pipe..."
else
    echo "Warning: A stream is already running on video$VIDEO_INDEX. Restarting..."
    kill $EXISTING_FFMPEG 2>/dev/null
    sleep 1
fi

# 4. Check if the physical camera is connected via USB
if ! gphoto2 --auto-detect | grep -q "Nikon"; then
    echo "Error: Physical Nikon camera not detected on USB."
    echo "Check USB cable and ensure camera is turned ON."
    exit 1
fi

# 5. Start the gphoto2 | ffmpeg chain in the background
# We pipe the D300's MJPEG to a standard 640x480 YUV feed
gphoto2 --capture-movie --stdout | ffmpeg -loglevel error -f mjpeg -i pipe:0 \
    -vf "pad=640:480:(ow-iw)/2:(oh-ih)/2,format=yuv420p" \
    -f v4l2 "/dev/video$VIDEO_INDEX" > /dev/null 2>&1 &

FFMPEG_PID=$!

# 6. Wait for the stream buffer to initialize
echo "Waiting for buffer..."
sleep 2

# 7. Start the Python Focus Peaking script
echo "Launching Focus Peaking Assist..."
python3 "$PYTHON_SCRIPT" --index "$VIDEO_INDEX" --config "$CONFIG_FILE"

# 8. Cleanup after Python exits (User presses 'q')
echo "Shutting down stream (PID: $FFMPEG_PID)..."
kill $FFMPEG_PID 2>/dev/null
