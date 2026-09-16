import os
import sqlite3
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

# ==================== BACKEND API & TELEGRAM BOT ====================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
OWNER_ID = 7094887417

def init_vip_db():
    conn = sqlite3.connect("xinon_users.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vips (
            device_id TEXT PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()

init_vip_db()

def is_vip(device_id: str) -> bool:
    if not device_id:
        return False
    conn = sqlite3.connect("xinon_users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM vips WHERE device_id = ?", (device_id,))
    res = cursor.fetchone()
    conn.close()
    return res is not None

@app.route('/api/chat', methods=['POST'])
def api_chat():
    # API ခေါ်တဲ့အချိန်တိုင်းမှာ Key ကို Environment ကနေ တိုက်ရိုက်ဖတ်ပြီး Client ဆောက်မယ်
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
