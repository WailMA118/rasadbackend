# fraud_detection/train_model.py
"""
تدريب نموذج كشف الاحتيال - تحديد الأشخاص المتورطين في عمليات التسريب
من خلال تحليل أنماط البيع والشراء
"""

import pandas as pd
import numpy as np
import os
import mysql.connector
import pickle
import json
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix

# ─── الإعدادات ──────────────────────────────────────────────────────────────

HOST = "localhost"
USER = "root"
PASSWORD = os.getenv("DB_PASSWORD", "wail")
DATABASE = "palestine_land_system_v5"
MODEL_DIR = os.path.join("fraud_detection", "models")
MODEL_PATH = os.path.join(MODEL_DIR, "fraud_model.pkl")
FEATURES_PATH = os.path.join(MODEL_DIR, "feature_columns.pkl")

os.makedirs(MODEL_DIR, exist_ok=True)

# ─── دوال قاعدة البيانات ────────────────────────────────────────────────────

def get_connection():
    """إنشاء اتصال بقاعدة البيانات"""
    return mysql.connector.connect(
        host=HOST,
        user=USER,
        password=PASSWORD,
        database=DATABASE
    )

def load_data():
    """تحميل البيانات من قاعدة البيانات"""
    conn = get_connection()

    owners = pd.read_sql("""
        SELECT owner_id, identity_type, full_name, owner_type, residence_country
        FROM owners
    """, conn)

    transactions = pd.read_sql("""
        SELECT transaction_id, parcel_id, seller_id, buyer_id, price, shares_sold, transaction_date, transaction_type
        FROM land_transactions
    """, conn)

    risk = pd.read_sql("""
        SELECT owner_id, risk_score
        FROM owner_risk_profiles
    """, conn)

    leakage_cases = pd.read_sql("""
        SELECT case_id, parcel_id, case_status, suspicion_score
        FROM leakage_cases
    """, conn)

    case_transactions = pd.read_sql("""
        SELECT case_id, transaction_id
        FROM case_transactions
    """, conn)

    conn.close()

    return {
        "owners": owners,
        "transactions": transactions,
        "risk": risk,
        "leakage_cases": leakage_cases,
        "case_transactions": case_transactions
    }

# ─── دوال استخراج الميزات ──────────────────────────────────────────────────

def compute_seller_features(transactions):
    """استخراج ميزات كل بائع من معاملاته"""
    sellers = transactions.copy()
    sellers = sellers.rename(columns={'seller_id': 'owner_id'})
    
    sellers["price"] = pd.to_numeric(sellers["price"], errors="coerce").fillna(0)
    sellers["shares_sold"] = pd.to_numeric(sellers["shares_sold"], errors="coerce").replace(0, np.nan)
    sellers["price_per_share"] = sellers["price"] / sellers["shares_sold"]
    sellers["price_per_share"] = sellers["price_per_share"].replace([np.inf, -np.inf], np.nan)

    agg = sellers.groupby("owner_id").agg(
        num_sales=("transaction_id", "count"),
        avg_sale_price=("price_per_share", "mean"),
        min_sale_price=("price_per_share", "min"),
        max_sale_price=("price_per_share", "max"),
        total_sales_value=("price", "sum"),
        std_sale_price=("price_per_share", "std"),
        gift_sales_ratio=("transaction_type", lambda x: (x == "gift").mean()),
    ).reset_index()

    agg = agg.fillna(0)
    agg.columns = ["owner_id"] + [f"seller_{col}" for col in agg.columns[1:]]
    
    return agg

def compute_buyer_features(transactions):
    """استخراج ميزات كل مشتري من معاملاته"""
    buyers = transactions.copy()
    buyers = buyers.rename(columns={'buyer_id': 'owner_id'})
    
    buyers["price"] = pd.to_numeric(buyers["price"], errors="coerce").fillna(0)
    buyers["shares_sold"] = pd.to_numeric(buyers["shares_sold"], errors="coerce").replace(0, np.nan)
    buyers["price_per_share"] = buyers["price"] / buyers["shares_sold"]
    buyers["price_per_share"] = buyers["price_per_share"].replace([np.inf, -np.inf], np.nan)

    agg = buyers.groupby("owner_id").agg(
        num_purchases=("transaction_id", "count"),
        avg_purchase_price=("price_per_share", "mean"),
        min_purchase_price=("price_per_share", "min"),
        max_purchase_price=("price_per_share", "max"),
        total_purchases_value=("price", "sum"),
        std_purchase_price=("price_per_share", "std"),
    ).reset_index()

    agg = agg.fillna(0)
    agg.columns = ["owner_id"] + [f"buyer_{col}" for col in agg.columns[1:]]
    
    return agg

def compute_owner_identity_features(owners):
    """استخراج ميزات الهوية والنوع"""
    df = owners[["owner_id", "identity_type", "owner_type", "residence_country"]].copy()
    
    # تصنيف نوع الهوية
    def classify_identity(identity_type):
        if pd.isna(identity_type):
            return "UNKNOWN"
        elif "Jerusalem" in str(identity_type):
            return "JR"
        elif "West Bank" in str(identity_type):
            return "WB"
        elif "Gaza" in str(identity_type):
            return "GZ"
        else:
            return "FOREIGN"
    
    df["identity_group"] = df["identity_type"].apply(classify_identity)
    df["is_corporate"] = (df["owner_type"] == "company").astype(int)
    df["is_foreign_resident"] = (~df["residence_country"].isin(["Palestine", "", None]) & df["residence_country"].notna()).astype(int)
    
    return df[["owner_id", "identity_group", "is_corporate", "is_foreign_resident"]]

def create_labels(owners, leakage_cases, case_transactions, transactions):
    """إنشاء التسميات - تحديد الأشخاص المتورطين بعمليات تسريب"""
    open_cases = leakage_cases[leakage_cases["case_status"].astype(str).str.lower() == "open"].copy()
    risky_case_ids = set(open_cases["case_id"].dropna().tolist())

    risky_tx = case_transactions[case_transactions["case_id"].isin(risky_case_ids)].copy()
    risky_tx_ids = set(risky_tx["transaction_id"].dropna().tolist())

    # الأشخاص المتورطين (بائعين أو مشترين)
    risky_tx_data = transactions[transactions["transaction_id"].isin(risky_tx_ids)].copy()
    
    risky_sellers = set(risky_tx_data["seller_id"].dropna().unique())
    risky_buyers = set(risky_tx_data["buyer_id"].dropna().unique())
    risky_people = risky_sellers.union(risky_buyers)

    labels = owners[["owner_id"]].copy()
    labels["is_involved_in_fraud"] = labels["owner_id"].apply(lambda x: 1 if x in risky_people else 0)
    labels["involvement_type"] = labels["owner_id"].apply(
        lambda x: "seller" if x in risky_sellers else ("buyer" if x in risky_buyers else "none")
    )

    return labels

def build_dataset(data):
    """بناء مجموعة البيانات الكاملة مع الميزات والتسميات"""
    owners = data["owners"].copy()
    transactions = data["transactions"].copy()
    risk = data["risk"].copy()
    leakage_cases = data["leakage_cases"].copy()
    case_transactions = data["case_transactions"].copy()

    # استخراج الميزات
    seller_f = compute_seller_features(transactions)
    buyer_f = compute_buyer_features(transactions)
    identity_f = compute_owner_identity_features(owners)
    labels = create_labels(owners, leakage_cases, case_transactions, transactions)

    # دمج البيانات
    df = owners[["owner_id", "full_name"]].copy()
    df = df.merge(seller_f, on="owner_id", how="left")
    df = df.merge(buyer_f, on="owner_id", how="left")
    df = df.merge(identity_f, on="owner_id", how="left")
    df = df.merge(labels, on="owner_id", how="left")
    df = df.merge(risk, left_on="owner_id", right_on="owner_id", how="left")

    feature_cols = [
        "seller_num_sales",
        "seller_avg_sale_price",
        "seller_min_sale_price",
        "seller_max_sale_price",
        "seller_total_sales_value",
        "seller_std_sale_price",
        "seller_gift_sales_ratio",
        "buyer_num_purchases",
        "buyer_avg_purchase_price",
        "buyer_min_purchase_price",
        "buyer_max_purchase_price",
        "buyer_total_purchases_value",
        "buyer_std_purchase_price",
        "is_corporate",
        "is_foreign_resident",
        "risk_score"
    ]

    # إضافة الأعمدة الناقصة
    for col in feature_cols:
        if col not in df.columns:
            df[col] = 0

    df[feature_cols] = df[feature_cols].fillna(0)
    df["is_involved_in_fraud"] = df["is_involved_in_fraud"].fillna(0).astype(int)

    return df, feature_cols

# ─── دوال التدريب ──────────────────────────────────────────────────────────

def train_model(df, feature_cols):
    """تدريب نموذج Random Forest"""
    X = df[feature_cols].copy()
    y = df["is_involved_in_fraud"].copy()

    # موازنة مجموعة البيانات
    df_combined = pd.concat([X, y], axis=1)

    majority = df_combined[df_combined["is_involved_in_fraud"] == 0]
    minority = df_combined[df_combined["is_involved_in_fraud"] == 1]

    if len(minority) > 0 and len(majority) > 0:
        minority_upsampled = minority.sample(min(len(majority), len(minority) * 3), replace=True, random_state=42)
        df_balanced = pd.concat([majority, minority_upsampled])
    else:
        df_balanced = df_combined

    X = df_balanced[feature_cols]
    y = df_balanced["is_involved_in_fraud"]

    print("\n📊 توزيع التسميات:")
    print(y.value_counts())

    if y.nunique() < 2 or y.value_counts().min() < 2:
        print("\n❌ لا توجد بيانات مُصنَّفة كافية للتدريب.")
        return None, None, None

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.30, random_state=42, stratify=y
    )

    model = RandomForestClassifier(
        n_estimators=300,
        max_depth=10,
        random_state=42,
        class_weight={0: 1, 1: 10}
    )

    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    print("\n🎯 الدقة:")
    accuracy = accuracy_score(y_test, y_pred)
    print(f"{accuracy:.4f}")

    print("\n📋 تقرير التصنيف:")
    report = classification_report(y_test, y_pred, digits=4, output_dict=True)
    print(classification_report(y_test, y_pred, digits=4))

    print("\n🔢 مصفوفة الالتباس:")
    cm = confusion_matrix(y_test, y_pred)
    print(cm)

    results = {
        "accuracy": accuracy,
        "classification_report": report,
        "confusion_matrix": cm.tolist(),
        "label_distribution": y.value_counts().to_dict(),
        "training_samples": len(X_train),
        "test_samples": len(X_test)
    }

    return model, feature_cols, results

def save_model(model, feature_cols):
    """حفظ النموذج والميزات"""
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)

    with open(FEATURES_PATH, "wb") as f:
        pickle.dump(feature_cols, f)

    print(f"✅ تم حفظ النموذج → {MODEL_PATH}")
    print(f"✅ تم حفظ الميزات → {FEATURES_PATH}")

def main():
    """الدالة الرئيسية للتدريب"""
    print("🚀 بدء تدريب نموذج كشف الأشخاص المتورطين بعمليات التسريب...")

    try:
        print("\n📦 تحميل البيانات...")
        data = load_data()

        print("\n⚙️  بناء الميزات...")
        df, feature_cols = build_dataset(data)

        print(f"\n📊 مجموعة البيانات جاهزة: {df.shape[0]} شخص × {df.shape[1]} عمود")
        print(f"🔢 الميزات: {len(feature_cols)}")
        print(f"🎯 الأشخاص المتورطين: {df['is_involved_in_fraud'].sum()}")

        print("\n🎯 تدريب النموذج...")
        model, feature_cols, results = train_model(df, feature_cols)

        if model is not None:
            save_model(model, feature_cols)

            results_path = os.path.join(MODEL_DIR, "training_results.json")
            with open(results_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"✅ تم حفظ نتائج التدريب → {results_path}")

            dataset_path = os.path.join(MODEL_DIR, "training_dataset.csv")
            df.to_csv(dataset_path, index=False)
            print(f"✅ تم حفظ مجموعة البيانات → {dataset_path}")

            return {
                "status": "success",
                "message": "تم تدريب النموذج بنجاح",
                "model_type": "Fraud Detection - Person Involvement",
                "model_path": MODEL_PATH,
                "features_path": FEATURES_PATH,
                "results_path": results_path,
                "dataset_path": dataset_path,
                "results": results
            }

        else:
            return {
                "status": "error",
                "message": "فشل في تدريب النموذج - بيانات غير كافية"
            }

    except Exception as e:
        print(f"❌ خطأ في التدريب: {str(e)}")
        return {
            "status": "error",
            "message": f"خطأ في التدريب: {str(e)}"
        }

if __name__ == "__main__":
    result = main()
    print("\n" + "="*50)
    print("نتيجة التدريب:")
    print(json.dumps(result, indent=2, ensure_ascii=False))