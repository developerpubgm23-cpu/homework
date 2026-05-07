import asyncio
import logging
import json
import base64
import html
import io
import os
import time
import zipfile
import aiosqlite
import openai
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton,
    InlineKeyboardMarkup, Message,
)

# ================================================================
#                       KONFIGURATSIYA
# ================================================================

BOT_TOKEN    = "8750252926:AAHITaGGUG8qwJ2ibHI05ucd8ObX7MSYUQ4"
ADMIN_IDS: List[int] = [7794276843]
DB_PATH      = "developer_ai.db"

# ── Groq API (barcha modellar shu yerda) ─────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE    = "https://api.groq.com/openai/v1"

# ── Google Gemini API (rasm generatsiya) ─────────────────────────
GEMINI_API_KEY            = os.getenv("GEMINI_API_KEY", "")
GEMINI_IMG_URL            = "https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-generate-001:predict"
GEMINI_FLASH_IMG_URL      = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent"
GEMINI_FLASH_PREVIEW_URL  = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image-preview:generateContent"

# ── OpenAI API (audio) ───────────────────────────────────────────
OPENAI_API_KEY          = os.getenv("OPENAI_API_KEY", "")
OPENAI_IMAGE_MODEL      = "gpt-image-1"
OPENAI_TRANSCRIBE_MODEL = "whisper-1"
OPENAI_CHAT_MODEL       = "gpt-4o-mini"
openai.api_key          = OPENAI_API_KEY

STICKER_IDS = {
    "welcome": "",
    "celebrate": "",
    "error": "",
}

# ── Checkout.uz ──────────────────────────────────────────────────
CHECKOUT_KEY  = os.getenv("CHECKOUT_KEY", "MjY1ZmZiZmMwMGQxNTc0MDU2MmU")
CHECKOUT_BASE = "https://checkout.uz/api/v1"

GROQ_MODELS: Dict[str, dict] = {
    # ── Meta LLaMA — Production ───────────────────────────────────
    "llama3_70b": {
        "id":    "llama-3.3-70b-versatile",
        "name":  "🦙 LLaMA 3.3 70B",
        "desc":  "Kuchli va universal (280 t/s)",
        "plan":  "free",
        "supports_system": True,
    },
    "llama3_8b": {
        "id":    "llama-3.1-8b-instant",
        "name":  "⚡ LLaMA 3.1 8B",
        "desc":  "Eng tez (560 t/s)",
        "plan":  "free",
        "supports_system": True,
    },
    # ── Meta LLaMA 4 — Preview ────────────────────────────────────
    "llama4_scout": {
        "id":    "meta-llama/llama-4-scout-17b-16e-instruct",
        "name":  "🦙 LLaMA 4 Scout 17B",
        "desc":  "Eng yangi, multimodal (750 t/s)",
        "plan":  "premium",
        "supports_system": True,
    },
    # ── OpenAI GPT OSS — Production ───────────────────────────────
    "gpt_oss_120b": {
        "id":    "openai/gpt-oss-120b",
        "name":  "🤖 GPT OSS 120B",
        "desc":  "OpenAI open-weight, veb qidirish (500 t/s)",
        "plan":  "premium",
        "supports_system": True,
    },
    "gpt_oss_20b": {
        "id":    "openai/gpt-oss-20b",
        "name":  "⚡ GPT OSS 20B",
        "desc":  "Eng tez OpenAI modeli (1000 t/s)",
        "plan":  "free",
        "supports_system": True,
    },
    # ── Qwen — Preview ────────────────────────────────────────────
    "qwen3_32b": {
        "id":    "qwen/qwen3-32b",
        "name":  "🌊 Qwen 3 32B",
        "desc":  "Ko'p tilli, mantiqiy (400 t/s)",
        "plan":  "free",
        "supports_system": True,
    },
    # ── Groq Compound Systems — Production ────────────────────────
    "compound": {
        "id":    "groq/compound",
        "name":  "🔬 Groq Compound",
        "desc":  "Veb qidirish + kod ijrosi (450 t/s)",
        "plan":  "professional",
        "supports_system": True,
    },
    "compound_mini": {
        "id":    "groq/compound-mini",
        "name":  "🔬 Groq Compound Mini",
        "desc":  "Yengil veb qidirish (450 t/s)",
        "plan":  "premium",
        "supports_system": True,
    },
}

DEFAULT_MODEL = "gpt_oss_20b"

# ── Tarif sozlamalari ─────────────────────────────────────────────
PLANS = {
    "free": {
        "uz": "🆓 Bepul",
        "ru": "🆓 Бесплатно",
        "en": "🆓 Free",
        "price":       0,
        "daily_limit": 50,
        "image_gen":   True,   
        "file_analysis": True,
        "free_models": True,
    },
    "premium": {
        "uz": "⚡ Premium",
        "ru": "⚡ Premium",
        "en": "⚡ Premium",
        "price":       19_990,
        "daily_limit": 100,
        "image_gen":   True,
        "file_analysis": True,
        "free_models": True,
    },
    "professional": {
        "uz": "👑 Professional",
        "ru": "👑 Professional",
        "en": "👑 Professional",
        "price":       39_990,
        "daily_limit": 1000,
        "image_gen":   True,
        "file_analysis": True,
        "free_models": True,
    },
}

MAX_HISTORY  = 20
MAX_TOKENS   = 2048
TEMPERATURE  = 0.7
FREE_IMAGE_LIMIT = 10

# ── System Prompt ─────────────────────────────────────────────────
SYSTEM_PROMPT = {
    "uz": (
        "Sen DEVELOPER AI — professional va do'stona sun'iy intellekt yordamchisan. "
        "Foydalanuvchi bilan O'zbek, Rus yoki Ingliz tilida muloqot qilasan. "
        "Qaysi tilda yozsalar, o'sha tilda javob berasan. "
        "Aniq, foydali, batafsil javoblar berasan. "
        "Dasturlash, matematika, ijod, tahlil — barcha sohalarda yordam berasan. "
        "Javoblarni chiroyli formatlaysan (HTML: <b>, <i>, <code>, <pre>). "
        "Hech qachon o'zingning texnik tafsilotlarini (API, model nomi) aytma."
    ),
    "ru": (
        "Ты DEVELOPER AI — профессиональный и дружелюбный ИИ-ассистент. "
        "Общайся на том языке, на котором пишет пользователь. "
        "Давай точные, полезные, подробные ответы. "
        "Форматируй красиво (HTML: <b>, <i>, <code>, <pre>). "
        "Никогда не раскрывай технические детали."
    ),
    "en": (
        "You are DEVELOPER AI — a professional and friendly AI assistant. "
        "Respond in whatever language the user writes. "
        "Give accurate, helpful, detailed answers. "
        "Format beautifully (HTML: <b>, <i>, <code>, <pre>). "
        "Never reveal technical details."
    ),
}

LANG_NAMES = {"uz": "🇺🇿 O'zbek", "ru": "🇷🇺 Русский", "en": "🇬🇧 English"}

# ── UI Tekstlar ───────────────────────────────────────────────────
T = {
    "welcome": {
        "uz": (
            "👋 <b>Salom, {name}!</b>\n\n"
            "🤖 <b>DEVELOPER AI</b> ga xush kelibsiz!\n\n"
            "<blockquote>"
            "💬 Istalgan savolingizni yozing\n"
            "🌐 3 tilda: O'zbek · Rus · Ingliz\n"
            "🧠 Suhbat tarixini eslab qoladi\n"
            "📄 Fayllarni tahlil qiladi\n"
            "🎨 Rasm yaratadi (bepul!)\n"
            "💻 Dasturlashda yordam beradi"
            "</blockquote>\n\n"
            "📋 <b>Tarif:</b> {plan} | "
            "📊 <b>Bugun:</b> {used}/{limit}\n\n"
            "👇 <b>Savolingizni yozing!</b>"
        ),
        "ru": (
            "👋 <b>Привет, {name}!</b>\n\n"
            "🤖 Добро пожаловать в <b>DEVELOPER AI</b>!\n\n"
            "<blockquote>"
            "💬 Задайте любой вопрос\n"
            "🌐 3 языка: Узбекский · Русский · Английский\n"
            "🧠 Запоминает историю чата\n"
            "📄 Анализирует файлы\n"
            "🎨 Создаёт изображения (бесплатно!)\n"
            "💻 Помогает с программированием"
            "</blockquote>\n\n"
            "📋 <b>Тариф:</b> {plan} | "
            "📊 <b>Сегодня:</b> {used}/{limit}\n\n"
            "👇 <b>Напишите вопрос!</b>"
        ),
        "en": (
            "👋 <b>Hello, {name}!</b>\n\n"
            "🤖 Welcome to <b>DEVELOPER AI</b>!\n\n"
            "<blockquote>"
            "💬 Ask anything you want\n"
            "🌐 3 languages: Uzbek · Russian · English\n"
            "🧠 Remembers chat history\n"
            "📄 Analyzes files\n"
            "🎨 Generates images (free!)\n"
            "💻 Helps with programming"
            "</blockquote>\n\n"
            "📋 <b>Plan:</b> {plan} | "
            "📊 <b>Today:</b> {used}/{limit}\n\n"
            "👇 <b>Type your question!</b>"
        ),
    },
    "limit_reached": {
        "uz": (
            "⚠️ <b>Bugungi limitingiz tugadi!</b>\n\n"
            "Bugun {limit} ta so'rov yubordingiz.\n\n"
            "📋 <b>Pro</b> yoki <b>Premium</b> tarif orqali "
            "limitingizni kengaytiring!"
        ),
        "ru": (
            "⚠️ <b>Дневной лимит исчерпан!</b>\n\n"
            "Сегодня вы отправили {limit} запросов.\n\n"
            "📋 Расширьте лимит через тариф <b>Pro</b> или <b>Premium</b>!"
        ),
        "en": (
            "⚠️ <b>Daily limit reached!</b>\n\n"
            "You've sent {limit} requests today.\n\n"
            "📋 Upgrade to <b>Pro</b> or <b>Premium</b> for more!"
        ),
    },
    "server_error": {
        "uz": "⚠️ <b>Server bilan muammo yuz berdi.</b>\nBiroz kutib qayta urinib ko'ring.",
        "ru": "⚠️ <b>Возникла проблема с сервером.</b>\nПодождите и попробуйте снова.",
        "en": "⚠️ <b>Server issue occurred.</b>\nPlease try again in a moment.",
    },
    "image_limit_reached": {
        "uz": "⚠️ <b>Free tarifda rasm generatsiya uchun kuniga {limit} ta limit bor.</b>\nIltimos, /plans orqali premiumga o'iting.",
        "ru": "⚠️ <b>Для бесплатного тарифа ограничение на генерацию изображений {limit} в день.</b>\nПожалуйста, перейдите на /plans.",
        "en": "⚠️ <b>Free plan allows {limit} image generations per day.</b>\nPlease upgrade via /plans.",
    },
    "ai11_soon": {
        "uz": "🚀 <b>AI 1.1 modeli yaratilmoqda...</b>\n\nTez orada taqdim etiladi! 🎉",
        "ru": "🚀 <b>Модель AI 1.1 в процессе создани...</b>\n\nСкоро будет представлена! 🎉",
        "en": "🚀 <b>AI 1.1 model is being created...</b>\n\nComing soon! 🎉",
    },
    "clear_done": {
        "uz": "🗑 <b>Suhbat tarixi tozalandi!</b>",
        "ru": "🗑 <b>История чата очищена!</b>",
        "en": "🗑 <b>Chat history cleared!</b>",
    },
    "image_gen": {
        "uz": "🎨 Rasm yaratilmoqda...",
        "ru": "🎨 Создаётся изображение...",
        "en": "🎨 Generating image...",
    },
    "select_lang": {
        "uz": "🌐 <b>Til tanlang:</b>",
        "ru": "🌐 <b>Выберите язык:</b>",
        "en": "🌐 <b>Select language:</b>",
    },
}

# ================================================================
#                          LOGGING & BOT
# ================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("DevAI")

bot     = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp      = Dispatcher(storage=storage)

# ================================================================
#                          DATABASE
# ================================================================

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                tg_id       INTEGER PRIMARY KEY,
                username    TEXT,
                full_name   TEXT,
                lang        TEXT DEFAULT 'uz',
                plan        TEXT DEFAULT 'free',
                plan_until  TEXT,
                model_key   TEXT DEFAULT 'llama3_70b',
                joined_at   TEXT DEFAULT (datetime('now')),
                is_banned   INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS usage (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                date        TEXT NOT NULL,
                count       INTEGER DEFAULT 0,
                UNIQUE(user_id, date)
            );
            CREATE TABLE IF NOT EXISTS image_usage (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                date        TEXT NOT NULL,
                count       INTEGER DEFAULT 0,
                UNIQUE(user_id, date)
            );
            CREATE TABLE IF NOT EXISTS payments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                plan        TEXT NOT NULL,
                amount      INTEGER NOT NULL,
                checkout_id TEXT,
                status      TEXT DEFAULT 'pending',
                created_at  TEXT DEFAULT (datetime('now')),
                paid_at     TEXT
            );
            CREATE TABLE IF NOT EXISTS conversations (
                user_id     INTEGER PRIMARY KEY,
                history     TEXT DEFAULT '[]',
                updated_at  TEXT DEFAULT (datetime('now'))
            );
        """)
        await db.commit()
    log.info("DB ready ✓")


async def db_upsert_user(tg_id: int, username: str, full_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT tg_id FROM users WHERE tg_id=?", (tg_id,)) as c:
            exists = await c.fetchone()
        if not exists:
            await db.execute(
                "INSERT INTO users(tg_id,username,full_name) VALUES(?,?,?)",
                (tg_id, username, full_name)
            )
        else:
            await db.execute(
                "UPDATE users SET username=?,full_name=? WHERE tg_id=?",
                (username, full_name, tg_id)
            )
        await db.commit()


async def db_get_user(tg_id: int) -> Optional[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)) as c:
            return await c.fetchone()


async def db_set(tg_id: int, field: str, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE users SET {field}=? WHERE tg_id=?", (value, tg_id))
        await db.commit()


async def db_get_usage(tg_id: int) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT count FROM usage WHERE user_id=? AND date=?", (tg_id, today)
        ) as c:
            row = await c.fetchone()
            return row[0] if row else 0


async def db_inc_usage(tg_id: int):
    today = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO usage(user_id,date,count) VALUES(?,?,1) "
            "ON CONFLICT(user_id,date) DO UPDATE SET count=count+1",
            (tg_id, today)
        )
        await db.commit()


async def db_get_image_usage(tg_id: int) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT count FROM image_usage WHERE user_id=? AND date=?", (tg_id, today)
        ) as c:
            row = await c.fetchone()
            return row[0] if row else 0


async def db_inc_image_usage(tg_id: int):
    today = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO image_usage(user_id,date,count) VALUES(?,?,1) "
            "ON CONFLICT(user_id,date) DO UPDATE SET count=count+1",
            (tg_id, today)
        )
        await db.commit()


async def db_get_history(tg_id: int) -> List[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT history FROM conversations WHERE user_id=?", (tg_id,)
        ) as c:
            row = await c.fetchone()
            if row:
                try:
                    return json.loads(row[0])
                except Exception:
                    return []
    return []


async def db_save_history(tg_id: int, history: List[dict]):
    if len(history) > MAX_HISTORY * 2:
        history = history[-MAX_HISTORY * 2:]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    h_json = json.dumps(history, ensure_ascii=False)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO conversations(user_id,history,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET history=?,updated_at=?",
            (tg_id, h_json, now, h_json, now)
        )
        await db.commit()


async def db_clear_history(tg_id: int):
    await db_save_history(tg_id, [])


async def db_all_ids() -> List[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT tg_id FROM users WHERE is_banned=0") as c:
            return [r[0] for r in await c.fetchall()]


async def db_admin_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        s = {}
        today = datetime.now().strftime("%Y-%m-%d")
        for k, sql in [
            ("total",  "SELECT COUNT(*) FROM users"),
            ("pro",    "SELECT COUNT(*) FROM users WHERE plan='pro'"),
            ("prem",   "SELECT COUNT(*) FROM users WHERE plan='premium'"),
            ("msgs",   "SELECT COALESCE(SUM(count),0) FROM usage"),
            ("today",  f"SELECT COALESCE(SUM(count),0) FROM usage WHERE date='{today}'"),
            ("rev",    "SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='paid'"),
        ]:
            async with db.execute(sql) as c:
                s[k] = (await c.fetchone())[0]
    return s


async def db_save_payment(user_id: int, plan: str, amount: int, checkout_id: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO payments(user_id,plan,amount,checkout_id) VALUES(?,?,?,?)",
            (user_id, plan, amount, checkout_id)
        )
        await db.commit()
        return cur.lastrowid


async def db_confirm_payment(checkout_id: str) -> Optional[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM payments WHERE checkout_id=? AND status='pending'",
            (checkout_id,)
        ) as c:
            pay = await c.fetchone()
        if not pay:
            return None
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        until = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        await db.execute(
            "UPDATE payments SET status='paid',paid_at=? WHERE checkout_id=?",
            (now, checkout_id)
        )
        await db.execute(
            "UPDATE users SET plan=?,plan_until=? WHERE tg_id=?",
            (pay["plan"], until, pay["user_id"])
        )
        await db.commit()
        return pay

# ================================================================
#                          HELPERS
# ================================================================

def get_lang(user: Optional[aiosqlite.Row]) -> str:
    if user and user["lang"]:
        return user["lang"]
    return "uz"


def get_plan(user: Optional[aiosqlite.Row]) -> str:
    if not user:
        return "free"
    plan  = user["plan"] or "free"
    until = user["plan_until"]
    if plan != "free" and until:
        try:
            if datetime.strptime(until, "%Y-%m-%d") < datetime.now():
                return "free"
        except Exception:
            pass
    return plan


def get_limit(plan: str) -> int:
    return PLANS.get(plan, PLANS["free"])["daily_limit"]


def t(key: str, lang: str, **kw) -> str:
    text = T.get(key, {}).get(lang) or T.get(key, {}).get("uz", "")
    if kw:
        try:
            text = text.format(**kw)
        except Exception:
            pass
    return text


def bold_text(text: str) -> str:
    return f"<b>{html.escape(text)}</b>"

async def answer_msg(
    msg: Message,
    text: str,
    reply_markup=None,
    sticker_key: Optional[str] = None,
):
    if sticker_key:
        await send_sticker_if_available(msg.chat.id, sticker_key)
    await msg.answer(text, parse_mode="HTML", reply_markup=reply_markup)


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


async def send_sticker_if_available(chat_id: int, sticker_key: str):
    sticker_id = STICKER_IDS.get(sticker_key)
    if not sticker_id:
        return
    try:
        await bot.send_sticker(chat_id, sticker=sticker_id)
    except Exception:
        pass


async def safe_edit(msg, text, kb=None):
    try:
        await msg.edit_text(text, reply_markup=kb)
    except Exception:
        try:
            await msg.delete()
        except Exception:
            pass
        await answer_msg(msg, text, reply_markup=kb)


async def ensure_user(msg: Message) -> Optional[aiosqlite.Row]:
    await db_upsert_user(
        msg.from_user.id,
        msg.from_user.username or "",
        msg.from_user.full_name or ""
    )
    return await db_get_user(msg.from_user.id)

#

async def groq_chat(
    messages: List[dict],
    model_key: str = DEFAULT_MODEL,
) -> Optional[str]:
    """
    Groq API ga POST so'rov.
    model_key → GROQ_MODELS dan model_id olinadi.

    MUHIM: Ba'zi modellar (Gemma) system role qabul qilmaydi.
    supports_system=False bo'lsa, system content user xabariga birlashtiriladi.
    """
    model_info = GROQ_MODELS.get(model_key, GROQ_MODELS[DEFAULT_MODEL])
    model_id   = model_info["id"]
    supports_system = model_info.get("supports_system", True)

    # System message ni tekshirish
    if not supports_system:
        # System contentni birinchi user xabariga qo'shib yuborish
        fixed_messages = []
        system_content = ""
        for m in messages:
            if m["role"] == "system":
                system_content = m["content"]
            else:
                fixed_messages.append(m)
        # System contentni birinchi user xabariga prefiks qilib qo'shish
        if system_content and fixed_messages:
            for i, m in enumerate(fixed_messages):
                if m["role"] == "user":
                    fixed_messages[i] = {
                        "role":    "user",
                        "content": f"[Yo'riqnoma: {system_content}]\n\n{m['content']}"
                    }
                    break
        messages = fixed_messages

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":       model_id,
        "messages":    messages,
        "max_tokens":  MAX_TOKENS,
        "temperature": TEMPERATURE,
        "stream":      False,
    }

    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{GROQ_BASE}/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as r:
                if r.status == 429:
                    log.warning(f"Groq rate limit: {model_id}")
                    return "__LIMIT__"
                if r.status != 200:
                    err_text = await r.text()
                    log.error(f"Groq {r.status} [{model_id}]: {err_text[:200]}")
                    # Fallback: default modelga qayta urinish
                    if model_key != DEFAULT_MODEL:
                        log.info(f"Fallback to {DEFAULT_MODEL}")
                        return await groq_chat(messages, DEFAULT_MODEL)
                    return None
                data = await r.json()
                content = data["choices"][0]["message"]["content"]
                return content
    except asyncio.TimeoutError:
        log.error(f"Groq timeout: {model_id}")
        return None
    except Exception as e:
        log.error(f"Groq error [{model_id}]: {e}")
        return None


async def groq_list_models() -> List[str]:
    """Groq da mavjud modellar ro'yxati."""
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{GROQ_BASE}/models",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                data = await r.json()
                return [m["id"] for m in data.get("data", [])]
    except Exception:
        return []

# ================================================================
#   RASM YARATISH — Together AI FLUX.1-schnell (BEPUL)
#   1) Groq LLaMA 3.1 8B   → promptni inglizchaga tarjima + boyitish
#   2) Together AI FLUX.1-schnell → 1024×1024 PNG rasm
#   API: https://docs.together.ai/docs/images-overview
# ================================================================

async def enhance_image_prompt(prompt: str, lang: str) -> str:
    """
    Foydalanuvchi promptini ingliz tiliga tarjima qilib,
    rasm yaratish uchun yaxshilaydi.
    Groq Gemma 2 9B orqali bajariladi.
    """
    system = (
        "You are an expert at creating image generation prompts. "
        "Translate the user's description to English if needed, "
        "then enhance it to be detailed, vivid, and suitable for image generation. "
        "Return ONLY the enhanced English prompt, nothing else. Max 100 words."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": f"Create image prompt for: {prompt}"},
    ]
    result = await groq_chat(messages, "llama3_8b")   # eng tez bepul model
    if result and result not in ("__LIMIT__", None):
        return result.strip()
    return prompt


async def openai_generate_image(prompt: str) -> Optional[bytes]:
    if not OPENAI_API_KEY:
        return None

    async def _download_image_url(url: str) -> Optional[bytes]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status == 200:
                        return await response.read()
                    log.error("OpenAI Image URL download failed %s: %s", response.status, await response.text())
        except Exception:
            log.exception("OpenAI Image URL download failed")
        return None

    def _get_value(item, key):
        if isinstance(item, dict):
            return item.get(key)
        return getattr(item, key, None)

    def _extract_image_data(result):
        data_list = None
        if hasattr(result, 'data') and result.data:
            data_list = result.data
        elif hasattr(result, 'output') and result.output:
            data_list = result.output
        if not data_list:
            return None, None
        first = data_list[0]
        return _get_value(first, 'b64_json'), _get_value(first, 'url')

    try:
        result = await openai.images.generate(
            model=OPENAI_IMAGE_MODEL,
            prompt=prompt,
            size="1024x1024",
            response_format="b64_json",
        )
    except Exception as e:
        msg = str(e).lower()
        if "response_format" in msg or "unknown parameter" in msg:
            try:
                result = await openai.images.generate(
                    model=OPENAI_IMAGE_MODEL,
                    prompt=prompt,
                    size="1024x1024",
                )
            except Exception as e2:
                log.error(f"OpenAI Image error after fallback: {e2}")
                return None
        else:
            log.error(f"OpenAI Image error: {e}")
            return None

    b64, url = _extract_image_data(result)
    if b64:
        return base64.b64decode(b64)
    if url:
        return await _download_image_url(url)

    log.error("OpenAI Image: missing b64_json or url in response")
    return None


async def openai_audio_transcribe(raw: bytes) -> Optional[str]:
    if not OPENAI_API_KEY:
        return None
    try:
        audio_file = io.BytesIO(raw)
        audio_file.name = "voice.ogg"
        response = await openai.Audio.acreate(
            model=OPENAI_TRANSCRIBE_MODEL,
            file=audio_file,
        )
        return response.text.strip() if getattr(response, 'text', None) else None
    except Exception as e:
        log.error(f"OpenAI Audio transcription error: {e}")
        return None


async def openai_chat(messages: List[dict]) -> Optional[str]:
    if not OPENAI_API_KEY:
        return None
    try:
        response = await openai.ChatCompletion.acreate(
            model=OPENAI_CHAT_MODEL,
            messages=messages,
            temperature=TEMPERATURE,
        )
        return response.choices[0].message.content
    except Exception as e:
        log.error(f"OpenAI chat error: {e}")
        return None


def extract_docx_text(raw: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
        text = []
        in_tag = False
        for ch in xml:
            if ch == "<":
                in_tag = True
                continue
            if ch == ">":
                in_tag = False
                text.append(" ")
                continue
            if not in_tag:
                text.append(ch)
        return " ".join("".join(text).split())
    except Exception:
        return ""


async def generate_image(prompt: str, lang: str) -> Optional[bytes]:
    """
    OpenAI orqali rasm yaratish.
    1) Promptni inglizchaga tarjima qilib yaxshilash.
    2) OpenAI Images API orqali PNG rasm olish.
    """
    enhanced = await enhance_image_prompt(prompt, lang)
    log.info(f"Image prompt (enhanced): {enhanced[:120]}")
    image = await openai_generate_image(enhanced)
    if image:
        return image
    log.warning("OpenAI image generation failed, trying Gemini fallback")
    return await gemini_generate_image(enhanced)


async def gemini_generate_image(prompt: str) -> Optional[bytes]:
    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "size": "1024x1024",
            "sampleCount": 1,
        },
    }
    headers = {"Content-Type": "application/json"}
    url = f"{GEMINI_IMG_URL}?key={GEMINI_API_KEY}"

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, headers=headers, timeout=120) as response:
                if response.status != 200:
                    body = await response.text()
                    log.error("Gemini image error %s: %s", response.status, body)
                    return await _generate_image_flash(prompt)

                body = await response.json()
                predictions = body.get("predictions") or []
                if not predictions:
                    log.error("Gemini image missing predictions: %s", body)
                    return await _generate_image_flash(prompt)

                image_data = predictions[0].get("image") or {}
                b64_data = image_data.get("imageBytes") or image_data.get("b64") or image_data.get("data")
                if not b64_data:
                    log.error("Gemini image response missing base64 field: %s", body)
                    return await _generate_image_flash(prompt)

                return base64.b64decode(b64_data)
        except Exception:
            log.exception("Gemini image request failed")
            return await _generate_image_flash(prompt)


async def _generate_image_flash(prompt: str) -> Optional[bytes]:
    payload = {
        "model": "gemini-2.5-flash-image",
        "text": prompt,
        "mediaType": "image/png",
        "image": {"size": "1024x1024"},
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GEMINI_API_KEY}",
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(GEMINI_FLASH_IMG_URL, json=payload, headers=headers, timeout=120) as response:
                if response.status != 200:
                    body = await response.text()
                    log.error("Gemini flash image error %s: %s", response.status, body)
                    return None

                body = await response.json()
                candidates = body.get("candidates") or []
                if not candidates:
                    log.error("Gemini flash image missing candidates: %s", body)
                    return None

                image_data = candidates[0].get("b64")
                if not image_data:
                    log.error("Gemini flash image missing b64: %s", body)
                    return None

                return base64.b64decode(image_data)
        except Exception:
            log.exception("Gemini flash image request failed")
            return None


@dp.message(F.voice)
async def handle_voice(msg: Message, state: FSMContext):
    cur = await state.get_state()
    if cur:
        return

    user = await ensure_user(msg)
    lang = get_lang(user)
    plan = get_plan(user)

    used = await db_get_usage(msg.from_user.id)
    limit = get_limit(plan)
    if used >= limit:
        await answer_msg(msg, t("limit_reached", lang, limit=limit), reply_markup=kb_plans(lang))
        return

    if not msg.voice:
        return

    await bot.send_chat_action(msg.chat.id, "typing")
    try:
        file = await bot.get_file(msg.voice.file_id)
        data = await bot.download_file(file.file_path)
        raw = data.read()
        transcript = await openai_audio_transcribe(raw)
        if not transcript:
            await answer_msg(msg, t("server_error", lang))
            return

        history = await db_get_history(msg.from_user.id)
        sys_p = SYSTEM_PROMPT.get(lang, SYSTEM_PROMPT["uz"])
        messages = [{"role": "system", "content": sys_p}]
        messages.extend(history[-MAX_HISTORY * 2:])
        messages.append({"role": "user", "content": transcript})

        resp = await openai_chat(messages)
        if resp is None:
            await answer_msg(msg, f"⚠️ <b>{t('server_error', lang)}</b>")
            return

        await answer_msg(msg, f"🎧 <b>Transcription:</b>\n<code>{transcript}</code>", parse_mode="HTML")
        await answer_msg(msg, f"✅ <b>Javob:</b>\n\n{resp}")

        history.append({"role": "user", "content": transcript})
        history.append({"role": "assistant", "content": resp})
        await db_save_history(msg.from_user.id, history)
        await db_inc_usage(msg.from_user.id)
    except Exception as e:
        log.error(f"Voice handling error: {e}")
        await answer_msg(msg, t("server_error", lang))

# ================================================================
#                       CHECKOUT.UZ
# ================================================================

async def co_create(amount: int, desc: str) -> Optional[dict]:
    headers = {
        "Authorization": f"Bearer {CHECKOUT_KEY}",
        "Content-Type":  "application/json",
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{CHECKOUT_BASE}/create_payment",
                json={"amount": amount, "description": desc},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)
                if data.get("status") == "success":
                    p = data.get("payment", {})
                    return {
                        "url": p.get("_url", ""),
                        "id":  p.get("_uuid") or str(p.get("_id", "")),
                    }
    except Exception as e:
        log.error(f"Checkout: {e}")
    return None


async def co_check(checkout_id: str) -> str:
    headers = {
        "Authorization": f"Bearer {CHECKOUT_KEY}",
        "Content-Type":  "application/json",
    }
    try:
        payload = ({"uuid": checkout_id} if "-" in str(checkout_id)
                   else {"id": int(checkout_id)})
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{CHECKOUT_BASE}/status_payment",
                json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)
                return str(data.get("data", {}).get("status", "pending")).lower()
    except Exception:
        return "error"

# ================================================================
#                       FSM STATES
# ================================================================

class ImageFlow(StatesGroup):
    enter_prompt = State()

class CodeFlow(StatesGroup):
    chatting = State()

class ServerFlow(StatesGroup):
    wait_zip = State()

class AdminFlow(StatesGroup):
    broadcast = State()

# ================================================================
#                       KEYBOARDS
# ================================================================

def kb_main(lang: str, plan: str, admin: bool = False) -> InlineKeyboardMarkup:
    lb = {
        "uz": {"ai10":"🤖 AI 1.0 (Faol)","ai11":"🚀 AI 1.1 (Tez orada)",
               "img":"🎨 Rasm yaratish","code":"🧑‍💻 Kod yozish","video":"🎬 Video generatsiya",
               "plans":"📋 Tariflar", "server":"⚙️ Serverga o'rnatish",
               "clear":"🗑 Tarixni tozalash","acc":"📊 Hisobim",
               "lang":"🌐 Til","help":"❓ Yordam","admin":"🛠 Admin Panel"},
        "ru": {"ai10":"🤖 AI 1.0 (Активен)","ai11":"🚀 AI 1.1 (Скоро)",
               "img":"🎨 Создать картинку","code":"🧑‍💻 Создать код","video":"🎬 Генерация видео",
               "plans":"📋 Тарифы", "server":"⚙️ Установить на сервер",
               "clear":"🗑 Очистить историю","acc":"📊 Мой аккаунт",
               "lang":"🌐 Язык","help":"❓ Помощь","admin":"🛠 Панель администратора"},
        "en": {"ai10":"🤖 AI 1.0 (Active)","ai11":"🚀 AI 1.1 (Soon)",
               "img":"🎨 Generate Image","code":"🧑‍💻 Generate Code","video":"🎬 Generate Video",
               "plans":"📋 Plans", "server":"⚙️ Install on Server",
               "clear":"🗑 Clear History","acc":"📊 My Account",
               "lang":"🌐 Language","help":"❓ Help","admin":"🛠 Admin Panel"},
    }.get(lang, {})
    keyboard = [
        [
            InlineKeyboardButton(text=lb.get("ai10","🤖 AI 1.0"),  callback_data="nav:ai10"),
            InlineKeyboardButton(text=lb.get("ai11","🚀 AI 1.1"),  callback_data="nav:ai11"),
        ],
        [
            InlineKeyboardButton(text=lb.get("img","🎨 Rasm"),     callback_data="nav:image"),
            InlineKeyboardButton(text=lb.get("code","🧑‍💻Kod yozish"),  callback_data="nav:code"), 
        ],    
        [
            InlineKeyboardButton(text=lb.get("video","🎬 Video generatsiya"), callback_data="nav:video"),
            InlineKeyboardButton(text=lb.get("server","⚙️ Serverga o'rnatish"), callback_data="nav:server"),
        ],
        [
            InlineKeyboardButton(text=lb.get("plans","📋 Tariflar"), callback_data="nav:plans"),
            InlineKeyboardButton(text=lb.get("clear","🗑 Tarix"),   callback_data="nav:clear"),
        ],
        [
            InlineKeyboardButton(text=lb.get("acc","📊 Hisob"),     callback_data="nav:account"),
            InlineKeyboardButton(text=lb.get("lang","🌐 Til"),      callback_data="nav:lang"),
        ],
        [
            InlineKeyboardButton(text=lb.get("help","❓ Yordam"),    callback_data="nav:help"),
        ],
    ]
    if admin:
        keyboard.append([
            InlineKeyboardButton(text=lb.get("admin","🛠 Admin Panel"), callback_data="nav:admin")
        ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def kb_models(lang: str, user_plan: str) -> InlineKeyboardMarkup:
    """Barcha Groq modellari."""
    rows = []
    for key, info in GROQ_MODELS.items():
        req    = info["plan"]
        avail  = (
            user_plan == "premium" or
            (user_plan == "pro" and req in ("free","pro")) or
            (user_plan == "free" and req == "free")
        )
        lock   = "" if avail else " 🔒"
        rows.append([InlineKeyboardButton(
            text=f"{info['name']}{lock} — {info['desc']}",
            callback_data=f"setmodel:{key}" if avail else f"locked:{req}"
        )])
    back_txt = {"uz":"◀️ Orqaga","ru":"◀️ Назад","en":"◀️ Back"}.get(lang,"◀️")
    rows.append([InlineKeyboardButton(text=back_txt, callback_data="back:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_plans(lang: str) -> InlineKeyboardMarkup:
    rows = []
    for k, info in PLANS.items():
        if k == "free":
            continue
        p = info["price"]
        p_str = f"{p//1000}K so'm/oy"
        rows.append([InlineKeyboardButton(
            text=f"{info[lang]} — {p_str}",
            callback_data=f"buyplan:{k}"
        )])
    back = {"uz":"◀️ Orqaga","ru":"◀️ Назад","en":"◀️ Back"}.get(lang,"◀️")
    rows.append([InlineKeyboardButton(text=back, callback_data="back:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_lang() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇺🇿 O'zbek",  callback_data="setlang:uz"),
        InlineKeyboardButton(text="🇷🇺 Русский",  callback_data="setlang:ru"),
        InlineKeyboardButton(text="🇬🇧 English",  callback_data="setlang:en"),
    ]])


def kb_back(lang: str) -> InlineKeyboardMarkup:
    back = {"uz":"◀️ Orqaga","ru":"◀️ Назад","en":"◀️ Back"}.get(lang,"◀️")
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=back, callback_data="back:main")
    ]])


def kb_code_exit(lang: str) -> InlineKeyboardMarkup:
    """Code AI sessiyasida exit va clear tugmalari."""
    lb = {
        "uz": {"exit": "🔴 Chiqish", "clear": "🗑 Tarixni tozalash"},
        "ru": {"exit": "🔴 Выход",   "clear": "🗑 Очистить историю"},
        "en": {"exit": "🔴 Exit",    "clear": "🗑 Clear History"},
    }.get(lang, {"exit": "🔴 Exit", "clear": "🗑 Clear"})
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=lb["exit"],  callback_data="code:exit"),
        InlineKeyboardButton(text=lb["clear"], callback_data="code:clear"),
    ]])


def kb_pay(url: str, pay_id: str, lang: str) -> InlineKeyboardMarkup:
    pay_txt   = {"uz":"💳 To'lov qilish","ru":"💳 Оплатить","en":"💳 Pay Now"}.get(lang,"💳")
    check_txt = {"uz":"✅ Tekshirish","ru":"✅ Проверить","en":"✅ Check"}.get(lang,"✅")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=pay_txt,   url=url)],
        [InlineKeyboardButton(text=check_txt, callback_data=f"checkpay:{pay_id}")],
        [InlineKeyboardButton(
            text={"uz":"◀️ Orqaga","ru":"◀️ Назад","en":"◀️ Back"}.get(lang,"◀️"),
            callback_data="back:main"
        )],
    ])

# ================================================================
#                       WELCOME
# ================================================================

async def send_welcome(target, user, lang: str, plan: str, admin: bool = False):
    used  = await db_get_usage(user["tg_id"])
    limit = get_limit(plan)
    name  = (user["full_name"] or "").split()[0] or "Foydalanuvchi"
    text  = t("welcome", lang,
               name=name,
               plan=PLANS[plan][lang],
               used=used, limit=limit)
    if isinstance(target, Message):
        await send_sticker_if_available(target.chat.id, "welcome")
        await target.answer(text, reply_markup=kb_main(lang, plan, admin))
    else:
        await safe_edit(target, text, kb_main(lang, plan, admin))

# ================================================================
#                       /start
# ================================================================

@dp.message(Command("start"))
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    user = await ensure_user(msg)
    lang = get_lang(user)
    plan = get_plan(user)
    await send_welcome(msg, user, lang, plan, is_admin(msg.from_user.id))

# ================================================================
#                       NAVIGATION
# ================================================================

@dp.callback_query(F.data == "back:main")
async def cb_back(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    user = await db_get_user(call.from_user.id)
    if not user:
        await answer_msg(call.message, "/start bosing")
        return
    await send_welcome(call.message, user, get_lang(user), get_plan(user), is_admin(call.from_user.id))


@dp.callback_query(F.data == "nav:ai11")
async def cb_ai11(call: CallbackQuery):
    user = await db_get_user(call.from_user.id)
    lang = get_lang(user)
    await call.answer(t("ai11_soon", lang), show_alert=True)


async def send_admin_panel(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    await state.clear()
    s = await db_admin_stats()
    models_list = await groq_list_models()
    models_txt  = "\n".join(f"  • <code>{m}</code>" for m in models_list[:15])
    await msg.answer(
        (
            f"🛡️ <b>Admin Panel</b>\n\n"
            f"👥 Jami: <b>{s['total']}</b>\n"
            f"⚡ Pro: <b>{s['pro']}</b>  |  👑 Premium: <b>{s['prem']}</b>\n"
            f"💬 Jami so'rovlar: <b>{s['msgs']}</b>\n"
            f"📊 Bugun: <b>{s['today']}</b>\n"
            f"💰 Daromad: <b>{s['rev']:,} so'm</b>\n\n"
            f"<b>Groq da mavjud modellar:</b>\n{models_txt}"
        ),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📣 Broadcast", callback_data="adm:bc")],
            [InlineKeyboardButton(text="📊 Statistics", callback_data="adm:stats")],
            [InlineKeyboardButton(text="◀️ Orqaga", callback_data="back:main")],
        ])
    )


@dp.callback_query(F.data == "nav:admin")
async def cb_nav_admin(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌ Access denied", show_alert=True)
        return
    await call.answer()
    await send_admin_panel(call.message, state)


@dp.callback_query(F.data == "adm:bc")
async def cb_adm_bc(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(AdminFlow.broadcast)
    await call.answer()
    await safe_edit(call.message, "📣 Broadcast xabarini yozing:", None)


@dp.callback_query(F.data == "adm:stats")
async def cb_adm_stats(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.answer()
    await send_admin_panel(call.message, state)


@dp.callback_query(F.data == "nav:clear")
async def cb_clear(call: CallbackQuery):
    user = await db_get_user(call.from_user.id)
    lang = get_lang(user)
    await db_clear_history(call.from_user.id)
    await call.answer(t("clear_done", lang), show_alert=True)


@dp.callback_query(F.data == "nav:lang")
async def cb_lang(call: CallbackQuery):
    user = await db_get_user(call.from_user.id)
    lang = get_lang(user)
    await call.answer()
    await safe_edit(call.message, t("select_lang", lang), kb_lang())


@dp.callback_query(F.data.startswith("setlang:"))
async def cb_setlang(call: CallbackQuery):
    nl = call.data.split(":")[1]
    await db_set(call.from_user.id, "lang", nl)
    await call.answer(LANG_NAMES[nl])
    user = await db_get_user(call.from_user.id)
    await send_welcome(call.message, user, nl, get_plan(user))


@dp.callback_query(F.data == "nav:code")
async def cb_code_nav(call: CallbackQuery, state: FSMContext):
    user = await ensure_user(call.message)
    lang = get_lang(user)
    plan = get_plan(user)
    await db_set(call.from_user.id, "model_key", "llama3_8b")
    _code_histories[call.from_user.id] = []
    await state.set_state(CodeFlow.chatting)
    await call.answer()
    greet = {
        "uz": (
            "💻 <b>CODE AI — Kod yozuvchi AI</b>\n\n"
            "⚡️ <b>LLaMA 3.1 8B</b> modeli kod yozish uchun tanlandi.\n"
            "📌 Python, JS, Go, Rust, C++, Java va boshqalar.\n\n"
            "<i>Yozishni boshlang yoki kod yuboring.</i>"
        ),
        "ru": (
            "💻 <b>CODE AI — ИИ для программирования</b>\n\n"
            "⚡️ <b>LLaMA 3.1 8B</b> теперь используется для кода.\n"
            "📌 Python, JS, Go, Rust, C++, Java и др.\n\n"
            "<i>Начните писать или отправьте код.</i>"
        ),
        "en": (
            "💻 <b>CODE AI — AI Coding Assistant</b>\n\n"
            "⚡️ <b>LLaMA 3.1 8B</b> is now active for code generation.\n"
            "📌 Python, JS, Go, Rust, C++, Java and more.\n\n"
            "<i>Start typing or send your code.</i>"
        ),
    }.get(lang, "💻 CODE AI started.")
    await safe_edit(call.message, greet, kb_code_exit(lang))


@dp.callback_query(F.data == "nav:video")
async def cb_video_nav(call: CallbackQuery):
    user = await ensure_user(call.message)
    lang = get_lang(user)
    text = {
        "uz": "🎬 Video generatsiya xizmati hozirda sozlanmoqda. Tez orada taqdim etamiz!",
        "ru": "🎬 Сервис генерации видео настраивается. Скоро будет доступен!",
        "en": "🎬 Video generation service is being configured. Coming soon!",
    }.get(lang, "🎬 Video generation service is being configured. Coming soon!")
    await call.answer(text, show_alert=True)


@dp.callback_query(F.data == "nav:server")
async def cb_server(call: CallbackQuery, state: FSMContext):
    user = await ensure_user(call.message)
    lang = get_lang(user)
    await call.answer()
    
    msgs = {
        "uz": (
            "🌐 <b>DEVELOPER AI Browser</b>\n\n"
            "Rasmiy browser ochildi. Google kabi ishlaydi!\n\n"
            "✨ <b>Imkoniyatlar:</b>\n"
            "• 🔍 Google qidiruv\n"
            "• 🎤 Ovoz bilan qidirish\n"
            "• 📌 Yorliq saqlash\n"
            "• ⚙️ Moslashtirish"
        ),
        "ru": (
            "🌐 <b>DEVELOPER AI Browser</b>\n\n"
            "Официальный браузер открыт. Работает как Google!\n\n"
            "✨ <b>Возможности:</b>\n"
            "• 🔍 Поиск Google\n"
            "• 🎤 Голосовой поиск\n"
            "• 📌 Сохранение ярлыков\n"
            "• ⚙️ Настройка"
        ),
        "en": (
            "🌐 <b>DEVELOPER AI Browser</b>\n\n"
            "Official browser is open. Works like Google!\n\n"
            "✨ <b>Features:</b>\n"
            "• 🔍 Google Search\n"
            "• 🎤 Voice Search\n"
            "• 📌 Save Shortcuts\n"
            "• ⚙️ Customize"
        ),
    }.get(lang, "🌐 Browser opened!")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text={"uz":"🌐 Browserga o'tish","ru":"🌐 Открыть браузер","en":"🌐 Open Browser"}.get(lang,"🌐"),
            url="http://127.0.0.1:8080"
        )],
        [InlineKeyboardButton(
            text={"uz":"↩️ Orqaga","ru":"↩️ Назад","en":"↩️ Back"}.get(lang,"↩️"),
            callback_data="back:main"
        )]
    ])
    
    await safe_edit(call.message, msgs, kb)


@dp.callback_query(F.data == "nav:ai10")
async def cb_ai10(call: CallbackQuery):
    user = await db_get_user(call.from_user.id)
    lang = get_lang(user)
    plan = get_plan(user)
    await call.answer()
    hdr = {
        "uz": "🤖 <b>AI 1.0 — Model tanlang</b>\n\n<i>Barchasi bepul!</i>",
        "ru": "🤖 <b>AI 1.0 — Выберите модель</b>\n\n<i>Все бесплатно!</i>",
        "en": "🤖 <b>AI 1.0 — Select Model</b>\n\n<i>All free!</i>",
    }.get(lang, "🤖 Model:")
    await safe_edit(call.message, hdr, kb_models(lang, plan))


@dp.callback_query(F.data.startswith("setmodel:"))
async def cb_setmodel(call: CallbackQuery):
    key  = call.data.split(":")[1]
    user = await db_get_user(call.from_user.id)
    lang = get_lang(user)
    plan = get_plan(user)
    m    = GROQ_MODELS.get(key)
    if not m:
        await call.answer("❌", show_alert=True); return

    req   = m["plan"]
    avail = (
        plan == "premium" or
        (plan == "pro" and req in ("free","pro")) or
        (plan == "free" and req == "free")
    )
    if not avail:
        msg = {
            "uz": f"🔒 Bu model {req.capitalize()} tarif uchun!",
            "ru": f"🔒 Эта модель для тарифа {req.capitalize()}!",
            "en": f"🔒 This model requires {req.capitalize()} plan!",
        }.get(lang,"🔒")
        await call.answer(msg, show_alert=True); return

    await db_set(call.from_user.id, "model_key", key)
    await call.answer(f"✅ {m['name']}")
    txt = {
        "uz": f"✅ <b>{m['name']}</b> tanlandi!\n\n{m['desc']}\n\nEndi yozing!",
        "ru": f"✅ <b>{m['name']}</b> выбрана!\n\n{m['desc']}\n\nПишите!",
        "en": f"✅ <b>{m['name']}</b> selected!\n\n{m['desc']}\n\nStart writing!",
    }.get(lang,"✅")
    await safe_edit(call.message, txt, kb_back(lang))


@dp.callback_query(F.data.startswith("locked:"))
async def cb_locked(call: CallbackQuery):
    user = await db_get_user(call.from_user.id)
    lang = get_lang(user)
    req  = call.data.split(":")[1]
    msg  = {
        "uz": f"🔒 Bu model <b>{req.capitalize()}</b> tarif uchun.\n📋 Tariflar bo'limiga o'ting.",
        "ru": f"🔒 Эта модель для тарифа <b>{req.capitalize()}</b>.\n📋 Перейдите в тарифы.",
        "en": f"🔒 This model requires <b>{req.capitalize()}</b> plan.\n📋 Go to Plans.",
    }.get(lang,"🔒")
    await call.answer(msg[:200], show_alert=True)

# ================================================================
#                       HISOB
# ================================================================

@dp.callback_query(F.data == "nav:account")
async def cb_account(call: CallbackQuery):
    user = await db_get_user(call.from_user.id)
    lang = get_lang(user)
    plan = get_plan(user)
    used  = await db_get_usage(call.from_user.id)
    limit = get_limit(plan)
    mk    = user["model_key"] or DEFAULT_MODEL
    mn    = GROQ_MODELS.get(mk, GROQ_MODELS[DEFAULT_MODEL])["name"]
    until = user["plan_until"] or "—"
    txt = {
        "uz": (
            f"📊 <b>Mening accountim</b>\n\n"
            f"📰 <b>{call.from_user.full_name}</b>\n"
            f"🆔 <code>{call.from_user.id}</code>\n"
            f"📋 Tarif: <b>{PLANS[plan]['uz']}</b>\n"
            f"📅 Tugaydi: <b>{until}</b>\n"
            f"🤖 Model: <b>{mn}</b>\n"
            f"📊 Bugungi: <b>{used}/{limit}</b>"
        ),
        "ru": (
            f"📊 <b>Мой аккаунт</b>\n\n"
            f"📰 <b>{call.from_user.full_name}</b>\n"
            f"🆔 <code>{call.from_user.id}</code>\n"
            f"📋 Тариф: <b>{PLANS[plan]['ru']}</b>\n"
            f"📅 До: <b>{until}</b>\n"
            f"🤖 Модель: <b>{mn}</b>\n"
            f"📊 Сегодня: <b>{used}/{limit}</b>"
        ),
        "en": (
            f"📊 <b>My Account</b>\n\n"
            f"📰 <b>{call.from_user.full_name}</b>\n"
            f"🆔 <code>{call.from_user.id}</code>\n"
            f"📋 Plan: <b>{PLANS[plan]['en']}</b>\n"
            f"📅 Until: <b>{until}</b>\n"
            f"🤖 Model: <b>{mn}</b>\n"
            f"📊 Today: <b>{used}/{limit}</b>"
        ),
    }.get(lang,"")
    await call.answer()
    await safe_edit(call.message, txt, kb_back(lang))

# ================================================================
#                       YORDAM
# ================================================================

@dp.callback_query(F.data == "nav:help")
async def cb_help(call: CallbackQuery):
    user = await db_get_user(call.from_user.id)
    lang = get_lang(user)
    txt = {
        "uz": (
            "❓ <b>Yordam</b>\n\n"
            "💬 <b>Matn</b> — Istalgan savol yozing\n"
            "📄 <b>Fayl</b> — .py, .js, .txt, .docx va boshqalar\n"
            "🖼 <b>Rasm</b> — Rasmni tavsiflab bering\n"
            "🎨 <b>/image</b> yoki <b>🎨 Rasm yaratish</b> tugmasi\n\n"
            "🤖 <b>AI 1.0 modellari (barchasi bepul):</b>\n"
            "• LLaMA 4 Maverick/Scout (Meta, yangi)\n"
            "• LLaMA 3.3 70B (kuchli, universal)\n"
            "• DeepSeek R1 (mantiq, tahlil)\n"
            "• Qwen 2.5 32B/Coder (ko'p til, kod)\n"
            "• Mixtral 8x7B (uzun kontekst)\n"
            "• Gemma 2 9B (Google)\n"
            "• Mistral Saba (tez)\n\n"
            "/clear — Tarixni tozalash\n"
            "/model — Model tanlash\n"
            "/plans — Tariflar\n"
            "/code — 💻 Kod yozuvchi AI"
        ),
        "ru": (
            "❓ <b>Помощь</b>\n\n"
            "💬 <b>Текст</b> — Любой вопрос\n"
            "📄 <b>Файл</b> — .py, .js, .txt, .docx и др.\n"
            "🖼 <b>Фото</b> — Опишите изображение\n"
            "🎨 <b>/image</b> или кнопка <b>🎨 Создать картинку</b>\n\n"
            "🤖 <b>Модели AI 1.0 (все бесплатно):</b>\n"
            "• LLaMA 4 Maverick/Scout (Meta, новые)\n"
            "• LLaMA 3.3 70B (мощный)\n"
            "• DeepSeek R1 (логика, анализ)\n"
            "• Qwen 2.5 32B/Coder (многоязычный, код)\n"
            "• Mixtral 8x7B (длинный контекст)\n"
            "• Gemma 2 9B (Google)\n"
            "• Mistral Saba (быстрый)\n\n"
            "/clear — Очистить историю\n"
            "/model — Выбор модели\n"
            "/plans — Тарифы\n"
            "/code — 💻 ИИ для написания кода"
        ),
        "en": (
            "❓ <b>Help</b>\n\n"
            "💬 <b>Text</b> — Ask anything\n"
            "📄 <b>File</b> — .py, .js, .txt, .docx etc.\n"
            "🖼 <b>Photo</b> — Describe the image\n"
            "🎨 <b>/image</b> or the image button\n\n"
            "🤖 <b>AI 1.0 models (all free):</b>\n"
            "• LLaMA 4 Maverick/Scout (Meta, new)\n"
            "• LLaMA 3.3 70B (powerful)\n"
            "• DeepSeek R1 (logic, analysis)\n"
            "• Qwen 2.5 32B/Coder (multilingual, code)\n"
            "• Mixtral 8x7B (long context)\n"
            "• Gemma 2 9B (Google)\n"
            "• Mistral Saba (fast)\n\n"
            "/clear — Clear history\n"
            "/model — Select model\n"
            "/plans — Plans\n"
            "/code — 💻 AI Coding Assistant\n"
            "/translate — 🔤 Translate text"
        ),
    }.get(lang,"")
    await call.answer()
    await safe_edit(call.message, txt, kb_back(lang))

# ================================================================
#                       TARIFLAR
# ================================================================

@dp.callback_query(F.data == "nav:plans")
async def cb_plans(call: CallbackQuery):
    user = await db_get_user(call.from_user.id)
    lang = get_lang(user)
    txt = {
        "uz": (
            "💎 <b>Tariflar</b>\n\n"
            "🆓 <b>Bepul</b> — 0 so'm\n"
            "  • Kuniga 30 ta so'rov\n"
            "  • Barcha bepul modellar (10 ta)\n"
            "  • Rasm yaratish ✅\n"
            "  • Fayl tahlili ✅\n\n"
            "⚡ <b>Pro</b> — 19,900 so'm/oy\n"
            "  • Kuniga 300 ta so'rov\n"
            "  • Barcha modellar + Compound Beta\n"
            "  • Ustuvor javob ✅\n\n"
            "👑 <b>Premium</b> — 39,900 so'm/oy\n"
            "  • Kuniga 1000 ta so'rov\n"
            "  • Barcha modellar\n"
            "  • Maksimal tezlik ✅"
        ),
        "ru": (
            "💎 <b>Тарифы</b>\n\n"
            "🆓 <b>Бесплатно</b> — 0 сум\n"
            "  • 30 запросов в день\n"
            "  • Все бесплатные модели (10 шт)\n"
            "  • Генерация изображений ✅\n"
            "  • Анализ файлов ✅\n\n"
            "⚡ <b>Pro</b> — 19 900 сум/мес\n"
            "  • 300 запросов в день\n"
            "  • Все модели + Compound Beta\n"
            "  • Приоритетный ответ ✅\n\n"
            "👑 <b>Premium</b> — 39 900 сум/мес\n"
            "  • 1000 запросов в день\n"
            "  • Все модели\n"
            "  • Максимальная скорость ✅"
        ),
        "en": (
            "💎 <b>Plans</b>\n\n"
            "🆓 <b>Free</b> — 0 UZS\n"
            "  • 30 requests/day\n"
            "  • All free models (10 models)\n"
            "  • Image generation ✅\n"
            "  • File analysis ✅\n\n"
            "⚡ <b>Pro</b> — 19,900 UZS/month\n"
            "  • 300 requests/day\n"
            "  • All models + Compound Beta\n"
            "  • Priority response ✅\n\n"
            "👑 <b>Premium</b> — 39,900 UZS/month\n"
            "  • 1000 requests/day\n"
            "  • All models\n"
            "  • Maximum speed ✅"
        ),
    }.get(lang,"")
    await call.answer()
    await safe_edit(call.message, txt, kb_plans(lang))


@dp.callback_query(F.data.startswith("buyplan:"))
async def cb_buyplan(call: CallbackQuery):
    pk   = call.data.split(":")[1]
    user = await db_get_user(call.from_user.id)
    lang = get_lang(user)
    info = PLANS.get(pk)
    if not info:
        await call.answer("❌", show_alert=True); return

    amount = info["price"]
    desc   = f"DEVELOPER AI {info[lang]} — 1 oy"
    pay    = await co_create(amount, desc)

    if not pay:
        await call.answer(t("server_error", lang)[:200], show_alert=True); return

    await db_save_payment(call.from_user.id, pk, amount, pay["id"])
    txt = {
        "uz": f"💳 <b>{info['uz']}</b>\n\n💰 {amount:,} so'm/oy\n\nTo'lash uchun bosing:",
        "ru": f"💳 <b>{info['ru']}</b>\n\n💰 {amount:,} сум/мес\n\nНажмите для оплаты:",
        "en": f"💳 <b>{info['en']}</b>\n\n💰 {amount:,} UZS/month\n\nClick to pay:",
    }.get(lang,"")
    await call.answer()
    await safe_edit(call.message, txt, kb_pay(pay["url"], pay["id"], lang))


@dp.callback_query(F.data.startswith("checkpay:"))
async def cb_checkpay(call: CallbackQuery):
    cid  = call.data.split(":",1)[1]
    user = await db_get_user(call.from_user.id)
    lang = get_lang(user)
    st   = await co_check(cid)
    if st in ("paid","completed"):
        pay = await db_confirm_payment(cid)
        if pay:
            pk = pay["plan"]
            pi = PLANS.get(pk, {})
            ok = {
                "uz": f"🎉 <b>To'lov tasdiqlandi!</b>\n✅ {pi.get('uz',pk)} — 30 kun!",
                "ru": f"🎉 <b>Оплата подтверждена!</b>\n✅ {pi.get('ru',pk)} — 30 дней!",
                "en": f"🎉 <b>Payment confirmed!</b>\n✅ {pi.get('en',pk)} — 30 days!",
            }.get(lang,"✅")
            await call.answer("✅")
            await safe_edit(call.message, ok, kb_back(lang))
        else:
            await call.answer({"uz":"Allaqachon aktivlashtirilgan!","ru":"Уже активировано!","en":"Already activated!"}[lang], show_alert=True)
    else:
        await call.answer({"uz":"⏳ Hali to'lanmagan.","ru":"⏳ Ещё не оплачено.","en":"⏳ Not paid yet."}[lang], show_alert=True)

# ================================================================
#                    RASM YARATISH
# ================================================================

@dp.callback_query(F.data == "nav:image")
async def cb_image_nav(call: CallbackQuery, state: FSMContext):
    user = await db_get_user(call.from_user.id)
    lang = get_lang(user)
    await call.answer()
    txt = {
        "uz": "🎨 <b>Rasm yaratish</b>\n\nRasmni O'zbek, Rus yoki Ingliz tilida tasvirlab yozing:\n\n<i>Misol: «ko'k osmonda uchayotgan ot»</i>",
        "ru": "🎨 <b>Создание изображения</b>\n\nОпишите желаемое изображение:\n\n<i>Пример: «лошадь летящая в синем небе»</i>",
        "en": "🎨 <b>Image Generation</b>\n\nDescribe the image you want:\n\n<i>Example: «a horse flying in blue sky»</i>",
    }.get(lang,"🎨")
    await state.set_state(ImageFlow.enter_prompt)
    await safe_edit(call.message, txt, kb_back(lang))


@dp.message(Command("image"))
async def cmd_image(msg: Message, state: FSMContext):
    user = await ensure_user(msg)
    lang = get_lang(user)
    prompt = (msg.text or "").replace("/image","").strip()
    if not prompt:
        await state.set_state(ImageFlow.enter_prompt)
        txt = {
            "uz":"🎨 Rasmni tasvirlab yozing:",
            "ru":"🎨 Опишите изображение:",
            "en":"🎨 Describe the image:",
        }.get(lang,"")
        await answer_msg(msg, txt, reply_markup=kb_back(lang))
        return
    await _do_image(msg, prompt, lang)


@dp.message(ImageFlow.enter_prompt)
async def msg_image_prompt(msg: Message, state: FSMContext):
    user = await ensure_user(msg)
    lang = get_lang(user)
    await state.clear()
    await _do_image(msg, msg.text or "", lang)


async def _do_image(msg: Message, prompt: str, lang: str):
    if not prompt.strip():
        return
    user = await ensure_user(msg)
    plan = get_plan(user)
    if plan == "free":
        image_used = await db_get_image_usage(msg.from_user.id)
        if image_used >= FREE_IMAGE_LIMIT:
            await answer_msg(msg, 
                f"⚠️ <b>{t('image_limit_reached', lang, limit=FREE_IMAGE_LIMIT)}</b>",
                reply_markup=kb_plans(lang)
            )
            return
    wait = await answer_msg(msg, t("image_gen", lang))
    await bot.send_chat_action(msg.chat.id, "upload_photo")
    if plan == "free":
        await db_inc_image_usage(msg.from_user.id)
    img = await generate_image(prompt, lang)
    try:
        await wait.delete()
    except Exception:
        pass
    if img:
        cap = {
            "uz": f"🎨 <b>Tayyor!</b>\n📝 <i>{prompt[:80]}</i>",
            "ru": f"🎨 <b>Готово!</b>\n📝 <i>{prompt[:80]}</i>",
            "en": f"🎨 <b>Done!</b>\n📝 <i>{prompt[:80]}</i>",
        }.get(lang,"🎨")
        await send_sticker_if_available(msg.chat.id, "celebrate")
        await msg.answer_photo(
            types.BufferedInputFile(img, filename="image.jpg"),
            caption=cap
        )
    else:
        await answer_msg(msg, f"⚠️ <b>{t('server_error', lang)}</b>")

# ================================================================
#                    ASOSIY XABAR HANDLER
# ================================================================

@dp.message(F.text, StateFilter(None))
async def handle_text(msg: Message, state: FSMContext):
    """Foydalanuvchi xabari → Groq API → javob."""
    cur = await state.get_state()
    if cur:
        return

    uid  = msg.from_user.id
    text = (msg.text or "").strip()
    if not text:
        return

    user = await ensure_user(msg)
    lang = get_lang(user)
    plan = get_plan(user)
    mkey = user["model_key"] or DEFAULT_MODEL

    # Limit tekshirish
    used  = await db_get_usage(uid)
    limit = get_limit(plan)
    if used >= limit:
        await answer_msg(msg, 
            f"⚠️ <b>{t('limit_reached', lang, limit=limit)}</b>",
            reply_markup=kb_plans(lang)
        )
        return

    await bot.send_chat_action(msg.chat.id, "typing")

    # Tarix + system prompt
    history = await db_get_history(uid)
    sys_p   = SYSTEM_PROMPT.get(lang, SYSTEM_PROMPT["uz"])
    messages = [{"role": "system", "content": sys_p}]
    messages.extend(history[-MAX_HISTORY * 2:])
    messages.append({"role": "user", "content": text})

    resp = await groq_chat(messages, mkey)

    if resp == "__LIMIT__":
        await answer_msg(msg, t("limit_reached", lang, limit=limit), reply_markup=kb_plans(lang))
        return

    if resp is None:
        await answer_msg(msg, f"⚠️ <b>{t('server_error', lang)}</b>")
        return

    # Tarixga qo'shish
    history.append({"role": "user",      "content": text})
    history.append({"role": "assistant", "content": resp})
    await db_save_history(uid, history)
    await db_inc_usage(uid)

    # Uzun javobni bo'laklarga bo'lish
    if len(resp) <= 4096:
        await answer_msg(msg, 
            f"✅ <b>Javob:</b>\n\n{resp}"
        )
    else:
        parts = [resp[i:i+4000] for i in range(0, len(resp), 4000)]
        for i, part in enumerate(parts):
            prefix = f"<i>({i+1}/{len(parts)})</i>\n\n" if len(parts) > 1 else ""
            await answer_msg(msg, prefix + part)
            if i < len(parts) - 1:
                await asyncio.sleep(0.3)

    mname = GROQ_MODELS.get(mkey, {}).get("name", mkey)
    log.info(f"User {uid} | {plan} | {mname} | {len(text)}→{len(resp)}")


@dp.message(F.photo)
async def handle_photo(msg: Message, state: FSMContext):
    """Rasm + matn."""
    cur = await state.get_state()
    if cur:
        return

    user = await ensure_user(msg)
    lang = get_lang(user)
    plan = get_plan(user)

    used  = await db_get_usage(msg.from_user.id)
    limit = get_limit(plan)
    if used >= limit:
        await answer_msg(msg, 
            f"⚠️ <b>{t('limit_reached', lang, limit=limit)}</b>"
        )
        return

    caption = msg.caption or {
        "uz":"Bu rasmda nima bor? Batafsil ayt.",
        "ru":"Что на этом фото? Опиши подробно.",
        "en":"What's in this image? Describe in detail.",
    }.get(lang,"")

    await bot.send_chat_action(msg.chat.id, "typing")

    # Rasmni URL orqali Groq ga yuborib bo'lmaydi (vision qo'llab-quvvatlanmaydi)
    # Shuning uchun matn so'rov sifatida yuboramiz
    history  = await db_get_history(msg.from_user.id)
    sys_p    = SYSTEM_PROMPT.get(lang, SYSTEM_PROMPT["uz"])
    messages = [{"role": "system", "content": sys_p}]
    messages.extend(history[-10:])
    messages.append({
        "role":    "user",
        "content": f"Foydalanuvchi rasm yubordi va shunday dedi: \"{caption}\". "
                   f"Rasmni ko'rolmasang ham, savolga javob ber yoki yordam ber."
    })

    mkey = user["model_key"] or DEFAULT_MODEL
    resp = await groq_chat(messages, mkey)

    if resp and resp != "__LIMIT__":
        history.append({"role": "user",      "content": f"[Rasm] {caption}"})
        history.append({"role": "assistant", "content": resp})
        await db_save_history(msg.from_user.id, history)
        await db_inc_usage(msg.from_user.id)
        await answer_msg(msg, resp[:4096])
    else:
        await answer_msg(msg, t("server_error", lang))


@dp.message(ServerFlow.wait_zip, F.document)
async def handle_server_zip(msg: Message, state: FSMContext):
    user = await ensure_user(msg)
    lang = get_lang(user)
    plan = get_plan(user)

    doc = msg.document
    if not doc or not doc.file_name or not doc.file_name.lower().endswith(".zip"):
        txt = {
            "uz": "❌ Iltimos, loyihangizni .zip formatida yuboring.",
            "ru": "❌ Пожалуйста, отправьте проект в формате .zip.",
            "en": "❌ Please send your project as a .zip file.",
        }.get(lang, "❌ Please send your project as a .zip file.")
        await answer_msg(msg, txt)
        return

    if doc.file_size > 20_000_000:
        sz_err = {
            "uz": "❌ Zip fayl 20MB dan kichik bo'lishi kerak.",
            "ru": "❌ Zip-файл должен быть меньше 20 МБ.",
            "en": "❌ Zip file must be smaller than 20MB.",
        }.get(lang, "❌ Zip file must be smaller than 20MB.")
        await answer_msg(msg, sz_err)
        return

    await bot.send_chat_action(msg.chat.id, "upload_document")
    try:
        file = await bot.get_file(doc.file_id)
        data = await bot.download_file(file.file_path)
        raw = data.read()
        uploads = Path("server_uploads")
        uploads.mkdir(exist_ok=True)
        save_name = f"{msg.from_user.id}_{int(time.time())}_{doc.file_name}"
        with open(uploads / save_name, "wb") as f:
            f.write(raw)

        target = "Vercel"
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                names = [n.lower() for n in zf.namelist() if not n.endswith("/")]
                if any(n.endswith("bot.py") or n.endswith("main.py") for n in names):
                    target = "AlwaysData"
                if any(n.endswith("requirements.txt") for n in names):
                    req = zf.read(next(n for n in names if n.endswith("requirements.txt"))).decode("utf-8", errors="replace").lower()
                    if "aiogram" in req or "python-telegram-bot" in req:
                        target = "AlwaysData"
        except Exception:
            pass

        msg_text = {
            "uz": (
                "✅ <b>Loyihangiz qabul qilindi.</b>\n\n"
                "Men uni tekshirdim va hozirda <b>{target}</b> uchun deploy qadamlarini tayyorlayman.\n"
                "Agar kerak bo'lsa, sizga .zip, token yoki fayl sozlamalari bo'yicha yordam beraman."
            ),
            "ru": (
                "✅ <b>Проект принят.</b>\n\n"
                "Я подготовлю шаги для деплоя на <b>{target}</b>.\n"
                "Если понадобится, помогу с .zip, токенами и настройками."
            ),
            "en": (
                "✅ <b>Your project is received.</b>\n\n"
                "I will prepare deployment steps for <b>{target}</b>.\n"
                "If needed, I can help you with .zip details, tokens, and settings."
            ),
        }.get(lang, "✅ Your project is received.")
        await answer_msg(msg, msg_text.format(target=target), reply_markup=kb_back(lang))
    except Exception:
        await answer_msg(msg, t("server_error", lang))
    finally:
        await state.clear()


@dp.message(F.document)
async def handle_document(msg: Message, state: FSMContext):
    """Matn fayllarini tahlil qilish."""
    cur = await state.get_state()
    if cur and cur != ServerFlow.wait_zip.state:
        return

    user = await ensure_user(msg)
    lang = get_lang(user)
    plan = get_plan(user)

    used  = await db_get_usage(msg.from_user.id)
    limit = get_limit(plan)
    if used >= limit:
        await answer_msg(msg, t("limit_reached", lang, limit=limit))
        return

    doc = msg.document
    if not doc:
        return

    if doc.file_size > 100_000:
        sz_err = {
            "uz":"❌ Fayl 100KB dan kichik bo'lishi kerak.",
            "ru":"❌ Файл должен быть меньше 100 КБ.",
            "en":"❌ File must be less than 100KB.",
        }.get(lang,"")
        await answer_msg(msg, sz_err)
        return

    allowed = {
        ".txt",".py",".js",".ts",".json",".md",".html",".css",
        ".xml",".yaml",".yml",".csv",".java",".cpp",".c",".go",
        ".rs",".php",".swift",".kt",".dart",".sql",".sh",".bat",
        ".docx",".pdf",".ogg",
    }
    fname = doc.file_name or "file"
    ext   = ("." + fname.rsplit(".",1)[-1].lower()) if "." in fname else ""
    if ext not in allowed:
        await answer_msg(msg, f"❌ <code>{ext}</code> qo'llab-quvvatlanmaydi.")
        return

    await bot.send_chat_action(msg.chat.id, "typing")

    try:
        file = await bot.get_file(doc.file_id)
        data = await bot.download_file(file.file_path)
        raw = data.read()
        if ext == ".docx":
            content = extract_docx_text(raw)
            if not content:
                await answer_msg(msg, {
                    "uz": "❌ .docx fayldan matn olinmadi. Iltimos, matnni nusxa ko'chirib yuboring.",
                    "ru": "❌ Не удалось извлечь текст из .docx. Пожалуйста, отправьте текст напрямую.",
                    "en": "❌ Could not extract text from .docx. Please send the text directly.",
                }.get(lang, "❌ Could not extract text from .docx. Please send the text directly."))
                return
        elif ext == ".pdf":
            await answer_msg(msg, {
                "uz": "❌ .pdf fayllar hozircha qo'llab-quvvatlanmaydi. Iltimos, matnni nusxa ko'chirib yuboring.",
                "ru": "❌ PDF файлы пока не поддерживаются. Пожалуйста, отправьте текст напрямую.",
                "en": "❌ PDF files are not supported yet. Please send the text directly.",
            }.get(lang, "❌ PDF files are not supported yet. Please send the text directly."))
            return
        else:
            content = raw.decode("utf-8", errors="replace")
    except Exception:
        await answer_msg(msg, t("server_error", lang))
        return

    caption = msg.caption or {
        "uz":"Bu faylni tahlil qil va tushuntir.",
        "ru":"Проанализируй этот файл и объясни.",
        "en":"Analyze this file and explain it.",
    }.get(lang,"")

    user_prompt = f"{caption}\n\n```{ext[1:] if ext else ''}\n{content[:8000]}\n```"

    history  = await db_get_history(msg.from_user.id)
    sys_p    = SYSTEM_PROMPT.get(lang, SYSTEM_PROMPT["uz"])
    messages = [{"role": "system", "content": sys_p}]
    messages.extend(history[-10:])
    messages.append({"role": "user", "content": user_prompt})

    mkey = user["model_key"] or DEFAULT_MODEL
    resp = await groq_chat(messages, mkey, )

    if resp and resp != "__LIMIT__":
        history.append({"role": "user",      "content": f"[Fayl: {fname}] {caption}"})
        history.append({"role": "assistant", "content": resp})
        await db_save_history(msg.from_user.id, history)
        await db_inc_usage(msg.from_user.id)
        await answer_msg(msg, f"📄 <b>{fname}</b>\n\n<i>Fayl tahlili natijasi:</i>\n{resp[:4000]}")
    else:
        await answer_msg(msg, t("server_error", lang))


@dp.message(Command("translate"))
async def cmd_translate(msg: Message, state: FSMContext):
    await state.clear()
    user = await ensure_user(msg)
    lang = get_lang(user)
    text = (msg.text or "").strip()
    parts = text.split(maxsplit=2)
    if len(parts) < 3:
        usage = {
            "uz": "🔤 /translate uz|ru|en matn — matnni tarjima qiladi.",
            "ru": "🔤 /translate uz|ru|en текст — переводит текст.",
            "en": "🔤 /translate uz|ru|en text — translates text.",
        }.get(lang, "🔤 /translate uz|ru|en text — translates text.")
        await answer_msg(msg, usage, reply_markup=kb_back(lang))
        return

    target = parts[1].lower()
    body = parts[2].strip()
    languages = {"uz": "Uzbek", "ru": "Russian", "en": "English"}
    if target not in languages:
        msg_text = {
            "uz": "❌ Iltimos, til kodini uz, ru yoki en sifatida yozing.",
            "ru": "❌ Пожалуйста, используйте код языка uz, ru или en.",
            "en": "❌ Please use language code uz, ru or en.",
        }.get(lang, "❌ Please use language code uz, ru or en.")
        await answer_msg(msg, msg_text, reply_markup=kb_back(lang))
        return

    used = await db_get_usage(msg.from_user.id)
    limit = get_limit(get_plan(user))
    if used >= limit:
        await answer_msg(msg, t("limit_reached", lang, limit=limit), reply_markup=kb_plans(lang))
        return

    await bot.send_chat_action(msg.chat.id, "typing")
    messages = [
        {"role": "system", "content": (
            "You are a professional translator. Translate the user text into the requested language, "
            "preserve meaning and tone, and return only the translated text."
        )},
        {"role": "user", "content": f"Translate to {languages[target]}:\n{body}"},
    ]
    resp = await groq_chat(messages, "llama3_8b")
    if resp is None or resp == "__LIMIT__":
        await answer_msg(msg, t("server_error", lang))
        return

    history = await db_get_history(msg.from_user.id)
    history.append({"role": "user", "content": f"[Translate to {target}] {body}"})
    history.append({"role": "assistant", "content": resp})
    await db_save_history(msg.from_user.id, history)
    await db_inc_usage(msg.from_user.id)
    await answer_msg(msg, resp)


# ================================================================
#                    COMMANDS
# ================================================================

# ── /code  — Kod yozuvchi AI (Groq) ──────────────────────────────

# Har bir foydalanuvchi uchun kod suhbat tarixi (xotirada)
_code_histories: Dict[int, List[dict]] = {}
MAX_CODE_HISTORY = 20

CODE_SYSTEM = {
    "uz": (
        "Sen CODE AI — professional dasturchi yordamchisan. "
        "Foydalanuvchi bilan O'zbek, Rus yoki Ingliz tilida gaplash. "
        "Qaysi tilda yozsalar, o'sha tilda javob ber. "
        "Faqat sifatli, ishlaydigan kod yoz. "
        "Kodni doim <pre><code>...\n</code></pre> blokida formatlaysan. "
        "Kodga foydali izohlar qo'shasan. "
        "Xatoni tushuntirib, to'g'ri yechim berasan. "
        "Zamonaviy yechimlar va best practices tavsiya qilasan."
    ),
    "ru": (
        "Ты CODE AI — профессиональный помощник по программированию. "
        "Общайся на языке пользователя (узбекский/русский/английский). "
        "Пиши только рабочий, качественный код. "
        "Всегда форматируй код в блоках <pre><code>...\n</code></pre>. "
        "Добавляй полезные комментарии. "
        "Объясняй ошибки и предлагай правильное решение. "
        "Рекомендуй современные решения и best practices."
    ),
    "en": (
        "You are CODE AI — a professional coding assistant. "
        "Respond in the user's language (Uzbek/Russian/English). "
        "Write only clean, working code. "
        "Always format code inside <pre><code>...\n</code></pre> blocks. "
        "Add helpful comments to the code. "
        "Explain bugs and provide correct solutions. "
        "Recommend modern solutions and best practices."
    ),
}


@dp.message(Command("code"))
async def cmd_code(msg: Message, state: FSMContext):
    """Code AI sessiyasini boshlash."""
    await state.clear()
    user = await ensure_user(msg)
    await db_set(msg.from_user.id, "model_key", "llama3_8b")
    lang = get_lang(user)
    plan = get_plan(user)

    used  = await db_get_usage(msg.from_user.id)
    limit = get_limit(plan)
    if used >= limit:
        await answer_msg(msg, t("limit_reached", lang, limit=limit), reply_markup=kb_plans(lang))
        return

    # Sessiya tarixini tozalash
    _code_histories[msg.from_user.id] = []
    await state.set_state(CodeFlow.chatting)

    inline_prompt = (msg.text or "").replace("/code", "", 1).strip()

    greet = {
        "uz": (
            "💻 <b>CODE AI — Kod yozuvchi AI</b>\n\n"
            "<blockquote>"
            "✅ Python, JS, Go, Rust, C++, Java va boshqalar\n"
            "✅ Kod yozish, debug, refaktorlash\n"
            "✅ Arxitektura va algoritmlar\n"
            "✅ Suhbat tarixi eslab qoladi\n"
            "</blockquote>\n\n"
            "💬 <b>Savolingizni yozing yoki kod yuboring!</b>\n"
            "<i>Chiqish: /exit yoki /start</i>"
        ),
        "ru": (
            "💻 <b>CODE AI — ИИ для программирования</b>\n\n"
            "<blockquote>"
            "✅ Python, JS, Go, Rust, C++, Java и другие\n"
            "✅ Написание, отладка, рефакторинг кода\n"
            "✅ Архитектура и алгоритмы\n"
            "✅ Запоминает историю чата\n"
            "</blockquote>\n\n"
            "💬 <b>Напишите вопрос или отправьте код!</b>\n"
            "<i>Выход: /exit или /start</i>"
        ),
        "en": (
            "💻 <b>CODE AI — AI Coding Assistant</b>\n\n"
            "<blockquote>"
            "✅ Python, JS, Go, Rust, C++, Java and more\n"
            "✅ Write, debug, refactor code\n"
            "✅ Architecture & algorithms\n"
            "✅ Remembers conversation history\n"
            "</blockquote>\n\n"
            "💬 <b>Write your question or send code!</b>\n"
            "<i>Exit: /exit or /start</i>"
        ),
    }.get(lang, "")

    if inline_prompt:
        await answer_msg(msg, greet, reply_markup=kb_code_exit(lang))
        await _handle_code_message(msg, inline_prompt, lang)
    else:
        await answer_msg(msg, greet, reply_markup=kb_code_exit(lang))


@dp.message(Command("exit"))
async def cmd_exit(msg: Message, state: FSMContext):
    """Code AI dan chiqish."""
    cur = await state.get_state()
    if cur == CodeFlow.chatting.state:
        user = await ensure_user(msg)
        lang = get_lang(user)
        plan = get_plan(user)
        _code_histories.pop(msg.from_user.id, None)
        await state.clear()
        bye = {
            "uz": "✅ <b>Code AI sessiyasi yakunlandi.</b>\n\nAsosiy menyuga qaytdingiz.",
            "ru": "✅ <b>Сессия Code AI завершена.</b>\n\nВы вернулись в главное меню.",
            "en": "✅ <b>Code AI session ended.</b>\n\nReturned to main menu.",
        }.get(lang, "")
        await answer_msg(msg, bye, reply_markup=kb_main(lang, plan, is_admin(msg.from_user.id)))
    else:
        await cmd_start(msg, state)


@dp.callback_query(F.data == "code:exit")
async def cb_code_exit(call: CallbackQuery, state: FSMContext):
    """Tugma orqali Code AI dan chiqish."""
    await call.answer()
    user = await db_get_user(call.from_user.id)
    lang = get_lang(user)
    plan = get_plan(user)
    _code_histories.pop(call.from_user.id, None)
    await state.clear()
    bye = {
        "uz": "✅ <b>Code AI sessiyasi yakunlandi.</b>",
        "ru": "✅ <b>Сессия Code AI завершена.</b>",
        "en": "✅ <b>Code AI session ended.</b>",
    }.get(lang, "")
    await safe_edit(call.message, bye, kb_main(lang, plan, is_admin(call.from_user.id)))


@dp.callback_query(F.data == "code:clear")
async def cb_code_clear(call: CallbackQuery):
    """Kod suhbat tarixini tozalash."""
    await call.answer()
    user = await db_get_user(call.from_user.id)
    lang = get_lang(user)
    _code_histories[call.from_user.id] = []
    msg_text = {
        "uz": "🗑 <b>Code AI tarixi tozalandi.</b> Davom eting!",
        "ru": "🗑 <b>История Code AI очищена.</b> Продолжайте!",
        "en": "🗑 <b>Code AI history cleared.</b> Continue!",
    }.get(lang, "")
    await answer_msg(call.message, msg_text, reply_markup=kb_code_exit(lang))


@dp.message(CodeFlow.chatting)
async def handle_code_chat(msg: Message, state: FSMContext):
    """Code AI sessiyasidagi barcha xabarlar."""
    user = await ensure_user(msg)
    lang = get_lang(user)
    plan = get_plan(user)
    text = (msg.text or "").strip()

    if not text:
        return

    # /exit yoki /start yozilsa
    if text.lower() in ("/exit", "/start"):
        await cmd_exit(msg, state)
        return

    # Limit tekshirish
    used  = await db_get_usage(msg.from_user.id)
    limit = get_limit(plan)
    if used >= limit:
        await state.clear()
        _code_histories.pop(msg.from_user.id, None)
        await answer_msg(msg, t("limit_reached", lang, limit=limit), reply_markup=kb_plans(lang))
        return

    await _handle_code_message(msg, text, lang)


async def _handle_code_message(msg: Message, text: str, lang: str):
    """Kod xabarini Groq API ga yuborib javob olish."""
    uid     = msg.from_user.id
    history = _code_histories.get(uid, [])
    sys_p   = CODE_SYSTEM.get(lang, CODE_SYSTEM["uz"])

    messages = [{"role": "system", "content": sys_p}]
    messages.extend(history[-MAX_CODE_HISTORY * 2:])
    messages.append({"role": "user", "content": text})

    await bot.send_chat_action(msg.chat.id, "typing")

    # Kuchli model ishlatish (llama3_70b yoki qwen3_32b)
    resp = await groq_chat(messages, "llama3_70b")

    if resp == "__LIMIT__" or resp is None:
        await answer_msg(msg, t("server_error", lang))
        return

    # Tarixni yangilash
    history.append({"role": "user",      "content": text})
    history.append({"role": "assistant", "content": resp})
    if len(history) > MAX_CODE_HISTORY * 2:
        history = history[-MAX_CODE_HISTORY * 2:]
    _code_histories[uid] = history

    await db_inc_usage(uid)

    # Javobni yuborish
    if len(resp) <= 4096:
        await answer_msg(msg, resp, reply_markup=kb_code_exit(lang))
    else:
        parts = [resp[i:i+4000] for i in range(0, len(resp), 4000)]
        for i, part in enumerate(parts):
            prefix = f"<i>({i+1}/{len(parts)})</i>\n\n" if len(parts) > 1 else ""
            kb = kb_code_exit(lang) if i == len(parts) - 1 else None
            await answer_msg(msg, prefix + part, reply_markup=kb)
            if i < len(parts) - 1:
                await asyncio.sleep(0.3)

    log.info(f"CodeAI | User {uid} | {len(text)}→{len(resp)}")



@dp.message(Command("clear"))
async def cmd_clear(msg: Message):
    user = await ensure_user(msg)
    lang = get_lang(user)
    await db_clear_history(msg.from_user.id)
    await answer_msg(msg, 
        t("clear_done", lang),
        reply_markup=kb_main(lang, get_plan(user), is_admin(msg.from_user.id))
    )


@dp.message(Command("model"))
async def cmd_model(msg: Message):
    user = await ensure_user(msg)
    lang = get_lang(user)
    plan = get_plan(user)
    hdr = {
        "uz": "🤖 <b>Model tanlang:</b>",
        "ru": "🤖 <b>Выберите модель:</b>",
        "en": "🤖 <b>Select model:</b>",
    }.get(lang,"")
    await answer_msg(msg, hdr, reply_markup=kb_models(lang, plan))


@dp.message(Command("plans"))
async def cmd_plans_cmd(msg: Message):
    user = await ensure_user(msg)
    lang = get_lang(user)
    await answer_msg(msg, 
        {"uz":"📋 Tariflar:","ru":"📋 Тарифы:","en":"📋 Plans:"}.get(lang,""),
        reply_markup=kb_plans(lang)
    )

# ================================================================
#                    ADMIN
# ================================================================

@dp.message(Command("admin"))
async def cmd_admin(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    await send_admin_panel(msg, state)


@dp.message(AdminFlow.broadcast)
async def msg_broadcast(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    await state.clear()
    text = msg.text or ""
    uids = await db_all_ids()
    sent = failed = 0
    sm   = await answer_msg(msg, f"📣 {len(uids)} ta foydalanuvchiga yuborilmoqda...")
    for uid in uids:
        try:
            await bot.send_message(uid, text)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.04)
    try:
        await sm.edit_text(f"✅ Yuborildi: {sent} | ❌ Xato: {failed}")
    except Exception:
        pass


@dp.message(Command("broadcast"))
async def cmd_broadcast(msg: Message):
    if not is_admin(msg.from_user.id): return
    text = (msg.text or "").replace("/broadcast","").strip()
    if not text:
        await answer_msg(msg, "❌ /broadcast [matn]"); return
    uids = await db_all_ids()
    sent = failed = 0
    for uid in uids:
        try:
            await bot.send_message(uid, f"📣 <b>Xabar:</b>\n\n{text}")
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await answer_msg(msg, f"✅ {sent} | ❌ {failed}")

# ================================================================
#                    WEB BROWSER SERVER
# ================================================================

WEB_PORT = 8080
WEB_HOST = "127.0.0.1"

async def handle_browser(request):
    """Serve the web_computer.html browser page."""
    try:
        html_path = Path(__file__).parent / "web_computer.html"
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        return aiohttp.web.Response(text=html_content, content_type='text/html')
    except Exception as e:
        log.error(f"Web server error: {e}")
        return aiohttp.web.Response(text="Error loading browser", status=500)

async def start_web_server():
    """Start aiohttp web server for the browser."""
    app = aiohttp.web.Application()
    app.router.add_get('/', handle_browser)
    app.router.add_get('/browser', handle_browser)
    
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, WEB_HOST, WEB_PORT)
    await site.start()
    log.info(f"Web Browser Server: http://{WEB_HOST}:{WEB_PORT} ✓")

# ================================================================
#                         MAIN
# ================================================================

async def main():
    await init_db()
    
    # Start web browser server
    try:
        await start_web_server()
    except Exception as e:
        log.error(f"Failed to start web server: {e}")
    
    log.info("DEVELOPER AI Bot ishga tushdi ✓")
    me = await bot.get_me()
    log.info(f"Bot: @{me.username}")

    # Modellar listini olish va logga yozish
    models = await groq_list_models()
    log.info(f"Groq models available: {len(models)} ta")

    for aid in ADMIN_IDS:
        try:
            await bot.send_message(
                aid,
                f"✅ <b>DEVELOPER AI ishga tushdi!</b>\n"
                f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                f"🤖 {len(GROQ_MODELS)} ta model | 3 tarif\n"
                f"🌐 Groq modellari: {len(models)} ta\n"
                f"🌐 Browser: http://127.0.0.1:8080"
            )
        except Exception:
            pass

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())