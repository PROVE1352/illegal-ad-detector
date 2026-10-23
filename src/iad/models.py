"""데이터 모델: 페이지, 근거, 탐지 결과."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Page:
    url: str
    html: str
    depth: int = 0
    status: int = 200
    parent_url: str | None = None
    is_iframe: bool = False
    external: bool = False          # 외부 도메인 iframe 등
    encoding: str = "utf-8"
    error: str | None = None
    top_url: str | None = None      # iframe 안 페이지면 최상위(부모) 페이지 URL
    frame_prefix: str = ""          # 'iframe[src="..."] >>> ' 누적 접두어

    @property
    def report_url(self) -> str:
        return self.top_url or self.url


@dataclass
class Evidence:
    rule: str          # 규칙 ID (예: hidden.display_none, keyword.gambling)
    detail: str        # 사람이 읽는 설명
    weight: float      # 가중치(+/-)
    group: str         # hidden / keyword / link / script / context


@dataclass
class Finding:
    page_url: str
    css_path: str
    tag: str
    snippet: str
    html: str
    evidence: list[Evidence] = field(default_factory=list)
    score: float = 0.0
    risk: str = "낮음"           # 높음 / 중간 / 낮음
    category: str = "기타"        # 도박 / 성인 / 불법금융 / 기타
    techniques: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    screenshot: str | None = None
    parent_url: str | None = None
    is_iframe: bool = False
    external: bool = False
    location: str = ""              # 요강 규칙 CSS 선택자(iframe >>> 포함)
    evidence_text: str = ""         # 정규화 전 원문
    official: list[str] = field(default_factory=list)   # HOMOGLYPH / JAMO / TRANSPARENT / OFFSCREEN
    extra_names: list[str] = field(default_factory=list)  # ETC 유형 이름
    frame_url: str | None = None    # iframe 안이면 실제 iframe 문서 URL

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    def has_group(self, group: str) -> bool:
        return any(e.group == group for e in self.evidence)

    def add(self, rule: str, detail: str, weight: float, group: str) -> None:
        self.evidence.append(Evidence(rule, detail, weight, group))
