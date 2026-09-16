import os
import sqlite3
import threading
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, Response, stream_with_context, render_template, redirect, url_for, session, flash
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from google import genai
from google.genai import types

# Telegram Bot အတွက် လိုအပ်သော library များ
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

# Initialize Flask with templates folder
app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app)

# ==================== CONFIGURATIONS ====================
TELEGRAM_TOKEN = "8854987165:AAHqjcgVAUoSEgtoIHabxAkPvZ-eoje5hcY"
OWNER_ID = 7094887417  # Boss (Owner) သီးသန့် ID
DB_NAME = "xinon_users.db"

# ==================== DATABASE CONFIGURATION (Email & Password) ====================
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

with app.app_context():
    db.create_all()

# ==================== WEB UI ROUTES ====================
@app.route('/')
def index():
    if 'user_email' in session:
        return redirect(url_for('chat_page'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_email' in session:
        return redirect(url_for('chat_page'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            session['user_email'] = user.email
            return redirect(url_for('chat_page'))
        else:
            flash('Email သို့မဟုတ် Password အမှားဖြစ်နေပါသည်!', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_email' in session:
        return redirect(url_for('chat_page'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('ဤ Email ဖြင့် အကောင့်ရှိနှင့်ပြီးသားပါ!', 'error')
            return redirect(url_for('register'))
        hashed_password = generate_password_hash(password, method='scrypt')
        new_user = User(email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('အကောင့်ဖွင့်ခြင်း အောင်မြင်ပါသည်။ ကျေးဇူးပြု၍ Login ဝင်ပါ။', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/chat')
def chat_page():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    return render_template('chat.html', email=session['user_email'])

@app.route('/logout')
def logout():
    session.pop('user_email', None)
    return redirect(url_for('index'))

# ==================== VIP & ADMIN DATABASE SETUP ====================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vips (
            device_id TEXT PRIMARY KEY,
            expiry_date TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            admin_id INTEGER PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ==================== HELPER FUNCTIONS ====================
def is_admin(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM admins WHERE admin_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res is not None

def is_vip(device_id: str) -> bool:
    if not device_id:
        return False
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM vips WHERE device_id = ?", (device_id,))
    res = cursor.fetchone()
    conn.close()
    return res is not None

def clean_expired_vips():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("DELETE FROM vips WHERE expiry_date < ?", (now_str,))
    conn.commit()
    conn.close()

# ==================== TELEGRAM BOT COMMAND HANDLERS ====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    clean_expired_vips()
    
    if user_id == OWNER_ID:
        await update.message.reply_text(
            "👑 **မင်္ဂလာပါ Boss (Owner)**\n\n"
            "🔹 **Admin စီမံရန်:**\n"
            "`/addadmin [user_id]`\n"
            "`/removeadmin [user_id]`\n"
            "`/listadmins`\n\n"
            "⭐ **VIP စီမံရန်:**\n"
            "`/addvip [Device_ID] [ရက်]`\n"
            "`/removevip [Device_ID]`\n"
            "`/listvips`",
            parse_mode="Markdown"
        )
    elif is_admin(user_id):
        await update.message.reply_text(
            "🛡 **မင်္ဂလာပါ Admin**\n\n"
            "⭐ **VIP စီမံရန်:**\n"
            "`/addvip [Device_ID] [ရက်]`\n"
            "`/removevip [Device_ID]`\n"
            "`/listvips`",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("⛔ ခွင့်ပြုချက်မရှိပါ။")

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Owner သီးသန့် ဖြစ်ပါသည်။")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("⚠️ ဥပမာ - `/addadmin 123456789`", parse_mode="Markdown")
        return
    
    new_admin_id = int(context.args[0])
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO admins (admin_id) VALUES (?)", (new_admin_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"👑 Admin အသစ်ထည့်ပြီးပါပြီ: `{new_admin_id}`", parse_mode="Markdown")

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Owner သီးသန့် ဖြစ်ပါသည်။")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("⚠️ ဥပမာ - `/removeadmin 123456789`", parse_mode="Markdown")
        return
    
    target_admin_id = int(context.args[0])
    if target_admin_id == OWNER_ID:
        await update.message.reply_text("⚠️ Boss ၏ ID ကို ဖယ်ရှား၍ မရပါ။")
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM admins WHERE admin_id = ?", (target_admin_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"🗑️ Admin ဖယ်ရှားပြီးပါပြီ: `{target_admin_id}`", parse_mode="Markdown")

async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Owner သီးသန့် ဖြစ်ပါသည်။")
        return
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT admin_id FROM admins")
    admins = cursor.fetchall()
    conn.close()
    
    admin_list_str = "\n".join([f"• `{a[0]}`" for a in admins]) if admins else "Admin မရှိသေးပါ။"
    await update.message.reply_text(f"📋 **Admin စာရင်းများ:**\n{admin_list_str}", parse_mode="Markdown")

async def add_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ ခွင့်ပြုချက် မရှိပါ။")
        return
    
    if len(context.args) < 2 or not context.args[1].isdigit():
        await update.message.reply_text("⚠️ ဥပမာ - `/addvip xdev_abc123 30`", parse_mode="Markdown")
        return
    
    dev_id = context.args[0]
    days = int(context.args[1])
    
    expiry_date = datetime.now() + timedelta(days=days)
    expiry_str = expiry_date.strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO vips (device_id, expiry_date) VALUES (?, ?)
        ON CONFLICT(device_id) DO UPDATE SET expiry_date = ?
    """, (dev_id, expiry_str, expiry_str))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"✅ **VIP ထည့်သွင်းပြီးပါပြီ!**\n\n"
        f"🔹 Device ID: `{dev_id}`\n"
        f"⏳ သက်တမ်း: {days} ရက်\n"
        f"📅 ကုန်ဆုံးရက်: `{expiry_str}`",
        parse_mode="Markdown"
    )

async def remove_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ ခွင့်ပြုချက် မရှိပါ။")
        return
    if not context.args:
        await update.message.reply_text("⚠️ ဥပမာ - `/removevip xdev_abc123`", parse_mode="Markdown")
        return
    
    dev_id = context.args[0]
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM vips WHERE device_id = ?", (dev_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"🗑️ VIP ဖယ်ရှားပြီးပါပြီ: `{dev_id}`", parse_mode="Markdown")

async def list_vips(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ ခွင့်ပြုချက် မရှိပါ။")
        return
    
    clean_expired_vips()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT device_id, expiry_date FROM vips")
    vips = cursor.fetchall()
    conn.close()
    
    if not vips:
        await update.message.reply_text("📋 Active VIP မရှိသေးပါ။")
        return
    
    msg = f"📋 **VIP စာရင်းများ (စုစုပေါင်း: {len(vips)} ယောက်):**\n\n"
    for v in vips:
        msg += f"• `ID:` {v[0]}\n  `ကုန်ဆုံးရက်:` {v[1]}\n\n"
        
    await update.message.reply_text(msg, parse_mode="Markdown")

def run_telegram_bot():
    try:
        application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("addadmin", add_admin))
        application.add_handler(CommandHandler("removeadmin", remove_admin))
        application.add_handler(CommandHandler("deladmin", remove_admin))
        application.add_handler(CommandHandler("listadmins", list_admins))
        
        application.add_handler(CommandHandler("addvip", add_vip))
        application.add_handler(CommandHandler("removevip", remove_vip))
        application.add_handler(CommandHandler("delvip", remove_vip))
        application.add_handler(CommandHandler("listvips", list_vips))
        
        print("🤖 Telegram Bot အောင်မြင်စွာ စတင်နေပါပြီ...")
        application.run_polling()
    except Exception as e:
        print(f"❌ Telegram Bot Error: {e}")

# ==================== WEBVIEW APP CHAT API ROUTE ====================
@app.route('/api/chat', methods=['POST'])
def api_chat():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return Response("[Error: GEMINI_API_KEY environment variable is missing on server.]", mimetype='text/plain')
    
    client = genai.Client(api_key=api_key)

    if request.files:
        device_id = request.form.get("device_id")
        prompt = request.form.get("prompt", "")
        user_id = request.form.get("user_id", 0)
        image_file = request.files.get("image")
        
        file_data = None
        if image_file:
            image_bytes = image_file.read()
            file_data = types.Part.from_bytes(
                data=image_bytes,
                mime_type=image_file.content_type
            )
    else:
        data = request.json or {}
        device_id = data.get("device_id")
        prompt = data.get("prompt", "")
        user_id = data.get("user_id", 0)
        file_data = None

    # အသုံးပြုသူ အမျိုးအစား ခွဲခြားခြင်း (Owner, VIP, Free)
    is_owner = (int(user_id) == OWNER_ID or device_id == "xdev_gg2bj8omwskmu282byb")
    user_is_vip = is_vip(device_id)

    # Free user များ Code တောင်းခြင်း ရှိမရှိ စစ်ဆေးရန် Keywords များ
    code_keywords = ["code", "python", "html", "javascript", "script", "program", "function", "source", "ကုဒ်", "ရေးပေး", "ရေးပြ"]
    is_asking_for_code = any(keyword in prompt.lower() for keyword in code_keywords)

    # Free user က Code တောင်းပါက တားမြစ်ရန်
    if not is_owner and not user_is_vip and is_asking_for_code:
        def restricted_generate():
            yield "❌ **Access Denied:** Free user များအနေဖြင့် AI ဆီမှ Code များကို တောင်းခံခွင့်မရှိပါ။ Code များ ရေးခိုင်းနိုင်ရန် VIP အဆင့်သို့ Upgrade ပြုလုပ်ပါ။"
        return Response(stream_with_context(restricted_generate()), mimetype='text/plain')

    # Model နှင့် System Instruction သတ်မှတ်ခြင်း (မူရင်းအတိုင်း)
    if is_owner:
        model_name = 'gemini-3.5-flash-lite'
        system_instruction = "You are Xinon AI, an elite, highly respectful personal assistant to your Creator and Boss..."
        safety_settings = [
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        ]
    elif user_is_vip:
        model_name = 'gemini-3.5-flash-lite'
        system_instruction = "You are Xinon AI, a premium and advanced assistant for VIP users, providing deep analytical, highly accurate, and professional responses..."
        safety_settings = [
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        ]
    else:
        model_name = 'gemini-3.1-flash-lite'
        system_instruction = "You are Xinon AI, a standard helpful assistant..."
        safety_settings = []

    contents = [prompt] if prompt else []
    if file_data:
        contents.append(file_data)

    def generate():
        try:
            response = client.models.generate_content_stream(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    safety_settings=safety_settings if safety_settings else None,
                )
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            yield f"\n[Error: {str(e)}]"

    return Response(stream_with_context(generate()), mimetype='text/plain')

# ==================== MAIN ENTRY POINT ====================
if __name__ == '__main__':
    # Telegram Bot ကို Background Thread ဖြင့် စတင်ခြင်း
    bot_thread = threading.Thread(target=run_telegram_bot)
    bot_thread.daemon = True
    bot_thread.start()

    # Flask App စတင်ခြင်း
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
