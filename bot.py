#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
БОТ ДЛЯ ПЛАНЕТЫ ZOV 🇷🇺
Реферальная система с анимацией сердечек.
ТЕКСТ ИЗВИНЕНИЙ НЕ ПРОПАДАЕТ!
"""

import asyncio
import logging
import sqlite3
import random
import string
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8439349587:AAFTbZSNSnbUvW5U-z_FcwYOEcHY8URPBGI")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1995696389"))

# ИМЯ БОТА (ВСТАВЬ СЮДА СВОЙ ЮЗЕРНЕЙМ БЕЗ @)
BOT_USERNAME = "gifpleasemebot"

APOLOGY_TEXT = (
    "Дорогая Катя! 🙏\n\n"
    "Я приношу тебе свои глубочайшие извинения за всё, что я тебе наговорил и как относился .\n"
    "Ты — важный человек, и я осознал это для себя и не хочу тебя терять .\n"
    "Прости меня, пожалуйста я очень сильно тебя люблю . ❤️"
)

NOTIFICATION_TEMPLATE = (
    "🔔 <b>НОВЫЙ ПЕРЕХОД ПО РЕФЕРАЛЬНОЙ ССЫЛКЕ</b>\n\n"
    "👤 <b>Пользователь:</b> {user_info}\n"
    "🆔 <b>ID:</b> <code>{user_id}</code>\n"
    "🔗 <b>Код ссылки:</b> <code>{code}</code>\n"
    "🕐 <b>Время:</b> {time}\n"
)

# ==================== БАЗА ДАННЫХ ====================
DB_PATH = "referrals.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ref_links (
            code TEXT PRIMARY KEY,
            created_by INTEGER,
            created_at TEXT,
            is_active INTEGER DEFAULT 1
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ref_clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            code TEXT,
            clicked_at TEXT,
            received_apology INTEGER DEFAULT 0,
            admin_notified INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


init_db()

# ==================== БОТ ====================
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def generate_ref_code() -> str:
    chars = string.ascii_letters + string.digits
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    while True:
        code = ''.join(random.choices(chars, k=8))
        cur.execute("SELECT code FROM ref_links WHERE code = ?", (code,))
        if not cur.fetchone():
            conn.close()
            return code
        conn.close()


def create_ref_link(code: str, admin_id: int) -> str:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ref_links (code, created_by, created_at) VALUES (?, ?, ?)",
        (code, admin_id, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return f"https://t.me/{BOT_USERNAME}?start={code}"


def is_ref_code_valid(code: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT is_active FROM ref_links WHERE code = ? AND is_active = 1", (code,))
    result = cur.fetchone()
    conn.close()
    return result is not None


def mark_click(user_id: int, code: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ref_clicks (user_id, code, clicked_at) VALUES (?, ?, ?)",
        (user_id, code, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def has_received_apology(user_id: int, code: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT received_apology FROM ref_clicks WHERE user_id = ? AND code = ? ORDER BY id DESC LIMIT 1",
        (user_id, code)
    )
    result = cur.fetchone()
    conn.close()
    return bool(result[0]) if result else False


def mark_apology_sent(user_id: int, code: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE ref_clicks SET received_apology = 1 WHERE user_id = ? AND code = ? AND received_apology = 0",
        (user_id, code)
    )
    conn.commit()
    conn.close()


def was_admin_notified(user_id: int, code: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT admin_notified FROM ref_clicks WHERE user_id = ? AND code = ? ORDER BY id DESC LIMIT 1",
        (user_id, code)
    )
    result = cur.fetchone()
    conn.close()
    return bool(result[0]) if result else False


def mark_admin_notified(user_id: int, code: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE ref_clicks SET admin_notified = 1 WHERE user_id = ? AND code = ? AND admin_notified = 0",
        (user_id, code)
    )
    conn.commit()
    conn.close()


def format_notification(user_id: int, code: str, user_first_name: str, user_last_name: str = "",
                        username: str = "") -> str:
    name_parts = []
    if user_first_name:
        name_parts.append(user_first_name)
    if user_last_name:
        name_parts.append(user_last_name)
    full_name = " ".join(name_parts) if name_parts else "Без имени"
    user_info = f"{full_name}"
    if username:
        user_info += f" (@{username})"
    current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    return NOTIFICATION_TEMPLATE.format(
        user_info=user_info,
        user_id=user_id,
        code=code,
        time=current_time
    )


# ==================== АНИМАЦИЯ СЕРДЦА ====================

async def animate_heart(message: Message):
    """Анимация сердца — ОТДЕЛЬНЫМ СООБЩЕНИЕМ, не редактирует текст извинений"""
    try:
        # Пауза перед анимацией
        await asyncio.sleep(0.5)

        # Отправляем первое сообщение с анимацией
        anim_msg = await message.answer("⏳ Сердце собирается...")

        heart_pattern = [
            "❤❤❤❤❤❤❤❤❤❤❤❤❤❤❤",
            "❤❤❤😘😘😘❤❤❤😘😘😘❤❤❤",
            "❤❤😘😘😘😘😘❤😘😘😘😘😘❤❤",
            "❤❤😘😘😘😘😘😘😘😘😘😘😘❤❤",
            "❤❤😘😘😘😘😘😘😘😘😘😘😘❤❤",
            "❤❤❤😘😘😘😘😘😘😘😘😘❤❤❤",
            "❤❤❤❤😘😘😘😘😘😘😘❤❤❤❤",
            "❤❤❤❤❤❤😘😘😘❤❤❤❤❤❤",
            "❤❤❤❤❤❤❤😘❤❤❤❤❤❤❤",
            "❤❤❤❤❤❤❤❤❤❤❤❤❤❤❤"
        ]

        # Строим строку за строкой
        current_build = []
        for i, line in enumerate(heart_pattern):
            current_build.append(line)
            progress = "▓" * (i + 1) + "░" * (len(heart_pattern) - i - 1)
            display_text = f"⏳ Строим сердечко... {progress}\n\n"
            display_text += "\n".join(current_build)
            await anim_msg.edit_text(display_text)
            await asyncio.sleep(0.4)

        await asyncio.sleep(0.5)

        # Показываем готовое сердце
        heart_display = "\n".join(heart_pattern)
        await anim_msg.edit_text(f"❤️ СЕРДЦЕ ГОТОВО! ❤️\n\n{heart_display}")
        await asyncio.sleep(0.8)

        # Пульсация
        for pulse in range(3):
            framed = []
            border = "❤" * 19
            framed.append(border)
            for line in heart_pattern:
                framed.append("❤" + line + "❤")
            framed.append(border)
            await anim_msg.edit_text("💓 ПУЛЬСАЦИЯ 💓\n\n" + "\n".join(framed))
            await asyncio.sleep(0.4)
            await anim_msg.edit_text("❤️ СЕРДЦЕ ❤️\n\n" + "\n".join(heart_pattern))
            await asyncio.sleep(0.4)

        await asyncio.sleep(0.5)

        # Появление надписи "Я ЛЮБЛЮ КАТЮ"
        text = "Я ЛЮБЛЮ ТЕБЯ!"
        for i in range(1, len(text) + 1):
            display_text = text[:i]
            await anim_msg.edit_text(f"❤️ {display_text} ❤️\n\n{heart_display}")
            await asyncio.sleep(0.25)

        await asyncio.sleep(0.5)

        # Финальная пульсация
        for pulse in range(3):
            framed_heart = []
            border = "❤" * 19
            framed_heart.append(border)
            for line in heart_pattern:
                framed_heart.append("❤" + line + "❤")
            framed_heart.append(border)
            await anim_msg.edit_text(
                f"💖💖💖 {text} 💖💖💖\n\n"
                + "\n".join(framed_heart)
            )
            await asyncio.sleep(0.4)
            await anim_msg.edit_text(
                f"❤️❤️❤️ {text} ❤️❤️❤️\n\n"
                + heart_display
            )
            await asyncio.sleep(0.4)

        await asyncio.sleep(0.5)

        # ФИНАЛ
        final_text = (
            "💖💖💖💖💖💖💖💖💖💖💖💖💖💖💖💖💖💖💖\n"
            "💖                                              💖\n"
            "💖     ❤️  Я ЛЮБЛЮ ТЕБЯ, КАТЯ!  ❤️     💖\n"
            "💖                                              💖\n"
            "💖💖💖💖💖💖💖💖💖💖💖💖💖💖💖💖💖💖💖\n\n"
            "✨ Надеюсь мы больше не будем друг друга оскарблять, а только любить ценить и доверять  ✨\n\n"
            "😘❤️😘❤️😘❤️😘❤️😘❤️😘❤️😘❤️😘❤️😘❤️"
        )
        await anim_msg.edit_text(final_text)

        # Мерцание финала
        for _ in range(2):
            await asyncio.sleep(0.4)
            await anim_msg.edit_text(final_text.replace("💖", "❤️"))
            await asyncio.sleep(0.4)
            await anim_msg.edit_text(final_text)

    except Exception as e:
        logging.error(f"Ошибка анимации: {e}")


# ==================== ОБРАБОТЧИКИ КОМАНД ====================

@dp.message(Command("createref"))
async def cmd_create_ref(message: Message, command: CommandObject):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        return

    code = generate_ref_code()
    ref_link = f"https://t.me/{BOT_USERNAME}?start={code}"
    create_ref_link(code, user_id)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Скопировать ссылку", url=ref_link)],
            [InlineKeyboardButton(text="🔁 Создать ещё", callback_data="create_ref_again")]
        ]
    )
    await message.answer(
        f"✅ <b>Реферальная ссылка создана, мой господин!</b>\n\n"
        f"<code>{ref_link}</code>\n\n"
        f"Код: <b>{code}</b>",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data == "create_ref_again")
async def callback_create_ref_again(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Эта кнопка только для админа.", show_alert=False)
        return

    code = generate_ref_code()
    ref_link = f"https://t.me/{BOT_USERNAME}?start={code}"
    create_ref_link(code, ADMIN_ID)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Скопировать ссылку", url=ref_link)],
            [InlineKeyboardButton(text="🔁 Создать ещё", callback_data="create_ref_again")]
        ]
    )
    await callback.message.edit_text(
        f"✅ <b>Новая реферальная ссылка создана, мой господин!</b>\n\n"
        f"<code>{ref_link}</code>\n\n"
        f"Код: <b>{code}</b>",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@dp.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject):
    user_id = message.from_user.id
    args = command.args

    if not args:
        return

    code = args.strip()
    if not is_ref_code_valid(code):
        return

    admin_notified_before = was_admin_notified(user_id, code)

    # ====== ОТПРАВЛЯЕМ ТЕКСТ ИЗВИНЕНИЙ (НЕ РЕДАКТИРУЕТСЯ) ======
    await message.answer(APOLOGY_TEXT)

    # ====== ЗАПУСКАЕМ АНИМАЦИЮ ОТДЕЛЬНЫМ СООБЩЕНИЕМ ======
    await animate_heart(message)

    if not has_received_apology(user_id, code):
        mark_click(user_id, code)
        mark_apology_sent(user_id, code)

    if not admin_notified_before:
        user = message.from_user
        notification_text = format_notification(
            user_id=user_id,
            code=code,
            user_first_name=user.first_name or "",
            user_last_name=user.last_name or "",
            username=user.username or ""
        )
        await bot.send_message(ADMIN_ID, notification_text)
        mark_admin_notified(user_id, code)


# ==================== ЗАПУСК ====================

async def main():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logging.info("🚀 Бот ZOV v3000 запущен. Админ ID: %s", ADMIN_ID)
    logging.info("✅ Анимация сердца активирована")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
