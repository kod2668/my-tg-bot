from threading import Thread
import os
import sqlite3
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters
from google import genai
from flask import Flask, request, jsonify

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# API Keys from Render Environment
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configure Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# Database setup
conn = sqlite3.connect('bot_database.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS vip (device_id TEXT PRIMARY KEY)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS bans (user_id INTEGER PRIMARY KEY)''')
conn.commit()

# Owner ID setup
OWNER_ID = 7094887417  # <--- ကိုယ့်ရဲ့ Telegram ID အမှန်

# --- HELPER FUNCTIONS ---
def is_device_vip(device_id):
    if not device_id:
        return False
    cursor.execute("SELECT device_id FROM vip WHERE device_id = ?", (device_id,))
    return cursor.fetchone() is not None

def is_admin_or_owner(user_id):
    if user_id == OWNER_ID:
        return True
    cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    return cursor.fetchone() is not None


# --- TELEGRAM COMMANDS (Owner & Admins Control Panel) ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id == OWNER_ID:
        await update.message.reply_text(
            "👑 မင်္ဂလာပါ Boss (Owner)။\n\n"
            "🔹 **Admin စီမံရန်:**\n"
            "/addadmin [user_id]\n"
            "/removeadmin [user_id]\n\n"
            "⭐ **VIP စီမံရန်:**\n"
            "/addvip [Device_ID]\n"
            "/removevip [Device_ID]"
        )
    elif is_admin_or_owner(user_id):
        await update.message.reply_text(
            "🛡️ မင်္ဂလာပါ Admin။\n\n"
            "⭐ **VIP စီမံရန်:**\n"
            "/addvip [Device_ID]\n"
            "/removevip [Device_ID]"
        )
    else:
        await update.message.reply_text("⛔ ဤ Bot ကို ခွင့်ပြုချက်ရသူများသာ အသုံးပြုနိုင်ပါသည်။")

# --- OWNER ONLY: ADMIN MANAGEMENT ---
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ ဤအမိန့်ကို ပိုင်ရှင် (Owner) သာ အသုံးပြုနိုင်ပါသည်။")
        return
        
    if not context.args:
        await update.message.reply_text("⚠️ အသုံးပြုပုံ: /addadmin [Telegram_User_ID]")
        return
        
    try:
        target_id = int(context.args[0])
        cursor.execute("REPLACE INTO admins (user_id) VALUES (?)", (target_id,))
        conn.commit()
        await update.message.reply_text(f"🛡️ Telegram ID: `{target_id}` ကို Admin အဖြစ် အောင်မြင်စွာ သတ်မှတ်လိုက်ပါပြီ။")
    except ValueError:
        await update.message.reply_text("⚠️ Telegram User ID သည် ဂဏန်းဖြစ်ရပါမည်။")

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ ဤအမိန့်ကို ပိုင်ရှင် (Owner) သာ အသုံးပြုနိုင်ပါသည်။")
        return
        
    if not context.args:
        await update.message.reply_text("⚠️ အသုံးပြုပုံ: /removeadmin [Telegram_User_ID]")
        return
        
    try:
        target_id = int(context.args[0])
        cursor.execute("DELETE FROM admins WHERE user_id = ?", (target_id,))
        conn.commit()
        await update.message.reply_text(f"🗑️ Telegram ID: `{target_id}` ကို Admin စာရင်းမှ ဖယ်ရှားလိုက်ပါပြီ။")
    except ValueError:
        await update.message.reply_text("⚠️ Telegram User ID သည် ဂဏန်းဖြစ်ရပါမည်။")

# --- OWNER & ADMINS: VIP MANAGEMENT ---
async def add_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin_or_owner(user_id):
        await update.message.reply_text("⛔ ဤအမိန့်ကို Owner နှင့် Admin များသာ အသုံးပြုနိုင်ပါသည်။")
        return
        
    if not context.args:
        await update.message.reply_text("⚠️ အသုံးပြုပုံ: /addvip [App_Device_ID]")
        return
        
    target_device_id = context.args[0]
    try:
        cursor.execute("REPLACE INTO vip (device_id) VALUES (?)", (target_device_id,))
        conn.commit()
        await update.message.reply_text(f"⭐ အောင်မြင်ပါပြီ!\nDevice ID: `{target_device_id}` ကို VIP သတ်မှတ်ပြီးပါပြီ။")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

async def remove_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin_or_owner(user_id):
        await update.message.reply_text("⛔ ဤအမိန့်ကို Owner နှင့် Admin များသာ အသုံးပြုနိုင်ပါသည်။")
        return
        
    if not context.args:
        await update.message.reply_text("⚠️ အသုံးပြုပုံ: /removevip [App_Device_ID]")
        return
        
    target_device_id = context.args[0]
    cursor.execute("DELETE FROM vip WHERE device_id = ?", (target_device_id,))
    conn.commit()
    await update.message.reply_text(f"🗑️ ပြီးပါပြီ!\nDevice ID: `{target_device_id}` ကို VIP စာရင်းမှ ဖယ်ရှားလိုက်ပါပြီ။")

async def ignore_regular_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin_or_owner(update.effective_user.id):
        await update.message.reply_text("ℹ️ ဤ Bot သည် App Backend ဖြစ်ပြီး Telegram တွင် စကားပြောရန် မဟုတ်ပါ။ Command များ (/addvip, /removevip) ကိုသာ အသုံးပြုပါ။")


# --- FLASK WEB SERVER FOR APP & RENDER ---
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Xinon Backend & Telegram Bot is running smoothly!"

@app_web.route('/chat', methods=['POST'])
def web_chat():
    try:
        data = request.get_json()
        user_message = data.get('message', '')
        device_id = data.get('device_id', '')

        if not user_message:
            return jsonify({"reply": "စာ မပါဝင်ပါ။"}), 400

        user_is_vip = is_device_vip(device_id)

        if not user_is_vip:
            system_instruction = "You are a helpful assistant. (Free User Mode)"
        else:
            system_instruction = "You are an advanced AI assistant for VIP users. Give detailed responses."

        prompt = f"{system_instruction}\n\nUser: {user_message}"
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        
        return jsonify({
            "reply": response.text,
            "is_vip": user_is_vip
        })
    except Exception as e:
        return jsonify({"reply": f"Error: {str(e)}", "is_vip": False}), 500

def run_web():
    app_web.run(host='0.0.0.0', port=10000)

def main():
    web_thread = Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()

    # Telegram Bot Setup
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("removeadmin", remove_admin))
    app.add_handler(CommandHandler("addvip", add_vip))
    app.add_handler(CommandHandler("removevip", remove_vip))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), ignore_regular_messages))

    print("Bot & Web Server running successfully...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()

