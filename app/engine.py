"""Presidio AnalyzerEngine / AnonymizerEngine の初期化と、
テキストマスキングのコアロジック。
"""

from functools import lru_cache

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from . import config
from .recognizers import get_all_recognizers

LANGUAGE = "ja"


# spaCyの日本語モデルは既定でNERラベルにORG/MONEY/QUANTITYを含むが、
# Presidioの既定設定はこれらを labels_to_ignore で捨て、DATE/TIMEを
# DATE_TIME に統合してしまう。マスキング対象として個別に扱いたいため、
# 独自のマッピング・無視リストを明示的に指定する。
SPACY_LABEL_MAPPING = {
    "PERSON": "PERSON",
    "PER": "PERSON",
    "GPE": "LOCATION",
    "LOC": "LOCATION",
    "ORG": "ORGANIZATION",
    "DATE": "DATE",
    "TIME": "TIME",
    "MONEY": "MONEY",
    "QUANTITY": "QUANTITY",
}
SPACY_LABELS_TO_IGNORE = [
    "O",
    "CARDINAL",
    "EVENT",
    "LANGUAGE",
    "LAW",
    "ORDINAL",
    "PERCENT",
    "PRODUCT",
    "WORK_OF_ART",
    "NORP",
    "FAC",
]


@lru_cache(maxsize=1)
def get_analyzer() -> AnalyzerEngine:
    nlp_configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": LANGUAGE, "model_name": config.SPACY_MODEL}],
        "ner_model_configuration": {
            "model_to_presidio_entity_mapping": SPACY_LABEL_MAPPING,
            "labels_to_ignore": SPACY_LABELS_TO_IGNORE,
        },
    }
    provider = NlpEngineProvider(nlp_configuration=nlp_configuration)
    nlp_engine = provider.create_engine()

    registry = RecognizerRegistry(supported_languages=[LANGUAGE])
    for recognizer in get_all_recognizers():
        registry.add_recognizer(recognizer)

    return AnalyzerEngine(
        nlp_engine=nlp_engine,
        registry=registry,
        supported_languages=[LANGUAGE],
    )


@lru_cache(maxsize=1)
def get_anonymizer() -> AnonymizerEngine:
    return AnonymizerEngine()


# 電話番号・マイナンバー・郵便番号などの書式が明確なパターンレコグナイザーは、
# spaCyが誤ってQUANTITY/DATE/MONEYなどの汎用ラベルを付けた場合でも
# 優先してマスキング対象として採用する。
PRIORITY_ENTITY_TYPES = {
    "PHONE_NUMBER",
    "EMAIL",
    "MY_NUMBER",
    "POSTAL_CODE",
    "CREDIT_CARD",
    "BANK_ACCOUNT",
    "PASSPORT",
}


def _resolve_overlaps(results):
    """重複するスパンのうち、書式ベースの検出を優先しつつ採用結果を決める。"""

    def priority_key(result):
        is_priority = result.entity_type in PRIORITY_ENTITY_TYPES
        return (not is_priority, -result.score, -(result.end - result.start))

    accepted = []
    occupied = []
    for result in sorted(results, key=priority_key):
        if any(result.start < end and result.end > start for start, end in occupied):
            continue
        accepted.append(result)
        occupied.append((result.start, result.end))

    return sorted(accepted, key=lambda r: r.start)


def _build_operators(style: str, entities: list) -> dict:
    if style == "mask":
        return {
            "DEFAULT": OperatorConfig(
                "mask",
                {"type": "mask", "masking_char": "*", "chars_to_mask": 9999, "from_end": False},
            )
        }
    if style == "redact":
        return {"DEFAULT": OperatorConfig("redact")}

    # style == "tag" (既定): [人物名] のような日本語ラベルに置換する。
    operators = {}
    for entity in entities:
        label = config.ENTITY_LABELS_JA.get(entity, entity)
        operators[entity] = OperatorConfig("replace", {"new_value": f"[{label}]"})
    operators["DEFAULT"] = OperatorConfig("replace", {"new_value": "[MASKED]"})
    return operators


def analyze_text(text: str, entities: list, score_threshold: float = None):
    if score_threshold is None:
        score_threshold = config.DEFAULT_SCORE_THRESHOLD
    analyzer = get_analyzer()
    return analyzer.analyze(
        text=text,
        entities=entities,
        language=LANGUAGE,
        score_threshold=score_threshold,
    )


def analyze_resolved(text: str, entities: list = None, score_threshold: float = None):
    """重複解決済みの検出結果一覧を返す。ファイル処理側でも共通利用する。"""
    if not entities:
        entities = config.ALL_ENTITY_CODES

    if not text:
        return []

    return _resolve_overlaps(analyze_text(text, entities, score_threshold))


def _anonymize(text: str, results: list, style: str, entities: list) -> tuple:
    anonymizer = get_anonymizer()
    operators = _build_operators(style, entities)
    anonymized = anonymizer.anonymize(text=text, analyzer_results=results, operators=operators)

    detections = [
        {
            "entity_type": r.entity_type,
            "entity_label": config.ENTITY_LABELS_JA.get(r.entity_type, r.entity_type),
            "start": r.start,
            "end": r.end,
            "score": round(r.score, 3),
            "text": text[r.start : r.end],
        }
        for r in sorted(results, key=lambda x: x.start)
    ]

    return anonymized.text, detections


def mask_text(text: str, entities: list = None, style: str = "tag", score_threshold: float = None):
    """テキストをマスキングし、(マスキング後テキスト, 検出結果一覧) を返す。"""
    if not entities:
        entities = config.ALL_ENTITY_CODES

    if not text:
        return "", []

    results = analyze_resolved(text, entities, score_threshold)
    return _anonymize(text, results, style, entities)


def mask_full_value(text: str, entity_type: str, style: str = "tag"):
    """セル・フィールドの値全体を、指定したエンティティ種別として一括マスキングする。

    表形式データ(CSV/Excel/JSON)で列名(例: 氏名・住所)からPIIの種別が
    分かっている場合に使う。単語単体のセル値はspaCyのNERでは文脈不足のため
    検出漏れしやすく、列名ベースで確実にマスキングするための経路。
    """
    if not text:
        return text, []

    result = RecognizerResult(entity_type=entity_type, start=0, end=len(text), score=1.0)
    return _anonymize(text, [result], style, [entity_type])
