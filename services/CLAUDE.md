# services/ 주의사항

## 핵심 규칙
- 서비스는 **비즈니스 로직만** 담당. 텔레그램 API 직접 호출 금지 (handlers에서 처리)
- `battle_service.py` 수정 시 → `tournament_service.py`, `ranked_service.py`에도 영향 확인

## 파일별 의존관계
```
battle_service.py ← tournament_service.py (토너먼트 배틀)
                  ← ranked_service.py (랭크전 배틀)
spawn_service.py  ← catch_service.py (포획)
evolution_service.py ← fusion_service.py (합성 시 진화 체크)
```

## 배틀 엔진
- `_resolve_battle()`: 턴 데이터 반환 (`turn_data` 리스트)
- 데미지 공식: 본가 스타일 (레벨, 공격, 방어, 타입상성, 자속보정)
- 코스트 제한: 팀 COST 18 이내 검증 필수

## 스폰
- 이로치 확률: 자연 10%, 아케이드 0.5%
- 마스터볼 사용자가 포획 시 하이퍼볼 환불 로직 있음
