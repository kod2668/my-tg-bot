import os
import threading
import sqlite3
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

# Render က Port တောင်းဆိုမှုကို ဖြေကြားရန် Dummy Web Server
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

def get_current_rule():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key='rule'")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else ""

def update_current_rule(new_rule):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET value=? WHERE key='rule'", (new_rule,))
    conn.commit()
    conn.close()

def get_user_role(user_id):
    if user_id == OWNER_ID:
        return "owner"
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "normal"

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
        await update.message.reply_text(
            "မင်္ဂလာပါ Boss! Database စနစ်ဖြင့် အောင်မြင်စွာ ချိတ်ဆက်ပြီးပါပြီ။ 👑\n\n"
            "🛠 **Owner Commands:**\n"
            "👉 `/setrule [AI လိုက်နာရမယ့် စည်းကမ်းအသစ်]` - AI ၏ ပုံစံ/စည်းကမ်းကို ချက်ချင်းပြောင်းရန်\n"
            "👉 `/addvip [user_id]` - User တစ်ဦးကို VIP သတ်မှတ်ရန်\n"
            "👉 `/ban [user_id]` - User တစ်ဦးကို ပိတ်ရန်\n"
            "👉 `/status` - မိမိ၏ User Status ကို စစ်ဆေးရန်",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"မင်္ဂလာပါ။ သင်၏အဆင့်မှာ [{role.upper()}] ဖြစ်ပါသည်။ Status စစ်ဆေးရန် `/status` ဟု ရိုက်ပါ။")

async def set_rule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("ဤ Command ကို Owner သာ အသုံးပြုနိုင်ပါသည်။")
        return
    if not context.args:
        await update.message.reply_text(f"လက်ရှိ စည်းမျဉ်း:\n`{get_current_rule()}`\n\nပြောင်းရန် ဥပမာ - `/setrule You must reply only in Myanmar language.`", parse_mode="Markdown")
        return
    
    new_rule = " ".join(context.args)
    update_current_rule(new_rule)
    await update.message.reply_text(f"✅ AI ၏ စည်းမျဉ်းအသစ်ကို Database ထဲသို့ အောင်မြင်စွာ သိမ်းဆည်းလိုက်ပါပြီ:\n\n`{new_rule}`", parse_mode="Markdown")

async def add_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if get_user_role(update.effective_user.id) not in ["owner", "admin"]:
        await update.message.reply_text("ခွင့်ပြုချက်မရှိပါ။")
        return
    try:
        if not context.args:
            await update.message.reply_text("ကျေးဇူးပြု၍ ID ထည့်ပါ။ ဥပမာ - `/addvip 123456789`")
            return
        target_id = int(context.args[0])
        set_user_role(target_id, "vip")
        await update.message.reply_text(f"⭐ User ID: {target_id} ကို VIP သို့ ပြောင်းလိုက်ပါပြီ။")
    except Exception:
        await update.message.reply_text("မှားယွင်းနေပါသည်။ /addvip [id] ဖြင့်သုံးပါ။")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if get_user_role(update.effective_user.id) not in ["owner", "admin"]:
        await update.message.reply_text("ခွင့်ပြုချက်မရှိပါ။")
        return
    try:
        if not context.args:
            await update.message.reply_text("ကျေးဇူးပြု၍ ID ထည့်ပါ။ ဥပမာ - `/ban 123456789`")
            return
        target_id = int(context.args[0])
        if target_id == OWNER_ID:
            await update.message.reply_text("Owner ကို Ban လို့ မရပါ။")
            return
        set_user_role(target_id, "banned")
        await update.message.reply_text(f"User ID: {target_id} ကို Ban လိုက်ပါပြီ။")
    except Exception:
        pass

async def check_my_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    role = get_user_role(user.id)
    
    if user.id == OWNER_ID:
        status_text = "👑 သင်သည် Bot ၏ ပိုင်ရှင် (Owner) ဖြစ်ပါသည်။"
    elif role == "vip":
        status_text = "⭐ သင်သည် VIP အဆင့် အသုံးပြုသူ ဖြစ်ပါသည်။"
    elif role == "banned":
        status_text = "🚫 သင့်ကို Bot အသုံးပြုခွင့် ပိတ်ပင်ထားပါသည်။"
    else:
        status_text = "👤 သင်သည် ပုံမှန် အဆင့် (Normal User) ဖြစ်ပါသည်။"
        
    await update.message.reply_text(f"📊 **User Status Info**\n\nID: `{user.id}`\nName: {user.first_name}\nStatus: {status_text}", parse_mode="Markdown")

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
            model="llama-3.1-8b-instant",
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
        await update.message.reply_text("Error occurred while processing your request.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setrule", set_rule))
    app.add_handler(CommandHandler("addvip", add_vip))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("status", check_my_status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot is polling with Database & Status Check...")
    app.run_polling()
  
