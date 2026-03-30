"""
04_predict.py — 2026年大阪杯 ML予測 + v5ルールとの統合スコア算出

入力:  ml/models/lgb_model.pkl
       ml/data/raw/osaka_hai_2026_entries.csv  (出走馬データ)
出力:  ml/output/osaka_hai_2026.json
"""

import os
import json
import pickle
import numpy as np
import pandas as pd

MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
OUT_DIR   = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUT_DIR, exist_ok=True)

# ── 2026年大阪杯 出走馬データ（手動入力） ──────────────────
# ルールベースv5の評価を特徴量として取り込む
ENTRIES_2026 = [
    # horse_name, age, sex, affiliation, running_style, popularity,
    # jockey_continued, prev_grade, prev_finish, course_exp_hanshin,
    # career_g1_wins, good_run_count, elimination_level,
    # track_condition(※レース当日確認)
    {
        "horse_name": "メイショウタバル", "age": 5, "sex": "牡", "affiliation": "栗東",
        "running_style": "先行", "popularity": 3, "jockey_continued": 1,
        "prev_grade": "G1", "prev_finish": 13, "course_exp_hanshin": 1,
        "career_g1_wins": 1, "good_run_count": 5, "elimination_level": 0,
        "track_condition": "良",
        "rule_v5": "◎", "rule_note": "好走条件MAX・阪神3戦3勝",
    },
    {
        "horse_name": "ダノンデサイル", "age": 5, "sex": "牡", "affiliation": "栗東",
        "running_style": "差し", "popularity": 2, "jockey_continued": 1,
        "prev_grade": "G1", "prev_finish": 3, "course_exp_hanshin": 0,
        "career_g1_wins": 3, "good_run_count": 4, "elimination_level": 0,
        "track_condition": "良",
        "rule_v5": "○", "rule_note": "G1 3勝・5歳・栗東・阪神初リスク",
    },
    {
        "horse_name": "ショウヘイ", "age": 4, "sex": "牡", "affiliation": "栗東",
        "running_style": "差し", "popularity": 4, "jockey_continued": 1,
        "prev_grade": "G2", "prev_finish": 1, "course_exp_hanshin": 1,
        "career_g1_wins": 0, "good_run_count": 4, "elimination_level": 0,
        "track_condition": "良",
        "rule_v5": "▲", "rule_note": "4歳・関西G1/G2実績・川田継続",
    },
    {
        "horse_name": "クロワデュノール", "age": 4, "sex": "牡", "affiliation": "栗東",
        "running_style": "差し", "popularity": 5, "jockey_continued": 1,
        "prev_grade": "G1", "prev_finish": 2, "course_exp_hanshin": 0,
        "career_g1_wins": 1, "good_run_count": 4, "elimination_level": 0,
        "track_condition": "良",
        "rule_v5": "△", "rule_note": "ダービー馬・阪神初・差し脚質",
    },
    {
        "horse_name": "レーベンスティール", "age": 6, "sex": "牡", "affiliation": "美浦",
        "running_style": "差し", "popularity": 1, "jockey_continued": 1,
        "prev_grade": "G2", "prev_finish": 1, "course_exp_hanshin": 0,
        "career_g1_wins": 0, "good_run_count": 1, "elimination_level": 2,
        "track_condition": "良",
        "rule_v5": "☆A", "rule_note": "中山記念完勝・消し×2（6歳+美浦）穴A型",
    },
    {
        "horse_name": "エコロヴァルツ", "age": 4, "sex": "牡", "affiliation": "栗東",
        "running_style": "先行", "popularity": 6, "jockey_continued": 1,
        "prev_grade": "G2", "prev_finish": 2, "course_exp_hanshin": 0,
        "career_g1_wins": 0, "good_run_count": 5, "elimination_level": 0,
        "track_condition": "良",
        "rule_v5": "候補", "rule_note": "4歳・栗東・先行・好走条件揃う",
    },
    {
        "horse_name": "ヨーホーレイク", "age": 8, "sex": "牡", "affiliation": "栗東",
        "running_style": "差し", "popularity": 9, "jockey_continued": 0,
        "prev_grade": "G2", "prev_finish": 3, "course_exp_hanshin": 0,
        "career_g1_wins": 1, "good_run_count": 0, "elimination_level": 2,
        "track_condition": "良",
        "rule_v5": "☆C", "rule_note": "菊花賞馬・8歳消し・穴C型（超穴）",
    },
    {
        "horse_name": "マテンロウレオ", "age": 7, "sex": "牡", "affiliation": "栗東",
        "running_style": "差し", "popularity": 11, "jockey_continued": 0,
        "prev_grade": "G2", "prev_finish": 6, "course_exp_hanshin": 1,
        "career_g1_wins": 0, "good_run_count": 0, "elimination_level": 3,
        "track_condition": "良",
        "rule_v5": "消し", "rule_note": "7歳・G1複数勝ちなし→Lv.3消し",
    },
]

# ── 特徴量エンジニアリング（02_preprocessと共通） ────────────

def encode_entry(entry: dict) -> dict:
    age = entry["age"]
    aff = entry["affiliation"]
    sty = entry["running_style"]
    trk = entry["track_condition"]
    style_map = {"逃げ": 0, "先行": 1, "差し": 2, "追込": 3}
    track_map  = {"良": 0, "稍重": 1, "重": 2, "不良": 3}
    grade_map  = {"G1": 3, "G2": 2, "G3": 1, "OP": 0}
    pop = entry["popularity"]

    return {
        "age_int":           age,
        "age_good":          int(age in [4, 5]),
        "age_bad":           int(age >= 7),
        "is_ritto":          int(aff == "栗東"),
        "is_miho":           int(aff == "美浦"),
        "is_front_runner":   int(sty in ["逃げ", "先行"]),
        "running_style_enc": style_map.get(sty, 2),
        "course_exp_hanshin": int(entry["course_exp_hanshin"]),
        "career_g1_wins":    int(entry["career_g1_wins"]),
        "has_g1_win":        int(entry["career_g1_wins"] >= 1),
        "popularity":        pop,
        "log_popularity":    np.log1p(pop),
        "is_favorite":       int(pop <= 3),
        "is_long_shot":      int(pop >= 8),
        "jockey_continued":  int(entry["jockey_continued"]),
        "prev_grade_enc":    grade_map.get(entry["prev_grade"], 0),
        "prev_finish":       int(entry["prev_finish"]),
        "prev_top3":         int(entry["prev_finish"] <= 3),
        "track_enc":         track_map.get(trk, 0),
        "is_heavy":          int(track_map.get(trk, 0) >= 2),
        "good_run_count":    int(entry["good_run_count"]),
        "elimination_level": int(entry["elimination_level"]),
        "rule_v5_score":     int(entry["good_run_count"]) - int(entry["elimination_level"]) * 2,
        "is_eliminated":     int(entry["elimination_level"] >= 2),
        "favorite_x_good":   int(pop <= 3) * int(entry["good_run_count"]),
        "age_x_ritto":       int(age in [4, 5]) * int(aff == "栗東"),
    }

FEATURE_COLS = [
    "age_int","age_good","age_bad","is_ritto","is_miho",
    "is_front_runner","running_style_enc","course_exp_hanshin","career_g1_wins","has_g1_win",
    "popularity","log_popularity","is_favorite","is_long_shot","jockey_continued",
    "prev_grade_enc","prev_finish","prev_top3","track_enc","is_heavy",
    "good_run_count","elimination_level","rule_v5_score","is_eliminated",
    "favorite_x_good","age_x_ritto",
]

# ── ルールベーススコア正規化 ────────────────────────────────

RULE_SCORE_MAP = {
    "◎": 1.0, "○": 0.75, "▲": 0.60, "△": 0.45,
    "☆A": 0.30, "☆B": 0.30, "☆C": 0.20, "候補": 0.50,
    "消し": 0.05,
}

# ── 統合スコア・確信度・買い目アドバイス ────────────────────

def get_confidence(integrated_rank: int, elimination_level: int) -> str:
    if integrated_rank == 1 and elimination_level == 0:
        return "★★★ 超高確信"
    elif integrated_rank <= 2 and elimination_level == 0:
        return "★★☆ 高確信"
    elif integrated_rank <= 4 and elimination_level <= 1:
        return "★☆☆ 中確信"
    elif elimination_level >= 2:
        return "☆ 低確信（穴のみ）"
    else:
        return "★☆☆ 中確信"

def get_bet_advice(rule_v5: str, integrated_rank: int, elimination_level: int) -> str:
    if rule_v5 == "◎" and elimination_level == 0:
        return "単勝増額・全ワイド軸"
    elif rule_v5 in ["○", "▲"] and elimination_level == 0:
        return "馬連+ワイド安定"
    elif rule_v5 == "△" and elimination_level == 0:
        return "ワイドのみ（馬連外す）"
    elif rule_v5 in ["☆A", "☆B"]:
        return "ワイド穴◎-☆ 少額"
    elif rule_v5 == "☆C":
        return "3連複◎○▲-☆ 少額"
    elif elimination_level >= 3:
        return "全買い目から除外"
    else:
        return "ワイドのみ"


def predict():
    # モデル読み込み
    model_path = os.path.join(MODEL_DIR, "lgb_model.pkl")
    with open(model_path, "rb") as f:
        model = pickle.load(f)

    # 特徴量行列を作成
    rows = []
    for entry in ENTRIES_2026:
        feats = encode_entry(entry)
        rows.append({**{"horse_name": entry["horse_name"],
                        "rule_v5": entry["rule_v5"],
                        "rule_note": entry["rule_note"],
                        "elimination_level": entry["elimination_level"]},
                     **feats})

    df = pd.DataFrame(rows)
    X = df[FEATURE_COLS].values
    ml_scores = model.predict(X)

    # ルールベーススコア取得
    rule_scores = df["rule_v5"].map(RULE_SCORE_MAP).fillna(0.1).values

    # 統合スコア（ML 60% + ルール 40%）
    integrated = 0.6 * ml_scores + 0.4 * rule_scores
    df["ml_score"]         = ml_scores
    df["rule_score"]       = rule_scores
    df["integrated_score"] = integrated

    # 統合ランキング
    df = df.sort_values("integrated_score", ascending=False).reset_index(drop=True)
    df["integrated_rank"] = df.index + 1

    # 確信度・買い目アドバイス
    df["confidence"] = df.apply(
        lambda r: get_confidence(r["integrated_rank"], r["elimination_level"]), axis=1)
    df["bet_advice"] = df.apply(
        lambda r: get_bet_advice(r["rule_v5"], r["integrated_rank"], r["elimination_level"]), axis=1)

    # JSON出力用に整形
    horses = []
    for _, row in df.iterrows():
        horses.append({
            "name":             row["horse_name"],
            "ml_score":         round(float(row["ml_score"]), 3),
            "rule_v5":          row["rule_v5"],
            "rule_score":       round(float(row["rule_score"]), 2),
            "integrated_score": round(float(row["integrated_score"]), 3),
            "integrated_rank":  int(row["integrated_rank"]),
            "confidence":       row["confidence"],
            "bet_advice":       row["bet_advice"],
            "rule_note":        row["rule_note"],
            "elimination_level": int(row["elimination_level"]),
        })

    output = {
        "race":    "大阪杯 2026",
        "updated": "2026-03-30",
        "model":   "LightGBM v1.0 × ルールベース v5",
        "note":    "ML(60%) + ルールベース v5(40%) の統合スコアでランキング",
        "horses":  horses,
    }

    out_path = os.path.join(OUT_DIR, "osaka_hai_2026.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # 結果表示
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║    2026年 大阪杯 ML×ルールベース 統合予測                    ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"{'順位':>3} {'馬名':16} {'ML確率':>7} {'v5印':>5} {'統合スコア':>9}  {'確信度'}")
    print("─" * 70)
    for h in horses:
        print(f"  {h['integrated_rank']:>2}  {h['name']:16}"
              f"  {h['ml_score']:>6.1%}  {h['rule_v5']:>5}"
              f"  {h['integrated_score']:>8.3f}   {h['confidence']}")
    print("─" * 70)
    print(f"\n✅ 保存: {out_path}")
    return output


if __name__ == "__main__":
    predict()
