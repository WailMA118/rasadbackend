# fraud_detection/predict.py
"""
التنبؤ بكشف الأشخاص المتورطين في عمليات التسريب

يدعم وضعين:
  1. batch_predict() → لجميع الأشخاص (دفعة)
  2. predict_person() → لشخص واحد
"""

import pandas as pd
import numpy as np
import os
import mysql.connector
import pickle
import json
from datetime import datetime

# ─── الإعدادات ──────────────────────────────────────────────────────────────

HOST = "localhost"
USER = "root"
PASSWORD = os.getenv("DB_PASSWORD", "wail")
DATABASE = "palestine_land_system_v5"
MODEL_DIR = os.path.join("fraud_detection", "models")
MODEL_PATH = os.path.join(MODEL_DIR, "fraud_model.pkl")
FEATURES_PATH = os.path.join(MODEL_DIR, "feature_columns.pkl")

# استيراد دوال من train_model
import sys
import os
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

try:
    from train_model import (
        get_connection, load_data, compute_seller_features,
        compute_buyer_features, compute_owner_identity_features,
        build_dataset
    )
except ImportError as e:
    print(f"[WARNING] استيراد محلي فشل: {e}")
    raise

# ─── تحميل النموذج ─────────────────────────────────────────────────────────

_model = None
_feature_cols = None

def _load_artifacts():
    """تحميل النموذج والميزات عند الاستيراد"""
    global _model, _feature_cols
    try:
        with open(MODEL_PATH, "rb") as f:
            _model = pickle.load(f)
        with open(FEATURES_PATH, "rb") as f:
            _feature_cols = pickle.load(f)
        print(f"[fraud_predict] ✅ النموذج محمّل ({len(_feature_cols)} ميزة)")
        return True
    except FileNotFoundError:
        print("[fraud_predict] ⚠️  لم يُعثر على النموذج. شغّل train_model.py أولاً.")
        return False

# تحميل النموذج عند الاستيراد
_load_artifacts()

# ─── دوال التنبؤ ───────────────────────────────────────────────────────────

def _prepare_features(df, feature_cols):
    """تجهيز مصفوفة الميزات مع ضمان التوافق"""
    for col in feature_cols:
        if col not in df.columns:
            df[col] = 0
    return df[feature_cols]

def batch_predict(save_csv: bool = False):
    """
    التنبؤ لجميع الأشخاص المتورطين (دفعة)

    المعاملات:
        save_csv: حفظ النتائج كملف CSV

    الإرجاع:
        dict: نتائج التنبؤ بتنسيق JSON
    """
    if _model is None:
        return {
            "status": "error",
            "message": "النموذج غير محمّل. شغّل train_model.py أولاً."
        }

    try:
        print("\n📦 تحميل البيانات...")
        data = load_data()

        print("\n⚙️  بناء الميزات...")
        df, feature_cols = build_dataset(data)

        df.fillna(0, inplace=True)

        # الاحتفاظ بـ owner_id والمعلومات الإضافية
        meta = df[["owner_id", "full_name", "identity_group", "involvement_type"]].copy()

        # إزالة الأعمدة غير المطلوبة
        drop_cols = ["is_involved_in_fraud"]
        X_raw = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")

        X = _prepare_features(X_raw, _feature_cols)

        # التنبؤ
        print("\n🔮 التنبؤ...")
        preds = _model.predict(X)
        probs = _model.predict_proba(X) if hasattr(_model, "predict_proba") else None

        # بناء النتائج
        results = []
        suspicious_people = []

        for i, row in meta.iterrows():
            owner_id = int(row["owner_id"])
            full_name = row["full_name"]
            prediction = int(preds[i])
            probability = float(probs[i][1]) if probs is not None else 0.0

            if probability > 0.4:  # إذا كانت احتمالية الاحتيال أكثر من 40%
                result = {
                    "owner_id": owner_id,
                    "full_name": full_name,
                    "identity_group": row["identity_group"],
                    "involvement_type": row["involvement_type"],
                    "is_suspicious": int(prediction),
                    "fraud_probability": round(probability, 4),
                    "confidence": round(max(probability, 1-probability), 4),
                    "risk_level": "High" if probability > 0.7 else "Medium" if probability > 0.4 else "Low",
                    "risk_description": _get_risk_description(probability, row["involvement_type"])
                }
                results.append(result)
                
                if prediction == 1:
                    suspicious_people.append(result)

        # إحصائيات
        predictions_array = np.array([int(preds[i]) for i in range(len(preds))])
        probabilities_array = np.array([probs[i][1] if probs is not None else 0.0 for i in range(len(preds))])

        stats = {
            "total_people": len(df),
            "suspicious_count": len(suspicious_people),
            "suspicious_percentage": round(float(len(suspicious_people) / len(df) * 100), 2) if len(df) > 0 else 0,
            "avg_fraud_probability": round(float(np.mean(probabilities_array)), 4),
            "high_risk_count": len([r for r in results if r["risk_level"] == "High"]),
            "medium_risk_count": len([r for r in results if r["risk_level"] == "Medium"]),
            "low_risk_count": len([r for r in results if r["risk_level"] == "Low"])
        }

        response = {
            "status": "success",
            "message": "تم التنبؤ بنجاح - تحديد الأشخاص المشبوهين",
            "timestamp": datetime.now().isoformat(),
            "statistics": stats,
            "suspicious_people": suspicious_people,
            "all_results": results
        }

        if save_csv:
            output_path = os.path.join(MODEL_DIR, "suspicious_people.csv")
            results_df = pd.DataFrame(suspicious_people)
            results_df.to_csv(output_path, index=False)
            response["csv_path"] = output_path
            print(f"✅ تم حفظ النتائج → {output_path}")

        print(f"\n📊 إحصائيات التنبؤ:")
        print(f"   المجموع: {stats['total_people']}")
        print(f"   مشبوهين: {stats['suspicious_count']} ({stats['suspicious_percentage']}%)")

        return response

    except Exception as e:
        return {
            "status": "error",
            "message": f"خطأ في التنبؤ: {str(e)}"
        }

def predict_person(owner_id: int):
    """
    التنبؤ لشخص واحد

    المعاملات:
        owner_id: معرف الشخص

    الإرجاع:
        dict: نتيجة التنبؤ بتنسيق JSON
    """
    if _model is None:
        return {
            "status": "error",
            "message": "النموذج غير محمّل. شغّل train_model.py أولاً."
        }

    try:
        conn = get_connection()

        # التحقق من وجود الشخص
        owner_check = pd.read_sql("SELECT owner_id, full_name FROM owners WHERE owner_id = %s", conn, params=[owner_id])
        if owner_check.empty:
            conn.close()
            return {
                "status": "error",
                "message": f"لا يوجد شخص بالمعرف {owner_id}"
            }

        full_name = owner_check["full_name"].iloc[0]

        # تحميل البيانات الكاملة
        data = load_data()
        
        # بناء البيانات وتصفيتها للشخص المحدد
        df, feature_cols = build_dataset(data)
        
        person_data = df[df["owner_id"] == owner_id]
        
        if person_data.empty:
            conn.close()
            return {
                "status": "error",
                "message": f"لا توجد بيانات كافية للشخص {owner_id}"
            }

        person_data.fillna(0, inplace=True)

        # إزالة الأعمدة غير المطلوبة
        drop_cols = ["is_involved_in_fraud"]
        X_raw = person_data.drop(columns=[c for c in drop_cols if c in person_data.columns], errors="ignore")
        X = _prepare_features(X_raw, _feature_cols)

        # التنبؤ
        pred = int(_model.predict(X)[0])
        probs = _model.predict_proba(X)[0] if hasattr(_model, "predict_proba") else [0.5, 0.5]

        probability = float(probs[1])
        confidence = round(max(probability, 1-probability), 4)

        # الحصول على معلومات الشخص
        person_info = person_data.iloc[0]

        # تحديد مستوى المخاطر
        if probability > 0.7:
            risk_level = "High"
            risk_description = "مخاطر عالية جداً - يُنصح بالتحقيق الفوري"
        elif probability > 0.4:
            risk_level = "Medium"
            risk_description = "مخاطر متوسطة - يُنصح بالمراقبة الدقيقة"
        else:
            risk_level = "Low"
            risk_description = "مخاطر منخفضة - شخص موثوق"

        conn.close()

        return {
            "status": "success",
            "message": "تم التنبؤ بنجاح",
            "timestamp": datetime.now().isoformat(),
            "person": {
                "owner_id": owner_id,
                "full_name": full_name,
                "identity_group": person_info.get("identity_group", "UNKNOWN"),
                "involvement_type": person_info.get("involvement_type", "none")
            },
            "prediction": {
                "is_suspicious": pred,
                "is_suspicious_text": "مشبوه" if pred == 1 else "غير مشبوه",
                "fraud_probability": round(probability, 4),
                "confidence": confidence,
                "risk_level": risk_level,
                "risk_description": risk_description
            },
            "behavioral_features": {
                "seller_sales_count": int(person_info.get("seller_num_sales", 0)),
                "buyer_purchases_count": int(person_info.get("buyer_num_purchases", 0)),
                "is_corporate": int(person_info.get("is_corporate", 0)),
                "is_foreign_resident": int(person_info.get("is_foreign_resident", 0)),
                "risk_score": float(person_info.get("risk_score", 0))
            },
            "model_info": {
                "type": "RandomForestClassifier",
                "features_count": len(_feature_cols),
                "model_accuracy": "91.64%"
            }
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"خطأ في التنبؤ للشخص {owner_id}: {str(e)}"
        }

def get_model_info():
    """إرجاع معلومات النموذج"""
    if _model is None:
        return {
            "status": "error",
            "message": "النموذج غير محمّل"
        }

    return {
        "status": "success",
        "model_loaded": True,
        "model_type": "Fraud Detection - Person Involvement",
        "model_path": MODEL_PATH,
        "features_path": FEATURES_PATH,
        "features_count": len(_feature_cols) if _feature_cols else 0,
        "model_accuracy": "~91.64%",
        "detects": "أشخاص متورطين في عمليات تسريب الأراضي",
        "feature_names": _feature_cols
    }

# ─── دالة مساعدة ───────────────────────────────────────────────────────────

def _get_risk_description(probability, involvement_type):
    """الحصول على وصف المخاطر"""
    if probability > 0.7:
        return f"خطر عالي جداً - {involvement_type} مشبوه جداً"
    elif probability > 0.4:
        return f"خطر متوسط - {involvement_type} يتطلب مراقبة"
    else:
        return f"خطر منخفض - {involvement_type} موثوق"

# ─── تشغيل مباشر ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🔮 اختبار التنبؤ - كشف الأشخاص المتورطين...")

    # اختبار معلومات النموذج
    info = get_model_info()
    print(json.dumps(info, indent=2, ensure_ascii=False))