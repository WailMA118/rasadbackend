# train_model.py
"""
تدريب نموذج XGBoost لاكتشاف تسريب الأراضي.
 
الميزات الجديدة:
  - يدمج الميزات الجغرافية (geo_features)
  - يتعامل مع عدم توازن الفئات (scale_pos_weight / sample_weight)
  - يحفظ قائمة الأعمدة لضمان التوافق مع predict.py
  - يستخدم Stratified K-Fold للتقييم
"""
 
import os
import joblib
import pandas as pd
import numpy as np
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier
 
from data_loader import load_data
from feature_engineering import build_dataset
from geo_features import GeoFeatureEngineer
from config import MODEL_DIR, MODEL_PATH, COLS_PATH
 
# ─── الثوابت ──────────────────────────────────────────────────────────────
 
TARGET_MAP = {"safe": 0, "suspected": 1, "leaked": 2}
RANDOM_STATE = 42
 
# أعمدة يجب حذفها قبل التدريب
_NON_FEATURE_COLS = [
    "leakage_label", "geom", "parcel_number", "basin_number",
    "locality_id", "land_type_id", "oslo_id",
    "registration_status", "oslo_class",   # ممثَّلة بـ one-hot
]
 
 
def prepare_xy(df: pd.DataFrame):
    y = df["leakage_label"].map(TARGET_MAP) if "leakage_label" in df.columns else None
 
    drop = [c for c in _NON_FEATURE_COLS if c in df.columns]
    X = df.drop(columns=drop, errors="ignore")
 
    # one-hot لأي عمود فئوي متبقٍّ
    X = pd.get_dummies(X, drop_first=True)
 
    # أعمدة رقمية فقط
    X = X.select_dtypes(include=["int64", "int32", "float64", "float32", "bool", "uint8"])
 
    return X, y
 
 
def main():
    os.makedirs(MODEL_DIR, exist_ok=True)
 
    # ── 1. تحميل البيانات ─────────────────────────────────────────────
    print("\n📦 تحميل البيانات …")
    data = load_data()
 
    # ── 2. الميزات النصية/الرقمية ─────────────────────────────────────
    print("\n⚙️  بناء الميزات …")
    df = build_dataset(data)
 
    # ── 3. الميزات الجغرافية ──────────────────────────────────────────
    if not data["parcels"].empty and not data["settlements"].empty:
        print("\n🗺️  حساب الميزات الجغرافية …")
        geo_eng = GeoFeatureEngineer(
            parcels_df    =data["parcels"],
            settlements_df=data["settlements"],
            expansion_df  =data.get("expansion"),
        )
        geo_df = geo_eng.run()
        df = df.merge(geo_df, on="parcel_id", how="left")
    else:
        print("\n⚠️  لا توجد بيانات جغرافية، يتم التخطي …")
 
    df.fillna(0, inplace=True)
 
    # ── 4. التحقق من وجود بيانات مُصنَّفة ────────────────────────────
    if "leakage_label" not in df.columns or df["leakage_label"].isna().all():
        raise ValueError("لا توجد بيانات مُصنَّفة في 'leakage_label'")
 
    labeled = df[df["leakage_label"].notna() & df["leakage_label"].isin(TARGET_MAP)]
    print(f"\n📊 توزيع الفئات:\n{labeled['leakage_label'].value_counts()}\n")
 
    X, y = prepare_xy(labeled)
 
    if y is None or y.isna().all():
        raise ValueError("لا يمكن بناء المتغير الهدف")
 
    valid_mask = y.notna()
    X, y = X[valid_mask], y[valid_mask]
 
    # ── 5. حفظ أعمدة التدريب ─────────────────────────────────────────
    joblib.dump(list(X.columns), COLS_PATH)
    print(f"✅ تم حفظ {len(X.columns)} عمود → {COLS_PATH}")
 
    # ── 6. أوزان الفئات (لمعالجة عدم التوازن) ─────────────────────────
    sample_weights = compute_sample_weight("balanced", y=y)
 
    # ── 7. تدريب النموذج ──────────────────────────────────────────────
    print("\n🚀 تدريب النموذج …")
    model = XGBClassifier(
        n_estimators   =300,
        max_depth      =6,
        learning_rate  =0.05,
        subsample      =0.8,
        colsample_bytree=0.8,
        objective      ="multi:softprob",
        num_class      =3,
        eval_metric    ="mlogloss",
        random_state   =RANDOM_STATE,
        n_jobs         =-1,
    )
    model.fit(X, y, sample_weight=sample_weights)
 
    # ── 8. تقييم بـ Stratified K-Fold ─────────────────────────────────
    print("\n📈 تقييم Stratified 5-Fold …")
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    cv_scores = []
    for train_idx, val_idx in skf.split(X, y):
        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]
        w_train, w_val = sample_weights[train_idx], sample_weights[val_idx]
        
        model_cv = XGBClassifier(
            n_estimators   =300,
            max_depth      =6,
            learning_rate  =0.05,
            subsample      =0.8,
            colsample_bytree=0.8,
            objective      ="multi:softprob",
            num_class      =3,
            eval_metric    ="mlogloss",
            random_state   =RANDOM_STATE,
            n_jobs         =-1,
        )
        model_cv.fit(X_train, y_train, sample_weight=w_train)
        y_pred_val = model_cv.predict(X_val)
        fold_f1 = np.mean(
            [((y_pred_val == i) & (y_val == i)).sum() / (y_val == i).sum() 
             for i in range(3) if (y_val == i).sum() > 0]
        )
        cv_scores.append(fold_f1)
    
    cv_scores = np.array(cv_scores)
    print(f"   F1-Macro (CV): {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")
 
    # تقرير كامل
    y_pred = model.predict(X)
    print("\n📋 تقرير التصنيف (على بيانات التدريب):")
    print(classification_report(y, y_pred, target_names=["safe", "suspected", "leaked"]))
    print("Confusion Matrix:\n", confusion_matrix(y, y_pred))
 
    # ── 9. حفظ النموذج ────────────────────────────────────────────────
    joblib.dump(model, MODEL_PATH)
    print(f"\n✅ تم حفظ النموذج → {MODEL_PATH}")
 
 
if __name__ == "__main__":
    main()
 