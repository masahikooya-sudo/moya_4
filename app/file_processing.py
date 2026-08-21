"""テキストファイル・CSVファイルのアップロードを受け取り、
マスキング済みの内容を生成するロジック。
"""

import csv
import io

from .engine import mask_text

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
