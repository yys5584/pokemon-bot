# database/ 주의사항

## 핵심 규칙
- **스키마 변경 시 반드시 `schema.py`에 마이그레이션 추가** (운영 DB 직접 ALTER 금지)
- 커넥션은 `connection.py`의 풀에서 가져올 것
- 쿼리 함수는 항상 커넥션을 인자로 받거나 풀에서 가져오는 패턴 사용

## 파일 역할
- `queries.py`: 포켓몬, 유저, 칭호, 팀 등 메인 쿼리 (가장 큼)
- `battle_queries.py`: 배틀 로그, 분석, BP 관련
- `ranked_queries.py`: 랭크전 매칭, ELO, 시즌
- `schema.py`: CREATE TABLE + ALTER TABLE 마이그레이션
- `seed.py`: 초기 데이터 (포켓몬, 스킬 등)

## 주의
- `swap_teams`에 CHECK 제약 우회 로직 있음 (임시 NULL 설정)
- 대시보드 세션은 `dashboard_sessions` 테이블에 영속화
