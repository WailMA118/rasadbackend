import pandas as pd
import numpy as np
import os
import mysql.connector
import pickle
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix

HOST = "localhost"
USER = "root"
PASSWORD = os.getenv("DB_PASSWORD")
DATABASE = "palestine_land_system_v5"
MODEL_PATH = "trained_model.pkl"

def get_connection():
    return mysql.connector.connect(
        host=HOST,
        user=USER,
        password=PASSWORD,
        database=DATABASE
    )

def load_data():
    conn = get_connection()

    parcels = pd.read_sql("SELECT parcel_id FROM land_parcels", conn)

    transactions = pd.read_sql("""
        SELECT transaction_id, parcel_id, buyer_id, seller_id, price, shares_sold, transaction_date
        FROM land_transactions
    """, conn)

    owners = pd.read_sql("""
        SELECT owner_id, identity_type, full_name
        FROM owners
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
        "parcels": parcels,
        "transactions": transactions,
        "owners": owners,
        "risk": risk,
        "leakage_cases": leakage_cases,
        "case_transactions": case_transactions
    }

def compute_price_features(transactions):
    df = transactions.copy()
    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0)
    df["shares_sold"] = pd.to_numeric(df["shares_sold"], errors="coerce").replace(0, np.nan)
    df["price_per_share"] = df["price"] / df["shares_sold"]
    df["price_per_share"] = df["price_per_share"].replace([np.inf, -np.inf], np.nan)

    agg = df.groupby("parcel_id").agg(
        price_mean=("price_per_share", "mean"),
        price_min=("price_per_share", "min"),
        price_max=("price_per_share", "max"),
        price_std=("price_per_share", "std"),
        num_transactions=("transaction_id", "count")
    ).reset_index()

    return agg

def compute_owner_features(transactions, owners):
    df = transactions.merge(owners, left_on="buyer_id", right_on="owner_id", how="left")

    def classify_owner(identity_type):
        if identity_type == "Jerusalem ID":
            return "JR"
        elif identity_type == "West Bank ID":
            return "WB"
        else:
            return "FOREIGN"

    df["buyer_group"] = df["identity_type"].apply(classify_owner)

    agg = (
        df.groupby("parcel_id")["buyer_group"]
        .value_counts(normalize=True)
        .unstack()
        .fillna(0)
        .reset_index()
    )

    rename_map = {}
    for col in agg.columns:
        if col != "parcel_id":
            rename_map[col] = f"buyer_{col}_ratio"
    agg = agg.rename(columns=rename_map)

    for col in ["buyer_JR_ratio", "buyer_WB_ratio", "buyer_FOREIGN_ratio"]:
        if col not in agg.columns:
            agg[col] = 0

    return agg

def compute_risk_features(transactions, risk):
    df = transactions.merge(risk, left_on="buyer_id", right_on="owner_id", how="left")
    df["risk_score"] = pd.to_numeric(df["risk_score"], errors="coerce").fillna(0)

    agg = df.groupby("parcel_id").agg(
        risk_mean=("risk_score", "mean"),
        risk_max=("risk_score", "max")
    ).reset_index()

    return agg

def create_labels(parcels, leakage_cases, case_transactions, transactions):
    open_cases = leakage_cases[leakage_cases["case_status"].astype(str).str.lower() == "open"].copy()
    risky_case_ids = set(open_cases["case_id"].dropna().tolist())

    risky_tx = case_transactions[case_transactions["case_id"].isin(risky_case_ids)].copy()
    risky_tx_ids = set(risky_tx["transaction_id"].dropna().tolist())

    risky_parcels = transactions[transactions["transaction_id"].isin(risky_tx_ids)]["parcel_id"].dropna().unique()

    labels = parcels.copy()
    labels["label"] = labels["parcel_id"].apply(lambda x: 1 if x in risky_parcels else 0)

    return labels

def build_dataset(data):
    parcels = data["parcels"].copy()
    transactions = data["transactions"].copy()
    owners = data["owners"].copy()
    risk = data["risk"].copy()
    leakage_cases = data["leakage_cases"].copy()
    case_transactions = data["case_transactions"].copy()

    price_f = compute_price_features(transactions)
    owner_f = compute_owner_features(transactions, owners)
    risk_f = compute_risk_features(transactions, risk)
    labels = create_labels(parcels, leakage_cases, case_transactions, transactions)

    df = parcels.merge(price_f, on="parcel_id", how="left")
    df = df.merge(owner_f, on="parcel_id", how="left")
    df = df.merge(risk_f, on="parcel_id", how="left")
    df = df.merge(labels, on="parcel_id", how="left")

    feature_cols = [
        "price_mean",
        "price_min",
        "price_max",
        "price_std",
        "num_transactions",
        "buyer_JR_ratio",
        "buyer_WB_ratio",
        "buyer_FOREIGN_ratio",
        "risk_mean",
        "risk_max"
    ]

    for col in feature_cols:
        if col not in df.columns:
            df[col] = 0

    df[feature_cols] = df[feature_cols].fillna(0)
    df["label"] = df["label"].fillna(0).astype(int)

    return df, feature_cols

def train_model(df, feature_cols):
    X = df[feature_cols].copy()
    y = df["label"].copy()

    # balance the dataset
    df_combined = pd.concat([X, y], axis=1)

    majority = df_combined[df_combined["label"] == 0]
    minority = df_combined[df_combined["label"] == 1]

    minority_upsampled = minority.sample(len(majority), replace=True, random_state=42)

    df_balanced = pd.concat([majority, minority_upsampled])

    X = df_balanced[feature_cols]
    y = df_balanced["label"]

    print("\nLABEL DISTRIBUTION")
    print(y.value_counts())

    if y.nunique() < 2 or y.value_counts().min() < 2:
        print("\nNot enough balanced labeled data for train/test split.")
        return None, X, y, None, None, None, None

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.30,
        random_state=42,
        stratify=y
    )

    model = RandomForestClassifier(
        n_estimators=300,
        max_depth=10,
        random_state=42,
        class_weight={0: 1, 1: 5}
    )

    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    print("\nACCURACY")
    print(accuracy_score(y_test, y_pred))

    print("\nCLASSIFICATION REPORT")
    print(classification_report(y_test, y_pred, digits=4))

    print("\nCONFUSION MATRIX")
    print(confusion_matrix(y_test, y_pred))

    return model, X, y, X_test, y_test, y_pred, X_train

def save_model(model):
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)

def predict_all(model, df, feature_cols):
    X_all = df[feature_cols].copy()
    preds = model.predict(X_all)

    results = df[["parcel_id", "label"]].copy()
    results["predicted_label"] = preds

    if hasattr(model, "predict_proba"):
        probs = model.predict_proba(X_all)
        if probs.shape[1] > 1:
            results["prediction_probability"] = probs[:, 1]
        else:
            results["prediction_probability"] = probs[:, 0]
    else:
        results["prediction_probability"] = None

    results["actual_label_name"] = results["label"].map({0: "Not Suspicious", 1: "Suspicious"})
    results["predicted_label_name"] = results["predicted_label"].map({0: "Not Suspicious", 1: "Suspicious"})

    return results

def main():
    data = load_data()
    df, feature_cols = build_dataset(data)

    print("\nDATASET READY")
    print(df.head())

    model, X, y, X_test, y_test, y_pred, X_train = train_model(df, feature_cols)

    df.to_csv("dataset_from_mysql.csv", index=False)
    print("\nSaved: dataset_from_mysql.csv")

    if model is not None:
        save_model(model)
        print(f"Saved: {MODEL_PATH}")

        results = predict_all(model, df, feature_cols)
        results.to_csv("parcel_predictions.csv", index=False)
        print("Saved: parcel_predictions.csv")

        print("\nPREDICTIONS")
        print(results.head(20))
    else:
        print("\nModel was not trained because labeled data is not enough.")

if __name__ == "__main__":
    main()