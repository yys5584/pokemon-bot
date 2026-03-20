# TGPoke Bot

Telegram 포켓몬 수집/배틀/거래 봇. python-telegram-bot 기반, PostgreSQL, Oracle Cloud VM 운영.

## Repo Map

```
main.py                 # 봇 엔트리포인트 (lifecycle만, ~300줄)
config.py               # 모든 설정값, 커스텀 이모지 ID, 칭호 정의, 코스트
handlers/               # 텔레그램 메시지/콜백 핸들러
  _register.py          #   핸들러 등록 (register_all_handlers)
  _common.py            #   공통 유틸 (중복 콜백 방지)
  admin.py              #   관리자 명령 (강제스폰, 대회시작 등)
  battle.py             #   배틀 도전/수락/결과, 파트너
  battle_team.py        #   팀 편집/등록/해제/스왑
  battle_shop.py        #   BP 상점, 전적, 티어
  battle_ranked.py      #   랭크전 + 자동랭크전
  battle_yacha.py       #   야차 베팅배틀
  dm_pokedex.py         #   도감, 내포켓몬
  dm_title.py           #   칭호 목록/선택/장착
  dm_status.py          #   상태창, 감정, 상성표
  dm_market.py          #   거래소 DM
  dm_fusion.py          #   합성 DM
  dm_trade.py           #   교환 DM
  dm_camp.py            #   캠프 시스템 DM
  group.py              #   그룹 채팅 명령
  tournament.py         #   대회 참가 (ㄷ)
  tutorial.py           #   튜토리얼
jobs/                   # 스케줄러 작업
  scheduler.py          #   register_all_jobs (모든 job 등록)
  kpi_report.py         #   KPI 일일/주간 리포트
  midnight.py           #   자정 리셋, 칭호 버프, 구독 지급
  ranked_jobs.py        #   랭크전 주간리셋/디케이
services/               # 비즈니스 로직 (핸들러에서 분리)
  battle_service.py     #   배틀 엔진 (_resolve_battle, _hp_bar)
  spawn_service.py      #   스폰/포획
  tournament_service.py #   토너먼트 진행
  ranked_service.py     #   랭크전 매칭
  market_service.py     #   거래소
  fusion_service.py     #   합성
  camp_service.py       #   캠프 비즈니스 로직
database/               # PostgreSQL 쿼리 레이어
  queries.py            #   핵심 쿼리 (Users, Pokemon CRUD)
  battle_queries.py     #   배틀 관련 쿼리
  ranked_queries.py     #   랭크전 쿼리
  spawn_queries.py      #   스폰/포획/아케이드 쿼리
  title_queries.py      #   칭호 쿼리
  stats_queries.py      #   통계/랭킹 쿼리
  kpi_queries.py        #   KPI 스냅샷/리포트 쿼리
  item_queries.py       #   가챠/아이템 쿼리
  mission_queries.py    #   일일 미션 쿼리
  camp_queries.py       #   캠프 쿼리
  schema.py             #   테이블 생성/마이그레이션
  connection.py         #   DB 커넥션 풀
models/                 # 포켓몬 데이터 정의 (스탯, 스킬, 타입)
utils/                  # 유틸리티
  card_generator.py     #   기본 카드 (스폰/라인업/챔피언/도감)
  battle_card_generator.py # 배틀카드/스킬GIF/던전GIF
  battle_calc.py        #   배틀 계산 (데미지, IV, 타입상성)
  helpers.py            #   공통 헬퍼 (이모지, 포맷팅)
  i18n.py               #   다국어 시스템
  parse.py              #   텍스트 파싱
  honorific.py          #   한국어 조사/존칭
dashboard/              # 웹 대시보드 (aiohttp, tgpoke.com)
  server.py             #   앱 설정, 미들웨어, 라우트 등록
  api_my.py             #   내 포켓몬/팀/도감 API
  api_advisor.py        #   AI 어드바이저 (Gemini)
  api_admin.py          #   관리자 패널 API
  api_market.py         #   거래소/결제 API
  api_analytics.py      #   분석/KPI API
  templates/index.html  #   SPA 프론트엔드
tests/                  # pytest 테스트
assets/                 # 포켓몬 이미지, 스티커, 이모지 원본
scripts/                # 일회성 스크립트 (패치노트, 마이그레이션)
docs/                   # 설계 문서
```

## Rules

### 필수
- 모든 시간은 **KST (UTC+9)** 기준
- 커스텀 이모지 사용 시 반드시 `parse_mode="HTML"`
- 커스텀 이모지 형식: `<tg-emoji emoji-id="ID">fallback</tg-emoji>`
- InlineKeyboardButton 라벨, query.answer() 팝업은 커스텀 이모지 **불가** → 기본 이모지 사용
- DB 스키마 변경 시 `database/schema.py`에 마이그레이션 추가

### 금지
- **배포/푸시/머지를 사용자 확인 없이 절대 하지 말 것**
- **봇 재시작을 사용자 확인 없이 절대 하지 말 것**
- `config.py`의 이모지 ID를 임의로 변경하지 말 것

### 컨벤션
- 언어: 한국어
- 브랜치: `dev` (개발/배포), `main` (안정)
- 커밋 메시지: 한국어 또는 영어, `feat:/fix:/chore:` 접두사

## Infra

| 항목 | 값 |
|------|-----|
| VM | 158.180.93.94 (ubuntu) |
| SSH 키 | 회사: `./oracle_vm`, 집: `~/.ssh/oracle_vm` |
| 봇 재시작 | `sudo systemctl restart pokemon-bot` |
| 로그 | `sudo journalctl -u pokemon-bot -f` |
| 대시보드 | https://tgpoke.com (port 8080, Cloudflare tunnel) |
| GitHub | https://github.com/yys5584/pokemon-bot |

## Commands

```bash
# 프리뷰 대시보드 (로컬)
python dashboard/run_preview.py    # port 8090

# 배포
ssh -i oracle_vm ubuntu@158.180.93.94
cd ~/pokemon-bot && git pull origin dev && sudo systemctl restart pokemon-bot
```
