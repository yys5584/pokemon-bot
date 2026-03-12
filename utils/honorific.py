"""구독 등급별 존댓말 시스템 (자낳괴 컨셉).

일반:   "문유가 포케볼을 던졌다!"
베이직: "문유님이 포케볼을 던졌습니다!"
채널장: "문유님께서 포케볼을 던지셨습니다!"

대상:
일반:   "Shawn이 문유에게 티배깅했다!"
베이직: "Shawn이 문유님에게 티배깅을 했습니다!"
채널장: "Shawn이 감히 문유님께 티배깅했네요 흐음..!"
"""


def _get_honorific(tier: str | None) -> str | None:
    """구독 티어 → honorific 레벨. None이면 비구독."""
    if not tier:
        return None
    from config import SUBSCRIPTION_TIERS
    tier_cfg = SUBSCRIPTION_TIERS.get(tier)
    if not tier_cfg:
        return None
    return tier_cfg.get("benefits", {}).get("honorific")


def format_actor(name: str, verb_casual: str, tier: str | None) -> str:
    """행위자 존칭 포맷.

    Args:
        name: 유저 이름 (decorated name, HTML 포함 가능)
        verb_casual: 반말 동사구 (예: "포켓볼을 던졌다!")
        tier: 구독 티어 ("basic", "channel_owner", None)

    Returns:
        "문유 포켓볼을 던졌다!" / "문유님이 포켓볼을 던졌습니다!" / "문유님께서 포켓볼을 던지셨습니다!"
    """
    honorific = _get_honorific(tier)

    if honorific == "supreme":
        # 채널장: 님께서 + ~셨습니다
        polite_verb = _to_supreme(verb_casual)
        return f"{name}님께서 {polite_verb}"
    elif honorific == "polite":
        # 베이직: 님이 + ~습니다
        polite_verb = _to_polite(verb_casual)
        return f"{name}님이 {polite_verb}"
    else:
        # 일반: 기존 형태 그대로 (조사 없이)
        return f"{name} {verb_casual}"


def format_target_action(
    actor_name: str, target_name: str,
    verb_casual: str, target_tier: str | None,
) -> str:
    """타 유저가 구독자에게 행동할 때 (티배깅 등).

    Args:
        actor_name: 행동한 사람 이름
        target_name: 대상 이름
        verb_casual: 반말 동사구 (예: "티배깅했다!")
        target_tier: 대상의 구독 티어

    Returns:
        "Shawn이 문유에게 티배깅했다!" /
        "Shawn이 문유님에게 티배깅을 했습니다!" /
        "Shawn이 감히 문유님께 티배깅했네요 흐음..!"
    """
    honorific = _get_honorific(target_tier)
    actor_subj = _attach_subject_particle(actor_name)

    if honorific == "supreme":
        # 채널장 대상: 감히 ~님께 ~했네요 흐음..!
        base_verb = verb_casual.rstrip("!").rstrip("다")
        return f"{actor_subj} 감히 {target_name}님께 {base_verb}했네요 흐음..!"
    elif honorific == "polite":
        # 베이직 대상: ~님에게 ~을 했습니다!
        base_verb = verb_casual.rstrip("!").rstrip("다")
        return f"{actor_subj} {target_name}님에게 {base_verb}을 했습니다!"
    else:
        # 일반
        return f"{actor_subj} {target_name}에게 {verb_casual}"


def honorific_name(name: str, tier: str | None) -> str:
    """이름에 존칭 접미사. "문유" → "문유님"."""
    honorific = _get_honorific(tier)
    if honorific in ("polite", "supreme"):
        return f"{name}님"
    return name


def honorific_catch_verb(verb: str, tier: str | None) -> str:
    """포획 동사 존칭 변환.

    "포획!" → "포획했습니다!" / "포획하셨습니다!"
    "확정 포획!" → "확정 포획했습니다!" / "확정 포획하셨습니다!"
    "잡았다!" → "잡았습니다!" / "잡으셨습니다!"
    """
    honorific = _get_honorific(tier)
    if not honorific:
        return verb

    v = verb.rstrip("!")

    # "~았다" / "~었다" 패턴 (잡았다, 도망갔다 등) → _to_polite/_to_supreme 사용
    if v.endswith("다"):
        if honorific == "supreme":
            return _to_supreme(verb)
        elif honorific == "polite":
            return _to_polite(verb)

    # 명사형 (포획, 확정 포획 등) → ~했습니다 / ~하셨습니다
    if honorific == "supreme":
        return f"{v}하셨습니다!"
    elif honorific == "polite":
        return f"{v}했습니다!"
    return verb


# ─── 한국어 변환 헬퍼 ────────────────────────────

def _attach_subject_particle(name: str) -> str:
    """이름 뒤에 주격조사 붙이기. 받침 유무 → 이/가."""
    if not name:
        return name
    last_char = name[-1]
    # ASCII (영문 등)
    if ord(last_char) < 0xAC00 or ord(last_char) > 0xD7A3:
        return f"{name}이"
    # 한글: 받침 있으면 '이', 없으면 '가'
    code = ord(last_char) - 0xAC00
    if code % 28 == 0:
        return f"{name}가"
    return f"{name}이"


def _to_polite(verb_casual: str) -> str:
    """반말 → 존칭 (습니다 체).
    "던졌다!" → "던졌습니다!"
    "신청했다!" → "신청했습니다!"
    "진화시켰다!" → "진화시켰습니다!"
    """
    # "~했다!" / "~다!" → "~했습니다!" / "~습니다!"
    v = verb_casual.rstrip("!")
    if v.endswith("다"):
        v = v[:-1] + "습니다"
    return v + "!"


def _to_supreme(verb_casual: str) -> str:
    """반말 → 극존칭 (셨습니다 체).
    "던졌다!" → "던지셨습니다!"
    "신청했다!" → "신청하셨습니다!"
    "진화시켰다!" → "진화시키셨습니다!"
    """
    v = verb_casual.rstrip("!")

    # "~했다" → "~하셨습니다"
    if v.endswith("했다"):
        return v[:-2] + "하셨습니다!"
    # "~졌다" (던졌다, 잡았다 류) → "~지셨습니다"
    if v.endswith("졌다"):
        return v[:-2] + "지셨습니다!"
    # "~켰다" (진화시켰다) → "~키셨습니다"
    if v.endswith("켰다"):
        return v[:-2] + "키셨습니다!"
    # "~았다" / "~었다" → 기본 변환
    if v.endswith("았다"):
        return v[:-2] + "으셨습니다!"
    if v.endswith("었다"):
        return v[:-2] + "으셨습니다!"
    # 기타: 그냥 습니다 변환
    if v.endswith("다"):
        return v[:-1] + "셨습니다!"
    return v + "셨습니다!"
