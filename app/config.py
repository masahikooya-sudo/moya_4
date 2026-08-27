import os

# spaCyの日本語モデル名。精度重視なら ja_core_news_lg / trf、
# 動作確認や軽量環境では ja_core_news_sm でも動作する。
SPACY_MODEL = os.environ.get("SPACY_MODEL", "ja_core_news_lg")

# Presidioの検出スコアしきい値（0.0〜1.0）。低いほど検出漏れは減るが誤検出は増える。
DEFAULT_SCORE_THRESHOLD = float(os.environ.get("SCORE_THRESHOLD", "0.35"))

# アップロードファイルの最大サイズ（バイト）。既定20MB(Office系は画像を含みやすいため)。
MAX_UPLOAD_SIZE = int(os.environ.get("MAX_UPLOAD_SIZE", str(20 * 1024 * 1024)))

# アップロード可能な拡張子ごとの種別。file_processing.py のディスパッチで使用する。
SUPPORTED_EXTENSIONS = (".txt", ".csv", ".xlsx", ".docx", ".pptx", ".pdf", ".json")

# 利用ログ(誰が何を入力/アップロードしたか)の出力先。
# 注意: AUDIT_LOG_RAW_INPUT を有効にすると、マスキング前の生データ
# (個人情報を含む可能性がある)がログファイルに保存される。
AUDIT_LOG_DIR = os.environ.get("AUDIT_LOG_DIR", "logs")
AUDIT_LOG_MAX_BYTES = int(os.environ.get("AUDIT_LOG_MAX_BYTES", str(10 * 1024 * 1024)))
AUDIT_LOG_BACKUP_COUNT = int(os.environ.get("AUDIT_LOG_BACKUP_COUNT", "5"))
AUDIT_LOG_RAW_INPUT = os.environ.get("AUDIT_LOG_RAW_INPUT", "true").lower() == "true"

# Googleログインによるアクセス制御。既定で有効。ローカルでの動作確認等で
# 一時的に無効化したい場合のみ AUTH_ENABLED=false を指定する。
AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "true").lower() == "true"
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
# ログインを許可するGoogle Workspaceドメイン(このドメインのアカウントのみアクセス可)。
GOOGLE_ALLOWED_DOMAIN = os.environ.get("GOOGLE_ALLOWED_DOMAIN", "pdpro.jp")
# セッションCookieの署名鍵。未設定の場合は起動のたびにランダム生成する(再起動でログイン状態が切れる)。
SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "")
# セッションCookieに Secure 属性を付与するか(HTTPS配信時のみ true にする)。
SESSION_HTTPS_ONLY = os.environ.get("SESSION_HTTPS_ONLY", "false").lower() == "true"

# サポートするエンティティ種別と日本語表示名、タグ置換時の表示ラベル。
ENTITY_DEFINITIONS = [
    {"code": "PERSON", "label": "人物名"},
    {"code": "LOCATION", "label": "住所・地名"},
    {"code": "ORGANIZATION", "label": "企業名・組織名"},
    {"code": "PHONE_NUMBER", "label": "電話番号"},
    {"code": "EMAIL", "label": "メールアドレス"},
    {"code": "MY_NUMBER", "label": "マイナンバー"},
    {"code": "POSTAL_CODE", "label": "郵便番号"},
    {"code": "CREDIT_CARD", "label": "クレジットカード番号"},
    {"code": "BANK_ACCOUNT", "label": "銀行口座番号"},
    {"code": "PASSPORT", "label": "パスポート番号"},
    {"code": "DATE", "label": "日付"},
    {"code": "TIME", "label": "時刻"},
    {"code": "MONEY", "label": "金額"},
    {"code": "QUANTITY", "label": "数量"},
]

ENTITY_LABELS_JA = {item["code"]: item["label"] for item in ENTITY_DEFINITIONS}
ALL_ENTITY_CODES = [item["code"] for item in ENTITY_DEFINITIONS]
