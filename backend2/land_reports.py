import os
import json
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import mysql.connector

HOST = "localhost"
USER = "root"
PASSWORD = os.getenv("wail")
DATABASE = "palestine_land_system_v5"

def get_connection():
    return mysql.connector.connect(
        host=HOST,
        user=USER,
        password=PASSWORD,
        database=DATABASE
    )

def load_data():
    conn = get_connection()

    transactions = pd.read_sql("""
        SELECT
            transaction_id,
            parcel_id,
            seller_id,
            buyer_id,
            transaction_date,
            price,
            transaction_type
        FROM land_transactions
    """, conn)

    parcels = pd.read_sql("""
        SELECT
            parcel_id,
            locality_id,
            land_type_id,
            oslo_id,
            registration_status,
            area_m2
        FROM land_parcels
    """, conn)

    localities = pd.read_sql("""
        SELECT
            locality_id,
            governorate_id,
            name
        FROM localities
    """, conn)

    governorates = pd.read_sql("""
        SELECT
            governorate_id,
            name
        FROM governorates
    """, conn)

    owners = pd.read_sql("""
        SELECT
            owner_id,
            full_name
        FROM owners
    """, conn)

    land_types = pd.read_sql("""
        SELECT
            land_type_id,
            name
        FROM land_types
    """, conn)

    conn.close()

    return transactions, parcels, localities, governorates, owners, land_types

def build_master_table(transactions, parcels, localities, governorates, owners, land_types):
    transactions["transaction_date"] = pd.to_datetime(transactions["transaction_date"], errors="coerce")

    seller_df = owners[["owner_id", "full_name"]].copy()
    seller_df = seller_df.rename(columns={"owner_id": "seller_id", "full_name": "seller_name"})

    buyer_df = owners[["owner_id", "full_name"]].copy()
    buyer_df = buyer_df.rename(columns={"owner_id": "buyer_id", "full_name": "buyer_name"})

    localities_df = localities[["locality_id", "governorate_id", "name"]].copy()
    localities_df = localities_df.rename(columns={"name": "locality_name"})

    governorates_df = governorates[["governorate_id", "name"]].copy()
    governorates_df = governorates_df.rename(columns={"name": "governorate_name"})

    land_types_df = land_types[["land_type_id", "name"]].copy()
    land_types_df = land_types_df.rename(columns={"name": "land_type_name"})

    master = transactions.merge(
        parcels[["parcel_id", "locality_id", "area_m2", "registration_status", "land_type_id", "oslo_id"]],
        on="parcel_id",
        how="left"
    )

    master = master.merge(
        localities_df,
        on="locality_id",
        how="left"
    )

    master = master.merge(
        governorates_df,
        on="governorate_id",
        how="left"
    )

    master = master.merge(
        land_types_df,
        on="land_type_id",
        how="left"
    )

    master = master.merge(
        seller_df,
        on="seller_id",
        how="left"
    )

    master = master.merge(
        buyer_df,
        on="buyer_id",
        how="left"
    )

    master = master[[
        "transaction_id",
        "parcel_id",
        "transaction_date",
        "transaction_type",
        "price",
        "seller_id",
        "seller_name",
        "buyer_id",
        "buyer_name",
        "locality_id",
        "locality_name",
        "governorate_id",
        "governorate_name",
        "land_type_id",
        "land_type_name",
        "area_m2",
        "registration_status",
        "oslo_id"
    ]]

    return master

def create_reports(master):
    daily_report = master.groupby(master["transaction_date"].dt.date).agg(
        transactions_count=("transaction_id", "count"),
        total_value=("price", "sum"),
        average_price=("price", "mean")
    ).reset_index().rename(columns={"transaction_date": "date"})

    master["month"] = master["transaction_date"].dt.to_period("M").astype(str)

    monthly_report = master.groupby("month").agg(
        transactions_count=("transaction_id", "count"),
        total_value=("price", "sum"),
        average_price=("price", "mean")
    ).reset_index()

    governorate_report = master.groupby("governorate_name").agg(
        transactions_count=("transaction_id", "count"),
        total_value=("price", "sum"),
        average_price=("price", "mean")
    ).reset_index().sort_values(by="transactions_count", ascending=False)

    locality_report = master.groupby(["governorate_name", "locality_name"]).agg(
        transactions_count=("transaction_id", "count"),
        total_value=("price", "sum"),
        average_price=("price", "mean")
    ).reset_index().sort_values(by="transactions_count", ascending=False)

    land_type_report = master.groupby("land_type_name").agg(
        transactions_count=("transaction_id", "count"),
        total_value=("price", "sum"),
        average_price=("price", "mean")
    ).reset_index().sort_values(by="transactions_count", ascending=False)

    top_buyers_report = master.groupby(["buyer_id", "buyer_name"]).agg(
        purchases_count=("transaction_id", "count"),
        total_spent=("price", "sum"),
        average_purchase=("price", "mean")
    ).reset_index().sort_values(by=["purchases_count", "total_spent"], ascending=False)

    top_sellers_report = master.groupby(["seller_id", "seller_name"]).agg(
        sales_count=("transaction_id", "count"),
        total_sales_value=("price", "sum"),
        average_sale=("price", "mean")
    ).reset_index().sort_values(by=["sales_count", "total_sales_value"], ascending=False)

    return (
        daily_report,
        monthly_report,
        governorate_report,
        locality_report,
        land_type_report,
        top_buyers_report,
        top_sellers_report
    )

def save_reports(master, daily_report, monthly_report, governorate_report, locality_report, land_type_report, top_buyers_report, top_sellers_report):
    os.makedirs("reports", exist_ok=True)
    os.makedirs("charts", exist_ok=True)

    # تحويل DataFrames إلى قواميس مع معالجة التواريخ والأرقام
    def df_to_dict(df):
        return df.astype(str).to_dict(orient='records')

    # إنشاء هيكل التقارير
    reports_data = {
        "generated_at": datetime.now().isoformat(),
        "master_table": {
            "total_records": len(master),
            "chart": "charts/master_table.png"
        },
        "daily_report": {
            "data": df_to_dict(daily_report),
            "chart": "charts/daily_report.png"
        },
        "monthly_report": {
            "data": df_to_dict(monthly_report),
            "chart": "charts/monthly_report.png"
        },
        "governorate_report": {
            "data": df_to_dict(governorate_report),
            "chart": "charts/governorate_report.png"
        },
        "locality_report": {
            "data": df_to_dict(locality_report),
            "chart": "charts/locality_report.png"
        },
        "land_type_report": {
            "data": df_to_dict(land_type_report),
            "chart": "charts/land_type_report.png"
        },
        "top_buyers_report": {
            "data": df_to_dict(top_buyers_report),
            "chart": "charts/top_buyers_report.png"
        },
        "top_sellers_report": {
            "data": df_to_dict(top_sellers_report),
            "chart": "charts/top_sellers_report.png"
        }
    }

    # حفظ التقارير بصيغة JSON
    with open("reports/all_reports.json", "w", encoding="utf-8") as f:
        json.dump(reports_data, f, ensure_ascii=False, indent=2)

    # حفظ كل تقرير بملف JSON منفصل
    with open("reports/master_table.json", "w", encoding="utf-8") as f:
        json.dump({"total_records": len(master), "records": df_to_dict(master)}, f, ensure_ascii=False, indent=2)

    with open("reports/daily_report.json", "w", encoding="utf-8") as f:
        json.dump(df_to_dict(daily_report), f, ensure_ascii=False, indent=2)

    with open("reports/monthly_report.json", "w", encoding="utf-8") as f:
        json.dump(df_to_dict(monthly_report), f, ensure_ascii=False, indent=2)

    with open("reports/governorate_report.json", "w", encoding="utf-8") as f:
        json.dump(df_to_dict(governorate_report), f, ensure_ascii=False, indent=2)

    with open("reports/locality_report.json", "w", encoding="utf-8") as f:
        json.dump(df_to_dict(locality_report), f, ensure_ascii=False, indent=2)

    with open("reports/land_type_report.json", "w", encoding="utf-8") as f:
        json.dump(df_to_dict(land_type_report), f, ensure_ascii=False, indent=2)

    with open("reports/top_buyers_report.json", "w", encoding="utf-8") as f:
        json.dump(df_to_dict(top_buyers_report), f, ensure_ascii=False, indent=2)

    with open("reports/top_sellers_report.json", "w", encoding="utf-8") as f:
        json.dump(df_to_dict(top_sellers_report), f, ensure_ascii=False, indent=2)

def draw_charts(daily_report, monthly_report, governorate_report, land_type_report, top_buyers_report, top_sellers_report):
    os.makedirs("charts", exist_ok=True)

    # رسم عدد المعاملات اليومية
    plt.figure(figsize=(10, 5))
    plt.plot(daily_report.iloc[:, 0], daily_report["transactions_count"], marker="o")
    plt.title("Daily Transactions Count")
    plt.xlabel("Date")
    plt.ylabel("Number of Transactions")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig("charts/daily_report.png", dpi=100, bbox_inches='tight')
    plt.close()

    # رسم عدد المعاملات الشهرية
    plt.figure(figsize=(8, 5))
    plt.plot(monthly_report["month"], monthly_report["transactions_count"], marker="o", color="green")
    plt.title("Monthly Transactions Count")
    plt.xlabel("Month")
    plt.ylabel("Number of Transactions")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig("charts/monthly_report.png", dpi=100, bbox_inches='tight')
    plt.close()

    # رسم المعاملات حسب المحافظة
    plt.figure(figsize=(8, 5))
    plt.bar(governorate_report["governorate_name"], governorate_report["transactions_count"], color="skyblue")
    plt.title("Transactions by Governorate")
    plt.xlabel("Governorate")
    plt.ylabel("Number of Transactions")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig("charts/governorate_report.png", dpi=100, bbox_inches='tight')
    plt.close()

    # رسم المعاملات حسب نوع الأرض
    plt.figure(figsize=(8, 5))
    plt.bar(land_type_report["land_type_name"], land_type_report["transactions_count"], color="coral")
    plt.title("Transactions by Land Type")
    plt.xlabel("Land Type")
    plt.ylabel("Number of Transactions")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig("charts/land_type_report.png", dpi=100, bbox_inches='tight')
    plt.close()

    # رسم أكثر المشترين
    if len(top_buyers_report) > 0:
        top_10_buyers = top_buyers_report.head(10)
        plt.figure(figsize=(10, 6))
        plt.barh(top_10_buyers["buyer_name"], top_10_buyers["purchases_count"], color="purple")
        plt.title("Top 10 Buyers")
        plt.xlabel("Number of Purchases")
        plt.tight_layout()
        plt.savefig("charts/top_buyers_report.png", dpi=100, bbox_inches='tight')
        plt.close()

    # رسم أكثر البائعين
    if len(top_sellers_report) > 0:
        top_10_sellers = top_sellers_report.head(10)
        plt.figure(figsize=(10, 6))
        plt.barh(top_10_sellers["seller_name"], top_10_sellers["sales_count"], color="orange")
        plt.title("Top 10 Sellers")
        plt.xlabel("Number of Sales")
        plt.tight_layout()
        plt.savefig("charts/top_sellers_report.png", dpi=100, bbox_inches='tight')
        plt.close()

    # رسم توزيع الأسعار (ماستر تيبل)
    plt.figure(figsize=(10, 5))
    plt.hist(monthly_report["transactions_count"], bins=20, color="teal", edgecolor="black")
    plt.title("Distribution of Transactions Count")
    plt.xlabel("Number of Transactions")
    plt.ylabel("Frequency")
    plt.tight_layout()
    plt.savefig("charts/master_table.png", dpi=100, bbox_inches='tight')
    plt.close()

    print("\n✅ تم حفظ جميع الرسوم البيانية في مجلد 'charts'")

def main():
    transactions, parcels, localities, governorates, owners, land_types = load_data()

    master = build_master_table(
        transactions,
        parcels,
        localities,
        governorates,
        owners,
        land_types
    )

    print("\n===== MASTER TABLE =====")
    print(master.head())

    (
        daily_report,
        monthly_report,
        governorate_report,
        locality_report,
        land_type_report,
        top_buyers_report,
        top_sellers_report
    ) = create_reports(master)

    print("\n========== DAILY REPORT ==========")
    print(daily_report)

    print("\n========== MONTHLY REPORT ==========")
    print(monthly_report)

    print("\n========== GOVERNORATE REPORT ==========")
    print(governorate_report)

    print("\n========== LOCALITY REPORT ==========")
    print(locality_report)

    print("\n========== LAND TYPE REPORT ==========")
    print(land_type_report)

    print("\n========== TOP BUYERS REPORT ==========")
    print(top_buyers_report)

    print("\n========== TOP SELLERS REPORT ==========")
    print(top_sellers_report)

    save_reports(
        master,
        daily_report,
        monthly_report,
        governorate_report,
        locality_report,
        land_type_report,
        top_buyers_report,
        top_sellers_report
    )

    print("\n✅ تم حفظ جميع التقارير في مجلد 'reports' بصيغة JSON")

    draw_charts(
        daily_report,
        monthly_report,
        governorate_report,
        land_type_report,
        top_buyers_report,
        top_sellers_report
    )

if __name__ == "__main__":
    main()