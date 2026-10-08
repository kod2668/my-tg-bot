import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

import psycopg
from flask import Flask, Response, jsonify, request, stream_with_context
from flask_cors import CORS
from google import genai
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from google.genai import types

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.getenv("DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_CLIENT_ID = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
OWNER_GOOGLE_SUB = (os.getenv("OWNER_GOOGLE_SUB") or "").strip()
SECRET_KEY = (os.getenv("SECRET_KEY") or "").strip()

ACCESS_TOKEN_DAYS = 30
ACCOUNT_DELETE_COOLDOWN_DAYS = 2
MAX_PROMPT_LENGTH = 20000
MAX_FILE_BYTES = 15 * 1024 * 1024

CODE_KEYWORDS = [
    "code", "python", "html", "javascript", "script",
    "program", "function", "source", "ကုဒ်", "ရေးပေး", "ရေးပြ"
]


def get_pg_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is missing")
    return psycopg.connect(DATABASE_URL)


def utc_now():
    return datetime.now(timezone.utc)


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def json_error(message, status=400):
    return jsonify({"error": message}), status


def init_db():
    if not DATABASE_URL:
        print("WARNING: DATABASE_URL is missing.")
        return

    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id BIGSERIAL PRIMARY KEY,
                    google_sub TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS auth_tokens (
                    token_hash TEXT PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    expires_at TIMESTAMPTZ NOT NULL,
                    revoked_at TIMESTAMPTZ
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_auth_tokens_user
                ON auth_tokens(user_id)
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_auth_tokens_expiry
                ON auth_tokens(expires_at)
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS deleted_google_accounts (
                    google_sub TEXT PRIMARY KEY,
                    email TEXT NOT NULL DEFAULT '',
                    deleted_at TIMESTAMPTZ NOT NULL,
                    available_at TIMESTAMPTZ NOT NULL
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_deleted_accounts_available
                ON deleted_google_accounts(available_at)
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title TEXT NOT NULL DEFAULT 'New chat',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversations_owner
                ON conversations(user_id, updated_at DESC)
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id BIGSERIAL PRIMARY KEY,
                    conversation_id BIGINT NOT NULL
                        REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                ON messages(conversation_id, created_at ASC, id ASC)
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS google_vips (
                    google_sub TEXT PRIMARY KEY,
                    expiry_date TIMESTAMPTZ NOT NULL
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_google_vips_expiry
                ON google_vips(expiry_date)
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS google_admins (
                    google_sub TEXT PRIMARY KEY
                )
            """)

            # Compatibility changes for databases created by the older main.py.
            # Old email/password rows remain readable but are no longer used for login.
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS google_sub TEXT")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name TEXT NOT NULL DEFAULT ''")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")
            cur.execute("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub ON users(google_sub) WHERE google_sub IS NOT NULL")

            # Old conversations used device_id as part of ownership. Native auth now
            # uses the authenticated Google-linked user_id, so the legacy column may
            # remain for compatibility but must no longer be required.
            cur.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS device_id TEXT")
            cur.execute("ALTER TABLE conversations ALTER COLUMN device_id DROP NOT NULL")

            cur.execute("""
                DELETE FROM auth_tokens
                WHERE expires_at < NOW() OR revoked_at IS NOT NULL
            """)

            cur.execute("""
                DELETE FROM deleted_google_accounts
                WHERE available_at <= NOW()
            """)

        conn.commit()


try:
    init_db()
except Exception as exc:
    print(f"WARNING: Database initialization failed: {exc}")


def verify_google_token(raw_token):
    if not raw_token:
        return None, "Google ID token is missing."
    if not GOOGLE_CLIENT_ID:
        return None, "GOOGLE_CLIENT_ID environment variable is missing on server."

    try:
        info = id_token.verify_oauth2_token(
            raw_token,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except Exception:
        return None, "Google authentication failed."

    if info.get("aud") != GOOGLE_CLIENT_ID:
        return None, "Google token audience is invalid."

    google_sub = str(info.get("sub") or "").strip()
    email = str(info.get("email") or "").strip().lower()
    display_name = str(
        info.get("name")
        or info.get("given_name")
        or ""
    ).strip()

    if not google_sub or not email:
        return None, "Google account information is incomplete."

    if info.get("email_verified") is not True:
        return None, "Google email is not verified."

    return {
        "google_sub": google_sub,
        "email": email,
        "display_name": display_name,
    }, None


def extract_bearer_token():
    header = (request.headers.get("Authorization") or "").strip()
    if not header.lower().startswith("bearer "):
        return None
    token = header[7:].strip()
    return token or None


def create_access_token(cur, user_id):
    raw_token = secrets.token_urlsafe(48)
    token_hash = hash_token(raw_token)
    expires_at = utc_now() + timedelta(days=ACCESS_TOKEN_DAYS)

    cur.execute("""
        INSERT INTO auth_tokens(token_hash, user_id, expires_at)
        VALUES(%s, %s, %s)
    """, (token_hash, user_id, expires_at))

    return raw_token, expires_at


def revoke_access_token(raw_token):
    if not raw_token or not DATABASE_URL:
        return
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE auth_tokens
                SET revoked_at = NOW()
                WHERE token_hash = %s AND revoked_at IS NULL
            """, (hash_token(raw_token),))
        conn.commit()


def get_authenticated_user():
    raw_token = extract_bearer_token()
    if not raw_token:
        return None, json_error("Authentication required.", 401)

    if not DATABASE_URL:
        return None, json_error("Database is unavailable.", 500)

    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT u.id, u.google_sub, u.email, u.display_name,
                           u.created_at, t.expires_at
                    FROM auth_tokens t
                    INNER JOIN users u ON u.id = t.user_id
                    WHERE t.token_hash = %s
                      AND t.revoked_at IS NULL
                      AND t.expires_at > NOW()
                """, (hash_token(raw_token),))
                row = cur.fetchone()

        if not row:
            return None, json_error("Invalid or expired session.", 401)

        return {
            "id": row[0],
            "google_sub": row[1],
            "email": row[2],
            "display_name": row[3] or "",
            "created_at": row[4],
            "token_expires_at": row[5],
        }, None
    except Exception as exc:
        return None, json_error(f"Authentication lookup failed: {exc}", 500)


def get_deleted_account_status(cur, google_sub):
    cur.execute("""
        SELECT available_at
        FROM deleted_google_accounts
        WHERE google_sub = %s
    """, (google_sub,))
    row = cur.fetchone()
    if not row:
        return None
    return row[0]


def ensure_user_from_google(identity):
    google_sub = identity["google_sub"]
    email = identity["email"]
    display_name = identity["display_name"]

    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            available_at = get_deleted_account_status(cur, google_sub)
            if available_at:
                if available_at > utc_now():
                    return None, {
                        "cooldown": True,
                        "available_at": available_at,
                    }
                cur.execute(
                    "DELETE FROM deleted_google_accounts WHERE google_sub = %s",
                    (google_sub,),
                )

            cur.execute("""
                SELECT id, google_sub, email, display_name, created_at
                FROM users
                WHERE google_sub = %s
            """, (google_sub,))
            row = cur.fetchone()

            if row:
                cur.execute("""
                    UPDATE users
                    SET email = %s, display_name = %s, updated_at = NOW()
                    WHERE id = %s
                """, (email, display_name, row[0]))
                user = {
                    "id": row[0],
                    "google_sub": row[1],
                    "email": email,
                    "display_name": display_name,
                    "created_at": row[4],
                }
            else:
                cur.execute("""
                    INSERT INTO users(google_sub, email, display_name)
                    VALUES(%s, %s, %s)
                    RETURNING id, google_sub, email, display_name, created_at
                """, (google_sub, email, display_name))
                row = cur.fetchone()
                user = {
                    "id": row[0],
                    "google_sub": row[1],
                    "email": row[2],
                    "display_name": row[3] or "",
                    "created_at": row[4],
                }

            access_token, expires_at = create_access_token(cur, user["id"])
        conn.commit()

    user["token_expires_at"] = expires_at
    return {
        "user": user,
        "access_token": access_token,
        "expires_at": expires_at,
    }, None


@app.route('/api/auth/google', methods=['POST'])
def api_google_auth():
    data = request.get_json(silent=True) or {}
    raw_token = str(data.get("id_token") or data.get("token") or "").strip()

    identity, error = verify_google_token(raw_token)
    if error:
        return json_error(error, 401)

    try:
        result, error_info = ensure_user_from_google(identity)
        if error_info and error_info.get("cooldown"):
            return jsonify({
                "success": False,
                "deleted": True,
                "cooldown": True,
                "available_at": error_info["available_at"].isoformat(),
                "message": "❌ Your account has been deleted. Please try again after 2 days.",
            }), 403

        user = result["user"]
        return jsonify({
            "success": True,
            "access_token": result["access_token"],
            "expires_at": result["expires_at"].isoformat(),
            "user": {
                "id": user["id"],
                "google_sub": user["google_sub"],
                "email": user["email"],
                "display_name": user["display_name"],
                "member_since": user["created_at"].isoformat() if user["created_at"] else None,
                "is_owner": is_owner_identity(user["google_sub"]),
                "is_vip": is_vip(user["google_sub"]),
                "vip_expiry": get_vip_expiry(user["google_sub"]),
            },
        })
    except psycopg.errors.UniqueViolation:
        return json_error("That Google account is already linked to another account.", 409)
    except Exception as exc:
        return json_error(f"Google sign-in failed: {exc}", 500)


@app.route('/api/me', methods=['GET'])
def api_me():
    user, error_response = get_authenticated_user()
    if error_response:
        return error_response

    return jsonify({
        "authenticated": True,
        "user": {
            "id": user["id"],
            "google_sub": user["google_sub"],
            "email": user["email"],
            "display_name": user["display_name"],
            "member_since": user["created_at"].isoformat() if user["created_at"] else None,
            "is_owner": is_owner_identity(user["google_sub"]),
            "is_vip": is_vip(user["google_sub"]),
            "vip_expiry": get_vip_expiry(user["google_sub"]),
        },
    })


@app.route('/api/logout', methods=['POST'])
def api_logout():
    raw_token = extract_bearer_token()
    if raw_token:
        try:
            revoke_access_token(raw_token)
        except Exception as exc:
            print(f"WARNING: Logout token revoke failed: {exc}")
    return jsonify({"success": True})


@app.route('/api/delete_account', methods=['DELETE', 'POST'])
def api_delete_account():
    user, error_response = get_authenticated_user()
    if error_response:
        return error_response

    google_sub = user["google_sub"]
    if is_owner_identity(google_sub):
        return json_error("The owner account cannot be deleted from the User App.", 403)

    now = utc_now()
    available_at = now + timedelta(days=ACCOUNT_DELETE_COOLDOWN_DAYS)
    raw_token = extract_bearer_token()

    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO deleted_google_accounts
                        (google_sub, email, deleted_at, available_at)
                    VALUES(%s, %s, %s, %s)
                    ON CONFLICT(google_sub) DO UPDATE
                    SET email = EXCLUDED.email,
                        deleted_at = EXCLUDED.deleted_at,
                        available_at = EXCLUDED.available_at
                """, (google_sub, user["email"], now, available_at))

                cur.execute("DELETE FROM google_vips WHERE google_sub = %s", (google_sub,))
                cur.execute("DELETE FROM google_admins WHERE google_sub = %s", (google_sub,))
                cur.execute("DELETE FROM users WHERE id = %s", (user["id"],))

                if raw_token:
                    cur.execute("DELETE FROM auth_tokens WHERE token_hash = %s", (hash_token(raw_token),))
            conn.commit()

        return jsonify({
            "success": True,
            "deleted": True,
            "cooldown_days": ACCOUNT_DELETE_COOLDOWN_DAYS,
            "available_at": available_at.isoformat(),
            "message": "Account deleted. The same Google account can be used again after 2 days.",
        })
    except Exception as exc:
        return json_error(f"Could not delete account: {exc}", 500)


def make_chat_title(prompt):
    title = " ".join((prompt or "").strip().split())
    if not title:
        return "New chat"
    if len(title) > 55:
        return title[:55].rstrip() + "..."
    return title


def conversation_belongs_to_user(cur, conversation_id, user_id):
    cur.execute("""
        SELECT id
        FROM conversations
        WHERE id = %s AND user_id = %s
    """, (conversation_id, user_id))
    return cur.fetchone() is not None


@app.route('/api/conversations', methods=['GET'])
def api_conversations():
    user, error_response = get_authenticated_user()
    if error_response:
        return error_response

    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, title, created_at, updated_at
                    FROM conversations
                    WHERE user_id = %s
                    ORDER BY updated_at DESC
                    LIMIT 100
                """, (user["id"],))
                rows = cur.fetchall()

        return jsonify({
            "conversations": [
                {
                    "id": row[0],
                    "title": row[1],
                    "created_at": row[2].isoformat() if row[2] else None,
                    "updated_at": row[3].isoformat() if row[3] else None,
                }
                for row in rows
            ]
        })
    except Exception as exc:
        return json_error(f"Could not load chat history: {exc}", 500)


@app.route('/api/conversations/<int:conversation_id>/messages', methods=['GET'])
def api_conversation_messages(conversation_id):
    user, error_response = get_authenticated_user()
    if error_response:
        return error_response

    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                if not conversation_belongs_to_user(cur, conversation_id, user["id"]):
                    return json_error("Conversation not found.", 404)

                cur.execute("""
                    SELECT id, role, content, created_at
                    FROM messages
                    WHERE conversation_id = %s
                    ORDER BY created_at ASC, id ASC
                """, (conversation_id,))
                rows = cur.fetchall()

        return jsonify({
            "conversation_id": conversation_id,
            "messages": [
                {
                    "id": row[0],
                    "role": row[1],
                    "content": row[2],
                    "created_at": row[3].isoformat() if row[3] else None,
                }
                for row in rows
            ],
        })
    except Exception as exc:
        return json_error(f"Could not load messages: {exc}", 500)


@app.route('/api/conversations/<int:conversation_id>', methods=['DELETE'])
def api_delete_conversation(conversation_id):
    user, error_response = get_authenticated_user()
    if error_response:
        return error_response

    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM conversations
                    WHERE id = %s AND user_id = %s
                """, (conversation_id, user["id"]))
                if cur.rowcount == 0:
                    return json_error("Conversation not found.", 404)
            conn.commit()
        return jsonify({"success": True})
    except Exception as exc:
        return json_error(f"Could not delete conversation: {exc}", 500)


def create_conversation(user_id, prompt):
    title = make_chat_title(prompt)
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO conversations(user_id, title)
                VALUES(%s, %s)
                RETURNING id, title
            """, (user_id, title))
            row = cur.fetchone()
        conn.commit()
    return row[0], row[1]


def save_message(conversation_id, user_id, role, content):
    if not content:
        return

    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            if not conversation_belongs_to_user(cur, conversation_id, user_id):
                raise ValueError("Conversation does not belong to this user")

            cur.execute("""
                INSERT INTO messages(conversation_id, role, content)
                VALUES(%s, %s, %s)
            """, (conversation_id, role, content))

            cur.execute("""
                UPDATE conversations
                SET updated_at = NOW()
                WHERE id = %s
            """, (conversation_id,))
        conn.commit()


def is_owner_identity(google_sub):
    return bool(google_sub and OWNER_GOOGLE_SUB and google_sub == OWNER_GOOGLE_SUB)


def clean_expired_vips():
    if not DATABASE_URL:
        return
    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM google_vips WHERE expiry_date < NOW()")
            conn.commit()
    except Exception as exc:
        print(f"WARNING: VIP cleanup failed: {exc}")


def get_vip_expiry(google_sub):
    if not google_sub or not DATABASE_URL:
        return None
    try:
        clean_expired_vips()
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT expiry_date
                    FROM google_vips
                    WHERE google_sub = %s AND expiry_date >= NOW()
                """, (google_sub,))
                row = cur.fetchone()
        return row[0].isoformat() if row and row[0] else None
    except Exception as exc:
        print(f"WARNING: VIP lookup failed: {exc}")
        return None


def is_vip(google_sub):
    return get_vip_expiry(google_sub) is not None


def is_admin_identity(google_sub):
    if is_owner_identity(google_sub):
        return True
    if not google_sub or not DATABASE_URL:
        return False
    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM google_admins WHERE google_sub = %s",
                    (google_sub,),
                )
                return cur.fetchone() is not None
    except Exception as exc:
        print(f"WARNING: Admin lookup failed: {exc}")
        return False


def require_admin():
    user, error_response = get_authenticated_user()
    if error_response:
        return None, error_response
    if not is_admin_identity(user["google_sub"]):
        return None, json_error("Admin access required.", 403)
    return user, None


def require_owner():
    user, error_response = get_authenticated_user()
    if error_response:
        return None, error_response
    if not is_owner_identity(user["google_sub"]):
        return None, json_error("Owner access required.", 403)
    return user, None


def find_registered_user(cur, google_sub):
    cur.execute("""
        SELECT id, google_sub, email, display_name, created_at
        FROM users
        WHERE google_sub = %s
    """, (google_sub,))
    return cur.fetchone()


@app.route('/api/admin/check', methods=['GET'])
def api_admin_check():
    user, error_response = get_authenticated_user()
    if error_response:
        return error_response
    return jsonify({
        "is_admin": is_admin_identity(user["google_sub"]),
        "is_owner": is_owner_identity(user["google_sub"]),
    })


@app.route('/api/admin/add_admin', methods=['POST'])
def api_admin_add_admin():
    _, error_response = require_owner()
    if error_response:
        return error_response

    data = request.get_json(silent=True) or {}
    google_sub = str(data.get("google_sub") or "").strip()
    if not google_sub:
        return json_error("Missing google_sub.")

    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                if find_registered_user(cur, google_sub) is None:
                    return json_error("That Google account is not registered in Xinon AI.", 404)
                cur.execute("""
                    INSERT INTO google_admins(google_sub)
                    VALUES(%s)
                    ON CONFLICT(google_sub) DO NOTHING
                """, (google_sub,))
            conn.commit()
        return jsonify({"success": True})
    except Exception as exc:
        return json_error(str(exc), 500)


@app.route('/api/admin/remove_admin', methods=['POST'])
def api_admin_remove_admin():
    _, error_response = require_owner()
    if error_response:
        return error_response

    data = request.get_json(silent=True) or {}
    google_sub = str(data.get("google_sub") or "").strip()
    if not google_sub:
        return json_error("Missing google_sub.")
    if google_sub == OWNER_GOOGLE_SUB:
        return json_error("The owner cannot be removed from owner access.")

    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM google_admins WHERE google_sub = %s", (google_sub,))
            conn.commit()
        return jsonify({"success": True})
    except Exception as exc:
        return json_error(str(exc), 500)


@app.route('/api/admin/list_admins', methods=['GET'])
def api_admin_list_admins():
    _, error_response = require_admin()
    if error_response:
        return error_response

    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT a.google_sub, u.email, u.display_name
                    FROM google_admins a
                    LEFT JOIN users u ON u.google_sub = a.google_sub
                    ORDER BY u.email NULLS LAST, a.google_sub
                """)
                rows = cur.fetchall()
        return jsonify({
            "admins": [
                {
                    "google_sub": row[0],
                    "email": row[1] or "",
                    "display_name": row[2] or "",
                }
                for row in rows
            ],
            "owner_google_sub": OWNER_GOOGLE_SUB,
        })
    except Exception as exc:
        return json_error(str(exc), 500)


@app.route('/api/admin/add_vip', methods=['POST'])
def api_admin_add_vip():
    _, error_response = require_admin()
    if error_response:
        return error_response

    data = request.get_json(silent=True) or {}
    google_sub = str(data.get("google_sub") or "").strip()
    try:
        days = int(data.get("days", 30))
    except (TypeError, ValueError):
        return json_error("days must be an integer.")

    if not google_sub:
        return json_error("Missing google_sub.")
    if days <= 0 or days > 3650:
        return json_error("days must be between 1 and 3650.")

    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                if find_registered_user(cur, google_sub) is None:
                    return json_error("That Google account is not registered in Xinon AI.", 404)

                cur.execute("""
                    SELECT expiry_date
                    FROM google_vips
                    WHERE google_sub = %s
                """, (google_sub,))
                existing = cur.fetchone()
                base = existing[0] if existing and existing[0] > utc_now() else utc_now()
                expiry_date = base + timedelta(days=days)

                cur.execute("""
                    INSERT INTO google_vips(google_sub, expiry_date)
                    VALUES(%s, %s)
                    ON CONFLICT(google_sub) DO UPDATE
                    SET expiry_date = EXCLUDED.expiry_date
                """, (google_sub, expiry_date))
            conn.commit()
        return jsonify({"success": True, "expiry_date": expiry_date.isoformat()})
    except Exception as exc:
        return json_error(str(exc), 500)


@app.route('/api/admin/remove_vip', methods=['POST'])
def api_admin_remove_vip():
    _, error_response = require_admin()
    if error_response:
        return error_response

    data = request.get_json(silent=True) or {}
    google_sub = str(data.get("google_sub") or "").strip()
    if not google_sub:
        return json_error("Missing google_sub.")

    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM google_vips WHERE google_sub = %s", (google_sub,))
            conn.commit()
        return jsonify({"success": True})
    except Exception as exc:
        return json_error(str(exc), 500)


@app.route('/api/admin/list_vips', methods=['GET'])
def api_admin_list_vips():
    _, error_response = require_admin()
    if error_response:
        return error_response

    try:
        clean_expired_vips()
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT v.google_sub, u.email, u.display_name, v.expiry_date
                    FROM google_vips v
                    LEFT JOIN users u ON u.google_sub = v.google_sub
                    WHERE v.expiry_date >= NOW()
                    ORDER BY v.expiry_date ASC
                """)
                rows = cur.fetchall()

        return jsonify({
            "vips": [
                {
                    "google_sub": row[0],
                    "email": row[1] or "",
                    "display_name": row[2] or "",
                    "expiry_date": row[3].isoformat() if row[3] else None,
                }
                for row in rows
            ]
        })
    except Exception as exc:
        return json_error(str(exc), 500)


@app.route('/api/admin/user_stats', methods=['GET'])
def api_admin_user_stats():
    _, error_response = require_admin()
    if error_response:
        return error_response

    try:
        clean_expired_vips()
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM users")
                total_users = cur.fetchone()[0]
                cur.execute("""
                    SELECT COUNT(*)
                    FROM google_vips v
                    INNER JOIN users u ON u.google_sub = v.google_sub
                    WHERE v.expiry_date >= NOW()
                """)
                vip_users = cur.fetchone()[0]

        return jsonify({
            "total_users": total_users,
            "free_users": max(0, total_users - vip_users),
            "vip_users": vip_users,
        })
    except Exception as exc:
        return json_error(f"Could not load user statistics: {exc}", 500)


@app.route('/api/chat', methods=['POST'])
def api_chat():
    user, error_response = get_authenticated_user()
    if error_response:
        return Response("[Error: Authentication required.]", mimetype="text/plain", status=401)

    if not GEMINI_API_KEY:
        return Response(
            "[Error: GEMINI_API_KEY environment variable is missing on server.]",
            mimetype="text/plain",
            status=500,
        )

    client = genai.Client(api_key=GEMINI_API_KEY)

    if request.files:
        prompt = (request.form.get("prompt") or "").strip()
        conversation_id = request.form.get("conversation_id", type=int)
        uploaded = request.files.get("image") or request.files.get("file")
        file_data = None

        if uploaded:
            image_bytes = uploaded.read()
            if len(image_bytes) > MAX_FILE_BYTES:
                return Response("[Error: File is too large.]", mimetype="text/plain", status=413)
            mime_type = uploaded.content_type or "application/octet-stream"
            file_data = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    else:
        data = request.get_json(silent=True) or {}
        prompt = str(data.get("prompt") or "").strip()
        conversation_id = data.get("conversation_id")
        file_data = None
        try:
            conversation_id = int(conversation_id) if conversation_id else None
        except (TypeError, ValueError):
            conversation_id = None

    if len(prompt) > MAX_PROMPT_LENGTH:
        return Response("[Error: Prompt is too long.]", mimetype="text/plain", status=413)

    try:
        if conversation_id:
            with get_pg_connection() as conn:
                with conn.cursor() as cur:
                    if not conversation_belongs_to_user(cur, conversation_id, user["id"]):
                        return Response("[Error: Conversation not found.]", mimetype="text/plain", status=404)
        else:
            conversation_id, _ = create_conversation(user["id"], prompt)
    except Exception as exc:
        return Response(
            f"[Error: PostgreSQL chat history is unavailable: {exc}]",
            mimetype="text/plain",
            status=500,
        )

    try:
        if prompt:
            save_message(conversation_id, user["id"], "user", prompt)
    except Exception as exc:
        return Response(
            f"[Error saving chat message: {exc}]",
            mimetype="text/plain",
            status=500,
        )

    google_sub = user["google_sub"]
    owner = is_owner_identity(google_sub)
    vip = is_vip(google_sub)

    is_asking_for_code = any(keyword in prompt.lower() for keyword in CODE_KEYWORDS)
    if not owner and not vip and is_asking_for_code:
        restricted_text = (
            "❌ **Access Denied:** Free user များအနေဖြင့် AI ဆီမှ Code များကို "
            "တောင်းခံခွင့်မရှိပါ။ Code များ ရေးခိုင်းနိုင်ရန် VIP အဆင့်သို့ Upgrade ပြုလုပ်ပါ။"
        )
        try:
            save_message(conversation_id, user["id"], "assistant", restricted_text)
        except Exception:
            pass

        return Response(
            stream_with_context(iter([restricted_text])),
            mimetype="text/plain",
            headers={"X-Conversation-Id": str(conversation_id)},
        )

    if owner:
        model_name = "gemini-3.5-flash-lite"
        system_instruction = (
            "You are Xinon AI, an elite, highly respectful personal assistant "
            "to your Creator and Boss..."
        )
        safety_settings = [
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        ]
    elif vip:
        model_name = "gemini-3.5-flash-lite"
        system_instruction = (
            "You are Xinon AI, a premium and advanced assistant for VIP users, "
            "providing deep analytical, highly accurate, and professional responses..."
        )
        safety_settings = [
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        ]
    else:
        model_name = "gemini-3.1-flash-lite"
        system_instruction = "You are Xinon AI, a standard helpful assistant..."
        safety_settings = []

    contents = []
    if prompt:
        contents.append(prompt)
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
                    safety_settings=safety_settings or None,
                ),
            )

            for chunk in response:
                if chunk.text:
                    full_ai_text += chunk.text
                    yield chunk.text

            if full_ai_text:
                try:
                    save_message(conversation_id, user["id"], "assistant", full_ai_text)
                except Exception as save_error:
                    print(f"WARNING: Could not save AI response: {save_error}")
        except Exception as exc:
            error_text = f"\n[Error: {exc}]"
            yield error_text
            try:
                save_message(conversation_id, user["id"], "assistant", error_text)
            except Exception:
                pass

    return Response(
        stream_with_context(generate()),
        mimetype="text/plain",
        headers={"X-Conversation-Id": str(conversation_id)},
    )


@app.get('/api/health')
def api_health():
    return jsonify({"ok": True, "service": "xinon-ai"})


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)