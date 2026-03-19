"""utils/battle_calc.py 단위 테스트 — 배틀 핵심 계산 로직."""

import random
from utils.battle_calc import (
    normalize_stat_hp,
    normalize_stat,
    _iv_mult,
    iv_total,
    calc_battle_stats,
    _single_type_mult,
    get_type_multiplier,
    _iv_tag,
    format_stats_line,
    calc_power,
    format_power,
    generate_ivs,
    get_normalized_base_stats,
)
import config


# ── normalize_stat ──

class TestNormalizeStat:
    def test_hp(self):
        """HP = raw + 60."""
        assert normalize_stat_hp(100) == 160

    def test_hp_zero(self):
        assert normalize_stat_hp(0) == 60

    def test_other_stat(self):
        """기타 스탯 = raw + 5."""
        assert normalize_stat(100) == 105

    def test_other_stat_zero(self):
        assert normalize_stat(0) == 5


# ── _iv_mult ──

class TestIvMult:
    def test_none_returns_1(self):
        """기존 포켓몬 (IV 없음) = 1.0."""
        assert _iv_mult(None) == 1.0

    def test_min_iv(self):
        """IV 0 = 0.85x."""
        assert abs(_iv_mult(0) - config.IV_MULT_MIN) < 1e-9

    def test_max_iv(self):
        """IV 31 = 1.15x."""
        expected = config.IV_MULT_MIN + config.IV_MULT_RANGE
        assert abs(_iv_mult(config.IV_MAX) - expected) < 1e-9

    def test_mid_iv(self):
        """IV 15~16 → 약 1.0 근처."""
        mid = _iv_mult(15)
        assert 0.98 < mid < 1.02


# ── iv_total ──

class TestIvTotal:
    def test_all_zero(self):
        assert iv_total(0, 0, 0, 0, 0, 0) == 0

    def test_all_max(self):
        assert iv_total(31, 31, 31, 31, 31, 31) == 186

    def test_none_treated_as_15(self):
        """None은 레거시 호환 = 15."""
        assert iv_total(None, None, None, None, None, None) == 90

    def test_mixed(self):
        assert iv_total(10, None, 20, 5, None, 31) == 10 + 15 + 20 + 5 + 15 + 31


# ── generate_ivs ──

class TestGenerateIvs:
    def test_returns_6_stats(self):
        ivs = generate_ivs()
        assert set(ivs.keys()) == {"iv_hp", "iv_atk", "iv_def", "iv_spa", "iv_spdef", "iv_spd"}

    def test_normal_range(self):
        random.seed(42)
        ivs = generate_ivs(is_shiny=False)
        for v in ivs.values():
            assert 0 <= v <= 31

    def test_shiny_minimum(self):
        """이로치는 최소 IV가 10."""
        random.seed(42)
        for _ in range(50):
            ivs = generate_ivs(is_shiny=True)
            for v in ivs.values():
                assert v >= config.IV_SHINY_MIN

    def test_deterministic_with_seed(self):
        """같은 시드 = 같은 결과."""
        random.seed(99)
        ivs1 = generate_ivs()
        random.seed(99)
        ivs2 = generate_ivs()
        assert ivs1 == ivs2


# ── calc_battle_stats ──

class TestCalcBattleStats:
    def test_legacy_no_iv(self):
        """IV 없이 레거시 모드 (Phase 1)."""
        stats = calc_battle_stats("epic", "offensive", friendship=3)
        assert all(stats[k] > 0 for k in ("hp", "atk", "def", "spa", "spdef", "spd"))

    def test_friendship_bonus(self):
        """친밀도 높으면 스탯 증가."""
        low = calc_battle_stats("epic", "offensive", friendship=0)
        high = calc_battle_stats("epic", "offensive", friendship=5)
        assert high["atk"] > low["atk"]

    def test_rarity_matters(self):
        """레어리티 높을수록 스탯 높음."""
        common = calc_battle_stats("common", "balanced", friendship=3)
        legendary = calc_battle_stats("legendary", "balanced", friendship=3)
        assert calc_power(legendary) > calc_power(common)

    def test_phase2_base_stats(self):
        """Phase 2: 개별 기본 스탯 제공 시 사용."""
        stats = calc_battle_stats(
            "epic", "offensive", friendship=3,
            base_hp=160, base_atk=105, base_def=85,
            base_spa=110, base_spdef=90, base_spd=100,
        )
        assert stats["hp"] > 0
        assert stats["atk"] > 0

    def test_iv_affects_stats(self):
        """IV 31 > IV 0."""
        low = calc_battle_stats("epic", "offensive", friendship=3,
                                iv_hp=0, iv_atk=0, iv_def=0, iv_spa=0, iv_spdef=0, iv_spd=0)
        high = calc_battle_stats("epic", "offensive", friendship=3,
                                 iv_hp=31, iv_atk=31, iv_def=31, iv_spa=31, iv_spdef=31, iv_spd=31)
        assert calc_power(high) > calc_power(low)

    def test_evo_stage_mult(self):
        """1단 < 2단 < 3단 (최종진화)."""
        s1 = calc_battle_stats("epic", "balanced", friendship=3, evo_stage=1)
        s2 = calc_battle_stats("epic", "balanced", friendship=3, evo_stage=2)
        s3 = calc_battle_stats("epic", "balanced", friendship=3, evo_stage=3)
        assert calc_power(s1) < calc_power(s2) < calc_power(s3)


# ── 타입 상성 ──

class TestTypeMultiplier:
    def test_super_effective(self):
        """불 → 풀 = 2배."""
        mult, idx = get_type_multiplier("fire", "grass")
        assert mult == 2.0

    def test_not_very_effective(self):
        """불 → 물 = 0.5배."""
        mult, idx = get_type_multiplier("fire", "water")
        assert mult == 0.5

    def test_neutral(self):
        """불 → 노말 = 1배."""
        mult, idx = get_type_multiplier("fire", "normal")
        assert mult == 1.0

    def test_immunity(self):
        """노말 → 고스트 = 0배."""
        mult, idx = get_type_multiplier("normal", "ghost")
        assert mult == 0.0

    def test_dual_type_defender(self):
        """불 → 풀/얼음 = 2 * 2 = 4배."""
        mult, idx = get_type_multiplier("fire", ["grass", "ice"])
        assert mult == 4.0

    def test_dual_type_attacker_picks_best(self):
        """[불, 물] → 풀: 불이 2배로 더 유리 → 불 선택."""
        mult, idx = get_type_multiplier(["fire", "water"], "grass")
        assert mult == 2.0
        assert idx == 0  # fire

    def test_dual_attacker_second_better(self):
        """[노말, 불] → 풀: 불(2배)이 노말(1배)보다 유리."""
        mult, idx = get_type_multiplier(["normal", "fire"], "grass")
        assert mult == 2.0
        assert idx == 1  # fire

    def test_same_type(self):
        """불 → 불 = 0.5배 (내성)."""
        mult, idx = get_type_multiplier("fire", "fire")
        assert mult == 0.5


# ── 포맷팅 ──

class TestFormatting:
    def test_iv_tag_positive(self):
        assert _iv_tag(195, 190) == "195(+5)"

    def test_iv_tag_negative(self):
        assert _iv_tag(185, 190) == "185(-5)"

    def test_iv_tag_zero(self):
        assert _iv_tag(190, 190) == "190"

    def test_format_stats_line_ko(self):
        stats = {"hp": 100, "atk": 80, "def": 70, "spa": 90, "spdef": 75, "spd": 85}
        line = format_stats_line(stats, lang="ko")
        assert "체100" in line
        assert "공80" in line
        assert "속85" in line

    def test_format_stats_line_en(self):
        stats = {"hp": 100, "atk": 80, "def": 70, "spa": 90, "spdef": 75, "spd": 85}
        line = format_stats_line(stats, lang="en")
        assert "HP100" in line
        assert "Atk80" in line

    def test_calc_power(self):
        stats = {"hp": 100, "atk": 80, "def": 70, "spa": 90, "spdef": 75, "spd": 85}
        assert calc_power(stats) == 500

    def test_format_power_no_base(self):
        stats = {"hp": 100, "atk": 80, "def": 70, "spa": 90, "spdef": 75, "spd": 85}
        assert format_power(stats) == "500"

    def test_format_power_with_diff(self):
        stats = {"hp": 110, "atk": 80, "def": 70, "spa": 90, "spdef": 75, "spd": 85}
        base = {"hp": 100, "atk": 80, "def": 70, "spa": 90, "spdef": 75, "spd": 85}
        assert format_power(stats, base) == "510(+10)"


# ── get_normalized_base_stats ──

class TestNormalizedBaseStats:
    def test_valid_pokemon(self):
        """리자몽(6)의 기본 스탯이 존재."""
        stats = get_normalized_base_stats(6)
        assert stats is not None
        assert stats["base_hp"] > 60  # HP = raw + 60

    def test_invalid_pokemon(self):
        """존재하지 않는 ID = None."""
        assert get_normalized_base_stats(99999) is None
