import os
import threading
import sqlite3
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

# Render Port 10000 Dummy Web Server
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY)

OWNER_ID = 7094887417  

# --- SQLite Database Setup ---
def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    # ဇယားများ ဖန်တီးခြင်း
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            role TEXT
        )
    """)
    conn.commit()
    
    # ပုံသေ System Rule မရှိသေးရင် ထည့်ရန်
    cursor.execute("SELECT value FROM settings WHERE key='rule'")
    if not cursor.fetchone():
        default_rule = "You are my private AI assistant. You must strictly follow my commands."
        cursor.execute("INSERT INTO settings (key, value) VALUES ('rule', ?)", (default_rule,))
        conn.commit()
    conn.close()

init_db()

# Database ထဲမှ စည်းမျဉ်းကို လှမ်းယူရန်
def get_current_rule():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key='rule'")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else ""

# Database ထဲသို့ စည်းမျဉ်းအသစ် သိမ်းရန်
def update_current_rule(new_rule):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET value=? WHERE key='rule'", (new_rule,))
    conn.commit()
    conn.close()

# User တစ်ဦး၏ Role ကို စစ်ဆေးရန် (vip, banned, normal)
def get_user_role(user_id):
    if user_id == OWNER_ID:
        return "owner"
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "normal"

# User Role သတ်မှတ်ရန်
def set_user_role(user_id, role):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (user_id, role) VALUES (?, ?)", (user_id, role))
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    role = get_user_role(user.id)

    if role == "banned":
        await update.message.reply_text("တောင်းပန်ပါတယ်၊ သင့်ကို Bot အသုံးပြုခွင့် ပိတ်ပင်ထားပါတယ်။")
        return

    if user.id == OWNER_ID:
        await update.message.reply_text("မင်္ဂလာပါ Boss! Database စနစ်ဖြင့် အောင်မြင်စွာ ချိတ်ဆက်ပြီးပါပြီ။ 👑")
    else:
        await update.message.reply_text(f"မင်္ဂလာပါ။ သင်၏အဆင့်မှာ [{role.upper()}] ဖြစ်ပါသည်။")

async def set_rule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text(f"လက်ရှိ စည်းမျဉ်း:\n`{get_current_rule()}`", parse_mode="Markdown")
        return
    
    new_rule = " ".join(context.args)
    update_current_rule(new_rule)
    await update.message.reply_text(f"✅ စည်းမျဉ်းအသစ်ကို Database ထဲသို့ သိမ်းဆည်းပြီးပါပြီ။")

async def add_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if get_user_role(update.effective_user.id) not in ["owner", "admin"]:
        return
    try:
        target_id = int(context.args[0])
        set_user_role(target_id, "vip")
        await update.message.reply_text(f"⭐ User ID: {target_id} ကို VIP သို့ ပြောင်းလိုက်ပါပြီ။")
    except Exception:
        await.message.reply_text("မှားယွင်းနေပါသည်။ /addvip [id] ဖြင့်သုံးပါ။")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if get_user_role(update.effective_user.id) not in ["owner", "admin"]:
        return
    try:
        target_id = int(context.args[0])
        if target_id == OWNER_ID:
            return
        set_user_role(target_id, "banned")
        await update.message.reply_text(f"User ID: {target_id} ကို Ban လိုက်ပါပြီ။")
    except Exception:
        pass

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    role = get_user_role(user.id)
    
    if role == "banned":
        return

    user_text = update.message.text
    try:
        current_rule = get_current_rule()
        truncated_text = user_text[:3000] if user_text else ""

        completion = groq_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": current_rule},
                {"role": "user", "content": truncated_text}
            ]
        )
        reply_text = completion.choices[0].message.content
        
        if user.id == OWNER_ID:
            reply_text = f"[Boss 👑]\n{reply_text}"
        elif role == "vip":
            reply_text = f"[VIP ⭐]\n{reply_text}"
            
        await update.message.reply_text(reply_text)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setrule", set_rule))
    app.add_handler(CommandHandler("addvip", add_vip))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot is polling with Database...")
    app.run_polling()
