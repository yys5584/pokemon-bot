# dashboard/ 주의사항

## 구조
- `server.py`: Flask 메인 서버 (API + 페이지 라우팅)
- `templates/index.html`: SPA 프론트엔드 (전체 UI가 이 파일 하나)
- `run_preview.py`: 로컬 프리뷰 서버 (port 8090, 목업 데이터)
- `run_standalone.py`: 독립 실행 서버

## 주의
- `index.html`이 매우 큼 (5000줄+). CSS, JS, HTML 모두 포함된 단일 파일
- 텔레그램 로그인 위젯 사용 → 프리뷰에서는 로그인 테스트 불가
- 세션은 `dashboard_sessions` PostgreSQL 테이블에 영속화
- Cloudflare tunnel로 tgpoke.com에 연결 (port 8080)

## 게시판
- 공지사항: 관리자만 글쓰기 가능
- 커뮤니티: 로그인 유저 글쓰기 가능
- 딥링킹: `/board/notice`, `/board/community`, `/board/post/{id}`
