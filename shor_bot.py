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
MAX_HISTORY       = 10

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
            dims = p.get("dimensions", {})
            cats = " > ".join(c["name"] for c in p.get("categories", []))
            desc = re.sub(r"<[^>]+>", "", p.get("short_description") or "")[:120]
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
        products_json = json.dumps(products_cache, ensure_ascii=False)
    return f"""אתה סוכן מוצרים של חנות "שור פתרונות" - חנות ישראלית המתמחה בפתרונות קירוי, הצללה, ריהוט גן וציוד שדה.

כשמישהו שואל אותך:
1. חפש במוצרים לפי שם, קטגוריה ותיאור
2. ענה בעברית בצורה קצרה וידידותית
3. כשמציג מוצרים - כתוב שם בשורה נפרדת, עם מחיר אם קיים
4. הגבל ל-8 מוצרים מקסימום
5. אם אין תוצאות - הצע קטגוריות קרובות
6. שמור תשובות קצרות (עד 300 מילה)
7. stock=1 אומר יש במלאי, stock=0 אומר אזל

רשימת המוצרים:
{products_json}"""

async def cmd_start(update: Update, context):
    user_histories[update.effective_user.id] = []
    with products_lock:
        count = len(products_cache)
    await update.message.reply_text(
        f"שלום! אני הסוכן של שור פתרונות 🏗️\n"
        f"אני מכיר {count} מוצרים ומעודכן ישירות מהאתר.\n\n"
        "לדוגמה:\n• תן לי גזיבואים עד 700 שח\n• מה יש בקמפינג?\n• ברזנט ירוק במלאי\n\nשאל אותי כל שאלה! 👇"
    )

async def cmd_reset(update: Update, context):
    user_histories[update.effective_user.id] = []
    await update.message.reply_text("✅ השיחה אופסה.")

async def cmd_refresh(update: Update, context):
    await update.message.reply_text("🔄 מרענן מוצרים...")
    try:
        fresh = fetch_products()
        if fresh:
            with products_lock:
                products_cache.clear()
                products_cache.extend(fresh)
            await update.message.reply_text(f"✅ עודכן! {len(fresh)} מוצרים.")
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

def main():
    logger.info("מפעיל סוכן מוצרים - שור פתרונות...")
    logger.info(f"API Key prefix: {ANTHROPIC_API_KEY[:20]}...")
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
