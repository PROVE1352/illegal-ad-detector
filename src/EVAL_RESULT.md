# 평가 결과 (2026-10-23 12:48:00)

- 명령: `uv run python src/eval.py` · 깊이 3 · 최대 300페이지 · 포트 8765
- 채점 단위: url + location + technique (요강 붙임4). location 은 DOM 에서 해석해 같은 요소인지 비교.
- 정확도 = 정탐 / result.json 전체 검출 단위(요강 '정답 추출 정확도' 정의와 동일).

| 세트 | 정답 | 검출 | 정탐 | 오탐 | 정확도 | 재현율 | F1 | 페이지 | 소요(초) |
|---|---|---|---|---|---|---|---|---|---|
| dev | 49 | 49 | 49 | 0 | 1.0 | 1.0 | 1.0 | 30 | 0.23 |
| holdout | 49 | 49 | 49 | 0 | 1.0 | 1.0 | 1.0 | 30 | 0.16 |

## 기법별 재현율 (result.json)

| 세트 | HOMOGLYPH | JAMO | TRANSPARENT | OFFSCREEN |
|---|---|---|---|---|
| dev | 11/11 | 7/7 | 11/11 | 20/20 |
| holdout | 11/11 | 7/7 | 11/11 | 20/20 |

## 추가 탐지 (result_extra.json, 본심사용)

| 세트 | ETC 정답 | 보고 | 적중 | 재현율 | 오탐(라벨 없음) |
|---|---|---|---|---|---|
| dev | 16 | 17 | 16 | 1.0 | 1 |
| holdout | 16 | 17 | 16 | 1.0 | 1 |

## dev 상세

### result.json 오탐 0건
### result.json 미탐 0건
### result_extra.json 미탐 0건
### result_extra.json 오탐 1건
- dev/post/post_library.html `iframe[src="http://localhost:8765/dev/ext/px.html"] >>> a` — numeric_domain+suspicious_tld / 분류=의심 링크 / 위험도=낮음 / 점수=4.5 — “go  [근거: 의심 TLD .top (777.top); 숫자가 많은 도메인 (777.top)]”
### 정상 문서(오탐 유도) 적중: 0건

## holdout 상세

### result.json 오탐 0건
### result.json 미탐 0건
### result_extra.json 미탐 0건
### result_extra.json 오탐 1건
- holdout/post/post_library.html `iframe[src="http://localhost:8765/holdout/ext/px.html"] >>> a` — numeric_domain+suspicious_tld / 분류=의심 링크 / 위험도=낮음 / 점수=4.5 — “go  [근거: 의심 TLD .xyz (777.xyz); 숫자가 많은 도메인 (777.xyz)]”
### 정상 문서(오탐 유도) 적중: 0건
