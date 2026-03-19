"""utils/honorific.py 단위 테스트 — 한국어 존칭 변환."""

from unittest.mock import patch
from utils.honorific import (
    _attach_subject_particle,
    _to_polite,
    _to_supreme,
    format_actor,
    format_target_action,
    honorific_name,
    honorific_catch_verb,
    _format_actor_i18n,
)


# ── 조사 ──

class TestSubjectParticle:
    def test_ends_with_batchim(self):
        """받침 있음 → '이'."""
        assert _attach_subject_particle("문유") == "문유가"  # 유: 받침 없음

    def test_ends_without_batchim(self):
        """받침 없음 → '가'."""
        assert _attach_subject_particle("피카츄") == "피카츄가"

    def test_ends_with_batchim_yes(self):
        """받침 있음 → '이'."""
        assert _attach_subject_particle("리자몽") == "리자몽이"

    def test_english_name(self):
        """영문 → '이'."""
        assert _attach_subject_particle("Shawn") == "Shawn이"

    def test_empty(self):
        assert _attach_subject_particle("") == ""


# ── 존칭 변환 ──

class TestToPolite:
    def test_basic(self):
        """던졌다! → 던졌습니다!"""
        assert _to_polite("던졌다!") == "던졌습니다!"

    def test_신청(self):
        assert _to_polite("신청했다!") == "신청했습니다!"

    def test_진화(self):
        assert _to_polite("진화시켰다!") == "진화시켰습니다!"


class TestToSupreme:
    def test_던졌다(self):
        """던졌다! → 던지셨습니다! (졌다 → 지셨습니다)"""
        assert _to_supreme("던졌다!") == "던지셨습니다!"

    def test_신청했다(self):
        """신청했다! → 신청하셨습니다!"""
        assert _to_supreme("신청했다!") == "신청하셨습니다!"

    def test_진화시켰다(self):
        """진화시켰다! → 진화시키셨습니다!"""
        assert _to_supreme("진화시켰다!") == "진화시키셨습니다!"

    def test_잡았다(self):
        """잡았다! → 잡으셨습니다!"""
        assert _to_supreme("잡았다!") == "잡으셨습니다!"


# ── format_actor ──

# config.SUBSCRIPTION_TIERS mock
_MOCK_TIERS = {
    "basic": {"benefits": {"honorific": "polite"}},
    "channel_owner": {"benefits": {"honorific": "supreme"}},
}


class TestFormatActor:
    @patch("utils.honorific.SUBSCRIPTION_TIERS", _MOCK_TIERS, create=True)
    def test_일반(self):
        result = format_actor("문유", "포켓볼을 던졌다!", None)
        assert result == "문유 포켓볼을 던졌다!"

    @patch("utils.honorific.SUBSCRIPTION_TIERS", _MOCK_TIERS, create=True)
    def test_베이직(self):
        result = format_actor("문유", "포켓볼을 던졌다!", "basic")
        assert "문유님이" in result
        assert "습니다" in result

    @patch("utils.honorific.SUBSCRIPTION_TIERS", _MOCK_TIERS, create=True)
    def test_채널장(self):
        result = format_actor("문유", "포켓볼을 던졌다!", "channel_owner")
        assert "문유님께서" in result
        assert "셨습니다" in result

    @patch("utils.honorific.SUBSCRIPTION_TIERS", _MOCK_TIERS, create=True)
    def test_english_no_honorific(self):
        result = format_actor("Moon", "threw a ball!", None, lang="en")
        assert result == "Moon threw a ball!"

    @patch("utils.honorific.SUBSCRIPTION_TIERS", _MOCK_TIERS, create=True)
    def test_english_polite(self):
        result = format_actor("Moon", "threw a ball!", "basic", lang="en")
        assert "Mr. Moon" in result


# ── format_target_action ──

class TestFormatTargetAction:
    @patch("utils.honorific.SUBSCRIPTION_TIERS", _MOCK_TIERS, create=True)
    def test_일반_대상(self):
        result = format_target_action("Shawn", "문유", "티배깅했다!", None)
        assert "Shawn이" in result
        assert "문유에게" in result

    @patch("utils.honorific.SUBSCRIPTION_TIERS", _MOCK_TIERS, create=True)
    def test_채널장_대상(self):
        result = format_target_action("Shawn", "문유", "티배깅했다!", "channel_owner")
        assert "감히" in result
        assert "문유님께" in result


# ── honorific_name ──

class TestHonorificName:
    @patch("utils.honorific.SUBSCRIPTION_TIERS", _MOCK_TIERS, create=True)
    def test_일반(self):
        assert honorific_name("문유", None) == "문유"

    @patch("utils.honorific.SUBSCRIPTION_TIERS", _MOCK_TIERS, create=True)
    def test_베이직(self):
        assert honorific_name("문유", "basic") == "문유님"

    @patch("utils.honorific.SUBSCRIPTION_TIERS", _MOCK_TIERS, create=True)
    def test_english_supreme(self):
        assert honorific_name("Moon", "channel_owner", lang="en") == "Sir Moon"

    @patch("utils.honorific.SUBSCRIPTION_TIERS", _MOCK_TIERS, create=True)
    def test_chinese(self):
        assert honorific_name("文", "basic", lang="zh-hans") == "文先生"


# ── honorific_catch_verb ──

class TestHonorificCatchVerb:
    @patch("utils.honorific.SUBSCRIPTION_TIERS", _MOCK_TIERS, create=True)
    def test_일반(self):
        assert honorific_catch_verb("포획!", None) == "포획!"

    @patch("utils.honorific.SUBSCRIPTION_TIERS", _MOCK_TIERS, create=True)
    def test_베이직_명사(self):
        """명사형 동사: 포획 → 포획했습니다!"""
        assert honorific_catch_verb("포획!", "basic") == "포획했습니다!"

    @patch("utils.honorific.SUBSCRIPTION_TIERS", _MOCK_TIERS, create=True)
    def test_채널장_명사(self):
        assert honorific_catch_verb("포획!", "channel_owner") == "포획하셨습니다!"

    @patch("utils.honorific.SUBSCRIPTION_TIERS", _MOCK_TIERS, create=True)
    def test_잡았다_베이직(self):
        assert honorific_catch_verb("잡았다!", "basic") == "잡았습니다!"

    @patch("utils.honorific.SUBSCRIPTION_TIERS", _MOCK_TIERS, create=True)
    def test_english_no_change(self):
        """영어는 변환 없음."""
        assert honorific_catch_verb("Caught!", "basic", lang="en") == "Caught!"
