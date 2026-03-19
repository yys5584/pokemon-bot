"""models/ 데이터 무결성 테스트 — 포켓몬 데이터 정합성 검증."""

from models.pokemon_data import ALL_POKEMON
from models.pokemon_base_stats import POKEMON_BASE_STATS
from models.pokemon_skills import (
    POKEMON_SKILLS,
    get_primary_skill,
    get_skill_display,
    get_max_skill_power,
)


# ── pokemon_data 기본 검증 ──

class TestPokemonData:
    def test_not_empty(self):
        assert len(ALL_POKEMON) > 0

    def test_unique_ids(self):
        """모든 포켓몬 ID가 유일해야 함."""
        ids = [p[0] for p in ALL_POKEMON]
        assert len(ids) == len(set(ids))

    def test_required_fields(self):
        """모든 포켓몬에 필수 필드 존재: (id, name_ko, name_en, rarity, type, gen, ...)"""
        for p in ALL_POKEMON:
            assert len(p) >= 6, f"Pokemon {p[0]} has too few fields"
            assert isinstance(p[0], int), f"Pokemon ID should be int: {p[0]}"
            assert isinstance(p[1], str), f"Pokemon name_ko should be str: {p[1]}"

    def test_evolution_chain_integrity(self):
        """evolves_from이 있으면 해당 ID가 실제 존재해야 함."""
        id_set = {p[0] for p in ALL_POKEMON}
        for p in ALL_POKEMON:
            evolves_from = p[6] if len(p) > 6 else None
            if evolves_from is not None:
                assert evolves_from in id_set, f"Pokemon {p[0]} evolves_from {evolves_from} which doesn't exist"


# ── pokemon_base_stats 검증 ──

class TestPokemonBaseStats:
    def test_not_empty(self):
        assert len(POKEMON_BASE_STATS) > 0

    def test_all_ids_valid(self):
        """base_stats의 모든 ID가 pokemon_data에 존재해야 함."""
        pokemon_ids = {p[0] for p in ALL_POKEMON}
        for pid in POKEMON_BASE_STATS:
            assert pid in pokemon_ids, f"Base stats for pokemon_id={pid} but not in ALL_POKEMON"

    def test_stats_are_positive(self):
        """모든 스탯이 양수여야 함."""
        for pid, entry in POKEMON_BASE_STATS.items():
            stats = entry[:6]  # hp, atk, def, spa, spdef, spd
            for i, stat in enumerate(stats):
                assert stat > 0, f"Pokemon {pid} stat[{i}] = {stat} (should be > 0)"

    def test_type_list_exists(self):
        """마지막 원소가 타입 리스트여야 함."""
        valid_types = {
            "normal", "fire", "water", "grass", "electric", "ice",
            "fighting", "poison", "ground", "flying", "psychic",
            "bug", "rock", "ghost", "dragon", "dark", "steel", "fairy",
        }
        for pid, entry in POKEMON_BASE_STATS.items():
            types = entry[-1]
            assert isinstance(types, list), f"Pokemon {pid}: types should be list, got {type(types)}"
            for t in types:
                assert t in valid_types, f"Pokemon {pid}: invalid type '{t}'"


# ── pokemon_skills 검증 ──

class TestPokemonSkills:
    def test_get_primary_skill_single(self):
        """단일 타입 포켓몬의 1차 스킬."""
        name, power = get_primary_skill(4)  # 파이리
        assert name == "불꽃세례"
        assert power == 1.2

    def test_get_primary_skill_dual(self):
        """이중 타입 포켓몬의 1차 스킬."""
        name, power = get_primary_skill(6)  # 리자몽 (fire/flying)
        assert name == "블래스트번"
        assert power == 1.5

    def test_get_primary_skill_fallback(self):
        """미등록 포켓몬 → 몸통박치기."""
        name, power = get_primary_skill(99999)
        assert name == "몸통박치기"
        assert power == 1.2

    def test_get_skill_display_single(self):
        assert get_skill_display(4) == "불꽃세례"

    def test_get_skill_display_dual(self):
        assert get_skill_display(6) == "블래스트번/에어슬래시"

    def test_get_max_skill_power(self):
        assert get_max_skill_power(6) == 1.5

    def test_skill_power_range(self):
        """모든 스킬 파워가 1.0~3.0 범위."""
        for pid, raw in POKEMON_SKILLS.items():
            if isinstance(raw, list):
                for name, power in raw:
                    assert 1.0 <= power <= 3.0, f"Pokemon {pid} skill '{name}' power={power}"
            else:
                name, power = raw
                assert 1.0 <= power <= 3.0, f"Pokemon {pid} skill '{name}' power={power}"
