"""Tests for services/market_service.py — calc_fee."""

import config
from services.market_service import calc_fee


class TestCalcFee:
    """calc_fee: 거래소 수수료 계산."""

    def test_minimum_fee(self):
        """최소 수수료는 1."""
        assert calc_fee(1) >= 1

    def test_zero_price(self):
        """가격 0이어도 최소 1."""
        assert calc_fee(0) >= 1

    def test_fee_rate(self):
        """수수료 = ceil(price * MARKET_FEE_RATE)."""
        import math
        price = 1000
        expected = max(1, math.ceil(price * config.MARKET_FEE_RATE))
        assert calc_fee(price) == expected

    def test_fee_is_int(self):
        assert isinstance(calc_fee(500), int)

    def test_fee_scales_with_price(self):
        """가격이 높을수록 수수료도 높음."""
        assert calc_fee(10000) > calc_fee(100)

    def test_large_price(self):
        """큰 가격도 정상 동작."""
        result = calc_fee(999999)
        assert result > 0
