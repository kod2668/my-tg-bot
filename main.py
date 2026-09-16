import os
import sqlite3
from flask import Flask, request, jsonify, Response, stream_with_context, render_template, redirect, url_for, session
from flask_cors import CORS
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
from google import genai
from google.genai import types

# Initialize Flask with templates folder
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
CORS(app)

# ==================== WEB UI ROUTES ====================
@app.route('/')
def home():
    if 'user' in session:
        return redirect(url_for('chat'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect(url_for('chat'))
        
    if request.method == 'POST':
        email = request.form.get('email') or request.form.get('username')
        if email:
            session['user'] = email
            return redirect(url_for('chat'))
        else:
            return render_template('login.html', error="ကျေးဇူးပြု၍ အချက်အလက်ဖြည့်ပါ")
            
    return render_template('login.html')

@app.route('/auth/google/callback', methods=['POST'])
def google_callback():
    try:
        # Google Sign-In ကနေ ပို့လိုက်တဲ့ Token ကို လက်ခံခြင်း
        token = request.form.get('credential')
        if token:
            # လိုအပ်ပါက token verification ထည့်နိုင်သည်၊ လက်တလောတွင် session စတင်ပေးသည်
            session['user'] = "Google User"
        return redirect(url_for('chat'))
    except Exception as e:
        return redirect(url_for('login'))

@app.route('/chat')
def chat():
    if 'user' not in session:
        return redirect(url_for('home'))
    return render_template('chat.html', user=session['user'])

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('home'))


# ==================== BACKEND API & TELEGRAM BOT ====================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
OWNER_ID = 7094887417

client = genai.Client(api_key=GEMINI_API_KEY)

def init_db():
    conn = sqlite3.connect("xinon_users.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vips (
            device_id TEXT PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()

init_db()

def is_vip(device_id: str) -> bool:
    if not device_id:
        return False
    conn = sqlite3.connect("xinon_users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM vips WHERE device_id = ?", (device_id,))
    res = cursor.fetchone()
    conn.close()
    return res is not None

# Telegram Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id == OWNER_ID:
        await update.message.reply_text("👑 မင်္ဂလာပါ Boss (Owner)။ Xinon AI စနစ် အဆင်သင့် ဖြစ်ပါပြီခင်ဗျ။")
    else:
        await update.message.reply_text("✨ Xinon AI သို့ ကြိုဆိုပါတယ်။ VIP အဆင့်မြှင့်တင်ရန် Device ID ပေးပို့ပါ။")

async def add_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ ဒါက Boss သီးသန့် အမိန့်ပေးရမယ့် ကိစ္စပါခင်ဗျ။")
        return
    if not context.args:
        await update.message.reply_text("⚠️ ဥပမာ - /addvip [Device_ID]")
        return
    
    dev_id = context.args[0]
    conn = sqlite3.connect("xinon_users.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO vips (device_id) VALUES (?)", (dev_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ VIP အဖြစ် အောင်မြင်စွာ ထည့်သွင်းပြီးပါပြီ Boss: {dev_id}")

@app.route('/api/chat', methods=['POST'])
def api_chat():
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
        tier = "boss"
    elif is_vip(device_id):
        tier = "vip"
    else:
        tier = "free"

    if tier == "boss":
        system_instruction = "You are Xinon AI, an elite, highly respectful personal assistant to your Creator and Boss..."
        safety_settings = [
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        ]
    elif tier == "vip":
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
                model='gemini-2.5-flash',
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
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
