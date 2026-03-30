"""
03_train.py — LightGBM学習 + Walk-forward Validation

評価指標:
  - AUC-ROC（3着以内 二値分類精度）
  - Recall@3（レース内上位3頭の予測精度）
  - ROI（疑似回収率）

出力:
  ml/models/lgb_model.pkl
  ml/models/feature_importance.csv
"""

import os
import json
import pickle
import warnings
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, classification_report

warnings.filterwarnings("ignore")

PROC_DIR   = os.path.join(os.path.dirname(__file__), "data", "processed")
MODEL_DIR  = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODEL_DIR, exist_ok=True)

from ml.02_preprocess import FEATURE_COLS, TARGET_COL   # noqa: E402

# ── LightGBM パラメータ（少サンプル向け小さめ設定） ──────────
LGB_PARAMS = {
    "objective":        "binary",
    "metric":           "auc",
    "verbosity":        -1,
    "num_leaves":       8,       # 過学習抑制
    "min_child_samples": 5,
    "learning_rate":    0.05,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq":     1,
    "lambda_l1":        0.5,
    "lambda_l2":        1.0,
    "seed":             42,
}


# ── Walk-forward Validation ──────────────────────────────────

def recall_at_k(df_pred: pd.DataFrame, k: int = 3) -> float:
    """
    各レース（年）内で上位k頭を予測し、実際のtop3と何頭重なるかの平均
    """
    scores = []
    for year, grp in df_pred.groupby("year"):
        pred_top = set(grp.nlargest(k, "pred_prob")["horse_name"])
        actual_top = set(grp[grp["is_top3"] == 1]["horse_name"])
        if actual_top:
            overlap = len(pred_top & actual_top)
            scores.append(overlap / len(actual_top))
    return np.mean(scores) if scores else 0.0


def pseudo_roi(df_pred: pd.DataFrame) -> float:
    """
    単純な疑似ROI: 各レースで予測1位の馬に単勝を買い、的中率を計算
    """
    wins, total = 0, 0
    for year, grp in df_pred.groupby("year"):
        best = grp.loc[grp["pred_prob"].idxmax()]
        if best["finish_int"] == 1:
            wins += 1
        total += 1
    return wins / total if total else 0.0


def walk_forward_cv(df: pd.DataFrame) -> dict:
    years = sorted(df["year"].unique())
    if len(years) < 4:
        print("[WARN] 年数が少なすぎるためCV不可。全データで学習します。")
        return {}

    results = []
    # 最低3年trainできるfoldから開始
    for val_year in years[3:]:
        train_df = df[df["year"] < val_year]
        val_df   = df[df["year"] == val_year]

        X_tr = train_df[FEATURE_COLS].values
        y_tr = train_df[TARGET_COL].values
        X_val = val_df[FEATURE_COLS].values
        y_val = val_df[TARGET_COL].values

        dtrain = lgb.Dataset(X_tr, label=y_tr)
        dval   = lgb.Dataset(X_val, label=y_val, reference=dtrain)

        model = lgb.train(
            LGB_PARAMS,
            dtrain,
            num_boost_round=300,
            valid_sets=[dval],
            callbacks=[lgb.early_stopping(30, verbose=False),
                       lgb.log_evaluation(-1)],
        )

        pred_prob = model.predict(X_val)
        val_df = val_df.copy()
        val_df["pred_prob"] = pred_prob

        auc = roc_auc_score(y_val, pred_prob) if y_val.sum() > 0 else 0.5
        r3  = recall_at_k(val_df, k=3)
        roi = pseudo_roi(val_df)

        results.append({
            "val_year":   val_year,
            "train_size": len(train_df),
            "auc":        round(auc, 3),
            "recall_at3": round(r3, 3),
            "pseudo_roi": round(roi, 3),
        })
        print(f"  fold val={val_year}: AUC={auc:.3f}  Recall@3={r3:.3f}  PseudoROI={roi:.2%}")

    avg = {
        "auc":        round(np.mean([r["auc"]        for r in results]), 3),
        "recall_at3": round(np.mean([r["recall_at3"] for r in results]), 3),
        "pseudo_roi": round(np.mean([r["pseudo_roi"] for r in results]), 3),
    }
    print(f"\n  📊 平均: AUC={avg['auc']}  Recall@3={avg['recall_at3']}  PseudoROI={avg['pseudo_roi']:.2%}")
    return {"folds": results, "avg": avg}


# ── ベースライン: ロジスティック回帰 ────────────────────────

def train_baseline(train_df: pd.DataFrame, test_df: pd.DataFrame) -> float:
    scaler = StandardScaler()
    X_tr = scaler.fit_transform(train_df[FEATURE_COLS])
    X_te = scaler.transform(test_df[FEATURE_COLS])
    y_tr = train_df[TARGET_COL].values
    y_te = test_df[TARGET_COL].values

    lr = LogisticRegression(C=0.1, max_iter=1000, random_state=42)
    lr.fit(X_tr, y_tr)
    pred = lr.predict_proba(X_te)[:, 1]
    auc = roc_auc_score(y_te, pred) if y_te.sum() > 0 else 0.5
    print(f"  Baseline (LogReg) Test AUC: {auc:.3f}")
    return auc


# ── 本番モデル学習（全trainデータ使用） ──────────────────────

def train_final(train_df: pd.DataFrame, test_df: pd.DataFrame):
    X_tr = train_df[FEATURE_COLS].values
    y_tr = train_df[TARGET_COL].values
    X_te = test_df[FEATURE_COLS].values
    y_te = test_df[TARGET_COL].values

    dtrain = lgb.Dataset(X_tr, label=y_tr, feature_name=FEATURE_COLS)

    model = lgb.train(
        LGB_PARAMS,
        dtrain,
        num_boost_round=500,
        callbacks=[lgb.log_evaluation(-1)],
    )

    pred_te = model.predict(X_te)
    test_df = test_df.copy()
    test_df["pred_prob"] = pred_te

    if y_te.sum() > 0:
        auc_te = roc_auc_score(y_te, pred_te)
    else:
        auc_te = 0.5
    r3_te  = recall_at_k(test_df, k=3)
    roi_te = pseudo_roi(test_df)

    print(f"\n  🎯 Test結果: AUC={auc_te:.3f}  Recall@3={r3_te:.3f}  PseudoROI={roi_te:.2%}")

    # 特徴量重要度
    fi = pd.DataFrame({
        "feature":    FEATURE_COLS,
        "importance": model.feature_importance(importance_type="gain"),
    }).sort_values("importance", ascending=False)
    fi_path = os.path.join(MODEL_DIR, "feature_importance.csv")
    fi.to_csv(fi_path, index=False, encoding="utf-8")

    print("\n── Top10 特徴量重要度 ──")
    for _, row in fi.head(10).iterrows():
        bar = "█" * int(row["importance"] / fi["importance"].max() * 20)
        print(f"  {row['feature']:28s} {bar} {row['importance']:.1f}")

    # テスト年の予測詳細
    print("\n── テスト期間 予測詳細 ──")
    for year, grp in test_df.sort_values(["year", "pred_prob"], ascending=[True, False]).groupby("year"):
        print(f"\n  {year}年:")
        for _, r in grp.head(5).iterrows():
            actual = "✓" if r["is_top3"] else "✗"
            print(f"    {actual} {r['horse_name']:16s} 予測確率={r['pred_prob']:.3f}  実際{r['finish_int']}着")

    return model, {
        "test_auc":    round(auc_te, 3),
        "test_recall3": round(r3_te, 3),
        "test_roi":    round(roi_te, 3),
    }, fi


def main():
    train_df = pd.read_csv(os.path.join(PROC_DIR, "train.csv"))
    test_df  = pd.read_csv(os.path.join(PROC_DIR, "test.csv"))
    full_df  = pd.read_csv(os.path.join(PROC_DIR, "full.csv"))

    print(f"Train: {len(train_df)}行 / Test: {len(test_df)}行\n")

    # 1. ベースライン
    print("── ベースライン (ロジスティック回帰) ──")
    train_baseline(train_df, test_df)

    # 2. Walk-forward CV
    print("\n── Walk-forward Validation (LightGBM) ──")
    cv_results = walk_forward_cv(full_df)

    # 3. 本番モデル
    print("\n── 本番モデル学習 (全trainデータ) ──")
    model, metrics, fi = train_final(train_df, test_df)

    # 4. モデル保存
    model_path = os.path.join(MODEL_DIR, "lgb_model.pkl")
    with open(model_path, "wb") as f:
        pickle.dump(model, f)

    meta = {
        "feature_cols": FEATURE_COLS,
        "target_col":   TARGET_COL,
        "lgb_params":   LGB_PARAMS,
        "cv_results":   cv_results,
        "test_metrics": metrics,
        "train_years":  sorted(train_df["year"].unique().tolist()),
        "test_years":   sorted(test_df["year"].unique().tolist()),
    }
    with open(os.path.join(MODEL_DIR, "model_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"\n✅ モデル保存: {model_path}")
    return model, metrics


if __name__ == "__main__":
    main()
