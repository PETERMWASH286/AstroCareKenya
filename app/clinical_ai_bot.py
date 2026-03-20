"""
Simple Clinical AI Assistant Telegram Bot
No external tools – just conversational AI for clinical queries.
Converts AI markdown responses to safe HTML for Telegram.
"""

import os
import sys
import json
import logging
import re
import requests
import markdown
import bleach
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import TimedOut

# Load environment variables
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not found in .env")

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------- CONFIGURATION ----------
PROVIDER = "openrouter"               # "openrouter" or "cerebras"
MODEL = "nvidia/nemotron-3-nano-30b-a3b:free"   # Change as needed
SYSTEM_PROMPT = (
    "You are a helpful, compassionate, and knowledgeable Clinical AI Assistant. "
    "You provide general medical information and support, but you are not a substitute "
    "for professional medical advice. Always encourage users to consult a qualified "
    "healthcare provider for personal health concerns. "
    "Respond in a warm, professional, and concise manner. "
    "Format your answers using Markdown: **bold**, *italic*, `code`, ```code blocks```, and numbered lists. "
    "Avoid excessive blank lines."
)

# Telegram allowed HTML tags
ALLOWED_TAGS = [
    'b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del',
    'a', 'code', 'pre'
]

# Conversation storage (user_id -> list of messages)
user_conversations = {}

# API endpoints
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"

# ---------- AI Call ----------
async def call_ai(messages, retries=3):
    """
    Non‑streaming call with extended timeout and retry logic.
    Returns the message content.
    """
    headers = {}
    url = ""
    if PROVIDER == "openrouter":
        url = OPENROUTER_URL
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
    elif PROVIDER == "cerebras":
        url = CEREBRAS_URL
        headers = {
            "Authorization": f"Bearer {CEREBRAS_API_KEY}",
            "Content-Type": "application/json"
        }
    else:
        return "Provider not configured."

    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2000,
    }

    for attempt in range(retries):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=180)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except requests.exceptions.Timeout:
            logger.warning(f"Attempt {attempt+1} timed out")
            if attempt == retries - 1:
                return "❌ The AI model is taking too long to respond. Please try a simpler query or try again later."
        except requests.exceptions.ConnectionError:
            logger.warning(f"Attempt {attempt+1} connection error")
            if attempt == retries - 1:
                return "❌ Network error connecting to AI service. Please try again later."
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error on attempt {attempt+1}: {e}")
            if response.status_code >= 500 and attempt < retries - 1:
                continue
            else:
                return f"❌ Error communicating with AI: {e}"
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            logger.error(f"Response parsing error: {e}")
            return "❌ Error: Unexpected response from AI."
    return "❌ Unknown error occurred."

# ---------- Formatting Helpers ----------
def collapse_blank_lines(text: str) -> str:
    """Replace more than two consecutive newlines with two."""
    return re.sub(r'\n{3,}', '\n\n', text)

def format_response(text: str) -> str:
    """Convert markdown to HTML and strip unsupported Telegram tags."""
    try:
        text = collapse_blank_lines(text)
        html = markdown.markdown(text, extensions=['extra', 'codehilite', 'tables'])
        # Replace heading tags with bold
        html = re.sub(r'<h[1-6]>(.*?)</h[1-6]>', r'<b>\1</b>', html, flags=re.DOTALL)
        clean = bleach.clean(html, tags=ALLOWED_TAGS, strip=True)
        return clean
    except Exception as e:
        logger.error(f"Formatting error: {e}")
        return text

# ---------- Command Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome = (
        f"👋 Hello {user.first_name}!\n\n"
        f"I'm your **Clinical AI Assistant**. I'm using the **{MODEL}** model via {PROVIDER}.\n\n"
        f"I can provide general medical information and support. "
        f"Remember: I am not a substitute for professional medical advice.\n\n"
        f"Commands:\n"
        f"/reset - Clear conversation history\n"
        f"/model - Show current model\n"
        f"/prompt - Show the system prompt I use"
    )
    await update.message.reply_text(welcome, parse_mode=ParseMode.MARKDOWN)

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_conversations:
        user_conversations[user_id] = []
    await update.message.reply_text("✅ Conversation reset.")

async def show_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Current model: `{MODEL}` (via {PROVIDER})",
        parse_mode=ParseMode.MARKDOWN
    )

async def show_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"System prompt:\n```\n{SYSTEM_PROMPT}\n```",
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text

    # Initialize conversation history if needed
    if user_id not in user_conversations:
        user_conversations[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add user message
    user_conversations[user_id].append({"role": "user", "content": user_text})

    # Show typing indicator
    await context.bot.send_chat_action(chat_id=user_id, action="typing")

    # Call AI
    ai_response = await call_ai(user_conversations[user_id])

    # Add assistant response to history (optional, for context)
    user_conversations[user_id].append({"role": "assistant", "content": ai_response})

    # Format and send
    formatted = format_response(ai_response)
    if len(formatted) > 4000:
        for i in range(0, len(formatted), 4000):
            await update.message.reply_text(
                formatted[i:i+4000],
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
    else:
        await update.message.reply_text(
            formatted,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if isinstance(context.error, TimedOut):
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⏱️ The request timed out. The AI might be overloaded. Please try again in a moment."
            )
        except:
            pass
    else:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ An unexpected error occurred. Please try again later."
            )
        except:
            pass

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("model", show_model))
    app.add_handler(CommandHandler("prompt", show_prompt))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    print(f"🤖 Clinical AI Assistant started. Provider: {PROVIDER}, Model: {MODEL}")
    print("Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES, timeout=30)

if __name__ == "__main__":
    main()