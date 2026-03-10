# handlers/ 주의사항

## 핵심 규칙
- 핸들러는 **텔레그램 I/O + UI 로직만** 담당. 비즈니스 로직은 services/로
- 커스텀 이모지 사용 시 반드시 `parse_mode="HTML"` 설정
- `InlineKeyboardButton` 라벨과 `query.answer()` 팝업에는 커스텀 이모지 **불가**

## 파일별 역할
- `admin.py`: 관리자 전용 (강제스폰, 대회시작, 아케이드). admin_id 체크 필수
- `battle.py`: 배틀, BP 상점, 팀 표시, 랭크전 UI (가장 큰 핸들러)
- `dm_pokedex.py`: 상태창, 도감, 칭호, 팀등록 (두 번째로 큰 핸들러)
- `group.py`: 그룹 채팅 명령 (ㅊ, ㅊㅊ, 스폰 등). 한글 명령은 MessageHandler 사용
- `tournament.py`: 대회 참가. `ㄷ` 명령

## 한글 명령어 주의
- `CommandHandler`는 한글 명령 지원 안 함 → `MessageHandler` + 필터 사용
- 예: 아레나등록, 대회시작 등은 MessageHandler
