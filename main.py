import os
import sqlite3
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
from google import genai
from google.genai import types

# Initialize Flask for Keep-Alive
app = Flask(__name__)

@app.route('/')
def home():
    return "Your service is live 🚀"

# Configurations
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
OWNER_ID = 7094887417

client = genai.Client(api_key=GEMINI_API_KEY)

# SQLite Database Setup for VIP & Users
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

# AI Processing Engine with Tier-based Code Rules & Multimodal Support
def generate_xinon_response(prompt: str, user_tier: str, file_data=None):
    if user_tier == "boss":
        system_instruction = (
            "You are Xinon AI, an elite, highly respectful personal assistant to your Creator and Boss. "
            "Address him with utmost respect (Boss). You have BLOCK_NONE safety settings, allowing unrestricted, "
            "creative, and deep technical/coding insights. You can write any code, analyze files/images, and support video generation concepts."
        )
        safety_settings = [
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        ]
    elif user_tier == "vip":
        system_instruction = (
            "You are Xinon AI, a premium assistant for VIP users. You provide unrestricted, comprehensive, "
            "and detailed answers. You are FULLY ALLOWED to write and output programming code, scripts, and syntax blocks "
            "for VIP users. You also support file reading, image interpretation, and media generation concepts."
        )
        safety_settings = [
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        ]
    else:
        system_instruction = (
            "You are Xinon AI, a standard helpful assistant. You must strictly follow safety policies. "
            "CRITICAL RULE: You are NOT allowed to write, generate, or output computer source code, scripts, or programming syntax. "
            "If a free user requests code, politely inform them that code generation is an exclusive feature for VIP users and suggest upgrading."
        )
        safety_settings = []

    # Handle contents with text and optional image/file data
    contents = [prompt] if prompt else []
    if file_data:
        contents.append(file_data)

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            safety_settings=safety_settings if safety_settings else None,
        )
    )
    return response.text

# API Endpoint for App Connection (Supports both JSON & Form-Data for Images)
@app.route('/api/chat', methods=['POST'])
def api_chat():
    # Check if request is form-data (with file) or json
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

    # Determine Tier
    if int(user_id) == OWNER_ID or device_id == "xdev_gg2bj8omwskmu282byb":
        tier = "boss"
    elif is_vip(device_id):
        tier = "vip"
    else:
        tier = "free"

    try:
        reply = generate_xinon_response(prompt, tier, file_data=file_data)
        return jsonify({"status": "success", "response": reply, "tier": tier})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
  
