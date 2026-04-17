# ═══════════════════════════════════════════════════════════════
# full_expansion.py — Full pipeline: all outputs for all settlements
# Run this after train_model.py has saved the model.
# ═══════════════════════════════════════════════════════════════

import os
import json
import numpy as np
import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import HeatMap
from shapely.geometry import mapping

from config import OUTPUT_DIR, SEVERITY_COLOR

# ── Output writers ────────────────────────────────────────────

class ResultTableWriter:

    def write(self, df: pd.DataFrame) -> str:
        cols = [
            "settlement_id", "name", "type", "established_year",
            "composite_risk", "xgb_risk", "ts_risk", "spatial_risk",
            "severity",
            "growth_rate_m2yr", "area_latest_m2", "forecast_5yr_area",
            "n_conf_total", "n_conf_recent",
            "leaked_ratio", "zone_c_coverage",
            "road_length_m", "n_transactions", "price_slope",
        ]
        out  = df[[c for c in cols if c in df.columns]].copy()
        for col in ["composite_risk", "xgb_risk", "ts_risk", "spatial_risk"]:
            if col in out: out[col] = out[col].round(4)

        path = os.path.join(OUTPUT_DIR, "settlement_expansion_risk.csv")
        out.to_csv(path, index=False)
        print(f"    CSV     → {path}")
        return path


class GeoJSONWriter:

    def write(self, df: pd.DataFrame,
              settlements_gdf: gpd.GeoDataFrame) -> str:
        geo = settlements_gdf[["settlement_id", "geometry"]].merge(
            df[["settlement_id", "name", "composite_risk", "severity",
                "xgb_risk", "ts_risk", "growth_rate_m2yr",
                "area_latest_m2", "n_conf_total"]],
            on="settlement_id", how="right"
        )
        
        # Create GeoJSON manually without requiring GDAL
        features = []
        for idx, row in geo.iterrows():
            feature = {
                "type": "Feature",
                "geometry": mapping(row["geometry"]),
                "properties": {
                    "settlement_id": int(row["settlement_id"]),
                    "name": str(row["name"]),
                    "composite_risk": float(row["composite_risk"]),
                    "severity": str(row["severity"]),
                    "xgb_risk": float(row["xgb_risk"]),
                    "ts_risk": float(row["ts_risk"]),
                    "growth_rate_m2yr": float(row["growth_rate_m2yr"]),
                    "area_latest_m2": float(row["area_latest_m2"]),
                    "n_conf_total": int(row["n_conf_total"]),
                }
            }
            features.append(feature)
        
        geojson_data = {
            "type": "FeatureCollection",
            "features": features
        }
        
        path = os.path.join(OUTPUT_DIR, "settlement_expansion_risk.geojson")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(geojson_data, f, indent=2, ensure_ascii=False)
        print(f"    GeoJSON → {path}")
        return path


class ComprehensiveJSONWriter:
    """Creates comprehensive JSON output with all analytics data"""

    def write(self, df: pd.DataFrame,
              settlements_gdf: gpd.GeoDataFrame) -> str:
        
        # Build comprehensive data structure
        comprehensive_data = {
            "metadata": {
                "timestamp": pd.Timestamp.now().isoformat(),
                "total_settlements": len(df),
                "analysis_type": "Settlement Expansion Risk Analysis",
                "region": "Palestine",
                "model": "Composite (XGBoost + Time Series + Spatial)"
            },
            "summary": {
                "total_settlements": int(len(df)),
                "critical_count": int((df['severity'] == 'critical').sum()),
                "high_count": int((df['severity'] == 'high').sum()),
                "medium_count": int((df['severity'] == 'medium').sum()),
                "low_count": int((df['severity'] == 'low').sum()),
                "average_risk": float(df['composite_risk'].mean()),
                "max_risk": float(df['composite_risk'].max()),
                "min_risk": float(df['composite_risk'].min()),
                "total_growth_m2yr": float(df['growth_rate_m2yr'].sum()),
                "total_confiscations": int(df['n_conf_total'].sum()),
                "total_leaked_parcels": float(df['leaked_ratio'].sum()),
                "avg_zone_c_coverage": float(df['zone_c_coverage'].mean()),
            },
            "risk_distribution": {
                "by_severity": {
                    "critical": int((df['severity'] == 'critical').sum()),
                    "high": int((df['severity'] == 'high').sum()),
                    "medium": int((df['severity'] == 'medium').sum()),
                    "low": int((df['severity'] == 'low').sum()),
                },
                "by_type": df['type'].value_counts().to_dict() if 'type' in df.columns else {},
            },
            "top_rankings": {
                "highest_risk": self._get_top_n(df, 'composite_risk', 10),
                "highest_growth": self._get_top_n(df, 'growth_rate_m2yr', 10),
                "most_confiscations": self._get_top_n(df, 'n_conf_total', 10),
                "highest_zone_c": self._get_top_n(df, 'zone_c_coverage', 10),
            },
            "detailed_settlements": self._build_settlement_records(df, settlements_gdf),
            "statistical_analysis": {
                "risk_scores": {
                    "composite": {
                        "mean": float(df['composite_risk'].mean()),
                        "median": float(df['composite_risk'].median()),
                        "std": float(df['composite_risk'].std()),
                        "min": float(df['composite_risk'].min()),
                        "max": float(df['composite_risk'].max()),
                        "q25": float(df['composite_risk'].quantile(0.25)),
                        "q75": float(df['composite_risk'].quantile(0.75)),
                    },
                    "xgb": {
                        "mean": float(df['xgb_risk'].mean()),
                        "median": float(df['xgb_risk'].median()),
                        "std": float(df['xgb_risk'].std()),
                    },
                    "timeseries": {
                        "mean": float(df['ts_risk'].mean()),
                        "median": float(df['ts_risk'].median()),
                        "std": float(df['ts_risk'].std()),
                    },
                    "spatial": {
                        "mean": float(df['spatial_risk'].mean()),
                        "median": float(df['spatial_risk'].median()),
                        "std": float(df['spatial_risk'].std()),
                    }
                },
                "growth_analysis": {
                    "mean_m2yr": float(df['growth_rate_m2yr'].mean()),
                    "median_m2yr": float(df['growth_rate_m2yr'].median()),
                    "total_m2yr": float(df['growth_rate_m2yr'].sum()),
                    "std_m2yr": float(df['growth_rate_m2yr'].std()),
                },
                "area_analysis": {
                    "mean_latest_m2": float(df['area_latest_m2'].mean()),
                    "total_latest_m2": float(df['area_latest_m2'].sum()),
                    "total_latest_km2": float(df['area_latest_m2'].sum() / 1_000_000),
                    "mean_forecast_5yr_m2": float(df['forecast_5yr_area'].mean()),
                    "total_forecast_5yr_m2": float(df['forecast_5yr_area'].sum()),
                    "total_forecast_5yr_km2": float(df['forecast_5yr_area'].sum() / 1_000_000),
                },
            }
        }
        
        # Save to file
        path = os.path.join(OUTPUT_DIR, "settlement_expansion_analysis.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(comprehensive_data, f, indent=2, ensure_ascii=False)
        
        print(f"    JSON    → {path}")
        return path

    def _get_top_n(self, df: pd.DataFrame, column: str, n: int = 10) -> list:
        """Get top N settlements by column"""
        top = df.nlargest(n, column)[
            ['settlement_id', 'name', 'type', 'severity', column]
        ].copy()
        
        result = []
        for idx, row in top.iterrows():
            result.append({
                "settlement_id": int(row['settlement_id']),
                "name": str(row['name']),
                "type": str(row.get('type', 'unknown')),
                "severity": str(row.get('severity', 'unknown')),
                column: float(row[column]) if pd.notna(row[column]) else None,
                "rank": len(result) + 1
            })
        
        return result

    def _build_settlement_records(self, df: pd.DataFrame,
                                  settlements_gdf: gpd.GeoDataFrame) -> list:
        """Build detailed settlement records"""
        records = []
        
        for idx, row in df.iterrows():
            record = {
                "settlement_id": int(row['settlement_id']),
                "name": str(row['name']),
                "type": str(row.get('type', 'unknown')),
                "established_year": int(row['established_year']) if pd.notna(row.get('established_year')) else None,
                "coordinates": self._get_geometry_coords(settlements_gdf, row['settlement_id']),
                "risk_assessment": {
                    "composite_risk": float(row['composite_risk']),
                    "severity": str(row['severity']),
                    "xgb_risk": float(row['xgb_risk']),
                    "ts_risk": float(row['ts_risk']),
                    "spatial_risk": float(row['spatial_risk']),
                },
                "expansion_metrics": {
                    "growth_rate_m2yr": float(row['growth_rate_m2yr']),
                    "area_latest_m2": float(row['area_latest_m2']),
                    "area_latest_km2": float(row['area_latest_m2'] / 1_000_000),
                    "forecast_5yr_area_m2": float(row.get('forecast_5yr_area', 0)),
                    "forecast_5yr_area_km2": float(row.get('forecast_5yr_area', 0) / 1_000_000),
                },
                "threat_indicators": {
                    "confiscation_orders": int(row.get('n_conf_total', 0)),
                    "recent_confiscations": int(row.get('n_conf_recent', 0)),
                    "leaked_parcel_ratio": float(row.get('leaked_ratio', 0)),
                    "zone_c_coverage": float(row.get('zone_c_coverage', 0)),
                },
                "connectivity": {
                    "road_length_m": float(row.get('road_length_m', 0)),
                    "transactions_count": int(row.get('n_transactions', 0)),
                    "price_trend": float(row.get('price_slope', 0)) if pd.notna(row.get('price_slope')) else None,
                }
            }
            records.append(record)
        
        return records

    def _get_geometry_coords(self, settlements_gdf: gpd.GeoDataFrame,
                            settlement_id: int) -> dict:
        """Extract geometry coordinates"""
        match = settlements_gdf[settlements_gdf['settlement_id'] == settlement_id]
        
        if match.empty:
            return {"lat": None, "lon": None, "geom_type": None}
        
        geom = match.iloc[0]['geometry']
        
        if geom is None or geom.is_empty:
            return {"lat": None, "lon": None, "geom_type": None}
        
        centroid = geom.centroid
        return {
            "lat": float(centroid.y),
            "lon": float(centroid.x),
            "geom_type": geom.geom_type
        }


class ComprehensiveReportWriter:
    """Creates comprehensive HTML report with table and map"""
    
    def _prepare_table_html(self, df: pd.DataFrame) -> str:
        """Prepare table HTML with only essential columns"""
        # Select only essential columns
        cols = [
            "name", "type",
            "composite_risk", "severity",
            "xgb_risk", "ts_risk", "spatial_risk",
            "growth_rate_m2yr", "area_latest_m2", "forecast_5yr_area",
            "n_conf_total", "leaked_ratio", "zone_c_coverage",
        ]
        table_df = df[[c for c in cols if c in df.columns]].copy()
        
        # Round risk scores
        for col in ["composite_risk", "xgb_risk", "ts_risk", "spatial_risk"]:
            if col in table_df:
                table_df[col] = table_df[col].round(4)
        
        return table_df.to_html(index=False, classes="report-table")
    
    def _generate_html_template(self, df: pd.DataFrame, table_html: str, map_html: str) -> str:
        """Generate complete HTML template with table and map"""
        # Calculate summary statistics first
        critical_count = int((df['severity']=='critical').sum())
        high_count = int((df['severity']=='high').sum())
        medium_count = int((df['severity']=='medium').sum())
        total_count = len(df)
        
        full_html = f"""
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>تقرير توسع المستوطنات</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #0f0f0f;
            color: #e0e0e0;
            line-height: 1.6;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }}
        
        header {{
            background: linear-gradient(135deg, #1a1a1a 0%, #2a2a2a 100%);
            color: #ffffff;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 30px;
            text-align: center;
            border: 1px solid #3498db;
        }}
        
        header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        
        header p {{
            font-size: 1.1em;
            opacity: 0.9;
        }}
        
        section {{
            background: #1a1a1a;
            padding: 20px;
            margin-bottom: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.5);
            border: 1px solid #333;
        }}
        
        h2 {{
            color: #ffffff;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }}
        
        .table-wrapper {{
            width: 100%;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        
        .report-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9em;
            background: #252525;
        }}
        
        .report-table th {{
            background-color: #1a1a1a;
            color: #ffffff;
            padding: 12px;
            text-align: right;
            font-weight: bold;
            border: 1px solid #444;
        }}
        
        .report-table td {{
            padding: 10px 12px;
            border: 1px solid #333;
            text-align: right;
            white-space: nowrap;
            color: #e0e0e0;
        }}
        
        .report-table tr:nth-child(even) {{
            background-color: #1f1f1f;
        }}
        
        .report-table tr:hover {{
            background-color: #2a2a2a;
        }}
        
        #map-container {{
            width: 100%;
            height: 600px;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.15);
        }}
        
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        
        .summary-card {{
            background: #1a3a52;
            color: #4db3ff;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            border-left: 5px solid #4db3ff;
            box-shadow: 0 4px 12px rgba(0,0,0,0.4);
        }}
        
        .summary-card.critical {{
            background: #4a1f1f;
            color: #ff6b6b;
            border-left: 5px solid #ff6b6b;
        }}
        
        .summary-card.high {{
            background: #523a1f;
            color: #ffa94d;
            border-left: 5px solid #ffa94d;
        }}
        
        .summary-card.medium {{
            background: #1f3a2f;
            color: #51cf66;
            border-left: 5px solid #51cf66;
        }}
        
        .summary-card h3 {{
            font-size: 0.85em;
            opacity: 1;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .summary-card .number {{
            font-size: 2.8em;
            font-weight: bold;
            letter-spacing: 2px;
        }}
        
        footer {{
            text-align: center;
            padding: 20px;
            background-color: #1a1a1a;
            color: #a0a0a0;
            border-radius: 8px;
            font-size: 0.9em;
            border: 1px solid #333;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>تقرير توسع المستوطنات</h1>
            <p>Settlement Expansion Risk Analysis Report</p>
        </header>
        
        <section>
            <h2>ملخص المخاطر</h2>
            <div class="summary">
                <div class="summary-card critical">
                    <h3>مخاطر حرجة</h3>
                    <div class="number">{critical_count}</div>
                </div>
                <div class="summary-card high">
                    <h3>مخاطر عالية</h3>
                    <div class="number">{high_count}</div>
                </div>
                <div class="summary-card medium">
                    <h3>مخاطر متوسطة</h3>
                    <div class="number">{medium_count}</div>
                </div>
                <div class="summary-card">
                    <h3>إجمالي المستوطنات</h3>
                    <div class="number">{total_count}</div>
                </div>
            </div>
        </section>
        
        <section>
            <h2>نتائج التحليل التفصيلية</h2>
            <div class="table-wrapper">{table_html}</div>
        </section>
        
        <section>
            <h2>الخريطة التفاعلية</h2>
            <div id="map-container">
                {map_html}
            </div>
        </section>
        
        <footer>
            <p>تم إنشاء هذا التقرير بواسطة نظام تحليل توسع المستوطنات</p>
            <p>Settlement Expansion Analysis System</p>
        </footer>
    </div>
</body>
</html>
        """
        return full_html
    
    def write(self, df: pd.DataFrame,
              settlements_gdf: gpd.GeoDataFrame,
              confiscation: gpd.GeoDataFrame,
              parcels: gpd.GeoDataFrame) -> str:
        """Generate full HTML report with table and embedded map"""
        
        # Generate table HTML
        table_html = self._prepare_table_html(df)
        
        # Generate map HTML
        map_writer = FoliumMapWriter()
        map_html = map_writer.get_map_html(df, settlements_gdf, confiscation, parcels)
        
        # Create comprehensive HTML using template function
        full_html = self._generate_html_template(df, table_html, map_html)
        
        # Save report
        path = os.path.join(OUTPUT_DIR, "settlement_expansion_report.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(full_html)
        
        print(f"    Report  → {path}")
        return path
    
    def get_html(self, df: pd.DataFrame,
                 settlements_gdf: gpd.GeoDataFrame,
                 confiscation: gpd.GeoDataFrame,
                 parcels: gpd.GeoDataFrame) -> str:
        """Return HTML as string without saving"""
        
        # Generate table HTML
        table_html = self._prepare_table_html(df)
        
        # Generate map HTML
        map_writer = FoliumMapWriter()
        map_html = map_writer.get_map_html(df, settlements_gdf, confiscation, parcels)
        
        # Create comprehensive HTML using template function
        full_html = self._generate_html_template(df, table_html, map_html)
        
        return full_html


class FoliumMapWriter:

    def write(self, df: pd.DataFrame,
              settlements_gdf: gpd.GeoDataFrame,
              confiscation: gpd.GeoDataFrame,
              parcels: gpd.GeoDataFrame) -> str:

        center = [31.9, 35.2]
        m = folium.Map(location=center, zoom_start=11,
                       tiles="CartoDB dark_matter")

        self._add_confiscation_heatmap(m, confiscation)
        self._add_leaked_parcels(m, parcels)
        self._add_settlements(m, df, settlements_gdf)
        self._add_legend(m)

        folium.LayerControl().add_to(m)

        # Save map HTML without button
        path = os.path.join(OUTPUT_DIR, "settlement_expansion_map.html")
        m.save(path)
        print(f"    Map     → {path}")
        return path
    
    def get_map_html(self, df: pd.DataFrame,
                     settlements_gdf: gpd.GeoDataFrame,
                     confiscation: gpd.GeoDataFrame,
                     parcels: gpd.GeoDataFrame) -> str:
        """Get map as HTML string (for embedding in report)"""
        center = [31.9, 35.2]
        m = folium.Map(location=center, zoom_start=11,
                       tiles="CartoDB dark_matter")

        self._add_confiscation_heatmap(m, confiscation)
        self._add_leaked_parcels(m, parcels)
        self._add_settlements(m, df, settlements_gdf)
        self._add_legend(m)

        folium.LayerControl().add_to(m)
        
        return m._repr_html_()

    # ── Layer builders ────────────────────────────────────────

    def _add_confiscation_heatmap(self, m, confiscation):
        conf_clean = confiscation[confiscation["geometry"].notna()].copy()
        conf_pts = [[g.centroid.y, g.centroid.x]
                    for g in conf_clean["geometry"] if g and not g.is_empty]
        if conf_pts:
            HeatMap(conf_pts, name="Confiscation orders heatmap",
                    radius=15, blur=20, max_zoom=14).add_to(m)

    def _add_leaked_parcels(self, m, parcels):
        leaked_layer = folium.FeatureGroup(name="Leaked parcels")
        leaked = parcels[parcels["leakage_label"].isin(["leaked", "suspected"])].copy()

        for _, p_row in leaked.iterrows():
            geom = p_row["geometry"]
            if geom is None or geom.is_empty:
                continue
            c = geom.centroid
            color = "#e74c3c" if p_row["leakage_label"] == "leaked" else "#e67e22"
            folium.CircleMarker(
                location=[c.y, c.x],
                radius=4,
                color=color,
                fill=True,
                fill_opacity=0.7,
                popup=f"Parcel {p_row['parcel_id']} - {p_row['leakage_label']}"
            ).add_to(leaked_layer)
        leaked_layer.add_to(m)

    def _add_settlements(self, m, df, settlements_gdf):
        settle_layer = folium.FeatureGroup(name="Settlements (risk)")
        
        # Merge settlements geometry with risk scores using settlements_gdf as base
        merged = settlements_gdf.merge(
            df[["settlement_id", "composite_risk", "severity", "xgb_risk",
                "ts_risk", "spatial_risk", "growth_rate_m2yr",
                "n_conf_total", "leaked_ratio",
                "zone_c_coverage", "forecast_5yr_area", "name"]],
            on="settlement_id", how="right"
        )

        for _, row in merged.iterrows():
            geom = row["geometry"]
            if geom is None or geom.is_empty:
                continue
            
            color = SEVERITY_COLOR.get(row["severity"], "#95a5a6")
            risk_pct = f"{row['composite_risk'] * 100:.1f}%"
            area_5yr = (f"{row['forecast_5yr_area'] / 10_000:.1f} ha"
                        if row.get("forecast_5yr_area", 0) > 0 else "N/A")
            
            popup_html = f"""
            <div style='font-family:sans-serif;min-width:200px'>
              <b style='font-size:14px'>{row.get('name', 'Unknown')}</b><br>
              <span style='color:{color};font-weight:bold'>
                Warning {row['severity'].upper()} RISK - {risk_pct}</span><br><hr>
              <table style='font-size:12px'>
                <tr><td>XGBoost risk</td><td>{row['xgb_risk']:.3f}</td></tr>
                <tr><td>Time-series risk</td><td>{row['ts_risk']:.3f}</td></tr>
                <tr><td>Spatial pressure</td><td>{row['spatial_risk']:.3f}</td></tr>
                <tr><td>Growth rate</td>
                    <td>{row['growth_rate_m2yr']:,.0f} m2/yr</td></tr>
                <tr><td>Confiscation orders</td>
                    <td>{int(row['n_conf_total'])}</td></tr>
                <tr><td>Leaked parcel ratio</td>
                    <td>{row['leaked_ratio']:.1%}</td></tr>
                <tr><td>Zone-C coverage</td>
                    <td>{row['zone_c_coverage']:.1%}</td></tr>
                <tr><td>Forecast area (5yr)</td><td>{area_5yr}</td></tr>
              </table>
            </div>
            """
            
            # Draw polygon
            if geom.geom_type == "Polygon":
                coords = [[c[1], c[0]] for c in geom.exterior.coords]
            elif geom.geom_type == "MultiPolygon":
                coords = [[c[1], c[0]] for c in
                          max(geom.geoms, key=lambda g: g.area).exterior.coords]
            else:
                continue

            folium.Polygon(
                locations=coords,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.45,
                weight=2,
                tooltip=row.get("name", ""),
                popup=folium.Popup(popup_html, max_width=300),
            ).add_to(settle_layer)

            # Centroid label
            centroid = geom.centroid
            folium.Marker(
                location=[centroid.y, centroid.x],
                icon=folium.DivIcon(
                    html=f'<div style="color:{color};font-size:9px;'
                         f'font-weight:bold;white-space:nowrap">'
                         f'{row.get("name","")}</div>',
                    icon_size=(120, 18)
                )
            ).add_to(settle_layer)

        settle_layer.add_to(m)

    def _add_legend(self, m):
        legend_html = """
        <div style='position:fixed;bottom:30px;left:30px;z-index:1000;
                    background:rgba(0,0,0,0.8);color:white;padding:12px;
                    border-radius:8px;font-family:sans-serif;font-size:12px'>
          <b>Settlement Expansion Risk</b><br>
          <span style='color:#c0392b'>●</span> Critical (&gt;75%)<br>
          <span style='color:#e67e22'>●</span> High (&gt;55%)<br>
          <span style='color:#f1c40f'>●</span> Medium (&gt;35%)<br>
          <span style='color:#2ecc71'>●</span> Low<br><hr>
          <span style='color:#e74c3c'>●</span> Leaked parcel<br>
          <span style='color:#e67e22'>●</span> Suspected parcel
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))


# ── Console table ─────────────────────────────────────────────

def print_ranking_table(df: pd.DataFrame):
    print("\n" + "═" * 80)
    print("  SETTLEMENT EXPANSION RISK RANKING")
    print("═" * 80)
    print(f"{'#':<4} {'Name':<28} {'Type':<12} {'Risk':<8} "
          f"{'Severity':<10} {'Growth m²/yr':<14} {'Confisc.'}")
    print("─" * 80)
    for i, row in df.head(20).iterrows():
        print(f"{i+1:<4} {str(row.get('name','?')):<28} "
              f"{str(row.get('type','?')):<12} "
              f"{row['composite_risk']:.3f}   "
              f"{row.get('severity','?'):<10} "
              f"{row.get('growth_rate_m2yr',0):>12,.0f}   "
              f"{int(row.get('n_conf_total',0))}")
    print("═" * 80)


# ── Helper functions ──────────────────────────────────────────

def generate_report_html(df: pd.DataFrame,
                         settlements_gdf: gpd.GeoDataFrame,
                         confiscation: gpd.GeoDataFrame,
                         parcels: gpd.GeoDataFrame) -> str:
    """
    Generate comprehensive HTML report with table and map.
    
    Returns HTML string that can be embedded in another page.
    Usage: html_content = generate_report_html(df, settlements, confiscation, parcels)
    """
    return ComprehensiveReportWriter().get_html(
        df, settlements_gdf, confiscation, parcels
    )


# ═══════════════════════════════════════════════════════════════
# Full pipeline entry point
# ═══════════════════════════════════════════════════════════════

def run_full_pipeline():
    from data_loader import get_engine, load_all
    from feature_engineering import FeatureMatrix
    from train_model import SettlementExpansionModel
    from timeseries import TimeSeriesForecaster
    from score_fusion import RiskFusion, AlertWriter

    print("\n" + "═" * 60)
    print("  SETTLEMENT EXPANSION — FULL PIPELINE")
    print("  Ramallah data | Palestine-wide model")
    print("═" * 60 + "\n")

    # 1. Data
    engine = get_engine()
    data   = load_all(engine)

    # 2. Features
    df = FeatureMatrix().build(data)

    if df.empty:
        print("ERROR: No settlements found.")
        return

    # 3a. XGBoost (load saved model)
    model = SettlementExpansionModel().load()
    xgb_proba = model.predict(df)

    # 3b. Time series
    area_map = dict(zip(df["settlement_id"], df["area_latest_m2"]))
    ts_df    = TimeSeriesForecaster().forecast_all(
        df["settlement_id"].tolist(),
        data["expansion_history"],
        area_map
    )

    # 4. Score fusion
    print("[score_fusion] Fusing risk scores …")
    df_final = RiskFusion().fuse(df, xgb_proba, ts_df)
    print_ranking_table(df_final)

    # 5. Outputs
    print("\n[outputs] Writing files …")
    ResultTableWriter().write(df_final)
    GeoJSONWriter().write(df_final, data["settlements"])
    ComprehensiveJSONWriter().write(df_final, data["settlements"])
    ComprehensiveReportWriter().write(
        df_final, data["settlements"],
        data["confiscation"], data["parcels"]
    )

    # 6. DB alerts
    n_alerts = AlertWriter().write(df_final, engine)

    # Summary
    print("\n" + "═" * 60)
    print("  PIPELINE COMPLETE")
    print(f"  Settlements analysed : {len(df_final)}")
    print(f"  Critical             : {(df_final['severity']=='critical').sum()}")
    print(f"  High                 : {(df_final['severity']=='high').sum()}")
    print(f"  Alerts written       : {n_alerts}")
    print(f"  Outputs dir          : {OUTPUT_DIR}")
    print("═" * 60 + "\n")

    return df_final


if __name__ == "__main__":
    run_full_pipeline()