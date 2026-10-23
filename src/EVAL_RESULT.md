# 평가 결과 (2026-10-23 12:20:48)

- 명령: `uv run python src/eval.py` · 깊이 3 · 최대 300페이지 · 포트 53001
- 채점 단위: url + location + technique (요강 붙임4). location 은 DOM 에서 해석해 같은 요소인지 비교.
- 정확도 = 정탐 / result.json 전체 검출 단위(요강 '정답 추출 정확도' 정의와 동일).

| 세트 | 정답 | 검출 | 정탐 | 오탐 | 정확도 | 재현율 | F1 | 페이지 | 소요(초) |
|---|---|---|---|---|---|---|---|---|---|
| dev | 38 | 38 | 38 | 0 | 1.0 | 1.0 | 1.0 | 28 | 0.2 |
| holdout | 38 | 38 | 38 | 0 | 1.0 | 1.0 | 1.0 | 28 | 0.14 |

## 기법별 재현율 (result.json)

| 세트 | HOMOGLYPH | JAMO | TRANSPARENT | OFFSCREEN |
|---|---|---|---|---|
| dev | 7/7 | 7/7 | 11/11 | 13/13 |
| holdout | 7/7 | 7/7 | 11/11 | 13/13 |

## 추가 탐지 (result_extra.json, 본심사용)

| 세트 | ETC 정답 | 보고 | 적중 | 재현율 | 오탐(라벨 없음) |
|---|---|---|---|---|---|
| dev | 17 | 17 | 17 | 1.0 | 0 |
| holdout | 17 | 17 | 17 | 1.0 | 0 |

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
