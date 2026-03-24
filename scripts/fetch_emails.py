"""
Gmail → GitHub 自動保存スクリプト
対象: @tokyo-tc.com からの「TTC所属馬近況情報：レッドエヴァンス」メール
実行: GitHub Actions (毎日1回)

必要な環境変数 (GitHub Secrets):
  GMAIL_CLIENT_ID       - OAuth2 クライアントID
  GMAIL_CLIENT_SECRET   - OAuth2 クライアントシークレット
  GMAIL_REFRESH_TOKEN   - リフレッシュトークン
"""

import base64
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ── 設定 ───────────────────────────────────────────
GMAIL_QUERY = 'from:@tokyo-tc.com subject:"TTC所属馬近況情報：レッドエヴァンス"'
SAVE_DIR    = Path("emails")
STATE_FILE  = Path(".github/fetch_state.json")   # 処理済みメールID を記録
JST         = timezone(timedelta(hours=9))
# ────────────────────────────────────────────────────


def get_credentials() -> Credentials:
    """環境変数からOAuth2認証情報を生成"""
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
        client_id=os.environ["GMAIL_CLIENT_ID"],
        client_secret=os.environ["GMAIL_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )
    creds.refresh(Request())
    return creds


def load_processed_ids() -> set:
    """処理済みメールIDをファイルから読み込む"""
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    return set()


def save_processed_ids(ids: set) -> None:
    """処理済みメールIDをファイルに書き込む"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(sorted(ids), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def sanitize_filename(name: str) -> str:
    """ファイル名に使えない文字を _ に変換"""
    return re.sub(r'[/\\:*?"<>|\s]+', "_", name)


def decode_body(payload: dict) -> tuple[str, str]:
    """メール本文（テキスト・HTML）をデコード"""
    text = ""
    html = ""

    def extract(part):
        nonlocal text, html
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data", "")
        if data:
            decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            if mime == "text/plain":
                text = decoded
            elif mime == "text/html":
                html = decoded
        for sub in part.get("parts", []):
            extract(sub)

    extract(payload)
    return text, html


def fetch_attachment(service, user_id: str, msg_id: str, att_id: str) -> bytes:
    """添付ファイルのバイト列を取得"""
    res = service.users().messages().attachments().get(
        userId=user_id, messageId=msg_id, id=att_id
    ).execute()
    return base64.urlsafe_b64decode(res["data"] + "==")


def process_message(service, msg_id: str) -> Path:
    """1通のメールを取得してJSONファイルとして保存"""
    raw = service.users().messages().get(
        userId="me", id=msg_id, format="full"
    ).execute()

    headers = {h["name"].lower(): h["value"] for h in raw["payload"]["headers"]}
    subject  = headers.get("subject", "no-subject")
    from_    = headers.get("from", "")
    date_str = headers.get("date", "")

    # 日付パース（フォールバックあり）
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str).astimezone(JST)
    except Exception:
        dt = datetime.now(JST)

    date_label   = dt.strftime("%Y-%m-%d")
    year_month   = dt.strftime("%Y-%m")
    timestamp    = dt.strftime("%Y-%m-%dT%H:%M:%S+09:00")

    text_body, html_body = decode_body(raw["payload"])

    # 添付ファイル処理
    attachments = []
    for part in raw["payload"].get("parts", []):
        att_id = part.get("body", {}).get("attachmentId")
        if not att_id:
            continue
        att_name = part.get("filename", "attachment")
        att_bytes = fetch_attachment(service, "me", msg_id, att_id)
        safe_att  = sanitize_filename(att_name)
        att_dir   = SAVE_DIR / year_month / "attachments"
        att_dir.mkdir(parents=True, exist_ok=True)
        att_path  = att_dir / f"{date_label}_{safe_att}"
        att_path.write_bytes(att_bytes)
        attachments.append({"name": att_name, "path": str(att_path)})
        print(f"  添付ファイル保存: {att_path}")

    # JSON保存
    email_data = {
        "id":          msg_id,
        "date":        timestamp,
        "from":        from_,
        "subject":     subject,
        "body":        text_body,
        "html_body":   html_body,
        "attachments": attachments,
    }

    safe_subject = sanitize_filename(subject)[:60]
    out_dir  = SAVE_DIR / year_month
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date_label}_{safe_subject}.json"
    out_path.write_text(
        json.dumps(email_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  保存完了: {out_path}")
    return out_path


def main():
    creds   = get_credentials()
    service = build("gmail", "v1", credentials=creds)

    processed = load_processed_ids()

    # メール検索
    results  = service.users().messages().list(userId="me", q=GMAIL_QUERY).execute()
    messages = results.get("messages", [])

    if not messages:
        print("新しいメールはありません")
        return

    new_ids = [m["id"] for m in messages if m["id"] not in processed]
    if not new_ids:
        print(f"未処理メールなし（全{len(messages)}件は処理済み）")
        return

    print(f"{len(new_ids)} 件を処理します")

    saved_count = 0
    for msg_id in new_ids:
        try:
            process_message(service, msg_id)
            processed.add(msg_id)
            saved_count += 1
        except Exception as e:
            print(f"  エラー (id={msg_id}): {e}", file=sys.stderr)

    save_processed_ids(processed)
    print(f"\n完了: {saved_count} 件保存しました")


if __name__ == "__main__":
    main()
