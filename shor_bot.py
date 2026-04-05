#!/usr/bin/env python3
"""
סוכן מוצרים - שור פתרונות
Telegram Bot | WooCommerce API + Claude AI

משתני סביבה נדרשים:
  TELEGRAM_TOKEN      - טוקן הבוט מ-BotFather
  ANTHROPIC_API_KEY   - מפתח API מ-Anthropic
  WC_URL              - כתובת האתר  (https://shorpitronot.co.il)
  WC_KEY              - WooCommerce Consumer Key
  WC_SECRET           - WooCommerce Consumer Secret
"""

import os
import json
import logging
import threading
import time
import requests
from anthropic import Anthropic
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ─── הגדרות ───────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN    = os.environ["TELEGRAM_TOKEN"]

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "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")
WC_URL            = os.environ.get("WC_URL", "https://shorpitronot.co.il")
WC_KEY            = os.environ["WC_KEY"]
WC_SECRET         = os.environ["WC_SECRET"]

REFRESH_INTERVAL  = 60 * 60   # רענון מוצרים כל שעה
MAX_HISTORY       = 10         # הודעות לשמור לכל משתמש

# ─── לוגים ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── מצב גלובלי ──────────────────────────────────────────────────────────────
client         = Anthropic(api_key=ANTHROPIC_API_KEY)
products_cache = []
products_lock  = threading.Lock()
user_histories : dict[int, list] = {}


# ─── שאיבת מוצרים מ-WooCommerce ──────────────────────────────────────────────
def fetch_products() -> list[dict]:
    """מביא את כל המוצרים הפעילים מ-WooCommerce."""
    logger.info("מביא מוצרים מ-WooCommerce...")
    all_products = []
    page = 1

    while True:
        try:
            resp = requests.get(
                f"{WC_URL}/wp-json/wc/v3/products",
                auth=(WC_KEY, WC_SECRET),
                params={"per_page": 100, "page": page, "status": "publish"},
                timeout=15,
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"שגיאה בשאיבת מוצרים (עמוד {page}): {e}")
            break

        batch = resp.json()
        if not batch:
            break

        for p in batch:
            dims = p.get("dimensions", {})
            cats = " > ".join(c["name"] for c in p.get("categories", []))
            desc = (p.get("short_description") or "")
            # strip basic HTML tags
            import re
            desc = re.sub(r"<[^>]+>", "", desc)[:120]

            all_products.append({
                "id":    p["id"],
                "name":  p.get("name", "")[:100],
                "cat":   cats[:80],
                "desc":  desc,
                "price": p.get("price") or p.get("regular_price") or "",
                "sale":  p.get("sale_price") or "",
                "h":     dims.get("height", ""),
                "l":     dims.get("length", ""),
                "w":     dims.get("width", ""),
                "stock": 1 if p.get("stock_status") == "instock" else 0,
            })

        logger.info(f"  עמוד {page}: {len(batch)} מוצרים")
        if len(batch) < 100:
            break
        page += 1

    logger.info(f"סה\"כ {len(all_products)} מוצרים נטענו.")
    return all_products


def refresh_loop():
    """רענון ברקע כל שעה."""
    while True:
        time.sleep(REFRESH_INTERVAL)
        try:
            fresh = fetch_products()
            if fresh:
                with products_lock:
                    products_cache.clear()
                    products_cache.extend(fresh)
                logger.info("מטמון מוצרים עודכן.")
        except Exception as e:
            logger.error(f"שגיאה בלולאת רענון: {e}")


# ─── System Prompt דינמי ─────────────────────────────────────────────────────
def build_system_prompt() -> str:
    with products_lock:
        products_json = json.dumps(products_cache, ensure_ascii=False)

    return f"""אתה סוכן מוצרים של חנות "שור פתרונות" - חנות ישראלית המתמחה בפתרונות קירוי, הצללה, ריהוט גן וציוד שדה.

כשמישהו שואל אותך:
1. חפש במוצרים לפי שם, קטגוריה ותיאור
2. ענה בעברית בצורה קצרה וידידותית — מתאים לטלגרם
3. כשמציג מוצרים — כתוב שם בשורה נפרדת, עם מחיר אם קיים
4. הגבל ל-8 מוצרים מקסימום
5. אם אין תוצאות — הצע קטגוריות קרובות
6. שמור תשובות קצרות (עד 300 מילה)
7. אם שואלים על מלאי — בדוק שדה stock (1=יש, 0=אזל)

רשימת המוצרים (מעודכנת מהאתר):
{products_json}"""


# ─── Telegram Handlers ───────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_histories[update.effective_user.id] = []
    with products_lock:
        count = len(products_cache)
    await update.message.reply_text(
        f"שלום! אני הסוכן של שור פתרונות 🏗️\n"
        f"אני מכיר {count} מוצרים ומעודכן ישירות מהאתר.\n\n"
        "לדוגמה:\n"
        "• תן לי שולחנות עד גובה 75 ס\"מ\n"
        "• מה יש לכם בקמפינג?\n"
        "• ברזנט ירוק במלאי\n\n"
        "שאל אותי כל שאלה! 👇"
    )


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_histories[update.effective_user.id] = []
    await update.message.reply_text("✅ השיחה אופסה. מה אתה מחפש?")


async def cmd_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """רענון ידני של המוצרים."""
    await update.message.reply_text("🔄 מרענן מוצרים מהאתר...")
    try:
        fresh = fetch_products()
        if fresh:
            with products_lock:
                products_cache.clear()
                products_cache.extend(fresh)
            await update.message.reply_text(f"✅ עודכן! {len(fresh)} מוצרים נטענו.")
        else:
            await update.message.reply_text("⚠️ לא הצלחתי להוריד מוצרים.")
    except Exception as e:
        await update.message.reply_text(f"❌ שגיאה: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text    = update.message.text.strip()
    if not text:
        return

    logger.info(f"User {user_id}: {text[:80]}")

    history = user_histories.get(user_id, [])
    history.append({"role": "user", "content": text})
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            system=build_system_prompt(),
            messages=history,
        )
        reply = response.content[0].text
    except Exception as e:
        logger.error(f"Anthropic error: {e}")
        reply = "מצטער, הייתה תקלה. נסה שוב בעוד רגע."

    history.append({"role": "assistant", "content": reply})
    user_histories[user_id] = history

    await update.message.reply_text(reply)


# ─── main ─────────────────────────────────────────────────────────────────────
def main():
    logger.info("מפעיל סוכן מוצרים - שור פתרונות...")

    # טעינה ראשונית
    initial = fetch_products()
    if initial:
        products_cache.extend(initial)
    else:
        logger.warning("לא הצלחתי לטעון מוצרים בהפעלה!")

    # רענון ברקע
    threading.Thread(target=refresh_loop, daemon=True).start()

    # הפעלת הבוט
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("reset",   cmd_reset))
    app.add_handler(CommandHandler("refresh", cmd_refresh))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("הבוט פועל!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
