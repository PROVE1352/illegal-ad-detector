"""작업지시서용 보강 정보(AR4): 발견 영역 분류, 조치 가이드, 신고처, defang URL, SHA-256 지문, 처리 우선순위.

리포트(report.py)·GUI(run_gui.py)·CSV 가 같은 함수를 쓴다. 탐지 로직에는 영향이 없다.
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse

from .models import Finding

_AREA_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("댓글", re.compile(r"comment|reply|cmt|repl|답글|댓글", re.I)),
    ("게시글 본문", re.compile(r"article|content|cont\b|view|post|body|desc|detail|bbs_?view|editor|se2|smart", re.I)),
    ("게시판 목록", re.compile(r"board|list|\btr\b|\btd\b|table|row|subject|title|notice", re.I)),
    ("하단(푸터)", re.compile(r"footer|foot|copyright|bottom", re.I)),
    ("상단/메뉴", re.compile(r"header|head\b|gnb|lnb|nav|menu|top", re.I)),
    ("사이드/배너", re.compile(r"side|aside|banner|bnr|widget|quick", re.I)),
]

# 조치 가이드: 기법/유형 → (요약, 단계 목록)
_GUIDES: dict[str, tuple[str, list[str]]] = {
    "OFFSCREEN": ("화면 밖·display:none 으로 숨긴 불법광고 텍스트", [
        "해당 선택자 요소를 게시글(또는 템플릿)에서 삭제",
        "게시글이면 작성자 계정·IP 확인 후 차단, 동일 작성자의 다른 글 전수 점검",
        "공통 영역(푸터·헤더·위젯)이면 서버 파일 변조(웹셸) 가능성 → 최근 수정 파일·무결성 점검",
    ]),
    "TRANSPARENT": ("배경색과 같은 색·투명 처리로 숨긴 불법광고 텍스트", [
        "해당 선택자 요소를 게시글(또는 템플릿)에서 삭제",
        "게시글이면 작성자 계정·IP 확인 후 차단, 동일 작성자의 다른 글 전수 점검",
        "에디터에서 글자색 지정이 가능하면 금칙어 필터를 색상과 무관하게 적용되도록 점검",
    ]),
    "HOMOGLYPH": ("전각·키릴·숫자 유사문자로 금칙어 필터를 우회한 불법광고", [
        "게시글 삭제 및 작성자 차단",
        "게시판 금칙어 필터에 NFKC 정규화·유사문자 치환을 추가(ｃａｓｉｎｏ→casino, t0t0→toto)",
    ]),
    "JAMO": ("자모 분리(ㅌㅗㅌㅗ)로 금칙어 필터를 우회한 불법광고", [
        "게시글 삭제 및 작성자 차단",
        "게시판 금칙어 필터에 자모 합성(ㅌㅗㅌㅗ→토토) 전처리를 추가",
    ]),
    "CLOAKING": ("일반 사용자에게는 보이지 않고 검색엔진 봇·검색 유입에만 노출되는 변조(서버 측 클로킹)", [
        "서버 침해 의심: 공통 JSP/PHP(index, footer, header), .htaccess, web.xml 필터 등 최근 변경 파일 점검",
        "웹셸 탐지(의심 업로드 파일·실행 가능한 첨부 폴더) 및 관리자 계정 비밀번호 변경",
        "네이버 서치어드바이저·구글 서치콘솔에서 색인 삭제 요청, 호스팅·보안관제(KISA 118)에 신고",
    ]),
    "SCRIPT_INJECTION": ("스크립트로 외부 링크·iframe 을 주입(또는 인코딩으로 숨김)", [
        "해당 <script> 의 출처 확인(템플릿 파일·게시글 본문·외부 JS)",
        "템플릿 파일이면 서버 변조로 간주하고 파일 무결성·웹셸 점검",
        "주입 대상 외부 도메인을 방화벽/프록시에서 차단",
    ]),
    "SCRIPT_DECODED": ("인코딩(base64·fromCharCode 등)으로 숨긴 스크립트 내용", ["SCRIPT_INJECTION 과 동일 조치, 디코딩된 내용(근거)을 증적으로 보관"]),
    "META_REFRESH": ("meta refresh 로 외부 사이트 자동 이동", ["해당 페이지/게시글 삭제 또는 meta 태그 제거", "이동 대상 도메인 차단"]),
    "JS_REDIRECT": ("JS 로 외부 사이트 자동 이동", ["스크립트 제거, 템플릿 변조 여부 점검", "이동 대상 도메인 차단"]),
    "HIDDEN_IFRAME": ("숨긴(1×1·display:none) iframe", ["iframe 제거, src 도메인 차단", "템플릿 변조 여부 점검"]),
    "EXTERNAL_IFRAME": ("외부 도메인 iframe", ["업무상 필요한 위젯인지 확인, 아니면 제거"]),
    "HTML_COMMENT": ("HTML 주석 안의 링크/키워드(검색엔진 노출용 흔적)", ["주석 제거, 게시글이면 작성자 점검"]),
    "NOSCRIPT": ("<noscript> 안의 링크/키워드", ["noscript 블록 제거, 작성자 점검"]),
    "HIDDEN_VISIBILITY_HIDDEN": ("visibility:hidden 으로 숨긴 요소", ["요소 삭제, 작성자/템플릿 점검"]),
    "HIDDEN_HIDDEN_ATTR": ("hidden/aria-hidden 속성으로 숨긴 요소", ["요소 삭제, 작성자/템플릿 점검"]),
    "HIDDEN_TINY_SIZE": ("1×1 크기·clip 으로 숨긴 요소", ["요소 삭제, 작성자/템플릿 점검"]),
    "HIDDEN_MARQUEE": ("marquee 안의 광고 문구", ["요소 삭제, 작성자 점검"]),
    "HIDDEN_EXTERNAL_LINK": ("숨긴 요소 안의 외부(비신뢰) 링크", ["링크 제거, 도메인 차단, 작성자/템플릿 점검"]),
    "SUSPICIOUS_TLD": ("의심 TLD(.top/.xyz 등) 외부 링크", ["게시글 삭제·작성자 차단", "도메인을 신고처에 제출"]),
    "SHORTENER": ("단축 URL 뒤에 숨긴 링크", ["게시글 삭제·작성자 차단", "단축 URL 의 실제 목적지 확인 후 신고"]),
    "MESSENGER": ("텔레그램/오픈채팅 유도 링크", ["게시글 삭제·작성자 차단", "계정명을 증적으로 보관해 신고"]),
    "NUMERIC_DOMAIN": ("숫자 위주 도메인 링크", ["게시글 삭제·작성자 차단"]),
    "ANCHOR_MISMATCH": ("표시 주소와 실제 링크가 다른 앵커(피싱형)", ["게시글 삭제·작성자 차단", "실제 링크 도메인 차단"]),
    "MASS_EXTERNAL_LINKS": ("한 영역에 외부 도메인 다수 링크(링크 스팸)", ["게시글 삭제·작성자 차단", "게시판 외부 링크 수 제한 설정"]),
    "OBFUSCATION_INSERT": ("제로폭·특수문자 삽입 난독화", ["게시글 삭제·작성자 차단", "금칙어 필터에 제로폭 문자 제거 전처리 추가"]),
    "DYNAMIC_INJECTION": ("렌더링 후에만 나타나는 주입 요소", ["주입 스크립트 출처 확인, 템플릿 변조 점검"]),
    "IMAGE_BANNER_AD": ("텍스트 없는 이미지 배너 링크(무작위·회전 도메인, 메신저, 광고성 alt)", [
        "배너 이미지의 실제 링크 대상 확인(브라우저로 열지 말고 defang 주소를 조회)",
        "게시글 첨부/본문 배너면 삭제·작성자 차단, 템플릿 배너 영역이면 관리자 계정·배너 관리 기능 침해 점검",
        "링크 도메인·텔레그램 채널을 증적으로 보관해 신고",
    ]),
}

REPORT_CONTACTS = {
    "도박": "사행산업통합감독위원회 불법사행산업 신고(1855-0112, www.ngcc.go.kr) / 방송통신심의위원회 1377",
    "성인": "방송통신심의위원회 1377(www.kocsc.or.kr) / 여성가족부 성매매 피해상담 1366",
    "불법금융": "금융감독원 불법사금융 신고 1332 / 경찰청 112",
    "기타": "한국인터넷진흥원(KISA) 118 / 경찰청 사이버수사국 ecrm.police.go.kr",
    "의심 링크": "한국인터넷진흥원(KISA) 불법스팸대응센터 118",
    "스크립트 주입": "한국인터넷진흥원(KISA) 침해사고 신고 118",
}


def area_of(f: Finding) -> str:
    if f.is_iframe or f.frame_url or " >>> " in f.location:
        return "iframe 위젯"
    if f.tag == "#comment":
        return "HTML 주석"
    if f.tag in ("script", "meta", "html"):
        return "스크립트/리다이렉트"
    hay = f.location.lower()
    for name, rx in _AREA_RULES:
        if rx.search(hay):
            return name
    return "본문 기타"


def guide_for(f: Finding) -> list[dict[str, object]]:
    """[{'name', 'summary', 'steps'}] — 4종 코드 먼저, 그다음 추가 유형(이름 접두어 CLOAKING_ 은 CLOAKING 가이드)."""
    out: list[dict[str, object]] = []
    seen: set[str] = set()
    for name in list(f.official) + list(f.extra_names):
        key = name
        if name.startswith("CLOAKING"):
            key = "CLOAKING"
        elif name.startswith("HIDDEN_") and name not in _GUIDES:
            key = "HIDDEN_TINY_SIZE" if "TINY" in name else "HIDDEN_HIDDEN_ATTR"
        elif name.upper() in _GUIDES:
            key = name.upper()
        if key in seen:
            continue
        seen.add(key)
        g = _GUIDES.get(key)
        if g:
            out.append({"name": name, "summary": g[0], "steps": list(g[1])})
    if not out:
        out.append({"name": "+".join(f.official + f.extra_names) or "SUSPICIOUS",
                    "summary": "의심 요소", "steps": ["내용 확인 후 삭제 여부 판단, 작성자 점검"]})
    return out


def contact_for(f: Finding) -> str:
    return REPORT_CONTACTS.get(f.category, REPORT_CONTACTS["기타"])


def defang(url: str) -> str:
    """hxxp://evil[.]top/path — 보고서에서 실수로 클릭되지 않게."""
    try:
        p = urlparse(url)
    except ValueError:
        return url.replace("http", "hxxp").replace(".", "[.]")
    host = (p.hostname or "").replace(".", "[.]")
    scheme = p.scheme.replace("http", "hxxp") if p.scheme else ""
    port = f":{p.port}" if p.port else ""
    rest = (p.path or "") + (("?" + p.query) if p.query else "")
    return f"{scheme}://{host}{port}{rest}" if scheme else f"{host}{port}{rest}"


def fingerprint(f: Finding) -> str:
    """검출 요소의 SHA-256(페이지 URL + 위치 + 원문 HTML). 재점검 시 같은 요소인지 대조용."""
    h = hashlib.sha256()
    h.update(f.page_url.encode("utf-8", "ignore"))
    h.update(b"\n")
    h.update(f.location.encode("utf-8", "ignore"))
    h.update(b"\n")
    h.update((f.html or f.evidence_text).encode("utf-8", "ignore"))
    return h.hexdigest()


def priority_of(f: Finding) -> str:
    """긴급: 요강 4종 또는 클로킹/스크립트 주입 + 높음 / 높음: 위험도 높음 또는 4종 / 보통: 그 외."""
    hard = bool(f.official) or any(n.startswith(("CLOAKING", "SCRIPT_")) for n in f.extra_names)
    if hard and f.risk == "높음":
        return "긴급"
    if hard or f.risk == "높음":
        return "높음"
    return "보통"


def enrich(f: Finding) -> dict[str, object]:
    return {
        "area": area_of(f),
        "priority": priority_of(f),
        "guide": guide_for(f),
        "contact": contact_for(f),
        "defanged_url": defang(f.page_url),
        "defanged_links": [defang(u) for u in f.links],
        "fingerprint": fingerprint(f),
    }
