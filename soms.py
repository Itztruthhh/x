import uuid
import qrcode
import aiosqlite
import asyncio
import nest_asyncio
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, ContextTypes

# Apply nest_asyncio to prevent event loop errors
nest_asyncio.apply()

# Telegram Bot Token (Replace with your actual bot token)
BOT_TOKEN = "7247839166:AAGxuiKewRAeXJB5R2I9cj1SMwLpl29neTo"

# File to Store Server Keys
KEY_FILE = 'keys.txt'

# Key Prices
KEY_PRICES = {
    "magic_server": {
        "1_Day": 150,
        "7_Days": 450,
        "1_Month": 1000
    },
    "not_available_server": {
        "1_month": 150,
        "3_months": 350,
        "6_months": 600
    }
}

# UPI ID (Replace with your actual UPI ID)
UPI_ID = "theycallmesoms@ybl"


# ====== Database Functions ======
async def setup_database():
    async with aiosqlite.connect("transactions.db") as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id TEXT PRIMARY KEY,
            user_id TEXT,
            server TEXT,
            duration TEXT,
            amount REAL,
            verified INTEGER DEFAULT 0
        )
        """)
        await db.commit()


async def save_transaction(transaction_id, user_id, server, duration, amount):
    async with aiosqlite.connect("transactions.db") as db:
        await db.execute(
            "INSERT INTO transactions (transaction_id, user_id, server, duration, amount) VALUES (?, ?, ?, ?, ?)",
            (transaction_id, user_id, server, duration, amount),
        )
        await db.commit()


async def get_transaction(transaction_id):
    async with aiosqlite.connect("transactions.db") as db:
        async with db.execute(
            "SELECT * FROM transactions WHERE transaction_id = ? AND verified = 0",
            (transaction_id,),
        ) as cursor:
            return await cursor.fetchone()


async def mark_transaction_verified(transaction_id):
    async with aiosqlite.connect("transactions.db") as db:
        await db.execute(
            "UPDATE transactions SET verified = 1 WHERE transaction_id = ?",
            (transaction_id,),
        )
        await db.commit()


# ====== Helper Functions ======
def generate_transaction_id():
    return str(uuid.uuid4())


def generate_upi_qr(amount, transaction_id):
    upi_data = f"upi://pay?pa={UPI_ID}&pn=ServerPayment&am={amount}&cu=INR&tid={transaction_id}"
    qr = qrcode.make(upi_data)
    qr_path = f"qr_{transaction_id}.png"
    qr.save(qr_path)
    return qr_path


def assign_server_key(server, duration):
    try:
        with open(KEY_FILE, 'r') as f:
            keys = f.readlines()

        for line in keys:
            key_data = line.strip().split(" ", 1)
            if len(key_data) == 2 and key_data[1] == duration:
                key = key_data[0]
                keys.remove(line)

                with open(KEY_FILE, 'w') as f:
                    f.writelines(keys)
                return key
    except FileNotFoundError:
        return None
    return None


# ====== Command Handlers ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    first_name = user.first_name or "User"

    await update.message.reply_text(
        f"Hello, {first_name}!\n\n"
        "Welcome to the Server Key Payment Bot!\n\n"
        "Here are the commands you can use:\n"
        "- /buy - View available servers and their prices.\n"
        "- /buy <server> <duration> - Purchase a server key.\n"
        "- /verify <transaction_id> - Verify your payment and get your key.\n\n"
        "Enjoy our services!"
    )


async def show_servers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    available_servers = "Here are the available servers and their prices:\n\n"
    for server, durations in KEY_PRICES.items():
        available_servers += f"{server.replace('_', ' ').title()}:\n"
        for duration, price in durations.items():
            available_servers += f"  - {duration.replace('_', ' ').title()}: ₹{price}\n"
            available_servers += "\nTo purchase a server, use the command:\n"
    available_servers += "/buy <server> <duration> (e.g., /buy magic_server 1_Day)"

    await update.message.reply_text(available_servers)


async def process_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 2:
        await show_servers(update, context)
        return

    user_id = update.message.from_user.id
    server, duration = context.args

    if server not in KEY_PRICES or duration not in KEY_PRICES[server]:
        await update.message.reply_text("❌ Invalid server or duration. Please check and try again.")
        return

    amount = KEY_PRICES[server][duration]
    transaction_id = generate_transaction_id()
    qr_path = generate_upi_qr(amount, transaction_id)

    await save_transaction(transaction_id, user_id, server, duration, amount)

    with open(qr_path, "rb") as qr_file:
        await update.message.reply_photo(
            photo=InputFile(qr_file),
            caption=(
                f"🔑 Server: {server.replace('_', ' ').title()}\n"
                f"📅 Duration: {duration.replace('_', ' ').title()}\n"
                f"💵 Amount: ₹{amount}\n"
                f"📤 Transaction ID: {transaction_id}\n\n"
                f"📌 Scan this QR code to complete your payment via UPI."
            ),
        )


async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("❌ Usage: /verify <transaction_id>")
        return

    transaction_id = context.args[0]
    transaction = await get_transaction(transaction_id)

    if transaction:
        _, user_id, server, duration, amount, verified = transaction
        key = assign_server_key(server, duration)

        if key:
            await mark_transaction_verified(transaction_id)
            await update.message.reply_text(f"✅ Payment verified!\nHere is your server key:\n\n{key}")
        else:
            await update.message.reply_text("❌ No keys available for the selected server and duration.")
    else:
        await update.message.reply_text("❌ Invalid transaction ID or payment already verified.")


# ====== Main Function ======
async def main():
    await setup_database()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("buy", process_buy))
    app.add_handler(CommandHandler("verify", verify))
    app.add_handler(CommandHandler("buy", show_servers))  # Handles /buy without arguments

    print("Bot is running...")
    await app.run_polling()


if name == "main":
    asyncio.get_event_loop().run_until_complete(main())
