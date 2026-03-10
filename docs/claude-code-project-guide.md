# Claude Code 프로젝트 구조 가이드

> Claude Code를 챗봇이 아닌 **프로젝트에 상주하는 시니어 엔지니어**처럼 쓰는 방법

---

## 목차
1. [왜 구조가 필요한가](#1-왜-구조가-필요한가)
2. [전체 구조 개요](#2-전체-구조-개요)
3. [CLAUDE.md — 프로젝트 북극성](#3-claudemd--프로젝트-북극성)
4. [.claude/skills/ — 재사용 가능한 전문가 모드](#4-claudeskills--재사용-가능한-전문가-모드)
5. [폴더별 CLAUDE.md — 위험지역 경고판](#5-폴더별-claudemd--위험지역-경고판)
6. [.claude/hooks/ — 자동 안전장치](#6-claudehooks--자동-안전장치)
7. [docs/ — 점진적 컨텍스트](#7-docs--점진적-컨텍스트)
8. [실전 적용 예시](#8-실전-적용-예시)
9. [자주 하는 실수](#9-자주-하는-실수)

---

## 1. 왜 구조가 필요한가

대부분의 사람들이 Claude Code를 이렇게 씁니다:

```
"이 버그 고쳐줘"
→ Claude가 코드를 읽고 → 수정하고 → 끝
```

이러면 **매 세션마다 같은 설명을 반복**해야 합니다:
- "우리 프로젝트는 이런 구조야"
- "이 파일은 건드리면 안 돼"
- "배포는 이렇게 해"
- "이 함수 수정하면 저기도 영향받아"

**프롬프트는 휘발성**입니다. 세션이 끝나면 사라집니다.
**구조는 영구적**입니다. 파일로 남아서 누구든, 언제든 같은 맥락을 공유합니다.

Claude에게 4가지를 항상 알려줘야 합니다:

| 요소 | 질문 | 해결하는 파일 |
|------|------|-------------|
| **WHY** | 이 시스템이 뭘 하는 거야? | `CLAUDE.md` |
| **WHERE** | 파일이 어디 있어? | `CLAUDE.md` (repo map) |
| **RULES** | 뭘 하면 안 돼? | `CLAUDE.md` + 폴더별 `CLAUDE.md` |
| **HOW** | 어떻게 작업해? | `.claude/skills/` |

---

## 2. 전체 구조 개요

```
my-project/
├── CLAUDE.md                    ← 프로젝트 북극성 (필수)
├── .claude/
│   ├── skills/                  ← 재사용 워크플로우
│   │   ├── deploy.md
│   │   ├── pr.md
│   │   └── custom-emoji.md
│   ├── hooks/                   ← 자동 안전장치
│   │   └── (hook 설정)
│   └── launch.json              ← 개발 서버 설정
├── docs/                        ← 상세 참고 문서
│   ├── architecture.md
│   └── game-design.md
├── src/
│   ├── auth/
│   │   └── CLAUDE.md            ← 위험 모듈 경고판
│   ├── database/
│   │   └── CLAUDE.md
│   └── ...
└── ...
```

---

## 3. CLAUDE.md — 프로젝트 북극성

프로젝트 루트에 놓는 **가장 중요한 파일**. Claude는 세션 시작 시 이 파일을 자동으로 읽습니다.

### 원칙
- **짧게 유지** (100줄 이내 권장). 너무 길면 중요한 내용을 놓침
- 지식 덤프가 아닌 **핵심 요약**
- 3가지만 담을 것: 목적(WHY), 파일맵(WHAT), 규칙+명령(HOW)

### 구조 템플릿

```markdown
# 프로젝트 이름

한 줄 설명: 이 프로젝트가 뭔지

## Repo Map
주요 디렉토리와 파일의 역할 (트리 형태)

## Rules
### 필수 — 항상 지켜야 할 것
### 금지 — 절대 하면 안 되는 것
### 컨벤션 — 코딩 스타일, 네이밍 등

## Commands
자주 쓰는 명령어 (빌드, 테스트, 배포 등)
```

### 좋은 예 vs 나쁜 예

**나쁜 예** (너무 김, 지식 덤프):
```markdown
# 프로젝트
우리 프로젝트는 2024년에 시작했고, React 18.2.0을 사용하며,
TypeScript 5.3을 쓰고, 상태관리는 Zustand를 쓰는데 이유는...
(300줄 계속...)
```

**좋은 예** (핵심만):
```markdown
# 프로젝트
React + TypeScript SPA. Zustand 상태관리.

## Repo Map
src/components/   # UI 컴포넌트
src/store/        # Zustand 스토어
src/api/          # API 클라이언트

## Rules
- 컴포넌트는 함수형만 사용
- API 호출은 반드시 src/api/ 경유
- 테스트 없이 PR 금지
```

---

## 4. .claude/skills/ — 재사용 가능한 전문가 모드

반복되는 작업 절차를 마크다운 파일로 정리해 놓는 곳.

### 왜 필요한가?
- 매번 "배포 어떻게 해?" 설명 안 해도 됨
- 팀원 간 **동일한 절차** 보장
- 실수 방지 (빠뜨리는 단계 없음)

### 실전 예시

#### `skills/deploy.md`
```markdown
# 배포 스킬
## 사전 조건
- 사용자 확인 필수
- 모든 변경사항 커밋 & 푸시 완료

## 절차
1. git status로 변경사항 확인
2. VM SSH 접속
3. git pull && 서비스 재시작
4. 로그 확인
```

#### `skills/code-review.md`
```markdown
# 코드 리뷰 스킬
## 체크리스트
- [ ] 보안 취약점 (SQL injection, XSS)
- [ ] 에러 핸들링
- [ ] 성능 이슈
- [ ] 기존 패턴과 일관성
```

#### `skills/add-api-endpoint.md`
```markdown
# API 엔드포인트 추가 스킬
1. routes/에 라우트 정의
2. controllers/에 핸들러 작성
3. services/에 비즈니스 로직
4. 테스트 작성
5. API 문서 업데이트
```

---

## 5. 폴더별 CLAUDE.md — 위험지역 경고판

특히 조심해야 하는 디렉토리에 작은 `CLAUDE.md`를 놓습니다.
Claude가 해당 폴더의 파일을 수정할 때 자동으로 참고합니다.

### 왜 필요한가?
루트 CLAUDE.md에 모든 주의사항을 쓰면 너무 길어집니다.
**위험한 곳에만 표지판**을 세워두는 개념입니다.

### 실전 예시

#### `database/CLAUDE.md`
```markdown
# database/ 주의사항
- 스키마 변경 시 반드시 마이그레이션 파일 작성
- 운영 DB 직접 ALTER 금지
- swap 로직에 CHECK 제약 우회 있음 (임시 NULL)
```

#### `services/CLAUDE.md`
```markdown
# services/ 주의사항
- battle_service 수정 → tournament, ranked에도 영향
- 서비스는 텔레그램 API 직접 호출 금지
```

#### `auth/CLAUDE.md`
```markdown
# auth/ 주의사항
- 토큰 만료 로직 수정 시 반드시 테스트
- 비밀번호 해싱 알고리즘 변경 금지
```

### 어디에 넣으면 좋은가?
| 폴더 | 넣어야 하는 이유 |
|------|---------------|
| `database/` | 스키마 변경은 되돌리기 어려움 |
| `auth/`, `billing/` | 보안/결제는 실수 비용이 높음 |
| `services/` | 파일 간 의존관계가 복잡함 |
| `infra/`, `deploy/` | 인프라 설정 실수는 서비스 장애 유발 |
| `migrations/` | 순서와 호환성이 중요 |

---

## 6. .claude/hooks/ — 자동 안전장치

Claude가 특정 행동을 할 때 **자동으로 실행**되는 스크립트.
사람이 "이거 했어?" 체크 안 해도 시스템이 강제합니다.

### 왜 필요한가?
- Claude가 규칙을 **깜빡해도** hook은 실행됨
- CLAUDE.md의 규칙은 "권고", hook은 "강제"
- 결정적(deterministic)이어야 하는 것들에 사용

### 설정 위치
`.claude/settings.json` 또는 `.claude/settings.local.json`

### 실전 예시

#### 코드 수정 후 자동 포맷팅
```json
{
  "hooks": {
    "afterEdit": {
      "command": "prettier --write {{file}}"
    }
  }
}
```

#### 특정 파일 수정 시 테스트 실행
```json
{
  "hooks": {
    "afterEdit": {
      "pattern": "services/**/*.py",
      "command": "pytest tests/ -x"
    }
  }
}
```

#### 위험 디렉토리 수정 차단
```json
{
  "hooks": {
    "beforeEdit": {
      "pattern": "auth/**",
      "command": "echo '⚠️ auth 디렉토리 수정은 확인이 필요합니다' && exit 1"
    }
  }
}
```

### Rules vs Hooks 사용 기준

| 상황 | Rules (CLAUDE.md) | Hooks |
|------|-------------------|-------|
| "PR 전에 테스트 돌려" | O | O (더 안전) |
| "한국어로 커밋 메시지 써" | O | X |
| "auth/ 수정 시 주의해" | O | O (차단 가능) |
| "배포 전 확인받아" | O | O (차단 가능) |
| "코드 포맷팅 맞춰" | X (깜빡할 수 있음) | O (자동) |

**원칙**: 깜빡하면 안 되는 것 → Hook, 판단이 필요한 것 → Rule

---

## 7. docs/ — 점진적 컨텍스트

CLAUDE.md에 다 쓰면 너무 길어지는 **상세 정보**를 여기에 놓습니다.
Claude는 필요할 때 이 파일들을 읽어옵니다.

### 넣으면 좋은 것들

| 파일 | 내용 |
|------|------|
| `docs/architecture.md` | 시스템 아키텍처 전체 그림 |
| `docs/adr/` | 아키텍처 결정 기록 (왜 X를 선택했는지) |
| `docs/game-design.md` | 게임 설계 문서 |
| `docs/api.md` | API 명세 |
| `docs/runbook.md` | 운영 매뉴얼 (장애 대응 등) |

### CLAUDE.md와의 관계
```
CLAUDE.md (항상 읽음)
├── "아키텍처 상세는 docs/architecture.md 참고"
├── "배틀 공식은 docs/battle-system.md 참고"
└── "게임 설계는 docs/game-design.md 참고"
```

Claude.md는 **목차**, docs는 **본문**이라고 생각하면 됩니다.

---

## 8. 실전 적용 예시

### Before: 구조 없이 사용

```
사용자: "배포해줘"
Claude: "어떻게 배포하나요? SSH 정보가 뭔가요? 브랜치는요?"
사용자: "ssh -i key ubuntu@IP 접속해서 git pull하고 restart해"
Claude: (실행)

--- 다음 세션 ---

사용자: "배포해줘"
Claude: "어떻게 배포하나요?"  ← 또 물어봄
```

### After: 구조 적용 후

```
사용자: "배포해줘"
Claude: (CLAUDE.md 읽음 → skills/deploy.md 참고)
Claude: "dev 브랜치에 커밋 3개 있습니다. VM에 배포할까요?"
사용자: "응"
Claude: (SSH 접속 → pull → restart → 로그 확인 → 완료 보고)
```

---

## 9. 자주 하는 실수

### 1. CLAUDE.md를 지식 덤프로 사용
**문제**: 300줄짜리 CLAUDE.md → Claude가 중요한 규칙을 놓침
**해결**: 핵심만 남기고, 상세 내용은 docs/로 분리

### 2. 규칙만 쓰고 구조화 안 함
**문제**: "이거 하지 마, 저거 하지 마" 나열만 → 읽기 어려움
**해결**: 필수/금지/컨벤션으로 분류

### 3. Skills를 안 만듦
**문제**: 매번 같은 절차를 프롬프트로 설명
**해결**: 반복 작업은 skills/에 레시피로 저장

### 4. 위험 모듈에 경고가 없음
**문제**: Claude가 DB 스키마를 마음대로 변경
**해결**: `database/CLAUDE.md`에 "마이그레이션 필수" 명시

### 5. Hook을 안 씀
**문제**: "포맷팅 맞춰줘"라고 했는데 깜빡함
**해결**: afterEdit hook으로 자동 포맷팅

---

## 체크리스트: 내 프로젝트에 적용하기

- [ ] 루트에 `CLAUDE.md` 생성 (목적, 파일맵, 규칙, 명령)
- [ ] `.claude/skills/`에 반복 작업 레시피 작성 (배포, PR, 테스트 등)
- [ ] 위험 폴더에 `CLAUDE.md` 배치 (DB, 인증, 결제 등)
- [ ] `.claude/hooks/`에 자동 안전장치 설정 (포맷팅, 테스트)
- [ ] `docs/`에 상세 문서 정리 (아키텍처, 설계, API)
- [ ] CLAUDE.md에서 docs/ 파일 참조 연결

---

*"프롬프팅은 일시적이고, 구조는 영구적이다."*
