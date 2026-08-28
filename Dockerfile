FROM python:3.11-slim

WORKDIR /app

ARG SPACY_MODEL=ja_core_news_lg

# python:3.11-slim にはタイムゾーンデータ(tzdata)が含まれていないため、
# ログのローテーション(audit_log.py)を日本時間の日付境界で行うために導入する。
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download ${SPACY_MODEL}

COPY app ./app
COPY static ./static

ENV SPACY_MODEL=${SPACY_MODEL}
ENV PYTHONUNBUFFERED=1
# サーバーのローカル時刻を日本時間にする。監査ログのローテーション
# (TimedRotatingFileHandler)はこのローカル時刻の午前0時を基準に行われる。
ENV TZ=Asia/Tokyo

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
