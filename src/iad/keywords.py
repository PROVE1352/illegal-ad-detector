"""키워드 사전(도박·성인·불법금융·기타)과 화이트리스트 문맥.

사전은 .py 모듈로 유지해 PyInstaller 번들에 데이터 파일이 필요 없게 한다.
각 항목: (키워드, 가중치). 키워드는 normalize.aggressive 로 정규화된 형태로 비교한다.
"""
from __future__ import annotations

from .normalize import (aggressive, chosung_of, consonant_runs, has_jamo, level_homoglyph, level_jamo, level_plain,
                        mixed_script_tokens, skeleton)

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
        ("casino", 2.5), ("baccarat", 3), ("toto", 1.5), ("totosite", 3), ("슬롯머신", 2), ("릴게임", 3), ("바다이야기", 3),
        ("도박", 1), ("놀이터추천", 4), ("검증업체", 3), ("보증업체", 3),
        ("슬롯", 1.5), ("무료슬롯", 3), ("슬롯체험", 3), ("슬롯게임", 3), ("카지노보너스", 3), ("가입보너스", 3),
        ("보너스코드", 2.5), ("가입코드", 2), ("추천코드", 1.5), ("먹튀없는", 3.5), ("메이저사이트", 3.5),
        ("안전사이트", 2.5), ("배팅", 1.5), ("베팅", 1.5), ("스포츠배팅", 3), ("스포츠베팅", 3), ("라이브배팅", 3),
        ("카지노추천", 4), ("바카라추천", 4), ("토토추천", 4), ("홀덤", 1.5), ("룰렛", 1.5), ("블랙잭", 1.5), ("포커", 1.5),
        ("slot", 1.5), ("slots", 1.5), ("slotmachine", 2.5), ("jackpot", 2), ("poker", 1.5), ("holdem", 2), ("roulette", 1.5),
        ("blackjack", 2), ("gambling", 1.5), ("onlinecasino", 4), ("livecasino", 3.5), ("freespin", 3), ("freebet", 3),
        ("bet365", 3), ("betting", 2), ("sportsbet", 3), ("sportsbetting", 3), ("bookmaker", 2.5),
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
    ("성인기", -2), ("성인자녀", -2), ("성인학", -1.5), ("국민체육진흥법", -3), ("처벌", -2), ("위반", -1.5),
    ("방송통신심의위원회", -3), ("유해정보", -2), ("청소년보호", -2), ("사이버수사", -3), ("수사", -1),
    ("운영자검거", -2), ("검거", -2), ("근절", -2), ("정보통신망법", -2), ("청소년", -1),
    ("초성퀴즈", -4), ("초성", -2), ("자음", -2), ("모음", -1), ("한글교육", -2), ("받침", -2), ("문해교육", -2),
    ("강원랜드", -3), ("관광", -2), ("규제", -2), ("현황", -1), ("정책", -1.5), ("안내", -0.5), ("프로그램", -1), ("관람", -1.5),
]

# 초성 축약(ㅋㅈㄴ=카지노) 판정: 2자 초성은 흔한 채팅 축약과 겹치므로 허용 목록 + 문맥어가 있을 때만
CHOSUNG_MIN_WEIGHT = 1.5
CHOSUNG_2CHAR_BLOCK = {"ㅇㄷ", "ㅁㅊ", "ㅊㅊ", "ㄱㅈ", "ㅈㅈ", "ㄱㅅ", "ㅅㄱ", "ㄷㄷ", "ㅎㅇ", "ㅂㅂ", "ㄴㄴ", "ㅇㅇ", "ㅇㅋ", "ㅈㅅ",
                       "ㅅㅂ", "ㅈㄹ", "ㄱㄱ", "ㅇㅈ", "ㄹㅇ", "ㅂㄹ", "ㅅㅇ", "ㄷㅊ", "ㄷㅂ", "ㅁㄹ", "ㅇㅍ", "ㅋㅋ", "ㅎㅎ", "ㅠㅠ"}
CHOSUNG_CONTEXT = ("사이트", "추천", "가입", "코드", "보너스", "입금", "환전", "배팅", "베팅", "머니", "이벤트", "주소", "도메인",
                   "링크", "바로가기", "텔레", "카톡", "문의", "출장", "만남", "대출", "승인", "입플", "첫충", "매충", "꽁")

# 스크립트 혼용(유사문자 위장) 토큰의 골격에서만 찾는 영문 도박어. 평문 'bet'·'win' 은 일반 영문에 흔해 사전에 넣지 않지만,
# 키릴·그리스·전각·leet 로 위장한 단어 안에서 복원되면 위장 자체가 신호이므로 인정한다. 전각만(ＷＩＮ, IME 입력) 인 토큰은 가중치 ≥2 만.
MIXED_TERMS: list[tuple[str, float]] = [
    ("casino", 3), ("baccarat", 3), ("toto", 2.5), ("slot", 2), ("slots", 2), ("bet", 2), ("betting", 2.5), ("poker", 2),
    ("holdem", 2.5), ("jackpot", 2.5), ("roulette", 2), ("blackjack", 2), ("gambling", 2), ("sportsbet", 3), ("freespin", 3),
    ("freebet", 3), ("bookmaker", 2.5), ("lotto", 2), ("lottery", 2), ("wager", 2.5), ("keno", 2), ("bingo", 1.5),
    ("win", 1.0), ("spin", 1.5), ("bonus", 1.5), ("powerball", 2.5), ("pachinko", 2.5), ("megabet", 3), ("sexy", 1.5),
    ("porn", 3), ("adult", 1.5), ("loan", 1.5), ("cash", 1.5),
]

# 광고 유도 보조어(조정안 A): 은닉이 확정된 요소에서 중위 키워드(1.5: 슬롯·카지노·토토…) 하나와 함께 있으면 광고로 본다
AD_INDUCEMENT: tuple[str, ...] = ("무료", "체험", "보너스", "코드", "가입", "쿠폰", "지급", "충전", "환전", "이벤트", "바로가기", "실시간",
                                  "입장", "%", "％", "주소", "도메인", "접속", "추천", "링크", "사이트", "머니", "배당", "출금", "입금")


def inducement_words(text: str) -> list[str]:
    plain = level_plain(text)
    return [w for w in AD_INDUCEMENT if w in plain]


# 정규화 단계별 사전 캐시: cat -> [(plain, jamo, homo, full, orig, weight)]
_NORM: dict[str, list[tuple[str, str, str, str, str, float]]] | None = None
_CHOSUNG: dict[str, list[tuple[str, str, float]]] | None = None   # cat -> [(초성, orig, weight)]
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
        global _CHOSUNG
        _CHOSUNG = {}
        for cat, items in KEYWORDS.items():
            for k, w in items:
                cho = chosung_of(k)
                if cho and w >= CHOSUNG_MIN_WEIGHT and len(cho) >= 2 and cho not in CHOSUNG_2CHAR_BLOCK:
                    _CHOSUNG.setdefault(cat, []).append((cho, k, w))


def chosung_hits(text: str) -> dict[str, list[tuple[str, float, str]]]:
    """초성 축약 매칭(ㅋㅈㄴ→카지노, ㅌㅌ→토토). 레벨은 JAMO.
    3자 이상 초성은 자음 덩어리 안에 포함되면 인정, 2자 초성은 덩어리 전체가 일치하고 문맥어가 함께 있을 때만."""
    _prepare()
    assert _CHOSUNG is not None
    runs = consonant_runs(text)
    if not runs:
        return {}
    plain = level_plain(text)
    has_ctx = any(c in plain for c in CHOSUNG_CONTEXT)
    out: dict[str, list[tuple[str, float, str]]] = {}
    for cat, items in _CHOSUNG.items():
        for cho, orig, w in items:
            ok = False
            if len(cho) >= 3:
                ok = any(cho in r for r in runs)
            elif has_ctx:
                ok = any(r == cho for r in runs)
            if ok:
                out.setdefault(cat, []).append((orig, w, LEVEL_JAMO))
    return out


def mixed_script_hits(text: str) -> dict[str, list[tuple[str, float, str]]]:
    """스크립트 혼용 토큰의 골격을 사전(한국어 사전 + MIXED_TERMS)과 대조한다. 레벨은 HOMOGLYPH."""
    toks = mixed_script_tokens(text)
    if not toks:
        return {}
    _prepare()
    assert _NORM is not None
    out: dict[str, list[tuple[str, float, str]]] = {}
    for tok, kind in toks:
        sks = {skeleton(tok), skeleton(tok, alt_i=True)}
        for cat, items in _NORM.items():
            for _p, _j, _h, k_full, orig, w in items:
                if w >= 1.0 and k_full and any(k_full in sk for sk in sks):
                    if kind == "fullwidth" and w < 2:
                        continue
                    out.setdefault(cat, []).append((orig, w, LEVEL_HOMOGLYPH))
        for term, w in MIXED_TERMS:
            if any(term in sk for sk in sks) and not (kind == "fullwidth" and w < 2):
                cat = "adult" if term in ("sexy", "porn", "adult") else "finance" if term in ("loan", "cash") else "gambling"
                out.setdefault(cat, []).append((term, w, LEVEL_HOMOGLYPH))
    return out


def match_keywords_levels(text: str, chosung: bool = True) -> dict[str, list[tuple[str, float, str]]]:
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
    t_homo_i = level_homoglyph(text, alt_i=True) if any(c in text for c in "1|!") else t_homo
    t_full = aggressive(text)
    t_full_i = aggressive(text, alt_i=True) if t_homo_i is not t_homo else t_full
    cho_hits = chosung_hits(text) if chosung else {}
    mixed_hits = mixed_script_hits(text)
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
            elif k_homo in t_homo or k_homo in t_homo_i:
                hits.append((orig, w, LEVEL_HOMOGLYPH))
            elif k_full in t_full or k_full in t_full_i:
                hits.append((orig, w, LEVEL_JAMO if has_jamo(text) else LEVEL_HOMOGLYPH))
        for orig, w, lv in cho_hits.get(cat, []):
            if not any(h[0] == orig for h in hits):
                hits.append((orig, w, lv))
        for orig, w, lv in mixed_hits.get(cat, []):
            if not any(h[0] == orig for h in hits):
                hits.append((orig, w, lv))
        pruned = [h for h in hits if not any(h[0] != o[0] and h[0] in o[0] for o in hits)]
        if pruned:
            result[cat] = pruned
    return result


def match_keywords(text: str) -> dict[str, list[tuple[str, float, bool]]]:
    """하위 호환: (키워드, 가중치, 난독화여부)."""
    return {cat: [(k, w, lv != LEVEL_PLAIN) for k, w, lv in hits] for cat, hits in match_keywords_levels(text).items()}


# 행정 문맥(예방·단속·신고 안내)에서 흔한 표현. 키워드 주변 ±window 안에 있으면 '안내문' 으로 본다.
ADMIN_CONTEXT: list[tuple[str, float]] = [
    ("예방", -2), ("단속", -2), ("적발", -2), ("주의보", -2), ("1336", -3), ("상담", -1), ("교육", -1.5), ("신고", -1.5),
    ("차단", -1.5), ("처벌", -2), ("수사", -1.5), ("검거", -2), ("근절", -2), ("캠페인", -2), ("피해", -1.5), ("위반", -1.5),
    ("안내", -0.5), ("홍보", -1), ("법률", -1), ("조례", -1.5), ("보도자료", -1.5), ("경찰", -1), ("유해", -1.5), ("중독", -2),
]
_NORM_ADMIN: list[tuple[str, str, float]] | None = None


def match_whitelist(text: str, window: int | None = None) -> list[tuple[str, float]]:
    """화이트리스트 문맥 매칭. window 를 주면 '불법 키워드 주변 ±window 자(정규화 문자열 기준)' 안의 행정 문맥만 센다."""
    global _NORM_ADMIN
    _prepare()
    assert _NORM is not None and _NORM_WHITELIST is not None
    if _NORM_ADMIN is None:
        _NORM_ADMIN = [(aggressive(k), k, w) for k, w in ADMIN_CONTEXT]
    norm = aggressive(text)
    out = [(orig, w) for nk, orig, w in _NORM_WHITELIST if nk in norm]
    if window is None:
        return out
    spans: list[tuple[int, int]] = []
    for items in _NORM.values():
        for _p, _j, _h, k_full, _o, w in items:
            if w < 1.0 or not k_full:
                continue
            start = 0
            while True:
                i = norm.find(k_full, start)
                if i < 0:
                    break
                spans.append((max(0, i - window), i + len(k_full) + window))
                start = i + 1
    if not spans:
        return out
    seen = {o for o, _ in out}
    for a, b in spans:
        win = norm[a:b]
        for nk, orig, w in _NORM_ADMIN:
            if orig not in seen and nk in win:
                seen.add(orig)
                out.append((orig, w))
    return out


def admin_context_score(text: str, window: int = 100) -> float:
    """불법 키워드 주변의 행정 문맥 총점(음수일수록 안내문에 가깝다)."""
    return sum(w for _, w in match_whitelist(text, window=window))
