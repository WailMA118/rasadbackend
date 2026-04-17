# API توثيق التقارير المخصصة

## المقدمة
نظام التقارير المخصصة يسمح بإنشاء تقارير مفصلة حسب معايير محددة (شخص، قطعة أرض، منطقة جغرافية، فترة زمنية).

---

## الـ Endpoints

### 1. إنشاء تقرير مخصص
**POST** `/generate-custom-report`

#### طلب البيانات:
```json
{
  "report_type": "person",           // نوع التقرير (person, parcel, region, period, monthly)
  "period": "آخر شهر",              // المدى الزمني
  "entity": "عمر الطميزي",            // اسم الشخص أو رقم القطعة (اختياري)
  "governorate": "رام الله",         // المحافظة (اختياري)
  "custom_start_date": "2024-01-01", // التاريخ الابتدائي (للفترة المخصصة)
  "custom_end_date": "2024-12-31",   // التاريخ النهائي (للفترة المخصصة)
  "notes": "ملاحظات إضافية"          // ملاحظات (اختياري)
}
```

#### أنواع التقارير:
- **person**: تقرير عن شخص أو مالك
  - يتطلب: `entity` (اسم أو رقم الهوية)
  - يعرض: معاملات البيع والشراء

- **parcel**: تقرير عن قطعة أرض
  - يتطلب: `entity` (رقم القطعة)
  - يعرض: تاريخ المعاملات والملكية

- **region**: تقرير عن منطقة جغرافية
  - يتطلب: `governorate` (اسم المحافظة)
  - يعرض: إحصائيات حسب الموقع

- **period**: تقرير فترة زمنية مخصصة
  - يتطلب: `custom_start_date`, `custom_end_date`
  - يعرض: كل المعاملات في الفترة

#### خيارات المدى الزمني:
- `آخر شهر`
- `آخر 3 أشهر`
- `آخر 6 أشهر`
- `هذا العام`
- `مخصص` (يتطلب التواريخ)

#### استجابة النجاح:
```json
{
  "status": "success",
  "message": "تم توليد التقرير بنجاح",
  "report": {
    "report_type": "person",
    "generated_at": "2024-04-16T20:00:00.000Z",
    "person": {
      "id": 180,
      "name": "عمر الطميزي"
    },
    "period": {
      "from": "2024-03-16",
      "to": "2024-04-16"
    },
    "summary": {
      "total_sales": 9,
      "total_sales_value": 13749109.22,
      "total_purchases": 0,
      "total_purchases_value": 0,
      "total_area_sold": 15000.5,
      "total_area_purchased": 0
    },
    "sales": [...],
    "purchases": [...]
  },
  "report_file": "/custom_reports/person_آخر_شهر.json",
  "chart_file": "/custom_charts/person_180_20240416_200000.png"
}
```

---

### 2. استرجاع تقرير مخصص محفوظ
**GET** `/custom-reports/{report_name}`

#### مثال:
```
GET /custom-reports/person_آخر_شهر
```

#### استجابة النجاح:
```json
{
  "status": "success",
  "report_name": "person_آخر_شهر",
  "data": { ... }
}
```

---

### 3. الحصول على رسم بياني
**GET** `/custom-charts/{chart_name}`

#### مثال:
```
GET /custom-charts/person_180_20240416_200000.png
```

---

## أمثلة الاستخدام

### مثال 1: تقرير عن شخص (آخر شهر)
```bash
curl -X POST "http://127.0.0.1:5000/generate-custom-report" \
  -H "Content-Type: application/json" \
  -d '{
    "report_type": "person",
    "period": "آخر شهر",
    "entity": "عمر الطميزي"
  }'
```

### مثال 2: تقرير عن محافظة (آخر 6 أشهر)
```bash
curl -X POST "http://127.0.0.1:5000/generate-custom-report" \
  -H "Content-Type: application/json" \
  -d '{
    "report_type": "region",
    "period": "آخر 6 أشهر",
    "governorate": "رام الله"
  }'
```

### مثال 3: تقرير فترة مخصصة
```bash
curl -X POST "http://127.0.0.1:5000/generate-custom-report" \
  -H "Content-Type: application/json" \
  -d '{
    "report_type": "period",
    "period": "مخصص",
    "custom_start_date": "2024-01-01",
    "custom_end_date": "2024-03-31",
    "governorate": "نابلس"
  }'
```

### مثال 4: تقرير عن قطعة أرض
```bash
curl -X POST "http://127.0.0.1:5000/generate-custom-report" \
  -H "Content-Type: application/json" \
  -d '{
    "report_type": "parcel",
    "period": "هذا العام",
    "entity": "62"
  }'
```

---

## بيانات الاستجابة

### ملخص التقرير (Summary)
يحتوي على:
- `total_transactions`: عدد المعاملات
- `total_value`: القيمة الإجمالية
- `average_transaction_value`: متوسط قيمة المعاملة
- `total_area`: الكمية الإجمالية (للمناطق)

### تفاصيل المعاملات
كل معاملة تحتوي على:
- `transaction_id`: رقم المعاملة
- `transaction_date`: تاريخ المعاملة
- `price`: السعر
- `transaction_type`: نوع المعاملة (sale, inheritance, etc.)
- `seller_name` / `buyer_name`: أسماء الأطراف
- `locality_name` / `governorate_name`: الموقع
- `area_m2`: المساحة

---

## الرسوم البيانية

يتم إنشاء رسم بياني تلقائياً لكل تقرير:
- **تقرير الشخص**: مقارنة بين المبيعات والمشتريات
- **تقرير المحافظة**: توزيع المعاملات حسب المواقع
- **الرسوم توفر**: ملف PNG يمكن عرضه مباشرة

---

## معالجة الأخطاء

### خطأ الشخص غير الموجود
```json
{
  "status": "error",
  "message": "الشخص 'عمر الطميزي' غير موجود"
}
```

### خطأ في البيانات المرسلة
```json
{
  "status": "error",
  "message": "يجب تحديد اسم الشخص أو رقم الهوية"
}
```

---

## ملاحظات تقنية

- التقارير تُحفظ تلقائياً في مجلد `custom_reports/`
- الرسوم البيانية تُحفظ في مجلد `custom_charts/`
- جميع البيانات تُحفظ بصيغة JSON مع دعم اللغة العربية
- يمكن الوصول للتقارير المحفوظة في أي وقت لاحق
