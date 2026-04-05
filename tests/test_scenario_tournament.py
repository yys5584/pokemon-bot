"""시나리오 테스트 — 대회(토너먼트) 풀 플로우.

실제 유저가 겪은 버그 기반:
- 이벤트 대회에서 1세대 한정인데 2~4세대 포켓몬이 나옴
- 같은 포켓몬이 중복으로 대회에 등록됨
- 모의대회에서 보상이 지급됨
- 이미 등록한 유저가 재등록됨
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from tests.scenario_helpers import FakeUser, reset_all_service_state, make_pokemon


@pytest.fixture(autouse=True)
def _clean_tournament():
    """매 테스트 전후 대회 상태 초기화."""
    reset_all_service_state()
    yield
    reset_all_service_state()


# ── 시나리오 1: 이벤트 대회 — 1세대(ID ≤ 151) 한정 검증 ──

class TestEventTournamentGenFilter:
    """이벤트 대회에서 등록되는 포켓몬이 올바른 세대인지 검증."""

    @pytest.mark.asyncio
    async def test_random_1v1_picks_from_given_pool_only(self):
        """register_player가 get_user_pokemon_caught_in_chat 결과에서만 선택하는지 검증.

        만약 DB에서 1세대만 돌려주면, 등록 포켓몬도 1세대여야 함.
        """
        from services.tournament_service import (
            _tournament_state, register_player,
        )

        # 대회 상태 세팅: 이벤트 모드
        _tournament_state["registering"] = True
        _tournament_state["chat_id"] = -100999
        _tournament_state["random_1v1"] = True
        _tournament_state["mock"] = True

        # 1세대 포켓몬만 있는 풀
        gen1_pool = [
            make_pokemon(25, "피카츄", "⚡", "common", instance_id=1001),
            make_pokemon(6, "리자몽", "🔥", "epic", instance_id=1002),
            make_pokemon(150, "뮤츠", "🧬", "legendary", instance_id=1003),
        ]

        with patch("services.tournament_service.bq") as mock_bq, \
             patch("services.tournament_service.queries") as mock_q, \
             patch("database.connection.get_db") as mock_get_db:
            mock_bq.get_user_pokemon_caught_in_chat = AsyncMock(return_value=gen1_pool)
            mock_q.add_master_ball = AsyncMock()
            mock_get_db.return_value = AsyncMock()

            # 10번 등록해서 모든 선택이 풀 안에 있는지 확인
            for i in range(10):
                user_id = 1000 + i
                # 매번 새 유저 등록
                success, msg = await register_player(user_id, f"유저{i}")
                assert success, f"등록 실패: {msg}"

                # 등록된 포켓몬이 풀에 있는 포켓몬인지 검증
                team = _tournament_state["participants"][user_id]["team"]
                assert len(team) == 1
                picked_id = team[0].get("pokemon_id", team[0].get("id"))
                valid_ids = {p["pokemon_id"] for p in gen1_pool}
                assert picked_id in valid_ids, (
                    f"유저{i}: pokemon_id={picked_id}가 풀에 없음! "
                    f"유효: {valid_ids}"
                )

    @pytest.mark.asyncio
    async def test_random_1v1_never_picks_outside_pool(self):
        """DB가 2~4세대를 반환하지 않으면, 2~4세대가 절대 선택 안 됨."""
        from services.tournament_service import (
            _tournament_state, register_player,
        )

        _tournament_state["registering"] = True
        _tournament_state["chat_id"] = -100999
        _tournament_state["random_1v1"] = True
        _tournament_state["mock"] = True

        # 1세대만 있는 풀 (2~4세대 152~493 없음)
        gen1_only = [make_pokemon(25, "피카츄", "⚡", "common", instance_id=2001)]

        with patch("services.tournament_service.bq") as mock_bq, \
             patch("services.tournament_service.queries") as mock_q, \
             patch("database.connection.get_db") as mock_get_db:
            mock_bq.get_user_pokemon_caught_in_chat = AsyncMock(return_value=gen1_only)
            mock_q.add_master_ball = AsyncMock()
            mock_get_db.return_value = AsyncMock()

            success, _ = await register_player(500, "테스터")
            assert success

            team = _tournament_state["participants"][500]["team"]
            picked_id = team[0].get("pokemon_id", team[0].get("id"))
            # 반드시 1세대 (≤151)
            assert picked_id <= 151, f"1세대 한정인데 pokemon_id={picked_id} 선택됨!"


# ── 시나리오 2: 중복 포켓몬 등록 방지 ──

class TestEventTournamentDuplicateSpecies:
    """같은 종의 포켓몬이 두 유저에게 중복 배정되지 않는지 검증."""

    @pytest.mark.asyncio
    async def test_used_species_excluded(self):
        """유저A가 피카츄(25) 배정 → 유저B 풀에서 피카츄 제외."""
        from services.tournament_service import (
            _tournament_state, register_player,
        )

        _tournament_state["registering"] = True
        _tournament_state["chat_id"] = -100999
        _tournament_state["random_1v1"] = True
        _tournament_state["mock"] = True

        # 유저A, 유저B 둘 다 피카츄+리자몽 보유
        pool_a = [
            make_pokemon(25, "피카츄", "⚡", "common", instance_id=3001),
            make_pokemon(6, "리자몽", "🔥", "epic", instance_id=3002),
        ]
        pool_b = [
            make_pokemon(25, "피카츄", "⚡", "common", instance_id=3003),
            make_pokemon(6, "리자몽", "🔥", "epic", instance_id=3004),
        ]

        call_count = 0

        async def _mock_get_pokemon(user_id, chat_id):
            nonlocal call_count
            call_count += 1
            return pool_a if call_count == 1 else pool_b

        with patch("services.tournament_service.bq") as mock_bq, \
             patch("services.tournament_service.queries") as mock_q, \
             patch("database.connection.get_db") as mock_get_db:
            mock_bq.get_user_pokemon_caught_in_chat = AsyncMock(side_effect=_mock_get_pokemon)
            mock_q.add_master_ball = AsyncMock()
            mock_get_db.return_value = AsyncMock()

            # 유저A 등록
            ok_a, _ = await register_player(100, "유저A")
            assert ok_a
            species_a = _tournament_state["participants"][100]["team"][0].get(
                "pokemon_id", _tournament_state["participants"][100]["team"][0].get("id")
            )

            # 유저B 등록 — A가 뽑은 종은 제외되어야 함
            ok_b, _ = await register_player(200, "유저B")
            assert ok_b
            species_b = _tournament_state["participants"][200]["team"][0].get(
                "pokemon_id", _tournament_state["participants"][200]["team"][0].get("id")
            )

            # 중복 아닌지 검증
            assert species_a != species_b, (
                f"중복! 유저A={species_a}, 유저B={species_b}"
            )


# ── 시나리오 3: 이중 등록 방지 ──

class TestTournamentDoubleRegistration:
    """같은 유저가 두 번 등록하면 거부되는지 검증."""

    @pytest.mark.asyncio
    async def test_duplicate_registration_rejected(self):
        from services.tournament_service import (
            _tournament_state, register_player,
        )

        _tournament_state["registering"] = True
        _tournament_state["chat_id"] = -100999
        _tournament_state["random_1v1"] = True
        _tournament_state["mock"] = True

        pool = [make_pokemon(25, "피카츄", "⚡", "common", instance_id=4001)]

        with patch("services.tournament_service.bq") as mock_bq, \
             patch("services.tournament_service.queries") as mock_q, \
             patch("database.connection.get_db") as mock_get_db:
            mock_bq.get_user_pokemon_caught_in_chat = AsyncMock(return_value=pool)
            mock_q.add_master_ball = AsyncMock()
            mock_get_db.return_value = AsyncMock()

            # 1차 등록 → 성공
            ok1, _ = await register_player(999, "테스터")
            assert ok1

            # 2차 등록 → 거부
            ok2, msg = await register_player(999, "테스터")
            assert not ok2
            assert "이미" in msg


# ── 시나리오 4: 등록 기간 아닐 때 참가 시도 → 거부 ──

class TestTournamentRegistrationClosed:
    """등록 기간이 아닌데 ㄷ 누르면 거부."""

    @pytest.mark.asyncio
    async def test_register_before_open(self):
        from services.tournament_service import register_player

        # registering=False 상태 (기본값)
        ok, msg = await register_player(111, "유저")
        assert not ok
        assert "등록 기간" in msg

    @pytest.mark.asyncio
    async def test_register_during_running(self):
        from services.tournament_service import (
            _tournament_state, register_player,
        )

        _tournament_state["registering"] = True
        _tournament_state["running"] = True
        _tournament_state["chat_id"] = -100999

        ok, msg = await register_player(111, "유저")
        assert not ok
        assert "진행 중" in msg
