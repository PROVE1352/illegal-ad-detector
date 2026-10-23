"""키워드 사전(도박·성인·불법금융·기타)과 화이트리스트 문맥.

사전은 .py 모듈로 유지해 PyInstaller 번들에 데이터 파일이 필요 없게 한다.
각 항목: (키워드, 가중치). 키워드는 normalize.aggressive 로 정규화된 형태로 비교한다.
"""
from __future__ import annotations

from .normalize import aggressive, has_jamo, level_homoglyph, level_jamo, level_plain

CATEGORY_LABEL = {
    "gambling": "도박",
    "adult": "성인",
    "finance": "불법금융",
    "other": "기타",
}

# 강한 키워드(단독으로도 의심): 가중치 3~4, 약한 키워드(문맥 필요): 1~1.5
KEYWORDS: dict[str, list[tuple[str, float]]] = {
    "gambling": [
        ("토토사이트", 4), ("사설토토", 4), ("안전놀이터", 4), ("메이저놀이터", 4), ("먹튀검증", 4),
        ("먹튀", 3), ("바카라", 3.5), ("카지노사이트", 4), ("온라인카지노", 4), ("라이브카지노", 4),
        ("슬롯사이트", 4), ("홀덤사이트", 3.5), ("파워볼", 3), ("사다리게임", 3), ("에볼루션카지노", 4),
        ("꽁머니", 4), ("첫충", 3), ("매충", 3), ("가입머니", 3.5), ("입플", 3), ("환전가능", 2.5),
        ("토토", 2), ("카지노", 1.5), ("배팅사이트", 3.5), ("베팅사이트", 3.5), ("스포츠토토사이트", 3),
        ("casino", 2.5), ("baccarat", 3), ("toto", 1.5), ("슬롯머신", 2), ("릴게임", 3), ("바다이야기", 3),
        ("도박", 1), ("놀이터추천", 4), ("검증업체", 3), ("보증업체", 3),
    ],
    "adult": [
        ("성인용품", 2), ("출장안마", 4), ("출장마사지", 4), ("조건만남", 4), ("성인야동", 4), ("야동", 3),
        ("무료야동", 4), ("성인방송", 3.5), ("성인사이트", 3.5), ("성인웹툰", 2.5), ("오피", 2.5),
        ("오피사이트", 4), ("키스방", 4), ("휴게텔", 4), ("안마방", 3.5), ("풀싸롱", 4), ("섹파", 4),
        ("애인대행", 4), ("19금", 1.5), ("성인", 0.8), ("porn", 3), ("av배우", 2.5), ("웹캠채팅", 2.5),
        ("야한", 1), ("몸캠", 3), ("핸플", 4), ("립카페", 4),
    ],
    "finance": [
        ("무담보대출", 2.5), ("당일대출", 2.5), ("무직자대출", 3), ("신불자대출", 3.5), ("급전", 2),
        ("일수대출", 3.5), ("개인돈", 3), ("월변", 3.5), ("휴대폰소액결제", 3), ("소액결제현금화", 4),
        ("정보이용료현금화", 4), ("상품권현금화", 3), ("카드깡", 4), ("작업대출", 4), ("통장임대", 4),
        ("통장매입", 4), ("대포통장", 4), ("코인리딩", 3), ("리딩방", 3), ("주식리딩방", 3.5), ("수익보장", 2),
        ("원금보장", 1.5), ("대출", 0.8), ("무서류대출", 3), ("신용불량자대출", 3),
    ],
    "other": [
        ("대포폰", 4), ("명의대여", 3), ("레플리카", 2.5), ("짝퉁", 2.5), ("명품레플", 3.5), ("이미테이션", 2),
        ("마약", 1.5), ("떨판매", 4), ("아이스판매", 4), ("졸피뎀", 3), ("비아그라판매", 3.5), ("시알리스", 3),
        ("정품비아그라", 3.5), ("해킹의뢰", 3.5), ("디비판매", 3.5), ("디비업자", 3.5), ("문자발송대행", 2),
        ("웹툰미리보기", 2), ("불법촬영", 1), ("유흥알바", 3), ("고수익알바", 3.5),
    ],
}

# 화이트리스트 문맥(정규화 후 비교): 공공기관의 정상 문서에서 흔한 문구. 매칭 시 감점.
WHITELIST_CONTEXT: list[tuple[str, float]] = [
    ("도박중독", -3), ("도박문제", -3), ("중독예방", -3), ("예방교육", -2), ("신고", -1.5), ("단속", -2),
    ("불법사이트차단", -3), ("차단", -1), ("피해예방", -2), ("상담센터", -2), ("1336", -2), ("치유", -2),
    ("사행산업", -2), ("사행성", -1.5), ("성인지", -3), ("성인지감수성", -3), ("성인지교육", -3), ("성인학습자", -2),
    ("성인문해", -2), ("성인교육", -2), ("성인병", -2), ("성인권", -2), ("정부지원대출", -3), ("햇살론", -3),
    ("서민금융", -3), ("대출사기", -2), ("불법사금융", -2), ("피해신고", -2), ("경찰", -1), ("법률", -1),
    ("조례", -1.5), ("공고", -1), ("보도자료", -1), ("안내문", -1), ("캠페인", -2), ("주의", -0.5),
    ("마약류관리", -2), ("마약예방", -3), ("의약품", -1.5), ("처방", -1.5), ("보건소", -2), ("금융감독원", -3),
    ("한국도박문제예방치유원", -4), ("금융위원회", -2), ("불법광고", -2), ("스팸", -1.5), ("성인건강", -2),
    ("성인기", -2), ("성인자녀", -2), ("성인학", -1.5),
]

# 정규화 단계별 사전 캐시: cat -> [(plain, jamo, homo, full, orig, weight)]
_NORM: dict[str, list[tuple[str, str, str, str, str, float]]] | None = None
_NORM_WHITELIST: list[tuple[str, str, float]] | None = None

LEVEL_PLAIN, LEVEL_JAMO, LEVEL_HOMOGLYPH, LEVEL_BOTH = "plain", "JAMO", "HOMOGLYPH", "both"


def _prepare() -> None:
    global _NORM, _NORM_WHITELIST
    if _NORM is None:
        _NORM = {
            cat: [(level_plain(k), level_jamo(k), level_homoglyph(k), aggressive(k), k, w) for k, w in items]
            for cat, items in KEYWORDS.items()
        }
        _NORM_WHITELIST = [(aggressive(k), k, w) for k, w in WHITELIST_CONTEXT]


def match_keywords_levels(text: str) -> dict[str, list[tuple[str, float, str]]]:
    """카테고리별 (키워드, 가중치, 레벨). 레벨: plain / JAMO / HOMOGLYPH / both.

    plain  : 난독화 해제 없이도 매칭(공백·특수문자 삽입 정도)
    JAMO   : 분리 자모를 합성해야 매칭
    HOMOGLYPH: 전각·키릴·숫자 유사문자를 치환해야 매칭
    both   : 둘 다 적용해야 매칭
    """
    _prepare()
    assert _NORM is not None
    t_plain = level_plain(text)
    t_jamo = level_jamo(text)
    t_homo = level_homoglyph(text)
    t_full = aggressive(text)
    result: dict[str, list[tuple[str, float, str]]] = {}
    for cat, items in _NORM.items():
        hits: list[tuple[str, float, str]] = []
        for k_plain, k_jamo, k_homo, k_full, orig, w in items:
            if not k_full:
                continue
            if k_plain in t_plain:
                hits.append((orig, w, LEVEL_PLAIN))
            elif k_jamo in t_jamo:
                hits.append((orig, w, LEVEL_JAMO))
            elif k_homo in t_homo:
                hits.append((orig, w, LEVEL_HOMOGLYPH))
            elif k_full in t_full:
                hits.append((orig, w, LEVEL_JAMO if has_jamo(text) else LEVEL_HOMOGLYPH))
        pruned = [h for h in hits if not any(h[0] != o[0] and h[0] in o[0] for o in hits)]
        if pruned:
            result[cat] = pruned
    return result


def match_keywords(text: str) -> dict[str, list[tuple[str, float, bool]]]:
    """하위 호환: (키워드, 가중치, 난독화여부)."""
    return {cat: [(k, w, lv != LEVEL_PLAIN) for k, w, lv in hits] for cat, hits in match_keywords_levels(text).items()}


def match_whitelist(text: str) -> list[tuple[str, float]]:
    _prepare()
    assert _NORM_WHITELIST is not None
    norm = aggressive(text)
    return [(orig, w) for nk, orig, w in _NORM_WHITELIST if nk in norm]
