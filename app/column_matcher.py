"""表形式データ(CSV/Excel/JSON)の列名・キー名からPIIのエンティティ種別を推定する。

単語単体のセル値(例: 姓だけの「田中」、ふりがなの「たなか」)はspaCyのNERでは
文脈不足のため検出漏れしやすい。列名(ヘッダー)がPIIの種別を明示している場合は、
NERの結果によらずセル値全体をそのエンティティ種別としてマスキングする。
"""

import re

# 値は完全一致・部分一致どちらでも判定に使うキーワード。
# 判定は上から順に調べ、最初に一致したエンティティ種別を採用する。
COLUMN_KEYWORDS = [
    ("PERSON", [
        "氏名", "お名前", "名前", "フルネーム", "姓名", "姓", "名字", "苗字",
        "ローマ字氏名", "担当者名", "担当者", "顧客名", "契約者名", "契約者",
        "申込者名", "申込者", "従業員氏名", "社員氏名", "氏名（漢字）", "氏名(漢字)",
        "name", "full name", "last name", "first name", "surname", "family name",
        "given name",
    ]),
    ("FURIGANA", [
        "フリガナ", "ふりがな", "カナ", "かな", "読み仮名", "よみがな",
        "カナ氏名", "フリガナ氏名", "せい めい", "furigana",
    ]),
    ("LOCATION", [
        "住所", "ご住所", "現住所", "自宅住所", "勤務先住所", "所在地", "居住地",
        "都道府県", "市区町村", "番地", "address",
    ]),
    ("ORGANIZATION", [
        "会社名", "企業名", "勤務先", "所属", "部署名", "部署", "組織名",
        "company", "organization",
    ]),
    ("EMAIL", [
        "メールアドレス", "メール", "Eメール", "eメール", "email", "mail",
    ]),
    ("PHONE_NUMBER", [
        "電話番号", "電話", "TEL", "携帯電話", "携帯", "FAX", "phone",
    ]),
    ("POSTAL_CODE", [
        "郵便番号", "〒", "zip", "postal code",
    ]),
    ("MY_NUMBER", [
        "マイナンバー", "個人番号",
    ]),
    ("BANK_ACCOUNT", [
        "口座番号", "銀行口座",
    ]),
    ("CREDIT_CARD", [
        "クレジットカード番号", "カード番号",
    ]),
    ("PASSPORT", [
        "パスポート番号", "旅券番号",
    ]),
    ("DATE", [
        "生年月日", "誕生日", "date of birth",
    ]),
]


def _normalize(header: str) -> str:
    return re.sub(r"\s+", "", header or "").lower()


def match_exact(header: str, allowed_entities: set) -> str | None:
    """列名(ヘッダー文字列)がキーワードと完全一致する場合のみエンティティ種別を返す。

    部分一致は行わない。1行のテキストが単独で完結したラベルと言えるかどうかを
    判定したい場合(file_processing.py のラベル直後の値の強制検出等)に使う。
    """
    normalized = _normalize(header)
    if not normalized:
        return None

    for entity_type, keywords in COLUMN_KEYWORDS:
        if entity_type not in allowed_entities:
            continue
        if any(_normalize(keyword) == normalized for keyword in keywords):
            return entity_type

    return None


def match_entity_type(header: str, allowed_entities: set) -> str | None:
    """列名(ヘッダー文字列)からエンティティ種別を推定する。

    allowed_entities に含まれる種別のみを候補とする(ユーザーが選択していない
    エンティティ種別の列は強制マスキングの対象にしない)。一致しなければ None。

    まず完全一致を優先して調べ(例:「会社名」がPERSON側の部分一致に誤って
    引っかからないようにするため)、完全一致が無ければ部分一致で判定する。
    """
    exact = match_exact(header, allowed_entities)
    if exact is not None:
        return exact

    normalized = _normalize(header)
    if not normalized:
        return None

    candidates = [
        (entity_type, keywords)
        for entity_type, keywords in COLUMN_KEYWORDS
        if entity_type in allowed_entities
    ]

    for entity_type, keywords in candidates:
        if any(_normalize(keyword) in normalized for keyword in keywords):
            return entity_type

    return None
