import os
import logging
import sqlite3
import requests
import google.generativeai as genai
from groq import Groq
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
)

logging.basicConfig(level=logging.INFO)

# ==========================================
# 🔑 فراخوانی کلیدها از Environment Variables
# ==========================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
GEMINI_KEY_1 = os.getenv("GEMINI_KEY_1", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")
GEMINI_KEY_2 = os.getenv("GEMINI_KEY_2", "")

SYSTEM_PROMPT = """
You are an expert, encouraging English teacher for a Persian-speaking student.
Rules:
1. Always correct any grammar or spelling mistakes in the user's message first under a '✏️ Correction:' section (with a short explanation in Persian).
2. Reply in simple English based on the user's level.
3. Keep your response brief (2-3 sentences) and end with a simple follow-up question.
"""

def init_db():
    conn = sqlite3.connect("english_academy.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            level TEXT DEFAULT 'A2'
        )
    """)
    conn.commit()
    conn.close()

def get_user_level(user_id):
    conn = sqlite3.connect("english_academy.db")
    cursor = conn.cursor()
    cursor.execute("SELECT level FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return 'A2'
    conn.close()
    return row[0]

def update_user_level(user_id, level):
    conn = sqlite3.connect("english_academy.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET level = ? WHERE user_id = ?", (level, user_id))
    conn.commit()
    conn.close()

async def ai_router(user_message: str, user_level: str) -> str:
    full_prompt = f"Student Level: {user_level}\n{SYSTEM_PROMPT}"
    
    # لایه ۱: Gemini 1.5 Flash
    try:
        logging.info("--> Layer 1: Gemini 1.5 Flash")
        genai.configure(api_key=GEMINI_KEY_1)
        model = genai.GenerativeModel("gemini-1.5-flash", system_instruction=full_prompt)
        res = model.generate_content(user_message)
        return res.text
    except Exception as e:
        logging.warning(f"Layer 1 Failed: {e}")

    # لایه ۲: Groq (Llama 3.3)
    try:
        logging.info("--> Layer 2: Groq")
        client = Groq(api_key=GROQ_API_KEY)
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": full_prompt}, {"role": "user", "content": user_message}]
        )
        return completion.choices[0].message.content
    except Exception as e:
        logging.warning(f"Layer 2 Failed: {e}")

    # لایه ۳: OpenRouter (Mistral)
    try:
        logging.info("--> Layer 3: OpenRouter")
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "mistralai/mistral-7b-instruct:free",
            "messages": [{"role": "system", "content": full_prompt}, {"role": "user", "content": user_message}]
        }
        res = requests.post("https://openrouter.ai/ai/v1/chat/completions", json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logging.warning(f"Layer 3 Failed: {e}")

    # لایه ۴: Cohere
    try:
        logging.info("--> Layer 4: Cohere")
        headers = {"Authorization": f"Bearer {COHERE_API_KEY}", "Content-Type": "application/json"}
        payload = {"message": user_message, "preamble": full_prompt, "model": "command-r-plus"}
        res = requests.post("https://api.cohere.com/v1/chat", json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json().get("text")
    except Exception as e:
        logging.warning(f"Layer 4 Failed: {e}")

    # لایه ۵: Gemini 2.0
    try:
        logging.info("--> Layer 5: Gemini 2.0")
        genai.configure(api_key=GEMINI_KEY_1)
        model = genai.GenerativeModel("gemini-2.0-flash", system_instruction=full_prompt)
        res = model.generate_content(user_message)
        return res.text
    except Exception as e:
        logging.warning(f"Layer 5 Failed: {e}")

    # لایه ۶: Gemini رزرو
    try:
        logging.info("--> Layer 6: Gemini Backup Key")
        genai.configure(api_key=GEMINI_KEY_2)
        model = genai.GenerativeModel("gemini-1.5-flash", system_instruction=full_prompt)
        res = model.generate_content(user_message)
        return res.text
    except Exception as e:
        logging.error(f"All Layers Failed: {e}")

    return "⚠️ متأسفانه تمامی سرویس‌ها مشغول هستند. لطفاً لحظاتی بعد دوباره پیام دهید."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lvl = get_user_level(user_id)
    keyboard = [
        [InlineKeyboardButton("🎯 تعیین / تغییر سطح", callback_data="change_level")],
        [InlineKeyboardButton("📊 وضعیت من", callback_data="my_status")]
    ]
    await update.message.reply_text(
        f"سلام {update.effective_user.first_name} عزیز! 👋\n\n📌 **سطح فعلی شما:** {lvl}\n"
        "هر پیامی به انگلیسی بفرستید، گرامر شما را بررسی کرده و پاسخ می‌دهم.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if query.data == "change_level":
        keyboard = [
            [InlineKeyboardButton("A1", callback_data="set_A1"), InlineKeyboardButton("A2", callback_data="set_A2")],
            [InlineKeyboardButton("B1", callback_data="set_B1"), InlineKeyboardButton("B2", callback_data="set_B2")],
            [InlineKeyboardButton("C1", callback_data="set_C1"), InlineKeyboardButton("C2", callback_data="set_C2")]
        ]
        await query.edit_message_text("سطح خود را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data.startswith("set_"):
        lvl = query.data.replace("set_", "")
        update_user_level(user_id, lvl)
        await query.edit_message_text(f"✅ سطح شما با موفقیت به **{lvl}** تغییر کرد.", parse_mode="Markdown")
    elif query.data == "my_status":
        lvl = get_user_level(user_id)
        await query.edit_message_text(f"👤 **پروفایل:**\n🔹 **سطح:** {lvl}\n🔹 **سیستم:** ۶ لایه هوش مصنوعی فعال", parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lvl = get_user_level(user_id)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    response = await ai_router(update.message.text, lvl)
    await update.message.reply_text(response)

def main():
    init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
