# data_loader.py
"""
تحميل البيانات من قاعدة البيانات المشتركة مع الـ backend.
- يُعالج أعمدة Geometry بشكل صحيح (MySQL يُرجع WKB/HEX).
- يوفّر load_data() و load_single_parcel() للتنبؤ المباشر.
"""

import pandas as pd
from sqlalchemy import create_engine, text
from config import DB_URI


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(DB_URI, pool_pre_ping=True)
    return _engine


# ─── الجداول وأعمدتها مع تحويل Geometry -> WKT ──────────────────────────────

_QUERIES = {
    "parcels": """
        SELECT
            parcel_id,
            basin_number,
            parcel_number,
            locality_id,
            land_type_id,
            oslo_id,
            leakage_label,
            registration_status,
            area_m2,
            ST_AsText(geom) AS geom
        FROM land_parcels
    """,

    "transactions": """
        SELECT
            transaction_id,
            parcel_id,
            seller_id,
            buyer_id,
            shares_sold,
            transaction_date,
            price,
            transaction_type
        FROM land_transactions
    """,

    "ownership": """
        SELECT
            ownership_id,
            parcel_id,
            owner_id,
            ownership_shares,
            start_date,
            end_date
        FROM parcel_ownership
    """,

    "owners": """
        SELECT
            owner_id,
            identity_type,
            owner_type,
            full_name,
            national_id,
            residence_country
        FROM owners
    """,

    "risk": """
        SELECT
            owner_id,
            risk_type,
            risk_score
        FROM owner_risk_profiles
    """,

    "settlements": """
        SELECT
            settlement_id,
            name,
            type,
            established_year,
            ST_AsText(geom) AS geom
        FROM settlements
    """,

    "poa": """
        SELECT
            poa_id,
            parcel_id,
            principal_owner_id,
            agent_id,
            issue_date,
            expiry_date
        FROM power_of_attorney
    """,

    "confiscations": """
        SELECT
            order_id,
            parcel_id,
            order_type,
            issue_date
        FROM confiscation_orders
    """,

    "expansion": """
        SELECT
            expansion_id,
            settlement_id,
            recorded_year,
            ST_AsText(geom) AS geom
        FROM settlement_expansion_history
    """,

    "oslo_zones": """
        SELECT
            zone_id,
            class
        FROM oslo_zones
    """,

    "leakage_cases": """
        SELECT
            case_id,
            parcel_id,
            case_status,
            suspicion_score
        FROM leakage_cases
    """,
}


def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
    """تحويل bytearray/bytes -> str لتجنب أخطاء الهاش."""
    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].apply(
                lambda x: x.decode("utf-8", errors="replace")
                if isinstance(x, (bytes, bytearray))
                else x
            )
    return df


def load_data() -> dict[str, pd.DataFrame]:
    """تحميل كل الجداول دفعةً واحدة."""
    engine = get_engine()
    data: dict[str, pd.DataFrame] = {}

    with engine.connect() as conn:
        for key, query in _QUERIES.items():
            try:
                df = pd.read_sql(text(query), conn)
                data[key] = _clean_df(df)
            except Exception as e:
                print(f"[data_loader] تعذّر تحميل '{key}': {e}")
                data[key] = pd.DataFrame()

    _print_summary(data)
    return data


def load_single_parcel(parcel_id: int) -> dict[str, pd.DataFrame]:
    """
    تحميل بيانات قطعة واحدة فقط (للتنبؤ الفوري من الـ backend).
    يُعيد نفس هيكل load_data() لكن مُفلترًا.
    """
    engine = get_engine()
    data = load_data()   # نحتاج الـ settlements والـ owners وغيرها كاملة

    # تصفية ما يخص القطعة
    for key in ("parcels", "transactions", "ownership", "confiscations", "poa", "leakage_cases"):
        if "parcel_id" in data[key].columns:
            data[key] = data[key][data[key]["parcel_id"] == parcel_id].copy()

    return data


def _print_summary(data: dict[str, pd.DataFrame]):
    print("\n[data_loader] تم التحميل:")
    for k, v in data.items():
        print(f"   {k:<20} -> {v.shape}")


def get_parcel_by_composite_key(basin_number: str, parcel_number: str, locality_id: str) -> pd.DataFrame:
    """
    الحصول على بيانات القطعة باستخدام المفتاح المركب:
    - basin_number
    - parcel_number
    - locality_id
    
    يعيد DataFrame بصف واحد أو None إذا لم توجد القطعة
    """
    engine = get_engine()
    
    query = """
        SELECT
            parcel_id,
            basin_number,
            parcel_number,
            locality_id,
            land_type_id,
            oslo_id,
            leakage_label,
            registration_status,
            area_m2
        FROM land_parcels
        WHERE basin_number = :basin_num
        AND parcel_number = :parcel_num
        AND locality_id = :local_id
        LIMIT 1
    """
    
    try:
        with engine.connect() as conn:
            df = pd.read_sql(
                text(query),
                conn,
                params={
                    "basin_num": basin_number,
                    "parcel_num": parcel_number,
                    "local_id": locality_id
                }
            )
            return _clean_df(df) if not df.empty else None
    except Exception as e:
        print(f"[data_loader] ❌ خطأ في البحث عن القطعة: {e}")
        return None