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

    gen1 = sum(1 for pid in caught_ids if pid <= 151)
    gen2 = sum(1 for pid in caught_ids if 152 <= pid <= 251)
    lines = [f"🏅 {escape_html(display_name)}의 도감 ({total}/251){title_part}"]
    lines.append(f"1세대: {gen1}/151 | 2세대: {gen2}/100\n")

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

    lines.append(f"\n수집률: {total / 251 * 100:.1f}%  ({page + 1}/{total_pages})")

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

    gen1 = sum(1 for pid in caught_ids if pid <= 151)
    gen2 = sum(1 for pid in caught_ids if 152 <= pid <= 251)
    lines = [f"🏅 {escape_html(display_name)}의 도감 ({total}/251){title_part}"]
    lines.append(f"1세대: {gen1}/151 | 2세대: {gen2}/100\n")

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

    lines.append(f"\n수집률: {total / 251 * 100:.1f}%  ({page + 1}/{total_pages})")

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
    1: "식물이야 동물이야? AI한테 물어봐도 '복합적 존재'라고 회피함. 30년째 미해결. 분류학계 버그.",
    2: "등에 꽃봉오리 무게 때문에 목디스크 온다는 설. 포켓몬계 VDT 증후군 1호 환자.",
    3: "메가진화하면 꽃이 더 거대해짐. 허리 괜찮냐고 아무도 안 물어봐주는 관심 부족 사회.",
    4: "꼬리 불 꺼지면 사망인데 수영은 어떻게 했을까. 30년 미해결 질문. IP65 방수설 유력.",
    5: "사춘기라 말 안 듣고 불 뿜으며 반항. 중2병은 종족을 초월한다는 걸 증명하는 포켓몬.",
    6: "PSA 10 1판 카드 4.2억원(2021). 비트코인 이더리움 다 이긴 수익률. 참고로 드래곤 아님.",
    7: "선글라스 꼬부기 부대가 애니 역대 레전드. 멋짐을 재정의한 거북이. 틱톡 밈으로도 영생 중.",
    8: "귀에 달린 솜털이 럭셔리 모피처럼 보이지만 실전용 수중 장비. 패션과 실용 겸비.",
    9: "등의 대포 반동을 체중으로 버팀. 뉴턴 3법칙 기말고사에 나오면 오답 처리되는 포켓몬.",
    10: "지우의 첫 포획인데 볼도 안 씀. 요즘이면 SNS에서 '노볼챌린지'로 바이럴됐을 듯.",
    11: "평생 '굳히기' 하나로 버팀. 한 우물만 파는 장인 정신인지 선택지가 없는 건지 논쟁 중.",
    12: "지우 버터플 이별 장면에서 안 울었으면 공감 능력 테스트 필요. 30년째 최루탄 현역.",
    13: "캐터피의 라이벌인데 존재감이 0. 같은 해 데뷔한 아이돌 중 안 뜬 쪽 포지션.",
    14: "단데기와 차이점을 ChatGPT한테 물어봐도 '둘 다 비슷합니다'라고 답변 회피함.",
    15: "메가진화까지 받았는데 티어 변동 없음. 스펙을 쌓아도 대우가 안 변하는 현실 반영.",
    16: "어딜 가나 출몰하는 새. 포켓몬계 치킨집. 100m마다 하나씩 있음.",
    17: "깃털이 화려해지는 사춘기. 인스타 프로필 사진을 처음 꾸미기 시작하는 시기.",
    18: "마하 2 비행 가능. 소닉붐이 소음 민원감인데 항공법 적용 대상인지 법적 검토 필요.",
    19: "이빨이 평생 자라서 뭘 계속 갉아야 함. 전세집 가구 파손 전문. 보증금 반환 불가.",
    20: "진화하니까 갑자기 위엄이 생김. 대학 졸업 후 정장 입으면 달라 보이는 효과.",
    21: "눈 마주치면 즉시 공격. 포켓몬계 길거리 시비꾼. 눈 피하고 빠르게 지나가세요.",
    22: "목이 긴 이유가 땅속 먹이 사냥용. 기린 아니고 새인데 기린 역할. 직업 미스매치.",
    23: "이름 거꾸로 = '보아'(뱀). 영어 이름 Ekans도 Snake 거꾸로. 작명에 진심인 닌텐도.",
    24: "가슴 무늬가 무서운 얼굴인데 본인은 소심. 타투 있는데 성격 순한 사람과 같은 맥락.",
    25: "원래 파트너 후보가 삐삐였는데 급 교체. 연간 로열티 수조원. 역대급 캐스팅 성공.",
    26: "피카츄 때문에 진화형인데 비인기. 형이 동생에게 밀린 케이스. 능력은 상위 인기는 하위.",
    27: "알로라에선 얼음타입. 본사 발령으로 극지방 이사 간 포켓몬계 비자발적 전근 케이스.",
    28: "등의 가시가 사실 굳은 피부. 각질 관리 안 하면 무기가 되는 유일한 사례. 보습제 필수.",
    29: "수컷보다 뿔이 작지만 독은 더 강함. 외형이 전투력을 결정하지 않는다는 교훈.",
    30: "진화하면 알을 못 낳는 게임 설정. 의도인지 버그인지 닌텐도도 30년째 침묵.",
    31: "새끼 보호 본능 MAX. 학부모 상담에서 교사 기 죽이는 한국 엄마 에너지 그 자체.",
    32: "큰 귀가 위성 안테나급 청력. 3층에서 속삭여도 5층에서 다 들림. 사생활 없음.",
    33: "등이 다이아몬드보다 단단한데 격투에 약하다? 밸런스 담당자 30년째 해명 없음.",
    34: "꼬리 한 번에 전봇대 절단. 이사 시 동행 금지 포켓몬 1위. 보증금 회수 불가 확정.",
    35: "피카츄 대신 주인공 파트너 오디션 탈락. 오디션 프로그램 비하인드 1화 소재.",
    36: "텔레그램 크립토 씬의 전설적 여성 아이돌. 보름달 뜨면 시세가 오른다는 미신이 있다. 실체는 불명.",
    37: "꼬리 6개→9개로 성장. 미용비만 월 수십만원 예상. 털 관리 예산이 식비를 초과.",
    38: "수명 1000년. 연금보험+복리 효과하면 우주급 자산. 재테크 포켓몬계 GOAT.",
    39: "열창하면 관객 전원 수면. 실력 문제가 아니라 기술 효과라서 더 슬픈 비운의 보컬.",
    40: "풍선 같은 탄성으로 바운스하면 멈출 수 없음. 물리법칙에서 이탈한 포켓몬.",
    41: "동굴 진입 시 100% 조우. 게이머 투표 '가장 피하고 싶은 포켓몬' 만년 1위.",
    42: "혈액형으로 피 맛을 구분한다는 설. MBTI 유행 전에 혈액형 분류 시작한 원조.",
    43: "한국명 '뚜벅쵸'. 로컬라이징 작명 센스가 귀여움 한도를 초과하는 포켓몬.",
    44: "악취 레벨이 기절급. 같이 사는 트레이너는 후각을 포기한 진정한 용자. 리스펙트.",
    45: "꽃가루 알레르기 유발. 봄철에 기상청이 '라플레시아 주의보'를 발령해야 하는 포켓몬.",
    46: "등의 버섯이 본체를 조종한다는 공식 설정. 포켓몬판 라스트 오브 어스. 넷플릭스 각.",
    47: "버섯이 커질수록 본체가 약해짐. 주인공이 버섯이었다는 충격 반전 호러.",
    48: "복안이 레이더급. 야간에 눈 빛나면 CCTV 3대분 성능. 야간 경비 채용 1순위.",
    49: "적 추적 시 독가루 살포. 전략적이긴 한데 뒷처리 담당은 항상 트레이너.",
    50: "땅 밑 몸통이 30년째 미공개. 닌텐도 공식 입장도 없음. 팬아트 상상력 자극 부동의 1위.",
    51: "세쌍둥이가 하나의 몸. 화장실은 어떡하는지 누구도 질문하지 않는 암묵적 합의.",
    52: "로켓단 나옹은 인간어를 독학한 천재. 근데 연봉 0원 무급 인턴. 고용노동부 신고감.",
    53: "CEO 집 고양이 바이브. 비싼 것만 터치하는 포스. 수염 6개는 고급 센서.",
    54: "만성 두통으로 초능력 발동. 편두통이 슈퍼파워가 되는 유일한 사례. 두통약 모델 0순위.",
    55: "올림픽 수영선수보다 빠른데 포켓몬이라 출전 불가. 금메달 하나는 확실한 재능 낭비.",
    56: "화나면 강해지지만 판단력이 급락. 분노 조절 프로그램 의무 수강 대상.",
    57: "화나면 무차별 공격. 격투게임 버튼 랜덤 연타하는 초보 플레이를 현실에 구현한 포켓몬.",
    58: "충성심 만렙. 포켓몬계 진돗개. 한번 주인 정하면 끝. 군견 적성검사 만점.",
    59: "하루 1만 리 주행. 유지비 사료값뿐. 테슬라보다 싸고 자율주행도 됨. 완전 친환경.",
    60: "피부가 투명해서 내장이 소용돌이로 비침. 과잉 정보 공유의 의인화. TMI의 원조.",
    61: "항상 땀을 흘림. 체질일 뿐 긴장한 게 아님. 오해하지 마세요. 다한증 포켓몬.",
    62: "수영+격투 만능. 포켓몬계 철인3종 선수 겸 PT 트레이너. 헬스장 창업하면 대박.",
    63: "하루 18시간 수면. 위험하면 자면서 순간이동 도주. 재택근무 라이프의 이상향.",
    64: "숟가락 구부리기 특기. 실제로 유리겔러가 닌텐도를 고소했던 실화 기반 포켓몬.",
    65: "IQ 5000. 인류 역사상 최고 지능인데 10살짜리한테 잡힘. AI 반란은 없을 듯.",
    66: "성인 100명을 가볍게 듦. 이삿짐센터 서류만 내면 즉시 채용. 면접 면제.",
    67: "달리는 KTX도 멈춤. 초당 500발 펀치. 교통법규 위반인지 법률 검토 요청 중.",
    68: "이삿짐센터에서 알바한다는 게 공식 설정. 시급이 궁금한데 고용노동부만 알고 있음.",
    69: "도감번호 69. 인터넷이 좋아하는 그 숫자. 순수한 풀 포켓몬인데 숫자 하나로 밈이 됨.",
    70: "산성 액체로 먹이 용해. 소화제 불필요 체질. 위장 건강 포켓몬계 최강.",
    71: "뭐든 삼킴. 먹방 유튜버 포켓몬. 매일 업로드 가능. 광고 단가 높을 듯.",
    72: "몸의 99%가 물. 수분 보충 불필요 체질. 하루 2L 물 마시기 챌린지 평생 면제.",
    73: "촉수 80개로 독 주입. 문어 다리 8개도 관리 힘든데 80개 관리하는 극한의 성실함.",
    74: "산길에서 돌인 줄 알고 밟으면 폭발하는 화. 등산 유튜버 몰카 전문 포켓몬.",
    75: "산 정상까지 올라가서 스스로 굴러 떨어짐. 시지프스 신화 포켓몬 에디션.",
    76: "1년에 한 번 탈피로 피부 리뉴얼. 피부과 갈 필요 없는 천연 필링 시스템.",
    77: "태어나자마자 뛰면서 다리 단련. 신생아부터 운동 시작. 갓생살기의 원조.",
    78: "시속 240km. 갈기가 불꽃. 고속도로 과속 카메라에 매일 찍히는 상습 과속범.",
    79: "꼬리 잘려도 아픔 못 느낌. 멍때리기 세계챔피언. 스트레스 제로 라이프의 교과서.",
    80: "꼬리에 셀러가 물려서 진화. 기생인지 공생인지 생물학 학회 30년째 토론 중.",
    81: "전자파로 전자기기 고장. 서버실 근처 출몰 시 IT팀 비상. 원인 불명 정전의 진범.",
    82: "3마리 합체. 합체 로봇 장르의 원조 포켓몬. 마징가보다 먼저였다고 주장 가능.",
    83: "항상 파를 들고 다님. 장봐서 귀가하시는 한국 어머니 비주얼. 파값은 본인 부담.",
    84: "머리 2개가 교대 수면. 수면 효율 200%. 워라밸을 초월한 수면밸의 끝.",
    85: "머리 3개가 각각 다른 의견. 팀 회의하면 결론이 절대 안 나옴. 의사결정 마비.",
    86: "빙산 위 낮잠이 일상인데 지구온난화로 침대가 녹는 중. 기후 위기 체감 포켓몬.",
    87: "영하 40도에서 활발. 천연 에어컨. 여름 전기세 폭탄 해결. 동거 신청자 폭주.",
    88: "지나간 자리 3년간 풀 안 자람. 최악의 이웃. 부동산 급매 사유 1위.",
    89: "손가락 터치만으로 식물 즉사. 잔디밭 영구 출입금지. 골프장 반경 1km 접근 불가.",
    90: "혀를 내밀어 공격. 예의 없는 포켓몬 1위. 부모님이 혀 내밀지 말라는 이유.",
    91: "껍질 닫으면 미사일도 못 뚫음. 방산업체에서 소재 분석 의뢰가 쇄도 중.",
    92: "가스 몸이라 바람 불면 증발. 체중 0.1kg. 역대 가장 극단적 체중 감량 사례.",
    93: "벽을 통과해서 월세 불필요. 건물주도 퇴거 불가. 전세 사기와 무관한 유일한 존재.",
    94: "방 온도가 갑자기 내려가면 이 녀석이 근처에 있다는 뜻. 에어컨이 아닙니다. 대피하세요.",
    95: "8.8m 바위뱀인데 방어력 의외로 약함. 겉바속촉 포켓몬. 외강내유의 교과서.",
    96: "잠자는 사람 꿈을 흡입하는 미식가. 좋은 꿈이 맛있고 악몽은 칼로리 낮은 다이어트식.",
    97: "진자로 최면 걸어 꿈을 먹음. 수면 클리닉 영구 출입금지. 포켓몬계 빌런 상위권.",
    98: "집게 1만 마력인데 정밀 작업 불가. 파워만 올리고 기술은 0인 스탯 미스.",
    99: "한쪽 집게만 비대 발달. 좌우 밸런스를 완전히 포기한 극단적 특화형.",
    100: "몬스터볼로 위장해서 만지면 감전. 포켓몬계 피싱 사기. 절대 속지 마세요.",
    101: "조금만 건드려도 폭발. 성격 가장 급한 포켓몬 부동의 1위. 안전거리 확보 필수.",
    102: "6개가 텔레파시 소통. 단톡방 불필요. 통신비 평생 0원. 통신사가 싫어하는 포켓몬.",
    103: "머리 3개가 독립적 사고. 자아가 3개라 MBTI도 3개. 심리상담비 3배 청구.",
    104: "죽은 어미의 뼈를 쓰고 보름달에 울음. 포켓몬 역대 가장 슬픈 설정. 눈물 주의.",
    105: "뼈 부메랑 기술은 수년간 수련의 결과. 슬픔을 전투력으로 승화시킨 성장 서사.",
    106: "다리가 3배로 늘어남. 스트레칭의 중요성을 온몸으로 입증하는 포켓몬.",
    107: "5분에 1000발 펀치. 복싱 심판이 카운트 포기할 속도. 자동 판정승.",
    108: "2m 혀로 뭐든 핥음. 위생 관념이 심각하게 우려됨. 핥기 전에 혀 좀 씻자. 진심.",
    109: "풍선형 몸에 유독가스 충전. 생일파티 초대 절대 금지. 축하 분위기 테러범.",
    110: "독가스 2배 출력. 환경부 블랙리스트 1순위. ESG 경영 불가능 포켓몬.",
    111: "빌딩에 돌진해도 아픔 0. 보험회사가 가장 기피하는 포켓몬. 보상금이 무한.",
    112: "다이아몬드 관통 + 2000도 마그마 돌파. 30년째 밸런스 패치 안 됨. 운영팀 방치.",
    113: "매일 영양만점 알 생산. 계란값 폭등 시대 최고의 솔루션. 양계장보다 효율적.",
    114: "덩굴 잘라도 즉시 재생. 미용실 가봤자 의미 없음. 미용비 평생 0원.",
    115: "새끼 위협하면 초사이어인 모드 돌입. 한국 학부모 에너지를 포켓몬화한 존재.",
    116: "먹물 뿜는 해마. 실제 해마는 안 뿜는데 포켓몬이니까 가능. 판타지 보정.",
    117: "독가시에 찔리면 기절. 수족관 직원 산재보험 필수 가입 대상.",
    118: "'수영의 여왕' 칭호 보유. 올림픽 있으면 금메달인데 국적이 없어서 출전 불가.",
    119: "산란기에 강을 거슬러 올라감. 금붕어인지 연어인지 정체성 혼란 30년째.",
    120: "밤에 코어가 빨갛게 깜빡임. 야간 비상 조명 대체 가능. 전기세 절약형.",
    121: "7색으로 빛나서 '보석의 별'. 주얼리 브랜드 앰배서더 1순위 후보.",
    122: "상상한 벽이 진짜 벽이 됨. VR 없이 가상현실 구현. 메타버스의 원조 포켓몬.",
    123: "양팔 낫으로 잔디 깎기 가능. 조경업체 즉시 채용. 위험수당 포함 연봉 협상.",
    124: "초기 디자인이 인종차별 논란으로 색상 수정됨. 포켓몬 PR팀 역대 최대 위기.",
    125: "번개를 기다리며 나무 위 대기. 자발적 피뢰침. 전기요금 절약의 아이콘.",
    126: "표면 온도 1200도. 악수 금지. 인사는 목례로. 물리적 스킨십 불가능.",
    127: "집게로 끼우면 절대 안 놓음. 집착의 의인화. '놓아줘요'는 통하지 않음.",
    128: "리더 결정을 박치기로 함. 민주적이진 않지만 결과는 확실. 효율 100%.",
    129: "공식 설정이 '가장 약하고 한심한 포켓몬'. 튀기만 함. 근데 이게 복선인 걸 아는 사람만 앎.",
    130: "마을 하나를 통째로 파괴. 잉어킹 시절 무시했던 모든 사람에게 보내는 인생역전 명함.",
    131: "인간 말을 알아듣고 슬픈 노래를 부름. 음원 내면 차트 1위 가능. 포켓몬계 발라드 장인.",
    132: "뭐든 변신 가능. 포켓몬 교배 만능키. 전 세대에서 가장 바쁜 포켓몬. 과로사 주의보.",
    133: "전 세대 합쳐 진화형 8개. 진로 고민 세계 1위. 진로상담센터 단골 고객.",
    134: "물에 녹아서 투명 모드. 숨바꼭질 밸런스 붕괴 캐릭. 반칙 판정 요청.",
    135: "온몸 털이 전기 바늘. 귀엽지만 터치하면 감전. 눈으로만 감상 전용.",
    136: "체온 900도. 겨울에 안으면 따뜻할 것 같지만 실상은 3도 화상. 하지 마세요.",
    137: "1997년 애니 38화 빛 깜빡이로 일본 어린이 700명 경련. 포켓몬 역사상 최대 사건.",
    138: "화석에서 부활. 쥬라기 공원 포켓몬 버전. 이안 말콤 박사가 경고했을 텐데.",
    139: "껍질이 고대에 방어구 재료였다는 설. 선사시대 방산업체 납품 실적.",
    140: "3억 년 전 해양 생물. 투구게가 모델. 현실에서도 살아있는 화석이라 불림.",
    141: "고대 바다 최상위 포식자. 지금 부활하면 해수욕장 전부 영업정지 확정.",
    142: "호박 속 유전자에서 복원. 쥬라기 공원 그 전개를 포켓몬이 먼저 했음.",
    143: "하루 400kg 식사. 한 달 식비 수천만원. 절대 키우면 안 되는 포켓몬 부동의 1위.",
    144: "전설의 얼음새. 데려오면 냉장고 불필요. 여름 전기세 걱정 끝. 절약의 끝판왕.",
    145: "번개 맞으면 오히려 파워업. 전기요금 0원의 꿈. 한전이 가장 경계하는 포켓몬.",
    146: "봄을 알리며 나타남. 기상청보다 정확한 계절 예보. AI 일기예보도 이 정확도 못 냄.",
    147: "오랫동안 환상의 존재. 빅풋이나 네시도 포켓몬이었으면 좋겠다는 인류의 로망.",
    148: "날씨를 바꾸는 능력. 기상청 취업하면 연봉 협상에서 절대 밀리지 않을 포켓몬.",
    149: "16시간 만에 지구 일주. 마하 2 피죤투보다 빠른데 성격은 느긋. 갭모에의 원조.",
    150: "유전자 조작 인공 포켓몬. 영화에서 실존주의 철학의 끝을 보여줌. AI 시대 선구자.",
    151: "현미경급 크기인데 모든 기술 사용 가능. 포켓몬계 치트키. 밸런스 팀 사퇴 사유.",
    # --- Gen 2 (성도 지방) ---
    152: "잎사귀를 머리에 달고 다니는데 향기가 좋아서 아로마 테라피 가능. 양재동 꽃시장 취업 각.",
    153: "목의 잎에서 나는 향으로 사람 기분을 조절함. 천연 항우울제. 정신과 대체 가능.",
    154: "숨결만으로 시든 풀을 되살림. 식물 킬러인 사람 옆에 한 마리 필수. 반려식물 보험.",
    155: "겁이 많아서 등에 불을 피워 자기 방어함. 소심한데 불꽃은 강한 MBTI I형 대표.",
    156: "속도와 민첩성이 장점. 배달의민족 라이더로 환생하면 배달왕 타이틀 확정.",
    157: "분노하면 목 뒤에서 불꽃이 솟구침. 회의 중 화난 직장인 시각화 버전.",
    158: "아무거나 보면 일단 물어봄. 턱 힘이 워낙 강해서 트레이너 손도 위험. 물음 = 애정.",
    159: "이빨이 빠져도 바로 새로 남. 치과 갈 필요 없는 인생. 치과의사의 천적.",
    160: "물속에서 시속 80km. 올림픽 자유형에 나가면 금메달인데 수영복 사이즈가 없음.",
    161: "꼬리로 서서 주변을 감시함. CCTV가 없던 시절 마을 보안 담당. 월급은 나무열매.",
    162: "몸길이 1.8m인데 체중 32kg. 모델 비율이지만 땅굴에서 삶. 재능 낭비.",
    163: "다리가 하나인 것처럼 보이지만 사실 두 다리를 너무 빨리 바꿔 딛는 것. 착시의 달인.",
    164: "머리를 180도 돌릴 수 있음. 뒤에서 험담하면 바로 포착. 직장 내 뒷담화 탐지기.",
    165: "혼자면 겁쟁이인데 무리 지으면 용감해짐. 인터넷 댓글러의 생태와 유사.",
    166: "등에 별무늬 수로 강함을 판단함. 별 다섯 개면 미슐랭 아니고 전투력 만렙.",
    167: "등에 얼굴 무늬가 있는 거미. 무늬가 웃는 얼굴이면 기분 좋은 거래요. 표정 = 컨디션.",
    168: "거미줄로 먹이를 감지하는데 진동 감도가 스마트워치 심박수 센서급.",
    169: "친밀도로 진화하는 박쥐. 주인을 좋아하면 날개가 4개로 늘어남. 사랑의 힘.",
    170: "심해 1000m에서 발광 안테나로 먹이 유인. 심해 인플루언서. 조회수 장사.",
    171: "빛이 워낙 강해서 5km 밖 물고기도 유인됨. 광고 효과 미쳤다고 바다 생물들 증언.",
    172: "전기 주머니 제어가 안 돼서 자기도 감전됨. 아기라 봐줘야 함. 성장통의 일종.",
    173: "별똥별이 떨어진 곳에서 발견됨. 본인은 별에서 왔다고 주장하는데 증거 불충분.",
    174: "온몸이 푹신해서 한번 튀면 멈출 수 없음. 아기 푸린보다 탄성이 좋음. 인간 슈퍼볼.",
    175: "행복한 사람 옆에서만 알이 부화함. 불행한 사람은 알도 안 까줌. 감정 필터 장착.",
    176: "행복을 나눠줄 사람을 찾아다님. 근데 요즘 행복한 사람이 없어서 멸종 위기 아닌지 걱정.",
    177: "하루 종일 한 방향만 봄. 해를 응시하는데 눈 안 아프냐는 질문에 무응답.",
    178: "오른쪽 눈으로 미래, 왼쪽 눈으로 과거를 봄. 주식 투자하면 부자인데 말을 안 함.",
    179: "양털에 정전기가 쌓여서 만지면 감전. 겨울 니트 입고 문고리 잡는 그 고통의 실체화.",
    180: "털이 빠져도 계속 자람. 양모 무한 생산 가능. 유니클로 히트텍 원료 후보.",
    181: "꼬리 끝 구슬 빛이 우주에서도 보인다는 설. 실제로 게임에서 등대 역할. 인건비 0원.",
    182: "진화하면 꽃이 피면서 춤을 춤. 하와이안 훌라댄스 포켓몬. 쉬는 날엔 광합성.",
    183: "금은 발매 전 '피카블루'라는 소문으로 전 세계가 들썩였던 포켓몬. 역대급 가짜뉴스.",
    184: "겉보기와 달리 수중에서 엄청난 괴력 발휘. 귀여운 외모로 방심시키는 전략가.",
    185: "나무인 척하는 바위 포켓몬. 물 뿌리면 도망감. 30년째 연기하는데 연기력은 안 늘음.",
    186: "배를 두드리면 드럼 소리가 남. 개구리가 왕이 되려면 리듬감이 필요한 세계관.",
    187: "체중 0.5kg. 바람 불면 날아감. 태풍 오면 출퇴근 불가. 기상청 확인 필수.",
    188: "꽃이 피면 기온 측정 가능. 자연산 온도계. 기상 관측소 취업 가능.",
    189: "전 세계를 바람 타고 이동. 포켓몬계 디지털 노마드. 여권도 비자도 필요 없음.",
    190: "꼬리 손이 진짜 손보다 기술이 좋음. 본체가 꼬리인지 원숭이인지 헷갈리는 포켓몬.",
    191: "포켓몬 전체에서 능력치 총합 최하위. 공식 인정 최약체. 근데 그게 오히려 매력.",
    192: "해가 지면 꽃잎을 닫고 움직이지 않음. 퇴근 후 소파에 눕는 직장인과 동일 패턴.",
    193: "눈을 움직이지 않고 360도 시야 확보. 뒤통수에 눈이 달린 셈. 컨닝 불가능.",
    194: "항상 멍한 표정으로 웃고 있음. 스트레스 제로. 현대인이 배워야 할 마인드셋.",
    195: "머리 위에 뭐가 부딪혀도 신경 안 씀. 포켓몬계 '됐고 퇴근이나 하자'의 아이콘.",
    196: "주인에게 충성하면 초능력 개발됨. 이브이 진화형 중 가장 우아한데 성격은 츤데레.",
    197: "독을 품은 땀을 분비함. 쓰다듬으면 위험할 수 있는데 밤에 빛나는 링이 너무 멋있음.",
    198: "나타나면 불길한 일이 생긴다는 미신. 까마귀 자체가 억울한 건데 포켓몬도 마찬가지.",
    199: "셀러가 머리를 물어서 천재가 됨. 기생충이 숙주를 똑똑하게 만드는 유일한 사례.",
    200: "비명 소리를 모아서 공격함. 소음 민원 1위 포켓몬. 층간소음 분쟁 전문.",
    201: "28가지 알파벳 형태가 있음. 고대 유적 벽화의 글자. 해독하면 논문 하나 나옴.",
    202: "공격 기술이 없고 반사만 함. '너 때문이야'의 의인화. 책임 전가의 달인.",
    203: "꼬리에 뇌가 있어서 잘 때도 꼬리가 경계함. 24시간 보안 시스템. 수면 중에도 야근.",
    204: "건드리면 자폭함. '날 건드리지 마'를 온몸으로 실천하는 포켓몬. 인내심 0.",
    205: "껍질 안에서 폭탄을 만들어 쏨. 평화로운 외관에 군수업체 숨기고 있는 포켓몬.",
    206: "일본 전설의 생물 '츠치노코' 모델. UMA 팬들의 로망. 실물은 좀 실망스러울 수 있음.",
    207: "절벽에서 소리 없이 활공해서 먹이를 낚아챔. 배달 드론의 원조. 소음 0데시벨.",
    208: "강철 몸 경도가 다이아몬드 이상. 지하 터널 공사에 투입하면 TBM 장비 필요 없음.",
    209: "무서운 얼굴인데 겁이 많아서 사람에게 잘 따름. 불독이 실은 순둥이인 것과 같은 이치.",
    210: "아래턱이 발달해서 한번 물면 안 놓음. 악력 측정기 고장 내는 수준. 핸드그립 필요 없음.",
    211: "독침이 있는 복어인데 맛이 좋다는 설정은 없음. 먹지 마세요. 진짜로.",
    212: "집게 안에 눈이 있어서 잡으면서 관찰 가능. 하이테크 곤충. 메가진화하면 더 무섭게 생김.",
    213: "방어력이 전 포켓몬 중 최고. 나무열매를 껍질 안에서 발효시키면 이상한사탕이 된다는 전설.",
    214: "장수풍뎅이 모델. 뿔로 자기 체중 100배를 들어올림. 이삿짐센터 원탑. 괴력몬 라이벌.",
    215: "밤에만 활동하며 알을 훔쳐 먹음. 고양이+족제비+도둑의 3중 합체. 양심은 없음.",
    216: "손바닥에 꿀이 배어있어서 항상 핥고 다님. 사탕 대신 자기 손을 핥는 절약형 곰.",
    217: "숲에서 먹이를 찾는 냄새 반경 수 km. 배민 리뷰 평점 4.9 맛집만 골라가는 능력.",
    218: "체온 800도. 물에 들어가면 주변이 증발함. 사우나에서 출입금지당하는 포켓몬.",
    219: "체온이 태양 표면(5500도)보다 높은 10000도. 물리적으로 불가능한데 포켓몬이라 가능.",
    220: "코로 먹이를 찾는데 온천과 버섯을 잘 찾음. 트러플 헌터 대체 가능. 미식 돼지.",
    221: "얼음으로 뒤덮인 몸 아래 실제 눈이 있음. 앞머리로 세상을 가리고 사는 빙하기 은둔자.",
    222: "산호 모델인데 지구온난화로 실제 산호가 백화 중. 현실이 게임보다 슬픈 케이스.",
    223: "물총으로 300m 밖 먹이를 맞춤. 올림픽 사격 금메달감인데 포켓몬이라 출전 불가.",
    224: "진화하면 문어가 되는 물고기. 진화론을 완전히 무시하는 포켓몬 진화의 상징.",
    225: "꼬리에서 음식을 꺼내 나눠줌. 산타 모티브인데 가끔 폭탄도 선물함. 복불복 크리스마스.",
    226: "등에 총어가 붙어살아도 신경 안 씀. 포켓몬계 무임승차 허용 대중교통.",
    227: "강철 날개가 칼날처럼 날카로움. 비행 후 착지하면 바닥에 흠집. 공항 활주로 관리 비용 상승.",
    228: "울음소리 들으면 도망가야 함. 새벽에 울면 저승사자가 온다는 전설. 근데 그냥 배고픈 것.",
    229: "입에서 나온 불에 데면 영원히 아프다는 설정. 포켓몬계 가장 잔인한 화상. 보험 적용 불가.",
    230: "용왕 같은 위엄인데 해마 기반. 바다 깊은 곳에서 소용돌이 만들며 군림. 해저 제왕.",
    231: "하루에 자기 체중만큼의 물을 코로 뿌림. 여름 워터파크 인력 대체 가능. 인건비 절약.",
    232: "타이어처럼 몸을 말아서 굴러감. 시속 50km. 자동차 없던 시절 이동 수단이었을 듯.",
    233: "폴리곤의 업그레이드 버전. AI 탑재라 스스로 학습함. 2026년에 태어났으면 ChatGPT 경쟁자.",
    234: "뿔에서 나오는 향으로 환각을 일으킴. 사슴인데 환각 유발이라 법적으로 좀 문제 될 듯.",
    235: "다른 포켓몬 기술을 따라 그리는 화가 개. 표절 시비가 영원한 포켓몬. 저작권 분쟁 전문.",
    236: "성격에 따라 3가지로 진화. 공격형이면 시라소몬, 방어형이면 홍수몬, 밸런스면 카포에라.",
    237: "머리로 서서 회전 공격. 카포에라 무술 모델. K-POP 아이돌 안무에 영향 줬을 수도.",
    238: "뭐든 입술로 확인하는 습성. 바닥도 핥아봄. 위생 관념이 0인 아기 포켓몬.",
    239: "플러그 모양 머리를 콘센트에 꽂으면 충전됨. 인간 보조배터리. 캠핑 필수템.",
    240: "코에서 불꽃을 뿜는 아기. 재채기 한번에 집이 탈 수 있음. 소방서 옆집에 살아야 함.",
    241: "하루 20리터 우유 생산. 밀크초콜릿 이름의 유래가 이 포켓몬이라는 도시전설. 낙농업 혁명.",
    242: "HP가 전 포켓몬 중 최고(255). 알이 완전영양식이라 병원에서 탐내는 포켓몬. 포켓몬센터 정규직.",
    243: "천둥과 함께 나타남. 세계를 돌아다니며 벼락을 떨어뜨림. 전기차 충전소 필요 없는 시대.",
    244: "화산 분화와 함께 태어났다는 전설. 포효 한 번에 화산이 폭발함. 근처 부동산 가치 최하.",
    245: "오염된 물을 정화하는 능력. 전 세계 수질오염 문제 해결 가능. 환경부 즉시 채용.",
    246: "땅속에서 흙을 먹고 자라는 유충. 산 하나를 다 먹어야 진화함. 개발 제한 구역 지정 필요.",
    247: "몸 안에서 가스를 압축해 제트처럼 날아다님. 껍질 안에서 진화 준비 중. 고치인데 비행 가능.",
    248: "한 마리가 산 하나를 통째로 부숨. 지도를 다시 그려야 하는 수준. 국토지리정보원 비상.",
    249: "날갯짓 한 번에 40일간 폭풍이 지속됨. 그래서 바다 깊은 곳에서 자고 있음. 현명한 선택.",
    250: "지우가 1화에서 본 전설의 새. 무지개빛 깃털을 보면 영원한 행복. 29년째 안 잡힘.",
    251: "시간여행이 가능한 요정. 숲의 수호자인데 양파 머리라 위엄이 좀 부족. 외모 보완 시급.",
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
        "📚 1세대 도감 (관동)": ["beginner", "collector", "trainer", "master", "champion", "living_dex"],
        "🌏 2세대 도감 (성도)": ["gen2_starter", "gen2_collector", "gen2_trainer", "gen2_master"],
        "💫 그랜드": ["grand_master"],
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
