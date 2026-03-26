"""
evans_YYYY.txt から各コメントを抽出し、reportフォルダにJSONファイルを保存する。
"""

import re
import json
import os
from pathlib import Path

EVANS_DIR = Path(r"C:\Users\nttom\OneDrive\ドキュメント\evans")
REPORT_DIR = Path(r"C:\Projects\evans\report")

# ノイズパターン（ナビゲーション、ページ番号等）
NOISE_PATTERNS = [
    r'\d{4}/\d{2}/\d{2} \d{2}:\d{2}\n?',
    r'レッドエヴァンス 近況情報｜現役[馬⾺]一覧｜東京サラブレッドクラブ\n?',
    r'Members\s*Ｍy page\n?',
    r'Ｍy page\s*\n?',
    r'Members\s*\n?',
    r'こんにちは\s*\n?',
    r'永井[\s　]*知明さん\s*\n?',
    r'ログアウト\s*\n?',
    r'個別のお知らせ\s*\n?',
    r'トップページ\s+所属馬情報.+\n?',
    r'トップページ\s+現役馬情報.+\n?',
    r'トップページ 近況情報.+\n?',
    r'トップページ\s*\n?',
    r'[45]歳 栗東 東田明士厩舎.+\n?',
    r'近況情報\s+調教タイム.+\n?',
    r'近況情報\s*\n?',
    r'調教タイム.+\n?',
    r'出走予定・戦績\s*\n?',
    r'ギャラリー\s*\n?',
    r'メール配信登録\s*\n?',
    r'プロフィール\s*\n?',
    r'アーカ\s*\n?',
    r'https://www\.tokyo-tc\.com/runners/\d+/info[^\n]*\n?',
    r'\d+/\d+\n',  # ページ番号 1/6 等
    r'関東財務局長.+\n?',
    r'会社案内\s*お?\s*\n?',
    r'所属馬情報\s*\n?',
    r'各種お申込み\s*\n?',
    r'ご請求・帳票照会\s*\n?',
    r'会員情報\s*\n?',
    r'お知らせ\s*\n?',
    r'クラブ案内\s*\n?',
    r'関連リンク\s*\n?',
    r'レッドエヴァンス\s*\n?',
    r'栗東 東田明士厩舎\s*\n?',
]

# ノイズとみなす文字列
NOISE_LOCATION_WORDS = {
    'こんにちは', 'ログアウト', 'クラブ案内', '関連リンク', 'お知らせ',
    '会員情報', '所属馬情報', 'プロフィール', 'アーカ', 'Members',
    'Ｍy page', 'メール配信登録', '個別のお知らせ', 'トップページ',
    '調教タイム', '出走予定・戦績', 'ギャラリー', 'レッドエヴァンス',
}


def clean_text(text: str) -> str:
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, '', text)
    # 複数の空行を1行に
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_named_comments(text: str) -> list[tuple[str, str]]:
    """「名前」「コメント」のペアを抽出する"""
    # 「XX調教師」「XX騎手」「助手」「コーチ」等に続く「...」を抽出
    pattern = re.compile(
        r'([^\s「」\n]{1,15}(?:調教師|騎手|助手|コーチ|番頭|牧場長|獣医師|スタッフ|担当者|係員))'
        r'「(.*?)」',
        re.DOTALL
    )
    results = []
    for m in pattern.finditer(text):
        name = m.group(1).strip()
        content = re.sub(r'\s+', ' ', m.group(2)).strip()
        if content:
            results.append((name, content))
    return results


def parse_text_file(txt_path: Path) -> list[dict]:
    """テキストファイルを読み込み、コメントリストを返す"""
    text = txt_path.read_text(encoding='utf-8')

    # 日付パターンで分割（YYYY.MM.DD）
    date_pattern = re.compile(r'(\d{4}\.\d{2}\.\d{2})\n')
    matches = list(date_pattern.finditer(text))

    comments = []
    for i, match in enumerate(matches):
        date_str = match.group(1)  # 例: 2026.03.20
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_raw = text[start:end]

        # ノイズを先に除去してから場所を取得
        section_cleaned = clean_text(section_raw)
        lines = section_cleaned.split('\n')

        # 最初の有効な行を場所として取得
        location = ''
        body_lines = []
        location_found = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if location_found:
                    body_lines.append(line)
                continue
            if not location_found:
                if stripped not in NOISE_LOCATION_WORDS:
                    location = stripped
                    location_found = True
                # ノイズ行はスキップ
            else:
                body_lines.append(line)

        body_raw = '\n'.join(body_lines)

        # ノイズ除去（2回目: body_rawにはすでに1回適用済みだが追加で除去）
        body = clean_text(body_raw)

        # 名前付きコメントを抽出
        named = extract_named_comments(body)

        date_fmt = date_str.replace('.', '-')

        if named:
            for name, content in named:
                # 各名前付きコメントを1件として登録
                comments.append({
                    'date': date_fmt,
                    'location': location,
                    'name': name,
                    'content': content,
                })
        else:
            # 名前なし → locationをnameとして扱い、本文全体をcontentに
            plain = re.sub(r'\s+', ' ', body).strip()
            if plain:
                comments.append({
                    'date': date_fmt,
                    'location': location,
                    'name': location,
                    'content': plain,
                })

    return comments


def save_comments(comments: list[dict]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # 同じ日付・名前が複数ある場合の連番管理
    counter: dict[str, int] = {}

    for comment in comments:
        date = comment['date']
        # ファイル名に使えない文字を除去
        name_safe = re.sub(r'[/\\:*?"<>|\s　]+', '_', comment['name'])[:30]
        base_key = f"{date}_{name_safe}"

        if base_key in counter:
            counter[base_key] += 1
            filename = f"{base_key}_{counter[base_key]}.json"
        else:
            counter[base_key] = 0
            filename = f"{base_key}.json"

        out_path = REPORT_DIR / filename
        out_path.write_text(
            json.dumps(comment, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )

    print(f"保存完了: {len(comments)} 件 → {REPORT_DIR}")


def main():
    all_comments = []
    for year in [2022, 2023, 2024, 2025, 2026]:
        txt_path = EVANS_DIR / f"evans_{year}.txt"
        if not txt_path.exists():
            print(f"スキップ: {txt_path} が見つかりません")
            continue
        print(f"処理中: {txt_path.name}")
        comments = parse_text_file(txt_path)
        print(f"  → {len(comments)} 件")
        all_comments.extend(comments)

    save_comments(all_comments)


if __name__ == '__main__':
    main()
