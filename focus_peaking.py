import cv2
import numpy as np
import configparser
import argparse
import subprocess

def load_config(config_file_path):
    config = configparser.ConfigParser()
    config.read(config_file_path)
    return config

def apply_zoom(frame, zoom_factor):
    """Digital magnification for precise focus checking."""
    if zoom_factor <= 1.0: return frame
    h, w = frame.shape[:2]
    new_h, new_w = int(h / zoom_factor), int(w / zoom_factor)
    start_y, start_x = (h - new_h) // 2, (w - new_w) // 2
    cropped = frame[start_y:start_y + new_h, start_x:start_x + new_w]
    return cv2.resize(cropped, (w, h), interpolation=cv2.INTER_CUBIC)

def apply_peaking(frame, threshold, blur_size):
    """Calculates edge gradients to highlight in-focus areas."""
    img = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred_img = cv2.GaussianBlur(img, blur_size, 0)
    
    # Sobel operators to find high-frequency detail (focus)
    gradient_x = cv2.Sobel(blurred_img, cv2.CV_64F, 1, 0, ksize=3)
    gradient_y = cv2.Sobel(blurred_img, cv2.CV_64F, 0, 1, ksize=3)
    mag = np.sqrt(gradient_x**2 + gradient_y**2)
    
    gradient_8bit = np.uint8(np.clip(mag, 0, 255))
    _, edges = cv2.threshold(gradient_8bit, threshold, 255, cv2.THRESH_BINARY)
    
    res = frame.copy()
    res[edges > 0] = [0, 0, 255] # Red highlight for sharp edges
    return res

def main():
    parser = argparse.ArgumentParser(description="Focus Peaking Assist Utility")
    parser.add_argument("--index", type=int, required=True, help="V4L2 device index")
    parser.add_argument("--config", type=str, default="config.ini", help="Path to config file")
    args = parser.parse_args()

    config = load_config(args.config)
    cap = cv2.VideoCapture(args.index)

    zoom_levels = [1.0, 2.0, 4.0]
    z_idx = 0
    peaking_enabled = True
    show_capture_msg = 0 

    print("--- Focus Peaking Assist ---")
    print("SPACE : Remote Shutter Trigger")
    print("F     : Toggle Peaking (ON/OFF)")
    print("Z     : Cycle Magnification (1x, 2x, 4x)")
    print("Q     : Quit")

    while True:
        ret, frame = cap.read()
        if not ret: continue

        # 1. Magnification
        display_frame = apply_zoom(frame, zoom_levels[z_idx])

        # 2. Focus Peaking
        if peaking_enabled:
            thresh = int(config.get('FocusPeaking', 'Threshold', fallback=100))
            b_size = eval(config.get('FocusPeaking', 'BlurKernelSize', fallback="(3,3)"))
            display_frame = apply_peaking(display_frame, thresh, b_size)

        # 3. HUD Display
        status_text = f"Mag: {zoom_levels[z_idx]}x | Peaking: {'ON' if peaking_enabled else 'OFF'}"
        cv2.putText(display_frame, status_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        if show_capture_msg > 0:
            cv2.putText(display_frame, "TRIGGERING SHUTTER...", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            show_capture_msg -= 1

        cv2.imshow("Focus Peaking Assist", display_frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('z'):
            z_idx = (z_idx + 1) % len(zoom_levels)
        elif key == ord('f'):
            peaking_enabled = not peaking_enabled
        elif key == 32: # SPACEBAR
            show_capture_msg = 30
            subprocess.Popen(["gphoto2", "--trigger-capture"])

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
