"""가짜 공공기관 사이트 픽스처 생성기(단일 소스 → HTML + labels.json).

python src/fixtures/gen_fixtures.py [--port 8765]
- dev/     : 규칙 튜닝용
- holdout/ : 검증용(규칙 튜닝에 쓰지 않음)
요소 id 는 중립적(c01 …)으로 붙이며 탐지기는 id 를 읽지 않는다. 라벨은 (doc, element_id, technique) 로 기록한다.
"""
from __future__ import annotations

import argparse
import base64
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent

CSS = """
body{font-family:sans-serif;margin:0;background:#fff;color:#222}
.header{background:#0b4ea2;color:#fff;padding:14px 24px}
.nav a{color:#fff;margin-right:12px;text-decoration:none}
.container{max-width:960px;margin:0 auto;padding:16px}
table.board-list{width:100%;border-collapse:collapse}
table.board-list td,table.board-list th{border-bottom:1px solid #ddd;padding:8px}
.article-body{line-height:1.7}
.comments{margin-top:24px;border-top:2px solid #eee}
.comment{padding:8px 0;border-bottom:1px solid #eee}
.sr-only{position:absolute;left:-9999px;top:auto;width:1px;height:1px;overflow:hidden}
.footer{color:#666;font-size:12px;padding:16px;border-top:1px solid #ddd}
"""


class Site:
    def __init__(self, name: str, port: int, seed: int) -> None:
        self.name = name
        self.port = port
        self.rng = random.Random(seed)
        self.labels: list[dict] = []
        self.files: dict[str, str | bytes] = {}
        self.decoys: list[str] = []
        self.n = 0

    # ---------- 유틸 ----------
    def nid(self) -> str:
        self.n += 1
        return f"c{self.n:02d}"

    def label(self, doc: str, eid: str, technique: str, category: str, page: str | None = None, extra: str = "",
              note: str = "") -> None:
        self.labels.append({"set": self.name, "page": page or doc, "doc": doc, "element_id": eid,
                            "technique": technique, "category": category, "extra_name": extra, "note": note})

    def ext(self, path: str) -> str:
        return f"http://localhost:{self.port}/{self.name}/{path}"

    def page(self, title: str, body: str, extra_head: str = "", list_href: str = "index.html") -> str:
        return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{title} - 행복시청</title>
<style>{CSS}</style>{extra_head}</head><body>
<div class="header"><h1>행복시청</h1><div class="nav"><a href="index.html">공지사항</a><a href="about.html">기관소개</a><a href="{list_href}">목록</a></div></div>
<div class="container">{body}</div>
<div class="footer">행복시청 · 행복로 1 · 전화 02-000-0000 · <a href="https://www.mois.go.kr">행정안전부</a></div>
</body></html>"""

    def post(self, path: str, title: str, body_html: str, comments: list[str], extra_head: str = "") -> None:
        cm = "".join(f'<li class="comment">{c}</li>' for c in comments)
        body = f"""<h2 class="title">{title}</h2>
<div class="meta">작성자: 행정지원과 · 조회 {self.rng.randint(10, 900)}</div>
<div class="article-body">{body_html}</div>
<div class="comments"><h3>댓글 {len(comments)}</h3><ul>{cm}</ul></div>"""
        self.files[path] = self.page(title, body, extra_head)

    # ---------- 사이트 생성 ----------
    def build(self) -> None:
        posts: list[tuple[str, str]] = []   # (path, title)

        def add(path: str, title: str, body: str, comments: list[str], head: str = "", decoy: bool = False) -> None:
            self.post(path, title, body, comments, head)
            posts.append((path, title))
            if decoy:
                self.decoys.append(path)

        v = self.name == "holdout"   # 변형 스위치
        p = self.ext  # 외부 URL

        # ----- 정상(오탐 유도) 문서 -----
        add("post/notice_gambling_prevention.html", "도박 중독 예방 주간 안내",
            "<p>행복시는 한국도박문제예방치유원과 함께 도박 중독 예방 캠페인을 진행합니다.</p>"
            "<p>불법 도박 사이트 신고는 국번 없이 1336(도박문제 상담), 사이버수사대 182 로 연락하세요.</p>"
            "<p>불법 토토 사이트 운영·광고는 국민체육진흥법 위반으로 처벌됩니다. 청소년 도박 예방 교육 자료는 아래 첨부를 참고하세요.</p>"
            '<p><a href="https://www.kcgp.or.kr">한국도박문제예방치유원 바로가기</a></p>',
            ["좋은 정보 감사합니다.", "예방 교육 신청은 어디서 하나요?"], decoy=True)
        add("post/notice_gender_edu.html", "2026년 성인지 교육 및 폭력예방교육 실시 안내",
            "<p>전 직원 대상 성인지 감수성 교육을 실시합니다. 성인지 교육은 법정 의무교육입니다.</p>"
            "<p>성인 학습자 대상 평생교육 프로그램(성인 문해교육)도 함께 접수합니다.</p>",
            ["일정 확인했습니다."], decoy=True)
        add("post/notice_loan.html", "서민 대상 정부지원 대출(햇살론) 안내",
            "<p>서민금융진흥원과 연계한 햇살론 등 정부지원 대출 상담을 안내합니다. 대출 사기 및 불법 사금융 피해 주의하세요.</p>"
            "<p>불법 사금융 피해신고: 금융감독원 1332</p>"
            '<ul><li><a href="https://www.kinfa.or.kr">서민금융진흥원</a></li><li><a href="https://www.fss.or.kr">금융감독원</a></li></ul>',
            ["문의 드립니다. 신청 자격이 궤변인가요?"], decoy=True)
        add("post/notice_block.html", "불법 유해정보 사이트 차단 안내",
            "<p>방송통신심의위원회 심의에 따라 불법 도박·성인물 사이트 접속이 차단됩니다. 차단 안내 페이지가 표시되면 접속을 중단하세요.</p>"
            "<p>불법 광고 스팸 문자는 118 로 신고하세요.</p>",
            ["ㅋㅋ 요즘 스팸 문자 너무 많아요", "２０２６년 ３월부터 시행이군요"], decoy=True)
        add("post/notice_drug.html", "보건소 마약류 예방 교육 안내",
            "<p>마약류관리에 관한 법률에 따른 의약품 안전 사용 교육. 졸피뎀 등 향정신성 의약품은 반드시 의사 처방에 따라 복용하세요.</p>",
            [], decoy=True)
        add("post/notice_links.html", "유관기관 홈페이지 안내",
            '<ul><li><a href="https://www.gov.kr">정부24</a></li><li><a href="https://www.mois.go.kr">행정안전부</a></li>'
            '<li><a href="https://www.korea.kr">대한민국 정책브리핑</a></li><li><a href="https://www.nts.go.kr">국세청</a></li>'
            '<li><a href="https://www.nhis.or.kr">국민건강보험</a></li><li><a href="https://www.youtube.com/@happycity">시청 유튜브</a></li></ul>'
            '<p class="sr-only">본문 바로가기</p><span class="sr-only">새 창 열림</span>',
            ["감사합니다"], decoy=True)
        add("post/notice_adult_health.html", "성인 건강검진 및 성인병 예방 안내",
            "<p>만 40세 이상 성인 대상 국가건강검진 안내. 성인병(고혈압·당뇨) 예방 수칙을 확인하세요.</p>"
            '<div class="hidden-nav" style="display:none"><a href="about.html">기관소개</a><a href="index.html">공지</a></div>',
            [], decoy=True)

        # ----- 요강 4종 (official) -----
        # OFFSCREEN
        i1 = self.nid()
        off1 = (f'<span id="{i1}" style="display:none">{"안전놀이터 추천 먹튀검증 완료 가입코드 7777" if not v else "메이저놀이터 추천 먹튀 없는 토토사이트 가입머니 지급"}</span>')
        i2 = self.nid()
        off2 = f'<p id="{i2}" class="visually-hidden">{"바카라 온라인카지노 첫충 30% 매충 10%" if not v else "라이브카지노 슬롯사이트 첫충 50% 꽁머니"}</p>'
        head_off = '<style>.visually-hidden{position:absolute;left:-9999px}</style>' if not v else \
                   '<style>.visually-hidden{position:absolute;top:-5000px;left:0}</style>'
        i3 = self.nid()
        off3 = f'<span id="{i3}" style="font-size:0">{"출장안마 출장마사지 24시 전국" if not v else "조건만남 애인대행 전국 출장"}</span>'
        i4 = self.nid()
        off4 = f'<div id="{i4}" style="font-size:1px;line-height:0">{"무직자대출 당일대출 신불자대출 100% 승인" if not v else "일수대출 개인돈 월변 무서류 당일"}</div>'
        i5 = self.nid()
        off5 = f'<span id="{i5}" style="position:absolute;left:-9999px">{"토토사이트 안전놀이터 보증업체" if not v else "검증업체 추천 사설토토 입플 이벤트"}</span>'
        i5b = self.nid()
        off5b = f'<span id="{i5b}" style="text-indent:-9999px;display:block">{"슬롯사이트 가입머니 3만" if not v else "파워볼 사다리게임 꽁머니 5만"}</span>'
        add("post/post_budget.html", "2026년 예산 집행 현황 공개",
            f"<p>2026년 상반기 예산 집행 현황을 공개합니다.{off1}</p><p>세부 내역은 첨부 참조.</p>{off2}<p>문의: 재정과{off3}</p>{off4}",
            [f"잘 봤습니다.{off5}", f"공개 감사합니다{off5b}"], head=head_off)
        for eid in (i1, i2, i3, i4, i5, i5b):
            self.label("post/post_budget.html", eid, "OFFSCREEN", "도박" if eid in (i1, i2, i5, i5b) else "성인" if eid == i3 else "불법금융")

        # TRANSPARENT
        t1 = self.nid()
        tr1 = f'<span id="{t1}" style="color:#ffffff">{"먹튀검증 안전놀이터 상담 텔레그램 @promo_777" if not v else "먹튀 없는 메이저놀이터 코드 VIP 텔레그램 @bet_777"}</span>'
        t2 = self.nid()
        tr2 = f'<span id="{t2}" style="color:transparent">{"성인야동 무료야동 사이트" if not v else "성인방송 웹캠채팅 19금"}</span>'
        t3 = self.nid()
        tr3 = f'<p id="{t3}" style="opacity:0">{"카드깡 소액결제현금화 정보이용료현금화" if not v else "상품권현금화 휴대폰소액결제 즉시 입금"}</p>'
        t4 = self.nid()
        bg = "#f0f0f0" if not v else "rgb(238, 238, 238)"
        tr4 = f'<div class="box" style="background-color:{bg};padding:8px">안내 박스<span id="{t4}" style="color:{bg}">{"에볼루션카지노 바카라 사이트 추천" if not v else "홀덤사이트 바카라 보증업체"}</span></div>'
        t5 = self.nid()
        tr5 = f'<span id="{t5}" style="color:rgb(255,255,255)">{"오피사이트 키스방 휴게텔 정보" if not v else "안마방 풀싸롱 핸플 정보"}</span>'
        add("post/post_recruit.html", "기간제 근로자 채용 공고",
            f"<p>행복시 기간제 근로자를 아래와 같이 모집합니다.{tr1}</p><p>접수기간: 10.1 ~ 10.15{tr2}</p>{tr3}{tr4}",
            [f"지원 자격 문의드립니다.{tr5}", "접수 완료했습니다."])
        self.label("post/post_recruit.html", t1, "TRANSPARENT", "도박")
        self.label("post/post_recruit.html", t2, "TRANSPARENT", "성인")
        self.label("post/post_recruit.html", t3, "TRANSPARENT", "불법금융")
        self.label("post/post_recruit.html", t4, "TRANSPARENT", "도박")
        self.label("post/post_recruit.html", t5, "TRANSPARENT", "성인")

        # HOMOGLYPH (가시 텍스트)
        h1 = self.nid()
        hg1 = f'<span id="{h1}">{"ｍｅｇａ－ＢＥＴ 첫충 30％ 지급" if not v else "ＶＩＰ－ＢＥＴ 매충 20％ 입플"}</span>'
        h2 = self.nid()
        hg2 = f'<span id="{h2}">{"саsino 바카라 추천 (키릴 с)" if not v else "온라인 cаsinо 슬롯머신 체험"}</span>'
        h3 = self.nid()
        hg3 = f'<span id="{h3}">{"t0t0 사이트 추천 안전 놀이터" if not v else "T0T0 메이저 놀이터 추천"}</span>'
        h4 = self.nid()
        hg4 = f'<span id="{h4}">{"ｃａｓｉｎｏ 사이트 입장" if not v else "ｂａｃｃａｒａｔ 라이브 입장"}</span>'
        add("post/post_festival.html", "행복시 가을 축제 개최 안내",
            f"<p>10월 마지막 주 행복공원에서 가을 축제가 열립니다.</p><p>주차 안내: 공영주차장 이용 {hg1}</p><p>{hg2}</p>",
            [f"기대됩니다! {hg3}", "주차 공간 충분한가요?", f"{hg4}"])
        for eid in (h1, h2, h3, h4):
            self.label("post/post_festival.html", eid, "HOMOGLYPH", "도박")

        # JAMO
        j1 = self.nid()
        jm1 = f'<span id="{j1}">{"ㅋㅏㅈㅣㄴㅗ ㅂㅗㄴㅓㅅㅡ 코드 LUCKY7" if not v else "ㅂㅏㅋㅏㄹㅏ ㅅㅏㅇㅣㅌㅡ 코드 WIN9"}</span>'
        j2 = self.nid()
        jm2 = f'<p id="{j2}">{"ㅌㅗㅌㅗ ㅅㅏㅇㅣㅌㅡ 추천 ㅁㅓㄱㅌㅟ 없는 곳" if not v else "ㅅㅏㅅㅓㄹㅌㅗㅌㅗ ㅇㅏㄴㅓㅅㅏㅇ 지급 ㄲㅗㅇㅁㅓㄴㅣ"}</p>'
        j3 = self.nid()
        jm3 = f'<span id="{j3}">{"바ㅋㅏ라 추천 가입 ㅁㅓㄴㅣ 지급" if not v else "슬ㄹㅗㅅ ㅅㅏㅇㅣㅌㅡ 첫충 50%"}</span>'
        j4 = self.nid()
        jm4 = f'<span id="{j4}">{"ㅊㅜㄹㅈㅏㅇㅇㅏㄴㅁㅏ 24시 전국" if not v else "ㅈㅗㄴㄴㅓㄴㅁㅏㄴㄴㅏㅁ 전국 ㅇㅗㅍㅣ"}</span>'
        add("post/post_water.html", "상수도 요금 고지서 발송 안내",
            f"<p>10월분 상수도 요금 고지서가 발송되었습니다.</p>{jm2}<p>납부 기한: 10/31 {jm1}</p>",
            ["납부했습니다", f"ㅋㅋ 벌써 10월이네요 {jm3}", f"{jm4}"])
        self.label("post/post_water.html", j1, "JAMO", "도박")
        self.label("post/post_water.html", j2, "JAMO", "도박")
        self.label("post/post_water.html", j3, "JAMO", "도박")
        self.label("post/post_water.html", j4, "JAMO", "성인")

        # 중첩: 숨김 + 자모 / 숨김 + 호모글리프 → 같은 요소에 2개 라벨
        c1 = self.nid()
        cb1 = f'<span id="{c1}" style="display:none">{"ㅌㅗㅌㅗ ㅅㅏㅇㅣㅌㅡ 가입코드 777" if not v else "ㅋㅏㅈㅣㄴㅗ ㅅㅏㅇㅣㅌㅡ 꽁머니"}</span>'
        c2 = self.nid()
        cb2 = f'<span id="{c2}" style="color:#fff">{"ｔｏｔｏ 안전놀이터 보증" if not v else "ｃａｓｉｎｏ 바카라 보증업체"}</span>'
        add("post/post_parking.html", "공영주차장 요금 조정 안내",
            f"<p>11월부터 공영주차장 요금이 조정됩니다.{cb1}</p><p>자세한 내용은 주차관리과로 문의하세요.{cb2}</p>", ["확인했습니다"])
        self.label("post/post_parking.html", c1, "OFFSCREEN", "도박")
        self.label("post/post_parking.html", c1, "JAMO", "도박")
        self.label("post/post_parking.html", c2, "TRANSPARENT", "도박")
        self.label("post/post_parking.html", c2, "HOMOGLYPH", "도박")

        # 외부 CSS 파일(클래스 규칙)·상속·transform/margin offscreen·rgba/hsla/8자리 hex 투명·근사색 + 하드 네거티브
        g1, g2, g3, g4, g5, g6, g7 = (self.nid() for _ in range(7))
        near = "#fdfdfd" if not v else "#fcfcfc"
        site_css = f"""/* 사이트 공통 */
@import url("theme.css");
.wrap-dark{{background:#222;color:#fff;padding:8px}}
.skip{{position:absolute;left:0;top:0;transform:translateX({"-9999px" if not v else "-12000px"})}}
.push{{position:relative;{"margin-left:-9999px" if not v else "margin-top:-8000px"}}}
.ghost{{color:{"rgba(0,0,0,0)" if not v else "hsla(0, 0%, 100%, 0)"}}}
.faint{{color:{near}}}
.alpha{{color:{"#00000000" if not v else "#ffffff05"}}}
.tabpane{{display:none}}
.tabpane.active{{display:block}}
@media print{{.no-print{{display:none}}}}
.hero{{background:url(bg.png) no-repeat;color:#fff;padding:20px}}
"""
        theme_css = ".theme-hide{" + ("position:absolute;top:-6000px" if not v else "font-size:0") + "}\n"
        self.files["css/site.css"] = site_css
        self.files["css/theme.css"] = theme_css
        add("post/post_notice_css.html", "정보화 교육 수강생 모집",
            f'<p>하반기 정보화 교육(스마트폰 활용) 수강생을 모집합니다.</p>'
            f'<p class="no-print">불법 토토사이트 광고 신고는 1336, 인쇄 시 이 안내는 제외됩니다.</p>'          # 인쇄 전용 display:none → 4종 아님
            f'<div class="hero"><span>{"토토사이트 불법광고 신고 안내" if not v else "카지노사이트 불법광고 신고 안내"} (배경 이미지 위 흰 글씨)</span></div>'   # 배경 이미지 → TRANSPARENT 아님
            f'<div class="wrap-dark">야간 교육 안내: 매주 화·목 19시 <span style="color:#fff">문의 정보화담당관</span></div>'
            f'<a class="skip" id="{g1}" href="https://{"kk-bet" if not v else "zz-bet"}.{"top" if not v else "xyz"}">{"안전놀이터 먹튀검증 토토사이트" if not v else "메이저놀이터 검증업체 사설토토"}</a>'
            f'<p class="push" id="{g2}">{"바카라 온라인카지노 첫충 이벤트" if not v else "라이브카지노 슬롯사이트 매충 이벤트"}</p>'
            f'<span class="ghost" id="{g3}">{"출장안마 출장마사지 24시" if not v else "조건만남 애인대행 24시"}</span>'
            f'<span class="faint" id="{g4}">{"무직자대출 당일대출 100% 승인" if not v else "신불자대출 일수대출 즉시 승인"}</span>'
            f'<div class="alpha" id="{g5}">{"카드깡 소액결제현금화" if not v else "정보이용료현금화 상품권현금화"}</div>'
            f'<div class="tabpane"><p>교육 장소: 시청 3층 전산교육장</p></div>'
            f'<div class="tabpane active"><p>준비물: 본인 스마트폰</p></div>'
            f'<div class="tabpane" id="{g6}"><p>{"꽁머니 가입머니 토토사이트 추천" if not v else "입플 첫충 메이저사이트 추천"}</p></div>'   # 숨긴 탭 안: 부모 display:none 상속
            f'<span class="theme-hide" id="{g7}">{"무료 슬롯 체험 바로가기" if not v else "무료 바카라 체험 카지노 보너스"}</span>',
            ["감사합니다"], head='<link rel="stylesheet" href="../css/site.css">')
        self.label("post/post_notice_css.html", g1, "OFFSCREEN", "도박")
        self.label("post/post_notice_css.html", g2, "OFFSCREEN", "도박")
        self.label("post/post_notice_css.html", g3, "TRANSPARENT", "성인")
        self.label("post/post_notice_css.html", g4, "TRANSPARENT", "불법금융")
        self.label("post/post_notice_css.html", g5, "TRANSPARENT", "불법금융")
        self.label("post/post_notice_css.html", g7, "OFFSCREEN", "도박")
        self.label("post/post_notice_css.html", g6, "OFFSCREEN", "도박", note="부모 display:none(외부 CSS 클래스) 상속")

        # iframe(같은 도메인) 안 OFFSCREEN + 외부 iframe 안 TRANSPARENT
        w1 = self.nid()
        self.files["widget/notice.html"] = f"""<!doctype html><html><head><meta charset="utf-8"><title>위젯</title></head><body>
<div class="wrap"><p>오늘의 날씨: 맑음</p><span id="{w1}" class="hidden-link" style="display:none">{"무료 슬롯 체험 바로가기 슬롯사이트" if not v else "무료 바카라 체험 카지노사이트 바로가기"}</span></div></body></html>"""
        self.label("widget/notice.html", w1, "OFFSCREEN", "도박", page="post/post_weather.html")
        e1 = self.nid()
        self.files["ext/banner.html"] = f"""<!doctype html><html><head><meta charset="utf-8"><title>배너</title></head><body>
<div class="banner"><img alt="배너" src="data:,"><span id="{e1}" style="color:#ffffff">{"온라인카지노 바카라 첫충 이벤트" if not v else "슬롯사이트 꽁머니 첫충 이벤트"}</span></div></body></html>"""
        self.label("ext/banner.html", e1, "TRANSPARENT", "도박", page="post/post_weather.html")
        add("post/post_weather.html", "기상 특보 대응 안내",
            f'<p>기상 특보 발령 시 행동요령을 안내합니다.</p><iframe src="../widget/notice.html" width="300" height="80"></iframe>'
            f'<iframe src="{p("ext/banner.html")}" width="300" height="80"></iframe>', ["감사합니다"])

        # EUC-KR 페이지 (cp949) : TRANSPARENT
        k1 = self.nid()
        euc = self.page("구인구직 게시판",
                        f'<h2 class="title">지역 일자리 정보</h2><div class="article-body"><p>지역 기업 채용 정보를 안내합니다.'
                        f'<span id="{k1}" style="color:#fff">{"고수익알바 유흥알바 당일 지급" if not v else "유흥알바 고수익알바 숙식 제공"}</span></p></div>')
        euc = euc.replace('<meta charset="utf-8">', '<meta http-equiv="Content-Type" content="text/html; charset=euc-kr">')
        self.files["post/post_jobs.html"] = euc.encode("cp949", errors="replace")
        posts.append(("post/post_jobs.html", "지역 일자리 정보"))
        self.label("post/post_jobs.html", k1, "TRANSPARENT", "기타")

        # ----- 추가 유형(ETC) -----
        x1 = self.nid()
        x2 = self.nid()
        x3 = self.nid()
        x4 = self.nid()
        x5 = self.nid()
        x6 = self.nid()
        x7 = self.nid()
        x8 = self.nid()
        x9 = self.nid()
        tld = "top" if not v else "xyz"
        b64 = base64.b64encode((f'<a href="http://casino-vip.{tld}">온라인 카지노</a>' if not v else f'<a href="http://slot-vip.{tld}">슬롯사이트</a>').encode()).decode()
        add("post/post_library.html", "시립도서관 휴관 안내",
            f'<p id="{x1}">정기 점검으로 11/3 휴관합니다.<!-- <a href="http://bet-{tld}777.{tld}">카지노사이트</a> 토토 --></p>'
            f'<p id="{x2}"><noscript><a href="http://{"casino-vip" if not v else "slot-vip"}.{tld}">안전놀이터 추천</a></noscript>휴관 중 반납은 무인반납기를 이용하세요.</p>'
            f'<iframe id="{x3}" src="{p("ext/px.html")}" width="1" height="1"></iframe>'
            f'<marquee id="{x4}">{"꽁머니 3만 지급 토토사이트" if not v else "가입머니 5만 지급 슬롯사이트"} http://{"win777" if not v else "luck888"}.{tld}</marquee>'
            f'<span id="{x5}" style="visibility:hidden">{"출장안마 전국 24시" if not v else "출장마사지 전국 24시"} http://{"anma24" if not v else "massage24"}.{tld}</span>'
            f'<div id="{x6}" hidden>{"무직자대출 당일대출" if not v else "신불자대출 당일 승인"} 상담 https://t.me/{"loan_fast" if not v else "money_now"}</div>'
            f'<script id="{x7}">document.write(\'<a href="http://{"bet365x" if not v else "bet777y"}.{tld}">{"바카라 추천" if not v else "슬롯 추천"}</a>\');</script>'
            f'<script id="{x8}">var s=atob("{b64}");eval("document.body.innerHTML+=s");</script>'
            f'<p id="{x9}">점검 문의: 도서관운영팀 <a href="http://{"www.library.go.kr" if not v else "www.nl.go.kr"}" >도서관 안내</a></p>',
            [])
        for eid, name, cat in ((x1, "HTML_COMMENT", "도박"), (x2, "NOSCRIPT", "도박"), (x3, "HIDDEN_IFRAME", "기타"),
                               (x4, "HIDDEN_MARQUEE", "도박"), (x5, "HIDDEN_VISIBILITY_HIDDEN", "성인"),
                               (x6, "HIDDEN_HIDDEN_ATTR", "불법금융"), (x7, "SCRIPT_INJECTION", "도박"),
                               (x8, "SCRIPT_INJECTION", "도박")):
            self.label("post/post_library.html", eid, "ETC", cat, extra=name)

        y1, y2, y3, y4, y5, y6 = (self.nid() for _ in range(6))
        add("post/post_culture.html", "문화센터 가을학기 수강생 모집",
            f'<p>가을학기 강좌를 모집합니다.</p><p id="{y1}">강좌 안내 → <a href="http://{"kk8282" if not v else "zz7979"}.{tld}">{"토토사이트 안전놀이터" if not v else "메이저놀이터 검증업체"}</a></p>'
            f'<p id="{y2}">신청: <a href="https://{"bit.ly" if not v else "han.gl"}/{"3xYzQ" if not v else "9kLmN"}">{"먹튀검증 안전 놀이터 바로가기" if not v else "꽁머니 이벤트 바로가기"}</a></p>'
            f'<p id="{y3}"><a href="http://{"casino-77" if not v else "slot-99"}.{tld}">www.happycity.go.kr</a> 공식 안내</p>',
            [f'<span id="{y4}">상담 문의 텔레그램 <a href="https://t.me/{"vip_bet" if not v else "vip_slot"}">@vip 바카라</a></span>',
             f'<span id="{y5}">토​토​사​이​트 추천 (제로폭 삽입) 먹​튀 없음 http://{"ttt" if not v else "sss"}{"123" if not v else "456"}.{tld}</span>',
             f'<div id="{y6}">추천 사이트 모음: <a href="http://a1.{tld}">1</a> <a href="http://b2.{tld}">2</a> <a href="http://c3.{tld}">3</a> '
             f'<a href="http://d4.{tld}">4</a> <a href="http://e5.{tld}">5</a> <a href="http://f6.{tld}">6</a></div>'])
        for eid, name, cat in ((y1, "SUSPICIOUS_TLD", "도박"), (y2, "SHORTENER", "도박"), (y3, "ANCHOR_MISMATCH", "기타"),
                               (y4, "MESSENGER", "도박"), (y5, "OBFUSCATION_INSERT", "도박"), (y6, "MASS_EXTERNAL_LINKS", "기타")):
            self.label("post/post_culture.html", eid, "ETC", cat, extra=name)

        # 클로킹: 일반 UA 에는 정상, 봇 UA/네이버 Referer 에는 숨김 링크 뭉치 (eval 서버가 .bot 파일로 응답)
        k1 = self.nid()
        normal_body = "<p>시민 제안 공모를 안내합니다. 접수: 10/20~11/5</p>"
        add("post/post_cloak.html", "시민 제안 공모 안내", normal_body, ["좋은 제안 많이 모이길"])
        bot_extra = (f'<div id="{k1}" style="position:absolute;left:-9999px">'
                     + " ".join(f'<a href="http://{w}.{tld}">{t}</a>' for w, t in (
                         (("bet-k1", "토토사이트"), ("cas-k2", "카지노사이트"), ("slot-k3", "슬롯사이트"), ("bac-k4", "바카라"))
                         if not v else (("mj-k1", "메이저놀이터"), ("ev-k2", "에볼루션카지노"), ("pb-k3", "파워볼"), ("hd-k4", "홀덤사이트"))))
                     + "</div>")
        self.files["post/post_cloak.html.bot"] = self.files["post/post_cloak.html"].replace("</body>", bot_extra + "</body>")
        self.label("post/post_cloak.html", k1, "ETC", "도박", extra="CLOAKING_OFFSCREEN")

        # 리다이렉트 페이지(목록에서 링크)
        self.files["ext/px.html"] = '<!doctype html><html><head><meta charset="utf-8"></head><body><a href="http://777.' + tld + '">go</a></body></html>'
        r1 = self.nid()
        r2 = self.nid()
        self.files["event/redirect.html"] = (f'<!doctype html><html><head><meta charset="utf-8"><title>이동</title>'
                                             f'<meta id="{r1}" http-equiv="refresh" content="0;url=http://{"go-casino" if not v else "go-slot"}.{tld}/"></head>'
                                             f'<body><p>잠시 후 이동합니다.</p><script id="{r2}">setTimeout(function(){{location.href="http://{"go-casino" if not v else "go-slot"}.{tld}/";}},100);</script></body></html>')
        self.label("event/redirect.html", r1, "ETC", "도박", extra="META_REFRESH")
        self.label("event/redirect.html", r2, "ETC", "도박", extra="JS_REDIRECT")

        # ----- 목록/페이지네이션/기관소개 -----
        self.rng.shuffle(posts)
        half = (len(posts) + 1) // 2
        for i, chunk in enumerate((posts[:half], posts[half:])):
            rows = "".join(f'<tr><td class="num">{n + 1}</td><td class="title"><a href="{path}">{title}</a></td><td class="date">2026-10-{(n % 28) + 1:02d}</td></tr>'
                           for n, (path, title) in enumerate(chunk))
            nav = '<div class="paging"><a href="index.html">1</a> <a href="list2.html">2</a></div>'
            extra_rows = ""
            if i == 1:
                extra_rows = '<tr><td class="num">99</td><td class="title"><a href="event/redirect.html">이벤트 바로가기</a></td><td class="date">2026-10-30</td></tr>'
            body = f'<h2>공지사항</h2><table class="board-list"><tr><th>번호</th><th>제목</th><th>날짜</th></tr>{rows}{extra_rows}</table>{nav}'
            self.files["index.html" if i == 0 else "list2.html"] = self.page("공지사항", body)
        self.files["about.html"] = self.page("기관소개", "<h2>기관소개</h2><p>행복시청은 시민의 행복을 위해 일합니다.</p>")
        self.decoys += ["index.html", "list2.html", "about.html"]

    def write(self, root: Path) -> None:
        for rel, content in self.files.items():
            path = root / self.name / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content, encoding="utf-8")


def generate(root: Path, port: int) -> dict:
    labels: list[dict] = []
    decoys: dict[str, list[str]] = {}
    for name, seed in (("dev", 1), ("holdout", 2)):
        s = Site(name, port, seed)
        s.build()
        s.write(root)
        labels += s.labels
        decoys[name] = s.decoys
    data = {"port": port, "labels": labels, "decoys": decoys,
            "schema": "labels[]: set, page(최상위 페이지), doc(요소가 실제로 있는 문서), element_id, technique(HOMOGLYPH|JAMO|TRANSPARENT|OFFSCREEN|ETC), category, extra_name"}
    (root / "labels.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    d = generate(HERE, a.port)
    print(f"labels: {len(d['labels'])}")
