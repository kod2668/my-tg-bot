import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

# 1. Render Port Check အတွက် Dummy Web Server ဖွင့်ပေးခြင်း
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    print(f"Web server running on port {port}")
    server.serve_forever()

# Background Thread ဖြင့် Web Server ကို သီးသန့် Run မည်
threading.Thread(target=run_web_server, daemon=True).start()

# 2. Telegram Bot & Groq Setup
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

groq_client = Groq(api_key=GROQ_API_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("မင်္ဂလာပါ။ AI Bot က စတင်အလုပ်လုပ်နေပါပြီ။ ဘာကူညီပေးရမလဲခင်ဗျာ။")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",  # Groq ရဲ့ အမှန်တကယ် လက်ရှိသုံးနေကျ Model နာမည်
            messages=[{"role": "user", "content": user_text}]
        )
        reply_text = completion.choices[0].message.content
        await update.message.reply_text(reply_text)
    except Exception as e:
        print(f"Groq API Error Details: {e}")
        await update.message.reply_text(f"Error: {e}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot is polling...")
    app.run_polling()
            model="llama3-70b-8192",  # Groq ရဲ့ အသုံးများတဲ့ Standard Model နာမည်သို့ ပြောင်းလိုက်သည်
            messages=[{"role": "user", "content": user_text}]
        )
        reply_text = completion.choices[0].message.content
        await update.message.reply_text(reply_text)
    except Exception as e:
        print(f"Groq API Error Details: {e}")
        await update.message.reply_text(f"Error: {e}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot is polling...")
    app.run_polling()
            model="llama-3.1-8b-instant",  # Model နာမည်အသစ် ပြောင်းထားသည်
            messages=[{"role": "user", "content": user_text}]
        )
        reply_text = completion.choices[0].message.content
        await update.message.reply_text(reply_text)
    except Exception as e:
        print(f"Groq API Error Details: {e}")  # Render Logs ထဲတွင် Error အမှန်ကို ပြရန်
        await update.message.reply_text(f"Error: {e}") # Telegram ထဲတွင် Error အမှန်ကို တိုက်ရိုက်ပြရန်

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot is polling...")
    app.run_polling()
