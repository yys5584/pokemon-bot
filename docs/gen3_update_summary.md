# 3세대 업데이트 요약

## 개요
3세대 포켓몬 135종(#252-386)을 봇에 추가. 기존 251종 → 386종 확장.

---

## 변경 파일

| 파일 | 변경 내용 | 상태 |
|------|----------|------|
| `models/pokemon_data.py` | Gen3 import 합침 (386종) | ✅ |
| `models/pokemon_base_stats.py` | Gen3 base stats merge (386종) | ✅ |
| `models/pokemon_skills.py` | Gen3 스킬 135개 추가 (386종) | ✅ |
| `models/pokemon_battle_data.py` | Gen3 배틀데이터 135개 추가 (386종) | ✅ |
| `database/seed.py` | 임계값 251→386 | ✅ |
| `config.py` | TITLES(386), 호연 칭호 4개, TRADE_MAP | ✅ |
| `utils/title_checker.py` | gen2 쿼리 수정 + gen3 쿼리/분기 추가 | ✅ |
| `database/queries.py` | `count_pokedex_gen3()` + 대시보드 gen3_count | ✅ |
| `handlers/dm_pokedex.py` | 251→386, 3세대 카운트, TMI 135개 | ✅ |
| `dashboard/templates/index.html` | 251→386, 3세대 컬럼 추가 | ✅ |
| `assets/pokemon/252~386.png` | 스프라이트 135개 다운로드 | ✅ |

---

## 세부 변경 사항

### 1. 데이터 파일
- `pokemon_data.py`: `ALL_POKEMON_GEN3` import + 합침
- `pokemon_base_stats.py`: `POKEMON_BASE_STATS_GEN3` dict merge
- `pokemon_data_gen3.py` / `pokemon_base_stats_gen3.py`: 크롤링 데이터 (이전 세션에서 생성)

### 2. 배틀 시스템
- `pokemon_skills.py`: 135개 스킬 (원작 대표기술명 한글, 파워 공식 적용)
- `pokemon_battle_data.py`: 135개 (primary_type, stat_type) 엔트리

### 3. DB 시딩
- `seed_pokemon_data()` 임계값: 251 → 386
- `seed_battle_data()`: Gen3 데이터가 POKEMON_BATTLE_DATA에 merge되면 자동 반영

### 4. 칭호 시스템

#### 호연 칭호 4개 추가
| 칭호 ID | 이름 | 조건 |
|---------|------|------|
| `gen3_starter` | 호연의 초보 | 3세대 도감 15종 |
| `gen3_collector` | 호연 수집가 | 3세대 도감 45종 |
| `gen3_trainer` | 호연 트레이너 | 3세대 도감 75종 |
| `gen3_master` | 호연 마스터 | 3세대 도감 135종 |

#### 기존 칭호 수정
- 그랜드마스터: 251종 → **386종**

#### title_checker.py 버그 수정
- gen2 쿼리: `pokemon_id > 151` → `BETWEEN 152 AND 251` (Gen3 포함 방지)
- gen3 쿼리 추가: `BETWEEN 252 AND 386`

### 5. 교환 진화
```
349 → 350  (빈티나 → 밀로틱)
366 → 367  (진주몽 → 헌테일)
```

### 6. UI 변경
- 도감 표시: `/251` → `/386`
- 세대별 카운트: `1세대/2세대` → `1세대/2세대/3세대`
- 대시보드 랭킹: 3세대 컬럼 추가

### 7. 도감 TMI 텍스트
- 135개 커뮤 밈/경쟁 메타/애니 레퍼런스 반영
- 주요: 가디안(퍼리), 레쿠쟈(AG 추방), 앱솔(오해), 게을킹(나태 특성) 등

### 8. 스프라이트
- PokeAPI official-artwork에서 252~386.png 135개 다운로드
- `assets/pokemon/` 총 386개 완성

---

## 참고사항
- Gen3 칭호 이모지: 임시로 기존 이모지 사용 (나중에 커스텀 이모지 업로드 후 교체)
- 원시회귀(Primal) 폼, 메가진화, 테오키스 폼체인지: 미포함 (기본형만)

## 배포 후 검증
1. 봇 시작 → pokemon_master 386건 시드 확인
2. Gen 3 포켓몬 자연 스폰 + 포획
3. 진화 (나무지기→나무돌이→나무킹, 빈티나→밀로틱 교환진화)
4. 배틀 (Gen 3 종족값 + 스킬 정상 적용)
5. 칭호 (호연 칭호, 그랜드마스터 386)
6. 도감 UI (386 기준 수집률)
