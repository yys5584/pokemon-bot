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

    def test_increasing_with_members(self):
        """멤버 수 증가 → 스폰 수 비감소."""
        prev = 0
        for count in (10, 20, 50, 100, 200, 500):
            spawns = calculate_daily_spawns(count)
            assert spawns >= prev, f"Spawns decreased at {count} members: {spawns} < {prev}"
            prev = spawns

    def test_spawn_tiers_coverage(self):
        """SPAWN_TIERS의 모든 구간이 정상 반환."""
        for min_m, max_m, expected in config.SPAWN_TIERS:
            assert calculate_daily_spawns(min_m) == expected
            assert calculate_daily_spawns(max_m) == expected

    def test_large_group(self):
        """500+ 멤버 그룹도 정상."""
        result = calculate_daily_spawns(1000)
        assert result > 0
        assert isinstance(result, int)
