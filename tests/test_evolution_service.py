"""Tests for services/evolution_service.py — build_trade_evo_info (순수함수)."""

import config
from services.evolution_service import build_trade_evo_info


class TestBuildTradeEvoInfo:
    """build_trade_evo_info: 교환 진화 대상 체크 (DB 불필요)."""

    def test_trade_evo_pokemon(self):
        """교환 진화 대상은 info dict 반환."""
        # TRADE_EVOLUTION_MAP에 있는 아무 포켓몬
        for source_id, target_id in config.TRADE_EVOLUTION_MAP.items():
            result = build_trade_evo_info(source_id, instance_id=999)
            assert result is not None
            assert result["source_id"] == source_id
            assert result["target_id"] == target_id
            assert result["instance_id"] == 999
            break  # 하나만 테스트

    def test_non_trade_evo_pokemon(self):
        """교환 진화 대상이 아닌 포켓몬은 None."""
        # 피카츄(25)는 교환 진화가 아님
        result = build_trade_evo_info(25, instance_id=999)
        assert result is None

    def test_all_trade_evo_targets_valid(self):
        """TRADE_EVOLUTION_MAP의 모든 target_id가 유효한 포켓몬인지."""
        from models.pokemon_data import ALL_POKEMON
        POKEMON_IDS = {p[0] for p in ALL_POKEMON}
        for source_id, target_id in config.TRADE_EVOLUTION_MAP.items():
            assert target_id in POKEMON_IDS, f"Trade evo target {target_id} (from {source_id}) not in POKEMON_IDS"

    def test_eevee_not_in_trade_evo(self):
        """이브이는 교환 진화가 아님."""
        result = build_trade_evo_info(config.EEVEE_ID, instance_id=1)
        assert result is None

    def test_eevee_evolutions_exist(self):
        """이브이 진화 대상들이 모두 유효."""
        from models.pokemon_data import ALL_POKEMON
        POKEMON_IDS = {p[0] for p in ALL_POKEMON}
        for evo_id in config.EEVEE_EVOLUTIONS:
            assert evo_id in POKEMON_IDS, f"Eevee evo {evo_id} not in POKEMON_IDS"

    def test_branch_evolutions_valid(self):
        """분기 진화 대상들이 모두 유효."""
        from models.pokemon_data import ALL_POKEMON
        POKEMON_IDS = {p[0] for p in ALL_POKEMON}
        for base_id, targets in config.BRANCH_EVOLUTIONS.items():
            assert base_id in POKEMON_IDS, f"Branch base {base_id} not in POKEMON_IDS"
            for target_id in targets:
                assert target_id in POKEMON_IDS, f"Branch target {target_id} (from {base_id}) not in POKEMON_IDS"
