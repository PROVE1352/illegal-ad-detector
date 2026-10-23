# GUI 스모크 판정 자체 검증용: 창을 띄우기 전에 예외로 죽는다(스모크가 FAIL 해야 정상).
raise RuntimeError("intentional startup failure")
