# 개발 주의사항 (dev.md)

이 문서는 개발 시 반드시 지켜야 할 기술적 제약사항을 정리한 것.
새로운 실수/교훈이 생기면 여기에 추가할 것.

---

## DB (Supabase + asyncpg)

### statement_cache_size = 0 유지 (절대 변경 금지)
- Supabase는 **PgBouncer (transaction mode)**를 사용
- PgBouncer는 요청마다 다른 DB 연결로 라우팅함
- prepared statement 캐시를 켜면 "이 질문 모르는데?" 에러 발생
- **`statement_cache_size`는 반드시 0으로 유지**
- 참고: 직접 PostgreSQL에 연결하는 경우에만 캐시 사용 가능

### DB 테이블명
- 포켓몬 마스터 데이터: `pokemon_master` (NOT "pokemon")
- 유저 보유 포켓몬: `user_pokemon`

### Supabase Free Tier 제한
- 백업 없음 — destructive 작업 절대 주의
- 연결 수 제한 있음 — `max_size=10` 초과 금지

---

## VM (Oracle Cloud Free Tier)

### 스펙 제한
- 1 OCPU, 1GB RAM (VM.Standard.E2.1.Micro)
- numpy 등 무거운 라이브러리 설치 시 메모리 부족 가능
- 새 패키지 추가 전 `pip install` 테스트 필수

### 서비스 관리
- 봇: `sudo systemctl restart pokemon-bot`
- 대시보드: 봇과 같은 프로세스 (별도 재시작 불필요)
- Cloudflare Tunnel: `cloudflared.service`

---

## Telegram Bot API

### parse_mode="HTML" 필수인 경우
- 커스텀 이모지 (`<tg-emoji>`) 사용하는 모든 메시지
- `send_message`, `send_photo`, `reply_text` 모두 해당
- 빠뜨리면 태그가 텍스트로 노출됨

### DM vs 그룹 필터
- `dm` 필터와 `group` 필터는 상호 배타적
- 같은 명령어라도 DM/그룹 핸들러 따로 등록 필요

---

## 코드 패턴

### 배포 전 체크리스트
1. `python -c "import py_compile; py_compile.compile('파일.py', doraise=True)"` 문법 검증
2. `git push` → VM `git pull` → `systemctl restart`
3. `journalctl -u pokemon-bot` 로그 확인
4. HTML 변경은 재시작 불필요, Python 변경은 재시작 필수

### 이벤트 캐시
- 이벤트 캐시는 30초마다 갱신
- 스폰 스케줄은 봇 재시작 시에만 반영
