# ═══════════════════════════════════════════════════════════════
# predict.py — Predict expansion risk for ONE specific settlement
# Usage:
#   python predict.py --id 3
#   python predict.py --name "Beit El"
# ═══════════════════════════════════════════════════════════════

import argparse
import json
import pandas as pd
import os
from pathlib import Path

from config import THR_CRITICAL, THR_HIGH, THR_MEDIUM, SEVERITY_COLOR, OUTPUT_DIR


# ── Prediction runner ─────────────────────────────────────────

class SingleSettlementPredictor:
    """
    Loads a saved model and runs the full prediction pipeline
    for exactly one settlement.

    Outputs:
      - Console report with all scores and top risk indicators
      - Forecast series (area per year)
    """

    def __init__(self):
        from data_loader import get_engine, load_all
        from feature_engineering import FeatureMatrix
        from train_model import SettlementExpansionModel
        from timeseries import TimeSeriesForecaster
        from score_fusion import RiskFusion

        self.engine      = get_engine()
        self._data       = None
        self._df         = None
        self.model       = SettlementExpansionModel().load()
        self.ts          = TimeSeriesForecaster()
        self.fusion      = RiskFusion()
        self._data_loader_cls    = load_all
        self._feature_matrix_cls = FeatureMatrix

    def _ensure_data(self):
        if self._data is None:
            self._data = self._data_loader_cls(self.engine)
            self._df   = self._feature_matrix_cls().build(self._data)

    def predict(self, settlement_id: int = None,
                name: str = None) -> dict:
        """
        Run prediction for a single settlement.
        Identify it by settlement_id OR name (case-insensitive).
        """
        self._ensure_data()
        df = self._df

        # ── Identify row ──────────────────────────────────────
        if settlement_id is not None:
            mask = df["settlement_id"] == settlement_id
        elif name is not None:
            mask = df["name"].str.lower() == name.lower()
        else:
            raise ValueError("Provide settlement_id or name.")

        if not mask.any():
            raise ValueError(f"Settlement not found: id={settlement_id} name={name}")

        row_df = df[mask].copy().reset_index(drop=True)
        sid    = int(row_df["settlement_id"].iloc[0])

        # ── XGBoost score ─────────────────────────────────────
        xgb_risk = float(self.model.predict(row_df)[0])

        # ── Time-series forecast ──────────────────────────────
        area_map = {sid: float(row_df["area_latest_m2"].iloc[0])}
        ts_df    = self.ts.forecast_all(
            [sid], self._data["expansion_history"], area_map
        )

        # ── Score fusion ──────────────────────────────────────
        import numpy as np
        result_df = self.fusion.fuse(row_df, np.array([xgb_risk]), ts_df)
        result    = result_df.iloc[0].to_dict()

        # Parse forecast series
        fc_series = {}
        raw = result.get("forecast_series", "{}")
        if isinstance(raw, str):
            fc_series = {int(k): v for k, v in json.loads(raw).items()}

        return {
            "settlement_id"    : sid,
            "name"             : result.get("name", "?"),
            "type"             : result.get("type", "?"),
            "established_year" : result.get("established_year"),
            "composite_risk"   : round(result["composite_risk"], 4),
            "xgb_risk"         : round(result["xgb_risk"], 4),
            "ts_risk"          : round(result["ts_risk"], 4),
            "spatial_risk"     : round(result["spatial_risk"], 4),
            "severity"         : result["severity"],
            # Key features
            "area_latest_m2"   : round(result.get("area_latest_m2", 0), 1),
            "growth_rate_m2yr" : round(result.get("growth_rate_m2yr", 0), 1),
            "forecast_5yr_area": round(result.get("forecast_5yr_area", 0), 1),
            "n_conf_total"     : int(result.get("n_conf_total", 0)),
            "n_conf_recent"    : int(result.get("n_conf_recent", 0)),
            "leaked_ratio"     : round(result.get("leaked_ratio", 0), 4),
            "zone_c_coverage"  : round(result.get("zone_c_coverage", 0), 4),
            "n_transactions"   : int(result.get("n_transactions", 0)),
            "road_length_m"    : round(result.get("road_length_m", 0), 1),
            # Derived
            "expansion_momentum"    : round(result.get("expansion_momentum", 0), 6),
            "legal_pressure_index"  : round(result.get("legal_pressure_index", 0), 4),
            "leakage_pressure"      : round(result.get("leakage_pressure", 0), 4),
            # Forecast
            "forecast_series"  : fc_series,
        }

    def top_features(self, n: int = 10) -> pd.DataFrame:
        """Return top-n feature importances from the loaded model."""
        return self.model.feature_importance(n)


# ── Console report ────────────────────────────────────────────

def _print_report(result: dict):
    sev   = result["severity"]
    color_map = {"critical":"🔴","high":"🟠","medium":"🟡","low":"🟢"}
    icon  = color_map.get(sev, "⚪")

    print("\n" + "═" * 60)
    print(f"  SETTLEMENT EXPANSION RISK REPORT")
    print("═" * 60)
    print(f"  Name            : {result['name']}")
    print(f"  Type            : {result['type']}")
    print(f"  Established     : {result['established_year']}")
    print(f"  ID              : {result['settlement_id']}")
    print("─" * 60)
    print(f"  {icon} Severity        : {sev.upper()}")
    print(f"  Composite risk  : {result['composite_risk']:.1%}")
    print(f"    ├─ XGBoost    : {result['xgb_risk']:.3f}")
    print(f"    ├─ TimeSeries : {result['ts_risk']:.3f}")
    print(f"    └─ Spatial    : {result['spatial_risk']:.3f}")
    print("─" * 60)
    print("  SPATIAL INDICATORS")
    print(f"  Current area    : {result['area_latest_m2']:>12,.0f} m²  "
          f"({result['area_latest_m2']/10000:.2f} ha)")
    print(f"  Growth rate     : {result['growth_rate_m2yr']:>12,.0f} m²/yr")
    print(f"  Forecast (5yr)  : {result['forecast_5yr_area']:>12,.0f} m²")
    print(f"  Confiscations   : {result['n_conf_total']:>3}  "
          f"(recent: {result['n_conf_recent']})")
    print(f"  Leaked ratio    : {result['leaked_ratio']:.1%} of nearby parcels")
    print(f"  Zone-C coverage : {result['zone_c_coverage']:.1%}")
    print(f"  Road length     : {result['road_length_m']:>10,.0f} m nearby")
    print(f"  Transactions    : {result['n_transactions']:>3}")
    print("─" * 60)
    print("  COMPOSITE INDICATORS")
    print(f"  Expansion momentum   : {result['expansion_momentum']:.6f}")
    print(f"  Legal pressure index : {result['legal_pressure_index']:.4f}")
    print(f"  Leakage pressure     : {result['leakage_pressure']:.4f}")
    print("─" * 60)

    fc = result.get("forecast_series", {})
    if fc:
        print("  AREA FORECAST (m²)")
        for yr in sorted(fc.keys()):
            bar = "█" * int(fc[yr] / max(fc.values()) * 20)
            print(f"    {yr} │ {fc[yr]:>12,.0f}  {bar}")

    print("═" * 60 + "\n")


# ── JSON Report Generator ───────────────────────────────────

def generate_json_report(result: dict) -> dict:
    """
    Generate comprehensive JSON report with all settlement expansion risk data.
    Returns JSON object without saving to file.
    """
    sev = result["severity"]
    severity_values = {
        "critical": 4,
        "high": 3,
        "medium": 2,
        "low": 1
    }
    
    # Calculate area growth percentage
    area_growth_pct = 0
    if result["area_latest_m2"] > 0:
        area_growth_pct = (result["forecast_5yr_area"] - result["area_latest_m2"]) / result["area_latest_m2"] * 100
    
    json_report = {
        "status": "success",
        "timestamp": pd.Timestamp.now().isoformat(),
        "settlement": {
            "id": result["settlement_id"],
            "name": result["name"],
            "type": result["type"],
            "established_year": result["established_year"],
        },
        "risk_assessment": {
            "severity": sev,
            "severity_level": severity_values.get(sev, 0),
            "composite_risk": result["composite_risk"],
            "xgb_risk": result["xgb_risk"],
            "ts_risk": result["ts_risk"],
            "spatial_risk": result["spatial_risk"],
        },
        "spatial_indicators": {
            "current_area_m2": result["area_latest_m2"],
            "current_area_km2": result["area_latest_m2"] / 1_000_000,
            "growth_rate_m2yr": result["growth_rate_m2yr"],
            "forecast_5yr_area_m2": result["forecast_5yr_area"],
            "forecast_5yr_area_km2": result["forecast_5yr_area"] / 1_000_000,
            "area_growth_percentage": area_growth_pct,
        },
        "confiscation_data": {
            "total_confiscations": result["n_conf_total"],
            "recent_confiscations": result["n_conf_recent"],
            "confiscation_ratio": result["n_conf_total"] / max(1, result["area_latest_m2"]) * 10_000,
        },
        "land_quality": {
            "leaked_parcel_ratio": result["leaked_ratio"],
            "zone_c_coverage": result["zone_c_coverage"],
            "legal_pressure_index": result["legal_pressure_index"],
            "leakage_pressure": result["leakage_pressure"],
        },
        "connectivity": {
            "road_length_m": result["road_length_m"],
            "transactions_count": result["n_transactions"],
            "expansion_momentum": result["expansion_momentum"],
        },
        "forecast": {
            "series": result["forecast_series"],
            "years": sorted(result["forecast_series"].keys()) if result["forecast_series"] else [],
        }
    }
    
    return json_report


def predict_settlement(settlement_id: int = None, name: str = None) -> dict:
    """
    Public function to predict expansion risk for a settlement.
    Can be called from FastAPI endpoints.
    
    Args:
        settlement_id: Settlement ID (integer)
        name: Settlement name (string)
    
    Returns:
        JSON report dict with all risk metrics and forecasts
    """
    if settlement_id is None and name is None:
        return {
            "status": "error",
            "message": "Provide either settlement_id or name"
        }
    
    try:
        predictor = SingleSettlementPredictor()
        result = predictor.predict(
            settlement_id=settlement_id,
            name=name
        )
        
        # Generate and return JSON report
        json_report = generate_json_report(result)
        
        return json_report
        
    except ValueError as e:
        return {
            "status": "error",
            "message": str(e)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Prediction failed: {str(e)}"
        }


def main():
    parser = argparse.ArgumentParser(
        description="Predict expansion risk for one settlement"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--id",   type=int,   help="settlement_id")
    group.add_argument("--name", type=str,   help="Settlement name")
    args = parser.parse_args()

    predictor = SingleSettlementPredictor()

    result = predictor.predict(
        settlement_id = args.id,
        name          = args.name,
    )
    
    # Print console report
    _print_report(result)

    print("  Top 10 model feature importances:")
    print(predictor.top_features(10).to_string(index=False))
    print()
    
    # Generate JSON report (no file save)
    json_report = generate_json_report(result)
    
    print(f"\n✓ JSON Report generated successfully")
    print(f"  Settlement: {json_report['settlement']['name']}")
    print(f"  Risk Level: {json_report['risk_assessment']['severity'].upper()}")
    print(f"  Composite Risk: {json_report['risk_assessment']['composite_risk']:.1%}\n")
    
    return json_report


if __name__ == "__main__":
    report = main()
    