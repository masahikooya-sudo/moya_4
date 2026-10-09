# マルチステージビルド: pip/setuptools/wheel等のビルド時専用ツールを
# 最終イメージに残さないため、依存関係のインストールは builder ステージで
# 行い、インストール結果(venv)だけを最終イメージにコピーする。
# (Trivyのイメージスキャンで、ビルド時ツールに起因する脆弱性
# (pip/wheel/setuptools付属のjaraco.context等)が実行時攻撃面として
# 検出されたための対応)
FROM python:3.11-slim AS builder

ARG SPACY_MODEL=ja_core_news_lg

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download ${SPACY_MODEL} \
    # アプリの実行(uvicornでのHTTPサーバー起動)にはpip/setuptools/wheelは
    # 不要なため、最終イメージに持ち込まないようここで削除する。
    && pip uninstall -y pip setuptools wheel


FROM python:3.11-slim

WORKDIR /app

# python:3.11-slim にはタイムゾーンデータ(tzdata)が含まれていないため、
# ログのローテーション(audit_log.py)を日本時間の日付境界で行うために導入する。
# あわせて、ビルド時点でDebianが修正パッチを公開済みのパッケージを
# 取り込むため apt-get upgrade も行う(Trivyのイメージスキャンで検出された
# OSパッケージの既知脆弱性のうち、パッチが存在するものに対応するため)。
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends tzdata \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY app ./app
COPY static ./static

ARG SPACY_MODEL=ja_core_news_lg
ENV SPACY_MODEL=${SPACY_MODEL}
ENV PYTHONUNBUFFERED=1
# サーバーのローカル時刻を日本時間にする。監査ログのローテーション
# (TimedRotatingFileHandler)はこのローカル時刻の午前0時を基準に行われる。
ENV TZ=Asia/Tokyo

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
