import os
from datetime import datetime, timedelta, timezone

import psycopg
from flask import (
    Flask, request, jsonify, Response, stream_with_context,
    render_template, redirect, url_for
)
from flask_cors import CORS
from google import genai
from google.genai import types

# Initialize Flask with templates folder
app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app)

# ==================== CONFIGURATIONS ====================
OWNER_ID = 7094887417
OWNER_DEVICE_ID = "055f419d68dab9df"

# Railway PostgreSQL connection
DATABASE_URL = os.getenv("DATABASE_URL")


# ==================== WEB UI ROUTES ====================
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/chat')
def chat_page():
    return render_template('chat.html')


# ==================== POSTGRES CONNECTION ====================
def get_pg_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is missing")
    return psycopg.connect(DATABASE_URL)


# ==================== VIP & ADMIN POSTGRES DATABASE ====================
def init_vip_admin_db():
    """Create PostgreSQL tables used by VIP/Admin management."""
    if not DATABASE_URL:
        print("WARNING: DATABASE_URL is missing; VIP/Admin storage is disabled.")
        return

    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS vips (
                        device_id TEXT PRIMARY KEY,
                        expiry_date TIMESTAMP NOT NULL
                    )
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS admins (
                        admin_id BIGINT PRIMARY KEY
                    )
                """)

            conn.commit()

        print("PostgreSQL VIP/Admin database initialized.")
    except Exception as e:
        print(f"WARNING: PostgreSQL VIP/Admin initialization failed: {e}")


init_vip_admin_db()


# ==================== POSTGRES CHAT HISTORY ====================
def init_chat_db():
    """Create PostgreSQL tables used by Xinon AI chat history."""
    if not DATABASE_URL:
        print("WARNING: DATABASE_URL is missing; chat history is disabled.")
        return

    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS conversations (
                        id BIGSERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        device_id TEXT NOT NULL,
                        title TEXT NOT NULL DEFAULT 'New chat',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id BIGSERIAL PRIMARY KEY,
                        conversation_id BIGINT NOT NULL
                            REFERENCES conversations(id) ON DELETE CASCADE,
                        role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                        content TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_conversations_owner
                    ON conversations (user_id, device_id, updated_at DESC)
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_messages_conversation
                    ON messages (conversation_id, created_at ASC)
                """)

            conn.commit()

        print("PostgreSQL chat history database initialized.")
    except Exception as e:
        print(f"WARNING: PostgreSQL initialization failed: {e}")


init_chat_db()


def make_chat_title(prompt):
    """Create a short sidebar title from the first user message."""
    title = " ".join((prompt or "").strip().split())
    if not title:
        return "New chat"
    if len(title) > 55:
        return title[:55].rstrip() + "..."
    return title


def conversation_belongs_to_user(cur, conversation_id, user_id, device_id):
    cur.execute("""
        SELECT id
        FROM conversations
        WHERE id = %s AND user_id = %s AND device_id = %s
    """, (conversation_id, user_id, device_id))
    return cur.fetchone() is not None


# ==================== CHAT HISTORY API ====================
@app.route('/api/conversations', methods=['GET'])
def api_conversations():
    """Return recent conversations for the current user/device."""
    device_id = (request.args.get("device_id") or "").strip()
    user_id = request.args.get("user_id", type=int) or 0

    if not device_id:
        return jsonify({"error": "Missing device_id"}), 400

    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, title, created_at, updated_at
                    FROM conversations
                    WHERE user_id = %s AND device_id = %s
                    ORDER BY updated_at DESC
                    LIMIT 50
                """, (user_id, device_id))

                rows = cur.fetchall()

        conversations = [
            {
                "id": row[0],
                "title": row[1],
                "created_at": row[2].isoformat() if row[2] else None,
                "updated_at": row[3].isoformat() if row[3] else None
            }
            for row in rows
        ]

        return jsonify({"conversations": conversations})

    except Exception as e:
        return jsonify({"error": f"Could not load chat history: {str(e)}"}), 500


@app.route('/api/conversations/<int:conversation_id>/messages', methods=['GET'])
def api_conversation_messages(conversation_id):
    """Load all messages belonging to one conversation."""
    device_id = (request.args.get("device_id") or "").strip()
    user_id = request.args.get("user_id", type=int) or 0

    if not device_id:
        return jsonify({"error": "Missing device_id"}), 400

    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                if not conversation_belongs_to_user(
                    cur, conversation_id, user_id, device_id
                ):
                    return jsonify({"error": "Conversation not found"}), 404

                cur.execute("""
                    SELECT id, role, content, created_at
                    FROM messages
                    WHERE conversation_id = %s
                    ORDER BY created_at ASC, id ASC
                """, (conversation_id,))

                rows = cur.fetchall()

        messages = [
            {
                "id": row[0],
                "role": row[1],
                "content": row[2],
                "created_at": row[3].isoformat() if row[3] else None
            }
            for row in rows
        ]

        return jsonify({
            "conversation_id": conversation_id,
            "messages": messages
        })

    except Exception as e:
        return jsonify({"error": f"Could not load messages: {str(e)}"}), 500


@app.route('/api/conversations/<int:conversation_id>', methods=['DELETE'])
def api_delete_conversation(conversation_id):
    """Delete one conversation and its messages."""
    device_id = (request.args.get("device_id") or "").strip()
    user_id = request.args.get("user_id", type=int) or 0

    if not device_id:
        return jsonify({"error": "Missing device_id"}), 400

    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM conversations
                    WHERE id = %s AND user_id = %s AND device_id = %s
                """, (conversation_id, user_id, device_id))

                if cur.rowcount == 0:
                    return jsonify({"error": "Conversation not found"}), 404

            conn.commit()

        return jsonify({"success": True})

    except Exception as e:
        return jsonify({"error": f"Could not delete conversation: {str(e)}"}), 500


def create_conversation(user_id, device_id, prompt):
    title = make_chat_title(prompt)

    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO conversations
                    (user_id, device_id, title)
                VALUES (%s, %s, %s)
                RETURNING id, title
            """, (user_id, device_id, title))

            row = cur.fetchone()

        conn.commit()

    return row[0], row[1]


def save_message(conversation_id, user_id, device_id, role, content):
    if not content:
        return

    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            if not conversation_belongs_to_user(
                cur, conversation_id, user_id, device_id
            ):
                raise ValueError("Conversation does not belong to this user")

            cur.execute("""
                INSERT INTO messages
                    (conversation_id, role, content)
                VALUES (%s, %s, %s)
            """, (conversation_id, role, content))

            cur.execute("""
                UPDATE conversations
                SET updated_at = NOW()
                WHERE id = %s
            """, (conversation_id,))

        conn.commit()


# ==================== HELPER FUNCTIONS ====================
def is_admin(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True

    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM admins WHERE admin_id = %s",
                    (user_id,)
                )
                res = cur.fetchone()
        return res is not None
    except Exception as e:
        print(f"PostgreSQL is_admin error: {e}")
        return False


def is_vip(device_id: str) -> bool:
    if not device_id:
        return False

    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM vips WHERE device_id = %s",
                    (device_id,)
                )
                res = cur.fetchone()
        return res is not None
    except Exception as e:
        print(f"PostgreSQL is_vip error: {e}")
        return False


def clean_expired_vips():
    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM vips WHERE expiry_date < %s",
                    (datetime.now(),)
                )
            conn.commit()
    except Exception as e:
        print(f"PostgreSQL clean_expired_vips error: {e}")


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

    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO admins (admin_id)
                    VALUES (%s)
                    ON CONFLICT (admin_id) DO NOTHING
                """, (admin_id,))
            conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/remove_admin', methods=['POST'])
def api_remove_admin():
    data = request.json or {}
    admin_id = data.get('admin_id')

    if not admin_id:
        return jsonify({"error": "Missing admin_id"}), 400

    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM admins WHERE admin_id = %s",
                    (admin_id,)
                )
            conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/list_admins', methods=['GET'])
def api_list_admins():
    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT admin_id FROM admins ORDER BY admin_id")
                admins = [row[0] for row in cur.fetchall()]
        return jsonify({"admins": admins})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/add_vip', methods=['POST'])
def api_add_vip():
    data = request.json or {}
    device_id = data.get('device_id')
    days = data.get('days', 30)

    if not device_id:
        return jsonify({"error": "Missing device_id"}), 400

    expiry_date = datetime.now() + timedelta(days=int(days))
    expiry_str = expiry_date.strftime("%Y-%m-%d %H:%M:%S")

    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO vips (device_id, expiry_date)
                    VALUES (%s, %s)
                    ON CONFLICT (device_id)
                    DO UPDATE SET expiry_date = EXCLUDED.expiry_date
                """, (device_id, expiry_date))
            conn.commit()
        # Keep the exact response format expected by the Telegram bot.
        return jsonify({"success": True, "expiry_date": expiry_str})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/remove_vip', methods=['POST'])
def api_remove_vip():
    data = request.json or {}
    device_id = data.get('device_id')

    if not device_id:
        return jsonify({"error": "Missing device_id"}), 400

    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM vips WHERE device_id = %s",
                    (device_id,)
                )
            conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/list_vips', methods=['GET'])
def api_list_vips():
    clean_expired_vips()

    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT device_id, expiry_date
                    FROM vips
                    ORDER BY expiry_date ASC, device_id ASC
                """)
                rows = cur.fetchall()

        # Convert PostgreSQL timestamps to the same string format
        # previously returned by the SQLite API.
        vips = [
            (
                row[0],
                row[1].strftime("%Y-%m-%d %H:%M:%S") if row[1] else None
            )
            for row in rows
        ]
        return jsonify({"vips": vips})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== WEBVIEW APP CHAT API ROUTE ====================
@app.route('/api/chat', methods=['POST'])
def api_chat():
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return Response(
            "[Error: GEMINI_API_KEY environment variable is missing on server.]",
            mimetype='text/plain'
        )

    client = genai.Client(api_key=api_key)

    # Image/file request
    if request.files:
        device_id = request.form.get("device_id")
        prompt = request.form.get("prompt", "")
        user_id = request.form.get("user_id", 0)
        conversation_id = request.form.get("conversation_id", type=int)
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
        conversation_id = data.get("conversation_id")
        file_data = None

        try:
            conversation_id = int(conversation_id) if conversation_id else None
        except (TypeError, ValueError):
            conversation_id = None

    device_id = (device_id or "").strip()

    # User ID
    try:
        user_id_int = int(user_id) if user_id else 0
    except (TypeError, ValueError):
        user_id_int = 0

    if not device_id:
        return Response(
            "[Error: device_id is missing.]",
            mimetype='text/plain',
            status=400
        )

    # Create a conversation automatically on the first message.
    # If an existing conversation_id is supplied, verify ownership.
    try:
        if conversation_id:
            with get_pg_connection() as conn:
                with conn.cursor() as cur:
                    if not conversation_belongs_to_user(
                        cur, conversation_id, user_id_int, device_id
                    ):
                        return Response(
                            "[Error: Conversation not found.]",
                            mimetype='text/plain',
                            status=404
                        )
        else:
            conversation_id, conversation_title = create_conversation(
                user_id_int, device_id, prompt
            )
    except Exception as e:
        return Response(
            f"[Error: PostgreSQL chat history is unavailable: {str(e)}]",
            mimetype='text/plain',
            status=500
        )

    # Save the user's message before generating the answer.
    try:
        if prompt:
            save_message(
                conversation_id,
                user_id_int,
                device_id,
                "user",
                prompt
            )
    except Exception as e:
        return Response(
            f"[Error saving chat message: {str(e)}]",
            mimetype='text/plain',
            status=500
        )

    # ==================== USER ACCESS TYPE ====================
    is_owner = (device_id == OWNER_DEVICE_ID)
    user_is_vip = is_vip(device_id)

    # Free user code restriction
    code_keywords = [
        "code", "python", "html", "javascript", "script",
        "program", "function", "source", "ကုဒ်", "ရေးပေး", "ရေးပြ"
    ]

    is_asking_for_code = any(
        keyword in prompt.lower()
        for keyword in code_keywords
    )

    if not is_owner and not user_is_vip and is_asking_for_code:
        restricted_text = (
            "❌ **Access Denied:** Free user များအနေဖြင့် AI ဆီမှ Code များကို "
            "တောင်းခံခွင့်မရှိပါ။ Code များ ရေးခိုင်းနိုင်ရန် VIP အဆင့်သို့ Upgrade ပြုလုပ်ပါ။"
        )

        try:
            save_message(
                conversation_id,
                user_id_int,
                device_id,
                "assistant",
                restricted_text
            )
        except Exception:
            pass

        def restricted_generate():
            yield restricted_text

        return Response(
            stream_with_context(restricted_generate()),
            mimetype='text/plain',
            headers={"X-Conversation-Id": str(conversation_id)}
        )

    # ==================== GEMINI CHAT MODEL HANDLING ====================
    if is_owner:
        model_name = 'gemini-3.5-flash-lite'
        system_instruction = (
            "You are Xinon AI, an elite, highly respectful personal assistant "
            "to your Creator and Boss..."
        )
        safety_settings = [
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=types.HarmBlockThreshold.BLOCK_NONE
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE
            ),
        ]
    elif user_is_vip:
        model_name = 'gemini-3.5-flash-lite'
        system_instruction = (
            "You are Xinon AI, a premium and advanced assistant for VIP users, "
            "providing deep analytical, highly accurate, and professional responses..."
        )
        safety_settings = [
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=types.HarmBlockThreshold.BLOCK_NONE
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE
            ),
        ]
    else:
        model_name = 'gemini-3.1-flash-lite'
        system_instruction = "You are Xinon AI, a standard helpful assistant..."
        safety_settings = []

    contents = [prompt] if prompt else []

    if file_data:
        contents.append(file_data)

    def generate():
        full_ai_text = ""

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
                    full_ai_text += chunk.text
                    yield chunk.text

            # Save the complete AI response after streaming finishes.
            if full_ai_text:
                try:
                    save_message(
                        conversation_id,
                        user_id_int,
                        device_id,
                        "assistant",
                        full_ai_text
                    )
                except Exception as save_error:
                    print(f"WARNING: Could not save AI response: {save_error}")

        except Exception as e:
            error_text = f"\n[Error: {str(e)}]"
            yield error_text

            # Save errors too, so the conversation remains complete.
            try:
                save_message(
                    conversation_id,
                    user_id_int,
                    device_id,
                    "assistant",
                    error_text
                )
            except Exception:
                pass

    return Response(
        stream_with_context(generate()),
        mimetype='text/plain',
        headers={"X-Conversation-Id": str(conversation_id)}
    )


# ==================== MAIN ENTRY POINT ====================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
