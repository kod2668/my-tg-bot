import os
import sqlite3
import threading
from flask import Flask, request, jsonify, Response, stream_with_context, render_template, redirect, url_for, session, flash
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
from google import genai
from google.genai import types

# Initialize Flask with templates folder
app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app)

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

# ==================== WEB UI ROUTES (Session Fixed) ====================
@app.route('/')
def index():
    # Login ဝင်ပြီးသားဆိုရင် Chat မျက်နှာသို့ အလိုအလျောက် ပို့ပေးမည် (ခဏခဏ Sign in လုပ်စရာမလိုတော့ပါ)
    if 'user_email' in session:
        return redirect(url_for('chat_page'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_email' in session:
        return redirect(url_for('chat_page'))
        
    if request.method == 'POST':
        email = request.form.get('email').strip().lower()
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            session['user_email'] = user.email
            session.permanent = True  # Session ကို အမြဲမှတ်ထားရန်
            return redirect(url_for('chat_page'))
        else:
            flash('Email သို့မဟုတ် Password အမှားဖြစ်နေပါသည်!', 'error')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_email' in session:
        return redirect(url_for('chat_page'))
        
    if request.method == 'POST':
        email = request.form.get('email').strip().lower()
        password = request.form.get('password')
        
        # Email ရှိပြီးသား ဟုတ်မဟုတ် ထပ်မံစစ်ဆေးခြင်း
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('ဤ Email ဖြင့် အကောင့်ရှိနှင့်ပြီးသားပါ! ကျေးဇူးပြု၍ Login ဝင်ပါ။', 'error')
            return redirect(url_for('login'))
            
        hashed_password = generate_password_hash(password, method='scrypt')
        new_user = User(email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        
        flash('အကောင့်ဖွင့်ခြင်း အောင်မြင်ပါသည်။ ယခု Login ဝင်နိုင်ပါပြီ။', 'success')
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
    return redirect(url_for('login'))

# ==================== BACKEND DATABASES & ACCESS CONTROLS ====================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
OWNER_ID = 7094887417  # Boss (Owner) သီးသန့် ID

def init_dbs():
    conn = sqlite3.connect("xinon_users.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vips (
            device_id TEXT PRIMARY KEY
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            admin_id INTEGER PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()

init_dbs()

def is_vip(device_id: str) -> bool:
    if not device_id:
        return False
    conn = sqlite3.connect("xinon_users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM vips WHERE device_id = ?", (device_id,))
    res = cursor.fetchone()
    conn.close()
    return res is not None

def is_admin(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    conn = sqlite3.connect("xinon_users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM admins WHERE admin_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res is not None

# ==================== TELEGRAM BOT MANAGEMENT COMMANDS ====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id == OWNER_ID:
        await update.message.reply_text(
            "👑 **မင်္ဂလာပါ Boss (Owner)။**\n\n"
            "🛠 **Boss ၏ စီမံခန့်ခွဲရန် Commands များ:**\n"
            "• `/addadmin [Telegram_ID]` - Admin အသစ်ထည့်ရန်\n"
            "• `/deladmin [Telegram_ID]` - Admin မှ ဖယ်ရှားရန်\n"
            "• `/listadmins` - Admin စာရင်းကြည့်ရန်\n"
            "• `/addvip [Device_ID]` - VIP အသစ်ထည့်ရန်\n"
            "• `/delvip [Device_ID]` - VIP ဖယ်ရှားရန်"
        )
    elif is_admin(user_id):
        await update.message.reply_text(
            "🛡 **မင်္ဂလာပါ Admin။**\n\n"
            "🛠 **Admin ၏ စီမံခန့်ခွဲရန် Commands များ:**\n"
            "• `/addvip [Device_ID]` - VIP အသစ်ထည့်ရန်\n"
            "• `/delvip [Device_ID]` - VIP ဖယ်ရှားရန်"
        )
    else:
        await update.message.reply_text("⛔ ခွင့်ပြုချက်မရှိပါ။ ဤ Bot သည် စီမံခန့်ခွဲရေးအတွက်သာ ဖြစ်ပါသည်။")

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ ဤ Command သည် Owner (Boss) သီးသန့် အသုံးပြုခွင့်ရှိပါသည်။")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("⚠️ ဥပမာ - `/addadmin 123456789`")
        return
    
    new_admin_id = int(context.args[0])
    conn = sqlite3.connect("xinon_users.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO admins (admin_id) VALUES (?)", (new_admin_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"👑 Admin အသစ်အဖြစ် အောင်မြင်စွာ ထည့်သွင်းပြီးပါပြီ: `{new_admin_id}`", parse_mode="Markdown")

async def del_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ ဤ Command သည် Owner (Boss) သီးသန့် အသုံးပြုခွင့်ရှိပါသည်။")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("⚠️ ဥပမာ - `/deladmin 123456789`")
        return
    
    target_admin_id = int(context.args[0])
    if target_admin_id == OWNER_ID:
        await update.message.reply_text("⚠️ Boss ၏ ID ကို ဖယ်ရှား၍ မရပါ။")
        return

    conn = sqlite3.connect("xinon_users.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM admins WHERE admin_id = ?", (target_admin_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"🗑️ Admin စာရင်းမှ အောင်မြင်စွာ ဖယ်ရှားပြီးပါပြီ: `{target_admin_id}`", parse_mode="Markdown")

async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ ဤ Command သည် Owner (Boss) သီးသန့် ဖြစ်ပါသည်။")
        return
    
    conn = sqlite3.connect("xinon_users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT admin_id FROM admins")
    admins = cursor.fetchall()
    conn.close()
    
    admin_list_str = "\n".join([str(a[0]) for a in admins]) if admins else "Admin မရှိသေးပါ။"
    await update.message.reply_text(f"📋 **လက်ရှိ Admin စာရင်းများ:**\n{admin_list_str}")

async def add_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ ဤ Command ကို အသုံးပြုရန် ခွင့်ပြုချက် မရှိပါ။")
        return
    if not context.args:
        await update.message.reply_text("⚠️ ဥပမာ - `/addvip xdev_xxx...`")
        return
    
    dev_id = context.args[0]
    conn = sqlite3.connect("xinon_users.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO vips (device_id) VALUES (?)", (dev_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ VIP အဖြစ် အောင်မြင်စွာ ထည့်သွင်းပြီးပါပြီ: `{dev_id}`", parse_mode="Markdown")

async def del_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ ဤ Command ကို အသုံးပြုရန် ခွင့်ပြုချက် မရှိပါ။")
        return
    if not context.args:
        await update.message.reply_text("⚠️ ဥပမာ - `/delvip xdev_xxx...`")
        return
    
    dev_id = context.args[0]
    conn = sqlite3.connect("xinon_users.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM vips WHERE device_id = ?", (dev_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"🗑️ VIP စာရင်းမှ အောင်မြင်စွာ ဖယ်ရှားပြီးပါပြီ: `{dev_id}`", parse_mode="Markdown")

# ==================== RUN TELEGRAM BOT IN BACKGROUND THREAD ====================
def run_telegram_bot():
    if TELEGRAM_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN" or not TELEGRAM_TOKEN:
        print("⚠️ Telegram Token မထည့်ထားပါ။")
        return
    
    try:
        application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("addadmin", add_admin))
        application.add_handler(CommandHandler("deladmin", del_admin))
        application.add_handler(CommandHandler("listadmins", list_admins))
        application.add_handler(CommandHandler("addvip", add_vip))
        application.add_handler(CommandHandler("delvip", del_vip))
        
        print("🤖 Management Telegram Bot ကို Background တွင် စတင်လည်ပတ်နေပါပြီ...")
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

    if int(user_id) == OWNER_ID or device_id == "xdev_gg2bj8omwskmu282byb":
        system_instruction = "You are Xinon AI, an elite, highly respectful personal assistant to your Creator and Boss..."
        safety_settings = [
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        ]
    elif is_vip(device_id):
        system_instruction = "You are Xinon AI, a premium assistant for VIP users..."
        safety_settings = [
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        ]
    else:
        system_instruction = "You are Xinon AI, a standard helpful assistant..."
        safety_settings = []

    contents = [prompt] if prompt else []
    if file_data:
        contents.append(file_data)

    def generate():
        try:
            response = client.models.generate_content_stream(
                model='gemini-3.6-flash',
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

if __name__ == '__main__':
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()

    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

