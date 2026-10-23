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
# 유니코드 confusables 보강(소문자화 뒤 적용): 체로키·아르메니아·기호. 한 단어 안 스크립트 혼용 토큰의 골격 복원에 쓴다.
CONFUSABLES_EXTRA = {
    "ꭺ": "a", "ꮯ": "c", "ꭰ": "d", "ꭼ": "e", "ꮐ": "g", "ꮋ": "h", "ꭵ": "i", "ꭻ": "j", "ꮶ": "k", "ꮮ": "l", "ꮇ": "m", "ꮑ": "n",
    "ꮎ": "o", "ꮲ": "p", "ꮢ": "r", "ꮪ": "s", "ꭲ": "t", "ꮩ": "v", "ꮃ": "w", "ꭹ": "y", "ꮓ": "z",
    "օ": "o", "ս": "u", "ո": "n", "ց": "g", "ա": "a", "ե": "e", "ѕ": "s", "є": "e", "ԁ": "d", "ԛ": "q", "ԝ": "w", "ӡ": "z",
    "€": "e", "£": "l", "¢": "c", "§": "s", "†": "t", "+": "t", "¥": "y", "¡": "i", "ƒ": "f", "ɒ": "a", "ʏ": "y", "ᴀ": "a",
    "ᴄ": "c", "ᴇ": "e", "ᴏ": "o", "ᴘ": "p", "ᴛ": "t", "ᴜ": "u", "ᴠ": "v", "ᴡ": "w", "ᴢ": "z", "ʙ": "b", "ɢ": "g", "ʜ": "h",
    "ɪ": "i", "ᴊ": "j", "ᴋ": "k", "ʟ": "l", "ᴍ": "m", "ʀ": "r", "ꜱ": "s",
}

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


_HALFWIDTH_JAMO = re.compile("[\uffa1-\uffdc]")
_CONJOINING = re.compile("[\u1100-\u11ff\ua960-\ua97f\ud7b0-\ud7ff]")


def level_jamo(text: str) -> str:
    """plain + 분리 자모 합성(JAMO 판정용). 호환 자모(ㅌㅗㅌㅗ)는 직접 합성, 첫가끝 조합형(U+1100~, NFD 분해 한글)은 NFC 로,
    반각 자모(U+FFA1~)는 호환 자모로 바꾼 뒤 합성한다. NFKC 전에 합성해야 호환 자모가 보존된다."""
    t = level_plain(text)
    if _HALFWIDTH_JAMO.search(t):
        t = _HALFWIDTH_JAMO.sub(lambda m: unicodedata.normalize("NFKC", m.group(0)), t)
    if _CONJOINING.search(t):
        t = unicodedata.normalize("NFC", t)
    return compose_jamo(t)


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


# 한글 음절 안 영문·숫자 시각 치환(ㅋr지노, ㅂrㅋrㄹr, 스ㅍ0츠토토, 토Eㅗ): 앞뒤 글자가 한글(음절·호환 자모)일 때만 자모로 바꾼다
KOREAN_LEET = {"r": "ㅏ", "E": "ㅌ", "O": "ㅇ", "o": "ㅇ", "0": "ㅇ", "I": "ㅣ", "l": "ㅣ", "|": "ㅣ", "1": "ㅣ", "L": "ㄴ", "7": "ㄱ",
               "H": "ㅐ", "T": "ㅜ", "c": "ㄷ", "C": "ㄷ", "2": "ㄹ"}
_HANGUL_CH = re.compile("[\uac00-\ud7a3\u3131-\u3163]")
_CONSONANT_CH = re.compile("[\u3131-\u314e]")
_LEET_CAND = re.compile("[rEOo0Il|1L7HTcC2]")


def korean_leet(t: str) -> str:
    """대소문자가 남아 있는 문자열에서 한글 사이에 낀 라틴/숫자 유사자를 자모로 치환한다(영문 약어·전화번호는 앞뒤가 한글이 아니라 그대로).
    O/o/0 은 바로 앞이 자음 자모면 모음 ㅗ(스ㅍ0츠→스포츠), 아니면 ㅇ(놀0ㅣ터→놀이터)."""
    if not _LEET_CAND.search(t) or not _HANGUL_CH.search(t):
        return t
    out = list(t)
    n = len(t)
    for i, ch in enumerate(t):
        if ch in KOREAN_LEET:
            prev_h = i > 0 and bool(_HANGUL_CH.match(t[i - 1]))
            next_h = i + 1 < n and bool(_HANGUL_CH.match(t[i + 1]))
            if prev_h or next_h:
                rep = KOREAN_LEET[ch]
                if ch in "Oo0" and i > 0 and _CONSONANT_CH.match(out[i - 1]):
                    rep = "ㅗ"
                out[i] = rep
    return "".join(out)


def level_homoglyph(text: str, alt_i: bool = False) -> str:
    """plain + NFKC(전각·호환문자) + 유사문자 치환(HOMOGLYPH 판정용). 한글 사이 영문·숫자 시각 치환 후에는 자모를 합성한다."""
    raw = _strip_noise(text or "")
    leet = korean_leet(raw)
    t = _nfkc_keep_jamo(level_plain(compose_jamo(leet) if leet != raw else text))
    t = _strip_noise(t.lower())
    return _map_homoglyphs(t, alt_i)


def _nfkc_keep_jamo(t: str) -> str:
    """NFKC 를 적용하되 호환 자모(ㄱ~ㅣ)는 그대로 둔다(NFKC 가 자모를 음절로 합성해 JAMO 판정과 섞이는 것 방지)."""
    out = []
    buf = []
    for ch in t:
        if "\u3131" <= ch <= "\u3163" or "\u1100" <= ch <= "\u11ff" or "\uffa1" <= ch <= "\uffdc":
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
    return any("\u3131" <= ch <= "\u3163" or "\u1100" <= ch <= "\u11ff" or "\uffa1" <= ch <= "\uffdc" for ch in text or "")


def aggressive(text: str, alt_i: bool = False) -> str:
    """키워드 탐지용 최대 정규화: 자모 합성 → NFKC → 한글 사이 시각 치환 → 유사문자 치환."""
    raw = _strip_noise(text or "")
    leet = korean_leet(raw)
    t = unicodedata.normalize("NFKC", level_jamo(compose_jamo(leet) if leet != raw else text))
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
    return bool(mixed_script_tokens(t))


# ---------- 스크립트 혼용 토큰(1급 HOMOGLYPH 신호) ----------
_TOKEN = re.compile(r"[\w@$!|€£¢§†+¡\uff01-\uff5e\u13a0-\u13ff\u0530-\u058f\u1d00-\u1d7f\ua730-\ua7ff\uab70-\uabbf]+")
_RANGES = (
    ("latin", re.compile(r"[a-zA-Z\u00c0-\u024f]")), ("cyrillic", re.compile("[\u0400-\u04ff]")),
    ("greek", re.compile("[\u0370-\u03ff]")), ("hangul", re.compile("[\uac00-\ud7a3\u3131-\u3163]")),
    ("fullwidth", re.compile("[\uff10-\uff19\uff21-\uff3a\uff41-\uff5a]")), ("digit", re.compile("[0-9]")),
    ("other", re.compile("[\u13a0-\u13ff\u0530-\u058f\u1d00-\u1d7f\ua730-\ua7ff\uab70-\uabbf]")),   # 기호(@$!…)는 글자 사이(leet)일 때만
)
_LEET_INSIDE = re.compile(r"[a-z][0-9@$!|€£¢§†+¡]+[a-z]")


def token_scripts(tok: str) -> set[str]:
    return {name for name, rx in _RANGES if rx.search(tok)}


def mixed_script_tokens(text: str) -> list[tuple[str, str]]:
    """한 단어 안에 스크립트가 섞인 토큰 [(토큰, 종류)]. 종류: 'mixed'(키릴·그리스·체로키 등 + 라틴/한글/숫자),
    'leet'(라틴 글자 사이에 숫자·기호), 'fullwidth'(전각 영문자 포함). 정상 러시아어 단어(순수 키릴)·'covid19'(숫자가 끝) 는 제외."""
    out: list[tuple[str, str]] = []
    for tok in _TOKEN.findall(text or ""):
        tok = tok.strip("@$!|€£¢§†+¡_")   # 멘션(@vip)·가격($10) 등 가장자리 기호는 위장이 아니다
        if len(tok) < 3 or tok.isdigit():
            continue
        sc = token_scripts(tok)
        disguise = sc & {"cyrillic", "greek", "other"}
        base = sc & {"latin", "hangul", "digit", "fullwidth"}
        if disguise and (base or len(disguise) > 1):
            out.append((tok, "mixed"))
        elif re.search("[\uff21-\uff3a\uff41-\uff5a]", tok):
            out.append((tok, "fullwidth"))
        elif "latin" in sc and _LEET_INSIDE.search(tok.lower()):
            out.append((tok, "leet"))
    return out


def skeleton(tok: str, alt_i: bool = False) -> str:
    """혼용 토큰을 라틴/한글 골격으로 되돌린다(NFKC → 소문자 → confusables/leet 치환 → 영숫자·한글만)."""
    t = unicodedata.normalize("NFKC", tok).lower()
    out = []
    for c in t:
        if alt_i and c in _ALT_I:
            out.append(_ALT_I[c])
        elif c in HOMOGLYPHS:
            out.append(HOMOGLYPHS[c])
        elif c in CONFUSABLES_EXTRA:
            out.append(CONFUSABLES_EXTRA[c])
        else:
            out.append(c)
    return re.sub(r"[^0-9a-z\uac00-\ud7a3]", "", "".join(out))


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
    """합성 가능한 분리 자모(ㅌㅗ 처럼 자음+모음, 첫가끝 조합형, 반각 자모)가 있으면 True. 'ㅋㅋ' 같은 단독 자음은 제외."""
    t = text or ""
    if _CONJOINING.search(t) or _HALFWIDTH_JAMO.search(t):
        return True
    return compose_jamo(t) != t
