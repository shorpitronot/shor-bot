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
MAX_PRODUCTS_TO_SEND = 40  # מקסימום מוצרים לשלוח ל-Claude

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
            slug = p.get("slug", "")
            all_products.append({
                "n": p.get("name", "")[:70],
                "c": cats.split(">")[0].strip()[:30],
                "p": p.get("price") or p.get("regular_price") or "",
                "s": 1 if p.get("stock_status") == "instock" else 0,
                "slug": slug,
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

def filter_products(query: str) -> list:
    """סינון חכם — מחזיר רק מוצרים רלוונטיים לשאלה."""
    with products_lock:
        all_products = list(products_cache)

    # מילות מפתח מהשאלה (ללא מילות עזר)
    stopwords = {"לי", "תן", "תראה", "רוצה", "מחפש", "יש", "כל", "של", "את", "עד",
                 "מתחת", "מעל", "בפחות", "ביותר", "שח", "ש\"ח", "שקל", "הכי",
                 "מה", "איזה", "אני", "גם", "רק", "עם", "בלי", "או", "ו", "מ", "ב", "ל"}

    words = [w for w in re.findall(r'[\u05d0-\u05ea\w]+', query.lower()) if w not in stopwords and len(w) > 1]

    if not words:
        return all_products[:MAX_PRODUCTS_TO_SEND]

    scored = []
    for p in all_products:
        name_lower = p["n"].lower()
        cat_lower = p["c"].lower()
        score = 0
        for w in words:
            if w in name_lower:
                score += 3
            if w in cat_lower:
                score += 2
        if score > 0:
            scored.append((score, p))

    # מיון לפי ציון, החזר עד MAX_PRODUCTS_TO_SEND
    scored.sort(key=lambda x: -x[0])
    filtered = [p for _, p in scored[:MAX_PRODUCTS_TO_SEND]]

    # אם אין תוצאות — שלח את כולם (מוגבל)
    if not filtered:
        return all_products[:MAX_PRODUCTS_TO_SEND]

    return filtered

def product_url(slug: str) -> str:
    return f"{WC_URL}/product/{slug}/" if slug else ""

def build_system_prompt(relevant_products: list) -> str:
    lines = ["שם|קטגוריה|מחיר|מלאי|קישור"]
    for p in relevant_products:
        url = product_url(p["slug"])
        lines.append(f"{p['n']}|{p['c']}|{p['p']}|{p['s']}|{url}")
    products_text = "\n".join(lines)

    return f"""אתה סוכן מוצרים של "שור פתרונות" - חנות ישראלית לקירוי, הצללה, ריהוט גן וציוד שדה.

הנחיות:
- ענה בעברית בקצרה ובידידותיות
- הצג עד 8 מוצרים רלוונטיים
- ציין מחיר אם קיים
- מלאי: 1=יש, 0=אזל
- אם המשתמש ביקש קישורים — הוסף את הקישור מהעמודה האחרונה
- אם אין מוצר מתאים — הצע קטגוריות קרובות

מוצרים רלוונטיים (שם|קטגוריה|מחיר|מלאי|קישור):
{products_text}"""

async def cmd_start(update: Update, context):
    user_histories[update.effective_user.id] = []
    with products_lock:
        count = len(products_cache)
    await update.message.reply_text(
        f"שלום! אני הסוכן של שור פתרונות 🏗️\n"
        f"מכיר {count} מוצרים מהאתר.\n\n"
        "דוגמאות:\n"
        "• גזיבו מתחת ל-700 ש\"ח\n"
        "• ציוד קמפינג במלאי\n"
        "• ברזנט ירוק + קישור\n\n"
        "שאל אותי כל שאלה! 👇"
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
            await update.message.reply_text(f"✅ {len(fresh)} מוצרים עודכנו.")
    except Exception as e:
        await update.message.reply_text(f"❌ שגיאה: {e}")

async def handle_message(update: Update, context):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if not text:
        return

    logger.info(f"User {user_id}: {text[:80]}")

    # סינון חכם — רק מוצרים רלוונטיים
    relevant = filter_products(text)
    logger.info(f"  מוצרים רלוונטיים: {len(relevant)}")

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
            system=build_system_prompt(relevant),
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
