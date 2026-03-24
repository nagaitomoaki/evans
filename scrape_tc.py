#!/usr/bin/env python3
"""
tokyo-tc.com の馬情報（コメント＋画像）を2022〜2026年分スクレイピングして
  tc_data/YYYY/
    articles.json   ← コメント一覧
    images/         ← 画像ファイル
に保存する。

使い方:
  pip install requests beautifulsoup4
  python scrape_tc.py
"""

import json
import os
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ── 設定 ─────────────────────────────────
HORSE_ID   = "2626"
BASE_URL   = "https://www.tokyo-tc.com"
LOGIN_URL  = f"{BASE_URL}/sign_in"
YEARS      = range(2022, 2027)   # 2022〜2026
OUTPUT_DIR = Path("tc_data")

# 認証情報（コミット前に空欄にすること）
MEMBER_NO = os.environ.get("TC_MEMBER_NO", "35004")
EMAIL     = os.environ.get("TC_EMAIL",     "nt.tomoaki.nagai@gmail.com")
PASSWORD  = os.environ.get("TC_PASSWORD",  "e723wyax")
# ─────────────────────────────────────────


def get_csrf_token(session: requests.Session, url: str) -> str:
    res = session.get(url, timeout=15)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    # Rails 系の authenticity_token
    tag = soup.find("input", {"name": "authenticity_token"})
    if tag:
        return tag["value"]
    # meta タグ fallback
    meta = soup.find("meta", {"name": "csrf-token"})
    return meta["content"] if meta else ""


def login(session: requests.Session) -> bool:
    print("ログイン中...")
    csrf = get_csrf_token(session, LOGIN_URL)
    payload = {
        "authenticity_token": csrf,
        "member[no]":         MEMBER_NO,
        "member[email]":      EMAIL,
        "member[password]":   PASSWORD,
        "commit":             "ログイン",
    }
    res = session.post(LOGIN_URL, data=payload, allow_redirects=True, timeout=15)
    # ログイン成功判定：sign_in ページにリダイレクトされていなければOK
    ok = "sign_in" not in res.url
    print(f"  → {'成功' if ok else '失敗'} ({res.url})")
    return ok


def scrape_year(session: requests.Session, year: int) -> list[dict]:
    url = f"{BASE_URL}/runners/{HORSE_ID}/info?article_at_year={year}"
    print(f"  取得中: {url}")
    res = session.get(url, timeout=15)
    if res.status_code != 200:
        print(f"  ⚠ HTTP {res.status_code}")
        return []

    soup = BeautifulSoup(res.text, "html.parser")
    articles = []

    # ── 記事ブロックを探す（サイト構造に合わせて調整） ──
    # よくあるパターン: article タグ / .article / .entry / .post
    blocks = (
        soup.select("article")
        or soup.select(".article")
        or soup.select(".entry")
        or soup.select(".post")
        or soup.select(".info-article")
        or soup.select(".news-item")
    )

    if not blocks:
        # フォールバック：全テキストを1記事として保存
        text = soup.get_text(separator="\n", strip=True)
        articles.append({"date": str(year), "title": "", "body": text, "images": []})
        return articles

    for block in blocks:
        date_tag  = block.select_one("time, .date, .article-date, .entry-date")
        title_tag = block.select_one("h1, h2, h3, .title, .article-title")
        body_tag  = block.select_one(".body, .content, .text, .article-body, p")

        date  = date_tag.get_text(strip=True)  if date_tag  else ""
        title = title_tag.get_text(strip=True) if title_tag else ""
        body  = body_tag.get_text(separator="\n", strip=True) if body_tag else block.get_text(separator="\n", strip=True)

        imgs = []
        for img in block.find_all("img"):
            src = img.get("src") or img.get("data-src", "")
            if src:
                imgs.append(src if src.startswith("http") else BASE_URL + src)

        articles.append({"date": date, "title": title, "body": body, "images": imgs})

    return articles


def download_image(session: requests.Session, url: str, dest: Path) -> bool:
    try:
        res = session.get(url, timeout=20, stream=True)
        res.raise_for_status()
        dest.write_bytes(res.content)
        return True
    except Exception as e:
        print(f"    画像DL失敗: {url}  ({e})")
        return False


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; scraper)"})

    if not login(session):
        print("ログインに失敗しました。認証情報を確認してください。")
        return

    all_data = {}

    for year in YEARS:
        print(f"\n── {year}年 ──")
        year_dir = OUTPUT_DIR / str(year)
        img_dir  = year_dir / "images"
        img_dir.mkdir(parents=True, exist_ok=True)

        articles = scrape_year(session, year)
        print(f"  記事数: {len(articles)}")

        # 画像ダウンロード
        for i, art in enumerate(articles):
            saved_paths = []
            for j, img_url in enumerate(art["images"]):
                ext  = os.path.splitext(img_url.split("?")[0])[-1] or ".jpg"
                fname = img_dir / f"art{i:03d}_img{j:03d}{ext}"
                if download_image(session, img_url, fname):
                    saved_paths.append(str(fname.relative_to(OUTPUT_DIR)))
                    print(f"    保存: {fname.name}")
                time.sleep(0.3)
            art["images"] = saved_paths

        # JSON 保存
        json_path = year_dir / "articles.json"
        json_path.write_text(
            json.dumps(articles, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  JSON: {json_path}")
        all_data[str(year)] = articles
        time.sleep(1)

    # 全年まとめ
    summary = OUTPUT_DIR / "all.json"
    summary.write_text(
        json.dumps(all_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n✅ 完了。全データ: {summary}")


if __name__ == "__main__":
    main()
