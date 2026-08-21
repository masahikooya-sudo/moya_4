"""テキストファイル・CSVファイル・Office文書・PDFのアップロードを受け取り、
マスキング済みの内容を生成するロジック。
"""

import csv
import io
import re

import pymupdf as fitz
import openpyxl
from docx import Document
from pptx import Presentation

from . import config
from .engine import analyze_resolved, mask_text

# 日本のビジネス文書で使われやすい文字コードの候補（優先順）。
CANDIDATE_ENCODINGS = ["utf-8-sig", "utf-8", "cp932", "shift_jis", "euc_jp"]


def decode_bytes(raw: bytes) -> tuple[str, str]:
    """バイト列を可能な文字コード候補で順にデコードする。

    戻り値: (デコード後文字列, 使用した文字コード)
    """
    last_error = None
    for encoding in CANDIDATE_ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except (UnicodeDecodeError, LookupError) as exc:
            last_error = exc
    raise ValueError(f"ファイルの文字コードを判定できませんでした: {last_error}")


def mask_plain_text_file(raw: bytes, entities: list, style: str):
    """.txt ファイルをマスキングする。"""
    text, _encoding = decode_bytes(raw)
    masked_text, detections = mask_text(text, entities=entities, style=style)
    return masked_text.encode("utf-8-sig"), detections


def mask_csv_file(raw: bytes, entities: list, style: str):
    """.csv ファイルの各セルをマスキングする。行・列構造は保持する。"""
    text, _encoding = decode_bytes(raw)

    # 区切り文字を簡易的に自動判定(カンマ / タブ)。
    sample = text[:2048]
    dialect = csv.excel
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
    except csv.Error:
        pass

    reader = csv.reader(io.StringIO(text), dialect)
    rows = list(reader)

    all_detections = []
    masked_rows = []
    for row_index, row in enumerate(rows):
        masked_row = []
        for col_index, cell in enumerate(row):
            if not cell:
                masked_row.append(cell)
                continue
            masked_cell, detections = mask_text(cell, entities=entities, style=style)
            masked_row.append(masked_cell)
            for detection in detections:
                detection["row"] = row_index
                detection["column"] = col_index
                all_detections.append(detection)
        masked_rows.append(masked_row)

    output = io.StringIO()
    writer = csv.writer(output, dialect=dialect)
    writer.writerows(masked_rows)

    return output.getvalue().encode("utf-8-sig"), all_detections


def mask_xlsx_file(raw: bytes, entities: list, style: str):
    """.xlsx ファイルの各セルをマスキングする。シート・書式は保持する。"""
    workbook = openpyxl.load_workbook(io.BytesIO(raw))
    all_detections = []

    for sheet in workbook.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if not isinstance(cell.value, str) or not cell.value:
                    continue
                masked, detections = mask_text(cell.value, entities=entities, style=style)
                if masked != cell.value:
                    cell.value = masked
                for detection in detections:
                    detection["sheet"] = sheet.title
                    detection["row"] = cell.row
                    detection["column"] = cell.column
                all_detections.extend(detections)

    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue(), all_detections


def _mask_paragraph_runs(paragraph, entities: list, style: str):
    """段落内のテキストをまとめてマスキングし、先頭の run に書き戻す。

    run単位の書式(太字など)は先頭run以外は失われるが、段落の構造・順序は保持する。
    """
    text = paragraph.text
    if not text.strip() or not paragraph.runs:
        return []

    masked, detections = mask_text(text, entities=entities, style=style)
    if masked != text:
        paragraph.runs[0].text = masked
        for run in paragraph.runs[1:]:
            run.text = ""
    return detections


def mask_docx_file(raw: bytes, entities: list, style: str):
    """.docx ファイルの本文・表・ヘッダー/フッターをマスキングする。"""
    document = Document(io.BytesIO(raw))
    all_detections = []

    def process_paragraphs(paragraphs):
        for paragraph in paragraphs:
            all_detections.extend(_mask_paragraph_runs(paragraph, entities, style))

    def process_tables(tables):
        for table in tables:
            for row in table.rows:
                for cell in row.cells:
                    process_paragraphs(cell.paragraphs)
                    process_tables(cell.tables)

    process_paragraphs(document.paragraphs)
    process_tables(document.tables)
    for section in document.sections:
        process_paragraphs(section.header.paragraphs)
        process_paragraphs(section.footer.paragraphs)

    output = io.BytesIO()
    document.save(output)
    return output.getvalue(), all_detections


def mask_pptx_file(raw: bytes, entities: list, style: str):
    """.pptx ファイルのテキストボックス・表をマスキングする。"""
    presentation = Presentation(io.BytesIO(raw))
    all_detections = []

    def process_text_frame(text_frame):
        for paragraph in text_frame.paragraphs:
            all_detections.extend(_mask_paragraph_runs(paragraph, entities, style))

    for slide_index, slide in enumerate(presentation.slides):
        for shape in slide.shapes:
            if shape.has_text_frame:
                process_text_frame(shape.text_frame)
            if shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        process_text_frame(cell.text_frame)

    output = io.BytesIO()
    presentation.save(output)
    return output.getvalue(), all_detections


def mask_pdf_file(raw: bytes, entities: list, style: str):
    """.pdf ファイルをマスキングする。

    PDFはテキストをその場で書き換えると元のレイアウトが崩れるため、検出箇所を
    黒塗り(redaction)することでマスキングする。style に応じて黒塗り部分に
    ラベルやマスク文字を重ねて表示する。
    """
    document = fitz.open(stream=raw, filetype="pdf")
    all_detections = []

    for page in document:
        page_text = page.get_text("text")
        if not page_text.strip():
            continue

        results = analyze_resolved(page_text, entities)
        seen = set()
        for result in results:
            matched_text = page_text[result.start : result.end].strip()
            search_query = re.sub(r"\s+", " ", matched_text).strip()
            if not search_query or search_query in seen:
                continue
            seen.add(search_query)

            rects = page.search_for(search_query)
            if not rects:
                continue

            label = config.ENTITY_LABELS_JA.get(result.entity_type, result.entity_type)
            for rect in rects:
                if style == "tag":
                    page.add_redact_annot(
                        rect, text=f"[{label}]", fontname="japan-s",
                        fill=(0, 0, 0), text_color=(1, 1, 1),
                    )
                elif style == "mask":
                    page.add_redact_annot(
                        rect, text="*" * min(len(search_query), 12), fontname="japan-s",
                        fill=(0, 0, 0), text_color=(1, 1, 1),
                    )
                else:  # redact
                    page.add_redact_annot(rect, fill=(0, 0, 0))

            all_detections.append(
                {
                    "entity_type": result.entity_type,
                    "entity_label": label,
                    "score": round(result.score, 3),
                    "text": matched_text,
                    "page": page.number + 1,
                }
            )

        page.apply_redactions()

    output = io.BytesIO()
    document.save(output)
    document.close()
    return output.getvalue(), all_detections
