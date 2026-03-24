/**
 * Gmail → GitHub 自動保存スクリプト
 * 対象: @tokyo-tc.com からのメール
 * 保存形式: JSON（emails/YYYY-MM/YYYY-MM-DD_件名.json）
 * 実行: 毎日1回（トリガー設定必要）
 *
 * 【設定方法】
 * 1. https://script.google.com を開く
 * 2. 「新しいプロジェクト」を作成
 * 3. このファイルの内容を貼り付ける
 * 4. 下記の CONFIG を自分の値に変更
 * 5. 「トリガー」→「トリガーを追加」→ 時間主導型・日タイマー を設定
 * 6. 初回は手動で saveNewEmails() を実行して権限を承認
 */

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
//  設定
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
const CONFIG = {
  // GitHub の設定
  GITHUB_TOKEN: "ghp_xxxxxxxxxxxxxxxxxx",  // ← Personal Access Token に変更
  GITHUB_OWNER: "nagaitomoaki",             // ← GitHubユーザー名
  GITHUB_REPO:  "evans",                   // ← リポジトリ名
  GITHUB_BRANCH: "main",                   // ← ブランチ名

  // Gmail フィルタ
  GMAIL_QUERY: "from:@tokyo-tc.com",        // ← 送信元フィルタ

  // 処理済みラベル（自動作成）
  PROCESSED_LABEL: "github-saved",

  // 保存先ディレクトリ
  SAVE_DIR: "emails",
};
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━


/**
 * メインエントリポイント（トリガーで毎日実行）
 */
function saveNewEmails() {
  const label = getOrCreateLabel(CONFIG.PROCESSED_LABEL);
  const threads = GmailApp.search(`${CONFIG.GMAIL_QUERY} -label:${CONFIG.PROCESSED_LABEL}`);

  if (threads.length === 0) {
    console.log("新しいメールはありません");
    return;
  }

  console.log(`${threads.length} 件のスレッドを処理します`);

  for (const thread of threads) {
    const messages = thread.getMessages();
    for (const msg of messages) {
      try {
        saveMessageToGitHub(msg);
      } catch (e) {
        console.error(`メール保存失敗: ${msg.getSubject()} - ${e}`);
      }
    }
    thread.addLabel(label);
  }
}


/**
 * 1通のメールをGitHubに保存
 */
function saveMessageToGitHub(msg) {
  const date    = msg.getDate();
  const subject = msg.getSubject();
  const from    = msg.getFrom();
  const body    = msg.getPlainBody();
  const htmlBody = msg.getBody();

  // 日付フォーマット
  const dateStr = Utilities.formatDate(date, "Asia/Tokyo", "yyyy-MM-dd");
  const yearMonth = Utilities.formatDate(date, "Asia/Tokyo", "yyyy-MM");
  const timestamp = Utilities.formatDate(date, "Asia/Tokyo", "yyyy-MM-dd'T'HH:mm:ss'+09:00'");

  // 添付ファイル処理
  const attachments = [];
  for (const att of msg.getAttachments()) {
    const attName = att.getName();
    const attData = Utilities.base64Encode(att.getBytes());
    const attPath = `${CONFIG.SAVE_DIR}/${yearMonth}/attachments/${dateStr}_${sanitizeFilename(attName)}`;

    // 添付ファイルをGitHubに保存
    commitToGitHub(attPath, attData, `Add attachment: ${attName}`, true);
    attachments.push({ name: attName, path: attPath });
  }

  // メール本体をJSONとして保存
  const emailData = {
    id:          msg.getId(),
    date:        timestamp,
    from:        from,
    subject:     subject,
    body:        body,
    html_body:   htmlBody,
    attachments: attachments,
  };

  const safeName = sanitizeFilename(subject).slice(0, 60) || "no-subject";
  const filePath = `${CONFIG.SAVE_DIR}/${yearMonth}/${dateStr}_${safeName}.json`;
  const content  = JSON.stringify(emailData, null, 2);
  const encoded  = Utilities.base64Encode(content, Utilities.Charset.UTF_8);

  commitToGitHub(filePath, encoded, `Add email: ${subject} (${dateStr})`);
  console.log(`保存完了: ${filePath}`);
}


/**
 * GitHub API 経由でファイルをコミット
 * @param {string}  path      - リポジトリ内のファイルパス
 * @param {string}  content   - base64エンコードされた内容
 * @param {string}  message   - コミットメッセージ
 * @param {boolean} isBinary  - バイナリファイルかどうか
 */
function commitToGitHub(path, content, message, isBinary = false) {
  const apiUrl = `https://api.github.com/repos/${CONFIG.GITHUB_OWNER}/${CONFIG.GITHUB_REPO}/contents/${path}`;
  const headers = {
    "Authorization": `token ${CONFIG.GITHUB_TOKEN}`,
    "Content-Type":  "application/json",
    "Accept":        "application/vnd.github.v3+json",
    "User-Agent":    "GoogleAppsScript",
  };

  // 既存ファイルの SHA を取得（更新の場合に必要）
  let sha = null;
  try {
    const getRes = UrlFetchApp.fetch(apiUrl, { headers, muteHttpExceptions: true });
    if (getRes.getResponseCode() === 200) {
      sha = JSON.parse(getRes.getContentText()).sha;
    }
  } catch (_) {}

  const payload = {
    message,
    content,
    branch: CONFIG.GITHUB_BRANCH,
    ...(sha ? { sha } : {}),
  };

  const res = UrlFetchApp.fetch(apiUrl, {
    method:             "put",
    headers,
    payload:            JSON.stringify(payload),
    muteHttpExceptions: true,
  });

  const code = res.getResponseCode();
  if (code !== 200 && code !== 201) {
    throw new Error(`GitHub API エラー ${code}: ${res.getContentText()}`);
  }
}


/**
 * Gmail ラベルを取得（なければ作成）
 */
function getOrCreateLabel(name) {
  return GmailApp.getUserLabelByName(name) || GmailApp.createLabel(name);
}


/**
 * ファイル名として使える文字列に変換
 */
function sanitizeFilename(name) {
  return name.replace(/[\/\\:*?"<>|\s]/g, "_").replace(/_+/g, "_");
}
