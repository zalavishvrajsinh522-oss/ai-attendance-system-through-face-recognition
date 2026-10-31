import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

    _db_url = os.environ.get("DATABASE_URL", "").strip()
    if _db_url:
        # Free cloud MySQL (e.g. Aiven) supplied via .env
        SQLALCHEMY_DATABASE_URI = _db_url
    else:
        # Zero-setup local fallback -- no server/install required
        instance_dir = os.path.join(basedir, "instance")
        os.makedirs(instance_dir, exist_ok=True)
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(instance_dir, "attendance.db")

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DEFAULT_GEOFENCE_RADIUS = float(os.environ.get("DEFAULT_GEOFENCE_RADIUS", 100))
    FACES_DIR = os.path.join(basedir, "static", "faces")
    MODEL_PATH = os.path.join(basedir, "instance", "lbph_model.yml")
