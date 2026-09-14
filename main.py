from threading import Thread
import os
import sqlite3
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters
import google.generativeai as genai
from flask import Flask

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# API Keys from Render Environment
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
# ပိုမိုတည်ငြိမ်သော gemini-pro မော်ဒယ်သို့ ပြောင်းလဲထားပါသည်
model = genai.GenerativeModel('gemini-pro')

# Database setup
conn = sqlite3.connect('bot_database.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS vip (user_id INTEGER PRIMARY KEY)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS bans (user_id INTEGER PRIMARY KEY)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, role TEXT)''')
conn.commit()

# Owner ID setup
OWNER_ID = 7094887417  # <--- ကိုယ့်ရဲ့ Telegram ID အမှန်

# Helper Functions for Permissions
def get_user_role(user_id):
    if user_id == OWNER_ID:
        return 'owner'
    
    cursor.execute("SELECT role FROM admins WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        return row[0] # 'senior' သို့မဟုတ် 'normal'
        
    cursor.execute("SELECT user_id FROM vip WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        return 'vip'
        
    return 'user'

# --- START COMMAND (Role အလိုက် နှုတ်ဆက်ပုံများ) ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    role = get_user_role(user_id)
    
    if role == 'owner':
        await update.message.reply_text("👑 မင်္ဂလာပါ ပြန်လည်ကြိုဆိုပါတယ် Boss။")
    elif role in ['senior', 'normal']:
        await update.message.reply_text(f"🛡️ မင်္ဂလာပါ Admin ({role.capitalize()})၊ Xinon ရဲ့ auto system talking AI မှ ကြိုဆိုပါတယ်။")
    elif role == 'vip':
        await update.message.reply_text(f"⭐ ချစ်ရပါသော VIP user ({user_id})၊ Xinon ရဲ့ auto system talking AI မှ ကြိုဆိုပါတယ်။")
    else:
        await update.message.reply_text("Xinon ရဲ့ auto system talking AI မှ ကြိုဆိုပါတယ်။ VIP ဝင်ချင်ရင် Telegram -> @REDXinon ထံမှာ မေးမြန်းနိုင်ပါတယ်။")

# --- MESSAGE HANDLER ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Check if user is banned
    cursor.execute("SELECT user_id FROM bans WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        return # Banned users are ignored

    user_message = update.message.text
    
    try:
        cursor.execute("SELECT value FROM settings WHERE key = 'rule'")
        rule_row = cursor.fetchone()
        system_instruction = rule_row[0] if rule_row else "You are a helpful assistant."

        prompt = f"{system_instruction}\n\nUser: {user_message}"
        response = model.generate_content(prompt)
        
        await update.message.reply_text(response.text)
    except Exception as e:
        logging.error(f"Gemini Error: {e}")
        await update.message.reply_text(f"Error occurred: {str(e)}")

# --- OWNER COMMANDS ---
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ ဤ အမိန့်ကို ပိုင်ရှင် (Owner) သာ အသုံးပြုနိုင်ပါသည်။")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("အသုံးပြုပုံ: /addadmin [user_id] [normal/senior]")
        return
        
    try:
        target_id = int(context.args[0])
        role = context.args[1].lower()
        if role not in ['normal', 'senior']:
            await update.message.reply_text("⚠️ Role သည် 'normal' သို့မဟုတ် 'senior' ဖြစ်ရပါမည်။")
            return
            
        cursor.execute("REPLACE INTO admins (user_id, role) VALUES (?, ?)", (target_id, role))
        conn.commit()
        await update.message.reply_text(f"✅ User ID: {target_id} ကို {role} admin အဖြစ် သတ်မှတ်ပြီးပါပြီ။")
    except ValueError:
        await update.message.reply_text("⚠️ User ID မှားယွင်းနေပါသည်။")

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ ဤ အမိန့်ကို ပိုင်ရှင် (Owner) သာ အသုံးပြုနိုင်ပါသည်။")
        return
        
    if not context.args:
        await update.message.reply_text("အသုံးပြုပုံ: /removeadmin [user_id]")
        return
        
    try:
        target_id = int(context.args[0])
        cursor.execute("DELETE FROM admins WHERE user_id = ?", (target_id,))
        conn.commit()
        await update.message.reply_text(f"✅ User ID: {target_id} ကို Admin စာရင်းမှ ဖယ်ရှားပြီးပါပြီ။")
    except ValueError:
        await update.message.reply_text("⚠️ User ID မှားယွင်းနေပါသည်။")

# --- VIP MANAGEMENT ---
async def add_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    role = get_user_role(user_id)
    
    if role not in ['owner', 'senior']:
        await update.message.reply_text("⛔ ဤ အမိန့်ကို Owner နှင့် Senior Admin များသာ အသုံးပြုနိုင်ပါသည်။")
        return
        
    if not context.args:
        await update.message.reply_text("အသုံးပြုပုံ: /addvip [user_id]")
        return
        
    try:
        target_id = int(context.args[0])
        cursor.execute("REPLACE INTO vip (user_id) VALUES (?)", (target_id,))
        conn.commit()
        await update.message.reply_text(f"⭐ User ID: {target_id} ကို VIP အဖြစ် သတ်မှတ်လိုက်ပါပြီ။")
    except ValueError:
        await update.message.reply_text("⚠️ User ID မှားယွင်းနေပါသည်။")

async def remove_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    role = get_user_role(user_id)
    
    if role not in ['owner', 'senior']:
        await update.message.reply_text("⛔ ဤ အမိန့်ကို Owner နှင့် Senior Admin များသာ အသုံးပြုနိုင်ပါသည်။")
        return
        
    if not context.args:
        await update.message.reply_text("အသုံးပြုပုံ: /removevip [user_id]")
        return
        
    try:
        target_id = int(context.args[0])
        cursor.execute("DELETE FROM vip WHERE user_id = ?", (target_id,))
        conn.commit()
        await update.message.reply_text(f"🗑️ User ID: {target_id} ကို VIP စာရင်းမှ ဖယ်ရှားလိုက်ပါပြီ။")
    except ValueError:
        await update.message.reply_text("⚠️ User ID မှားယွင်းနေပါသည်။")

# --- BAN MANAGEMENT ---
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sender_role = get_user_role(user_id)
    
    if sender_role not in ['owner', 'senior', 'normal']:
        await update.message.reply_text("⛔ ဤ အမိန့်ကို Admin များသာ အသုံးပြုနိုင်ပါသည်။")
        return
        
    if not context.args:
        await update.message.reply_text("အသုံးပြုပုံ: /ban [user_id]")
        return
        
    try:
        target_id = int(context.args[0])
        target_role = get_user_role(target_id)
        
        if sender_role == 'normal' and target_role in ['owner', 'senior', 'normal', 'vip']:
            await update.message.reply_text("⛔ Normal Admin သည် VIP များကိုသော်လည်းကောင်း၊ အခြား Admin များကိုသော်လည်းကောင်း Ban ခွင့်မရှိပါ။")
            return
            
        cursor.execute("REPLACE INTO bans (user_id) VALUES (?)", (target_id,))
        conn.commit()
        await update.message.reply_text(f"🚫 User ID: {target_id} ကို Bot သုံးခွင့်မှ ပိတ်ပင်လိုက်ပါပြီ။")
    except ValueError:
        await update.message.reply_text("⚠️ User ID မှားယွင်းနေပါသည်။")

# --- OTHER COMMANDS ---
async def set_rule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ ဒီ အမိန့်ကို ပိုင်ရှင် (Owner) သာ အသုံးပြုနိုင်ပါသည်။")
        return
    
    new_rule = " ".join(context.args)
    if not new_rule:
        await update.message.reply_text("ကျေးဇူးပြု၍ သတ်မှတ်မည့် စည်းမျဉ်းကို ရေးပါ။ ဥပမာ: /setrule ယဉ်ကျေးစွာပြောပါ")
        return
        
    cursor.execute("REPLACE INTO settings (key, value) VALUES ('rule', ?)", (new_rule,))
    conn.commit()
    await update.message.reply_text("✅ စည်းမျဉ်းအသစ်ကို သိမ်းဆည်းပြီးပါပြီ။")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    role = get_user_role(user_id)
    await update.message.reply_text(f"👤 Your current role status is: **{role.upper()}**")

# --- FLASK WEB SERVER FOR RENDER ---
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Telegram Bot is running smoothly!"

def run_web():
    app_web.run(host='0.0.0.0', port=10000)

def main():
    # Start Flask thread for Render port binding
    web_thread = Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()

    # Telegram Bot Application Setup
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("setrule", set_rule))
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("removeadmin", remove_admin))
    app.add_handler(CommandHandler("addvip", add_vip))
    app.add_handler(CommandHandler("removevip", remove_vip))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("Bot is polling successfully...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
    
