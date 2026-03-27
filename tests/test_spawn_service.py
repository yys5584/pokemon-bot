"""Tests for services/spawn_service.py — calculate_daily_spawns, is_midnight_bonus."""

import config
from services.spawn_service import calculate_daily_spawns


class TestCalculateDailySpawns:
    """calculate_daily_spawns: 멤버 수 → 일일 스폰 수."""

    def test_below_minimum(self):
        """최소 멤버 미만이면 0."""
        result = calculate_daily_spawns(config.SPAWN_MIN_MEMBERS - 1)
        assert result == 0

    def test_zero_members(self):
        assert calculate_daily_spawns(0) == 0

    def test_minimum_members(self):
        """최소 멤버 수에서 스폰 시작."""
        result = calculate_daily_spawns(config.SPAWN_MIN_MEMBERS)
        assert result > 0

    def test_all_same_spawns(self):
        """모든 채팅방 동일 2회 스폰."""
        assert calculate_daily_spawns(10) == 2
        assert calculate_daily_spawns(100) == 2
        assert calculate_daily_spawns(1000) == 2
        assert calculate_daily_spawns(5000) == 2
