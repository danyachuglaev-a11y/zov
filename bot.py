import sqlite3
import os
import asyncio
import aiohttp
from datetime import datetime, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ========== КОНФИГУРАЦИЯ (ЗАПОЛНИ) ==========
BOT_TOKEN = "7983079912:AAHCefiaT0VKoxZWF_x-QyBSnR9foinaG1U"  # Например: "789123456:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"
TON_WALLET_ADDRESS = "UQDfFJfq4mdt51_MD7PZ7MXnnOfXdw3nh18l9x4u8cNCqIh9"  # Например: "EQAVKMzqtrvNB2SkcBONOijadqFZ1gMdjmzh1Y3HB1p_zai5"
TONAPI_KEY = "148e5d93fcc4001bdebbcd308221432d26e8a39719224a5d5769fd49274e14e3"


# =============================================

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect("zov_work.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            type TEXT NOT NULL,
            amount_ton REAL,
            comment TEXT,
            tx_hash TEXT UNIQUE
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS bot_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()

def clear_old_data():
    """Удаляет ВСЕ записи НЕ за сегодня"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect("zov_work.db")
    c = conn.cursor()
    c.execute("DELETE FROM operations WHERE date != ?", (today_str,))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted

def add_auto_transaction(date, tx_hash, amount_ton, op_type, comment=""):
    conn = sqlite3.connect("zov_work.db")
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO operations (date, type, amount_ton, comment, tx_hash)
            VALUES (?, ?, ?, ?, ?)
        """, (date, op_type, amount_ton, comment, tx_hash))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def get_daily_summary(date):
    conn = sqlite3.connect("zov_work.db")
    c = conn.cursor()
    c.execute("SELECT SUM(amount_ton) FROM operations WHERE date=? AND type='expense_ton'", (date,))
    expense_ton = c.fetchone()[0] or 0.0
    c.execute("SELECT SUM(amount_ton) FROM operations WHERE date=? AND type='income_ton'", (date,))
    income_ton = c.fetchone()[0] or 0.0
    conn.close()
    return expense_ton, income_ton

def get_all_operations(date):
    conn = sqlite3.connect("zov_work.db")
    c = conn.cursor()
    c.execute("SELECT type, amount_ton, comment, tx_hash FROM operations WHERE date=? ORDER BY id DESC", (date,))
    rows = c.fetchall()
    conn.close()
    return rows

def is_tx_already_recorded(tx_hash):
    conn = sqlite3.connect("zov_work.db")
    c = conn.cursor()
    c.execute("SELECT id FROM operations WHERE tx_hash = ?", (tx_hash,))
    row = c.fetchone()
    conn.close()
    return row is not None

def get_all_tx_hashes():
    """Возвращает множество всех хэшей в базе"""
    conn = sqlite3.connect("zov_work.db")
    c = conn.cursor()
    c.execute("SELECT tx_hash FROM operations WHERE tx_hash IS NOT NULL")
    rows = c.fetchall()
    conn.close()
    return {row[0] for row in rows}

# ========== КУРСЫ КРИПТЫ ==========
async def get_ton_price(vs_currency: str = "rub") -> float:
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies={vs_currency}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                return float(data["the-open-network"][vs_currency])
    except:
        return 85.0 if vs_currency == "rub" else 1.2

# ========== TON API (СБОР ВСЕХ ТРАНЗАКЦИЙ ЗА СЕГОДНЯ) ==========
async def fetch_and_update_today_transactions():
    """
    Загружает ВСЕ транзакции за сегодня и обновляет базу.
    НЕ отправляет никаких сообщений в чат.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    url = f"https://toncenter.com/api/v2/getTransactions?address={TON_WALLET_ADDRESS}&limit=100&archival=true&api_key={TONAPI_KEY}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    return 0
                
                existing_hashes = get_all_tx_hashes()
                new_count = 0
                
                for tx in data.get("result", []):
                    tx_unixtime = tx.get("utime", 0)
                    tx_date = datetime.fromtimestamp(tx_unixtime).strftime("%Y-%m-%d")
                    
                    # Только сегодняшние
                    if tx_date != today_str:
                        continue
                    
                    tx_hash = tx["transaction_id"]["hash"]
                    
                    # Пропускаем уже записанные
                    if tx_hash in existing_hashes:
                        continue
                    
                    comment = tx.get("in_msg", {}).get("message", "")
                    
                    # Входящая транзакция
                    in_msg = tx.get("in_msg", {})
                    if in_msg.get("source") and in_msg.get("source") != TON_WALLET_ADDRESS:
                        value_nano = int(in_msg.get("value", 0))
                        if value_nano > 0:
                            value_ton = value_nano / 1e9
                            add_auto_transaction(today_str, tx_hash, value_ton, "income_ton", comment or "входящий перевод")
                            new_count += 1
                            existing_hashes.add(tx_hash)
                    
                    # Исходящие транзакции
                    out_msgs = tx.get("out_msgs", [])
                    for out_msg in out_msgs:
                        if out_msg.get("destination") and out_msg.get("destination") != TON_WALLET_ADDRESS:
                            value_nano = int(out_msg.get("value", 0))
                            if value_nano > 0:
                                value_ton = value_nano / 1e9
                                add_auto_transaction(today_str, tx_hash, value_ton, "expense_ton", comment or "исходящий перевод")
                                new_count += 1
                                existing_hashes.add(tx_hash)
                
                return new_count
    except Exception as e:
        print(f"Ошибка TON API: {e}")
        return 0

# ========== АВТО-СБРОС В НОЧЬ (удаляем всё, кроме сегодня) ==========
async def auto_reset_midnight(context: ContextTypes.DEFAULT_TYPE):
    """В полночь удаляет все данные НЕ за сегодня"""
    deleted = clear_old_data()
    print(f"🌙 [СБРОС] Полночь. Удалено {deleted} записей. Оставлены только данные за сегодня.")

# ========== АВТО-ФОНОВОЕ ОБНОВЛЕНИЕ (тихо) ==========
async def auto_update_background(context: ContextTypes.DEFAULT_TYPE):
    """Фоновое обновление данных кошелька — без отправки сообщений"""
    new_count = await fetch_and_update_today_transactions()
    if new_count > 0:
        print(f"🔄 Фоновое обновление: добавлено {new_count} новых транзакций")

# ========== ФОРМИРОВАНИЕ ОТЧЁТА ==========
async def generate_report_text(date):
    exp_ton, inc_ton = get_daily_summary(date)
    net_ton = inc_ton - exp_ton
    
    ton_price_rub = await get_ton_price("rub")
    ton_price_usd = await get_ton_price("usd")
    
    net_rub = net_ton * ton_price_rub
    net_usd = net_ton * ton_price_usd
    
    operations = get_all_operations(date)
    
    report = f"═══════════════════════════════════\n"
    report += f"📅 ОТЧЁТ ZOV ВОРКЕР за {date}\n"
    report += f"═══════════════════════════════════\n\n"
    
    report += f"💎 TON (АВТО-УЧЁТ):\n"
    report += f"   Потрачено:  {exp_ton:.4f} TON\n"
    report += f"   Получено:   {inc_ton:.4f} TON\n"
    report += f"   ▶ ЧИСТЫМИ:  {net_ton:.4f} TON\n\n"
    
    report += f"🔄 КОНВЕРТАЦИЯ:\n"
    report += f"   Курс TON:   {ton_price_rub:.2f} ₽ / {ton_price_usd:.2f} $\n"
    report += f"   ▶ В рублях:   {net_rub:.2f} ₽\n"
    report += f"   ▶ В долларах: {net_usd:.2f} $\n\n"
    
    report += f"═══════════════════════════════════\n"
    report += f"📋 ДЕТАЛЬНАЯ ВЫПИСКА:\n"
    report += f"═══════════════════════════════════\n"
    
    if not operations:
        report += "За сегодня пока нет операций.\n"
    else:
        for op in operations:
            op_type, amount_ton, comment, tx_hash = op
            arrow = "➕" if op_type == "income_ton" else "➖"
            type_name = "Доход" if op_type == "income_ton" else "Расход"
            report += f"{arrow} {type_name}: {amount_ton:.4f} TON"
            if comment:
                report += f" | {comment}"
            if tx_hash:
                report += f" | tx: {tx_hash[:12]}..."
            report += "\n"
    
    report += f"═══════════════════════════════════\n"
    report += f"🇷🇺 ZOV ВОРКЕР 🇷🇺"
    
    return report, net_ton, net_rub, net_usd

# ========== КЛАВИАТУРА ==========
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 Отчёт (текст)", callback_data="report_text"),
         InlineKeyboardButton("📎 Отчёт (файл)", callback_data="report_file")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ========== ОБРАБОТЧИКИ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🇷🇺 *ZOV Work Tracker (тихий режим)* 🇷🇺\n\n"
        "⚡ РЕЖИМ РАБОТЫ:\n"
        "• 💎 TON — АВТОМАТИЧЕСКОЕ ФОНОВОЕ ОБНОВЛЕНИЕ\n"
        "• 🔄 Бот сам проверяет кошелёк и обновляет данные\n"
        "• 📊 Ты нажимаешь «Отчёт» — получаешь актуальную выписку\n"
        "• 🌙 В полночь — сброс данных за прошлый день\n\n"
        "Нажми «Отчёт», чтобы увидеть все транзакции за сегодня:",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    if data == "check_wallet":
        # Ручная проверка (на всякий случай оставил)
        await query.edit_message_text("🔍 Обновляю данные кошелька...")
        new_count = await fetch_and_update_today_transactions()
        await query.edit_message_text(f"✅ Обновлено. Добавлено {new_count} новых транзакций.")
        await query.message.reply_text("Продолжаем?", reply_markup=get_main_keyboard())
    
    elif data in ["report_text", "report_file"]:
        await query.edit_message_text("📊 Формирую отчёт...")
        
        # ПЕРЕД ОТЧЁТОМ — ПРИНУДИТЕЛЬНО ОБНОВЛЯЕМ ДАННЫЕ
        new_count = await fetch_and_update_today_transactions()
        
        report_text, net_ton, net_rub, net_usd = await generate_report_text(today_str)
        
        # Добавляем информацию об обновлении
        if new_count > 0:
            report_text = f"🔄 Обновлено: +{new_count} новых транзакций\n\n{report_text}"
        
        if data == "report_text":
            await query.edit_message_text(report_text)
        else:
            file_path = f"zov_report_{today_str}.txt"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(report_text)
            with open(file_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=f,
                    filename=f"zov_report_{today_str}.txt",
                    caption=f"📎 Выписка за {today_str}\nЧистый TON: {net_ton:.4f} | ₽: {net_rub:.2f} | $: {net_usd:.2f}"
                )
            os.remove(file_path)
            await query.edit_message_text("✅ Отчёт отправлен файлом.")
        await query.message.reply_text("Продолжаем?", reply_markup=get_main_keyboard())

# ========== ЗАПУСК ==========
def main():
    init_db()
    
    # При старте — удаляем всё, что не сегодня
    deleted = clear_old_data()
    print(f"🔄 При запуске: удалено {deleted} старых записей")
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # ФОНОВЫЕ ЗАДАЧИ (без отправки сообщений в чат)
    job_queue = app.job_queue
    
    if job_queue:
        # Авто-обновление кошелька каждые 30 секунд (тихо)
        job_queue.run_repeating(auto_update_background, interval=30, first=10)
        # Авто-сброс в полночь
        job_queue.run_daily(auto_reset_midnight, time=time(0, 0, 0))
        print("✅ Фоновые задачи запущены: обновление каждые 30 сек, сброс в полночь")
    
    print("🇷🇺 ZOV WORK BOT (тихий режим) запущен. Жду приказов, мой господин.")
    print(f"📍 Кошелёк: {TON_WALLET_ADDRESS}")
    print("📊 Бот молчит в фоне. Ты нажимаешь «Отчёт» — видишь актуальные данные.")
    
    app.run_polling()

if __name__ == "__main__":
    main()
