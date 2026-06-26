#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
БОТ ДЛЯ ПЛАНЕТЫ ZOV 🇷🇺 (версия для python-telegram-bot)
Реферальная система с анимацией сердечек.
"""

import asyncio
import logging
import sqlite3
import random
import string
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = "8439349587:AAFTbZSNSnbUvW5U-z_FcwYOEcHY8URPBGI"
ADMIN_ID = 1995696389  # ЗАМЕНИТЕ НА СВОЙ ID

APOLOGY_TEXT = (
    "Дорогая Катя! 🙏\n\n"
    "Я приношу тебе свои глубочайшие извинения за всё, что произошло.\n"
    "Ты — важный человек в моей жизни и я очень люблю тебя .\n"
    "Прости меня, пожалуйста. ❤️\n\n"
    "➡️ Смотри, что я для тебя приготовил..."
)

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

# ==================== АНИМАЦИЯ СЕРДЕЧЕК ====================

async def animate_hearts(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id: int):
    """
    Анимирует сообщение с сердечками через редактирование.
    """
    chat_id = update.effective_chat.id
    delay = 0.3
    
    try:
        # Этап 1: Одно сердечко
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="❤️")
        await asyncio.sleep(delay)
        
        # Этап 2: Маленькое сердце
        small_heart = ["  ❤️  ", "❤️❤️❤️", "  ❤️  "]
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="\n".join(small_heart))
        await asyncio.sleep(delay)
        
        # Этап 3: Среднее сердце
        medium_heart = ["  ❤️❤️  ", "❤️❤️❤️❤️", "❤️❤️❤️❤️", "  ❤️❤️  "]
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="\n".join(medium_heart))
        await asyncio.sleep(delay)
        
        # Этап 4: Большое сердце
        big_heart = ["  ❤️❤️❤️  ", "❤️❤️❤️❤️❤️", "❤️❤️❤️❤️❤️", "❤️❤️❤️❤️❤️", "  ❤️❤️❤️  "]
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="\n".join(big_heart))
        await asyncio.sleep(delay)
        
        # Этап 5: Огромное сердце
        huge_heart = [
            "    ❤️❤️❤️    ",
            "  ❤️❤️❤️❤️❤️  ",
            "❤️❤️❤️❤️❤️❤️❤️",
            "❤️❤️❤️❤️❤️❤️❤️",
            "❤️❤️❤️❤️❤️❤️❤️",
            "  ❤️❤️❤️❤️❤️  ",
            "    ❤️❤️❤️    "
        ]
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="\n".join(huge_heart))
        await asyncio.sleep(delay * 1.5)
        
        # Этап 6: Слово "I"
        i_pattern = ["❤️❤️❤️", "  ❤️  ", "  ❤️  ", "  ❤️  ", "❤️❤️❤️"]
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="\n".join(i_pattern))
        await asyncio.sleep(delay)
        
        # Мерцание для "I"
        for _ in range(2):
            await asyncio.sleep(0.15)
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="✨\n" + "\n".join(i_pattern) + "\n✨")
            await asyncio.sleep(0.15)
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="\n".join(i_pattern))
        
        await asyncio.sleep(delay)
        
        # Этап 7: Слово "LOVE"
        love_pattern = [
            "❤️     ❤️❤️❤️   ❤️❤️❤️   ❤️❤️❤️",
            "❤️     ❤️   ❤️  ❤️   ❤️  ❤️   ❤️",
            "❤️     ❤️   ❤️  ❤️   ❤️  ❤️   ❤️",
            " ❤️❤️   ❤️❤️❤️   ❤️❤️❤️   ❤️❤️❤️",
            "   ❤️   ❤️      ❤️   ❤️  ❤️   ❤️",
            "   ❤️   ❤️      ❤️   ❤️  ❤️   ❤️",
            "❤️❤️     ❤️      ❤️❤️❤️   ❤️❤️❤️"
        ]
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="\n".join(love_pattern))
        await asyncio.sleep(delay)
        
        for _ in range(2):
            await asyncio.sleep(0.15)
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="✨✨\n" + "\n".join(love_pattern) + "\n✨✨")
            await asyncio.sleep(0.15)
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="\n".join(love_pattern))
        
        await asyncio.sleep(delay)
        
        # Этап 8: Слово "YOU"
        you_pattern = [
            "❤️❤️❤️   ❤️❤️❤️   ❤️❤️❤️❤️❤️",
            "❤️   ❤️  ❤️   ❤️  ❤️     ❤️",
            "❤️   ❤️  ❤️   ❤️  ❤️     ❤️",
            "❤️❤️❤️   ❤️❤️❤️   ❤️     ❤️",
            "❤️   ❤️  ❤️   ❤️  ❤️     ❤️",
            "❤️   ❤️  ❤️   ❤️  ❤️     ❤️",
            "❤️   ❤️  ❤️❤️❤️   ❤️❤️❤️❤️❤️"
        ]
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="\n".join(you_pattern))
        await asyncio.sleep(delay)
        
        for _ in range(2):
            await asyncio.sleep(0.15)
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="✨✨✨\n" + "\n".join(you_pattern) + "\n✨✨✨")
            await asyncio.sleep(0.15)
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="\n".join(you_pattern))
        
        await asyncio.sleep(delay)
        
        # Этап 9: Финальная фраза
        final_text = "❤️❤️❤️ I LOVE YOU ❤️❤️❤️"
        for i in range(5):
            if i % 2 == 0:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=f"💖 {final_text} 💖")
            else:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=f"❤️ {final_text} ❤️")
            await asyncio.sleep(0.3)
        
        # Финальный кадр
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="💖💖💖\n\n❤️ I LOVE YOU ❤️\n\n💖💖💖"
        )
        await asyncio.sleep(0.5)
        
        # Градиент сердец
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
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"{grad}\n\n❤️ I LOVE YOU ❤️\n\n{grad[::-1]}"
            )
            await asyncio.sleep(0.2)
        
        # Финальное сообщение
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="💖💖💖💖💖💖💖💖💖\n\n❤️  I LOVE YOU, KATYA!  ❤️\n\n💖💖💖💖💖💖💖💖💖\n\nТы прощена ❤️"
        )
    
    except Exception as e:
        logging.error(f"Ошибка анимации: {e}")

# ==================== ОБРАБОТЧИКИ КОМАНД ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        return
    
    code = args[0].strip()
    if not is_ref_code_valid(code):
        return
    
    admin_notified_before = was_admin_notified(user_id, code)
    
    # Отправляем текст извинений
    msg = await update.message.reply_text(APOLOGY_TEXT)
    
    # Запускаем анимацию
    await animate_hearts(update, context, msg.message_id)
    
    if not has_received_apology(user_id, code):
        mark_click(user_id, code)
        mark_apology_sent(user_id, code)
    
    # Уведомление админа
    if not admin_notified_before:
        user = update.effective_user
        notification_text = format_notification(
            user_id=user_id,
            code=code,
            user_first_name=user.first_name or "",
            user_last_name=user.last_name or "",
            username=user.username or ""
        )
        await context.bot.send_message(ADMIN_ID, notification_text, parse_mode=ParseMode.HTML)
        mark_admin_notified(user_id, code)

async def create_ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /createref — только для админа"""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    
    code = generate_ref_code()
    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={code}"
    create_ref_link(code, user_id)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(text="📋 Скопировать ссылку", url=ref_link)],
        [InlineKeyboardButton(text="🔁 Создать ещё", callback_data="create_ref_again")]
    ])
    
    await update.message.reply_text(
        f"✅ <b>Реферальная ссылка создана, мой господин!</b>\n\n"
        f"<code>{ref_link}</code>\n\n"
        f"Код: <b>{code}</b>\n"
        f"При переходе пользователь увидит анимацию с сердечками и извинения.",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )

async def create_ref_again(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопки 'Создать ещё'"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("Эта кнопка только для админа.", show_alert=False)
        return
    
    code = generate_ref_code()
    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={code}"
    create_ref_link(code, ADMIN_ID)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(text="📋 Скопировать ссылку", url=ref_link)],
        [InlineKeyboardButton(text="🔁 Создать ещё", callback_data="create_ref_again")]
    ])
    
    await query.edit_message_text(
        f"✅ <b>Новая реферальная ссылка создана, мой господин!</b>\n\n"
        f"<code>{ref_link}</code>\n\n"
        f"Код: <b>{code}</b>\n"
        f"При переходе пользователь увидит анимацию с сердечками и извинения.",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )

# ==================== ОБРАБОТКА ОШИБОК ====================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Логирование ошибок"""
    logging.error(f"Update {update} caused error {context.error}")

# ==================== ЗАПУСК ====================

def main():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    
    # Создаём приложение с увеличенным таймаутом (решение ошибки TimedOut)
    application = Application.builder().token(BOT_TOKEN).connect_timeout(30.0).read_timeout(30.0).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("createref", create_ref))
    application.add_handler(CallbackQueryHandler(create_ref_again, pattern="create_ref_again"))
    application.add_error_handler(error_handler)
    
    logging.info("🚀 Бот ZOV v3000 запущен. Админ ID: %s", ADMIN_ID)
    logging.info("✅ Анимация сердечек активирована")
    
    application.run_polling()

if __name__ == "__main__":
    main()
