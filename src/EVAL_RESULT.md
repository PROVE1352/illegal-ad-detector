# 평가 결과 (2026-10-23 15:39:49)

- 명령: `uv run python src/eval.py` · 깊이 3 · 최대 300페이지 · 포트 8765
- 채점 단위: url + location + technique (요강 붙임4). location 은 DOM 에서 해석해 같은 요소인지 비교.
- 정확도 = 정탐 / result.json 전체 검출 단위(요강 '정답 추출 정확도' 정의와 동일).

| 세트 | 정답 | 검출 | 정탐 | 오탐 | 정확도 | 재현율 | F1 | 페이지 | 소요(초) |
|---|---|---|---|---|---|---|---|---|---|
| dev | 59 | 59 | 59 | 0 | 1.0 | 1.0 | 1.0 | 42 | 0.22 |
| holdout | 59 | 59 | 59 | 0 | 1.0 | 1.0 | 1.0 | 42 | 0.21 |

## 기법별 재현율 (result.json)

| 세트 | HOMOGLYPH | JAMO | TRANSPARENT | OFFSCREEN |
|---|---|---|---|---|
| dev | 12/12 | 10/10 | 13/13 | 24/24 |
| holdout | 12/12 | 10/10 | 13/13 | 24/24 |

## 추가 탐지 (result_extra.json, 본심사용)

| 세트 | ETC 정답 | 보고 | 적중 | 재현율 | 오탐(라벨 없음) |
|---|---|---|---|---|---|
| dev | 22 | 30 | 22 | 1.0 | 0 |
| holdout | 22 | 30 | 22 | 1.0 | 0 |

## 실사이트 정상 세트 (fixtures/realworld, 오프라인)

- 출처: https://www.mois.go.kr/frt/bbs/type010/commonSelectBoardList.do?bbsId=BBSMSTR_000000000008 (10쪽, 1회 수집) · 통과 조건: 4종 0건 · ETC ≤9 · 쪽당 CPU ≤1.0s
- 결과: 4종 0건 · ETC 0건 · 쪽당 CPU 0.231s(합계 2.31s, time.process_time, 이 머신 실측) → **PASS**

## dev 상세

### result.json 오탐 0건
### result.json 미탐 0건
### result_extra.json 미탐 0건
### result_extra.json 오탐 0건
### 정상 문서(오탐 유도) 적중: 0건

## holdout 상세

### result.json 오탐 0건
### result.json 미탐 0건
### result_extra.json 미탐 0건
### result_extra.json 오탐 0건
### 정상 문서(오탐 유도) 적중: 0건
