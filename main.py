import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, Response, stream_with_context, render_template, redirect, url_for
from flask_cors import CORS
from google import genai
from google.genai import types

# Initialize Flask with templates folder
app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app)

# ==================== CONFIGURATIONS ====================
OWNER_ID = 7094887417  # Boss (Owner) သီးသန့် ID
DB_NAME = "xinon_users.db"

# ==================== WEB UI ROUTES (Login/Register များ ဖြုတ်ပြီးသား) ====================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat')
def chat_page():
    return render_template('chat.html')

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

# ==================== TELEGRAM BOT API ENDPOINTS ====================
@app.route('/api/check_admin', methods=['GET'])
def api_check_admin():
    user_id = request.args.get('user_id', type=int)
    if not user_id:
        return jsonify({"is_admin": False})
    return jsonify({"is_admin": is_admin(user_id)})

@app.route('/api/add_admin', methods=['POST'])
def api_add_admin():
    data = request.json or {}
    admin_id = data.get('admin_id')
    if not admin_id:
        return jsonify({"error": "Missing admin_id"}), 400
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR IGNORE INTO admins (admin_id) VALUES (?)", (admin_id,))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/remove_admin', methods=['POST'])
def api_remove_admin():
    data = request.json or {}
    admin_id = data.get('admin_id')
    if not admin_id:
        return jsonify({"error": "Missing admin_id"}), 400
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM admins WHERE admin_id = ?", (admin_id,))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/list_admins', methods=['GET'])
def api_list_admins():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT admin_id FROM admins")
    admins = [row[0] for row in cursor.fetchall()]
    conn.close()
    return jsonify({"admins": admins})

@app.route('/api/add_vip', methods=['POST'])
def api_add_vip():
    data = request.json or {}
    device_id = data.get('device_id')
    days = data.get('days', 30)
    if not device_id:
        return jsonify({"error": "Missing device_id"}), 400
    
    expiry_date = datetime.now() + timedelta(days=int(days))
    expiry_str = expiry_date.strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO vips (device_id, expiry_date) 
            VALUES (?, ?)
        """, (device_id, expiry_str))
        conn.commit()
        return jsonify({"success": True, "expiry_date": expiry_str})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()
import os
import sqlite3
import urllib.parse
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, Response, stream_with_context, render_template, redirect, url_for
from flask_cors import CORS
from google import genai
from google.genai import types

# Initialize Flask with templates folder
app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app)

# ==================== CONFIGURATIONS ====================
OWNER_ID = 7094887417  # Boss (Owner) သီးသန့် ID
DB_NAME = "xinon_users.db"

# ==================== WEB UI ROUTES (Login/Register များ ဖြုတ်ပြီးသား) ====================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat')
def chat_page():
    return render_template('chat.html')

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

# ==================== TELEGRAM BOT API ENDPOINTS ====================
@app.route('/api/check_admin', methods=['GET'])
def api_check_admin():
    user_id = request.args.get('user_id', type=int)
    if not user_id:
        return jsonify({"is_admin": False})
    return jsonify({"is_admin": is_admin(user_id)})

@app.route('/api/add_admin', methods=['POST'])
def api_add_admin():
    data = request.json or {}
    admin_id = data.get('admin_id')
    if not admin_id:
        return jsonify({"error": "Missing admin_id"}), 400
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR IGNORE INTO admins (admin_id) VALUES (?)", (admin_id,))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/remove_admin', methods=['POST'])
def api_remove_admin():
    data = request.json or {}
    admin_id = data.get('admin_id')
    if not admin_id:
        return jsonify({"error": "Missing admin_id"}), 400
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM admins WHERE admin_id = ?", (admin_id,))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/list_admins', methods=['GET'])
def api_list_admins():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT admin_id FROM admins")
    admins = [row[0] for row in cursor.fetchall()]
    conn.close()
    return jsonify({"admins": admins})

@app.route('/api/add_vip', methods=['POST'])
def api_add_vip():
    data = request.json or {}
    device_id = data.get('device_id')
    days = data.get('days', 30)
    if not device_id:
        return jsonify({"error": "Missing device_id"}), 400
    
    expiry_date = datetime.now() + timedelta(days=int(days))
    expiry_str = expiry_date.strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO vips (device_id, expiry_date) 
            VALUES (?, ?)
        """, (device_id, expiry_str))
        conn.commit()
        return jsonify({"success": True, "expiry_date": expiry_str})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/remove_vip', methods=['POST'])
def api_remove_vip():
    data = request.json or {}
    device_id = data.get('device_id')
    if not device_id:
        return jsonify({"error": "Missing device_id"}), 400
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM vips WHERE device_id = ?", (device_id,))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/list_vips', methods=['GET'])
def api_list_vips():
    clean_expired_vips()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT device_id, expiry_date FROM vips")
    vips = cursor.fetchall()
    conn.close()
    return jsonify({"vips": vips})

# ==================== WEBVIEW APP CHAT API ROUTE ====================
@app.route('/api/chat', methods=['POST'])
def api_chat():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return Response("[Error: GEMINI_API_KEY environment variable is missing on server.]", mimetype='text/plain')
    
    client = genai.Client(api_key=api_key)

    # ပုံ (သို့မဟုတ်) ဖိုင်ပါလာခြင်း ရှိမရှိ စစ်ဆေးခြင်း
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
    try:
        user_id_int = int(user_id) if user_id else 0
    except:
        user_id_int = 0

    is_owner = (user_id_int == OWNER_ID or device_id == "055f419d68dab9df")
    user_is_vip = is_vip(device_id)

    # Free user များ Code တောင်းခြင်း ရှိမရှိ စစ်ဆေးရန် Keywords များ
    code_keywords = ["code", "python", "html", "javascript", "script", "program", "function", "source", "ကုဒ်", "ရေးပေး", "ရေးပြ"]
    is_asking_for_code = any(keyword in prompt.lower() for keyword in code_keywords)

    if not is_owner and not user_is_vip and is_asking_for_code:
        def restricted_generate():
            yield "❌ **Access Denied:** Free user များအနေဖြင့် AI ဆီမှ Code များကို တောင်းခံခွင့်မရှိပါ။ Code များ ရေးခိုင်းနိုင်ရန် VIP အဆင့်သို့ Upgrade ပြုလုပ်ပါ။"
        return Response(stream_with_context(restricted_generate()), mimetype='text/plain')

    # ==================== AI IMAGE GENERATION HANDLING (100% Free Pollinations API) ====================
    image_keywords = ["generate", "create", "draw", "painting", "photo", "image", "img", "ပုံဖန်တီး", "ပုံဆွဲ", "ပုံထုတ်", "ပုံ"]
    is_asking_for_image = any(keyword in prompt.lower() for keyword in image_keywords)

    if is_asking_for_image and not file_data:
        def generate_image_response():
            try:
                # Prompt ကို URL အတွက် အဆင်ပြေအောင် encode လုပ်ခြင်း
                safe_prompt = urllib.parse.quote(prompt)
                
                # Pollinations.ai ကို အသုံးပြု၍ လုံးဝအခမဲ့ ပုံထုတ်ခြင်း (API Key / Card လုံးဝ မလိုပါ)
                image_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1024&height=1024&nologo=true"
                
                # Markdown ပုံစံဖြင့် Frontend သို့ တိုက်ရိုက်ထုတ်ပေးခြင်း
                yield f"![Generated Image]({image_url})\n\n✨ **Prompt:** {prompt} \n*(Powered by Free AI)*"

            except Exception as e:
                yield f"\n[Image Generation Error: {str(e)}]"
        return Response(stream_with_context(generate_image_response()), mimetype='text/plain')

    # ==================== GEMINI CHAT MODEL HANDLING (လုံးဝ မထိပါ) ====================
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
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
