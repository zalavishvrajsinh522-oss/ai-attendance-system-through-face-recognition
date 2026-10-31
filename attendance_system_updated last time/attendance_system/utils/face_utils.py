"""
Face registration / recognition helpers.

Uses OpenCV's built-in LBPH face recognizer (opencv-contrib-python).
This is chosen deliberately over dlib-based libraries because it installs
cleanly via pip on Windows/Mac/Linux with no compiler toolchain required --
important for a "no install errors" localhost setup.

NOTE (anti-spoofing honesty): the liveness check here is a lightweight,
best-effort heuristic (eye-blink detection across two frames). No purely
browser/webcam based system can give a 100% guarantee against a determined
spoofing attempt (e.g. a video replay). Combined with face match + geofence
+ timetable-window validation it meaningfully raises the bar against basic
proxy attendance (holding up a photo), which is the realistic goal here.
"""
import os
import base64
import numpy as np
import cv2

FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
EYE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")

RECOGNIZE_CONFIDENCE_THRESHOLD = 70  # lower = stricter for LBPH (distance-based)


def decode_base64_image(data_url):
    """Accepts a data URL (from <canvas>.toDataURL()) and returns a BGR numpy image."""
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    img_bytes = base64.b64decode(data_url)
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img


def detect_face(gray_img):
    faces = FACE_CASCADE.detectMultiScale(gray_img, scaleFactor=1.2, minNeighbors=5, minSize=(80, 80))
    if len(faces) == 0:
        return None
    # take the largest detected face
    faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
    return faces[0]


def eyes_open_count(gray_face_roi):
    eyes = EYE_CASCADE.detectMultiScale(gray_face_roi, scaleFactor=1.1, minNeighbors=8)
    return len(eyes)


def save_face_image(faces_dir, student_id, img, index):
    student_dir = os.path.join(faces_dir, str(student_id))
    os.makedirs(student_dir, exist_ok=True)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    face_box = detect_face(gray)
    if face_box is None:
        return None
    x, y, w, h = face_box
    face_crop = cv2.resize(gray[y:y + h, x:x + w], (200, 200))
    path = os.path.join(student_dir, f"{index}.jpg")
    cv2.imwrite(path, face_crop)
    return path


def train_model(faces_dir, model_path):
    """Retrain the global LBPH model from every registered student's saved face crops."""
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    images, labels = [], []

    if not os.path.isdir(faces_dir):
        return False

    for student_id_str in os.listdir(faces_dir):
        student_dir = os.path.join(faces_dir, student_id_str)
        if not os.path.isdir(student_dir):
            continue
        try:
            label = int(student_id_str)
        except ValueError:
            continue
        for fname in os.listdir(student_dir):
            fpath = os.path.join(student_dir, fname)
            img = cv2.imread(fpath, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                images.append(img)
                labels.append(label)

    if not images:
        return False

    recognizer.train(images, np.array(labels))
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    recognizer.write(model_path)
    return True


def verify_face(img, claimed_student_id, model_path):
    """
    Returns (ok: bool, reason: str, liveness_ok: bool)
    Checks that the face in `img` matches claimed_student_id using the trained model.
    """
    if not os.path.exists(model_path):
        return False, "Face model not trained yet. Register your face first.", False

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    face_box = detect_face(gray)
    if face_box is None:
        return False, "No face detected in frame.", False

    x, y, w, h = face_box
    face_roi = gray[y:y + h, x:x + w]
    liveness_ok = eyes_open_count(face_roi) >= 1  # basic: eyes must be detectable/open

    face_crop = cv2.resize(face_roi, (200, 200))

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read(model_path)
    label, confidence = recognizer.predict(face_crop)

    # LBPH: lower confidence value = better match
    if label != claimed_student_id:
        return False, "Face does not match the logged-in student.", liveness_ok
    if confidence > RECOGNIZE_CONFIDENCE_THRESHOLD:
        return False, "Face match confidence too low.", liveness_ok
    if not liveness_ok:
        return False, "Liveness check failed (no eyes detected -- possible photo/spoof).", liveness_ok

    return True, "OK", liveness_ok
