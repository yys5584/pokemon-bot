"""시나리오 테스트 — 콜백 라우팅 & 체인 검증.

실제 유저가 겪은 버그 기반:
- 콜백 버튼이 안 먹힘 (패턴 등록 누락)
- 팀 편집 중 상태 꼬임
- 배틀 수락 버튼 무반응
"""

import re

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ── 시나리오 1: 모든 콜백 패턴이 register에 등록되어 있는지 ──

class TestCallbackPatternCoverage:
    """실제 사용되는 callback_data가 _register.py의 패턴에 매칭되는지."""

    # _register.py에 등록된 모든 콜백 패턴 (정규식)
    REGISTERED_PATTERNS = [
        r"^gmypk_",
        r"^lang_",
        r"^settings_",
        r"^status_",
        r"^close_msg$",
        r"^catch_keep_\d+$",
        r"^catch_release_\d+$",
        r"^dex_",
        r"^mypoke_",
        r"^rel_",
        r"^fus_",
        r"^sml_",
        r"^dg_",
        r"^boss_",
        r"^title_",
        r"^tlist_",
        r"^titlep_",
        r"^partner_",
        r"^t(edit|slot_view|pick|rem|p|f|cl|done|cancel|del|swap|swap_cancel|sw)_",
        r"^battle_",
        r"^ranked_",
        r"^b(detail|skip|tbag)_",
        r"^shop_",
        r"^gacha_",
        r"^(item_|ivr_|ivstone_|egg_hatch_|sct_|trt_|pers_)",
        r"^nurt_",
        r"^mkt_",
        r"^tevo_",
        r"^gtrade_",
        r"^tut_",
        r"^yacha_",
        r"^yres_",
        r"^captcha_",
        r"^help_",
        r"^pmenu_",
        r"^sub_",
        r"^evt_dm_",
        r"^camp_",
        r"^cdm_",
        r"^tarot_birth_",
        r"^tarot_skip_",
        r"^tarot_time_",
        r"^tarot_topic_",
        r"^tarot_gender_",
        r"^tarot_ctx_",
        r"^tarot_sub_",
        r"^tarot_read_",
        r"^tarot_pick_",
        r"^tarot_page_",
        r"^tarot_again_",
        r"^cs_",
    ]

    def _matches_any_pattern(self, callback_data: str) -> bool:
        """callback_data가 등록된 패턴 중 하나에 매칭되는지."""
        return any(re.match(p, callback_data) for p in self.REGISTERED_PATTERNS)

    # 팀 편집 콜백
    def test_team_edit_callbacks_registered(self):
        """팀 편집 관련 콜백들이 패턴에 매칭되는지."""
        team_callbacks = [
            "tedit_1",          # 팀 편집 메뉴
            "tslot_view_1",     # 슬롯 보기  (← 이전 버그: slot_view 누락)
            "tpick_1_25",       # 포켓몬 선택
            "trem_1",           # 슬롯 제거
            "tp_1",             # 페이지네이션
            "tf_1",             # 필터
            "tcl_1",            # 팀 초기화
            "tdone_1",          # 완료
            "tcancel_1",        # 취소
            "tdel_1",           # 삭제
            "tswap_1",          # 스왑
            "tswap_cancel_1",   # 스왑 취소
            "tsw_1_2",          # 스왑 실행
        ]
        for cb in team_callbacks:
            assert self._matches_any_pattern(cb), f"팀 콜백 '{cb}'가 어떤 패턴에도 매칭 안 됨!"

    # 배틀 콜백
    def test_battle_callbacks_registered(self):
        """배틀 관련 콜백들이 매칭되는지."""
        battle_callbacks = [
            "battle_accept_12345",
            "battle_decline_12345",
            "battle_cancel_12345",
            "bdetail_12345",
            "bskip_12345",
            "btbag_12345",
        ]
        for cb in battle_callbacks:
            assert self._matches_any_pattern(cb), f"배틀 콜백 '{cb}'가 어떤 패턴에도 매칭 안 됨!"

    # 랭크전 콜백
    def test_ranked_callbacks_registered(self):
        """랭크전 콜백 매칭."""
        ranked_callbacks = [
            "ranked_queue",
            "ranked_cancel",
            "ranked_rematch",
        ]
        for cb in ranked_callbacks:
            assert self._matches_any_pattern(cb), f"랭크전 콜백 '{cb}'가 어떤 패턴에도 매칭 안 됨!"

    # 포획 결과 콜백
    def test_catch_result_callbacks_registered(self):
        """포획 후 유지/방생 콜백."""
        catch_callbacks = [
            "catch_keep_12345",
            "catch_release_12345",
        ]
        for cb in catch_callbacks:
            assert self._matches_any_pattern(cb), f"포획 콜백 '{cb}'가 어떤 패턴에도 매칭 안 됨!"

    # 던전 콜백
    def test_dungeon_callbacks_registered(self):
        """던전 콜백."""
        dg_callbacks = [
            "dg_enter_1",
            "dg_skill_1",
            "dg_buff_1",
            "dg_reroll_1",
        ]
        for cb in dg_callbacks:
            assert self._matches_any_pattern(cb), f"던전 콜백 '{cb}'가 어떤 패턴에도 매칭 안 됨!"

    # 타로 콜백 체인 (multi-step)
    def test_tarot_callback_chain_registered(self):
        """타로 전체 흐름의 콜백들이 빠짐없이 등록되어 있는지."""
        tarot_flow = [
            "tarot_birth_3",       # 생월 선택
            "tarot_skip_1",        # 스킵
            "tarot_time_morning",  # 시간대
            "tarot_topic_love",    # 주제
            "tarot_gender_female", # 성별
            "tarot_ctx_work",      # 맥락
            "tarot_sub_career",    # 세부
            "tarot_read_1",        # 카드 읽기
            "tarot_pick_3",        # 카드 선택
            "tarot_page_2",        # 페이지네이션
            "tarot_again_1",       # 다시 뽑기
        ]
        for cb in tarot_flow:
            assert self._matches_any_pattern(cb), f"타로 콜백 '{cb}'가 어떤 패턴에도 매칭 안 됨!"


# ── 시나리오 2: 콜백 패턴에 구멍이 없는지 (회귀 테스트) ──

class TestCallbackPatternCompleteness:
    """_register.py 파일을 직접 파싱해서 패턴 수를 검증."""

    def test_register_has_minimum_callback_handlers(self):
        """최소 45개 이상의 CallbackQueryHandler가 등록되어 있어야 함."""
        import pathlib
        register_path = pathlib.Path(__file__).parent.parent / "handlers" / "_register.py"
        content = register_path.read_text(encoding="utf-8")
        count = content.count("CallbackQueryHandler(")
        assert count >= 45, (
            f"CallbackQueryHandler가 {count}개밖에 없음 (최소 45개 예상). "
            f"새 콜백 핸들러를 추가했으면 _register.py에 등록했는지 확인!"
        )

    def test_no_duplicate_callback_patterns(self):
        """같은 패턴이 중복 등록되지 않았는지."""
        import pathlib
        register_path = pathlib.Path(__file__).parent.parent / "handlers" / "_register.py"
        content = register_path.read_text(encoding="utf-8")

        patterns = re.findall(r'pattern=r"([^"]+)"', content)
        seen = set()
        duplicates = []
        for p in patterns:
            if p in seen:
                duplicates.append(p)
            seen.add(p)

        assert not duplicates, f"중복 콜백 패턴 발견: {duplicates}"


# ── 시나리오 3: FakeUser로 콜백 핸들러 호출 검증 ──

class TestFakeUserCallbackFlow:
    """FakeUser로 실제 핸들러를 호출할 수 있는지 기본 검증."""

    def test_fake_user_send_creates_valid_update(self):
        """FakeUser.send()가 올바른 mock update를 만드는지."""
        from tests.scenario_helpers import FakeUser

        user = FakeUser(12345, "테스터")
        update, ctx = user.send("ㅊ")

        assert update.effective_user.id == 12345
        assert update.effective_user.first_name == "테스터"
        assert update.message.text == "ㅊ"
        assert update.callback_query is None

    def test_fake_user_press_creates_valid_callback(self):
        """FakeUser.press()가 올바른 mock callback query를 만드는지."""
        from tests.scenario_helpers import FakeUser

        user = FakeUser(12345, "테스터")
        update, ctx = user.press("battle_accept_999")

        assert update.callback_query is not None
        assert update.callback_query.data == "battle_accept_999"
        assert update.callback_query.from_user.id == 12345

    def test_fake_user_context_persists(self):
        """같은 FakeUser의 context.user_data가 핸들러 간에 유지되는지."""
        from tests.scenario_helpers import FakeUser

        user = FakeUser(12345, "테스터")

        # 1차 호출
        update1, ctx1 = user.send("팀")
        ctx1.user_data["flow_state"] = "team_edit"

        # 2차 호출 — 같은 user_data 참조
        update2, ctx2 = user.press("tedit_1")
        assert ctx2.user_data.get("flow_state") == "team_edit", \
            "같은 유저의 user_data가 핸들러 간에 공유되어야 함"

    def test_different_users_have_separate_state(self):
        """다른 FakeUser는 독립적인 user_data를 가져야 함."""
        from tests.scenario_helpers import FakeUser

        user_a = FakeUser(111, "유저A")
        user_b = FakeUser(222, "유저B")

        _, ctx_a = user_a.send("팀")
        ctx_a.user_data["my_state"] = "A의 상태"

        _, ctx_b = user_b.send("팀")
        assert "my_state" not in ctx_b.user_data, \
            "다른 유저의 user_data가 섞이면 안 됨"
