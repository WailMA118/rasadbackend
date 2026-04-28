# predict.py
"""
التنبؤ بدرجة خطر التسريب لكل قطعة أرض.
 
يدعم وضعَين:
  1. batch_predict()  → لكل القطع (دفعة)
  2. predict_parcel() → لقطعة واحدة (من الـ backend مباشرة)
 
يضمن توافق الأعمدة مع ما تدرّب عليه النموذج.
"""
 
import joblib
import pandas as pd
import numpy as np
 
from leak_deetection.data_loader import load_data, load_single_parcel
from leak_deetection.feature_engineering import build_dataset
from leak_deetection.geo_features import GeoFeatureEngineer
from leak_deetection.config import MODEL_PATH, COLS_PATH
 
_LABEL_MAP = {0: "safe", 1: "suspected", 2: "leaked"}
 
# ─── تحميل النموذج عند الاستيراد ──────────────────────────────────────────
 
def _load_artifacts():
    model = joblib.load(MODEL_PATH)
    feature_cols = joblib.load(COLS_PATH)
    return model, feature_cols
 
try:
    _model, _feature_cols = _load_artifacts()
    print(f"[predict] النموذج محمّل ({len(_feature_cols)} ميزة)")
except FileNotFoundError:
    _model, _feature_cols = None, None
    print("[predict] لم يُعثر على النموذج. شغّل train_model.py أولًا.")
 
 
# ─── تجهيز مصفوفة الميزات (مع ضمان التوافق) ──────────────────────────────
 
def _prepare_features(df: pd.DataFrame, feature_cols: list) -> pd.DataFrame:
    # one-hot لأي عمود فئوي متبقٍّ
    df = pd.get_dummies(df, drop_first=True)
    df = df.select_dtypes(include=["int64", "int32", "float64", "float32", "bool", "uint8"])
 
    # إضافة الأعمدة الناقصة بقيمة 0
    for col in feature_cols:
        if col not in df.columns:
            df[col] = 0
 
    # الترتيب نفسه كوقت التدريب
    return df[feature_cols]
 
 
# ─── 1. تنبؤ دفعي (batch) ────────────────────────────────────────────────
 
def batch_predict(save_csv: bool = True) -> pd.DataFrame:
    if _model is None:
        raise RuntimeError("النموذج غير محمّل. شغّل train_model.py أولًا.")
 
    print("\nتحميل البيانات ...")
    data = load_data()
 
    print("\nبناء الميزات ...")
    df = build_dataset(data)
 
    if not data["parcels"].empty and not data["settlements"].empty:
        print("\nالميزات الجغرافية ...")
        geo_eng = GeoFeatureEngineer(
            parcels_df    =data["parcels"],
            settlements_df=data["settlements"],
            expansion_df  =data.get("expansion"),
        )
        geo_df = geo_eng.run()
        df = df.merge(geo_df, on="parcel_id", how="left")
 
    df.fillna(0, inplace=True)
 
    # أعمدة لا تدخل في النموذج
    meta_cols = ["parcel_id", "leakage_label"]
    meta = df[[c for c in meta_cols if c in df.columns]].copy()
 
    drop_cols = [
        "leakage_label", "geom", "parcel_number", "basin_number",
        "locality_id", "land_type_id", "oslo_id",
        "registration_status", "oslo_class",
    ]
    X_raw = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")
 
    X = _prepare_features(X_raw, _feature_cols)
 
    # تنبؤ
    probs  = _model.predict_proba(X)
    preds  = _model.predict(X)
 
    result = meta.copy()
    result["risk_score"]       = np.round(probs[:, 2] * 100, 2)   # احتمال "leaked" %
    result["suspected_score"]  = np.round(probs[:, 1] * 100, 2)
    result["prediction"]       = pd.Series(preds).map(_LABEL_MAP).values
    result["confidence"]       = np.round(probs.max(axis=1) * 100, 2)
 
    if save_csv:
        out_path = "predictions.csv"
        result.to_csv(out_path, index=False)
        print(f"\nالنتائج محفوظة → {out_path}")
 
    print(f"\nتوزيع التنبؤات:\n{result['prediction'].value_counts()}")
    print(result[["parcel_id", "risk_score", "prediction", "confidence"]].head(10))
    return result
 
 
# ─── 2. تنبؤ لقطعة واحدة (للـ backend) ─────────────────────────────────
 
def predict_parcel(parcel_id: int) -> dict:
    """
    يُعيد dict جاهز للإرسال كـ JSON response من FastAPI.
 
    مثال الاستخدام في route:
        from predict import predict_parcel
        result = await asyncio.to_thread(predict_parcel, parcel_id)
    """
    if _model is None:
        raise RuntimeError("النموذج غير محمّل.")
 
    data = load_single_parcel(parcel_id)
 
    if data["parcels"].empty:
        return {"error": f"لا توجد قطعة بـ id={parcel_id}"}
 
    df = build_dataset(data)
 
    if not data["parcels"].empty and not data["settlements"].empty:
        geo_eng = GeoFeatureEngineer(
            parcels_df    =data["parcels"],
            settlements_df=data["settlements"],
            expansion_df  =data.get("expansion"),
        )
        geo_df = geo_eng.run()
        df = df.merge(geo_df, on="parcel_id", how="left")
 
    df.fillna(0, inplace=True)
 
    drop_cols = [
        "leakage_label", "geom", "parcel_number", "basin_number",
        "locality_id", "land_type_id", "oslo_id",
        "registration_status", "oslo_class",
    ]
    X_raw = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")
    X = _prepare_features(X_raw, _feature_cols)
 
    probs = _model.predict_proba(X)[0]
    pred  = int(_model.predict(X)[0])
 
    return {
        "parcel_id"      : int(parcel_id),
        "prediction"     : _LABEL_MAP[pred],
        "risk_score"     : round(float(probs[2]) * 100, 2),
        "suspected_score": round(float(probs[1]) * 100, 2),
        "safe_score"     : round(float(probs[0]) * 100, 2),
        "confidence"     : round(float(probs.max()) * 100, 2),
    }
 
 
# ─── تشغيل مباشر ──────────────────────────────────────────────────────────
 
if __name__ == "__main__":
    batch_predict()