import os
import json
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import mysql.connector
from io import BytesIO
import base64

HOST = "localhost"
USER = "root"
DATABASE = "palestine_land_system_v5"

# الاتصال سيتم تمريره من main.py
_CONNECTION_PASSWORD = None

def set_connection_password(password):
    """تعيين كلمة المرور"""
    global _CONNECTION_PASSWORD
    _CONNECTION_PASSWORD = password

def get_connection():
    if _CONNECTION_PASSWORD is None:
        raise ValueError("كلمة المرور لم يتم تعيينها. استخدم set_connection_password()")
    
    return mysql.connector.connect(
        host=HOST,
        user=USER,
        password=_CONNECTION_PASSWORD,
        database=DATABASE
    )

def get_date_range(period, custom_start=None, custom_end=None):
    """تحويل نص المدى الزمني إلى تواريخ"""
    end_date = datetime.now().date()
    
    if period == "آخر شهر":
        start_date = end_date - timedelta(days=30)
    elif period == "آخر 3 أشهر":
        start_date = end_date - timedelta(days=90)
    elif period == "آخر 6 أشهر":
        start_date = end_date - timedelta(days=180)
    elif period == "هذا العام":
        start_date = datetime(end_date.year, 1, 1).date()
    elif period == "مخصص" and custom_start and custom_end:
        start_date = datetime.strptime(custom_start, "%Y-%m-%d").date()
        end_date = datetime.strptime(custom_end, "%Y-%m-%d").date()
    else:
        start_date = end_date - timedelta(days=30)
    
    return start_date, end_date

def get_person_report(entity_name, period, governorate=None):
    """تقرير عن شخص أو مالك"""
    conn = get_connection()
    start_date, end_date = get_date_range(period)
    
    # البحث عن الشخص برقم أو اسم
    query = """
        SELECT owner_id, full_name FROM owners 
        WHERE full_name LIKE %s OR owner_id LIKE %s
        LIMIT 1
    """
    owners_df = pd.read_sql(query, conn, params=(f"%{entity_name}%", f"%{entity_name}%"))
    
    if owners_df.empty:
        return {"status": "error", "message": f"الشخص '{entity_name}' غير موجود"}
    
    owner_id = int(owners_df.iloc[0]['owner_id'])
    owner_name = str(owners_df.iloc[0]['full_name'])
    
    # معاملات البيع (كبائع)
    sales_query = """
        SELECT lt.transaction_id, lt.transaction_date, lt.price, lt.transaction_type,
               lp.area_m2, lp.registration_status, l.name as locality_name, g.name as governorate_name,
               o.full_name as buyer_name
        FROM land_transactions lt
        JOIN land_parcels lp ON lt.parcel_id = lp.parcel_id
        JOIN localities l ON lp.locality_id = l.locality_id
        JOIN governorates g ON l.governorate_id = g.governorate_id
        JOIN owners o ON lt.buyer_id = o.owner_id
        WHERE lt.seller_id = %s AND lt.transaction_date BETWEEN %s AND %s
    """
    
    # معاملات الشراء (كمشتري)
    purchases_query = """
        SELECT lt.transaction_id, lt.transaction_date, lt.price, lt.transaction_type,
               lp.area_m2, lp.registration_status, l.name as locality_name, g.name as governorate_name,
               o.full_name as seller_name
        FROM land_transactions lt
        JOIN land_parcels lp ON lt.parcel_id = lp.parcel_id
        JOIN localities l ON lp.locality_id = l.locality_id
        JOIN governorates g ON l.governorate_id = g.governorate_id
        JOIN owners o ON lt.seller_id = o.owner_id
        WHERE lt.buyer_id = %s AND lt.transaction_date BETWEEN %s AND %s
    """
    
    sales = pd.read_sql(sales_query, conn, params=(owner_id, start_date, end_date))
    purchases = pd.read_sql(purchases_query, conn, params=(owner_id, start_date, end_date))
    
    conn.close()
    
    report_data = {
        "report_type": "person",
        "generated_at": datetime.now().isoformat(),
        "person": {
            "id": int(owner_id),
            "name": owner_name
        },
        "period": {
            "from": str(start_date),
            "to": str(end_date)
        },
        "summary": {
            "total_sales": len(sales),
            "total_sales_value": float(sales['price'].sum()) if len(sales) > 0 else 0,
            "total_purchases": len(purchases),
            "total_purchases_value": float(purchases['price'].sum()) if len(purchases) > 0 else 0,
            "total_area_sold": float(sales['area_m2'].sum()) if len(sales) > 0 else 0,
            "total_area_purchased": float(purchases['area_m2'].sum()) if len(purchases) > 0 else 0,
        },
        "sales": sales.astype(str).to_dict(orient='records') if len(sales) > 0 else [],
        "purchases": purchases.astype(str).to_dict(orient='records') if len(purchases) > 0 else []
    }
    
    return report_data

def get_parcel_report(parcel_id, period):
    """تقرير عن قطعة أرض"""
    conn = get_connection()
    start_date, end_date = get_date_range(period)
    
    try:
        parcel_id = int(parcel_id)
    except (ValueError, TypeError):
        return {"status": "error", "message": f"رقم القطعة '{parcel_id}' غير صحيح"}
    
    # معلومات القطعة
    parcel_query = """
        SELECT lp.parcel_id, lp.area_m2, lp.registration_status, lt.name as land_type_name,
               l.name as locality_name, g.name as governorate_name
        FROM land_parcels lp
        JOIN land_types lt ON lp.land_type_id = lt.land_type_id
        JOIN localities l ON lp.locality_id = l.locality_id
        JOIN governorates g ON l.governorate_id = g.governorate_id
        WHERE lp.parcel_id = %s
    """
    
    # معاملات هذه القطعة
    transactions_query = """
        SELECT lt.transaction_id, lt.transaction_date, lt.price, lt.transaction_type,
               o1.full_name as seller_name, o2.full_name as buyer_name
        FROM land_transactions lt
        JOIN owners o1 ON lt.seller_id = o1.owner_id
        JOIN owners o2 ON lt.buyer_id = o2.owner_id
        WHERE lt.parcel_id = %s AND lt.transaction_date BETWEEN %s AND %s
        ORDER BY lt.transaction_date DESC
    """
    
    parcel_df = pd.read_sql(parcel_query, conn, params=(parcel_id,))
    transactions_df = pd.read_sql(transactions_query, conn, params=(parcel_id, start_date, end_date))
    
    conn.close()
    
    if parcel_df.empty:
        return {"status": "error", "message": f"القطعة '{parcel_id}' غير موجودة"}
    
    report_data = {
        "report_type": "parcel",
        "generated_at": datetime.now().isoformat(),
        "parcel": {
            "id": int(parcel_df.iloc[0]['parcel_id']),
            "area": float(parcel_df.iloc[0]['area_m2']),
            "land_type": parcel_df.iloc[0]['land_type_name'],
            "locality": parcel_df.iloc[0]['locality_name'],
            "governorate": parcel_df.iloc[0]['governorate_name'],
            "registration_status": parcel_df.iloc[0]['registration_status']
        },
        "period": {
            "from": str(start_date),
            "to": str(end_date)
        },
        "summary": {
            "total_transactions": len(transactions_df),
            "total_value": float(transactions_df['price'].sum()) if len(transactions_df) > 0 else 0,
            "average_transaction_value": float(transactions_df['price'].mean()) if len(transactions_df) > 0 else 0,
        },
        "transactions": transactions_df.astype(str).to_dict(orient='records') if len(transactions_df) > 0 else []
    }
    
    return report_data

def get_region_report(governorate_name, period):
    """تقرير عن منطقة جغرافية"""
    conn = get_connection()
    start_date, end_date = get_date_range(period)
    
    transactions_query = """
        SELECT lt.transaction_id, lt.transaction_date, lt.price, lt.transaction_type,
               l.name as locality_name, lt.parcel_id, lp.area_m2,
               o1.full_name as seller_name, o2.full_name as buyer_name
        FROM land_transactions lt
        JOIN land_parcels lp ON lt.parcel_id = lp.parcel_id
        JOIN localities l ON lp.locality_id = l.locality_id
        JOIN governorates g ON l.governorate_id = g.governorate_id
        JOIN owners o1 ON lt.seller_id = o1.owner_id
        JOIN owners o2 ON lt.buyer_id = o2.owner_id
        WHERE g.name = %s AND lt.transaction_date BETWEEN %s AND %s
        ORDER BY lt.transaction_date DESC
    """
    
    transactions_df = pd.read_sql(transactions_query, conn, params=(governorate_name, start_date, end_date))
    
    # تقرير حسب الموقع
    locality_report = transactions_df.groupby('locality_name').agg({
        'transaction_id': 'count',
        'price': ['sum', 'mean'],
        'area_m2': 'sum'
    }).reset_index() if len(transactions_df) > 0 else pd.DataFrame()
    
    conn.close()
    
    report_data = {
        "report_type": "region",
        "generated_at": datetime.now().isoformat(),
        "governorate": governorate_name,
        "period": {
            "from": str(start_date),
            "to": str(end_date)
        },
        "summary": {
            "total_transactions": len(transactions_df),
            "total_value": float(transactions_df['price'].sum()) if len(transactions_df) > 0 else 0,
            "average_transaction_value": float(transactions_df['price'].mean()) if len(transactions_df) > 0 else 0,
            "total_area": float(transactions_df['area_m2'].sum()) if len(transactions_df) > 0 else 0,
        },
        "transactions": transactions_df.astype(str).to_dict(orient='records') if len(transactions_df) > 0 else [],
        "by_locality": locality_report.astype(str).to_dict(orient='records') if len(locality_report) > 0 else []
    }
    
    return report_data

def get_period_report(start_date_str, end_date_str, governorate=None):
    """تقرير فترة زمنية مخصصة"""
    conn = get_connection()
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    
    if governorate and governorate != "كل المحافظات":
        query = """
            SELECT lt.transaction_id, lt.transaction_date, lt.price, lt.transaction_type,
                   l.name as locality_name, g.name as governorate_name, lt.parcel_id, lp.area_m2,
                   o1.full_name as seller_name, o2.full_name as buyer_name
            FROM land_transactions lt
            JOIN land_parcels lp ON lt.parcel_id = lp.parcel_id
            JOIN localities l ON lp.locality_id = l.locality_id
            JOIN governorates g ON l.governorate_id = g.governorate_id
            JOIN owners o1 ON lt.seller_id = o1.owner_id
            JOIN owners o2 ON lt.buyer_id = o2.owner_id
            WHERE g.name = %s AND lt.transaction_date BETWEEN %s AND %s
            ORDER BY lt.transaction_date DESC
        """
        transactions_df = pd.read_sql(query, conn, params=(governorate, start_date, end_date))
    else:
        query = """
            SELECT lt.transaction_id, lt.transaction_date, lt.price, lt.transaction_type,
                   l.name as locality_name, g.name as governorate_name, lt.parcel_id, lp.area_m2,
                   o1.full_name as seller_name, o2.full_name as buyer_name
            FROM land_transactions lt
            JOIN land_parcels lp ON lt.parcel_id = lp.parcel_id
            JOIN localities l ON lp.locality_id = l.locality_id
            JOIN governorates g ON l.governorate_id = g.governorate_id
            JOIN owners o1 ON lt.seller_id = o1.owner_id
            JOIN owners o2 ON lt.buyer_id = o2.owner_id
            WHERE lt.transaction_date BETWEEN %s AND %s
            ORDER BY lt.transaction_date DESC
        """
        transactions_df = pd.read_sql(query, conn, params=(start_date, end_date))
    
    # تقرير حسب نوع المعاملة
    transaction_type_report = transactions_df.groupby('transaction_type').agg({
        'transaction_id': 'count',
        'price': ['sum', 'mean']
    }).reset_index() if len(transactions_df) > 0 else pd.DataFrame()
    
    conn.close()
    
    report_data = {
        "report_type": "period",
        "generated_at": datetime.now().isoformat(),
        "governorate": governorate or "كل المحافظات",
        "period": {
            "from": str(start_date),
            "to": str(end_date)
        },
        "summary": {
            "total_transactions": len(transactions_df),
            "total_value": float(transactions_df['price'].sum()) if len(transactions_df) > 0 else 0,
            "average_transaction_value": float(transactions_df['price'].mean()) if len(transactions_df) > 0 else 0,
            "total_area": float(transactions_df['area_m2'].sum()) if len(transactions_df) > 0 else 0,
        },
        "transactions": transactions_df.astype(str).to_dict(orient='records') if len(transactions_df) > 0 else [],
        "by_transaction_type": transaction_type_report.astype(str).to_dict(orient='records') if len(transaction_type_report) > 0 else []
    }
    
    return report_data

def generate_custom_report(report_type, period, entity=None, governorate=None, 
                          start_date=None, end_date=None):
    """دالة رئيسية لتوليد التقارير المخصصة"""
    
    if report_type == "person":
        if not entity:
            return {"status": "error", "message": "يجب تحديد اسم الشخص أو رقم الهوية"}
        return get_person_report(entity, period, governorate)
    
    elif report_type == "parcel":
        if not entity:
            return {"status": "error", "message": "يجب تحديد رقم القطعة"}
        return get_parcel_report(entity, period)
    
    elif report_type == "region":
        if not governorate or governorate == "كل المحافظات":
            return {"status": "error", "message": "يجب تحديد المحافظة"}
        return get_region_report(governorate, period)
    
    elif report_type == "period":
        if period == "مخصص" and (not start_date or not end_date):
            return {"status": "error", "message": "يجب تحديد التاريخ الابتدائي والنهائي"}
        return get_period_report(start_date or datetime.now().date(), 
                                end_date or datetime.now().date(), governorate)
    
    else:
        return {"status": "error", "message": f"نوع التقرير '{report_type}' غير معروف"}

def save_custom_report(report_data, report_name=None):
    """حفظ التقرير المخصص"""
    os.makedirs("custom_reports", exist_ok=True)
    
    if report_name is None:
        report_name = f"{report_data['report_type']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    file_path = f"custom_reports/{report_name}.json"
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    
    return file_path

def generate_chart_for_report(report_data):
    """توليد رسم بياني للتقرير المخصص"""
    os.makedirs("custom_charts", exist_ok=True)
    
    report_type = report_data.get('report_type')
    chart_path = None
    
    try:
        if report_type == "person":
            # رسم بياني للمبيعات والمشتريات
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
            
            person_name = report_data['person']['name']
            
            summary = report_data['summary']
            ax1.bar(['المبيعات', 'المشتريات'], 
                   [summary['total_sales'], summary['total_purchases']], 
                   color=['#FF6B6B', '#4ECDC4'])
            ax1.set_title(f'عدد المعاملات - {person_name}')
            ax1.set_ylabel('عدد المعاملات')
            
            ax2.bar(['المبيعات', 'المشتريات'], 
                   [summary['total_sales_value'], summary['total_purchases_value']], 
                   color=['#FF6B6B', '#4ECDC4'])
            ax2.set_title('قيمة المعاملات')
            ax2.set_ylabel('القيمة')
            
            plt.tight_layout()
            chart_name = f"person_{report_data['person']['id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            chart_path = f"custom_charts/{chart_name}.png"
            plt.savefig(chart_path, dpi=100, bbox_inches='tight')
            plt.close()
            
        elif report_type == "region":
            # رسم بياني للمحافظة
            if report_data.get('by_locality'):
                localities = [item['locality_name'] for item in report_data['by_locality']]
                transactions = [float(item[('transaction_id', 'count')]) for item in report_data['by_locality']]
                
                plt.figure(figsize=(10, 6))
                plt.bar(localities, transactions, color='#95E1D3')
                plt.title(f'المعاملات حسب الموقع - {report_data["governorate"]}')
                plt.xlabel('الموقع')
                plt.ylabel('عدد المعاملات')
                plt.xticks(rotation=45)
                plt.tight_layout()
                
                chart_name = f"region_{report_data['governorate']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                chart_path = f"custom_charts/{chart_name}.png"
                plt.savefig(chart_path, dpi=100, bbox_inches='tight')
                plt.close()
        
        return chart_path
    except Exception as e:
        print(f"خطأ في توليد الرسم البياني: {e}")
        return None
