import subprocess
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ၁။ Telegram Bot Token ကို ဒီမှာ ထည့်ပါ
TOKEN = "8854987165:AAHEUTH2wL26WrG-cYR3UDd5IyCZa4ZA6gE"

# Local AI ဆီက အဖြေတောင်းမည့် Function
def ask_local_ai(prompt):
    cmd = [
        "./build/bin/llama-cli",
        "-m", "model.gguf",
        "-p", f"You are a helpful assistant. User: {prompt}\nAI:",
        "-n", "128",
        "--temp", "0.7"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd="/data/data/com.termux/files/home/llama.cpp")
    
    # AI ပြန်ဖြေတဲ့ စာသားကို ခွဲထုတ်ခြင်း
    output = result.stdout
    if "AI:" in output:
        return output.split("AI:")[-1].strip()
    return output

# /start command အတွက်
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("မင်္ဂလာပါ။ ဖုန်းထဲက Local AI Bot မှ ကြိုဆိုပါတယ်။ ဘာမေးချင်ပါသလဲ?")

# စာပို့လိုက်တိုင်း AI က ပြန်ဖြေပေးမည့် Function
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await update.message.reply_text("AI စဉ်းစားနေသည်...")
    
    ai_response = ask_local_ai(user_text)
    await update.message.reply_text(ai_response)

if __name__ == '__main__':


    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Telegram Bot စတင်ပွင့်နေပါပြီ...")
    app.run_polling()
