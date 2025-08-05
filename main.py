import json
import os
import random
import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import CommandStart, Command
from aiogram.exceptions import TelegramNetworkError
from aiogram.utils.executor import start_webhook
import aiohttp

# Logging sozlamalari
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Bot sozlamalari
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_PATH = "/webhook"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 8080))
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Ma'lumotlarni yuklash
def load_data():
    data = {"Dictionary": {}, "Grammar": {}}
    dict_names = []
    grammar_names = []
    
    try:
        with open('dictionary.json', 'r', encoding='utf-8') as f:
            dictionary_data = json.load(f)
            dict_names = list(dictionary_data.keys())
            for dict_name in dict_names:
                data["Dictionary"][dict_name] = dictionary_data[dict_name]
    except FileNotFoundError:
        logger.error("dictionary.json fayli topilmadi")
        return None, [], []
    except json.JSONDecodeError as e:
        logger.error(f"dictionary.json faylini dekodlashda xato: {e}")
        return None, [], []
    
    try:
        with open('grammar.json', 'r', encoding='utf-8') as f:
            grammar_data = json.load(f)
            grammar_names = list(grammar_data.keys())
            for grammar_name in grammar_names:
                data["Grammar"][grammar_name] = grammar_data[grammar_name]
    except FileNotFoundError:
        logger.warning("grammar.json fayli topilmadi, bo'sh Grammar ma'lumotlari ishlatiladi")
        data["Grammar"] = {}
    except json.JSONDecodeError as e:
        logger.error(f"grammar.json faylini dekodlashda xato: {e}")
        data["Grammar"] = {}
    
    logger.info(f"Yuklangan lug'atlar: {len(dict_names)}, grammatika bo'limlari: {len(grammar_names)}")
    return data, dict_names, grammar_names

DATA, DICT_NAMES, GRAMMAR_NAMES = load_data()
if DATA is None:
    logger.critical("Ma'lumot fayllari yuklanmadi!")
    raise Exception("Ma'lumot fayllari yuklanmadi!")

# Konstantalar
LEVEL_MAPPING = {
    "✨ Oson": "Easy",
    "🌟 O‘rta": "Medium",
    "🔥 Qiyin": "Hard"
}
LEVEL_EMOJIS = {
    "Easy": "✨",
    "Medium": "🌟",
    "Hard": "🔥"
}
ITEMS_PER_PAGE = 10
TIME_LIMIT = int(os.getenv("TIME_LIMIT", 30))  # Default to 30 if not set
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))  # Set your admin ID in Render environment variables

# Holatlar
class QuizStates(StatesGroup):
    quiz_menu = State()
    choosing_dict = State()
    choosing_grammar = State()
    lugat_levels = State()
    choosing_count = State()
    asking_question = State()
    confirming_end = State()
    random_questions = State()

class LearningStates(StatesGroup):
    learning_menu = State()
    choosing_dict = State()
    choosing_grammar = State()
    lugat_levels = State()
    showing_items = State()

class AdminStates(StatesGroup):
    waiting_for_message = State()

class FeedbackStates(StatesGroup):
    waiting_for_feedback = State()

# Dinamik klaviaturalar
def get_main_menu(is_admin=False, has_wrong_answers=False):
    keyboard = [
        [KeyboardButton(text="🚀 Quiz boshlash"), KeyboardButton(text="📚 O‘quv rejimi")],
        [KeyboardButton(text="ℹ️ Bot haqida"), KeyboardButton(text="📬 Fikr yuborish")],
    ]
    if has_wrong_answers:
        keyboard.append([KeyboardButton(text="🔄 Xatolarni tuzatish")])
    if is_admin:
        keyboard.append([KeyboardButton(text="🛠 Admin paneli")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)

def get_dict_menu(page=0, per_page=6):
    keyboard = []
    start = page * per_page
    end = start + per_page
    dict_slice = DICT_NAMES[start:end]
    
    for i in range(0, len(dict_slice), 2):
        row = [KeyboardButton(text=f"📖 {dict_slice[i]}")]
        if i + 1 < len(dict_slice):
            row.append(KeyboardButton(text=f"📖 {dict_slice[i+1]}"))
        keyboard.append(row)
    
    nav_row = []
    if page > 0:
        nav_row.append(KeyboardButton(text="⬅️ Oldingi sahifa"))
    if end < len(DICT_NAMES):
        nav_row.append(KeyboardButton(text="➡️ Keyingi sahifa"))
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([KeyboardButton(text="↩️ Orqaga")])
    
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)

def get_grammar_menu(page=0, per_page=6):
    keyboard = []
    start = page * per_page
    end = start + per_page
    grammar_slice = GRAMMAR_NAMES[start:end]
    
    for i in range(0, len(grammar_slice), 2):
        row = [KeyboardButton(text=f"📚 {grammar_slice[i]}")]
        if i + 1 < len(grammar_slice):
            row.append(KeyboardButton(text=f"📚 {grammar_slice[i+1]}"))
        keyboard.append(row)
    
    nav_row = []
    if page > 0:
        nav_row.append(KeyboardButton(text="⬅️ Oldingi sahifa"))
    if end < len(GRAMMAR_NAMES):
        nav_row.append(KeyboardButton(text="➡️ Keyingi sahifa"))
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([KeyboardButton(text="↩️ Orqaga")])
    
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)

def get_learning_navigation(page, total_pages):
    keyboard = []
    nav_row = []
    if page > 0:
        nav_row.append(KeyboardButton(text="⬅️ Oldingi sahifa"))
    if page < total_pages - 1:
        nav_row.append(KeyboardButton(text="➡️ Keyingi sahifa"))
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([KeyboardButton(text="↩️ Orqaga")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)

REPEAT_WRONG_MARKUP = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🔄 Xatolarni tuzatish")]],
    resize_keyboard=True, one_time_keyboard=True
)

QUIZ_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📖 Lug‘atlar"), KeyboardButton(text="📚 Grammatika")],
        [KeyboardButton(text="🎲 Tasodifiy savollar"), KeyboardButton(text="↩️ Bosh menyuga")]
    ], resize_keyboard=True, one_time_keyboard=True
)

LEARNING_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📖 Lug‘atlar"), KeyboardButton(text="📚 Grammatika")],
        [KeyboardButton(text="↩️ Bosh menyuga")]
    ], resize_keyboard=True, one_time_keyboard=True
)

LUGAT_LEVELS = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✨ Oson daraja"), KeyboardButton(text="🌟 O‘rta daraja")],
        [KeyboardButton(text="🔥 Qiyin daraja"), KeyboardButton(text="↩️ Orqaga")]
    ], resize_keyboard=True, one_time_keyboard=True
)

COUNT_MARKUP = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✍️ O‘zingiz kiriting"), KeyboardButton(text="🌕 Hammasini ishlash")],
        [KeyboardButton(text="↩️ Orqaga")]
    ], resize_keyboard=True, one_time_keyboard=True
)

ADMIN_MARKUP = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👤 Foydalanuvchilar ro‘yxati"), KeyboardButton(text="📩 Xabar yuborish")],
        [KeyboardButton(text="↩️ Bosh menyuga")]
    ], resize_keyboard=True, one_time_keyboard=True
)

CONFIRM_END_MARKUP = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="✔️ Ha, tugatish"), KeyboardButton(text="✖️ Yo‘q, davom etish")]],
    resize_keyboard=True, one_time_keyboard=True
)

# Foydalanuvchilarni saqlash
async def save_user(user_id: int, username: str):
    users = await load_json('users.json', [])
    user = next((u for u in users if u['id'] == user_id), None)
    current_time = datetime.now().isoformat()
    
    if user:
        user['username'] = username or user.get('username', 'Nomalum')
        user['last_active'] = current_time
        logger.info(f"Foydalanuvchi yangilandi: ID={user_id}, Username=@{username or 'Nomalum'}, Oxirgi faol: {current_time}")
    else:
        new_user = {
            'id': user_id,
            'username': username or 'Nomalum',
            'last_active': current_time
        }
        users.append(new_user)
        logger.info(f"Yangi foydalanuvchi saqlandi: ID={user_id}, Username=@{username or 'Nomalum'}, Oxirgi faol: {current_time}")
    
    await save_to_json('users.json', users)

# Fayl bilan ishlash
async def save_to_json(filename: str, data: list):
    try:
        async with asyncio.Lock():
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        logger.debug(f"{filename} fayliga ma'lumot saqlandi")
    except Exception as e:
        logger.error(f"{filename} saqlashda xato: {e}")

async def load_json(filename: str, default=None):
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        logger.warning(f"{filename} fayli topilmadi, default qiymat ishlatiladi")
        return default or []
    except Exception as e:
        logger.error(f"{filename} yuklashda xato: {e}")
        return default or []

# Taymer
async def question_timer(message: types.Message, state: FSMContext):
    countdown = await message.answer(f"⏳ {TIME_LIMIT} sekund qoldi", parse_mode="HTML")
    try:
        for remaining in range(TIME_LIMIT - 1, -1, -1):
            await asyncio.sleep(1)
            if (await state.get_data()).get('answered', False):
                await countdown.delete()
                return
            emoji = "⏳" if remaining > TIME_LIMIT // 2 else "⏲" if remaining > 5 else "⏰"
            await countdown.edit_text(f"{emoji} {remaining} sekund qoldi", parse_mode="HTML")
        await countdown.edit_text("⏰ Vaqt tugadi! ⏰")
        await end_test(message, state)
    except asyncio.CancelledError:
        await countdown.delete()

async def cancel_timer(state: FSMContext):
    timer_task = (await state.get_data()).get('timer_task')
    if timer_task and not timer_task.done():
        timer_task.cancel()
        try:
            await timer_task
        except asyncio.CancelledError:
            pass

# Handlerlar
@dp.message(CommandStart())
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username
    await save_user(user_id, username)
    await message.answer(
        "<b>🌟 Quiz botga xush kelibsiz! 🌟</b>\n\n"
        "Bu yerda bilimingizni sinab ko‘rishingiz yoki o‘rganishingiz mumkin!\n"
        "👇 Quyidagi tugmalardan birini tanlang:",
        reply_markup=get_main_menu(user_id == ADMIN_ID),
        parse_mode="HTML"
    )

@dp.message(lambda msg: msg.text == "ℹ️ Bot haqida")
async def about_bot(message: types.Message):
    await message.answer(
        "<b>ℹ️ Bot haqida ma’lumot</b>\n\n"
        "🌟 <b>Lug‘at va grammatika:</b> Turli bo‘limlar\n"
        "📚 <b>Rejimlar:</b> Quiz va O‘quv rejimi\n"
        "⏳ <b>Vaqt chegarasi:</b> Quiz savollari uchun\n"
        "📊 <b>Natijalar:</b> Test oxirida ko‘rish\n\n"
        "<i>Bilimlaringizni sinashga yoki o‘rganishga tayyormisiz?</i>",
        parse_mode="HTML"
    )

@dp.message(lambda msg: msg.text == "📬 Fikr yuborish")
async def feedback_start(message: types.Message, state: FSMContext):
    await save_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "<b>✍️ Fikringizni yozing, adminlarimiz ko‘rib chiqadi:</b>",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="↩️ Orqaga")]],
            resize_keyboard=True,
            one_time_keyboard=True
        ),
        parse_mode="HTML"
    )
    await state.set_state(FeedbackStates.waiting_for_feedback)

@dp.message(FeedbackStates.waiting_for_feedback)
async def save_feedback(message: types.Message, state: FSMContext):
    await save_user(message.from_user.id, message.from_user.username)
    if message.text == "↩️ Orqaga":
        await start_handler(message, state)
        return
    
    feedback_text = message.text
    user_id = message.from_user.id
    username = message.from_user.username or "Nomalum"
    
    try:
        await bot.send_message(
            ADMIN_ID,
            f"<b>📬 Yangi fikr:</b>\n"
            f"<b>Foydalanuvchi:</b> @{username} (ID: {user_id})\n"
            f"<b>Xabar:</b> {feedback_text}",
            parse_mode="HTML"
        )
        await message.answer(
            "<b>✅ Fikringiz yuborildi, rahmat!</b>",
            reply_markup=get_main_menu(user_id == ADMIN_ID),
            parse_mode="HTML"
        )
        logger.info(f"Fikr yuborildi: ID={user_id}, Username=@{username}, Xabar={feedback_text}")
    except Exception as e:
        await message.answer(
            "<b>❌ Fikr yuborishda xato yuz berdi, qaytadan urinib ko‘ring!</b>",
            parse_mode="HTML"
        )
        logger.error(f"Fikr yuborishda xato: ID={user_id}, Xato={e}")
    
    await state.clear()

@dp.message(lambda msg: msg.text == "🛠 Admin paneli" and msg.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message, state: FSMContext):
    await message.answer(
        "<b>🛠 Admin paneli</b>\n\n"
        "👇 Quyidagi amallarni bajarishingiz mumkin:",
        reply_markup=ADMIN_MARKUP,
        parse_mode="HTML"
    )
    await state.clear()

@dp.message(lambda msg: msg.text == "👤 Foydalanuvchilar ro‘yxati" and msg.from_user.id == ADMIN_ID)
async def show_users(message: types.Message):
    users = await load_json('users.json', [])
    if not users:
        await message.answer("<b>👤 Hozircha foydalanuvchilar yo‘q!</b>", reply_markup=ADMIN_MARKUP, parse_mode="HTML")
        return
    
    user_list = "\n".join(
        f"👤 ID: {u['id']} | @{u['username']} | Oxirgi faol: {u.get('last_active', 'Nomalum')}"
        for u in users
    )
    await message.answer(
        f"<b>👥 Foydalanuvchilar soni: {len(users)}</b>\n\n{user_list}",
        reply_markup=ADMIN_MARKUP,
        parse_mode="HTML"
    )

@dp.message(lambda msg: msg.text == "📩 Xabar yuborish" and msg.from_user.id == ADMIN_ID)
async def send_broadcast_start(message: types.Message, state: FSMContext):
    await message.answer(
        "<b>📩 Foydalanuvchilarga xabar yuborish</b>\n\nYubormoqchi bo‘lgan xabarni kiriting:",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_message)

@dp.message(AdminStates.waiting_for_message)
async def send_broadcast(message: types.Message, state: FSMContext):
    users = await load_json('users.json', [])
    if not users:
        await message.answer("<b>❗ Hozircha foydalanuvchilar yo‘q!</b>", reply_markup=ADMIN_MARKUP, parse_mode="HTML")
        await state.clear()
        return
    
    sent, failed = 0, 0
    broadcast_message = message.text
    
    logger.info(f"Xabar yuborish boshlandi. Jami foydalanuvchilar: {len(users)}")
    logger.info(f"Yuboriladigan xabar: {broadcast_message}")
    
    for user in users:
        user_id = user['id']
        username = user.get('username', 'Nomalum')
        try:
            await bot.send_message(chat_id=user_id, text=broadcast_message, parse_mode="HTML")
            sent += 1
            logger.info(f"Xabar yuborildi: ID={user_id}, Username=@{username}")
        except Exception as e:
            failed += 1
            error_msg = str(e).lower()
            logger.error(f"Xabar yuborishda xato: ID={user_id}, Xato: {error_msg}")
            if "blocked by user" in error_msg or "chat not found" in error_msg:
                logger.warning(f"Foydalanuvchi ro‘yxatdan o‘chirilmoqda: ID={user_id}")
                users = [u for u in users if u['id'] != user_id]
                await save_to_json('users.json', users)
                logger.info(f"Foydalanuvchi o‘chirildi: ID={user_id}")
    
    result_text = (
        f"<b>📬 Xabar yuborish natijasi:</b>\n"
        f"✅ Muvaffaqiyatli: {sent} ta\n"
        f"❌ Xato: {failed} ta\n"
        f"👥 Jami foydalanuvchilar: {len(users)} ta"
    )
    await message.answer(result_text, reply_markup=ADMIN_MARKUP, parse_mode="HTML")
    logger.info(f"Xabar yuborish yakunlandi. Muvaffaqiyatli: {sent}, Xato: {failed}")
    
    await state.clear()

@dp.message(lambda msg: msg.text in ["↩️ Bosh menyuga", "↩️ Orqaga"])
async def back_to_menu(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    user_data = await state.get_data()
    
    if current_state in [QuizStates.quiz_menu.state, QuizStates.random_questions.state, LearningStates.learning_menu.state]:
        await start_handler(message, state)
    elif current_state == QuizStates.choosing_dict.state:
        await message.answer("<b>🌟 Bo‘lim tanlash</b>\n\nQuyidagilardan birini tanlang:", reply_markup=QUIZ_MENU, parse_mode="HTML")
        await state.set_state(QuizStates.quiz_menu)
    elif current_state == QuizStates.choosing_grammar.state:
        await message.answer("<b>🌟 Bo‘lim tanlash</b>\n\nQuyidagilardan birini tanlang:", reply_markup=QUIZ_MENU, parse_mode="HTML")
        await state.set_state(QuizStates.quiz_menu)
    elif current_state == QuizStates.lugat_levels.state:
        await message.answer("<b>📖 Lug‘at tanlash</b>\n\nKerakli lug‘atni tanlang:", reply_markup=get_dict_menu(), parse_mode="HTML")
        await state.set_state(QuizStates.choosing_dict)
    elif current_state == QuizStates.choosing_count.state:
        if user_data.get('section') == "Grammar":
            page = user_data.get('grammar_page', 0)
            await message.answer("<b>📚 Grammatika tanlash</b>\n\nBo‘limni tanlang:", reply_markup=get_grammar_menu(page), parse_mode="HTML")
            await state.set_state(QuizStates.choosing_grammar)
        elif user_data.get('section') == "Random":
            await message.answer("<b>🌟 Bo‘lim tanlash</b>\n\nQuyidagilardan birini tanlang:", reply_markup=QUIZ_MENU, parse_mode="HTML")
            await state.set_state(QuizStates.quiz_menu)
        else:
            await message.answer("<b>🌠 Daraja tanlash</b>\n\nDarajani tanlang:", reply_markup=LUGAT_LEVELS, parse_mode="HTML")
            await state.set_state(QuizStates.lugat_levels)
    elif current_state == LearningStates.choosing_dict.state:
        await message.answer("<b>📚 O‘quv rejimi</b>\n\nQuyidagilardan birini tanlang:", reply_markup=LEARNING_MENU, parse_mode="HTML")
        await state.set_state(LearningStates.learning_menu)
    elif current_state == LearningStates.choosing_grammar.state:
        await message.answer("<b>📚 O‘quv rejimi</b>\n\nQuyidagilardan birini tanlang:", reply_markup=LEARNING_MENU, parse_mode="HTML")
        await state.set_state(LearningStates.learning_menu)
    elif current_state == LearningStates.lugat_levels.state:
        page = user_data.get('dict_page', 0)
        await message.answer("<b>📖 Lug‘at tanlash</b>\n\nKerakli lug‘atni tanlang:", reply_markup=get_dict_menu(page), parse_mode="HTML")
        await state.set_state(LearningStates.choosing_dict)
    elif current_state == LearningStates.showing_items.state:
        if user_data.get('section') == "Dictionary":
            await message.answer("<b>🌠 Daraja tanlash</b>\n\nDarajani tanlang:", reply_markup=LUGAT_LEVELS, parse_mode="HTML")
            await state.set_state(LearningStates.lugat_levels)
        else:
            page = user_data.get('grammar_page', 0)
            await message.answer("<b>📚 Grammatika tanlash</b>\n\nBo‘limni tanlang:", reply_markup=get_grammar_menu(page), parse_mode="HTML")
            await state.set_state(LearningStates.choosing_grammar)
    else:
        await state.clear()
        await message.answer(
            "<b>🌟 Bosh menu</b>\n\n👇 Quyidagi tugmalardan birini tanlang:",
            reply_markup=get_main_menu(message.from_user.id == ADMIN_ID),
            parse_mode="HTML"
        )

@dp.message(lambda msg: msg.text == "🚀 Quiz boshlash")
async def start_quiz(message: types.Message, state: FSMContext):
    await save_user(message.from_user.id, message.from_user.username)
    await message.answer("<b>🌟 Bo‘lim tanlash</b>\n\nQuyidagilardan birini tanlang:", reply_markup=QUIZ_MENU, parse_mode="HTML")
    await state.set_state(QuizStates.quiz_menu)

@dp.message(lambda msg: msg.text == "📚 O‘quv rejimi")
async def start_learning(message: types.Message, state: FSMContext):
    await save_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "<b>📚 O‘quv rejimi</b>\n\nQuyidagilardan birini tanlang:",
        reply_markup=LEARNING_MENU,
        parse_mode="HTML"
    )
    await state.set_state(LearningStates.learning_menu)

@dp.message(QuizStates.quiz_menu)
async def quiz_menu_handler(message: types.Message, state: FSMContext):
    await save_user(message.from_user.id, message.from_user.username)
    if message.text == "📖 Lug‘atlar":
        await state.update_data(dict_page=0)
        await message.answer("<b>📖 Lug‘at tanlash</b>\n\nKerakli lug‘atni tanlang:", reply_markup=get_dict_menu(), parse_mode="HTML")
        await state.set_state(QuizStates.choosing_dict)
    elif message.text == "📚 Grammatika":
        await state.update_data(grammar_page=0)
        await message.answer("<b>📚 Grammatika tanlash</b>\n\nBo‘limni tanlang:", reply_markup=get_grammar_menu(), parse_mode="HTML")
        await state.set_state(QuizStates.choosing_grammar)
    elif message.text == "🎲 Tasodifiy savollar":
        all_questions = []
        for dict_name in DATA["Dictionary"]:
            for level in DATA["Dictionary"][dict_name]:
                all_questions.extend(list(DATA["Dictionary"][dict_name][level].items()))
        for grammar_name in DATA["Grammar"]:
            all_questions.extend(list(DATA["Grammar"][grammar_name].items()))
        
        if not all_questions:
            await message.answer("<b>❗ Hozircha tasodifiy savollar mavjud emas!</b>", parse_mode="HTML")
            return
        
        available_questions = len(all_questions)
        await state.update_data(section="Random", available_questions=available_questions, all_questions=all_questions)
        await message.answer(
            f"<b>🎲 Tasodifiy savollar sonini tanlang</b>\n\nJami mavjud: {available_questions} ta",
            reply_markup=COUNT_MARKUP,
            parse_mode="HTML"
        )
        await state.set_state(QuizStates.random_questions)
    elif message.text == "↩️ Bosh menyuga":
        await start_handler(message, state)
    else:
        await message.answer("<b>❗ Iltimos, menyudan tanlang!</b>", parse_mode="HTML")

@dp.message(QuizStates.random_questions)
async def choose_random_count(message: types.Message, state: FSMContext):
    await save_user(message.from_user.id, message.from_user.username)
    user_data = await state.get_data()
    available = user_data.get('available_questions', 0)
    all_questions = user_data.get('all_questions', [])

    if message.text == "↩️ Orqaga":
        await message.answer("<b>🌟 Bo‘lim tanlash</b>\n\nQuyidagilardan birini tanlang:", reply_markup=QUIZ_MENU, parse_mode="HTML")
        await state.set_state(QuizStates.quiz_menu)
        return
    
    if message.text == "✍️ O‘zingiz kiriting":
        await message.answer(f"<b>🔢 Savollar sonini kiriting (1-{available}):</b>", parse_mode="HTML")
        return
    
    if message.text == "🌕 Hammasini ishlash":
        count = available
    elif message.text.isdigit():
        count = int(message.text)
    else:
        await message.answer("<b>❗ Iltimos, menyudan tanlang yoki raqam kiriting!</b>", parse_mode="HTML")
        return

    if 0 < count <= available:
        questions = random.sample(all_questions, count)
        await state.update_data(questions=questions, current=0, correct=0, wrong_answers=[])
        await send_question(message, state)
    else:
        await message.answer(f"<b>❗ 1-{available} oralig‘ida son kiriting!</b>", parse_mode="HTML")

@dp.message(QuizStates.choosing_dict)
async def choose_dict_handler(message: types.Message, state: FSMContext):
    await save_user(message.from_user.id, message.from_user.username)
    user_data = await state.get_data()
    page = user_data.get('dict_page', 0)
    
    if message.text == "⬅️ Oldingi sahifa":
        page = max(0, page - 1)
        await state.update_data(dict_page=page)
        await message.answer("<b>📖 Lug‘at tanlash</b>\n\nKerakli lug‘atni tanlang:", reply_markup=get_dict_menu(page), parse_mode="HTML")
    elif message.text == "➡️ Keyingi sahifa":
        page += 1
        await state.update_data(dict_page=page)
        await message.answer("<b>📖 Lug‘at tanlash</b>\n\nKerakli lug‘atni tanlang:", reply_markup=get_dict_menu(page), parse_mode="HTML")
    else:
        selected_dict = message.text.replace("📖 ", "")
        if selected_dict in DICT_NAMES:
            if selected_dict not in DATA["Dictionary"]:
                await message.answer(
                    f"<b>❗ '{selected_dict}' lug‘ati mavjud emas!</b>\nBoshqa lug‘atni tanlang:",
                    reply_markup=get_dict_menu(page),
                    parse_mode="HTML"
                )
                return
            await state.update_data(section="Dictionary", selected_dict=selected_dict)
            await message.answer("<b>🌠 Daraja tanlash</b>\n\nDarajani tanlang:", reply_markup=LUGAT_LEVELS, parse_mode="HTML")
            await state.set_state(QuizStates.lugat_levels)
        elif message.text == "↩️ Orqaga":
            await message.answer("<b>🌟 Bo‘lim tanlash</b>\n\nQuyidagilardan birini tanlang:", reply_markup=QUIZ_MENU, parse_mode="HTML")
            await state.set_state(QuizStates.quiz_menu)
        else:
            await message.answer("<b>❗ Iltimos, lug‘atni tanlang!</b>", reply_markup=get_dict_menu(page), parse_mode="HTML")

@dp.message(QuizStates.choosing_grammar)
async def choose_grammar_handler(message: types.Message, state: FSMContext):
    await save_user(message.from_user.id, message.from_user.username)
    user_data = await state.get_data()
    page = user_data.get('grammar_page', 0)
    
    if message.text == "⬅️ Oldingi sahifa":
        page = max(0, page - 1)
        await state.update_data(grammar_page=page)
        await message.answer("<b>📚 Grammatika tanlash</b>\n\nBo‘limni tanlang:", reply_markup=get_grammar_menu(page), parse_mode="HTML")
    elif message.text == "➡️ Keyingi sahifa":
        page += 1
        await state.update_data(grammar_page=page)
        await message.answer("<b>📚 Grammatika tanlash</b>\n\nBo‘limni tanlang:", reply_markup=get_grammar_menu(page), parse_mode="HTML")
    else:
        selected_category = message.text.replace("📚 ", "")
        if selected_category in GRAMMAR_NAMES:
            if selected_category not in DATA["Grammar"]:
                await message.answer(
                    f"<b>❗ '{selected_category}' bo‘limi mavjud emas!</b>\nBoshqa bo‘limni tanlang:",
                    reply_markup=get_grammar_menu(page),
                    parse_mode="HTML"
                )
                return
            available_questions = len(DATA["Grammar"].get(selected_category, {}))
            if available_questions == 0:
                await message.answer(
                    f"<b>❗ '{selected_category}' bo‘limida savollar yo‘q!</b>\nBoshqa bo‘limni tanlang:",
                    reply_markup=get_grammar_menu(page),
                    parse_mode="HTML"
                )
                return
            await state.update_data(section="Grammar", selected_category=selected_category, available_questions=available_questions)
            await message.answer(
                f"<b>🌕 Savollar sonini tanlang</b>\n\nJami mavjud: {available_questions} ta",
                reply_markup=COUNT_MARKUP,
                parse_mode="HTML"
            )
            await state.set_state(QuizStates.choosing_count)
        elif message.text == "↩️ Orqaga":
            await message.answer("<b>🌟 Bo‘lim tanlash</b>\n\nQuyidagilardan birini tanlang:", reply_markup=QUIZ_MENU, parse_mode="HTML")
            await state.set_state(QuizStates.quiz_menu)
        else:
            await message.answer("<b>❗ Iltimos, bo‘limni tanlang!</b>", reply_markup=get_grammar_menu(page), parse_mode="HTML")

@dp.message(QuizStates.lugat_levels)
async def choose_level(message: types.Message, state: FSMContext):
    await save_user(message.from_user.id, message.from_user.username)
    level = LEVEL_MAPPING.get(message.text.replace(" daraja", ""))
    user_data = await state.get_data()
    selected_dict = user_data.get('selected_dict')
    if level in ["Easy", "Medium", "Hard"]:
        if selected_dict not in DATA["Dictionary"]:
            page = user_data.get('dict_page', 0)
            await message.answer(
                f"<b>❗ '{selected_dict}' lug‘ati mavjud emas!</b>",
                reply_markup=get_dict_menu(page),
                parse_mode="HTML"
            )
            await state.set_state(QuizStates.choosing_dict)
            return
        available_questions = len(DATA["Dictionary"][selected_dict].get(level, {}))
        if available_questions == 0:
            await message.answer(
                f"<b>❗ '{selected_dict}' lug‘atida '{level}' darajasida savollar yo‘q!</b>\nBoshqa darajani tanlang:",
                reply_markup=LUGAT_LEVELS,
                parse_mode="HTML"
            )
            return
        await state.update_data(level=level, available_questions=available_questions)
        await message.answer(
            f"<b>🌕 Savollar sonini tanlang</b>\n\nJami mavjud: {available_questions} ta",
            reply_markup=COUNT_MARKUP,
            parse_mode="HTML"
        )
        await state.set_state(QuizStates.choosing_count)
    elif message.text == "↩️ Orqaga":
        page = user_data.get('dict_page', 0)
        await message.answer("<b>📖 Lug‘at tanlash</b>\n\nKerakli lug‘atni tanlang:", reply_markup=get_dict_menu(page), parse_mode="HTML")
        await state.set_state(QuizStates.choosing_dict)
    else:
        await message.answer("<b>❗ Iltimos, darajani tanlang!</b>", parse_mode="HTML")

@dp.message(QuizStates.choosing_count)
async def choose_count(message: types.Message, state: FSMContext):
    await save_user(message.from_user.id, message.from_user.username)
    user_data = await state.get_data()
    available = user_data.get('available_questions', 0)

    if message.text == "↩️ Orqaga":
        if user_data.get('section') == "Grammar":
            page = user_data.get('grammar_page', 0)
            await message.answer("<b>📚 Grammatika tanlash</b>\n\nBo‘limni tanlang:", reply_markup=get_grammar_menu(page), parse_mode="HTML")
            await state.set_state(QuizStates.choosing_grammar)
        elif user_data.get('section') == "Random":
            await message.answer("<b>🌟 Bo‘lim tanlash</b>\n\nQuyidagilardan birini tanlang:", reply_markup=QUIZ_MENU, parse_mode="HTML")
            await state.set_state(QuizStates.quiz_menu)
        else:
            await message.answer("<b>🌠 Daraja tanlash</b>\n\nDarajani tanlang:", reply_markup=LUGAT_LEVELS, parse_mode="HTML")
            await state.set_state(QuizStates.lugat_levels)
        return
    
    if message.text == "✍️ O‘zingiz kiriting":
        await message.answer(f"<b>🔢 Savollar sonini kiriting (1-{available}):</b>", parse_mode="HTML")
        return
    
    if message.text == "🌕 Hammasini ishlash":
        count = available
    elif message.text.isdigit():
        count = int(message.text)
    else:
        await message.answer("<b>❗ Iltimos, menyudan tanlang yoki raqam kiriting!</b>", parse_mode="HTML")
        return

    if 0 < count <= available:
        if user_data['section'] == "Dictionary":
            questions = random.sample(
                list(DATA["Dictionary"][user_data['selected_dict']][user_data['level']].items()), count
            )
        elif user_data['section'] == "Grammar":
            questions = random.sample(
                list(DATA["Grammar"][user_data['selected_category']].items()), count
            )
        else:
            questions = random.sample(user_data['all_questions'], count)
        await state.update_data(questions=questions, current=0, correct=0, wrong_answers=[])
        await send_question(message, state)
    else:
        await message.answer(f"<b>❗ 1-{available} oralig‘ida son kiriting!</b>", parse_mode="HTML")

async def send_question(message: types.Message, state: FSMContext):
    await save_user(message.from_user.id, message.from_user.username)
    user_data = await state.get_data()
    current = user_data.get('current', 0)
    questions = user_data.get('questions', [])
    section = user_data.get('section', 'Dictionary')
    level = user_data.get('level', 'Easy') if section == "Dictionary" else None
    
    if current >= len(questions):
        await end_test(message, state)
        return
    
    question = questions[current][0]
    if section == "Random":
        text = (
            f"<b>🎲 {current + 1}/{len(questions)} - Tasodifiy savol ❓</b>\n\n"
            f"💡 <b>{question}</b>\n\n"
            f"<i>Javobingizni yozing yoki /end</i>"
        )
    else:
        text = (
            f"<b>{LEVEL_EMOJIS.get(level, '📚')} {current + 1}/{len(questions)} - "
            f"{'Lug‘at savoli' if section == 'Dictionary' else 'Grammatika savoli'} ❓</b>\n\n"
            f"💡 <b>{question}</b>\n\n"
            f"<i>{'Рус тилида жавоб беринг' if section == 'Grammar' else 'Javobingizni yozing'} yoki /end</i>"
        )
    await message.answer(text, parse_mode="HTML")
    await state.update_data(answered=False, timer_task=asyncio.create_task(question_timer(message, state)))
    await state.set_state(QuizStates.asking_question)

@dp.message(QuizStates.asking_question)
async def check_answer(message: types.Message, state: FSMContext):
    await save_user(message.from_user.id, message.from_user.username)
    await cancel_timer(state)
    user_data = await state.get_data()
    current = user_data.get('current', 0)
    questions = user_data.get('questions', [])
    
    if message.text == "/end":
        await message.answer("<b>⏹ Quizni yakunlashni xohlaysizmi?</b>", reply_markup=CONFIRM_END_MARKUP, parse_mode="HTML")
        await state.set_state(QuizStates.confirming_end)
        return

    correct_answer = str(questions[current][1]).lower().strip()
    user_answer = message.text.lower().strip()
    await state.update_data(answered=True)
    
    wrong_answers = user_data.get('wrong_answers', [])
    if user_answer == correct_answer:
        await state.update_data(correct=user_data.get('correct', 0) + 1)
        await message.answer("<b>✅ To‘g‘ri javob!</b> 🌟", parse_mode="HTML")
    else:
        wrong_answers.append({
            'question': questions[current][0],
            'correct': correct_answer,
            'user_answer': user_answer
        })
        await state.update_data(wrong_answers=wrong_answers)
        await message.answer(f"<b>❌ Xato!</b>\nTo‘g‘ri javob: <i>{correct_answer}</i>", parse_mode="HTML")
    
    await state.update_data(current=current + 1)
    await send_question(message, state)

@dp.message(QuizStates.confirming_end)
async def confirm_end(message: types.Message, state: FSMContext):
    await save_user(message.from_user.id, message.from_user.username)
    if message.text == "✔️ Ha, tugatish":
        await end_test(message, state)
    elif message.text == "✖️ Yo‘q, davom etish":
        await send_question(message, state)
    else:
        await message.answer("<b>❗ Faqat 'Ha' yoki 'Yo‘q' ni tanlang!</b>", parse_mode="HTML")

async def end_test(message: types.Message, state: FSMContext):
    await cancel_timer(state)
    user_data = await state.get_data()
    correct = user_data.get('correct', 0)
    total = min(user_data.get('current', 0), len(user_data.get('questions', [])))
    percent = round((correct / total) * 100, 2) if total > 0 else 0
    wrong_answers = user_data.get('wrong_answers', [])
    
    result_header = "<b>🎉 Test yakunlandi! 🎉</b>\n\n"
    result_stats = (
        f"📊 <b>Savollar:</b> {total} ta\n"
        f"✅ <b>To‘g‘ri:</b> {correct} ta\n"
        f"❌ <b>Xato:</b> {total - correct} ta\n"
        f"📈 <b>Foiz:</b> {percent}%\n"
    )
    
    result_comment = (
        "🌟 <b>Zo‘r natija!</b> Siz ajoyib bilimga egasiz! 👏" if percent >= 90 else
        "✨ <b>Yaxshi harakat!</b> Juda yaxshi natija! 👍" if percent >= 70 else
        "📚 <b>O‘rtacha!</b> Yana mashq qiling, muvaffaqiyat yaqin! 😉" if percent >= 50 else
        "🚀 <b>Harakat qiling!</b> Bilimingizni oshirish uchun vaqt ajrating! 💪"
    )
    
    wrong_answers_text = ""
    if wrong_answers:
        wrong_answers_text = "\n<b>❌ Noto‘g‘ri javoblaringiz:</b>\n"
        for i, wa in enumerate(wrong_answers, 1):
            wrong_answers_text += (
                f"{i}. <i>{wa['question']}</i>\n"
                f"   Sizning javobingiz: <b>{wa['user_answer']}</b>\n"
                f"   To‘g‘ri javob: <b>{wa['correct']}</b>\n"
            )
    
    final_message = (
        f"{result_header}"
        f"<code>════════════════════</code>\n"
        f"{result_stats}"
        f"<code>════════════════════</code>\n"
        f"{result_comment}"
        f"{wrong_answers_text}"
        f"\n<code>════════════════════</code>\n"
        "<i>Yana sinab ko‘rish uchun /start ni bosing!</i>"
    )
    
    has_wrong_answers = bool(wrong_answers)
    await state.update_data(wrong_questions=wrong_answers if has_wrong_answers else [])
    await message.answer(
        final_message,
        parse_mode="HTML",
        reply_markup=get_main_menu(message.from_user.id == ADMIN_ID, has_wrong_answers)
        if not has_wrong_answers else REPEAT_WRONG_MARKUP
    )
    await state.set_state(None)

@dp.message(lambda msg: msg.text == "🔄 Xatolarni tuzatish")
async def repeat_wrong_questions(message: types.Message, state: FSMContext):
    await save_user(message.from_user.id, message.from_user.username)
    user_data = await state.get_data()
    wrong_questions = user_data.get('wrong_questions', [])
    
    if not wrong_questions:
        await message.answer(
            "<b>✅ Sizda xato javoblar yo‘q!</b> 🌟",
            parse_mode="HTML",
            reply_markup=get_main_menu(message.from_user.id == ADMIN_ID)
        )
        return
    
    questions = [(wq['question'], wq['correct']) for wq in wrong_questions]
    section = user_data.get('section', 'Dictionary')
    level = user_data.get('level', 'Easy') if section == "Dictionary" else None
    
    await state.update_data(
        questions=questions,
        current=0,
        correct=0,
        wrong_answers=[],
        section=section,
        level=level,
        available_questions=len(questions)
    )
    
    await message.answer(
        f"<b>🔄 Xato savollarni tuzatish boshlandi ({len(questions)} ta savol)</b>",
        parse_mode="HTML"
    )
    await send_question(message, state)

@dp.message(LearningStates.learning_menu)
async def learning_menu_handler(message: types.Message, state: FSMContext):
    await save_user(message.from_user.id, message.from_user.username)
    if message.text == "📖 Lug‘atlar":
        await state.update_data(dict_page=0)
        await message.answer("<b>📖 Lug‘at tanlash</b>\n\nKerakli lug‘atni tanlang:", reply_markup=get_dict_menu(), parse_mode="HTML")
        await state.set_state(LearningStates.choosing_dict)
    elif message.text == "📚 Grammatika":
        await state.update_data(grammar_page=0)
        await message.answer("<b>📚 Grammatika tanlash</b>\n\nBo‘limni tanlang:", reply_markup=get_grammar_menu(), parse_mode="HTML")
        await state.set_state(LearningStates.choosing_grammar)
    elif message.text == "↩️ Bosh menyuga":
        await start_handler(message, state)
    else:
        await message.answer("<b>❗ Iltimos, menyudan tanlang!</b>", parse_mode="HTML")

@dp.message(LearningStates.choosing_dict)
async def learning_choose_dict(message: types.Message, state: FSMContext):
    await save_user(message.from_user.id, message.from_user.username)
    user_data = await state.get_data()
    page = user_data.get('dict_page', 0)
    
    if message.text == "⬅️ Oldingi sahifa":
        page = max(0, page - 1)
        await state.update_data(dict_page=page)
        await message.answer("<b>📖 Lug‘at tanlash</b>\n\nKerakli lug‘atni tanlang:", reply_markup=get_dict_menu(page), parse_mode="HTML")
    elif message.text == "➡️ Keyingi sahifa":
        page += 1
        await state.update_data(dict_page=page)
        await message.answer("<b>📖 Lug‘at tanlash</b>\n\nKerakli lug‘atni tanlang:", reply_markup=get_dict_menu(page), parse_mode="HTML")
    else:
        selected_dict = message.text.replace("📖 ", "")
        if selected_dict in DICT_NAMES:
            if selected_dict not in DATA["Dictionary"]:
                await message.answer(
                    f"<b>❗ '{selected_dict}' lug‘ati mavjud emas!</b>\nBoshqa lug‘atni tanlang:",
                    reply_markup=get_dict_menu(page),
                    parse_mode="HTML"
                )
                return
            await state.update_data(section="Dictionary", selected_dict=selected_dict)
            await message.answer("<b>🌠 Daraja tanlash</b>\n\nDarajani tanlang:", reply_markup=LUGAT_LEVELS, parse_mode="HTML")
            await state.set_state(LearningStates.lugat_levels)
        elif message.text == "↩️ Orqaga":
            await message.answer("<b>📚 O‘quv rejimi</b>\n\nQuyidagilardan birini tanlang:", reply_markup=LEARNING_MENU, parse_mode="HTML")
            await state.set_state(LearningStates.learning_menu)
        else:
            await message.answer("<b>❗ Iltimos, lug‘atni tanlang!</b>", reply_markup=get_dict_menu(page), parse_mode="HTML")

@dp.message(LearningStates.choosing_grammar)
async def learning_choose_grammar(message: types.Message, state: FSMContext):
    await save_user(message.from_user.id, message.from_user.username)
    user_data = await state.get_data()
    page = user_data.get('grammar_page', 0)
    
    if message.text == "⬅️ Oldingi sahifa":
        page = max(0, page - 1)
        await state.update_data(grammar_page=page)
        await message.answer("<b>📚 Grammatika tanlash</b>\n\nBo‘limni tanlang:", reply_markup=get_grammar_menu(page), parse_mode="HTML")
    elif message.text == "➡️ Keyingi sahifa":
        page += 1
        await state.update_data(grammar_page=page)
        await message.answer("<b>📚 Grammatika tanlash</b>\n\nBo‘limni tanlang:", reply_markup=get_grammar_menu(page), parse_mode="HTML")
    else:
        selected_category = message.text.replace("📚 ", "")
        if selected_category in GRAMMAR_NAMES:
            if selected_category not in DATA["Grammar"]:
                await message.answer(
                    f"<b>❗ '{selected_category}' bo‘limi mavjud emas!</b>\nBoshqa bo‘limni tanlang:",
                    reply_markup=get_grammar_menu(page),
                    parse_mode="HTML"
                )
                return
            items = list(DATA["Grammar"].get(selected_category, {}).items())
            if not items:
                await message.answer(
                    f"<b>❗ '{selected_category}' bo‘limida ma’lumot yo‘q!</b>\nBoshqa bo‘limni tanlang:",
                    reply_markup=get_grammar_menu(page),
                    parse_mode="HTML"
                )
                return
            await state.update_data(section="Grammar", selected_category=selected_category, items=items, current_page=0)
            await show_learning_page(message, state)
        elif message.text == "↩️ Orqaga":
            await message.answer("<b>📚 O‘quv rejimi</b>\n\nQuyidagilardan birini tanlang:", reply_markup=LEARNING_MENU, parse_mode="HTML")
            await state.set_state(LearningStates.learning_menu)
        else:
            await message.answer("<b>❗ Iltimos, bo‘limni tanlang!</b>", reply_markup=get_grammar_menu(page), parse_mode="HTML")

@dp.message(LearningStates.lugat_levels)
async def learning_choose_level(message: types.Message, state: FSMContext):
    await save_user(message.from_user.id, message.from_user.username)
    level = LEVEL_MAPPING.get(message.text.replace(" daraja", ""))
    user_data = await state.get_data()
    selected_dict = user_data.get('selected_dict')
    
    if level in ["Easy", "Medium", "Hard"]:
        if selected_dict not in DATA["Dictionary"]:
            page = user_data.get('dict_page', 0)
            await message.answer(
                f"<b>❗ '{selected_dict}' lug‘ati mavjud emas!</b>",
                reply_markup=get_dict_menu(page),
                parse_mode="HTML"
            )
            await state.set_state(LearningStates.choosing_dict)
            return
        items = list(DATA["Dictionary"][selected_dict].get(level, {}).items())
        if not items:
            await message.answer(
                f"<b>❗ '{selected_dict}' lug‘atida '{level}' darajasida so‘zlar yo‘q!</b>\nBoshqa darajani tanlang:",
                reply_markup=LUGAT_LEVELS,
                parse_mode="HTML"
            )
            return
        await state.update_data(level=level, items=items, current_page=0)
        await show_learning_page(message, state)
    elif message.text == "↩️ Orqaga":
        page = user_data.get('dict_page', 0)
        await message.answer("<b>📖 Lug‘at tanlash</b>\n\nKerakli lug‘atni tanlang:", reply_markup=get_dict_menu(page), parse_mode="HTML")
        await state.set_state(LearningStates.choosing_dict)
    else:
        await message.answer("<b>❗ Iltimos, darajani tanlang!</b>", parse_mode="HTML")

@dp.message(LearningStates.showing_items)
async def learning_show_handler(message: types.Message, state: FSMContext):
    await save_user(message.from_user.id, message.from_user.username)
    user_data = await state.get_data()
    current_page = user_data.get('current_page', 0)
    total_pages = user_data.get('total_pages', 1)
    
    if message.text == "⬅️ Oldingi sahifa":
        current_page = max(0, current_page - 1)
        await state.update_data(current_page=current_page)
        await show_learning_page(message, state)
    elif message.text == "➡️ Keyingi sahifa":
        current_page = min(total_pages - 1, current_page + 1)
        await state.update_data(current_page=current_page)
        await show_learning_page(message, state)
    elif message.text == "↩️ Orqaga":
        if user_data.get('section') == "Dictionary":
            await message.answer("<b>🌠 Daraja tanlash</b>\n\nDarajani tanlang:", reply_markup=LUGAT_LEVELS, parse_mode="HTML")
            await state.set_state(LearningStates.lugat_levels)
        else:
            page = user_data.get('grammar_page', 0)
            await message.answer("<b>📚 Grammatika tanlash</b>\n\nBo‘limni tanlang:", reply_markup=get_grammar_menu(page), parse_mode="HTML")
            await state.set_state(LearningStates.choosing_grammar)
    else:
        await message.answer("<b>❗ Iltimos, menyudan tanlang!</b>", parse_mode="HTML")

async def show_learning_page(message: types.Message, state: FSMContext):
    await save_user(message.from_user.id, message.from_user.username)
    user_data = await state.get_data()
    section = user_data.get('section')
    items = user_data.get('items', [])
    current_page = user_data.get('current_page', 0)
    level = user_data.get('level') if section == "Dictionary" else None
    selected_dict = user_data.get('selected_dict') if section == "Dictionary" else user_data.get('selected_category')
    
    total_pages = (len(items) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    start = current_page * ITEMS_PER_PAGE
    end = min(start + ITEMS_PER_PAGE, len(items))
    page_items = items[start:end]
    
    item_list = "\n".join(f"{i + start + 1}. <b>{key}</b> → {value}" for i, (key, value) in enumerate(page_items))
    title = f"<b>📖 '{selected_dict}' - {level} daraja</b>" if section == "Dictionary" else f"<b>📚 '{selected_dict}' grammatikasi</b>"
    text = (
        f"{title}\n\n"
        f"{item_list}\n\n"
        f"<i>Sahifa: {current_page + 1}/{total_pages} | Jami: {len(items)} ta</i>"
    )
    
    await state.update_data(total_pages=total_pages)
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_learning_navigation(current_page, total_pages)
    )
    await state.set_state(LearningStates.showing_items)

# Webhook setup
async def on_startup(_):
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url)
    logger.info(f"Webhook set to {webhook_url}")

async def on_shutdown(_):
    await bot.delete_webhook()
    logger.info("Webhook deleted")

async def main():
    if os.getenv("RENDER"):  # Run as webhook on Render
        await start_webhook(
            dispatcher=dp,
            webhook_path=WEBHOOK_PATH,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            skip_updates=True,
            host=WEBAPP_HOST,
            port=WEBAPP_PORT
        )
    else:  # Run as polling locally
        max_retries = 3
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Botni ishga tushirish urinishi: {attempt + 1}/{max_retries}")
                await dp.start_polling(bot)
                break
            except TelegramNetworkError as e:
                logger.error(f"Tarmoq xatosi: {e}, {attempt + 1}/{max_retries} urinish")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    logger.critical("Maksimal urinishlar soni tugadi!")
                    raise
            except Exception as e:
                logger.error(f"Botni ishga tushirishda xato: {e}")
                raise
            finally:
                await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())