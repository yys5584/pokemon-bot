"""Tests for services/abuse_service.py — 순수 함수 단위 테스트."""

import time
from unittest.mock import patch
from services.abuse_service import (
    format_lock_duration,
    _generate_wrong_choices,
    create_challenge,
    get_pending_challenge,
    is_challenge_expired,
    _pending_challenges,
    CHALLENGE_TIMEOUT_SEC,
)


# ── format_lock_duration ──

class TestFormatLockDuration:
    def test_minutes(self):
        assert format_lock_duration(300) == "5분"

    def test_hours(self):
        assert format_lock_duration(3600) == "1시간"

    def test_2_hours(self):
        assert format_lock_duration(7200) == "2시간"

    def test_90_minutes_shows_hours(self):
        """90분 = 5400초 → 1시간 (정수 나눗셈)."""
        assert format_lock_duration(5400) == "1시간"

    def test_zero(self):
        assert format_lock_duration(0) == "0분"


# ── _generate_wrong_choices ──

class TestGenerateWrongChoices:
    def test_returns_list(self):
        result = _generate_wrong_choices("피카츄")
        assert isinstance(result, list)

    def test_count(self):
        result = _generate_wrong_choices("피카츄", 3)
        assert len(result) == 3

    def test_excludes_correct(self):
        for _ in range(10):
            result = _generate_wrong_choices("피카츄", 5)
            assert "피카츄" not in result

    def test_all_unique(self):
        result = _generate_wrong_choices("피카츄", 5)
        assert len(result) == len(set(result))


# ── create_challenge ──

class TestCreateChallenge:
    def setup_method(self):
        _pending_challenges.clear()

    def test_structure(self):
        ch = create_challenge(123, 456, "피카츄")
        assert ch["user_id"] == 123
        assert ch["session_id"] == 456
        assert ch["expected"] == "피카츄"
        assert ch["type"] == "name_choice"
        assert ch["answered"] is False

    def test_choices_contain_correct(self):
        ch = create_challenge(123, 456, "피카츄")
        assert "피카츄" in ch["choices"]

    def test_choices_4_total(self):
        ch = create_challenge(123, 456, "피카츄")
        assert len(ch["choices"]) == 4

    def test_stored_in_pending(self):
        create_challenge(123, 456, "피카츄")
        assert 123 in _pending_challenges

    def teardown_method(self):
        _pending_challenges.clear()


# ── get_pending_challenge ──

class TestGetPendingChallenge:
    def setup_method(self):
        _pending_challenges.clear()

    def test_no_challenge(self):
        assert get_pending_challenge(999) is None

    def test_existing(self):
        create_challenge(123, 456, "피카츄")
        ch = get_pending_challenge(123)
        assert ch is not None
        assert ch["expected"] == "피카츄"

    def test_expired_still_returned(self):
        """만료된 챌린지도 처리용으로 반환됨."""
        create_challenge(123, 456, "피카츄")
        _pending_challenges[123]["created_at"] = time.time() - CHALLENGE_TIMEOUT_SEC - 10
        ch = get_pending_challenge(123)
        assert ch is not None

    def teardown_method(self):
        _pending_challenges.clear()


# ── is_challenge_expired ──

class TestIsChallengeExpired:
    def test_not_expired(self):
        ch = {"created_at": time.time()}
        assert is_challenge_expired(ch) is False

    def test_expired(self):
        ch = {"created_at": time.time() - CHALLENGE_TIMEOUT_SEC - 1}
        assert is_challenge_expired(ch) is True

    def test_boundary(self):
        """정확히 타임아웃 시점은 만료."""
        ch = {"created_at": time.time() - CHALLENGE_TIMEOUT_SEC - 0.1}
        assert is_challenge_expired(ch) is True
