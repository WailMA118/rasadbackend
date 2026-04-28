# fraud_detection/config.py
"""
إعدادات نظام كشف الاحتيال
"""

import os

# إعدادات قاعدة البيانات
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = os.getenv("DB_PASSWORD", "wail")
DB_NAME = "palestine_land_system_v5"

# مسارات النماذج والملفات
MODEL_DIR = os.path.join("fraud_detection", "models")
MODEL_PATH = os.path.join(MODEL_DIR, "fraud_model.pkl")
FEATURES_PATH = os.path.join(MODEL_DIR, "feature_columns.pkl")
RESULTS_PATH = os.path.join(MODEL_DIR, "training_results.json")
DATASET_PATH = os.path.join(MODEL_DIR, "training_dataset.csv")

# إعدادات النموذج
RANDOM_STATE = 42
TEST_SIZE = 0.3
N_ESTIMATORS = 300
MAX_DEPTH = 10

# عتبات المخاطر
HIGH_RISK_THRESHOLD = 0.7
MEDIUM_RISK_THRESHOLD = 0.4

# فئات التنبؤ
PREDICTION_LABELS = {
    0: "Not Suspicious",
    1: "Suspicious"
}

RISK_LEVELS = {
    "Low": "مخاطر منخفضة - حالة طبيعية",
    "Medium": "مخاطر متوسطة - يُنصح بالمراقبة",
    "High": "مخاطر عالية جداً - يُنصح بالتحقيق الفوري"
}