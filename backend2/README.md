# Backend API Server

## تشغيل الخادم

### الطريقة الأولى: استخدام Python مباشرة
```bash
cd C:\Users\waila\OneDrive\Desktop\backend2
(.venv\Scripts\activate)
python -m uvicorn main:app --reload --port=5000
```

### الطريقة الثانية: استخدام ملف Batch
```bash
run_server.bat
```

### الطريقة الثالثة: استخدام PowerShell Script
```powershell
.\run_server.ps1
```

## الـ API Endpoints

### Leak Detection (كشف التسريب)
#### POST /leak_detection/all
الحصول على جميع عمليات التسريب المكتشفة خلال فترة زمنية محددة.

**Request Body:**
```json
{
  "period": "آخر شهر"
}
```

#### POST /leak_detection/parcel
التحقق من حالة قطعة أرض محددة.

**Request Body:**
```json
{
  "basin_number": "123",
  "parcel_number": "456",
  "locality_id": "789"
}
```

### Fraud Detection (كشف الاحتيال)
#### POST /fraud_detection/train
تدريب نموذج كشف الاحتيال.

#### GET /fraud_detection/batch_predict
الحصول على تنبؤات الاحتيال لجميع القطع.

#### GET /fraud_detection/parcel/{parcel_id}
التحقق من حالة قطعة أرض محددة للكشف عن الاحتيال.

#### GET /fraud_detection/model_info
الحصول على معلومات النموذج.

## الخادم يعمل على
http://127.0.0.1:5000

## توثيق API
http://127.0.0.1:5000/docs

