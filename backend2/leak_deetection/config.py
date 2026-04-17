# config.py
import os

DB_URI = os.getenv(
    "DB_URI",
    "mysql+mysqlconnector://root:wail@localhost/palestine_land_system_v5"
)


MODEL_DIR  = os.getenv("MODEL_DIR", os.path.join("leak_deetection", "models"))
MODEL_PATH = os.path.join(MODEL_DIR, "xgb_model.pkl")
COLS_PATH  = os.path.join(MODEL_DIR, "feature_columns.pkl")