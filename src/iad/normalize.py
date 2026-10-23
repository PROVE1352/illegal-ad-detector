"""난독화 정규화: 전각/호환문자, 자모 분리, 유사문자, 공백·특수문자·이모지 삽입."""
from __future__ import annotations

import re
import unicodedata

CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONG = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ",
        "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]
_CHO_IDX = {c: i for i, c in enumerate(CHO)}
_JUNG_IDX = {c: i for i, c in enumerate(JUNG)}
_JONG_IDX = {c: i for i, c in enumerate(JONG) if c}

# 유사문자(homoglyph) → 기본 라틴/숫자
HOMOGLYPHS = {
    "0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "9": "g", "2": "z", "@": "a", "$": "s", "|": "l",
    # 키릴
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y", "к": "k", "і": "i", "ѕ": "s", "т": "t",
    "в": "b", "н": "h", "м": "m", "ѵ": "v", "ј": "j", "ԁ": "d", "ԛ": "q", "ԝ": "w", "ѡ": "w", "ԍ": "g", "ғ": "f",
    "ё": "e", "ї": "i", "ӏ": "l", "һ": "h", "ԛ": "q", "ԝ": "w",
    # 그리스
    "ο": "o", "α": "a", "ε": "e", "ι": "i", "ν": "v", "τ": "t", "β": "b", "κ": "k", "ρ": "p", "υ": "u", "χ": "x",
    "μ": "u", "η": "n", "ω": "w", "γ": "y", "ζ": "z",
    # 라틴 확장
    "ı": "i", "ł": "l", "ø": "o", "ß": "b", "ſ": "s", "đ": "d", "ƅ": "b", "ɡ": "g", "ɑ": "a", "ɩ": "i", "ɴ": "n",
}
# 숫자 1/|/! 은 l 과 i 둘 다로 읽힐 수 있어(cas1no, s1ot) 대체 변형을 하나 더 만든다
_ALT_I = {"1": "i", "|": "i", "!": "i", "l": "l"}

_ZERO_WIDTH = re.compile("[​‌‍⁠﻿­͏ᅟᅠㅤ]")
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF⭐⭕‼⁉〰〽㊗㊙️]"
)
_NOISE = re.compile(r"[\s\.\,\-\_\*\+\=\/\\\~\^\'\"\`\(\)\[\]\{\}<>:;?!#%&·•※★☆♡♥▶◀■□○●◎◇◆△▲▽▼→←↑↓ㆍ…‥『』「」【】〔〕《》〈〉]+")


def compose_jamo(text: str) -> str:
    """분리된 호환 자모(ㅌㅗㅌㅗ)를 음절(토토)로 합성한다."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in _CHO_IDX and i + 1 < n and text[i + 1] in _JUNG_IDX:
            cho = _CHO_IDX[c]
            jung = _JUNG_IDX[text[i + 1]]
            jong = 0
            j = i + 2
            if j < n and text[j] in _JONG_IDX and not (j + 1 < n and text[j + 1] in _JUNG_IDX):
                jong = _JONG_IDX[text[j]]
                j += 1
            out.append(chr(0xAC00 + (cho * 21 + jung) * 28 + jong))
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def basic(text: str) -> str:
    """NFKC + 제로폭 제거 + 소문자. 공백은 유지(문맥 매칭용)."""
    t = unicodedata.normalize("NFKC", text or "")
    t = _ZERO_WIDTH.sub("", t)
    return t.lower()


def _strip_noise(t: str) -> str:
    t = _ZERO_WIDTH.sub("", t)
    t = _EMOJI.sub("", t)
    return _NOISE.sub("", t)


def level_plain(text: str) -> str:
    """난독화 해제 없음: 소문자화 + 공백·특수문자·이모지·제로폭 제거만."""
    return _strip_noise((text or "").lower())


def level_jamo(text: str) -> str:
    """plain + 분리 자모 합성(JAMO 판정용). NFKC 전에 합성해야 호환 자모가 보존된다."""
    return compose_jamo(level_plain(text))


_DIGIT_HOMO = {"0", "1", "2", "3", "4", "5", "7", "8", "9"}
_ALNUM_RUN = re.compile(r"[0-9a-z@$|!\u0400-\u04ff\u0370-\u03ffıłøßſđƅɡɑɩɴ]+")


def _map_homoglyphs(t: str, alt_i: bool = False) -> str:
    """유사문자 치환. 숫자→문자 치환은 (치환 후) 라틴 문자가 섞인 토큰 안에서만(전화번호 '7070' 이 'toto' 가 되는 것 방지).
    alt_i=True 면 1/|/! 을 l 대신 i 로 읽는다."""
    def repl(m: re.Match) -> str:
        tok = m.group(0)
        letters = "".join(HOMOGLYPHS.get(c, c) if c not in _DIGIT_HOMO else c for c in tok)
        if not any("a" <= c <= "z" for c in letters):
            return letters
        out = []
        for c in tok:
            if alt_i and c in _ALT_I:
                out.append(_ALT_I[c])
            else:
                out.append(HOMOGLYPHS.get(c, c))
        return "".join(out)
    return _ALNUM_RUN.sub(repl, t)


def level_homoglyph(text: str, alt_i: bool = False) -> str:
    """plain + NFKC(전각·호환문자) + 유사문자 치환(HOMOGLYPH 판정용)."""
    t = _nfkc_keep_jamo(level_plain(text))
    t = _strip_noise(t.lower())
    return _map_homoglyphs(t, alt_i)


def _nfkc_keep_jamo(t: str) -> str:
    """NFKC 를 적용하되 호환 자모(ㄱ~ㅣ)는 그대로 둔다(NFKC 가 자모를 음절로 합성해 JAMO 판정과 섞이는 것 방지)."""
    out = []
    buf = []
    for ch in t:
        if "\u3131" <= ch <= "\u3163":
            if buf:
                out.append(unicodedata.normalize("NFKC", "".join(buf)))
                buf = []
            out.append(ch)
        else:
            buf.append(ch)
    if buf:
        out.append(unicodedata.normalize("NFKC", "".join(buf)))
    return "".join(out)


def has_jamo(text: str) -> bool:
    return any("\u3131" <= ch <= "\u3163" or "\u1100" <= ch <= "\u11ff" for ch in text or "")


def aggressive(text: str, alt_i: bool = False) -> str:
    """키워드 탐지용 최대 정규화: 자모 합성 → NFKC → 유사문자 치환."""
    t = unicodedata.normalize("NFKC", level_jamo(text))
    t = _strip_noise(t.lower())
    return _map_homoglyphs(t, alt_i)


def collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", basic(text)).strip()


_FULLWIDTH = re.compile("[\uff10-\uff19\uff21-\uff3a\uff41-\uff5a]")
_CYRILLIC_GREEK = re.compile("[\u0400-\u04ff\u0370-\u03ff]")
_LATIN = re.compile("[a-zA-Z]")
_HANGUL = re.compile("[\uac00-\ud7a3]")


_WORD = re.compile(r"[\w\u0400-\u04ff\u0370-\u03ff\uac00-\ud7a3@$|!]+")
_CONSONANT_RUN = re.compile("[\u3131-\u314e]{2,}")


def has_homoglyph_chars(text: str) -> bool:
    """전각 영숫자가 있거나, 한 단어 안에 키릴·그리스 문자가 라틴/한글/숫자와 섞여 있으면(스크립트 혼용) True.
    문장 전체가 키릴인 정상 러시아어 텍스트는 해당하지 않는다."""
    t = text or ""
    if _FULLWIDTH.search(t):
        return True
    for tok in _WORD.findall(t):
        if _CYRILLIC_GREEK.search(tok) and (_LATIN.search(tok) or _HANGUL.search(tok) or re.search(r"\d", tok)):
            return True
    return False


def chosung_of(word: str) -> str | None:
    """한글 음절 단어 → 초성 문자열(카지노→ㅋㅈㄴ). 음절이 아닌 글자가 있으면 None."""
    out = []
    for ch in word:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            out.append(CHO[(code - 0xAC00) // 588])
        else:
            return None
    return "".join(out)


def consonant_runs(text: str) -> list[str]:
    """호환 자음만 2자 이상 이어진 덩어리(ㅋㅈㄴ, ㅌㅌ)."""
    return _CONSONANT_RUN.findall(text or "")


def has_composable_jamo(text: str) -> bool:
    """합성 가능한 분리 자모(ㅌㅗ 처럼 자음+모음)가 있으면 True. 'ㅋㅋ' 같은 단독 자음은 제외."""
    t = text or ""
    return compose_jamo(t) != t
