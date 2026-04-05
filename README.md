# 🤖 סוכן מוצרים - שור פתרונות

בוט טלגרם המחובר ישירות ל-WooCommerce ועונה בעברית על שאלות מוצרים.

---

## שלב 1 — צור בוט בטלגרם

1. פתח טלגרם ← חפש **@BotFather**
2. שלח: `/newbot`
3. בחר שם (לדוגמה: `שור פתרונות מוצרים`)
4. בחר username (לדוגמה: `shor_products_bot`)
5. שמור את ה-**TOKEN** שתקבל

---

## שלב 2 — העלה ל-GitHub

1. כנס ל: https://github.com ← צור חשבון אם אין
2. לחץ **New repository** ← שם: `shor-bot` ← **Create**
3. העלה את 4 הקבצים: `shor_bot.py`, `requirements.txt`, `Procfile`, `README.md`
   - לחץ **Add file** ← **Upload files**

---

## שלב 3 — פרוס ב-Railway

1. כנס ל: https://railway.app ← **Login with GitHub**
2. לחץ **New Project** ← **Deploy from GitHub repo**
3. בחר את ה-repo `shor-bot`
4. Railway יתחיל לבנות את הפרויקט

### הוסף משתני סביבה:
לחץ על הפרויקט ← **Variables** ← הוסף את הבאים:

| שם משתנה | ערך |
|----------|-----|
| `TELEGRAM_TOKEN` | הטוקן מ-BotFather |
| `ANTHROPIC_API_KEY` | המפתח מ-console.anthropic.com |
| `WC_URL` | `https://shorpitronot.co.il` |
| `WC_KEY` | ה-Consumer Key מ-WooCommerce |
| `WC_SECRET` | ה-Consumer Secret מ-WooCommerce |

5. לאחר הוספת המשתנים ← לחץ **Deploy**

זהו! הבוט פעיל 24/7 🎉

---

## פקודות הבוט

| פקודה | תיאור |
|-------|-------|
| `/start` | הפעלה ואיפוס שיחה |
| `/reset` | ניקוי היסטוריית שיחה |
| `/refresh` | רענון מידי של המוצרים מהאתר |
| כל הודעה | שאלה חופשית על מוצרים |

---

## עדכון מוצרים

המוצרים מתרעננים **אוטומטית כל שעה** מהאתר.
לרענון מידי — שלח `/refresh` בבוט.

---

## עלות משוערת

- **Railway**: ~$0.50/חודש (הרבה מתחת לקרדיט החינמי של $5)
- **Anthropic API**: ~$0.10-0.30/חודש (תלוי בכמות שאלות)
- **סה"כ**: בפועל חינם 🎉
