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
  - 対応形式: テキスト(`.txt`) / CSV(`.csv`) / Excel(`.xlsx`) / Word(`.docx`) / PowerPoint(`.pptx`) / PDF(`.pdf`)
  - CSV/Excelは行・列(シート)構造を保持したまま各セルをマスキングします
  - Word/PowerPointは段落・表のテキストをマスキングします(書式は段落内の先頭runに統合されます)
  - PDFはテキストをその場で書き換えるとレイアウトが崩れるため、検出箇所を黒塗り(redaction)して
    その上にラベル/マスク文字を重ねる方式でマスキングします
  - テキスト/CSV は文字コードを UTF-8 (BOM有無) / Shift_JIS(cp932) / EUC-JP から自動判定します
- マスキング対象エンティティの選択(チェックボックス)
- 置換方式の選択
  - タグ置換: `[人物名]` のような日本語ラベルに置換(既定)
  - マスク文字: `*` に置換
  - 完全に削除: 検出箇所を削除

## セットアップ

### ローカル実行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 日本語モデルをダウンロード(精度重視: lg / 軽量: sm)
python -m spacy download ja_core_news_lg

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

ブラウザで `http://localhost:8000` を開くとWeb UIが表示されます。

環境変数 `SPACY_MODEL` で使用するモデルを切り替えられます(既定: `ja_core_news_lg`)。
動作確認だけしたい場合はダウンロードが軽い `ja_core_news_sm` を指定してください。

```bash
SPACY_MODEL=ja_core_news_sm uvicorn app.main:app --reload
```

### Docker

```bash
cd masking-tool
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
- `POST /api/mask/file` — `multipart/form-data` (`file`, `entities`(カンマ区切り, 省略可), `style`)

## 制限事項・今後の改善案

- CSV/Excelは現状セル単位で逐次解析しているため、行数の多いファイルは処理に時間がかかります。
- マイナンバー・銀行口座番号は形式が単純な数字列であるため、文脈語による補助検出に依存しています。
  厳密な運用が必要な場合は、事前に列名などで対象列を絞り込む運用と組み合わせることを推奨します。
- `ja_core_news_lg` はモデルサイズが大きいため、初回起動時にダウンロード時間がかかります。
- Word/PowerPointは、1つの段落内で検出したテキストを先頭のrunに書き戻すため、
  段落内で文字ごとに異なる書式(一部だけ太字、色分けなど)が設定されている場合、
  マスキング後は先頭runの書式に統一されます(段落・表・スライドの構造自体は保持されます)。
- PDFは検出した文字列と同一のテキストをページ内で検索して黒塗りするため、
  ページ内で改行やハイフネーションによって分割された文字列は検出できない場合があります。
  また黒塗り部分に重ねるラベルは日本語CJKフォント(`japan-s`)で描画しています。
