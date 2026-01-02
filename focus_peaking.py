import cv2
import numpy as np
import configparser
import argparse
import os
import time

# Global variables for mouse tracking and piping
zoom_center_x = -1
zoom_center_y = -1
CMD_PIPE = "/tmp/camera_cmd"

def mouse_callback(event, x, y, flags, param):
    global zoom_center_x, zoom_center_y
    if event == cv2.EVENT_LBUTTONDOWN:
        zoom_center_x = x
        zoom_center_y = y

def apply_zoom(frame, zoom_factor):
    global zoom_center_x, zoom_center_y
    h, w = frame.shape[:2]
    
    # 1x View Logic: Show where the next zoom will land
    if zoom_factor <= 1.0:
        if zoom_center_x != -1:
            cv2.drawMarker(frame, (zoom_center_x, zoom_center_y), (0, 255, 0), 
                           cv2.MARKER_CROSS, 20, 2)
        return frame
    
    # Zoomed View Logic
    curr_x = zoom_center_x if zoom_center_x != -1 else w // 2
    curr_y = zoom_center_y if zoom_center_y != -1 else h // 2

    new_h, new_w = int(h / zoom_factor), int(w / zoom_factor)
    
    # Clamp bounds to keep crop inside frame
    start_x = max(0, min(curr_x - new_w // 2, w - new_w))
    start_y = max(0, min(curr_y - new_h // 2, h - new_h))
    
    cropped = frame[start_y:start_y + new_h, start_x:start_x + new_w]
    
    # Map the anchor point to the zoomed display
    rel_x = curr_x - start_x
    rel_y = curr_y - start_y
    
    zoomed_frame = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_CUBIC)
    
    # Draw green crosshair on zoomed output
    draw_x = int(rel_x * zoom_factor)
    draw_y = int(rel_y * zoom_factor)
    cv2.drawMarker(zoomed_frame, (draw_x, draw_y), (0, 255, 0), 
                   cv2.MARKER_CROSS, 30, 2)
    
    return zoomed_frame

def apply_peaking(frame, sensitivity):
    """
    Refined Peaking: Uses Canny for thin lines. 
    Removes Gaussian blur to preserve micro-contrast for macro work.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Canny provides a 1-pixel wide line by suppressing non-maximum gradients
    low_thresh = sensitivity
    high_thresh = sensitivity * 2
    edges = cv2.Canny(gray, low_thresh, high_thresh)
    
    # Apply the red highlight
    res = frame.copy()
    res[edges > 0] = [0, 0, 255] # BGR Red
    return res

def main():
    global zoom_center_x, zoom_center_y
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--config", type=str, default="config.ini")
    args = parser.parse_args()

    # FIX: Corrected ConfigParser access
    config = configparser.ConfigParser()
    config.read(args.config)
    
    # Initialize Camera with Retry Logic to ensure the V4L2 device is ready
    print(f"Waiting for /dev/video{args.index} to initialize...")
    cap = cv2.VideoCapture(args.index)
    start_init = time.time()
    while not cap.isOpened():
        cap.open(args.index)
        if time.time() - start_init > 10:
            print(f"ERROR: Could not open /dev/video{args.index}. Is the bash script running?")
            return
        time.sleep(0.5)

    print("Stream connected. Press 'q' to quit.")
    cv2.namedWindow("Focus Peaking Assist")
    cv2.setMouseCallback("Focus Peaking Assist", mouse_callback)

    zoom_levels = [1.0, 2.0, 4.0, 6.0]
    z_idx = 0
    peaking_enabled = True
    show_capture_msg = 0 

    while True:
        ret, frame = cap.read()
        if not ret: 
            continue

        # 1. Apply Zoom and POI Crosshairs
        display_frame = apply_zoom(frame, zoom_levels[z_idx])

        # 2. Apply Refined Peaking
        if peaking_enabled:
            # Re-purposing 'Threshold' from config as the Canny sensitivity
            try:
                sensitivity = int(config.get('FocusPeaking', 'Threshold', fallback=50))
            except:
                sensitivity = 50
            display_frame = apply_peaking(display_frame, sensitivity)

        # 3. HUD Display
        status = f"Mag: {zoom_levels[z_idx]}x | Peaking: {'ON' if peaking_enabled else 'OFF'}"
        cv2.putText(display_frame, status, (10, 30), 0, 0.6, (0, 255, 0), 2)
        
        if show_capture_msg > 0:
            cv2.putText(display_frame, "COMMAND SENT: CAPTURING...", (10, 60), 0, 0.7, (0, 0, 255), 2)
            show_capture_msg -= 1

        cv2.imshow("Focus Peaking Assist", display_frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'): 
            break
        elif key == ord('z'):
            z_idx = (z_idx + 1) % len(zoom_levels)
        elif key == ord('r'):
            zoom_center_x, zoom_center_y = -1, -1
        elif key == ord('f'):
            peaking_enabled = not peaking_enabled
        elif key == 32: # SPACEBAR
            show_capture_msg = 60
            try:
                # Direct command to the Unified Shell pipe
                if os.path.exists(CMD_PIPE):
                    with open(CMD_PIPE, "w") as f:
                        f.write("capture\n")
                    print("Capture command sent.")
                else:
                    print(f"Error: {CMD_PIPE} not found. Start the bash script first.")
            except Exception as e:
                print(f"Pipe Error: {e}")

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
