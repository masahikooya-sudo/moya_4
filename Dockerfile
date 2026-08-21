FROM python:3.11-slim

WORKDIR /app

ARG SPACY_MODEL=ja_core_news_lg

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download ${SPACY_MODEL}

COPY app ./app
COPY static ./static

ENV SPACY_MODEL=${SPACY_MODEL}
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
