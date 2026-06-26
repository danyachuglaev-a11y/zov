#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
БОТ ДЛЯ ПЛАНЕТЫ ZOV 🇷🇺
Реферальная система с анимацией сердечек.
- Только админ создаёт ссылки (/createref)
- При переходе по ссылке и отправке /start:
  1. Пользователь получает текст извинений перед Катей
  2. Запускается анимация: ❤️ → большое сердце → "I LOVE YOU" из сердечек
- Админу приходит уведомление о переходе
- Обычный /start без реф-метки — игнорируется
"""

import asyncio
import logging
import sqlite3
import random
import string
from datetime import datetime
from typing import Optional

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = "8439349587:AAFTbZSNSnbUvW5U-z_FcwYOEcHY8URPBGI"
ADMIN_ID = 1995696389  # ЗАМЕНИ НА СВОЙ ID

# Текст извинений перед Катей (отправляется перед анимацией)
APOLOGY_TEXT = (
    "Дорогая Катя! 🙏\n\n"
    "Я приношу тебе свои глубочайшие извинения за всё, что произошло.\n"
    "Ты — важный человек для меня за эти почти 9 месяцев я понял что я очень тебя люблю .\n"
    "Прости меня, пожалуйста. ❤️\n\n"
    "➡️ Смотри, что я для тебя приготовил..."
)

# Формат уведомления для админа
NOTIFICATION_TEMPLATE = (
    "🔔 <b>НОВЫЙ ПЕРЕХОД ПО РЕФЕРАЛЬНОЙ ССЫЛКЕ</b>\n\n"
    "👤 <b>Пользователь:</b> {user_info}\n"
    "🆔 <b>ID:</b> <code>{user_id}</code>\n"
    "🔗 <b>Код ссылки:</b> <code>{code}</code>\n"
    "🕐 <b>Время:</b> {time}\n"
    "📊 <b>Статус:</b> Извинения + анимация отправлены ✅"
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
    return f"https://t.me/ВАШ_ЮЗЕРНЕЙМ_БОТА?start={code}"

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

def format_notification(user_id: int, code: str, user_first_name: str, user_last_name: str = "", username: str = "") -> str:
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

# ==================== [NEW] ФУНКЦИИ АНИМАЦИИ СЕРДЕЧЕК ====================

async def animate_hearts(message: Message, delay: float = 0.3):
    """
    Запускает анимацию сердечек с редактированием одного сообщения.
    Этапы:
    1. Одно сердечко ❤️
    2. Маленькое сердце из 5 сердечек
    3. Среднее сердце из 13 сердечек
    4. Большое сердце из 25 сердечек
    5. Огромное сердце из 41 сердечка
    6. Слово "I" из сердечек
    7. Слово "LOVE" из сердечек
    8. Слово "YOU" из сердечек
    9. Финальная фраза "I LOVE YOU ❤️" с мерцанием
    """
    
    # Этап 1: Одно сердечко
    await message.edit_text("❤️")
    await asyncio.sleep(delay)
    
    # Этап 2: Маленькое сердце (5 сердец)
    small_heart = [
        "  ❤️  ",
        "❤️❤️❤️",
        "  ❤️  "
    ]
    await message.edit_text("\n".join(small_heart))
    await asyncio.sleep(delay)
    
    # Этап 3: Среднее сердце (13 сердец)
    medium_heart = [
        "  ❤️❤️  ",
        "❤️❤️❤️❤️",
        "❤️❤️❤️❤️",
        "  ❤️❤️  "
    ]
    await message.edit_text("\n".join(medium_heart))
    await asyncio.sleep(delay)
    
    # Этап 4: Большое сердце (25 сердец)
    big_heart = [
        "  ❤️❤️❤️  ",
        "❤️❤️❤️❤️❤️",
        "❤️❤️❤️❤️❤️",
        "❤️❤️❤️❤️❤️",
        "  ❤️❤️❤️  "
    ]
    await message.edit_text("\n".join(big_heart))
    await asyncio.sleep(delay)
    
    # Этап 5: Огромное сердце (41 сердце)
    huge_heart = [
        "    ❤️❤️❤️    ",
        "  ❤️❤️❤️❤️❤️  ",
        "❤️❤️❤️❤️❤️❤️❤️",
        "❤️❤️❤️❤️❤️❤️❤️",
        "❤️❤️❤️❤️❤️❤️❤️",
        "  ❤️❤️❤️❤️❤️  ",
        "    ❤️❤️❤️    "
    ]
    await message.edit_text("\n".join(huge_heart))
    await asyncio.sleep(delay * 1.5)
    
    # Этап 6: Слово "I" из сердечек (с анимацией появления)
    i_pattern = [
        "❤️❤️❤️",
        "  ❤️  ",
        "  ❤️  ",
        "  ❤️  ",
        "❤️❤️❤️"
    ]
    await message.edit_text("\n".join(i_pattern))
    await asyncio.sleep(delay)
    
    # Добавляем мерцание для "I"
    for _ in range(2):
        await asyncio.sleep(0.15)
        await message.edit_text("✨\n" + "\n".join(i_pattern) + "\n✨")
        await asyncio.sleep(0.15)
        await message.edit_text("\n".join(i_pattern))
    
    await asyncio.sleep(delay)
    
    # Этап 7: Слово "LOVE" из сердечек
    love_pattern = [
        "❤️     ❤️❤️❤️   ❤️❤️❤️   ❤️❤️❤️",
        "❤️     ❤️   ❤️  ❤️   ❤️  ❤️   ❤️",
        "❤️     ❤️   ❤️  ❤️   ❤️  ❤️   ❤️",
        " ❤️❤️   ❤️❤️❤️   ❤️❤️❤️   ❤️❤️❤️",
        "   ❤️   ❤️      ❤️   ❤️  ❤️   ❤️",
        "   ❤️   ❤️      ❤️   ❤️  ❤️   ❤️",
        "❤️❤️     ❤️      ❤️❤️❤️   ❤️❤️❤️"
    ]
    await message.edit_text("\n".join(love_pattern))
    await asyncio.sleep(delay)
    
    # Мерцание для "LOVE"
    for _ in range(2):
        await asyncio.sleep(0.15)
        await message.edit_text("✨✨\n" + "\n".join(love_pattern) + "\n✨✨")
        await asyncio.sleep(0.15)
        await message.edit_text("\n".join(love_pattern))
    
    await asyncio.sleep(delay)
    
    # Этап 8: Слово "YOU" из сердечек
    you_pattern = [
        "❤️❤️❤️   ❤️❤️❤️   ❤️❤️❤️❤️❤️",
        "❤️   ❤️  ❤️   ❤️  ❤️     ❤️",
        "❤️   ❤️  ❤️   ❤️  ❤️     ❤️",
        "❤️❤️❤️   ❤️❤️❤️   ❤️     ❤️",
        "❤️   ❤️  ❤️   ❤️  ❤️     ❤️",
        "❤️   ❤️  ❤️   ❤️  ❤️     ❤️",
        "❤️   ❤️  ❤️❤️❤️   ❤️❤️❤️❤️❤️"
    ]
    await message.edit_text("\n".join(you_pattern))
    await asyncio.sleep(delay)
    
    # Мерцание для "YOU"
    for _ in range(2):
        await asyncio.sleep(0.15)
        await message.edit_text("✨✨✨\n" + "\n".join(you_pattern) + "\n✨✨✨")
        await asyncio.sleep(0.15)
        await message.edit_text("\n".join(you_pattern))
    
    await asyncio.sleep(delay)
    
    # Этап 9: Финальная фраза "I LOVE YOU ❤️" с пульсацией
    final_text = "❤️❤️❤️ I LOVE YOU ❤️❤️❤️"
    for i in range(5):
        if i % 2 == 0:
            await message.edit_text(f"💖 {final_text} 💖")
        else:
            await message.edit_text(f"❤️ {final_text} ❤️")
        await asyncio.sleep(0.3)
    
    # Финальный кадр с увеличенным текстом
    await message.edit_text(
        "💖💖💖\n\n"
        "❤️ I LOVE YOU ❤️\n\n"
        "💖💖💖"
    )
    await asyncio.sleep(0.5)
    
    # Добавляем дополнительный эффект — градиент сердец (разные цвета)
    hearts_gradient = [
        "❤️🧡💛💚💙💜❤️",
        "🧡💛💚💙💜❤️🧡",
        "💛💚💙💜❤️🧡💛",
        "💚💙💜❤️🧡💛💚",
        "💙💜❤️🧡💛💚💙",
        "💜❤️🧡💛💚💙💜",
        "❤️🧡💛💚💙💜❤️"
    ]
    for grad in hearts_gradient:
        await message.edit_text(
            f"{grad}\n\n"
            "❤️ I LOVE YOU ❤️\n\n"
            f"{grad[::-1]}"
        )
        await asyncio.sleep(0.2)
    
    # Финальное сообщение с текстом извинений и анимацией
    await message.edit_text(
        "💖💖💖💖💖💖💖💖💖\n\n"
        "❤️  I LOVE YOU, KATYA!  ❤️\n\n"
        "💖💖💖💖💖💖💖💖💖\n\n"
        "Ты прощена ❤️"
    )

# ==================== ОБРАБОТЧИКИ КОМАНД ====================

@dp.message(Command("createref"))
async def cmd_create_ref(message: Message, command: CommandObject):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        return
    
    code = generate_ref_code()
    bot_username = (await bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={code}"
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
        f"Код: <b>{code}</b>\n"
        f"При переходе пользователь увидит анимацию с сердечками и извинения.",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )

@dp.callback_query(F.data == "create_ref_again")
async def callback_create_ref_again(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Эта кнопка только для админа.", show_alert=False)
        return
    
    code = generate_ref_code()
    bot_username = (await bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={code}"
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
        f"Код: <b>{code}</b>\n"
        f"При переходе пользователь увидит анимацию с сердечками и извинения.",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

@dp.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject):
    """
    Обработка /start с анимацией сердечек.
    """
    user_id = message.from_user.id
    args = command.args
    
    if not args:
        return
    
    code = args.strip()
    if not is_ref_code_valid(code):
        return
    
    admin_notified_before = was_admin_notified(user_id, code)
    
    # Если пользователь уже получал извинения — отправляем повторно (с анимацией)
    if has_received_apology(user_id, code):
        # Отправляем текст извинений
        apology_msg = await message.answer(APOLOGY_TEXT)
        # Запускаем анимацию (редактируем сообщение с текстом извинений)
        await animate_hearts(apology_msg)
        
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
        return
    
    # Первый переход
    mark_click(user_id, code)
    
    # Отправляем текст извинений
    apology_msg = await message.answer(APOLOGY_TEXT)
    
    # Запускаем анимацию (редактируем сообщение с текстом извинений)
    await animate_hearts(apology_msg)
    
    mark_apology_sent(user_id, code)
    
    # Уведомление админа
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
    logging.info("🚀 Бот ZOV v3000 запущен. Админ ID: %s", ADMIN_ID)
    logging.info("✅ Анимация сердечек активирована")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
