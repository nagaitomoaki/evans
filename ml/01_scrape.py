"""
01_scrape.py — netkeibaから大阪杯・近似G1/G2レースデータを収集

対象レース:
  - 大阪杯    G1 阪神芝2000m  2017〜2025
  - 宝塚記念  G1 阪神芝2200m  2017〜2025
  - 金鯱賞    G2 中京芝2000m  2017〜2025
  - 中山記念  G2 中山芝1800m  2017〜2025

出力: ml/data/raw/{race_name}_{year}.csv
"""

import time
import re
import csv
import os
import requests
from bs4 import BeautifulSoup

# ── 設定 ──────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
SLEEP_SEC = 3.0   # リクエスト間隔（robots.txt 遵守）
OUT_DIR = os.path.join(os.path.dirname(__file__), "data", "raw")
os.makedirs(OUT_DIR, exist_ok=True)

# ── 対象レース定義（netkeiba race_id） ──────────────
# race_id 形式: YYYYRRTTHH
#   YYYY=年 RR=競馬場コード(06=阪神,09=中京,08=中山) TT=開催回 HH=レース番号
# ※ 各年のrace_idはnetkeibaで実際に確認が必要
TARGET_RACES = {
    "osaka_hai": {
        "name": "大阪杯", "grade": "G1", "course": "阪神", "distance": 2000,
        "ids": {
            2017: "201706030411", 2018: "201806030411", 2019: "201906030411",
            2020: "202006030411", 2021: "202106030411", 2022: "202206030411",
            2023: "202306030411", 2024: "202406030411", 2025: "202506030411",
        }
    },
    "takarazuka": {
        "name": "宝塚記念", "grade": "G1", "course": "阪神", "distance": 2200,
        "ids": {
            2017: "201706030811", 2018: "201806030811", 2019: "201906030811",
            2020: "202006030811", 2021: "202106030811", 2022: "202206030811",
            2023: "202306030811", 2024: "202406030811", 2025: "202506030811",
        }
    },
    "kinko_sho": {
        "name": "金鯱賞", "grade": "G2", "course": "中京", "distance": 2000,
        "ids": {
            2017: "201709020811", 2018: "201809020811", 2019: "201909020811",
            2020: "202009020811", 2021: "202109020811", 2022: "202209020811",
            2023: "202309020811", 2024: "202409020811", 2025: "202509020811",
        }
    },
    "nakayama_kinen": {
        "name": "中山記念", "grade": "G2", "course": "中山", "distance": 1800,
        "ids": {
            2017: "201708010811", 2018: "201808010811", 2019: "201908010811",
            2020: "202008010811", 2021: "202108010811", 2022: "202208010811",
            2023: "202308010811", 2024: "202408010811", 2025: "202508010811",
        }
    },
}

# ── スクレイパー ──────────────────────────────────

def fetch_race(race_id: str) -> BeautifulSoup | None:
    url = f"https://db.netkeiba.com/race/{race_id}/"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.encoding = "EUC-JP"
        if resp.status_code != 200:
            print(f"  [WARN] HTTP {resp.status_code}: {url}")
            return None
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"  [ERROR] {url}: {e}")
        return None


def parse_race_result(soup: BeautifulSoup, race_meta: dict, year: int) -> list[dict]:
    """レース結果テーブルをパースして馬ごとのdictリストを返す"""
    rows = []
    table = soup.select_one("table.race_table_01")
    if not table:
        return rows

    # トラック状態・クッション値はページ上部から取得
    track_condition = ""
    cushion_value = ""
    track_info = soup.find(text=re.compile(r"馬場"))
    if track_info:
        track_condition = track_info.strip()

    headers_el = table.select("tr:first-child th")
    col_names = [h.get_text(strip=True) for h in headers_el]

    for tr in table.select("tr")[1:]:
        cells = tr.select("td")
        if len(cells) < 10:
            continue

        def get(idx, default=""):
            if idx < len(cells):
                return cells[idx].get_text(strip=True)
            return default

        # 列インデックスはnetkeibaの標準レイアウトに合わせる
        row = {
            "race_name":   race_meta["name"],
            "grade":       race_meta["grade"],
            "course":      race_meta["course"],
            "distance":    race_meta["distance"],
            "year":        year,
            "finish":      get(0),            # 着順
            "gate_num":    get(1),            # 枠番
            "horse_num":   get(2),            # 馬番
            "horse_name":  get(3),            # 馬名
            "sex_age":     get(4),            # 性齢（例: 牡5）
            "weight_rider": get(5),           # 斤量
            "jockey":      get(6),            # 騎手
            "time":        get(7),            # タイム
            "margin":      get(8),            # 着差
            "odds":        get(9),            # 単勝オッズ
            "popularity":  get(10),           # 人気
            "horse_weight": get(17) if len(cells) > 17 else "",  # 馬体重
            "trainer":     get(18) if len(cells) > 18 else "",   # 調教師
            "track_condition": track_condition,
            "cushion_value": cushion_value,
        }

        # 馬名のリンクからhorse_idを取得
        horse_link = cells[3].select_one("a")
        if horse_link and horse_link.get("href"):
            m = re.search(r"/horse/(\d+)/", horse_link["href"])
            row["horse_id"] = m.group(1) if m else ""
        else:
            row["horse_id"] = ""

        rows.append(row)

    return rows


def scrape_all():
    all_rows = []
    for race_key, meta in TARGET_RACES.items():
        print(f"\n=== {meta['name']} ({meta['grade']}) ===")
        for year, race_id in sorted(meta["ids"].items()):
            out_file = os.path.join(OUT_DIR, f"{race_key}_{year}.csv")
            if os.path.exists(out_file):
                print(f"  {year}: スキップ（既存）")
                # 既存ファイルを読み込んでallに追加
                with open(out_file, encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    all_rows.extend(list(reader))
                continue

            print(f"  {year} (id={race_id}) 取得中...", end=" ")
            soup = fetch_race(race_id)
            if soup is None:
                print("失敗")
                continue

            rows = parse_race_result(soup, meta, year)
            if not rows:
                print("データなし（race_idを確認してください）")
                continue

            # 年別CSV保存
            with open(out_file, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

            all_rows.extend(rows)
            print(f"{len(rows)}頭 OK")
            time.sleep(SLEEP_SEC)

    # 全データ結合CSV
    if all_rows:
        combined_file = os.path.join(OUT_DIR, "all_races_raw.csv")
        with open(combined_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=all_rows[0].keys())
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"\n✅ 全データ保存: {combined_file} ({len(all_rows)}行)")
    else:
        print("\n⚠️  データが取得できませんでした。race_idを確認してください。")

    return all_rows


if __name__ == "__main__":
    scrape_all()
