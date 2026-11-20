import cv2
import mediapipe as mp
import numpy as np
import matplotlib.pyplot as plt
import time
import os
import serial


# ============================================================
# 1. CONFIGURATION
# ============================================================

CAMERA_INDEX = 0

# EAR below this value is treated as eyes closed.
EAR_THRESHOLD = 0.22

# Eyes must remain closed for at least this duration to mark DROWSY.
DROWSY_TIME = 1.5

# Serial connection to ESP32 (CH340 USB-to-Serial).
# Change COM5 to the port shown in Windows Device Manager / Arduino IDE.
ESP32_PORT = "COM3"
BAUD_RATE = 115200

# MediaPipe model file must be in the same folder as this Python file.
MODEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "face_landmarker.task"
)


# ============================================================
# 2. DISTANCE FUNCTION
# ============================================================

def distance(p1, p2):
    return np.sqrt(
        (p1[0] - p2[0]) ** 2 +
        (p1[1] - p2[1]) ** 2
    )


# ============================================================
# 3. EYE ASPECT RATIO (EAR)
# ============================================================

def calculate_ear(landmarks, eye_indices):
    p1 = landmarks[eye_indices[0]]
    p2 = landmarks[eye_indices[1]]
    p3 = landmarks[eye_indices[2]]
    p4 = landmarks[eye_indices[3]]
    p5 = landmarks[eye_indices[4]]
    p6 = landmarks[eye_indices[5]]

    # EAR = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)
    vertical_1 = distance(
        (p2.x, p2.y),
        (p6.x, p6.y)
    )

    vertical_2 = distance(
        (p3.x, p3.y),
        (p5.x, p5.y)
    )

    horizontal = distance(
        (p1.x, p1.y),
        (p4.x, p4.y)
    )

    if horizontal == 0:
        return 0.0

    return (vertical_1 + vertical_2) / (2.0 * horizontal)


# ============================================================
# 4. EYE LANDMARK INDICES
# ============================================================

LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]


# ============================================================
# 5. ESP32 SERIAL COMMUNICATION
# ============================================================

esp32 = None
last_sent_status = None


def send_status(status):
    """Send a state to ESP32 only when the state changes.

    Python sends one of:
      NORMAL, EYES_CLOSED, DROWSY, NO_FACE

    The ESP32 sketch maps DROWSY to the red LED and vibration module.
    """
    global last_sent_status, esp32

    if esp32 is None:
        return

    commands = {
        "NORMAL": "NORMAL",
        "EYES CLOSED": "EYES_CLOSED",
        "DROWSY": "DROWSY",
        "NO_FACE": "NO_FACE"
    }

    command = commands.get(status)
    if command is None or command == last_sent_status:
        return

    try:
        esp32.write((command + "\n").encode("ascii"))
        last_sent_status = command
        print(f"ESP32 <= {command}")
    except (serial.SerialException, OSError) as error:
        print(f"Serial send error: {error}")
        print("ESP32 connection is disabled; detection will continue without LED/motor output.")
        try:
            esp32.close()
        except Exception:
            pass
        esp32 = None
        last_sent_status = None


def connect_esp32():
    """Open the ESP32 serial port. Return None if it is unavailable."""
    try:
        connection = serial.Serial(
            port=ESP32_PORT,
            baudrate=BAUD_RATE,
            timeout=1,
            write_timeout=1
        )
        # Opening the serial port may reset an ESP32 board.
        time.sleep(2)
        connection.reset_input_buffer()
        print(f"ESP32 connected on {ESP32_PORT} at {BAUD_RATE} baud.")
        return connection
    except (serial.SerialException, OSError) as error:
        print(f"Could not open ESP32 port {ESP32_PORT}: {error}")
        print("Check the COM port and close Arduino Serial Monitor.")
        print("Webcam detection will continue without external outputs.")
        return None


# ============================================================
# 6. CHECK MODEL FILE
# ============================================================

if not os.path.exists(MODEL_PATH):
    print("MODEL FILE NOT FOUND:")
    print(MODEL_PATH)
    print("Place face_landmarker.task in the same folder as this Python file.")
    raise SystemExit(1)


# ============================================================
# 7. INITIALIZE MEDIAPIPE FACE LANDMARKER
# ============================================================

BaseOptions = mp.tasks.BaseOptions
VisionRunningMode = mp.tasks.vision.RunningMode

options = mp.tasks.vision.FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=MODEL_PATH),
    running_mode=VisionRunningMode.VIDEO,
    num_faces=1,
    min_face_detection_confidence=0.5,
    min_face_presence_confidence=0.5,
    min_tracking_confidence=0.5
)

landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(options)


# ============================================================
# 8. OPEN WEBCAM AND ESP32
# ============================================================

cap = cv2.VideoCapture(CAMERA_INDEX)

if not cap.isOpened():
    print("Could not open webcam. Check CAMERA_INDEX and camera permissions.")
    landmarker.close()
    raise SystemExit(1)

print("Webcam opened.")
print("Press ESC to exit.")

# Serial is optional for testing: if ESP32 is disconnected, Python detection
# still runs and displays the webcam/plot.
esp32 = connect_esp32()


# ============================================================
# 9. PLOT DATA AND TIMERS
# ============================================================

time_history = []
ear_history = []

# Use monotonic time for durations; it is not affected by system clock changes.
app_start_time = time.monotonic()
video_start_time = app_start_time
previous_frame_timestamp = -1
closed_start = None


# ============================================================
# 10. MATPLOTLIB WINDOW
# ============================================================

plt.ion()

fig, ax = plt.subplots(figsize=(8, 4))
line, = ax.plot([], [], linewidth=2)

ax.axhline(
    EAR_THRESHOLD,
    linestyle="--",
    linewidth=1.5,
    label="EAR threshold"
)

ax.set_xlabel("Time (s)")
ax.set_ylabel("EAR")
ax.set_title("Real-time Eye Aspect Ratio")
ax.grid(True)
ax.legend()


# ============================================================
# 11. MAIN CAMERA LOOP
# ============================================================

try:
    while True:
        ret, frame = cap.read()

        if not ret:
            print("Could not read a frame from webcam.")
            send_status("NO_FACE")
            break

        # Mirror image, like a mirror.
        frame = cv2.flip(frame, 1)

        # OpenCV BGR -> RGB.
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Create MediaPipe Image.
        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=rgb_frame
        )

        # MediaPipe VIDEO mode requires a monotonically increasing timestamp
        # in milliseconds. Ensure it always increases, even if two frames
        # are processed within the same millisecond.
        frame_timestamp = int((time.monotonic() - video_start_time) * 1000)
        frame_timestamp = max(frame_timestamp, previous_frame_timestamp + 1)
        previous_frame_timestamp = frame_timestamp

        result = landmarker.detect_for_video(mp_image, frame_timestamp)

        if len(result.face_landmarks) > 0:
            landmarks = result.face_landmarks[0]

            # Calculate EAR for both eyes and take the average.
            left_ear = calculate_ear(landmarks, LEFT_EYE)
            right_ear = calculate_ear(landmarks, RIGHT_EYE)
            ear = (left_ear + right_ear) / 2.0

            # Draw eye landmark points.
            h, w, _ = frame.shape
            for idx in LEFT_EYE + RIGHT_EYE:
                x = int(landmarks[idx].x * w)
                y = int(landmarks[idx].y * h)
                cv2.circle(frame, (x, y), 3, (0, 255, 0), -1)

            # Eye-closure timer.
            current_time = time.monotonic()

            if ear < EAR_THRESHOLD:
                if closed_start is None:
                    closed_start = current_time
                closed_duration = current_time - closed_start
            else:
                closed_start = None
                closed_duration = 0.0

            # Classify current state.
            if closed_start is not None and closed_duration >= DROWSY_TIME:
                status = "DROWSY"
                status_color = (0, 0, 255)
            elif ear < EAR_THRESHOLD:
                status = "EYES CLOSED"
                status_color = (0, 165, 255)
            else:
                status = "NORMAL"
                status_color = (0, 255, 0)

            # Send status to ESP32. The ESP32 sketch controls LEDs and motor.
            send_status(status)

            # Display EAR.
            cv2.putText(
                frame,
                f"EAR: {ear:.3f}",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2
            )

            # Display state.
            cv2.putText(
                frame,
                f"STATUS: {status}",
                (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                status_color,
                2
            )

            # Display eye-closure duration.
            cv2.putText(
                frame,
                f"Closed: {closed_duration:.2f} s",
                (20, 120),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2
            )

            # Save plot data.
            elapsed = current_time - app_start_time
            time_history.append(elapsed)
            ear_history.append(ear)

            # Keep only the latest 300 points.
            max_points = 300
            if len(time_history) > max_points:
                time_history = time_history[-max_points:]
                ear_history = ear_history[-max_points:]

            # Update Matplotlib plot.
            if len(time_history) > 1:
                line.set_data(time_history, ear_history)

                ax.set_xlim(
                    max(0, time_history[-1] - 10),
                    max(10, time_history[-1])
                )

                ax.set_ylim(
                    0,
                    max(0.5, max(ear_history) + 0.05)
                )

                fig.canvas.draw()
                fig.canvas.flush_events()

        else:
            # Do not let a missing face count as continuous eye closure.
            closed_start = None
            send_status("NO_FACE")

            cv2.putText(
                frame,
                "NO FACE DETECTED",
                (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                2
            )

        # Display webcam.
        cv2.imshow("Drowsiness Detection", frame)

        # ESC to exit.
        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break

finally:
    # Try to switch off external outputs before releasing the serial port.
    send_status("NO_FACE")

    cap.release()
    cv2.destroyAllWindows()

    landmarker.close()

    if esp32 is not None and esp32.is_open:
        esp32.close()

    plt.ioff()
    plt.close("all")

    print("Program stopped.")
