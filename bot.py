import sqlite3
import os
import aiohttp
from datetime import datetime
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
    conn.commit()
    conn.close()


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
    c.execute("SELECT id, type, amount_ton, comment, tx_hash FROM operations WHERE date=? ORDER BY id DESC", (date,))
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


# ========== TON API (ТОЛЬКО СЕГОДНЯ) ==========
async def get_today_transactions():
    today_str = datetime.now().strftime("%Y-%m-%d")

    url = f"https://toncenter.com/api/v2/getTransactions?address={TON_WALLET_ADDRESS}&limit=100&archival=true&api_key={TONAPI_KEY}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    return []

                new_txs = []

                for tx in data.get("result", []):
                    tx_unixtime = tx.get("utime", 0)
                    tx_date = datetime.fromtimestamp(tx_unixtime).strftime("%Y-%m-%d")

                    if tx_date != today_str:
                        continue

                    tx_hash = tx["transaction_id"]["hash"]

                    if is_tx_already_recorded(tx_hash):
                        continue

                    comment = tx.get("in_msg", {}).get("message", "")

                    # Входящая транзакция
                    in_msg = tx.get("in_msg", {})
                    if in_msg.get("source") and in_msg.get("source") != TON_WALLET_ADDRESS:
                        value_nano = int(in_msg.get("value", 0))
                        if value_nano > 0:
                            value_ton = value_nano / 1e9
                            new_txs.append({
                                "hash": tx_hash,
                                "value_ton": value_ton,
                                "type": "income_ton",
                                "comment": comment or "входящий перевод"
                            })

                    # Исходящие транзакции
                    out_msgs = tx.get("out_msgs", [])
                    for out_msg in out_msgs:
                        if out_msg.get("destination") and out_msg.get("destination") != TON_WALLET_ADDRESS:
                            value_nano = int(out_msg.get("value", 0))
                            if value_nano > 0:
                                value_ton = value_nano / 1e9
                                new_txs.append({
                                    "hash": tx_hash,
                                    "value_ton": value_ton,
                                    "type": "expense_ton",
                                    "comment": comment or "исходящий перевод"
                                })

                return new_txs
    except Exception as e:
        print(f"Ошибка TON API: {e}")
        return []


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

    for op in operations:
        op_id, op_type, amount_ton, comment, tx_hash = op
        arrow = "➕" if op_type == "income_ton" else "➖"
        type_name = "Доход" if op_type == "income_ton" else "Расход"
        report += f"{arrow} {type_name}: {amount_ton:.4f} TON"
        if comment:
            report += f" | {comment}"
        if tx_hash:
            report += f" | tx: {tx_hash[:16]}..."
        report += "\n"

    report += f"═══════════════════════════════════\n"
    report += f"🇷🇺 ZOV ВОРКЕР ЗАВЕРШИЛ ОТЧЁТ 🇷🇺"

    return report, net_ton, net_rub, net_usd


# ========== КЛАВИАТУРА ==========
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔄 Проверить кошелёк (TON за сегодня)", callback_data="check_wallet")],
        [InlineKeyboardButton("📊 Отчёт (текст)", callback_data="report_text"),
         InlineKeyboardButton("📎 Отчёт (файл)", callback_data="report_file")]
    ]
    return InlineKeyboardMarkup(keyboard)


# ========== ОБРАБОТЧИКИ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🇷🇺 *ZOV Work Tracker (только TON)* 🇷🇺\n\n"
        "⚡ РЕЖИМ РАБОТЫ:\n"
        "• 💎 TON — ПОЛНОСТЬЮ АВТОМАТИЧЕСКИ\n"
        "• 📅 Только транзакции за сегодня\n\n"
        "Функции:\n"
        "• 🔄 Проверить кошелёк\n"
        "• 📊 Отчёт (текст или .txt файл)\n"
        "• 💱 Конвертация TON → ₽ / $\n\n"
        "Выбери действие:",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    today_str = datetime.now().strftime("%Y-%m-%d")

    if data == "check_wallet":
        await query.edit_message_text("🔍 Проверяю TON кошелёк (транзакции за сегодня)...")

        new_txs = await get_today_transactions()

        if not new_txs:
            await query.edit_message_text("✅ Новых транзакций за сегодня не найдено.")
        else:
            count = 0
            for tx in new_txs:
                if add_auto_transaction(today_str, tx["hash"], tx["value_ton"], tx["type"], tx["comment"]):
                    count += 1
                    arrow = "🟢 +" if tx["type"] == "income_ton" else "🔴 -"
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"{arrow} {tx['value_ton']:.4f} TON\nКоммент: {tx['comment']}"
                    )
            await query.edit_message_text(f"✅ Записано {count} новых транзакций за сегодня.")
        await query.message.reply_text("Продолжаем?", reply_markup=get_main_keyboard())

    elif data in ["report_text", "report_file"]:
        await query.edit_message_text("📊 Формирую отчёт...")
        report_text, net_ton, net_rub, net_usd = await generate_report_text(today_str)

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
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🇷🇺 ZOV WORK BOT (только TON) запущен. Жду приказов, мой господин.")
    print(f"📍 Кошелёк: {TON_WALLET_ADDRESS}")
    app.run_polling()


if __name__ == "__main__":
    main()
