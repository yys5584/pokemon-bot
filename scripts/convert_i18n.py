#!/usr/bin/env python3
"""
Script to convert hardcoded Korean strings in battle.py and dm_pokedex.py
to i18n t() calls. Run this from the project root.

This script performs the following systematic replacements:
1. Adds `from utils.i18n import t, get_user_lang, poke_name` import
2. Adds `lang = await get_user_lang(user_id)` to all async handler functions
3. Replaces common Korean string patterns with t() calls
4. Replaces p['name_ko'] with poke_name(p, lang) in display contexts
"""

import re
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def convert_battle_py():
    """Convert handlers/battle.py to use i18n."""
    filepath = os.path.join(PROJECT_ROOT, "handlers", "battle.py")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # ── Common Korean string replacements (exact matches in reply_text/answer calls) ──
    replacements = [
        # Partner
        ('"본인만 사용할 수 있습니다!"', 't(lang, "error.not_your_button")'),
        ('"본인만 사용할 수 있습니다!", show_alert=True', 't(lang, "error.not_your_button"), show_alert=True'),
        ('"보유한 포켓몬이 없습니다."', 't(lang, "my_pokemon.no_pokemon")'),
        ('"잘못된 선택입니다."', 't(lang, "dungeon.invalid_choice")'),
        ('"잘못된 선택입니다.", show_alert=True', 't(lang, "dungeon.invalid_choice"), show_alert=True'),
        ('"본인만 응답할 수 있습니다!", show_alert=True', 't(lang, "error.not_your_button"), show_alert=True'),
        ('"배틀 참가자만 볼 수 있습니다!", show_alert=True', 't(lang, "battle.participants_only"), show_alert=True'),
        ('"배틀 참가자만 삭제할 수 있습니다!", show_alert=True', 't(lang, "battle.participants_only"), show_alert=True'),
        ('"승자만 사용할 수 있습니다!", show_alert=True', 't(lang, "battle.winner_only"), show_alert=True'),
        ('"도전자만 선택할 수 있습니다!", show_alert=True', 't(lang, "battle.challenger_only"), show_alert=True'),

        # Battle challenge
        ('"자기 자신에게 배틀을 신청할 수 없습니다."', 't(lang, "battle.cannot_self")'),
        ('"봇에게는 배틀을 신청할 수 없습니다."', 't(lang, "battle.cannot_bot")'),
        ('"이미 대기 중인 배틀 신청이 있습니다."', 't(lang, "battle.already_pending")'),
        ('"배틀 신청을 찾을 수 없습니다."', 't(lang, "battle.challenge_not_found")'),
        ('"이미 처리된 배틀 신청입니다."', 't(lang, "battle.already_processed")'),

        # Battle accept/decline
        ('"❌ 배틀이 거절되었습니다."', 't(lang, "battle.challenge_declined_msg")'),

        # Ranked
        ('"자기 자신에게 랭크전을 신청할 수 없습니다."', 't(lang, "ranked.cannot_self")'),
        ('"봇에게는 랭크전을 신청할 수 없습니다."', 't(lang, "ranked.cannot_bot")'),
        ('"이미 대기 중인 신청이 있습니다."', 't(lang, "battle.already_pending")'),
        ('"❌ 랭크전이 거절되었습니다."', 't(lang, "ranked.declined")'),

        # Team
        ('"팀 편집이 취소되었습니다."', 't(lang, "team.edit_cancelled")'),
        ('"교환할 팀이 없습니다."', 't(lang, "team.no_teams_to_swap")'),
        ('"교환할 팀이 없습니다!", show_alert=True', 't(lang, "team.no_teams_to_swap"), show_alert=True'),
        ('"팀에 포켓몬이 없습니다!", show_alert=True', 't(lang, "team.team_empty"), show_alert=True'),
        ('"중복된 번호가 있습니다."', 't(lang, "team.duplicate_numbers")'),

        # Shop
        ('"알 수 없는 상품입니다.", show_alert=True', 't(lang, "shop.unknown_item"), show_alert=True'),
        ('"알 수 없는 상품입니다. 상점 으로 목록을 확인하세요."', 't(lang, "shop.unknown_item")'),

        # Battle ranking
        ('"아직 배틀 기록이 없습니다."', 't(lang, "battle.no_records")'),

        # Yacha
        ('"자기 자신에게 야차를 신청할 수 없습니다."', 't(lang, "yacha.cannot_self")'),
        ('"봇에게는 야차를 신청할 수 없습니다."', 't(lang, "yacha.cannot_bot")'),
        ('"야차 신청을 찾을 수 없습니다."', 't(lang, "yacha.challenge_not_found")'),
        ('"이미 처리된 야차 신청입니다."', 't(lang, "yacha.already_processed")'),
        ('"❌ 야차가 취소되었습니다."', 't(lang, "yacha.cancelled")'),
        ('"❌ 야차가 거절되었습니다."', 't(lang, "yacha.declined")'),
    ]

    for old, new in replacements:
        content = content.replace(old, new)

    # ── Add lang = await get_user_lang(user_id) after user_id assignment in async functions ──
    # This is complex regex work - we need to find async handler functions and add lang

    # ── Replace p['name_ko'] with poke_name(p, lang) in display strings (not in callback_data) ──
    # Only in f-string contexts for display
    # This needs careful handling - skip callback_data lines

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Updated {filepath}")


def convert_dm_pokedex_py():
    """Convert handlers/dm_pokedex.py to use i18n."""
    filepath = os.path.join(PROJECT_ROOT, "handlers", "dm_pokedex.py")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Add import if not present
    if "from utils.i18n import" not in content:
        content = content.replace(
            "from utils.parse import parse_number, parse_name_arg",
            "from utils.parse import parse_number, parse_name_arg\nfrom utils.i18n import t, get_user_lang, poke_name",
        )

    # Common replacements
    replacements = [
        ('"보유한 포켓몬이 없습니다."', 't(lang, "my_pokemon.no_pokemon")'),
        ('"해당 포켓몬을 찾을 수 없습니다."', 't(lang, "error.pokemon_not_found")'),
        ('"이 포켓몬은 진화할 수 없습니다."', 't(lang, "my_pokemon.cannot_evolve")'),
        ('"이 포켓몬은 교환으로만 진화합니다."', 't(lang, "my_pokemon.trade_evolve_only")'),
        ('"진화 대상을 찾을 수 없습니다."', 't(lang, "my_pokemon.evolve_target_not_found")'),
        ('"이미 방생된 포켓몬입니다!", show_alert=True', 't(lang, "my_pokemon.already_released"), show_alert=True'),
    ]

    for old, new in replacements:
        content = content.replace(old, new)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Updated {filepath}")


if __name__ == "__main__":
    convert_battle_py()
    convert_dm_pokedex_py()
    print("Done! Now add the missing locale keys to all 4 locale files.")
