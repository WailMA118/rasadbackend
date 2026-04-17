# feature_engineering.py
"""
بناء مجموعة الميزات الكاملة للنموذج من جداول الـ backend.

الفئات المُعالجة:
  A) ميزات الأسعار والمعاملات
  B) ميزات المشتري حسب نوع الهوية (كل أنواع الهوية الموجودة في النموذج)
  C) ميزات مخاطر المالك
  D) ميزات توكيل الملكية (POA) — مؤشر احتيال قوي
  E) ميزات أوامر الحجز/المصادرة
  F) ميزات الملكية الحالية
  G) ميزات قضايا التسريب التاريخية
  H) ترميز الأعمدة الفئوية (registration_status، oslo_zone)
"""

import pandas as pd
import numpy as np


# ─── A: أسعار المعاملات ────────────────────────────────────────────────────

def compute_price_features(transactions: pd.DataFrame) -> pd.DataFrame:
    t = transactions.copy()
    t["price"] = pd.to_numeric(t["price"], errors="coerce").fillna(0)
    t["shares_sold"] = pd.to_numeric(t["shares_sold"], errors="coerce").replace(0, np.nan)
    t["price_per_share"] = t["price"] / t["shares_sold"]

    agg = t.groupby("parcel_id").agg(
        price_mean   =("price_per_share", "mean"),
        price_min    =("price_per_share", "min"),
        price_max    =("price_per_share", "max"),
        price_std    =("price_per_share", "std"),
        num_tx       =("transaction_id",  "count"),
        total_value  =("price",           "sum"),
        gift_ratio   =("transaction_type", lambda x: (x == "gift").mean()),
        inherit_ratio=("transaction_type", lambda x: (x == "inheritance").mean()),
        confiscation_tx=("transaction_type", lambda x: (x == "confiscation").mean()),
    ).reset_index()

    agg["price_std"] = agg["price_std"].fillna(0)
    return agg


# ─── B: تصنيف المشترين حسب نوع الهوية ────────────────────────────────────

# كل أنواع هوية الـ backend (Owner.identity_type)
_ID_GROUPS = {
    "West Bank ID":       "WB",
    "Jerusalem ID":       "JR",
    "Gaza ID":            "GZ",
    "Israeli_ID":         "IL",
    "Jordanian Passport": "JO",
    "Foreign Passport":   "FP",
    "Corporate/Org":      "CO",
}

def compute_owner_features(transactions: pd.DataFrame, owners: pd.DataFrame) -> pd.DataFrame:
    df = transactions.merge(
        owners[["owner_id", "identity_type", "owner_type", "residence_country"]],
        left_on="buyer_id", right_on="owner_id", how="left"
    )

    df["buyer_group"] = df["identity_type"].map(_ID_GROUPS).fillna("OTHER")

    # نسبة كل فئة هوية لكل قطعة
    group_ratios = (
        df.groupby("parcel_id")["buyer_group"]
        .value_counts(normalize=True)
        .unstack()
        .fillna(0)
    )
    group_ratios.columns = [f"buyer_{c}_ratio" for c in group_ratios.columns]

    # هل هناك مشترٍ مؤسسي؟
    df["is_corporate"] = (df["owner_type"] == "company").astype(int)
    corp_flag = df.groupby("parcel_id")["is_corporate"].max().rename("has_corporate_buyer")

    # هل المشتري مقيم خارج فلسطين؟
    df["is_foreign_resident"] = (
        ~df["residence_country"].isin(["Palestine", "", None])
        & df["residence_country"].notna()
    ).astype(int)
    foreign_flag = df.groupby("parcel_id")["is_foreign_resident"].max().rename("has_foreign_resident_buyer")

    result = group_ratios.join(corp_flag).join(foreign_flag).reset_index()
    return result


# ─── C: مخاطر المالك ──────────────────────────────────────────────────────

def compute_risk_features(transactions: pd.DataFrame, risk: pd.DataFrame) -> pd.DataFrame:
    # نقيّم كلًا من البائع والمشتري
    buyer_risk  = transactions.merge(risk, left_on="buyer_id",  right_on="owner_id", how="left")
    seller_risk = transactions.merge(risk, left_on="seller_id", right_on="owner_id", how="left")

    buyer_agg = buyer_risk.groupby("parcel_id").agg(
        buyer_risk_mean=("risk_score", "mean"),
        buyer_risk_max =("risk_score", "max"),
    ).reset_index()

    seller_agg = seller_risk.groupby("parcel_id").agg(
        seller_risk_mean=("risk_score", "mean"),
        seller_risk_max =("risk_score", "max"),
    ).reset_index()

    # أنواع المخاطر كـ one-hot
    risk_types = pd.get_dummies(risk["risk_type"], prefix="rt")
    risk["has_suspicious"]   = risk_types.get("rt_suspicious_activity", 0)
    risk["has_blacklisted"]  = risk_types.get("rt_blacklisted", 0)
    risk["has_foreign_entity"] = risk_types.get("rt_foreign_entity", 0)

    buyer_flags = transactions.merge(
        risk[["owner_id", "has_suspicious", "has_blacklisted", "has_foreign_entity"]],
        left_on="buyer_id", right_on="owner_id", how="left"
    ).groupby("parcel_id")[["has_suspicious", "has_blacklisted", "has_foreign_entity"]].max().reset_index()

    result = buyer_agg.merge(seller_agg, on="parcel_id", how="outer")
    result = result.merge(buyer_flags, on="parcel_id", how="outer")
    result = result.fillna(0)
    return result


# ─── D: توكيلات الملكية (POA) ─────────────────────────────────────────────

def compute_poa_features(poa: pd.DataFrame) -> pd.DataFrame:
    if poa.empty:
        return pd.DataFrame(columns=["parcel_id", "num_poa", "poa_expired_ratio"])

    poa = poa.copy()
    poa["expiry_date"] = pd.to_datetime(poa["expiry_date"], errors="coerce")
    poa["is_expired"]  = (poa["expiry_date"] < pd.Timestamp.now()).astype(int)

    agg = poa.groupby("parcel_id").agg(
        num_poa          =("poa_id",     "count"),
        poa_expired_ratio=("is_expired", "mean"),
        poa_unique_agents=("agent_id",   "nunique"),
    ).reset_index()

    return agg


# ─── E: أوامر الحجز والمصادرة ──────────────────────────────────────────────

def compute_confiscation_features(confiscations: pd.DataFrame) -> pd.DataFrame:
    if confiscations.empty:
        return pd.DataFrame(columns=["parcel_id", "num_confiscations"])

    agg = confiscations.groupby("parcel_id").agg(
        num_confiscations=("order_id", "count"),
    ).reset_index()

    return agg


# ─── F: ميزات الملكية الحالية ─────────────────────────────────────────────

def compute_ownership_features(ownership: pd.DataFrame) -> pd.DataFrame:
    if ownership.empty:
        return pd.DataFrame(columns=["parcel_id", "num_owners", "ownership_fragmentation"])

    active = ownership[ownership["end_date"] == "9999-12-31"].copy() if "end_date" in ownership.columns else ownership.copy()

    agg = active.groupby("parcel_id").agg(
        num_owners =("owner_id",         "nunique"),
        total_shares=("ownership_shares", "sum"),
    ).reset_index()

    # تشتّت الملكية: كلما زاد عدد الملاك كلما ارتفع الخطر
    agg["ownership_fragmentation"] = agg["num_owners"] / (agg["total_shares"] + 1e-5)
    return agg


# ─── G: قضايا التسريب السابقة ─────────────────────────────────────────────

def compute_case_features(leakage_cases: pd.DataFrame) -> pd.DataFrame:
    if leakage_cases.empty:
        return pd.DataFrame(columns=["parcel_id", "num_cases", "max_suspicion_score", "has_open_case"])

    agg = leakage_cases.groupby("parcel_id").agg(
        num_cases           =("case_id",         "count"),
        max_suspicion_score =("suspicion_score",  "max"),
        has_open_case       =("case_status",       lambda x: (x == "open").any().astype(int)),
    ).reset_index()

    return agg


# ─── H: ترميز الأعمدة الفئوية ─────────────────────────────────────────────

def encode_categorical(df: pd.DataFrame, oslo_zones: pd.DataFrame) -> pd.DataFrame:
    # registration_status
    reg_dummies = pd.get_dummies(df["registration_status"], prefix="reg")
    df = pd.concat([df, reg_dummies], axis=1)

    # oslo_zone
    if not oslo_zones.empty and "oslo_id" in df.columns:
        df = df.merge(oslo_zones.rename(columns={"zone_id": "oslo_id", "class": "oslo_class"}),
                      on="oslo_id", how="left")
        oslo_dummies = pd.get_dummies(df["oslo_class"], prefix="oslo")
        df = pd.concat([df, oslo_dummies], axis=1)

    # حذف الأعمدة الأصلية 
    drop_cols = ["registration_status", "oslo_class", "basin_number",
                 "parcel_number", "geom",
                 "locality_id", "land_type_id", "oslo_id"]
    df.drop(columns=[c for c in drop_cols if c in df.columns], inplace=True)

    return df


# ─── الدالة الرئيسية ───────────────────────────────────────────────────────

def build_dataset(data: dict) -> pd.DataFrame:
    parcels      = data["parcels"]
    transactions = data["transactions"]
    owners       = data["owners"]
    risk         = data["risk"]
    poa          = data.get("poa",          pd.DataFrame())
    confiscations= data.get("confiscations",pd.DataFrame())
    ownership    = data.get("ownership",    pd.DataFrame())
    leakage_cases= data.get("leakage_cases",pd.DataFrame())
    oslo_zones   = data.get("oslo_zones",   pd.DataFrame())

    df = parcels.copy()
    df["area_m2"] = pd.to_numeric(df["area_m2"], errors="coerce").fillna(0)

    if not transactions.empty:
        df = df.merge(compute_price_features(transactions),        on="parcel_id", how="left")
        df = df.merge(compute_owner_features(transactions, owners), on="parcel_id", how="left")
        df = df.merge(compute_risk_features(transactions, risk),    on="parcel_id", how="left")

    df = df.merge(compute_poa_features(poa),                       on="parcel_id", how="left")
    df = df.merge(compute_confiscation_features(confiscations),     on="parcel_id", how="left")
    df = df.merge(compute_ownership_features(ownership),            on="parcel_id", how="left")
    df = df.merge(compute_case_features(leakage_cases),             on="parcel_id", how="left")

    df = encode_categorical(df, oslo_zones)

    df.fillna(0, inplace=True)

    print(f"[feature_engineering] ✅ Dataset: {df.shape[0]} rows × {df.shape[1]} cols")
    return df