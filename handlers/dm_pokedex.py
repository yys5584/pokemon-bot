"""DM handlers for Pokedex and My Pokemon."""

import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ContextTypes

import config
from database import queries
from utils.helpers import hearts_display, rarity_display, escape_html
from utils.card_generator import generate_card

logger = logging.getLogger(__name__)

POKEDEX_PAGE_SIZE = 10
ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "pokemon")


async def pokedex_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /도감 or /pokedex command (DM only)."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    display_name = update.effective_user.first_name or "트레이너"

    await queries.ensure_user(user_id, display_name, update.effective_user.username)

    # Check if searching for a specific Pokemon name
    from utils.parse import parse_args, parse_number
    text = (update.message.text or "").strip()
    args = parse_args(text)

    if args and not args[0].isdigit():
        # Pokemon name search: "도감 파이리"
        name_query = " ".join(args)
        await _show_pokemon_detail(update, user_id, name_query)
        return

    # Get user's pokedex entries
    pokedex = await queries.get_user_pokedex(user_id)
    caught_ids = {p["pokemon_id"]: p for p in pokedex}
    total = len(caught_ids)

    # Get user info for title
    user = await queries.get_user(user_id)
    title_part = f" {user['title_emoji']} {user['title']}" if user and user["title"] else ""

    # Page handling
    page = 0
    num = parse_number(text)
    if num is not None:
        page = num - 1

    # Build Pokedex display
    all_pokemon = await queries.get_all_pokemon()
    start = page * POKEDEX_PAGE_SIZE
    end = start + POKEDEX_PAGE_SIZE
    page_pokemon = all_pokemon[start:end]
    total_pages = (len(all_pokemon) + POKEDEX_PAGE_SIZE - 1) // POKEDEX_PAGE_SIZE

    lines = [f"🏅 {escape_html(display_name)}의 도감 ({total}/151){title_part}\n"]

    for pm in page_pokemon:
        pid = pm["id"]
        if pid in caught_ids:
            entry = caught_ids[pid]
            evo_mark = " ★진화" if entry["method"] == "evolve" else ""
            trade_mark = " 🔄교환" if entry["method"] == "trade" else ""
            lines.append(
                f"{pid:03d} {pm['emoji']} {pm['name_ko']}{evo_mark}{trade_mark}"
            )
        else:
            lines.append(f"{pid:03d} ・ ???")

    lines.append(f"\n수집률: {total / 151 * 100:.1f}%  ({page + 1}/{total_pages})")

    # Pagination buttons
    buttons = []
    if page > 0:
        buttons.append(
            InlineKeyboardButton("◀ 이전", callback_data=f"dex_{page}")
        )
    if end < len(all_pokemon):
        buttons.append(
            InlineKeyboardButton("다음 ▶", callback_data=f"dex_{page + 2}")
        )

    markup = InlineKeyboardMarkup([buttons]) if buttons else None

    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=markup,
    )


async def pokedex_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Pokedex pagination callback."""
    query = update.callback_query
    if not query or not query.data.startswith("dex_"):
        return

    await query.answer()

    user_id = query.from_user.id
    page = int(query.data.split("_")[1]) - 1

    pokedex = await queries.get_user_pokedex(user_id)
    caught_ids = {p["pokemon_id"]: p for p in pokedex}
    total = len(caught_ids)

    user = await queries.get_user(user_id)
    display_name = user["display_name"] if user else "트레이너"
    title_part = f" {user['title_emoji']} {user['title']}" if user and user["title"] else ""

    all_pokemon = await queries.get_all_pokemon()
    start = page * POKEDEX_PAGE_SIZE
    end = start + POKEDEX_PAGE_SIZE
    page_pokemon = all_pokemon[start:end]
    total_pages = (len(all_pokemon) + POKEDEX_PAGE_SIZE - 1) // POKEDEX_PAGE_SIZE

    lines = [f"🏅 {escape_html(display_name)}의 도감 ({total}/151){title_part}\n"]

    for pm in page_pokemon:
        pid = pm["id"]
        if pid in caught_ids:
            entry = caught_ids[pid]
            evo_mark = " ★진화" if entry["method"] == "evolve" else ""
            trade_mark = " 🔄교환" if entry["method"] == "trade" else ""
            lines.append(
                f"{pid:03d} {pm['emoji']} {pm['name_ko']}{evo_mark}{trade_mark}"
            )
        else:
            lines.append(f"{pid:03d} ・ ???")

    lines.append(f"\n수집률: {total / 151 * 100:.1f}%  ({page + 1}/{total_pages})")

    buttons = []
    if page > 0:
        buttons.append(
            InlineKeyboardButton("◀ 이전", callback_data=f"dex_{page}")
        )
    if end < len(all_pokemon):
        buttons.append(
            InlineKeyboardButton("다음 ▶", callback_data=f"dex_{page + 2}")
        )

    markup = InlineKeyboardMarkup([buttons]) if buttons else None

    try:
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=markup,
        )
    except Exception:
        pass  # Message might not have changed


async def my_pokemon_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /내포켓몬 command (DM only)."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or "트레이너",
        update.effective_user.username,
    )

    pokemon_list = await queries.get_user_pokemon_list(user_id)

    if not pokemon_list:
        await update.message.reply_text(
            "보유한 포켓몬이 없습니다.\n"
            "그룹 채팅방에서 ㅊ 으로 잡아보세요!"
        )
        return

    # Check if a specific index was given: "내포켓몬 3"
    from utils.parse import parse_number
    text = (update.message.text or "").strip()
    num = parse_number(text)
    idx = (num - 1) if num is not None else 0
    idx = max(0, min(idx, len(pokemon_list) - 1))

    await _send_my_pokemon_page(update.message, user_id, pokemon_list, idx)


async def _send_my_pokemon_page(message, user_id: int, pokemon_list: list, idx: int):
    """Send a single Pokemon card with photo and navigation buttons."""
    p = pokemon_list[idx]
    total = len(pokemon_list)

    hearts = hearts_display(p["friendship"])
    evo_text = ""
    if p["evolves_to"] and p["evolution_method"] == "friendship" and p["friendship"] >= 5:
        evo_text = "\n✨ 진화 가능! → 진화 " + str(idx + 1)
    elif p["evolves_to"] and p["evolution_method"] == "trade":
        evo_text = "\n🔄 교환으로 진화 가능"

    # Master ball count
    master_balls = await queries.get_master_balls(user_id)
    ball_text = f"\n🟣 마스터볼: {master_balls}개" if master_balls > 0 else ""

    caption = (
        f"🎒 내 포켓몬 ({idx + 1}/{total}){ball_text}\n\n"
        f"{p['emoji']} {p['name_ko']}\n"
        f"친밀도: {hearts}{evo_text}\n\n"
        f"밥 {idx + 1} / 놀기 {idx + 1}"
    )

    # Navigation buttons
    buttons = []
    if idx > 0:
        buttons.append(
            InlineKeyboardButton("◀ 이전", callback_data=f"mypoke_{user_id}_{idx - 1}")
        )
    if idx < total - 1:
        buttons.append(
            InlineKeyboardButton("다음 ▶", callback_data=f"mypoke_{user_id}_{idx + 1}")
        )
    markup = InlineKeyboardMarkup([buttons]) if buttons else None

    pid = p["pokemon_id"]
    image_path = os.path.join(ASSETS_DIR, f"{pid}.png")

    if os.path.exists(image_path):
        with open(image_path, "rb") as f:
            await message.reply_photo(photo=f, caption=caption, reply_markup=markup)
    else:
        await message.reply_text(caption, reply_markup=markup)


async def my_pokemon_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 내포켓몬 pagination callback."""
    query = update.callback_query
    if not query or not query.data.startswith("mypoke_"):
        return

    await query.answer()

    parts = query.data.split("_")
    # mypoke_{user_id}_{idx}
    user_id = int(parts[1])
    idx = int(parts[2])

    # Only the owner can navigate
    if query.from_user.id != user_id:
        return

    pokemon_list = await queries.get_user_pokemon_list(user_id)
    if not pokemon_list:
        return

    idx = max(0, min(idx, len(pokemon_list) - 1))
    p = pokemon_list[idx]
    total = len(pokemon_list)

    hearts = hearts_display(p["friendship"])
    evo_text = ""
    if p["evolves_to"] and p["evolution_method"] == "friendship" and p["friendship"] >= 5:
        evo_text = "\n✨ 진화 가능! → 진화 " + str(idx + 1)
    elif p["evolves_to"] and p["evolution_method"] == "trade":
        evo_text = "\n🔄 교환으로 진화 가능"

    caption = (
        f"🎒 내 포켓몬 ({idx + 1}/{total})\n\n"
        f"{p['emoji']} {p['name_ko']}\n"
        f"친밀도: {hearts}{evo_text}\n\n"
        f"밥 {idx + 1} / 놀기 {idx + 1}"
    )

    buttons = []
    if idx > 0:
        buttons.append(
            InlineKeyboardButton("◀ 이전", callback_data=f"mypoke_{user_id}_{idx - 1}")
        )
    if idx < total - 1:
        buttons.append(
            InlineKeyboardButton("다음 ▶", callback_data=f"mypoke_{user_id}_{idx + 1}")
        )
    markup = InlineKeyboardMarkup([buttons]) if buttons else None

    pid = p["pokemon_id"]
    image_path = os.path.join(ASSETS_DIR, f"{pid}.png")

    # For photo messages, we need to edit media + caption
    try:
        if os.path.exists(image_path):
            from telegram import InputMediaPhoto
            with open(image_path, "rb") as f:
                await query.edit_message_media(
                    media=InputMediaPhoto(media=f, caption=caption),
                    reply_markup=markup,
                )
        else:
            await query.edit_message_caption(caption=caption, reply_markup=markup)
    except Exception:
        pass


# --- Pokemon TMI data (웃긴 버전) ---
POKEMON_TMI = {
    1: "식물이야 동물이야? 30년째 학계 논쟁 중. 비건들도 혼란스러워함.",
    2: "등에 꽃봉오리가 자라면서 허리가 점점 아파온다. 포켓몬계 디스크 환자 1호.",
    3: "메가진화하면 꽃이 더 커짐. 허리는 괜찮은 건지 아무도 안 물어봐줌.",
    4: "꼬리불 꺼지면 죽는다는데 수영 수업은 어떻게 했을까. 체육 면제?",
    5: "사춘기 파이리. 말 안 듣고 반항하기 시작함. 진화의 과정입니다.",
    6: "2021년 PSA 10 1판 카드가 약 4.2억원에 낙찰됨. 포켓몬계 비트코인. 근데 드래곤 타입 아님.",
    7: "선글라스 쓴 꼬부기 부대가 애니 최고 인기 에피소드. 멋짐의 정의를 다시 쓴 거북이.",
    8: "귀가 푹신해 보이지만 사실 날카로운 무기. 겉보기에 속으면 안 되는 포켓몬.",
    9: "등에서 대포를 쏘는데 반동으로 안 날아가는 게 더 신기함. 뉴턴 뒤집는 거북이.",
    10: "지우가 처음 잡은 포켓몬. 몬스터볼 안 쓰고 맨손으로 잡음. 스킬 이슈.",
    11: "'굳히기'만 쓸 수 있는 비극의 포켓몬. 이 녀석 인생이 참 단단하다.",
    12: "지우의 버터플이 떠나는 장면에서 안 울었으면 사람이 아님. 공식 눈물 유발 1위.",
    13: "캐터피의 라이벌인데 아무도 관심 없음. 포켓몬계 만년 조연.",
    14: "단데기랑 뭐가 다른지 솔직히 설명할 수 있는 사람 0명.",
    15: "메가진화까지 받았는데도 대우가 안 좋은 비운의 벌. 꿀은 안 만듦.",
    16: "어딜 가나 있는 비둘기. 근데 참새 크기. 비둘기라 우기는 참새.",
    17: "사춘기 구구. 머리 깃털이 드디어 멋있어지는 시기. 앞머리 세팅 완료.",
    18: "마하 2로 날 수 있다는데 소닉붐으로 동네가 매일 개판이 될 듯.",
    19: "이빨이 평생 자라서 뭔가를 계속 갉아야 함. 치과비는 걱정 없는 포켓몬.",
    20: "꼬렛이 진화하면 갑자기 위엄이 생김. 쥐 주제에 간지라니. 인생역전.",
    21: "성격이 더럽기로 유명. 눈 마주치면 바로 공격함. 동네 양아치 참새.",
    22: "목이 긴 이유가 땅속 먹이 먹으려고. 기린의 새 버전. 진화의 신비.",
    23: "이름 거꾸로 하면 '보아'(뱀). 영어 이름 Ekans도 Snake 거꾸로. 작명 천재.",
    24: "가슴 무늬가 무서운 얼굴인데 실제론 순한 편. 포켓몬계 강한 척하는 소심이.",
    25: "원래 주인공 파트너는 삐삐였는데 급 교체됨. 연간 로열티만 수조원. 인생역전 아이콘.",
    26: "피카츄가 너무 인기라 진화형인데 오히려 비인기. 형이 동생한테 밀리는 케이스.",
    27: "알로라 지방에선 얼음타입. 원래 사막인데 직장 때문에 극지방으로 이사 간 케이스.",
    28: "등의 가시가 사실 말린 피부. 각질 관리 안 하면 이렇게 됩니다. 보습 중요.",
    29: "수컷보다 뿔이 작지만 독은 더 강함. 크기가 전부가 아니라는 증거.",
    30: "진화하면 알을 못 낳게 된다는 게임 설정이 있음. 포켓몬 최대 미스터리 중 하나.",
    31: "새끼를 지킬 때 가장 강해짐. 한국 엄마들과 공통점 다수 발견.",
    32: "큰 귀가 레이더 역할. 엄마가 뒷담화하면 바로 알아채는 수준의 청력.",
    33: "등이 다이아몬드보다 단단하다면서 왜 격투기에 약한 건지... 설정 오류 의심.",
    34: "꼬리 한 번 휘두르면 전봇대가 부러짐. 이사할 때 절대 데려가면 안 되는 포켓몬.",
    35: "원래 피카츄 대신 주인공 파트너 후보였음. 오디션 탈락 후 조용히 살고 있음.",
    36: "보름달 밤에 모여서 춤추는 모습이 목격됨. 포켓몬계 새벽 클럽러.",
    37: "꼬리 6개로 태어나서 9개까지 늘어남. 꼬리 관리비가 장난 아닐 듯. 미용실 단골.",
    38: "1000년 산다는 전설. 연금보험 가입 추천. 복리의 마법을 누릴 수 있는 유일한 포켓몬.",
    39: "노래 부르면 모두 잠듦. 본인은 열심히 부르는데 관객이 다 자는 비극의 가수.",
    40: "풍선처럼 탄력 있어서 한번 튀면 멈출 수 없음. 인간 에어바운스.",
    41: "동굴만 가면 100% 조우. 포켓몬 역사상 가장 귀찮은 존재 부동의 1위.",
    42: "피를 빨 때 혈액형으로 맛을 구분함. 혈액형 성격론의 원조일지도?",
    43: "이름이 '뚜벅뚜벅+쵸'. 한국 작명센스가 귀여움의 극치를 달리는 포켓몬.",
    44: "기절할 정도의 악취를 풍김. 같이 사는 트레이너 존경합니다. 진심으로.",
    45: "꽃가루가 알레르기 유발. 봄철에 기상캐스터가 라플레시아 주의보 내려야 함.",
    46: "등의 버섯이 본체를 조종한다는 설이 있음. 포켓몬계 좀비 호러의 시작.",
    47: "버섯이 커지면 본체가 약해짐. 사실상 버섯이 진짜 주인공. 충격 반전.",
    48: "눈이 레이더라서 밤에도 벌레 잡아냄. 야간에 마주치면 눈 빛나서 무서울 듯.",
    49: "적을 쫓을 때 인분을 뿌림. 전략적이긴 한데... 위생 관념이 좀 우려됨.",
    50: "땅 밑 몸통이 어떻게 생겼는지 30년째 미스터리. 팬아트 상상력 자극 1위.",
    51: "세쌍둥이가 하나의 몸. 셋이서 월세 나눠 내는 건지 궁금해지는 포켓몬.",
    52: "로켓단 나옹은 인간어를 독학한 천재. 근데 월급은 0원. 노동착취.",
    53: "사장님 고양이 느낌. 비싼 캔사료만 먹을 것 같은 포스. 6개 수염은 레이더.",
    54: "만성 두통 환자. 두통약 CF 모델 1순위 후보. 타이레놀 러브콜 기다리는 중.",
    55: "올림픽 수영선수보다 빠름. 근데 포켓몬 올림픽은 없음. 능력 낭비.",
    56: "화나면 강해지지만 머리가 나빠짐. 분노 조절의 중요성을 알려주는 교육용 포켓몬.",
    57: "화나면 닥치는 대로 때림. 격투게임 초보자의 플레이 스타일 그 자체.",
    58: "충성심 MAX. 포켓몬계 진돗개. 한 번 따르면 끝까지 따르는 갓독.",
    59: "하루 1만 리를 달림. 기름값 안 드는 오토바이. 유지비 사료값뿐.",
    60: "피부가 투명해서 내장이 소용돌이 모양으로 비침. TMI의 원조. 과한 공유.",
    61: "항상 땀을 흘림. 긴장하는 게 아니라 건강한 거래요. 오해하지 마세요.",
    62: "수영+격투 만능. 포켓몬계 철인3종 선수. 헬스장 PT도 가능할 듯.",
    63: "하루 18시간 잠. 위험하면 자면서 순간이동으로 도망감. 꿈의 직장인 라이프.",
    64: "숟가락 구부리기 특기. 실제로 초능력자 유리겔러가 닌텐도 고소했었음. 실화임.",
    65: "IQ 5000. 인류 역사상 가장 똑똑한 생물체. 근데 10살짜리 트레이너한테 잡힘.",
    66: "어른 100명을 가볍게 들어올림. 이사짐센터 즉시 채용 가능. 면접 면제.",
    67: "달리는 기차도 멈춰 세움. 2초에 1000발 펀치. 교통법규 위반 아닌가 이거.",
    68: "이사짐센터에서 아르바이트한다는 게 공식 설정. 시급이 궁금해지는 포켓몬.",
    69: "도감번호 69. 인터넷이 좋아하는 그 숫자. 그냥 풀 포켓몬인데 밈이 됨.",
    70: "산성 액체로 먹이를 녹여 먹음. 소화제 필요 없는 포켓몬. 위장 최강.",
    71: "뭐든 삼킴. 포켓몬계 먹방 유튜버. 먹지 못하는 게 없음. 구독 좋아요.",
    72: "몸의 99%가 물. 다이어트 중이신 분들이 부러워하는 체질. 수분 충전 완료.",
    73: "촉수 80개로 독 주입. 문어 다리 8개도 복잡한데 80개라니. 관리가 대단함.",
    74: "산길에서 돌인 줄 알고 밟으면 화냄. 등산객 전문 몰래카메라 포켓몬.",
    75: "산 정상까지 올라가서 스스로 굴러 떨어짐. 시지프스 신화 포켓몬 버전.",
    76: "1년에 한 번 탈피. 피부관리의 달인. 피부과 추천 포켓몬.",
    77: "태어나자마자 겨우 서는데 달리면서 다리가 강해짐. 인생 요약 한 줄.",
    78: "시속 240km. 갈기가 불꽃처럼 타오름. 고속도로 과속 단속 대상 1호.",
    79: "꼬리 잘려도 아픔을 못 느낌. 멍때리기 세계챔피언. 스트레스 제로 라이프.",
    80: "꼬리에 셀러가 물려서 진화함. 기생인지 공생인지 30년째 논쟁 중.",
    81: "전자파로 기계 망가뜨림. 정전 나면 이 녀석 탓일 수 있음. IT회사 근처 출몰 주의.",
    82: "3마리가 합체. 볼타론인지 마징가인지. 합체 로봇 원조 포켓몬.",
    83: "항상 파를 들고 다님. 장봐서 집에 오시는 한국 어머니 느낌. 파값은 본인 부담.",
    84: "머리 2개가 교대로 잠잔다. 수면 시간 효율 200%. 직장인들이 부러워하는 능력.",
    85: "머리 3개가 각각 다른 생각. 회의하면 결론이 절대 안 나는 타입.",
    86: "빙산 위에서 낮잠 자는 모습이 목격됨. 지구온난화로 침대가 녹는 중...",
    87: "영하 40도에서도 활발. 에어컨 필요 없는 포켓몬. 여름에 옆에 있고 싶다.",
    88: "지나간 자리에 3년간 풀이 안 자람. 최악의 이웃. 부동산 가격 폭락 주범.",
    89: "손가락으로 땅 터치하면 풀이 시듦. 잔디밭 출입금지. 골프장 영구 퇴장.",
    90: "혀를 내밀어 공격함. 예의 없는 포켓몬 1위. 어른들이 혀 내밀지 말라고 한 이유.",
    91: "껍질 닫으면 로켓포도 못 뚫음. 방탄 조끼 제조사에서 러브콜 오는 중.",
    92: "가스로 된 몸. 바람 불면 날아감. 역대 가장 성공적인 다이어트 사례.",
    93: "벽을 통과 가능. 월세를 안 내도 되는 유일한 포켓몬. 건물주도 못 막음.",
    94: "방 온도가 갑자기 내려가면 팬텀이 근처에 있다는 뜻. 에어컨 아닙니다 도망치세요.",
    95: "8.8m 바위뱀인데 방어력이 의외로 낮음. 외강내유. 겉은 바위 속은 두부.",
    96: "잠자는 사람 꿈을 흡입. 좋은 꿈이 맛있다니 악몽은 다이어트 식단인 셈.",
    97: "진자로 최면 걸어서 꿈을 먹어치움. 포켓몬계 논란 캐릭터. 수면 클리닉 출입금지.",
    98: "집게 1만 마력인데 정밀 작업은 못함. 파워만 올리고 기술은 안 올린 스탯 실패작.",
    99: "한쪽 집게만 비대하게 발달. 팔씨름은 항상 오른팔로만. 좌우 밸런스 포기.",
    100: "몬스터볼이랑 닮아서 만지면 감전됨. 포켓몬계 몰래카메라. 속지 마세요.",
    101: "조금만 건드려도 대폭발. 성격 가장 급한 포켓몬 1위. 멀리서 감상하세요.",
    102: "6개가 텔레파시로 소통. 단톡방 필요 없는 포켓몬. 통신비 0원.",
    103: "머리 3개가 독립적으로 생각. 자아가 3개. 심리상담비 3배.",
    104: "죽은 어미의 뼈를 쓰고 다님. 보름달에 울음. 포켓몬 역대 가장 슬픈 설정. ㅠㅠ",
    105: "뼈 부메랑 기술은 오랜 수련의 결과. 호주 원주민과 공통점 있음.",
    106: "다리가 3배로 늘어남. 스트레칭의 중요성을 온몸으로 보여주는 포켓몬.",
    107: "5분에 1000발 펀치. 복싱 심판이 세다가 포기할 속도. 판정승 불가.",
    108: "2m 혀로 뭐든 핥음. 위생 관념이 많이 우려되는 포켓몬. 손 씻자.",
    109: "풍선 같은 몸에 유독가스 가득. 생일 파티에 절대 초대하면 안 됨.",
    110: "독가스 2배. 환경부 블랙리스트 1순위. 탄소배출권 거래 불가.",
    111: "빌딩에 박아도 안 아픔. 보험회사가 가장 두려워하는 포켓몬.",
    112: "다이아몬드도 뚫고 2000도 마그마도 걸어다님. 밸런스 패치가 시급한 포켓몬.",
    113: "매일 영양만점 알을 낳음. 계란값 폭등 시대에 가장 필요한 포켓몬.",
    114: "덩굴 잘라도 바로 재생됨. 미용실 가기 싫어하는 포켓몬 1위. 어차피 또 자라.",
    115: "새끼 위협하면 초사이어인 모드. 한국 학부모 상위호환. 내 새끼 건들지 마.",
    116: "먹물 뿜는 해마. 실제 해마는 안 뿜는데 판타지 마음대로 추가됨.",
    117: "독가시에 찔리면 기절. 수족관 직원 산재보험 필수 가입 대상.",
    118: "수영의 여왕이라 불림. 포켓몬 올림픽 있으면 수영 금메달 확정.",
    119: "산란기에 강을 거슬러 올라감. 금붕어인지 연어인지 정체성 혼란.",
    120: "밤에 코어가 빨갛게 깜빡임. 야간 비상 조명으로 활용 가능.",
    121: "7색으로 빛나서 '보석의 별'이라 불림. 주얼리 브랜드 모델 섭외 1순위.",
    122: "마임이 벽이라 생각하면 진짜 벽이 됨. 상상이 현실이 되는 포켓몬. 부동산 혁명.",
    123: "양팔 낫으로 잔디 깎기 가능. 조경업체 즉시 채용. 위험수당 포함.",
    124: "초기 디자인이 인종차별 논란으로 색이 보라색으로 변경됨. 포켓몬 흑역사.",
    125: "번개를 기다리며 나무 위에 서있음. 자발적 피뢰침. 전기요금 절약의 아이콘.",
    126: "표면 온도 1200도. 악수하면 안 됨. 절대로. 인사는 목례로.",
    127: "집게로 끼우면 절대 안 놓음. 포켓몬계 집착의 아이콘. 놓아줘요 제발.",
    128: "리더 정할 때 박치기. 민주적이진 않지만 확실한 방법. 국회에서 도입 검토 중(아님).",
    129: "'세상에서 가장 약하고 한심한 포켓몬' 공식 설정. 튀는 것밖에 못함. 근데 500원에 팔림.",
    130: "마을 하나 완전 파괴. 잉어킹 시절 무시한 거 후회하게 해주는 포켓몬. 인생 2막.",
    131: "인간 말을 알아듣고 슬픈 노래를 부름. 포켓몬계 발라드 가수. 앨범 내면 대박날 듯.",
    132: "뭐든 변신 가능. 포켓몬 교배 만능키. 전 세대에서 가장 바쁜 포켓몬. 과로사 주의.",
    133: "진화형이 8개(전 세대 포함). 포켓몬계 진로 고민 세계 1위. 상담사 추천.",
    134: "물에 녹아서 안 보임. 숨바꼭질 사기 캐릭터. 반칙 아닌가 이거.",
    135: "온몸 털이 전기 바늘. 귀엽지만 쓰다듬으면 감전. 터치 불가. 눈으로만 감상.",
    136: "체온 900도. 겨울에 안으면 따뜻할 줄 알았지? 화상 3도입니다.",
    137: "애니 38화에서 빛 깜빡이 연출로 일본 어린이 700명 경련. 포켓몬 역사상 최대 사건.",
    138: "화석에서 부활. 쥬라기 공원 포켓몬 버전. 이안 말콤 박사가 경고했을 텐데.",
    139: "껍질이 고대에 방탄조끼 재료였다는 설. 선사시대 군수업체 납품용.",
    140: "3억 년 전 바다에 살았음. 투구게가 모델. 실제로 살아있는 화석이라 불림.",
    141: "고대 바다 최상위 포식자. 지금 살아있으면 해수욕장 영업정지 확정.",
    142: "호박 속 유전자에서 복원. 진짜 쥬라기 공원 그 전개. 인겐 박사 오마주.",
    143: "하루 400kg 먹음. 한 달 식비만 수천만원. 절대 키우면 안 되는 포켓몬 1위.",
    144: "전설의 얼음새. 데려오면 냉장고 필요 없음. 전기세 절약.",
    145: "번개 맞으면 오히려 강해짐. 전기요금 0원의 꿈. 한전이 싫어하는 포켓몬.",
    146: "봄을 알리며 나타남. 기상청보다 정확한 계절 예보. 기상캐스터 실업 위기.",
    147: "오랫동안 환상의 포켓몬이었음. 빅풋이나 네시도 포켓몬이었으면 좋겠다.",
    148: "날씨를 바꾸는 능력. 기상청 취업 가능. 연봉 협상 유리할 듯.",
    149: "16시간 만에 지구 일주. 마하 2인 피죤투보다 빠른데 본인은 느긋한 성격. 갭모에.",
    150: "유전자 조작 인공 포켓몬. 영화에서 '나는 누구인가'로 철학의 끝을 보여줌.",
    151: "현미경으로만 보이면서 모든 기술 사용 가능. 포켓몬계 치트키. 밸런스 무시.",
}


async def _show_pokemon_detail(update: Update, user_id: int, name_query: str):
    """Show detailed info for a specific Pokemon."""
    pokemon = await queries.search_pokemon_by_name(name_query)

    if not pokemon:
        await update.message.reply_text(f"'{name_query}' 포켓몬을 찾을 수 없습니다.")
        return

    pid = pokemon["id"]
    rarity_text = rarity_display(pokemon["rarity"])

    # Check if user has it
    pokedex = await queries.get_user_pokedex(user_id)
    caught_ids = {p["pokemon_id"] for p in pokedex}
    owned = "✅ 보유 중" if pid in caught_ids else "❌ 미보유"

    # Evolution chain
    evo_line = await _build_evo_chain(pokemon)

    # TMI
    tmi = POKEMON_TMI.get(pid, "")

    lines = [
        f"{pokemon['emoji']} No.{pid:03d} {pokemon['name_ko']} ({pokemon['name_en']})",
        f"등급: {rarity_text}",
        f"포획률: {int(pokemon['catch_rate'] * 100)}%",
        f"상태: {owned}",
    ]

    if evo_line:
        lines.append(f"\n📊 진화: {evo_line}")

    if pokemon["evolution_method"] == "trade":
        lines.append("⚠️ 교환으로만 진화 가능!")

    if tmi:
        lines.append(f"\n💡 {tmi}")

    caption = "\n".join(lines)

    # Generate 16:9 card image
    card_buf = generate_card(pid, pokemon["name_ko"], pokemon["rarity"], pokemon["emoji"])
    await update.message.reply_photo(photo=card_buf, caption=caption)


async def _build_evo_chain(pokemon: dict) -> str:
    """Build evolution chain string like 파이리 → 리자드 → 리자몽"""
    chain = []

    # Go to the base form
    current = pokemon
    while current.get("evolves_from"):
        prev = await queries.get_pokemon(current["evolves_from"])
        if not prev:
            break
        current = prev

    # Walk forward
    while current:
        chain.append(f"{current['emoji']}{current['name_ko']}")
        if current.get("evolves_to"):
            nxt = await queries.get_pokemon(current["evolves_to"])
            current = nxt
        else:
            break

    return " → ".join(chain) if len(chain) > 1 else ""


# ============================================================
# Title List (all titles + how to unlock)
# ============================================================

async def title_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '칭호목록' command (DM) — show all titles and unlock conditions."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or "트레이너",
        update.effective_user.username,
    )

    # Get user's unlocked titles
    unlocked = await queries.get_user_titles(user_id)
    unlocked_ids = {ut["title_id"] for ut in unlocked}

    lines = ["🏷️ 전체 칭호 목록\n"]

    # Group by category
    categories = {
        "📚 도감 기반": ["beginner", "collector", "trainer", "master", "champion", "living_dex"],
        "🐉 전설": ["legend_hunter"],
        "🎯 활동 기반": ["first_catch", "catch_master", "run_expert", "owl", "decisive", "love_fan", "diligent"],
        "💎 수집 특화": ["furry", "rare_hunter"],
        "🟣 마스터볼": ["masterball_rich"],
        "🤝 교환": ["trader"],
    }

    for cat_name, title_ids in categories.items():
        cat_lines = []
        for tid in title_ids:
            t_info = config.UNLOCKABLE_TITLES.get(tid)
            if not t_info:
                continue
            name, emoji, desc, _, _ = t_info
            status = "✅" if tid in unlocked_ids else "🔒"
            cat_lines.append(f"  {status} {emoji} {name} — {desc}")

        if cat_lines:
            lines.append(f"\n{cat_name}")
            lines.extend(cat_lines)

    total = len(config.UNLOCKABLE_TITLES)
    got = len(unlocked_ids)
    lines.append(f"\n\n해금: {got}/{total}개")
    lines.append("'칭호' 명령어로 장착할 수 있어요!")

    await update.message.reply_text("\n".join(lines))


# ============================================================
# Title Selection
# ============================================================

async def title_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '칭호' command (DM) — show unlocked titles and let user equip one."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    display_name = update.effective_user.first_name or "트레이너"
    await queries.ensure_user(user_id, display_name, update.effective_user.username)

    # Check and unlock any new titles first
    from utils.title_checker import check_and_unlock_titles
    await check_and_unlock_titles(user_id)

    unlocked = await queries.get_user_titles(user_id)
    user = await queries.get_user(user_id)
    current_title = user.get("title", "") if user else ""

    if not unlocked:
        await update.message.reply_text(
            "🏷️ 아직 해금된 칭호가 없습니다!\n\n"
            "포켓몬을 잡고, 활동하면 칭호가 해금돼요.\n"
            "예: 첫 포획, 도감 15종, 잡기 실패 50회 등"
        )
        return

    lines = ["🏷️ 내 칭호 목록\n"]

    buttons = []
    for ut in unlocked:
        tid = ut["title_id"]
        t_info = config.UNLOCKABLE_TITLES.get(tid)
        if not t_info:
            continue
        name, emoji, desc, _, _ = t_info
        equipped = " ✅" if name == current_title else ""
        lines.append(f"{emoji} {name}{equipped} — {desc}")
        btn_label = f"{'✅ ' if name == current_title else ''}{emoji} {name}"
        buttons.append(InlineKeyboardButton(btn_label, callback_data=f"title_{tid}"))

    # Add "remove title" button
    no_title_mark = " ✅" if not current_title else ""
    lines.append(f"\n🚫 칭호 없음{no_title_mark}")
    buttons.append(InlineKeyboardButton(f"{'✅ ' if not current_title else ''}🚫 해제", callback_data="title_none"))

    # 2 buttons per row
    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "\n".join(lines) + "\n\n⬇️ 장착할 칭호를 선택하세요:",
        reply_markup=markup,
    )


async def title_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle title selection callback."""
    query = update.callback_query
    if not query or not query.data.startswith("title_"):
        return

    await query.answer()
    user_id = query.from_user.id
    title_id = query.data.replace("title_", "")

    if title_id == "none":
        await queries.equip_title(user_id, "", "")
        await query.edit_message_text("🚫 칭호를 해제했습니다.")
        return

    # Check if user has this title
    if not await queries.has_title(user_id, title_id):
        await query.edit_message_text("❌ 해금되지 않은 칭호입니다.")
        return

    t_info = config.UNLOCKABLE_TITLES.get(title_id)
    if not t_info:
        return

    name, emoji, desc, _, _ = t_info
    await queries.equip_title(user_id, name, emoji)
    await query.edit_message_text(f"✅ 칭호 장착: 「{emoji} {name}」\n\n채팅방에서 이름 옆에 표시됩니다!")
