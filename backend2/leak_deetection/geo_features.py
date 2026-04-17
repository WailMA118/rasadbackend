# geo_features.py
"""
حساب الميزات الجغرافية للقطع.
 
الإصلاحات عن النسخة القديمة:
  - MySQL يُرجع WKT بعد ST_AsText() → نستخدم wkt.loads مباشرة.
  - حساب المسافة مُحسَّن: نستخدم unary_union للمستوطنات ثم distance واحدة.
  - حساب الـ CRS: نُحوّل إلى إسقاط متري (EPSG:32636) للمسافات الدقيقة بالمتر.
  - دعم DataFrames فارغة.
"""
 
import pandas as pd
import numpy as np
from shapely import wkt
from shapely.ops import unary_union, transform
import pyproj
from functools import lru_cache
 
 
# إسقاط WGS84 → UTM Zone 36N (مناسب لفلسطين) لحساب المسافات بالمتر
_WGS84 = pyproj.CRS("EPSG:4326")
_UTM36N = pyproj.CRS("EPSG:32636")
_project_to_utm = pyproj.Transformer.from_crs(_WGS84, _UTM36N, always_xy=True).transform
 
 
def _to_utm(geom):
    """تحويل geometry من WGS84 إلى UTM36N."""
    return transform(_project_to_utm, geom)
 
 
def _safe_wkt_load(wkt_str):
    """تحميل WKT مع معالجة الأخطاء."""
    try:
        if wkt_str and isinstance(wkt_str, str):
            return wkt.loads(wkt_str)
    except Exception:
        pass
    return None
 
 
class GeoFeatureEngineer:
    """
    يحسب الميزات الجغرافية لكل قطعة أرض بالنسبة للمستوطنات.
 
    Parameters
    ----------
    parcels_df     : DataFrame يحتوي على عمود 'geom' (WKT) و 'parcel_id'
    settlements_df : DataFrame يحتوي على عمود 'geom' (WKT)
    expansion_df   : DataFrame يحتوي على عمود 'geom' (WKT) — اختياري
    """
 
    def __init__(self, parcels_df: pd.DataFrame,
                 settlements_df: pd.DataFrame,
                 expansion_df: pd.DataFrame | None = None):
 
        self.parcels    = parcels_df.copy()
        self.settlements = settlements_df.copy()
        self.expansion  = expansion_df.copy() if expansion_df is not None else None
 
        # تحميل الـ geometries
        self.parcels["geometry"] = self.parcels["geom"].apply(_safe_wkt_load)
        self.settlements["geometry"] = self.settlements["geom"].apply(_safe_wkt_load)
 
        if self.expansion is not None:
            self.expansion["geometry"] = self.expansion["geom"].apply(_safe_wkt_load)
 
        # ✅ تحسين: دمج كل المستوطنات في geometry واحدة
        valid_settlements = self.settlements["geometry"].dropna().tolist()
        if valid_settlements:
            self._settlements_union = _to_utm(unary_union(valid_settlements))
        else:
            self._settlements_union = None
 
        # ✅ تحسين: دمج كل مناطق التوسع في geometry واحدة
        if self.expansion is not None:
            valid_exp = self.expansion["geometry"].dropna().tolist()
            self._expansion_union = unary_union(valid_exp) if valid_exp else None
        else:
            self._expansion_union = None
 
    # ── حساب المسافة (متر) لكل قطعة ──────────────────────────────────────
 
    def compute_distance_to_settlement(self):
        if self._settlements_union is None:
            self.parcels["dist_to_settlement_m"] = np.nan
            return
 
        def _dist(geom):
            if geom is None:
                return np.nan
            try:
                return _to_utm(geom).distance(self._settlements_union)
            except Exception:
                return np.nan
 
        self.parcels["dist_to_settlement_m"] = self.parcels["geometry"].apply(_dist)
 
    # ── علامة القُرب (أقل من threshold متر) ─────────────────────────────
 
    def compute_near_settlement_flag(self, threshold_m: float = 500.0):
        if "dist_to_settlement_m" not in self.parcels.columns:
            self.compute_distance_to_settlement()
        self.parcels["near_settlement"] = (
            self.parcels["dist_to_settlement_m"] < threshold_m
        ).astype(int)
 
    # ── هل القطعة داخل منطقة توسع؟ ──────────────────────────────────────
 
    def compute_inside_expansion(self):
        if self._expansion_union is None:
            self.parcels["inside_expansion"] = 0
            return
 
        def _intersects(geom):
            if geom is None:
                return 0
            try:
                return int(geom.intersects(self._expansion_union))
            except Exception:
                return 0
 
        self.parcels["inside_expansion"] = self.parcels["geometry"].apply(_intersects)
 
    # ── درجة المخاطر المكانية ─────────────────────────────────────────────
 
    def compute_spatial_risk(self):
        if "dist_to_settlement_m" not in self.parcels.columns:
            self.compute_distance_to_settlement()
 
        # نُطبّق Sigmoid معكوس: كلما قلّت المسافة زاد الخطر
        d = self.parcels["dist_to_settlement_m"].fillna(1e6)
        self.parcels["spatial_risk_score"] = 1 / (1 + d / 1000)  # [0,1]
 
    # ── تشغيل كل الحسابات ────────────────────────────────────────────────
 
    def run(self) -> pd.DataFrame:
        self.compute_distance_to_settlement()
        self.compute_near_settlement_flag()
        self.compute_inside_expansion()
        self.compute_spatial_risk()
 
        cols = [
            "parcel_id",
            "dist_to_settlement_m",
            "near_settlement",
            "inside_expansion",
            "spatial_risk_score",
        ]
        available = [c for c in cols if c in self.parcels.columns]
        result = self.parcels[available].copy()
 
        print(f"[geo_features] ✅ Geo features computed for {len(result)} parcels")
        return result