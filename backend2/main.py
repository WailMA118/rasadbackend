# app كامل
from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse
from sqlalchemy import select, func, Column, BigInteger, Integer, Date, Numeric, Enum, String
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta
from pydantic import BaseModel
from db import Database
from custom_reports import generate_custom_report, save_custom_report, generate_chart_for_report, set_connection_password
import json
import os
import sys
import pandas as pd

# إضافة settlement_models إلى المسار
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'settlement_models'))

DATABASE_URL = "mysql+aiomysql://root:wail@localhost/palestine_land_system_v5"

db_instance = Database(DATABASE_URL)

# تعيين كلمة المرور للتقارير المخصصة
set_connection_password("wail")

# Pydantic Models
class CustomReportRequest(BaseModel):
    report_type: str  # person, parcel, region, period, monthly
    period: str = "آخر شهر"  # آخر شهر، آخر 3 أشهر، آخر 6 أشهر، هذا العام، مخصص
    entity: str = None  # اسم الشخص أو رقم القطعة
    governorate: str = None  # المحافظة
    custom_start_date: str = None  # التاريخ الابتدائي (للفترة المخصصة)
    custom_end_date: str = None  # التاريخ النهائي (للفترة المخصصة)
    notes: str = None  # ملاحظات إضافية

class LeakDetectionAllRequest(BaseModel):
    period: str = "آخر شهر"  # شهر، 3 أشهر، 6 أشهر، عام
    
class LeakDetectionParcelRequest(BaseModel):
    basin_number: str
    parcel_number: str
    locality_id: str

class FraudDetectionParcelRequest(BaseModel):
    parcel_id: int

async def get_db():
    async for session in db_instance.get_session():
        yield session


app = FastAPI()

# ربط مجلدات الرسوم البيانية
if not os.path.exists("charts"):
    os.makedirs("charts")
if not os.path.exists("custom_charts"):
    os.makedirs("custom_charts")
if not os.path.exists("custom_reports"):
    os.makedirs("custom_reports")

app.mount("/charts", StaticFiles(directory="charts"), name="charts")
app.mount("/custom_charts", StaticFiles(directory="custom_charts"), name="custom_charts")
app.mount("/custom_reports", StaticFiles(directory="custom_reports"), name="custom_reports")

@app.on_event("startup")
async def startup():
    await db_instance.init_models()

@app.get("/reports")
async def get_all_reports():
    """
    إرجاع جميع التقارير والرسوم البيانية
    """
    try:
        # قراءة ملف التقارير الرئيسي
        with open("reports/all_reports.json", "r", encoding="utf-8") as f:
            reports = json.load(f)
        
        return {
            "status": "success",
            "message": "جميع التقارير والرسوم البيانية",
            "data": reports,
            "charts_base_url": "/charts"
        }
    except FileNotFoundError:
        return {
            "status": "error",
            "message": "لم يتم العثور على ملفات التقارير. يرجى تشغيل land_reports.py أولاً"
        }

@app.get("/reports/{report_name}")
async def get_specific_report(report_name: str):
    """
    إرجاع تقرير محدد
    """
    try:
        with open(f"reports/{report_name}.json", "r", encoding="utf-8") as f:
            report = json.load(f)
        
        return {
            "status": "success",
            "report_name": report_name,
            "data": report
        }
    except FileNotFoundError:
        return {
            "status": "error",
            "message": f"التقرير '{report_name}' غير موجود"
        }

@app.get("/charts/{chart_name}")
async def get_chart(chart_name: str):
    """
    إرجاع الصورة البيانية
    """
    chart_path = f"charts/{chart_name}"
    if os.path.exists(chart_path):
        return FileResponse(chart_path, media_type="image/png")
    else:
        return {
            "status": "error",
            "message": f"الرسم البياني '{chart_name}' غير موجود"
        }

@app.post("/generate-custom-report")
async def generate_custom_report_endpoint(request: CustomReportRequest):
    """
    توليد تقرير مخصص حسب البيانات المرسلة
    """
    try:
        # توليد التقرير
        report_data = generate_custom_report(
            report_type=request.report_type,
            period=request.period,
            entity=request.entity,
            governorate=request.governorate,
            start_date=request.custom_start_date,
            end_date=request.custom_end_date
        )
        
        if report_data.get("status") == "error":
            return report_data
        
        # إضافة الملاحظات
        if request.notes:
            report_data["notes"] = request.notes
        
        # حفظ التقرير
        report_name = f"{request.report_type}_{request.period.replace(' ', '_')}"
        file_path = save_custom_report(report_data, report_name)
        
        # توليد الرسم البياني
        chart_path = generate_chart_for_report(report_data)
        
        return {
            "status": "success",
            "message": "تم توليد التقرير بنجاح",
            "report": report_data,
            "report_file": f"/custom_reports/{report_name}.json",
            "chart_file": f"/custom_charts/{os.path.basename(chart_path)}" if chart_path else None
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"خطأ في توليد التقرير: {str(e)}"
        }

@app.get("/custom-reports/{report_name}")
async def get_custom_report(report_name: str):
    """
    إرجاع تقرير مخصص محفوظ
    """
    try:
        with open(f"custom_reports/{report_name}.json", "r", encoding="utf-8") as f:
            report = json.load(f)
        
        return {
            "status": "success",
            "report_name": report_name,
            "data": report
        }
    except FileNotFoundError:
        return {
            "status": "error",
            "message": f"التقرير '{report_name}' غير موجود"
        }

@app.get("/custom-charts/{chart_name}")
async def get_custom_chart(chart_name: str):
    """
    إرجاع الرسم البياني المخصص
    """
    chart_path = f"custom_charts/{chart_name}"
    if os.path.exists(chart_path):
        return FileResponse(chart_path, media_type="image/png")
    else:
        return {
            "status": "error",
            "message": f"الرسم البياني '{chart_name}' غير موجود"
        }

@app.get("/settlement_expansion/json")
async def get_settlement_expansion_json():
    """
    إرجاع تحليل توسع المستوطنات شامل بصيغة JSON
    """
    json_path = "settlement_models/outputs/settlement_expansion_analysis.json"
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return {
            "status": "success",
            "message": "تحليل توسع المستوطنات",
            "data": data
        }
    except FileNotFoundError:
        return {
            "status": "error",
            "message": f"ملف التحليل الشامل غير موجود. يرجى تشغيل settlement_models/full_expansion.py أولاً",
            "file_path": json_path
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"خطأ في قراءة الملف: {str(e)}"
        }

@app.get("/settlement_expansion/html")
async def get_settlement_expansion_html():
    """
    إرجاع تقرير توسع المستوطنات بصيغة HTML
    """
    html_path = "settlement_models/outputs/settlement_expansion_report.html"
    if os.path.exists(html_path):
        return FileResponse(html_path, media_type="text/html")
    else:
        return {
            "status": "error",
            "message": f"ملف التقرير HTML غير موجود. يرجى تشغيل settlement_models/full_expansion.py أولاً",
            "file_path": html_path
        }

@app.get("/settlement_expansion/predict/id/{settlement_id}")
async def predict_settlement_by_id(settlement_id: int):
    """
    التنبؤ بخطر توسع المستوطنة حسب المعرف
    """
    from predict import predict_settlement
    
    result = predict_settlement(settlement_id=settlement_id)
    return result

@app.get("/settlement_expansion/predict/name/{name}")
async def predict_settlement_by_name(name: str):
    """
    التنبؤ بخطر توسع المستوطنة حسب الاسم
    """
    from predict import predict_settlement
    
    result = predict_settlement(name=name)
    return result

# ─── Leak Detection Endpoints ──────────────────────────────────────────

@app.get("/leak_detection/all")
async def get_all_detected_leaks(period: str = "آخر شهر"):
    """
    إرجاع جميع عمليات التسريب المكتشفة خلال المدة الزمنية المحددة
    
    المدد المدعومة:
    - آخر شهر: آخر 30 يوم
    - آخر 3 أشهر: آخر 90 يوم
    - آخر 6 أشهر: آخر 180 يوم
    - هذا العام: آخر 365 يوم
    """
    try:
        import sys
        import os as os_module
        
        leak_path = os_module.path.join(os_module.path.dirname(__file__), 'leak_deetection')
        if leak_path not in sys.path:
            sys.path.insert(0, leak_path)
        
        from predict import batch_predict
        import asyncio
        
        # تنفيذ التنبؤ في thread منفصل
        predictions = await asyncio.to_thread(batch_predict, save_csv=False)
        
        # تحديد فترة زمنية
        period_map = {
            "آخر شهر": 30,
            "آخر 3 أشهر": 90,
            "آخر 6 أشهر": 180,
            "هذا العام": 365,
        }
        
        days = period_map.get(period, 30)
        
        # تصفية التنبؤات حسب الفترة الزمنية
        if not isinstance(predictions, pd.DataFrame):
            try:
                predictions = pd.DataFrame(predictions)
            except Exception:
                return {
                    "status": "error",
                    "message": "صيغة البيانات غير متوقعة - يجب أن تكون DataFrame أو قابل للتحويل إلى DataFrame"
                }

        leaked_parcels = predictions[predictions["prediction"] == "leaked"].copy()
        suspected_parcels = predictions[predictions["prediction"] == "suspected"].copy()
        
        return {
            "status": "success",
            "message": f"التسريبات المكتشفة خلال {period}",
            "period": period,
            "days": days,
            "statistics": {
                "total_parcels": len(predictions),
                "leaked_count": len(leaked_parcels),
                "suspected_count": len(suspected_parcels),
                "safe_count": len(predictions[predictions["prediction"] == "safe"]),
            },
            "leaked_parcels": leaked_parcels[["parcel_id", "risk_score", "confidence"]].to_dict(orient="records") if len(leaked_parcels) > 0 else [],
            "suspected_parcels": suspected_parcels[["parcel_id", "risk_score", "suspected_score", "confidence"]].to_dict(orient="records") if len(suspected_parcels) > 0 else [],
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"خطأ في جلب التسريبات: {str(e)}"
        }

@app.get("/leak_detection/parcel")
async def check_parcel_leakage(basin_number: str, parcel_number: str, locality_id: str):
    """
    التحقق من حالة قطعة أرض محددة باستخدام المفتاح المركب:
    - basin_number
    - parcel_number
    - locality_id
    
    يعيد التنبؤ والدرجات وسرعة الثقة
    """
    try:
        import sys
        import os as os_module
        
        leak_path = os_module.path.join(os_module.path.dirname(__file__), 'leak_deetection')
        if leak_path not in sys.path:
            sys.path.insert(0, leak_path)
        
        from data_loader import get_parcel_by_composite_key
        from predict import predict_parcel
        import asyncio
        
        # البحث عن parcel_id من المفتاح المركب
        parcel_data = await asyncio.to_thread(
            get_parcel_by_composite_key,
            basin_number,
            parcel_number,
            locality_id
        )
        
        if parcel_data is None or parcel_data.empty:
            return {
                "status": "error",
                "message": f"لا توجد قطعة بهذه المواصفات",
                "composite_key": {
                    "basin_number": basin_number,
                    "parcel_number": parcel_number,
                    "locality_id": locality_id
                }
            }
        
        parcel_id = parcel_data['parcel_id'].iloc[0]
        
        # التنبؤ
        prediction = await asyncio.to_thread(predict_parcel, parcel_id)
        
        # إضافة المعلومات الإضافية
        prediction.update({
            "composite_key": {
                "basin_number": basin_number,
                "parcel_number": parcel_number,
                "locality_id": locality_id
            },
            "status": "success",
            "message": "تم التحقق من حالة القطعة بنجاح"
        })
        
        return prediction
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"خطأ في التحقق من القطعة: {str(e)}",
            "composite_key": {
                "basin_number": basin_number,
                "parcel_number": parcel_number,
                "locality_id": locality_id
            }
        }

# ─── Fraud Detection Endpoints ──────────────────────────────────────────

@app.get("/fraud_detection/batch_predict")
async def get_all_suspicious_people():
    """
    إرجاع جميع الأشخاص المتورطين في عمليات التسريب
    
    يعيد:
    - قائمة بالأشخاص المشبوهين مع:
      * owner_id, full_name, identity_group
      * is_suspicious, fraud_probability, confidence
      * risk_level, involvement_type
    - إحصائيات عامة عن عدد المشبوهين
    """
    try:
        import sys
        import os as os_module
        
        fraud_det_path = os_module.path.join(os_module.path.dirname(__file__), 'fraud_detection')
        if fraud_det_path not in sys.path:
            sys.path.insert(0, fraud_det_path)
        
        from predict import batch_predict
        import asyncio
        
        # تنفيذ التنبؤ في thread منفصل
        result = await asyncio.to_thread(batch_predict, save_csv=True)
        
        return result
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"خطأ في جلب الأشخاص المتورطين: {str(e)}"
        }

@app.get("/fraud_detection/owner/{owner_id}")
async def get_owner_involvement(owner_id: int):
    """
    التحقق من تورط شخص معين في عمليات التسريب
    
    المعاملات:
        owner_id: معرف الشخص
    
    يعيد:
    - بيانات الشخص الشخصية
    - التنبؤ بالتورط (0/1)
    - درجة احتمالية الاحتيال
    - مستوى المخاطر
    - ميزات السلوك (عدد المبيعات، المشتريات، إلخ)
    """
    try:
        import sys
        import os as os_module
        
        fraud_det_path = os_module.path.join(os_module.path.dirname(__file__), 'fraud_detection')
        if fraud_det_path not in sys.path:
            sys.path.insert(0, fraud_det_path)
        
        from predict import predict_person
        import asyncio
        
        # التنبؤ للشخص المحدد
        result = await asyncio.to_thread(predict_person, owner_id)
        
        return result
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"خطأ في التحقق من الشخص {owner_id}: {str(e)}"
        }

