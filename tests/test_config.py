"""Tests for config.py helper functions — get_iv_grade, get_tier, get_division_info, etc."""

import config


class TestGetIvGrade:
    """get_iv_grade: IV 총합 → 등급."""

    def test_s_grade(self):
        grade, _ = config.get_iv_grade(186)
        assert grade == "S"

    def test_a_grade(self):
        grade, _ = config.get_iv_grade(130)
        assert grade == "A"

    def test_d_grade(self):
        grade, _ = config.get_iv_grade(0)
        assert grade == "D"

    def test_boundary(self):
        """각 등급 경계값 테스트."""
        for threshold, expected_grade, _ in config.IV_GRADE_THRESHOLDS:
            grade, _ = config.get_iv_grade(threshold)
            assert grade == expected_grade
            # 1 아래는 다른 등급이어야 함 (가장 낮은 임계값 제외)
            if threshold > 0:
                lower_grade, _ = config.get_iv_grade(threshold - 1)
                assert lower_grade != expected_grade or expected_grade == "D"


class TestGetChatLevelInfo:
    """get_chat_level_info: CXP → 레벨 정보."""

    def test_level_low_cxp(self):
        info = config.get_chat_level_info(0)
        assert info["level"] >= 0
        assert isinstance(info["spawn_bonus"], (int, float))

    def test_high_cxp(self):
        info = config.get_chat_level_info(999999)
        assert info["level"] > 0
        assert info["next_cxp"] is None  # 최고 레벨

    def test_returns_dict_keys(self):
        info = config.get_chat_level_info(100)
        for key in ("level", "spawn_bonus", "shiny_boost_pct", "rarity_boosts", "specials", "next_cxp"):
            assert key in info


class TestGetTitleBuffByName:
    """get_title_buff_by_name: 칭호 이름 → 버프 dict."""

    def test_existing_buff(self):
        # 초대 챔피언은 버프가 있음
        buff = config.get_title_buff_by_name("초대 챔피언")
        assert buff is not None
        assert "daily_masterball" in buff or "extra_feed" in buff

    def test_no_buff(self):
        buff = config.get_title_buff_by_name("존재하지않는칭호")
        assert buff is None

    def test_empty_name(self):
        buff = config.get_title_buff_by_name("")
        assert buff is None


class TestRankedTier:
    """get_tier, get_tier_index, get_division_info, etc."""

    def test_bronze_at_0(self):
        key, name, icon = config.get_tier(0)
        assert key == "bronze"

    def test_master_at_1000(self):
        key, name, icon = config.get_tier(1000)
        assert key == "master"

    def test_tier_increases_with_rp(self):
        """RP가 높을수록 티어가 높아야 함."""
        prev_idx = 0
        for rp in (0, 200, 400, 600, 800, 1000):
            key, _, _ = config.get_tier(rp)
            idx = config.get_tier_index(key)
            assert idx >= prev_idx
            prev_idx = idx

    def test_get_tier_index(self):
        assert config.get_tier_index("bronze") > 0
        assert config.get_tier_index("master") > config.get_tier_index("bronze")

    def test_get_tier_info(self):
        info = config.get_tier_info("bronze")
        assert info is not None
        assert info[0] == "bronze"

    def test_get_tier_info_invalid(self):
        assert config.get_tier_info("nonexistent") is None

    def test_division_info_bronze(self):
        tier, div, display_rp = config.get_division_info(0)
        assert tier == "bronze"

    def test_division_info_master(self):
        tier, div, display_rp = config.get_division_info(1250)
        assert tier == "master"
        assert display_rp == 1250

    def test_division_base_rp(self):
        rp = config.get_division_base_rp("bronze", 2)
        assert isinstance(rp, int)
        assert rp >= 0


class TestGetMaxFriendship:
    """get_max_friendship: 포켓몬별 최대 친밀도."""

    def test_normal_pokemon(self):
        pokemon = {"rarity": "common"}
        result = config.get_max_friendship(pokemon)
        assert result == config.MAX_FRIENDSHIP

    def test_returns_int(self):
        pokemon = {"rarity": "epic"}
        assert isinstance(config.get_max_friendship(pokemon), int)


# ── get_ranked_badge_html ──

class TestGetRankedBadgeHtml:
    def test_master(self):
        result = config.get_ranked_badge_html("master")
        assert "tg-emoji" in result
        assert "emoji-id" in result

    def test_challenger(self):
        result = config.get_ranked_badge_html("challenger")
        assert "tg-emoji" in result

    def test_bronze_default_division(self):
        result = config.get_ranked_badge_html("bronze")
        assert "tg-emoji" in result

    def test_with_division(self):
        result = config.get_ranked_badge_html("silver", 1)
        assert "tg-emoji" in result


# ── get_division_base_rp ──

class TestGetDivisionBaseRp:
    def test_bronze_div2(self):
        rp = config.get_division_base_rp("bronze", 2)
        assert rp >= 0

    def test_bronze_div1(self):
        rp_1 = config.get_division_base_rp("bronze", 1)
        rp_2 = config.get_division_base_rp("bronze", 2)
        assert rp_1 > rp_2  # div 1은 상위

    def test_invalid_tier(self):
        assert config.get_division_base_rp("nonexistent", 1) == 0


# ── tier_division_display ──

class TestTierDivisionDisplay:
    def test_unranked(self):
        result = config.tier_division_display("unranked")
        assert "언랭" in result

    def test_placement(self):
        result = config.tier_division_display("unranked", placement_done=False, placement_games=3)
        assert "배치중" in result
        assert "3" in result

    def test_challenger(self):
        result = config.tier_division_display("challenger", total_rp=1500)
        assert "챌린저" in result
        assert "1500" in result

    def test_master(self):
        result = config.tier_division_display("master", total_rp=1250)
        assert "마스터" in result
        assert "1250" in result

    def test_normal_tier(self):
        result = config.tier_division_display("silver", division=1, display_rp=78)
        assert "실버" in result
        assert "78" in result


# ── get_camp_level_info ──

class TestGetCampLevelInfo:
    def test_level_1(self):
        row = config.get_camp_level_info(1)
        assert row is not None
        assert row[0] == 1

    def test_invalid_level_returns_last(self):
        row = config.get_camp_level_info(9999)
        assert row is not None
        assert row == config.CAMP_LEVEL_TABLE[-1]

    def test_all_levels(self):
        for lv_row in config.CAMP_LEVEL_TABLE:
            result = config.get_camp_level_info(lv_row[0])
            assert result[0] == lv_row[0]
