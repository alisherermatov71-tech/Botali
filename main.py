import asyncio
import aiohttp
import aiosqlite
import logging
import os
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ========== CONFIG ==========
BOT_TOKEN = os.getenv("BOT_TOKEN", "8811948718:AAEoP4731AVb-vYoezwj5U_Z8vqDESpSNpI")
ADMIN_ID = int(os.getenv("ADMIN_ID", 8078029788))
GRIZZLY_API = os.getenv("GRIZZLY_API", "bc7da6d7866c44761b0ad51b3e9482a6")
USD_TO_KZT = 500
MARGIN = 1.2 # 20% үстеме
REF_BONUS = 15
KASPI_NUM = "77471164091"
KASPI_NAME = "АББОС П"
CARD_NUM = "4400430307661584"
CARD_NAME = "АБДУЛЛО П"
DB_NAME = "grizzly.db"
API_URL = "https://grizzlysms.com/stubs/handler.php"

COUNTRIES = {
    "0": "🇷🇺 Ресей", "1": "🇺🇸 АҚШ", "2": "🇺🇦 Украина", "3": "🇬🇧 Ұлыбритания",
    "4": "🇭🇰 Гонконг", "5": "🇵🇱 Польша", "6": "🇰🇿 Қазақстан", "7": "🇮🇹 Италия",
    "8": "🇪 Эстония", "9": "🇱🇹 Литва", "10": "🇮🇳 Үндістан", "11": "🇲🇾 Малайзия",
    "12": "🇧🇷 Бразилия", "13": "🇹🇷 Түркия", "14": "🇮🇩 Индонезия", "15": "🇨🇴 Колумбия",
    "16": "🇧🇩 Бангладеш", "17": "🇳🇬 Нигерия", "18": "🇵🇭 Филиппин", "19": "🇻🇳 Вьетнам",
    "20": "🇲🇽 Мексика", "21": "🇦🇷 Аргентина", "22": "🇪🇬 Египет", "23": "🇵🇰 Пакистан", "24": "🇹🇭 Тайланд"
}
SERVICES = {"tg": "📱 Telegram", "wa": "💬 WhatsApp"}

# ========== DB ==========
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0, ref_id INTEGER, ref_bonus_given INTEGER DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, service TEXT, country TEXT, number TEXT, price REAL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        await db.execute("CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, photo_id TEXT, status TEXT DEFAULT 'pending')")
        await db.execute("CREATE TABLE IF NOT EXISTS channels(channel_id TEXT PRIMARY KEY)")
        await db.execute("CREATE TABLE IF NOT EXISTS active_numbers(id TEXT PRIMARY KEY, user_id INTEGER, number TEXT, service TEXT)")
        await db.commit()

async def get_balance(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        c = await db.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
        r = await c.fetchone()
        return r[0] if r else 0

async def add_balance(user_id, amount):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user_id,))
        await db.execute("UPDATE users SET balance = balance +? WHERE user_id=?", (amount, user_id))
        await db.commit()

# ========== UTILS ==========
async def check_sub(user_id, bot: Bot):
    async with aiosqlite.connect(DB_NAME) as db:
        c = await db.execute("SELECT channel_id FROM channels")
        channels = await c.fetchall()
    if not channels: return True
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch[0], user_id=user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        except: return False
    return True

async def get_channels_kb():
    async with aiosqlite.connect(DB_NAME) as db:
        c = await db.execute("SELECT channel_id FROM channels")
        channels = await c.fetchall()
    kb = [[InlineKeyboardButton(text=f"📢 Канал", url=f"https://t.me/{i[0].replace('-100','')}")] for i in channels]
    kb.append([InlineKeyboardButton(text="✅ Тексеру", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# ========== GRIZZLYSMS API ==========
async def api_call(params):
    params["api_key"] = GRIZZLY_API
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(API_URL, params=params, timeout=15) as r:
                return await r.json()
    except: return {"status": "ERROR"}

async def get_prices(): return await api_call({"action": "getPrices"})
async def get_number(service, country): return await api_call({"action": "getNumber", "service": service, "country": country})
async def get_status(number_id): return await api_call({"action": "getStatus", "id": number_id})

# ========== KEYBOARDS ==========
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 TOP 10 Ең арзан", callback_data="top10")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"), InlineKeyboardButton(text="🎁 Реферал", callback_data="ref")],
        [InlineKeyboardButton(text="💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton(text="💳 Баланс толықтыру", callback_data="topup")],
        [InlineKeyboardButton(text="📱 Telegram", callback_data="list_tg"), InlineKeyboardButton(text="💬 WhatsApp", callback_data="list_wa")],
        [InlineKeyboardButton(text="📜 Тарих", callback_data="history")]
    ])

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Пайдаланушылар", callback_data="a_users")],
        [InlineKeyboardButton(text="📢 Міндетті каналдар", callback_data="a_channels")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="a_stats")]
    ])

# ========== FSM ==========
class Topup(StatesGroup): waiting_photo = State()
class Admin(StatesGroup): wait_channel_add = State(); wait_channel_del = State()

# ========== HANDLERS ==========
router = Router()

@router.message(F.text.startswith("/start"))
async def start(m: Message):
    args = m.text.split()
    ref_id = int(args[1]) if len(args) > 1 and args[1].isdigit() and int(args[1])!= m.from_user.id else None
    async with aiosqlite.connect(DB_NAME) as db: await db.execute("INSERT OR IGNORE INTO users(user_id, ref_id) VALUES(?,?)", (m.from_user.id, ref_id)); await db.commit()
    await m.answer("👋 GrizzlySMS Виртуалды нөмірлер дүкені", reply_markup=main_menu())

@router.callback_query(F.data == "check_sub")
async def recheck(c: CallbackQuery):
    if await check_sub(c.from_user.id, bot):
        async with aiosqlite.connect(DB_NAME) as db:
            user = await db.execute_fetchone("SELECT ref_id, ref_bonus_given FROM users WHERE user_id=?", (c.from_user.id,))
            if user and user[0] and user[1] == 0:
                await add_balance(user[0], REF_BONUS)
                await db.execute("UPDATE users SET ref_bonus_given=1 WHERE user_id=?", (c.from_user.id,))
                await db.commit()
                await bot.send_message(user[0], f"🎉 +{REF_BONUS}₸. Сіздің рефералыңыз каналға жазылды.")
        await c.message.edit_text("✅ Рахмет! Жазылдыңыз.", reply_markup=main_menu())
    else: await c.answer("Сіз барлық каналдарға жазылмадыңыз", show_alert=True)

@router.callback_query(F.data == "balance")
async def balance(c: CallbackQuery):
    if not await check_sub(c.from_user.id, bot): await c.message.edit_text("⛔️ Каналдарға жазылыңыз:", reply_markup=await get_channels_kb()); return
    bal = await get_balance(c.from_user.id)
    await c.message.edit_text(f"💰 Сіздің балансыңыз: {bal:.2f} ₸", reply_markup=main_menu())

@router.callback_query(F.data == "profile")
async def profile(c: CallbackQuery):
    bal = await get_balance(c.from_user.id)
    async with aiosqlite.connect(DB_NAME) as db: orders = await db.execute_fetchone("SELECT COUNT(*) FROM orders WHERE user_id=?", (c.from_user.id,))
    await c.message.edit_text(f"👤 Профиль\nID: `{c.from_user.id}`\n💰 Баланс: {bal:.2f} ₸\n📦 Сатып алған: {orders[0]} номер", reply_markup=main_menu())

@router.callback_query(F.data == "ref")
async def ref_menu(c: CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        count = await db.execute_fetchone("SELECT COUNT(*) FROM users WHERE ref_id=?", (c.from_user.id,))
        earned = await db.execute_fetchone("SELECT COUNT(*) FROM users WHERE ref_id=? AND ref_bonus_given=1", (c.from_user.id,))
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start={c.from_user.id}"
    text = f"🎁 Реферал бағдарламасы\n\nСілтеме: `{ref_link}`\nШақырған: {count[0]}\nАктив: {earned[0]}\nТабыс: {earned[0] * REF_BONUS} ₸\n\nШарт: Адам каналға жазылған соң {REF_BONUS}₸"
    await c.message.edit_text(text, reply_markup=main_menu())

@router.callback_query(F.data == "topup")
async def topup(c: CallbackQuery, state: FSMContext):
    if not await check_sub(c.from_user.id, bot): await c.message.edit_text("⛔️ Каналдарға жазылыңыз:", reply_markup=await get_channels_kb()); return
    text = f"💳 Баланс толықтыру\nKaspi:\n📱 {KASPI_NUM}\n👤 {KASPI_NAME}\n\nКарта:\n💳 {CARD_NUM}\n👤 {CARD_NAME}\n\nТөлем жасап, чек скрин жіберіңіз"
    await c.message.edit_text(text); await state.set_state(Topup.waiting_photo)

@router.message(Topup.waiting_photo, F.photo)
async def get_photo(m: Message, state: FSMContext):
    photo_id = m.photo[-1].file_id
    async with aiosqlite.connect(DB_NAME) as db: await db.execute("INSERT INTO payments(user_id, photo_id) VALUES(?,?)", (m.from_user.id, photo_id)); await db.commit()
    await bot.send_photo(ADMIN_ID, photo_id, caption=f"Төлем: {m.from_user.id}",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"✅ Қабылдау +1000₸", callback_data=f"accept_{m.from_user.id}")]]))
    await m.answer("Чек әкімшіге жіберілді."); await state.clear()

@router.callback_query(F.data.startswith("accept_"))
async def accept_pay(c: CallbackQuery):
    if c.from_user.id!= ADMIN_ID: return
    user_id = int(c.data.split("_")[1]); await add_balance(user_id, 1000)
    await bot.send_message(user_id, "✅ Төлем қабылданды. +1000 ₸"); await c.message.edit_caption("✅ Қабылданды")

@router.callback_query(F.data == "top10")
async def top10(c: CallbackQuery):
    if not await check_sub(c.from_user.id, bot): await c.message.edit_text("⛔️ Каналдарға жазылыңыз:", reply_markup=await get_channels_kb()); return
    await c.message.edit_text("🔄 Бағаларды жүктеп жатырмын...")
    prices = await get_prices()
    if prices.get("status")!= "SUCCESS": await c.message.edit_text("API уақытша қолжетімсіз", reply_markup=main_menu()); return
    all_offers = []
    for service, service_name in SERVICES.items():
        if service in prices["data"]:
            for cid, info in prices["data"][service].items():
                if int(info["count"]) > 0:
                    price_kzt = int(float(info["cost"]) * USD_TO_KZT * MARGIN)
                    all_offers.append({"price": price_kzt, "text": f"{service_name} | {COUNTRIES.get(cid, f'Ел {cid}')} — {price_kzt} ₸ ({info['count']})", "callback": f"buy_{service}_{cid}"})
    top_10 = sorted(all_offers, key=lambda x: x["price"])[:10]
    if not top_10: await c.message.edit_text("Қазір номер жоқ. 10 мин кейін көріңіз", reply_markup=main_menu()); return
    kb = [[InlineKeyboardButton(text=i["text"], callback_data=i["callback"])] for i in top_10]
    kb.append([InlineKeyboardButton(text="⬅️ Артқа", callback_data="back")])
    await c.message.edit_text("🔥 TOP 10 Ең арзан ұсыныс:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("list_"))
async def service_list(c: CallbackQuery):
    if not await check_sub(c.from_user.id, bot): await c.message.edit_text("⛔️ Каналдарға жазылыңыз:", reply_markup=await get_channels_kb()); return
    service = "tg" if c.data == "list_tg" else "wa"
    await c.message.edit_text("🔄 Жүктелуде...")
    prices = await get_prices(); kb = []
    if prices.get("status")!= "SUCCESS": await c.message.edit_text("API қате", reply_markup=main_menu()); return
    for cid, cname in COUNTRIES.items():
        if service in prices["data"] and cid in prices["data"][service] and int(prices["data"][service][cid]["count"]) > 0:
            price_kzt = int(float(prices["data"][service][cid]["cost"]) * USD_TO_KZT * MARGIN)
            count = prices["data"][service][cid]["count"]
            kb.append([InlineKeyboardButton(text=f"{cname} — {price_kzt} ₸ ({count})", callback_data=f"buy_{service}_{cid}")])
    kb.append([InlineKeyboardButton(text="⬅️ Артқа", callback_data="back")])
    if not kb: await c.message.edit_text("Қазір номер жоқ", reply_markup=main_menu()); return
    await c.message.edit_text(f"{SERVICES[service]} үшін ел таңдаңыз:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("buy_"))
async def buy(c: CallbackQuery):
    _, service, country = c.data.split("_")
    prices = await get_prices()
    if service not in prices["data"] or country not in prices["data"][service] or int(prices["data"][service][country]["count"]) == 0:
        await c.answer("Бұл елде номер бітті", show_alert=True); return
    price_kzt = int(float(prices["data"][service][country]["cost"]) * USD_TO_KZT * MARGIN)
    bal = await get_balance(c.from_user.id)
    if bal < price_kzt: await c.answer(f"Баланс жеткіліксіз. Керек: {price_kzt}₸", show_alert=True); return

    res = await get_number(service, country)
    if res.get("status") == "SUCCESS":
        number = res["data"]["number"]; id = res["data"]["id"]
        await add_balance(c.from_user.id, -price_kzt)
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("INSERT INTO orders(user_id, service, country, number, price) VALUES(?,?,?,?,?)", (c.from_user.id, service, country, number, price_kzt))
            await db.execute("INSERT INTO active_numbers(id, user_id, number, service) VALUES(?,?,?,?)", (id, c.from_user.id, number, service))
            await db.commit()
        await c.message.edit_text(f"✅ Номер алынды!\n📱 Номер: +{number}\n💰 Бағасы: {price_kzt} ₸\n\nКодты күтіп тұрмын...", reply_markup=main_menu())
        asyncio.create_task(check_sms(id, c.from_user.id, number))
    else: await c.answer("Номер алу мүмкін болмады. Басқа елді таңдаңыз", show_alert=True)

async def check_sms(number_id, user_id, number):
    for i in range(20):
        await asyncio.sleep(30)
        res = await get_status(number_id)
        if res.get("status") == "SUCCESS" and res.get("data"):
            code = res["data"]
            await bot.send_message(user_id, f"🔥 Код келді!\n\n`{code}`\n📱 Номер: +{number}")
            async with aiosqlite.connect(DB_NAME) as db: await db.execute("DELETE FROM active_numbers WHERE id=?", (number_id,)); await db.commit()
            return
        elif res.get("status") == "CANCEL":
            await bot.send_message(user_id, f"❌ Номердің уақыты бітті: +{number}"); return
    await bot.send_message(user_id, f"⏰ 10 минут ішінде код келмеді: +{number}")

@router.callback_query(F.data == "history")
async def history(c: CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db: orders = await db.execute_fetchall("SELECT service, country, number, price FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10", (c.from_user.id,))
    text = "📜 Соңғы 10 тапсырыс:\n" + "\n".join([f"{SERVICES[i[0]]} {COUNTRIES.get(i[1],i[1])} +{i[2]} - {i[3]}₸" for i in orders]) if orders else "Тапсырыс жоқ"
    await c.message.edit_text(text, reply_markup=main_menu())

@router.callback_query(F.data == "back")
async def back(c: CallbackQuery): await c.message.edit_text("👋 Негізгі мәзір", reply_markup=main_menu())

# ========== ADMIN ==========
@router.message(F.text == "/admin")
async def admin_panel(m: Message):
    if m.from_user.id == ADMIN_ID: await m.answer("👑 Админ панель", reply_markup=admin_menu())

@router.callback_query(F.data == "a_channels")
async def a_channels(c: CallbackQuery):
    if c.from_user.id!= ADMIN_ID: return
    async with aiosqlite.connect(DB_NAME) as db: channels = await db.execute_fetchall("SELECT channel_id FROM channels")
    text = "📢 Каналдар:\n" + "\n".join([i[0] for i in channels]) if channels else "Канал жоқ"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Қосу", callback_data="add_channel")],[InlineKeyboardButton(text="➖ Өшіру", callback_data="del_channel")],[InlineKeyboardButton(text="⬅️ Артқа", callback_data="admin_back")]])
    await c.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data == "add_channel")
async def add_channel(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("@username немесе -100ID жіберіңіз"); await state.set_state(Admin.wait_channel_add)
@router.message(Admin.wait_channel_add)
async def save_channel(m: Message, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db: await db.execute("INSERT OR IGNORE INTO channels(channel_id) VALUES(?)", (m.text,)); await db.commit()
    await m.answer(f"✅ {m.text} қосылды"); await state.clear()

@router.callback_query(F.data == "del_channel")
async def del_channel(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Өшіретін канал ID жіберіңіз"); await state.set_state(Admin.wait_channel_del)
@router.message(Admin.wait_channel_del)
async def delete_channel(m: Message, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db: await db.execute("DELETE FROM channels WHERE channel_id=?", (m.text,)); await db.commit()
    await m.answer(f"✅ {m.text} өшірілді"); await state.clear()

@router.callback_query(F.data == "admin_back")
async def admin_back(c: CallbackQuery): await c.message.edit_text("👑 Админ панель", reply_markup=admin_menu())

# ========== RUN ==========
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(router)

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
