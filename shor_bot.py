#!/usr/bin/env python3
import os, json, logging, threading, time, re, requests
from anthropic import Anthropic
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN    = os.environ["TELEGRAM_TOKEN"]
WC_URL            = os.environ.get("WC_URL", "https://shorpitronot.co.il")
WC_KEY            = os.environ["WC_KEY"]
WC_SECRET         = os.environ["WC_SECRET"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

REFRESH_INTERVAL  = 60 * 60
MAX_HISTORY       = 6

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

products_cache = []
products_lock  = threading.Lock()
user_histories: dict[int, list] = {}

def fetch_products():
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
            logger.error(f"שגיאה: {e}")
            break
        batch = resp.json()
        if not batch:
            break
        for p in batch:
            cats = " > ".join(c["name"] for c in p.get("categories", []))
            # שמור רק נתונים חיוניים וקצרים
            all_products.append({
                "n": p.get("name", "")[:60],
                "c": cats.split(">")[0].strip()[:30],
                "p": p.get("price") or p.get("regular_price") or "",
                "s": 1 if p.get("stock_status") == "instock" else 0,
            })
        logger.info(f"  עמוד {page}: {len(batch)} מוצרים")
        if len(batch) < 100:
            break
        page += 1
    logger.info(f"סה\"כ {len(all_products)} מוצרים נטענו.")
    return all_products

def refresh_loop():
    while True:
        time.sleep(REFRESH_INTERVAL)
        try:
            fresh = fetch_products()
            if fresh:
                with products_lock:
                    products_cache.clear()
                    products_cache.extend(fresh)
        except Exception as e:
            logger.error(f"שגיאה ברענון: {e}")

def build_system_prompt():
    with products_lock:
        # המר לפורמט CSV קומפקטי במקום JSON
        lines = ["שם|קטגוריה|מחיר|במלאי"]
        for p in products_cache:
            lines.append(f"{p['n']}|{p['c']}|{p['p']}|{p['s']}")
        products_text = "\n".join(lines)

    return f"""אתה סוכן מוצרים של "שור פתרונות" - חנות ישראלית לקירוי, הצללה, ריהוט גן וציוד שדה.

הנחיות:
- ענה בעברית בקצרה
- הצג עד 8 מוצרים רלוונטיים
- ציין מחיר אם קיים
- במלאי: 1=יש, 0=אזל
- אם אין תוצאות מדויקות - הצע אלטרנטיבות

מוצרים (שם|קטגוריה|מחיר|במלאי):
{products_text}"""

async def cmd_start(update: Update, context):
    user_histories[update.effective_user.id] = []
    with products_lock:
        count = len(products_cache)
    await update.message.reply_text(
        f"שלום! אני הסוכן של שור פתרונות 🏗️\n"
        f"מכיר {count} מוצרים מהאתר.\n\n"
        "דוגמאות:\n• גזיבו מתחת ל-700 ש\"ח\n• ציוד קמפינג\n• ברזנט ירוק במלאי\n\nשאל! 👇"
    )

async def cmd_reset(update: Update, context):
    user_histories[update.effective_user.id] = []
    await update.message.reply_text("✅ השיחה אופסה.")

async def cmd_refresh(update: Update, context):
    await update.message.reply_text("🔄 מרענן...")
    try:
        fresh = fetch_products()
        if fresh:
            with products_lock:
                products_cache.clear()
                products_cache.extend(fresh)
            await update.message.reply_text(f"✅ {len(fresh)} מוצרים עודכנו.")
    except Exception as e:
        await update.message.reply_text(f"❌ שגיאה: {e}")

async def handle_message(update: Update, context):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if not text:
        return
    logger.info(f"User {user_id}: {text[:80]}")
    history = user_histories.get(user_id, [])
    history.append({"role": "user", "content": text})
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=build_system_prompt(),
            messages=history,
        )
        reply = response.content[0].text
    except Exception as e:
        logger.error(f"Anthropic error: {e}")
        reply = "מצטער, הייתה תקלה. נסה שוב."
    history.append({"role": "assistant", "content": reply})
    user_histories[user_id] = history
    await update.message.reply_text(reply)

def main():
    logger.info("מפעיל סוכן מוצרים - שור פתרונות...")
    initial = fetch_products()
    if initial:
        products_cache.extend(initial)
    threading.Thread(target=refresh_loop, daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("reset",   cmd_reset))
    app.add_handler(CommandHandler("refresh", cmd_refresh))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("הבוט פועל!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
