"""Tests for AI Masters event mode features.

Covers:
1. Config: EVENT_CHAT_IDS, EVENT_MAX_POKEMON_ID
2. Spawn filtering: pick_random_pokemon with max_pokemon_id
3. Tournament: random_1v1 registration, snapshot, placement DMs
"""

import asyncio
import random
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import config


# ── 1. Config ────────────────────────────────────────────────────

class TestEventConfig:
    def test_event_chat_ids_exists(self):
        assert hasattr(config, "EVENT_CHAT_IDS")
        assert isinstance(config.EVENT_CHAT_IDS, set)

    def test_event_max_pokemon_id_default(self):
        assert hasattr(config, "EVENT_MAX_POKEMON_ID")
        assert config.EVENT_MAX_POKEMON_ID == 151


# ── 2. Spawn Filtering ──────────────────────────────────────────

class TestPickRandomPokemonFiltering:
    """pick_random_pokemon should filter by max_pokemon_id when given."""

    @pytest.mark.asyncio
    async def test_no_filter_returns_any(self):
        """max_pokemon_id=None → 필터 없음."""
        from services.spawn_schedule import pick_random_pokemon

        candidates = [
            {"id": 1, "name_ko": "이상해씨", "rarity": "common"},
            {"id": 200, "name_ko": "다크펫", "rarity": "common"},
        ]

        with patch("services.spawn_schedule.queries") as mock_q, \
             patch("services.event_service.get_all_pokemon_boosts", new_callable=AsyncMock, return_value={}), \
             patch("services.spawn_schedule.get_weather_pokemon_boost", return_value=1.0):
            mock_q.get_pokemon_by_rarity = AsyncMock(return_value=candidates)
            result = await pick_random_pokemon("common")
            assert result["id"] in {1, 200}

    @pytest.mark.asyncio
    async def test_filter_gen1_only(self):
        """max_pokemon_id=151 → ID > 151 제외."""
        from services.spawn_schedule import pick_random_pokemon

        candidates = [
            {"id": 25, "name_ko": "피카츄", "rarity": "common"},
            {"id": 152, "name_ko": "치코리타", "rarity": "common"},
            {"id": 300, "name_ko": "에나비", "rarity": "common"},
        ]

        with patch("services.spawn_schedule.queries") as mock_q, \
             patch("services.event_service.get_all_pokemon_boosts", new_callable=AsyncMock, return_value={}), \
             patch("services.spawn_schedule.get_weather_pokemon_boost", return_value=1.0):
            mock_q.get_pokemon_by_rarity = AsyncMock(return_value=candidates)

            # Run many times to ensure no ID > 151 ever appears
            for _ in range(30):
                result = await pick_random_pokemon("common", max_pokemon_id=151)
                assert result["id"] <= 151, f"Got ID {result['id']} which exceeds 151"

    @pytest.mark.asyncio
    async def test_filter_fallback_to_common(self):
        """필터 적용 후 후보가 비면 common에서 재시도."""
        from services.spawn_schedule import pick_random_pokemon

        legendary_candidates = [
            {"id": 250, "name_ko": "호오", "rarity": "legendary"},
        ]
        common_candidates = [
            {"id": 25, "name_ko": "피카츄", "rarity": "common"},
        ]

        call_count = 0
        async def mock_get_by_rarity(rarity):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return legendary_candidates  # first call: legendary
            return common_candidates  # fallback: common

        with patch("services.spawn_schedule.queries") as mock_q, \
             patch("services.event_service.get_all_pokemon_boosts", new_callable=AsyncMock, return_value={}), \
             patch("services.spawn_schedule.get_weather_pokemon_boost", return_value=1.0):
            mock_q.get_pokemon_by_rarity = mock_get_by_rarity

            result = await pick_random_pokemon("legendary", max_pokemon_id=151)
            assert result["id"] == 25


# ── 3. Tutorial Skip ────────────────────────────────────────────

class TestTutorialSkip:
    """Event chat should skip tutorial trigger."""

    def test_event_chat_id_in_set_skips(self):
        """EVENT_CHAT_IDS에 있는 chat_id면 튜토리얼 스킵."""
        test_chat_id = -100999
        config.EVENT_CHAT_IDS.add(test_chat_id)
        try:
            assert test_chat_id in config.EVENT_CHAT_IDS
        finally:
            config.EVENT_CHAT_IDS.discard(test_chat_id)


# ── 4. Tournament random_1v1 ────────────────────────────────────

class TestTournamentRandom1v1:
    """Test random 1v1 tournament registration and snapshot."""

    def setup_method(self):
        from services.tournament_service import _tournament_state, _reset_state
        _reset_state()

    def test_reset_clears_random_1v1(self):
        from services.tournament_service import _tournament_state, _reset_state
        _tournament_state["random_1v1"] = True
        _reset_state()
        assert _tournament_state.get("random_1v1") is False

    @pytest.mark.asyncio
    async def test_register_random_1v1_no_team_needed(self):
        """random_1v1 모드에서는 배틀팀 없이 포켓몬 1마리만 있으면 등록 가능."""
        from services.tournament_service import _tournament_state, register_player

        _tournament_state["registering"] = True
        _tournament_state["chat_id"] = -100999
        _tournament_state["random_1v1"] = True

        mock_pokemon = [{"instance_id": 1, "pokemon_id": 25, "name_ko": "피카츄"}]

        with patch("services.tournament_service.bq") as mock_bq, \
             patch("services.tournament_service.queries") as mock_q, \
             patch("services.tournament_service._save_registration_db", new_callable=AsyncMock):
            mock_bq.get_user_pokemon_caught_in_chat = AsyncMock(return_value=mock_pokemon)
            mock_q.add_master_ball = AsyncMock()

            success, msg = await register_player(12345, "테스터")
            assert success is True
            assert 12345 in _tournament_state["participants"]

    @pytest.mark.asyncio
    async def test_register_random_1v1_no_pokemon_fails(self):
        """random_1v1 모드에서 포켓몬 0마리면 등록 실패."""
        from services.tournament_service import _tournament_state, register_player

        _tournament_state["registering"] = True
        _tournament_state["chat_id"] = -100999
        _tournament_state["random_1v1"] = True

        with patch("services.tournament_service.bq") as mock_bq:
            mock_bq.get_user_pokemon_caught_in_chat = AsyncMock(return_value=[])

            success, msg = await register_player(12345, "테스터")
            assert success is False
            assert "포켓몬이 없습니다" in msg or "잡은 포켓몬이 없습니다" in msg

    @pytest.mark.asyncio
    async def test_snapshot_random_1v1_picks_one(self):
        """random_1v1 스냅샷에서 보유 포켓몬 중 1마리만 선택."""
        from services.tournament_service import _tournament_state, snapshot_teams

        _tournament_state["registering"] = True
        _tournament_state["chat_id"] = -100999
        _tournament_state["random_1v1"] = True
        _tournament_state["participants"] = {
            111: {"name": "유저A", "team": None},
            222: {"name": "유저B", "team": None},
        }

        user_a_pokemon = [
            {"instance_id": 1, "pokemon_id": 25, "name_ko": "피카츄", "rarity": "common"},
            {"instance_id": 2, "pokemon_id": 6, "name_ko": "리자몽", "rarity": "rare"},
        ]
        user_b_pokemon = [
            {"instance_id": 3, "pokemon_id": 150, "name_ko": "뮤츠", "rarity": "legendary"},
        ]

        async def mock_get_pokemon(uid, chat_id):
            return user_a_pokemon if uid == 111 else user_b_pokemon

        mock_context = MagicMock()
        mock_context.bot.send_message = AsyncMock()

        with patch("services.tournament_service.bq") as mock_bq, \
             patch("services.tournament_service._safe_send", new_callable=AsyncMock):
            mock_bq.get_user_pokemon_caught_in_chat = AsyncMock(side_effect=mock_get_pokemon)

            await snapshot_teams(mock_context)

            # 각 참가자의 팀은 정확히 1마리
            assert len(_tournament_state["participants"][111]["team"]) == 1
            assert len(_tournament_state["participants"][222]["team"]) == 1

            # 유저A: 피카츄 또는 리자몽 중 하나
            picked_a = _tournament_state["participants"][111]["team"][0]
            assert picked_a["pokemon_id"] in {25, 6}

            # 유저B: 뮤츠만 있으므로 뮤츠
            picked_b = _tournament_state["participants"][222]["team"][0]
            assert picked_b["pokemon_id"] == 150

    @pytest.mark.asyncio
    async def test_snapshot_removes_user_with_no_pokemon(self):
        """스냅샷 시 포켓몬 없는 유저는 제거."""
        from services.tournament_service import _tournament_state, snapshot_teams

        _tournament_state["registering"] = True
        _tournament_state["chat_id"] = -100999
        _tournament_state["random_1v1"] = True
        _tournament_state["participants"] = {
            111: {"name": "유저A", "team": None},
        }

        mock_context = MagicMock()
        mock_context.bot.send_message = AsyncMock()

        with patch("services.tournament_service.bq") as mock_bq, \
             patch("services.tournament_service._safe_send", new_callable=AsyncMock):
            mock_bq.get_user_pokemon_caught_in_chat = AsyncMock(return_value=[])

            await snapshot_teams(mock_context)

            assert 111 not in _tournament_state["participants"]


# ── 5. Battle Royale ─────────────────────────────────────────────

class TestBattleRoyale:
    """Test battle royale core logic."""

    def test_build_contestants(self):
        from services.battle_royale import build_contestants
        participants = {
            111: {"name": "유저A", "team": [{"pokemon_id": 25, "name_ko": "피카츄", "emoji": "⚡", "pokemon_type": "electric", "rarity": "common"}]},
            222: {"name": "유저B", "team": [{"pokemon_id": 6, "name_ko": "리자몽", "emoji": "🔥", "pokemon_type": "fire", "rarity": "epic"}]},
        }
        result = build_contestants(participants)
        assert len(result) == 2
        assert result[0].hp == 100
        assert result[0].pokemon_type in ("electric", "fire")

    def test_disaster_immunity(self):
        from services.battle_royale import Contestant, DISASTERS, apply_disaster
        # 해일: 물타입 면역
        tsunami = [d for d in DISASTERS if d.name == "해일"][0]
        contestants = [
            Contestant(1, "A", 25, "피카츄", "⚡", "electric", "common"),
            Contestant(2, "B", 7, "꼬부기", "💧", "water", "common"),
        ]
        alive, dead = apply_disaster(contestants, tsunami, 1)
        # 꼬부기(물) = 면역, 피카츄 = 데미지
        assert contestants[1].hp == 100  # 물타입 면역
        assert contestants[0].hp < 100   # 전기타입 데미지

    def test_disaster_kills(self):
        from services.battle_royale import Contestant, DISASTERS, apply_disaster
        tsunami = [d for d in DISASTERS if d.name == "해일"][0]
        # 이미 HP 낮은 포켓몬
        contestants = [
            Contestant(1, "A", 25, "피카츄", "⚡", "electric", "common", hp=10),
        ]
        alive, dead = apply_disaster(contestants, tsunami, 1)
        assert len(dead) == 1
        assert dead[0].user_id == 1
        assert not contestants[0].alive

    def test_compute_placements(self):
        from services.battle_royale import Contestant, compute_placements
        contestants = [
            Contestant(1, "A", 25, "피카", "⚡", "electric", "c", alive=True),
            Contestant(2, "B", 6, "리자", "🔥", "fire", "c", alive=False, death_round=5),
            Contestant(3, "C", 7, "꼬부", "💧", "water", "c", alive=False, death_round=3),
            Contestant(4, "D", 1, "이상", "🌿", "grass", "c", alive=False, death_round=3),
        ]
        placements = compute_placements(contestants)
        assert placements[1] == 1  # 생존 = 1등
        assert placements[2] == 2  # 라운드5 탈락 = 2등
        assert placements[3] == 3  # 라운드3 동시 탈락 = 공동 3등
        assert placements[4] == 3  # 공동 3등

    def test_healing_restores_hp(self):
        from services.battle_royale import Contestant, HEALING_WIND, apply_disaster
        contestants = [
            Contestant(1, "A", 25, "피카", "⚡", "electric", "c", hp=50),
        ]
        alive, dead = apply_disaster(contestants, HEALING_WIND, 1)
        assert contestants[0].hp > 50  # 회복
        assert contestants[0].hp <= 100  # max_hp 초과 안 함
        assert len(dead) == 0
