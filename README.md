# 日本語マスキングツール

Microsoft Presidio と spaCy の日本語モデルを使って、テキスト中の個人情報・機密情報をマスキングするWebアプリです。

## 検出できるエンティティ種別

| エンティティ | 表示名 | 検出方法 |
| --- | --- | --- |
| PERSON | 人物名 | spaCy 日本語NER |
| LOCATION | 住所・地名 | spaCy 日本語NER |
| ORGANIZATION | 企業名・組織名 | spaCy 日本語NER |
| DATE | 日付 | spaCy 日本語NER |
| TIME | 時刻 | spaCy 日本語NER |
| MONEY | 金額 | spaCy 日本語NER |
| QUANTITY | 数量 | spaCy 日本語NER |
| PHONE_NUMBER | 電話番号 | 正規表現 |
| EMAIL | メールアドレス | 正規表現 |
| MY_NUMBER | マイナンバー | 正規表現 + 文脈語 |
| POSTAL_CODE | 郵便番号 | 正規表現 |
| CREDIT_CARD | クレジットカード番号 | Presidio標準(Luhnチェック) |
| BANK_ACCOUNT | 銀行口座番号 | 正規表現 + 文脈語 |
| PASSPORT | パスポート番号 | 正規表現 |

> マイナンバー・銀行口座番号は単なる数字列のため誤検出/検出漏れが起こり得ます。
> 「マイナンバー」「口座番号」等の文脈語が近くにあるとスコアが上がるようPresidioの
> コンテキスト機能を利用していますが、重要な用途では出力結果を必ず目視確認してください。

## 機能

- 直接入力したテキストのマスキング
- ファイルをアップロードしてマスキングし、ダウンロード
  - 対応形式: テキスト(`.txt`) / CSV(`.csv`) / Excel(`.xlsx`) / Word(`.docx`) / PowerPoint(`.pptx`) / PDF(`.pdf`) / JSON(`.json`)
  - CSV/Excel/JSONは行・列(シート)構造やオブジェクト構造を保持したまま各セル・各値をマスキングします
  - **CSV/Excel/JSONは列名(先頭行のヘッダー、またはJSONのキー名)からもPIIの種別を判定します**。
    「氏名」「ふりがな」「住所」「会社名」「メールアドレス」等の列名を検出した場合、その列の値は
    (単語単体でNERが検出しづらい場合でも)内容によらず該当エンティティとして丸ごとマスキングします。
    どの列名がどのエンティティに対応するかは `app/column_matcher.py` を参照してください。
    この列名ベースの判定も、画面で選択したエンティティ種別(チェックボックス)の範囲内でのみ働きます。
  - **アップロード後、実際にマスキングする前に確認画面を表示します**(下記「アップロード時の確認フロー」参照)。
    列名から推定した種別を人が確認・修正できるほか、PDF/PowerPointのように列が明確でない
    ファイルでは、自動判定だけでは見落とし・誤検出が避けられないため、検出候補を一覧表示して
    実際にマスキングする項目をユーザーが選んでから処理します。
  - Word/PowerPointは段落・表のテキストをマスキングします(書式は段落内の先頭runに統合されます)
  - PDFはテキストをその場で書き換えるとレイアウトが崩れるため、検出箇所を黒塗り(redaction)して
    その上にラベル/マスク文字を重ねる方式でマスキングします
  - テキスト/CSV は文字コードを UTF-8 (BOM有無) / Shift_JIS(cp932) / EUC-JP から自動判定します
- マスキング対象エンティティの選択(チェックボックス)
- 置換方式の選択
  - タグ置換: `[人物名]` のような日本語ラベルに置換(既定)
  - マスク文字: `*` に置換
  - 完全に削除: 検出箇所を削除

## アップロード時の確認フロー

ファイルアップロードは「① 解析(マスキングはまだしない) → ② 確認 → ③ 実際にマスキング」の
2段階で処理します(直接入力したテキストは対象外で、従来通り1回の操作で処理されます)。

1. ファイルを選択して「個人情報をマスキングする」を押すと、まず `POST /api/analyze/file` で
   ファイルを解析します(この時点ではファイルは書き換えません)。
2. 解析結果に応じて、確認画面が表示されます。
   - **CSV/Excel/JSON(列がある形式)**: 列名(ヘッダー/キー名)ごとに、`app/column_matcher.py` が
     推定したエンティティ種別がプルダウンで表示されます。列の先頭付近の値もサンプルとして
     表示されるので、推定が誤っていないか、マスキングすべき列が「対象外」になっていないかを
     確認し、必要であれば選び直せます。
   - **TXT/Word/PowerPoint/PDF(明確な列を持たない形式)**: NERで検出されたPII候補が
     種別・値・出現回数付きの一覧(チェックボックス)で表示されます。誤検出があればチェックを
     外すことで、その項目はマスキングされません。
   - 解析の結果、候補が1件も無かった場合は確認画面を出さずにそのままマスキングします。
3. 内容を確認して「確認内容でマスキングを実行」を押すと、選んだ内容で
   `POST /api/mask/file` を呼び出し、実際にマスキングしたファイルをダウンロードできます。

ファイルを選び直したり、マスキング対象エンティティ(チェックボックス)を変更したりすると、
確認内容は破棄され、次回実行時に解析からやり直します(置換方式の変更は解析結果に影響しないため、
確認済みの内容はそのまま使われます)。

## Googleログインによるアクセス制御

既定 (`AUTH_ENABLED=true`) では、アプリへのアクセス前にGoogleアカウントでのログインを要求します。
ログイン後、指定したGoogle Workspaceドメイン(既定: `pdpro.jp`)のアカウントのみアクセスを許可し、
それ以外のアカウントは `/login` へ差し戻されます。認証・認可は `app/auth.py` / `app/main.py` の
`AuthMiddleware` で実装しています。

### Google Cloud側の設定

1. [Google Cloud Console](https://console.cloud.google.com/) で対象プロジェクトを開く(なければ作成)。
2. 「APIとサービス」→「OAuth同意画面」で、ユーザーの種類(社内利用なら「内部」を推奨)や
   アプリ名等を設定する。
3. 「APIとサービス」→「認証情報」→「認証情報を作成」→「OAuthクライアントID」で
   アプリケーションの種類「ウェブアプリケーション」を選択する。
4. 「承認済みのリダイレクトURI」に、実際に公開するURLの `/auth/callback` を追加する。
   - 例: `http://localhost:8000/auth/callback`(ローカル確認用)
   - 例: `https://mask.example.com/auth/callback`(本番用ドメイン)
5. 発行された「クライアントID」「クライアントシークレット」を控える。

### アプリ側の設定

```bash
cp .env.example .env
```

`.env` を編集し、以下を設定する。

| 環境変数 | 説明 |
| --- | --- |
| `GOOGLE_CLIENT_ID` | Google Cloud Consoleで発行したクライアントID(必須) |
| `GOOGLE_CLIENT_SECRET` | 同クライアントシークレット(必須) |
| `GOOGLE_ALLOWED_DOMAIN` | ログインを許可するGoogle Workspaceドメイン(既定: `pdpro.jp`) |
| `SESSION_SECRET_KEY` | セッションCookie署名鍵。`openssl rand -hex 32` 等で生成した値を推奨 |

`SESSION_SECRET_KEY` を省略すると起動のたびにランダム生成されるため、再起動でログイン状態が
切れます(動作確認程度であれば省略可)。`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` が未設定の
まま `AUTH_ENABLED=true` で起動しようとした場合、アプリは起動時にエラーで停止します
(意図せず無防備な状態で公開されることを防ぐため)。

ローカルでの動作確認等でログインを一時的に無効化したい場合は `AUTH_ENABLED=false` を指定します。

```bash
AUTH_ENABLED=false uvicorn app.main:app --reload
```

社内ネットワーク限定などHTTPSでの配信でない場合は `SESSION_HTTPS_ONLY=false`(既定)のままにします。
HTTPSでの配信時は `SESSION_HTTPS_ONLY=true` を設定し、セッションCookieに `Secure` 属性を付与してください。

## セットアップ

### ローカル実行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 日本語モデルをダウンロード(精度重視: lg / 軽量: sm)
python -m spacy download ja_core_news_lg

cp .env.example .env   # Google認証の設定(上記参照)

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

ブラウザで `http://localhost:8000` を開くとログイン画面が表示されます。

環境変数 `SPACY_MODEL` で使用するモデルを切り替えられます(既定: `ja_core_news_lg`)。
動作確認だけしたい場合はダウンロードが軽い `ja_core_news_sm` を指定してください。

```bash
SPACY_MODEL=ja_core_news_sm uvicorn app.main:app --reload
```

### Docker

```bash
cp .env.example .env   # Google認証の設定(上記参照)
docker compose up --build
```

`http://localhost:8000` でアクセスできます。使用するモデルは
`SPACY_MODEL` 環境変数で切り替え可能です。

```bash
SPACY_MODEL=ja_core_news_sm docker compose up --build
```

## API

- `GET /api/entities` — 選択可能なエンティティ種別一覧
- `POST /api/mask/text` — `{ "text": "...", "entities": ["PERSON", ...], "style": "tag" }`
- `POST /api/analyze/file` — `multipart/form-data` (`file`, `entities`(カンマ区切り, 省略可))。
  ファイルをマスキングせずに解析し、確認用の候補を返す(アップロード時の確認フロー参照)。
  - CSV/Excel/JSON: `{"kind": "tabular", "groups": [{"group": シート名またはnull, "columns": [{"key", "header", "suggested", "suggested_label", "sample"}, ...]}]}`
  - TXT/Word/PowerPoint/PDF: `{"kind": "freeform", "candidates": [{"entity_type", "entity_label", "text", "sample", "count"}, ...]}`
- `POST /api/mask/file` — `multipart/form-data` (`file`, `entities`(カンマ区切り, 省略可), `style`,
  `column_overrides`(省略可), `confirmed_candidates`(省略可))
  - `column_overrides`: CSV/Excel/JSON向け。`/api/analyze/file` が返した `key` をキーとし、
    値にエンティティ種別または `null` を指定するJSONオブジェクト文字列。指定した場合、列名からの
    自動判定の代わりに使用する。
  - `confirmed_candidates`: TXT/Word/PowerPoint/PDF向け。`/api/analyze/file` が返した候補のうち
    実際にマスキングしたいものを `[{"entity_type": ..., "text": ...}, ...]` の形式で指定する
    JSON配列文字列。指定した場合、この一覧に含まれる検出のみをマスキング対象とする。
  - どちらも省略した場合は、従来通り自動判定(列名推定 / NER検出)の結果をそのまま全てマスキングする。
- `GET /api/me` — ログイン中のユーザー情報(`{"email": ..., "name": ...}`。未ログイン時は `null`)
- `GET /login` / `GET /auth/login` / `GET /auth/callback` / `GET /logout` — Googleログイン関連

`AUTH_ENABLED=true`(既定)の場合、上記のうち `/login` `/auth/login` `/auth/callback` `/static/*` 以外は
すべて未ログイン時にアクセスできません(画面は `/login` へリダイレクト、APIは401を返します)。

## 利用ログ(誰が何を入力/アップロードしたか)

すべてのマスキングリクエストについて、`logs/audit.log` (JSON Lines形式) に
1リクエスト1行で記録します。Docker実行時は `docker-compose.yml` で
`./logs:/app/logs` をマウントしているため、ホスト側の `logs/audit.log` から
直接確認できます(標準出力にも出すため `docker compose logs` でも見えます)。

記録内容の例(テキスト直接入力):

```json
{"user": "taro.tanaka@pdpro.jp", "type": "text", "style": "tag", "entities_requested": ["PERSON", "EMAIL"], "detection_count": 2, "entities_detected": {"PERSON": 1, "EMAIL": 1}, "timestamp": "2026-08-21T02:00:00+00:00", "input_content": "田中太郎さんのメールは taro@example.com です。"}
```

先頭の `user` にはログインユーザーのメールアドレスが入ります(`AUTH_ENABLED=false` で
認証を無効化している場合は `"anonymous"` になります)。ファイルアップロードの場合は
`filename` / `extension` も記録され、`input_content` にはファイルから抽出した
元のテキスト(マスキング前)が入ります。

> **⚠️ 重要な注意点**
> このツールは個人情報を隠すためのものですが、既定 (`AUDIT_LOG_RAW_INPUT=true`) では
> `input_content` に**マスキング前の生データ(個人情報を含む可能性がある)**を
> そのまま記録します。つまりログファイル自体が新たな個人情報の保管場所になります。
> ログファイルへのアクセス権限・保管期間・削除ポリシーは運用者の責任で管理してください。
>
> 生データを記録したくない場合は、環境変数で無効化できます(メタデータ・検出件数のみ記録)。
>
> ```bash
> AUDIT_LOG_RAW_INPUT=false docker compose up --build
> ```

ログのローテーションは既定で1ファイル10MB・最大5世代分保持します
(`AUDIT_LOG_MAX_BYTES` / `AUDIT_LOG_BACKUP_COUNT` で変更可能)。

## 制限事項・今後の改善案

- CSV/Excel/JSONは現状セル(値)単位で逐次解析しているため、行数の多いファイルは処理に時間がかかります。
- マイナンバー・銀行口座番号は形式が単純な数字列であるため、文脈語による補助検出に依存しています。
  列名が「マイナンバー」「口座番号」等であれば列名ベースの強制マスキング(下記)が働きますが、
  列名が曖昧な場合は出力結果を必ず目視確認してください。
- CSV/Excelの列名ベースの強制マスキングは、各シート/ファイルの**先頭行をヘッダーとみなす**前提で
  動作します。ヘッダー行が無いデータや、`app/column_matcher.py` に登録されていない言い回しの
  列名(例: 独自の略称)は自動では対象にならないため、確認画面のプルダウンで手動で種別を
  選び直してください。
- 確認画面で調整した内容は再解析するまで(ファイルの再選択、またはマスキング対象エンティティの
  チェックボックス変更まで)保持されます。置換方式(タグ/マスク文字/削除)の変更は確認内容に
  影響しないため、再解析されません。
- JSONの `column_overrides` はキー名(トップレベルのフィールド名)単位で適用されます。異なる
  階層に同名キーが存在する場合、確認画面には最上位階層のキーのみが列挙されますが、選択した
  種別は同名の全てのキーに(階層を問わず)適用されます。
- `ja_core_news_lg` はモデルサイズが大きいため、初回起動時にダウンロード時間がかかります。
- Word/PowerPointは、1つの段落内で検出したテキストを先頭のrunに書き戻すため、
  段落内で文字ごとに異なる書式(一部だけ太字、色分けなど)が設定されている場合、
  マスキング後は先頭runの書式に統一されます(段落・表・スライドの構造自体は保持されます)。
- PDFは検出した文字列と同一のテキストをページ内で検索して黒塗りするため、
  ページ内で改行やハイフネーションによって分割された文字列は検出できない場合があります。
  また黒塗り部分に重ねるラベルは日本語CJKフォント(`japan-s`)で描画しています。
