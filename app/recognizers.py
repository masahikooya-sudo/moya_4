"""日本語PII検出用のPresidioカスタムレコグナイザー定義。

- spaCyの日本語モデルのNER結果を PERSON / LOCATION / ORGANIZATION /
  DATE / TIME / MONEY / QUANTITY にマッピングするレコグナイザー
- 正規表現ベースの日本特有の識別子（電話番号・マイナンバー・郵便番号・
  銀行口座番号・パスポート番号・メールアドレス）を検出するレコグナイザー
"""

import re

from presidio_analyzer import EntityRecognizer, Pattern, PatternRecognizer, RecognizerResult


class JapaneseSpacyRecognizer(EntityRecognizer):
    """spaCyのNERラベルをマスキング対象のエンティティ種別へマッピングする。"""

    # engine.py の NerModelConfiguration により、この時点で ent.label_ は
    # 既に最終的なエンティティ名(LOCATION/ORGANIZATION等)へ変換済みだが、
    # 変換されずspaCy由来の生ラベル(GPE/ORG/PER等)のままになるケースの
    # 保険として、両方のラベル表記をマッピングしておく。
    LABEL_TO_ENTITY = {
        "PERSON": "PERSON",
        "PER": "PERSON",
        "ORG": "ORGANIZATION",
        "ORGANIZATION": "ORGANIZATION",
        "GPE": "LOCATION",
        "LOC": "LOCATION",
        "LOCATION": "LOCATION",
        "DATE": "DATE",
        "TIME": "TIME",
        "MONEY": "MONEY",
        "QUANTITY": "QUANTITY",
    }

    DEFAULT_SCORE = 0.85

    def __init__(self, supported_language: str = "ja"):
        super().__init__(
            supported_entities=sorted(set(self.LABEL_TO_ENTITY.values())),
            supported_language=supported_language,
            name="JapaneseSpacyRecognizer",
        )

    def load(self) -> None:
        # モデルのロード自体はPresidioのNlpEngineが行うため何もしない。
        return None

    def analyze(self, text, entities, nlp_artifacts=None):
        results = []
        if nlp_artifacts is None:
            return results

        for ent in nlp_artifacts.entities:
            entity_type = self.LABEL_TO_ENTITY.get(ent.label_)
            if entity_type is None or entity_type not in entities:
                continue
            results.append(
                RecognizerResult(
                    entity_type=entity_type,
                    start=ent.start_char,
                    end=ent.end_char,
                    score=self.DEFAULT_SCORE,
                )
            )
        return results


def build_email_recognizer() -> PatternRecognizer:
    # PDFから抽出したテキストでは、フォームのフィールド幅等の都合で
    # メールアドレスの途中(@の前後・ドットの前後)に改行や空白が挟まる
    # ことがある。厳密に空白なしを要求すると検出漏れになるため、
    # 区切り記号の前後に少量の空白類(改行含む)を許容する。
    pattern = Pattern(
        name="email_pattern",
        regex=(
            r"[a-zA-Z0-9._%+\-]+\s{0,2}@\s{0,2}[a-zA-Z0-9\-]+"
            r"(?:\s{0,2}\.\s{0,2}[a-zA-Z0-9\-]+)*\s{0,2}\.\s{0,2}[a-zA-Z]{2,}"
        ),
        score=0.9,
    )
    return PatternRecognizer(
        supported_entity="EMAIL",
        supported_language="ja",
        patterns=[pattern],
        context=["メール", "メールアドレス", "連絡先", "email", "mail"],
        name="JapaneseEmailRecognizer",
    )


def build_furigana_recognizer() -> PatternRecognizer:
    """氏名のふりがな(カタカナ表記)を検出する。

    「ハシモト タロウ」のように、カタカナの単語が空白区切りで2つ以上
    連続する文字列をふりがなとみなす。単発のカタカナ語(外来語等)との
    誤検出を減らすため、2語以上の連続を要求し、文脈語(フリガナ等)が
    近くにあればスコアを加点する。
    """
    pattern = Pattern(
        name="furigana_pattern",
        regex=r"(?<![ァ-ヶー])[ァ-ヶー]{2,10}[ 　][ァ-ヶー]{2,10}(?![ァ-ヶー])",
        score=0.55,
    )
    return PatternRecognizer(
        supported_entity="FURIGANA",
        supported_language="ja",
        patterns=[pattern],
        context=["ふりがな", "フリガナ", "よみがな", "読み仮名", "カナ", "furigana"],
        name="JapaneseFuriganaRecognizer",
    )


def build_phone_recognizer() -> PatternRecognizer:
    patterns = [
        # 携帯電話 (070/080/090) やフリーダイヤル(0120/0800)、固定電話(市外局番あり)
        Pattern(
            name="jp_phone_hyphen",
            regex=r"(?<!\d)0\d{1,4}-\d{1,4}-\d{3,4}(?!\d)",
            score=0.75,
        ),
        # ハイフンなしの11桁携帯番号
        Pattern(
            name="jp_phone_mobile_plain",
            regex=r"(?<!\d)0[789]0\d{8}(?!\d)",
            score=0.6,
        ),
        # 国際表記 +81
        Pattern(
            name="jp_phone_intl",
            regex=r"\+81[-\s]?\d{1,4}[-\s]?\d{1,4}[-\s]?\d{3,4}(?!\d)",
            score=0.85,
        ),
    ]
    return PatternRecognizer(
        supported_entity="PHONE_NUMBER",
        supported_language="ja",
        patterns=patterns,
        context=["電話", "TEL", "Tel", "携帯", "連絡先", "FAX"],
        name="JapanesePhoneRecognizer",
    )


def build_my_number_recognizer() -> PatternRecognizer:
    # マイナンバー(個人番号)は12桁。3桁ごとにハイフンまたはスペース区切りで
    # 記載されることが多い。文脈語での加点を前提に基本スコアは中程度に設定。
    pattern = Pattern(
        name="my_number_pattern",
        regex=r"(?<!\d)\d{4}[-\s]?\d{4}[-\s]?\d{4}(?!\d)",
        score=0.3,
    )
    return PatternRecognizer(
        supported_entity="MY_NUMBER",
        supported_language="ja",
        patterns=[pattern],
        context=["マイナンバー", "個人番号", "個人番号カード", "My Number", "MyNumber"],
        name="JapaneseMyNumberRecognizer",
    )


def build_postal_code_recognizer() -> PatternRecognizer:
    # 末尾に「-数字」が続く場合は電話番号などの一部である可能性が高いため除外する。
    pattern = Pattern(
        name="postal_code_pattern",
        regex=r"(?<!\d)〒?\s?\d{3}-\d{4}(?!-?\d)",
        score=0.7,
    )
    return PatternRecognizer(
        supported_entity="POSTAL_CODE",
        supported_language="ja",
        patterns=[pattern],
        context=["郵便番号", "〒", "住所"],
        name="JapanesePostalCodeRecognizer",
    )


def build_bank_account_recognizer() -> PatternRecognizer:
    # 日本の銀行口座番号は一般的に7桁（普通・当座）。単独の数字列は
    # 誤検出しやすいため基本スコアを低めにし、文脈語で加点する。
    pattern = Pattern(
        name="bank_account_pattern",
        regex=r"(?<!\d)\d{7,8}(?!\d)",
        score=0.25,
    )
    return PatternRecognizer(
        supported_entity="BANK_ACCOUNT",
        supported_language="ja",
        patterns=[pattern],
        context=["口座番号", "口座", "普通", "当座", "銀行", "支店"],
        name="JapaneseBankAccountRecognizer",
    )


def build_passport_recognizer() -> PatternRecognizer:
    # 日本国旅券番号: アルファベット2文字 + 数字7桁 (例: TZ1234567)
    pattern = Pattern(
        name="passport_pattern",
        regex=r"(?<![A-Za-z0-9])[A-Z]{2}\d{7}(?![A-Za-z0-9])",
        score=0.4,
    )
    return PatternRecognizer(
        supported_entity="PASSPORT",
        supported_language="ja",
        patterns=[pattern],
        context=["パスポート", "旅券", "passport"],
        name="JapanesePassportRecognizer",
    )


class JapaneseCreditCardRecognizer(PatternRecognizer):
    """クレジットカード番号レコグナイザー。

    Presidio標準のCreditCardRecognizerは正規表現に \\b (単語境界) を使っており、
    日本語の文字(漢字・ひらがな等)は正規表現上「単語文字」として扱われるため、
    「カード番号は4111...」のように直前が日本語の文字だと境界が成立せず検出漏れが
    発生する。そのため桁数ベースの先読み・後読みで境界を判定する独自実装とする。
    """

    PATTERNS = [
        Pattern(
            name="credit_card_pattern",
            regex=(
                r"(?<!\d)(?:4\d{3}|5[1-5]\d{2}|3[47]\d{2}|6(?:011|5\d{2}))"
                r"[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{1,4}(?!\d)"
            ),
            score=0.3,
        )
    ]

    def __init__(self):
        super().__init__(
            supported_entity="CREDIT_CARD",
            supported_language="ja",
            patterns=self.PATTERNS,
            context=["カード", "クレジット", "credit", "card"],
            name="JapaneseCreditCardRecognizer",
        )

    def validate_result(self, pattern_text: str):
        digits = [int(c) for c in re.sub(r"\D", "", pattern_text)]
        checksum = 0
        for i, digit in enumerate(reversed(digits)):
            if i % 2 == 1:
                digit *= 2
                if digit > 9:
                    digit -= 9
            checksum += digit
        return checksum % 10 == 0


def get_all_recognizers():
    return [
        JapaneseSpacyRecognizer(),
        JapaneseCreditCardRecognizer(),
        build_email_recognizer(),
        build_furigana_recognizer(),
        build_phone_recognizer(),
        build_my_number_recognizer(),
        build_postal_code_recognizer(),
        build_bank_account_recognizer(),
        build_passport_recognizer(),
    ]
