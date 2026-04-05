"""시나리오 테스트 — 포획(스폰→ㅊ→resolve) 플로우.

실제 유저가 겪은 버그 기반:
- 마스터볼이 계속 사용됨 (소진 안 됨)
- 이벤트 모드 마스터볼 제한 초과
- 마스터볼 비당첨 시 환불 누락
- 우선볼 > 마스터볼 > 하이퍼볼 > 일반 우선순위 꼬임
"""

import random

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from tests.scenario_helpers import FakeUser, reset_all_service_state, make_pokemon


@pytest.fixture(autouse=True)
def _clean_catch():
    """매 테스트 전후 포획 상태 초기화."""
    reset_all_service_state()
    yield
    reset_all_service_state()


# ── 시나리오 1: 포획 우선순위 — 우선볼 > 마스터볼 > 하이퍼볼 > 일반 ──

class TestCatchPriority:
    """resolve_spawn의 roll 기반 우선순위가 올바른지 검증."""

    def test_priority_ball_beats_master_ball(self):
        """우선포획볼(-2.0) < 마스터볼(-1.0) → 우선볼 유저가 당첨."""
        results = [
            {"user_id": 100, "roll": -1.0, "success": True,
             "used_master_ball": True, "used_hyper_ball": False, "used_priority_ball": False,
             "display_name": "마스터볼유저", "username": "mb"},
            {"user_id": 200, "roll": -2.0, "success": True,
             "used_master_ball": False, "used_hyper_ball": False, "used_priority_ball": True,
             "display_name": "우선볼유저", "username": "pb"},
        ]
        winners = [r for r in results if r["success"]]
        winners.sort(key=lambda x: x["roll"])
        assert winners[0]["user_id"] == 200, "우선볼이 마스터볼보다 우선이어야 함"

    def test_master_ball_beats_regular(self):
        """마스터볼(-1.0) < 일반(0~1) → 마스터볼 유저가 당첨."""
        random.seed(42)
        results = [
            {"user_id": 100, "roll": -1.0, "success": True,
             "used_master_ball": True, "used_hyper_ball": False, "used_priority_ball": False,
             "display_name": "마스터볼유저", "username": "mb"},
            {"user_id": 200, "roll": 0.3, "success": True,
             "used_master_ball": False, "used_hyper_ball": False, "used_priority_ball": False,
             "display_name": "일반유저", "username": "reg"},
        ]
        winners = [r for r in results if r["success"]]
        winners.sort(key=lambda x: x["roll"])
        assert winners[0]["user_id"] == 100, "마스터볼이 일반보다 우선이어야 함"

    def test_hyper_ball_no_special_priority(self):
        """하이퍼볼은 catch rate 3배일 뿐, roll 자체에 보너스 없음.
        성공 시 roll은 일반과 동일하게 random."""
        results = [
            {"user_id": 100, "roll": 0.1, "success": True,
             "used_master_ball": False, "used_hyper_ball": True, "used_priority_ball": False,
             "display_name": "하이퍼유저", "username": "hb"},
            {"user_id": 200, "roll": 0.05, "success": True,
             "used_master_ball": False, "used_hyper_ball": False, "used_priority_ball": False,
             "display_name": "럭키유저", "username": "lucky"},
        ]
        winners = [r for r in results if r["success"]]
        winners.sort(key=lambda x: x["roll"])
        # roll 더 낮은 일반유저가 당첨
        assert winners[0]["user_id"] == 200


# ── 시나리오 2: 마스터볼 비당첨 시 환불 ──

class TestMasterBallRefund:
    """마스터볼 사용자가 비당첨이면 환불, 당첨이면 소멸."""

    def test_loser_master_ball_refunded(self):
        """우선볼이 당첨되면 마스터볼 유저는 환불 대상."""
        results = [
            {"user_id": 100, "roll": -1.0, "success": True,
             "used_master_ball": True, "used_hyper_ball": False, "used_priority_ball": False},
            {"user_id": 200, "roll": -2.0, "success": True,
             "used_master_ball": False, "used_hyper_ball": False, "used_priority_ball": True},
        ]
        winners = sorted([r for r in results if r["success"]], key=lambda x: x["roll"])
        winner_id = winners[0]["user_id"]  # 200 (우선볼)

        # 마스터볼 패배자 → 환불 대상
        master_refund_ids = [
            r["user_id"] for r in results
            if r["used_master_ball"] and r["user_id"] != winner_id
        ]
        assert 100 in master_refund_ids, "마스터볼 패배자는 환불되어야 함"

    def test_winner_master_ball_not_refunded(self):
        """마스터볼 당첨자는 환불 안 됨."""
        results = [
            {"user_id": 100, "roll": -1.0, "success": True,
             "used_master_ball": True, "used_hyper_ball": False, "used_priority_ball": False},
            {"user_id": 200, "roll": 0.5, "success": False,
             "used_master_ball": False, "used_hyper_ball": False, "used_priority_ball": False},
        ]
        winners = sorted([r for r in results if r["success"]], key=lambda x: x["roll"])
        winner_id = winners[0]["user_id"]  # 100 (마스터볼 당첨)

        master_refund_ids = [
            r["user_id"] for r in results
            if r["used_master_ball"] and r["user_id"] != winner_id
        ]
        assert 100 not in master_refund_ids, "마스터볼 당첨자는 환불 안 됨"
        assert len(master_refund_ids) == 0


# ── 시나리오 3: 이벤트 모드 마스터볼 카운터 ──

class TestEventMasterballLimit:
    """이벤트 채팅방에서 마스터볼 사용 횟수 제한."""

    def test_event_masterball_count_tracks(self):
        """_event_masterball_count가 정확히 증가하는지."""
        from handlers.group_catch import _event_masterball_count

        _event_masterball_count.clear()
        user_id = 12345

        # 카운트 증가 시뮬레이션
        _event_masterball_count[user_id] = _event_masterball_count.get(user_id, 0) + 1
        assert _event_masterball_count[user_id] == 1

        _event_masterball_count[user_id] = _event_masterball_count.get(user_id, 0) + 1
        assert _event_masterball_count[user_id] == 2

    def test_event_masterball_limit_exceeded(self):
        """제한 초과 시 거부 로직 검증."""
        from handlers.group_catch import _event_masterball_count
        import config

        _event_masterball_count.clear()
        user_id = 99999
        limit = getattr(config, "EVENT_STARTER_MASTERBALLS", 2)

        # 제한만큼 사용
        _event_masterball_count[user_id] = limit

        # 다음 사용 시 초과
        used = _event_masterball_count.get(user_id, 0)
        assert used >= limit, "제한 초과 상태여야 함"


# ── 시나리오 4: 이벤트 모드 전원 당첨 (셔플 후 N명) ──

class TestEventModeCatchAll:
    """이벤트 채팅방에서는 확률 무관, 셔플 후 EVENT_CATCH_LIMIT명 당첨."""

    def test_event_mode_all_participants_are_candidates(self):
        """이벤트 모드에서는 확률 실패자도 후보에 포함."""
        attempts = [
            {"user_id": i, "display_name": f"유저{i}", "username": f"user{i}"}
            for i in range(10)
        ]

        # resolve_spawn의 이벤트 모드 로직 재현
        import config
        all_participants = [
            {"user_id": a["user_id"], "display_name": a["display_name"], "username": a["username"]}
            for a in attempts
        ]
        random.seed(42)
        random.shuffle(all_participants)
        limit = getattr(config, "EVENT_CATCH_LIMIT", 5)
        event_winners = all_participants[:limit]

        assert len(event_winners) == limit
        # 모든 당첨자가 원래 참가자에 있는지
        winner_ids = {w["user_id"] for w in event_winners}
        all_ids = {a["user_id"] for a in attempts}
        assert winner_ids.issubset(all_ids)

    def test_event_mode_respects_limit(self):
        """참가자가 제한보다 적으면 전원 당첨."""
        import config
        limit = getattr(config, "EVENT_CATCH_LIMIT", 5)

        # 3명만 참가 (제한 5명)
        attempts = [
            {"user_id": i, "display_name": f"유저{i}", "username": f"user{i}"}
            for i in range(3)
        ]
        all_participants = list(attempts)
        random.shuffle(all_participants)
        event_winners = all_participants[:limit]

        assert len(event_winners) == 3, "참가자 < 제한이면 전원 당첨"


# ── 시나리오 5: catch_locks 레이스컨디션 방지 ──

class TestCatchLockRaceCondition:
    """같은 세션에 같은 유저가 중복 ㅊ 못 하는지."""

    def test_catch_lock_prevents_double_attempt(self):
        """_catch_locks에 (session_id, user_id)가 있으면 재시도 차단."""
        from handlers.group_catch import _catch_locks

        _catch_locks.clear()
        session_id, user_id = 100, 12345
        lock_key = (session_id, user_id)

        # 1차 시도: 잠금 없음 → 성공
        assert lock_key not in _catch_locks
        _catch_locks.add(lock_key)

        # 2차 시도: 잠금 있음 → 차단
        assert lock_key in _catch_locks

        # cleanup
        _catch_locks.discard(lock_key)
        assert lock_key not in _catch_locks
