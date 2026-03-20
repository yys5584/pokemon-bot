"""Tests for services/battle_service.py — _prepare_combatant, _calc_damage, _resolve_battle, _calculate_bp."""

import random
import pytest


class TestPrepareCombatant:
    """_prepare_combatant: pokemon dict → battle-ready dict."""

    def test_basic_output_keys(self):
        from services.battle_service import _prepare_combatant
        pokemon = {
            "pokemon_id": 6, "name_ko": "리자몽", "emoji": "🔥",
            "rarity": "epic", "stat_type": "offensive", "friendship": 3,
            "pokemon_type": "fire", "is_shiny": 0,
            "iv_hp": 20, "iv_atk": 25, "iv_def": 15,
            "iv_spa": 28, "iv_spdef": 18, "iv_spd": 22,
        }
        result = _prepare_combatant(pokemon)
        # 필수 키 존재
        for key in ("name", "type", "rarity", "stats", "current_hp", "skills", "pokemon_id", "iv_grade"):
            assert key in result, f"Missing key: {key}"
        assert result["name"] == "리자몽"
        assert result["current_hp"] == result["stats"]["hp"]

    def test_partner_bonus(self):
        from services.battle_service import _prepare_combatant
        pokemon = {
            "pokemon_id": 25, "name_ko": "피카츄", "emoji": "⚡",
            "rarity": "uncommon", "stat_type": "balanced", "friendship": 3,
            "pokemon_type": "electric", "is_shiny": 0,
            "iv_hp": 15, "iv_atk": 15, "iv_def": 15,
            "iv_spa": 15, "iv_spdef": 15, "iv_spd": 15,
        }
        normal = _prepare_combatant(pokemon, is_partner=False)
        partner = _prepare_combatant(pokemon, is_partner=True)
        # 파트너는 ATK +5%
        assert partner["stats"]["atk"] > normal["stats"]["atk"]
        assert partner["stats"]["atk"] == int(normal["stats"]["atk"] * 1.05)

    def test_camp_bonus(self):
        from services.battle_service import _prepare_combatant
        import config
        pokemon = {
            "pokemon_id": 25, "name_ko": "피카츄", "emoji": "⚡",
            "rarity": "uncommon", "stat_type": "balanced", "friendship": 3,
            "pokemon_type": "electric", "is_shiny": 0,
            "iv_hp": 15, "iv_atk": 15, "iv_def": 15,
            "iv_spa": 15, "iv_spdef": 15, "iv_spd": 15,
        }
        normal = _prepare_combatant(pokemon, camp_placed=False)
        camped = _prepare_combatant(pokemon, camp_placed=True)
        bonus = config.CAMP_BATTLE_BONUS
        # 캠프 배치: 모든 스탯 +bonus%
        assert camped["stats"]["hp"] == int(normal["stats"]["hp"] * (1 + bonus))

    def test_shiny_flag(self):
        from services.battle_service import _prepare_combatant
        pokemon = {
            "pokemon_id": 6, "name_ko": "리자몽", "emoji": "🔥",
            "rarity": "epic", "stat_type": "offensive", "friendship": 3,
            "pokemon_type": "fire", "is_shiny": 1,
            "iv_hp": 15, "iv_atk": 15, "iv_def": 15,
            "iv_spa": 15, "iv_spdef": 15, "iv_spd": 15,
        }
        result = _prepare_combatant(pokemon)
        assert result["is_shiny"] is True


class TestCalcDamage:
    """_calc_damage: deterministic damage tests with seeded random."""

    def _make_combatant(self, **overrides):
        base = {
            "name": "테스트몬",
            "type": ["fire"],
            "rarity": "common",
            "is_shiny": False,
            "stats": {"hp": 100, "atk": 50, "def": 40, "spa": 45, "spdef": 40, "spd": 50},
            "current_hp": 100,
            "skills": [("몸통박치기", 1.2)],
            "skill_name": "몸통박치기",
            "skill_power": 1.2,
            "pokemon_id": 1,
        }
        base.update(overrides)
        return base

    def test_damage_positive(self):
        from services.battle_service import _calc_damage
        random.seed(42)
        atk = self._make_combatant(stats={"hp": 100, "atk": 80, "def": 40, "spa": 60, "spdef": 40, "spd": 50})
        dfn = self._make_combatant(stats={"hp": 100, "atk": 50, "def": 50, "spa": 45, "spdef": 50, "spd": 40})
        damage, _, _, _, _ = _calc_damage(atk, dfn)
        assert damage > 0

    def test_type_advantage_more_damage(self):
        from services.battle_service import _calc_damage
        # fire vs grass = 2x
        random.seed(100)
        atk = self._make_combatant(type=["fire"], stats={"hp": 100, "atk": 60, "def": 40, "spa": 50, "spdef": 40, "spd": 50})
        dfn_grass = self._make_combatant(type=["grass"], stats={"hp": 100, "atk": 50, "def": 50, "spa": 45, "spdef": 50, "spd": 40})
        dfn_water = self._make_combatant(type=["water"], stats={"hp": 100, "atk": 50, "def": 50, "spa": 45, "spdef": 50, "spd": 40})

        random.seed(100)
        dmg_vs_grass, _, _, mult_grass, _ = _calc_damage(atk, dfn_grass)
        random.seed(100)
        dmg_vs_water, _, _, mult_water, _ = _calc_damage(atk, dfn_water)

        assert mult_grass > mult_water  # fire vs grass > fire vs water
        assert dmg_vs_grass > dmg_vs_water

    def test_returns_tuple_of_5(self):
        from services.battle_service import _calc_damage
        random.seed(0)
        atk = self._make_combatant()
        dfn = self._make_combatant()
        result = _calc_damage(atk, dfn)
        assert len(result) == 5


class TestCalculateBP:
    """_calculate_bp: BP reward calculation."""

    def test_base_bp(self):
        from services.battle_service import _calculate_bp
        import config
        bp = _calculate_bp(6, 6, perfect=False, streak=1)
        expected = config.BP_WIN_BASE + 6 * config.BP_WIN_PER_ENEMY
        assert bp == expected

    def test_perfect_bonus(self):
        from services.battle_service import _calculate_bp
        import config
        normal = _calculate_bp(6, 6, perfect=False, streak=1)
        perfect = _calculate_bp(6, 6, perfect=True, streak=1)
        assert perfect == normal + config.BP_PERFECT_WIN

    def test_streak_bonus_at_3(self):
        from services.battle_service import _calculate_bp
        import config
        no_streak = _calculate_bp(6, 6, perfect=False, streak=2)
        streak_3 = _calculate_bp(6, 6, perfect=False, streak=3)
        assert streak_3 == no_streak + config.BP_STREAK_BONUS

    def test_streak_bonus_at_6(self):
        from services.battle_service import _calculate_bp
        import config
        streak_5 = _calculate_bp(6, 6, perfect=False, streak=5)
        streak_6 = _calculate_bp(6, 6, perfect=False, streak=6)
        assert streak_6 == streak_5 + config.BP_STREAK_BONUS


class TestHpBar:
    """_hp_bar: HP bar display."""

    def test_full_hp(self):
        from services.battle_service import _hp_bar
        bar = _hp_bar(100, 100)
        assert "█" in bar
        assert "░" not in bar

    def test_zero_hp(self):
        from services.battle_service import _hp_bar
        bar = _hp_bar(0, 100)
        assert "█" not in bar

    def test_half_hp(self):
        from services.battle_service import _hp_bar
        bar = _hp_bar(50, 100, length=10)
        filled = bar.count("█")
        empty = bar.count("░")
        assert filled == 5
        assert empty == 5


class TestResolveBattle:
    """_resolve_battle: full battle simulation."""

    def _make_team(self, count=1, atk=60, dfn=50):
        from services.battle_service import _prepare_combatant
        team = []
        for i in range(count):
            pokemon = {
                "pokemon_id": 6, "pokemon_instance_id": 1000 + i,
                "name_ko": "리자몽", "emoji": "🔥",
                "rarity": "epic", "stat_type": "offensive", "friendship": 3,
                "pokemon_type": "fire", "is_shiny": 0,
                "iv_hp": 20, "iv_atk": 25, "iv_def": 15,
                "iv_spa": 28, "iv_spdef": 18, "iv_spd": 22,
            }
            team.append(_prepare_combatant(pokemon))
        return team

    def test_battle_has_winner(self):
        from services.battle_service import _resolve_battle
        random.seed(42)
        team_a = self._make_team(3)
        team_b = self._make_team(3)
        result = _resolve_battle(team_a, team_b)
        assert result["winner"] in ("challenger", "defender")
        assert "turn_data" in result
        assert len(result["turn_data"]) > 0

    def test_battle_returns_stats(self):
        from services.battle_service import _resolve_battle
        random.seed(42)
        team_a = self._make_team(1)
        team_b = self._make_team(1)
        result = _resolve_battle(team_a, team_b)
        assert "perfect_win" in result
        assert isinstance(result["perfect_win"], bool)
