"""
02_preprocess.py — 前処理・特徴量エンジニアリング

入力:  ml/data/raw/osaka_hai_manual.csv（または scrape済み all_races_raw.csv）
出力:
  ml/data/processed/train.csv   (〜2023年)
  ml/data/processed/test.csv    (2024〜2025年)
  ml/data/processed/full.csv    (全データ)
"""

import os
import numpy as np
import pandas as pd

RAW_DIR  = os.path.join(os.path.dirname(__file__), "data", "raw")
PROC_DIR = os.path.join(os.path.dirname(__file__), "data", "processed")
os.makedirs(PROC_DIR, exist_ok=True)


# ── 特徴量エンジニアリング ────────────────────────────────

def load_raw() -> pd.DataFrame:
    """スクレイピング済みCSV or 手動CSVを読み込む（優先度順）"""
    combined = os.path.join(RAW_DIR, "all_races_raw.csv")
    manual   = os.path.join(RAW_DIR, "osaka_hai_manual.csv")
    if os.path.exists(combined):
        print(f"[INFO] スクレイピングデータを使用: {combined}")
        df = pd.read_csv(combined)
    elif os.path.exists(manual):
        print(f"[INFO] 手動データを使用: {manual}")
        df = pd.read_csv(manual)
    else:
        raise FileNotFoundError("データファイルが見つかりません。01_scrape.py を先に実行してください。")
    print(f"  読み込み: {len(df)}行 × {len(df.columns)}列")
    return df


def encode_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # ── 年齢: 4-5歳優位を反映 ──
    df["age_int"] = pd.to_numeric(df["age"], errors="coerce").fillna(5).astype(int)
    df["age_good"] = df["age_int"].isin([4, 5]).astype(int)       # 好走条件
    df["age_bad"]  = (df["age_int"] >= 7).astype(int)             # 消し条件

    # ── 所属 ──
    df["is_ritto"]   = (df["affiliation"] == "栗東").astype(int)
    df["is_miho"]    = (df["affiliation"] == "美浦").astype(int)

    # ── 脚質 ──
    style_map = {"逃げ": 0, "先行": 1, "差し": 2, "追込": 3, "追い込み": 3}
    df["running_style_enc"] = df["running_style"].map(style_map).fillna(2).astype(int)
    df["is_front_runner"]   = df["running_style"].isin(["逃げ", "先行"]).astype(int)

    # ── 馬場状態 ──
    track_map = {"良": 0, "稍重": 1, "重": 2, "不良": 3}
    df["track_enc"] = df["track_condition"].map(track_map).fillna(0).astype(int)
    df["is_heavy"]  = (df["track_enc"] >= 2).astype(int)

    # ── 人気・オッズ ──
    df["popularity"] = pd.to_numeric(df["popularity"], errors="coerce").fillna(9).astype(int)
    df["is_favorite"]     = (df["popularity"] <= 3).astype(int)   # 1〜3番人気
    df["is_long_shot"]    = (df["popularity"] >= 8).astype(int)   # 8番人気以下
    df["log_popularity"]  = np.log1p(df["popularity"])             # 対数変換

    # ── 前走成績 ──
    grade_map = {"G1": 3, "G2": 2, "G3": 1, "OP": 0}
    df["prev_grade_enc"] = df["prev_grade"].map(grade_map).fillna(0).astype(int)
    df["prev_finish"]    = pd.to_numeric(df["prev_finish"], errors="coerce").fillna(5).astype(int)
    df["prev_top3"]      = (df["prev_finish"] <= 3).astype(int)

    # ── 騎手継続 ──
    df["jockey_continued"] = pd.to_numeric(df["jockey_continued"], errors="coerce").fillna(0).astype(int)

    # ── コース実績 ──
    df["course_exp_hanshin"] = pd.to_numeric(df["course_exp_hanshin"], errors="coerce").fillna(0).astype(int)

    # ── G1実績 ──
    df["career_g1_wins"] = pd.to_numeric(df["career_g1_wins"], errors="coerce").fillna(0).astype(int)
    df["has_g1_win"]     = (df["career_g1_wins"] >= 1).astype(int)

    # ── ルールベース特徴量（既存v5モデルを特徴量化） ──
    df["good_run_count"]    = pd.to_numeric(df["good_run_count"],    errors="coerce").fillna(0).astype(int)
    df["elimination_level"] = pd.to_numeric(df["elimination_level"], errors="coerce").fillna(0).astype(int)
    df["rule_v5_score"]     = df["good_run_count"] - df["elimination_level"] * 2
    df["is_eliminated"]     = (df["elimination_level"] >= 2).astype(int)

    # ── 統合スコア（人気×ルールの交互作用） ──
    df["favorite_x_good"] = df["is_favorite"] * df["good_run_count"]
    df["age_x_ritto"]     = df["age_good"]    * df["is_ritto"]

    # ── 目的変数 ──
    df["finish_int"] = pd.to_numeric(df["finish"], errors="coerce").fillna(99).astype(int)
    df["is_top3"]    = (df["finish_int"] <= 3).astype(int)
    df["is_top5"]    = (df["finish_int"] <= 5).astype(int)
    df["is_winner"]  = (df["finish_int"] == 1).astype(int)

    return df


# ── 特徴量リスト ──────────────────────────────────────────

FEATURE_COLS = [
    # 馬個体
    "age_int", "age_good", "age_bad",
    "is_ritto", "is_miho",
    "is_front_runner", "running_style_enc",
    "course_exp_hanshin", "career_g1_wins", "has_g1_win",
    # レース文脈
    "popularity", "log_popularity", "is_favorite", "is_long_shot",
    "jockey_continued",
    "prev_grade_enc", "prev_finish", "prev_top3",
    # 馬場
    "track_enc", "is_heavy",
    # ルールベース統合
    "good_run_count", "elimination_level", "rule_v5_score", "is_eliminated",
    # 交互作用
    "favorite_x_good", "age_x_ritto",
]

TARGET_COL  = "is_top3"   # 主目的変数（3着以内）
TARGET_COL2 = "is_top5"   # 副目的変数（5着以内）


def split_and_save(df: pd.DataFrame):
    """時系列に沿ってtrain/testに分割して保存"""
    # 手元データは大阪杯のみのため2024以降をtest
    train = df[df["year"] <= 2023].copy()
    test  = df[df["year"] >= 2024].copy()

    print(f"\n[INFO] Train: {len(train)}行 ({train['year'].min()}〜{train['year'].max()})")
    print(f"[INFO] Test:  {len(test)}行  ({test['year'].min()}〜{test['year'].max()})")
    print(f"[INFO] Train top3率: {train['is_top3'].mean():.1%}")
    print(f"[INFO] Test  top3率: {test['is_top3'].mean():.1%}")

    # 使用する列のみ保存
    save_cols = FEATURE_COLS + [TARGET_COL, TARGET_COL2, "is_winner",
                                "year", "horse_name", "finish_int"]
    train[save_cols].to_csv(os.path.join(PROC_DIR, "train.csv"), index=False, encoding="utf-8")
    test[save_cols].to_csv(os.path.join(PROC_DIR, "test.csv"),  index=False, encoding="utf-8")
    df[save_cols].to_csv(os.path.join(PROC_DIR, "full.csv"),   index=False, encoding="utf-8")

    print(f"\n✅ 保存完了:")
    print(f"   {PROC_DIR}/train.csv")
    print(f"   {PROC_DIR}/test.csv")
    print(f"   {PROC_DIR}/full.csv")
    return train, test


def main():
    df_raw = load_raw()
    df = encode_features(df_raw)

    print("\n── 特徴量サマリー ──")
    print(df[FEATURE_COLS + ["is_top3"]].describe().round(2).to_string())

    train, test = split_and_save(df)
    return train, test


if __name__ == "__main__":
    main()
