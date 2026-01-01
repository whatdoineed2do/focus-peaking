import cv2
import numpy as np
import configparser
import argparse
import subprocess
import os
import signal

# Global variables for mouse tracking
zoom_center_x = -1
zoom_center_y = -1

def mouse_callback(event, x, y, flags, param):
    global zoom_center_x, zoom_center_y
    if event == cv2.EVENT_LBUTTONDOWN:
        zoom_center_x = x
        zoom_center_y = y

def apply_zoom(frame, zoom_factor):
    global zoom_center_x, zoom_center_y
    h, w = frame.shape[:2]
    
    if zoom_factor <= 1.0:
        # Draw crosshair on 1x view to show where NEXT zoom will anchor
        if zoom_center_x != -1:
            cv2.drawMarker(frame, (zoom_center_x, zoom_center_y), (0, 255, 0), 
                           cv2.MARKER_CROSS, 20, 2)
        return frame
    
    # Calculate crop coordinates based on anchor or center
    curr_x = zoom_center_x if zoom_center_x != -1 else w // 2
    curr_y = zoom_center_y if zoom_center_y != -1 else h // 2

    new_h, new_w = int(h / zoom_factor), int(w / zoom_factor)
    
    # Clamp bounds
    start_x = max(0, min(curr_x - new_w // 2, w - new_w))
    start_y = max(0, min(curr_y - new_h // 2, h - new_h))
    
    cropped = frame[start_y:start_y + new_h, start_x:start_x + new_w]
    
    # Draw a small crosshair in the zoomed view to indicate the exact anchor
    # We map the global click back to the relative coordinates of the crop
    rel_x = curr_x - start_x
    rel_y = curr_y - start_y
    
    # Resize the crop to fill window
    zoomed_frame = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_CUBIC)
    
    # Draw crosshair on zoomed output (scaled to window size)
    # Scale factor is w / new_w (which is the zoom_factor)
    draw_x = int(rel_x * zoom_factor)
    draw_y = int(rel_y * zoom_factor)
    cv2.drawMarker(zoomed_frame, (draw_x, draw_y), (0, 255, 0), 
                   cv2.MARKER_CROSS, 30, 2)
    
    return zoomed_frame

def apply_peaking(frame, threshold, blur_size):
    img = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred_img = cv2.GaussianBlur(img, blur_size, 0)
    gx = cv2.Sobel(blurred_img, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(blurred_img, cv2.CV_64F, 0, 1, ksize=3)
    mag = np.sqrt(gx**2 + gy**2)
    gradient_8bit = np.uint8(np.clip(mag, 0, 255))
    _, edges = cv2.threshold(gradient_8bit, threshold, 255, cv2.THRESH_BINARY)
    res = frame.copy()
    res[edges > 0] = [0, 0, 255] 
    return res

def main():
    global zoom_center_x, zoom_center_y
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--config", type=str, default="config.ini")
    args = parser.parse_args()

    config = configparser.ConfigParser()
    config.read(args.config)
    
    cap = cv2.VideoCapture(args.index)
    cv2.namedWindow("Focus Peaking Assist")
    cv2.setMouseCallback("Focus Peaking Assist", mouse_callback)

    zoom_levels = [1.0, 2.0, 4.0]
    z_idx = 0
    peaking_enabled = True
    show_capture_msg = 0 

    while True:
        ret, frame = cap.read()
        if not ret: continue

        # 1. Zoom with POI
        display_frame = apply_zoom(frame, zoom_levels[z_idx])

        # 2. Peaking
        if peaking_enabled:
            thresh = int(config.get('FocusPeaking', 'Threshold', fallback=100))
            b_size = eval(config.get('FocusPeaking', 'BlurKernelSize', fallback="(3,3)"))
            display_frame = apply_peaking(display_frame, thresh, b_size)

        # 3. HUD Display
        status = f"Mag: {zoom_levels[z_idx]}x | Peaking: {'ON' if peaking_enabled else 'OFF'}"
        cv2.putText(display_frame, status, (10, 30), 0, 0.6, (0, 255, 0), 2)
        
        if show_capture_msg > 0:
            cv2.putText(display_frame, "TRIGGERING SHUTTER...", (10, 60), 0, 0.7, (0, 0, 255), 2)
            show_capture_msg -= 1

        cv2.imshow("Focus Peaking Assist", display_frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'): break
        elif key == ord('z'):
            z_idx = (z_idx + 1) % len(zoom_levels)
        elif key == ord('r'):
            zoom_center_x, zoom_center_y = -1, -1
        elif key == ord('f'):
            peaking_enabled = not peaking_enabled
        elif key == 32: # SPACE
            show_capture_msg = 45 
            try:
                # 1. More robust PID search
                # We use 'pgrep -x' to find the exact executable and check arguments
                cmd = "pgrep -f 'gphoto2.*capture-movie'"
                pid_output = subprocess.check_output(cmd, shell=True).decode().strip()
                
                if pid_output:
                    # Take the first PID if multiple are returned
                    target_pid = int(pid_output.split('\n')[0])
                    
                    # 2. Send the signal
                    os.kill(target_pid, signal.SIGUSR1)
                    print(f"Trigger Signal (SIGUSR1) sent to PID: {target_pid}")
                else:
                    print("Error: gphoto2 stream process not found.")
            except subprocess.CalledProcessError:
                print("Error: pgrep could not find gphoto2. Is the stream running?")
            except Exception as e:
                print(f"Trigger error: {e}")

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
