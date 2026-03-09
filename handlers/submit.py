from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from datetime import datetime, timezone
from config import ADMIN_IDS
from models.db import get_user, upsert_user, save_submission
from utils.cooldown import get_remaining, format_remaining

# States
NAME, DESCRIPTION, LINK, PRICE, PRICE_AMOUNT, IMAGE, CONFIRM = range(7)

SKIP_IMAGE_CB = "skip_image"
CONFIRM_YES_CB = "confirm_yes"
CONFIRM_NO_CB = "confirm_no"
PRICE_FREE_CB = "price_free"
PRICE_PAID_CB = "price_paid"


async def start_submit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await upsert_user(user.id, user.username or "")

    db_user = await get_user(user.id)
    remaining = get_remaining(db_user.get("last_published_at") if db_user else None)

    if remaining and user.id not in ADMIN_IDS:
        await update.message.reply_text(
            f"⏳ עדיין לא עברו {5} ימים מהפרסום האחרון שלך.\n"
            f"נותרו: *{format_remaining(remaining)}*\n\n"
            f"תוכל להגיש שוב בקרוב!",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "🛠 *הגשת כלי AI*\n\n"
        "נתחיל עם השם של הכלי — מה שמו?",
        parse_mode="Markdown",
    )
    return NAME


async def got_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("תיאור קצר של הכלי — במשפט או שניים:")
    return DESCRIPTION


async def got_description(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["description"] = update.message.text.strip()
    await update.message.reply_text("לינק לכלי:")
    return LINK


async def got_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    if not link.startswith("http"):
        await update.message.reply_text("⚠️ נראה שהלינק לא תקין. נסה שוב:")
        return LINK
    ctx.user_data["link"] = link

    kb = [
        [InlineKeyboardButton("🆓 חינם", callback_data=PRICE_FREE_CB),
         InlineKeyboardButton("💰 בתשלום", callback_data=PRICE_PAID_CB)]
    ]
    await update.message.reply_text(
        "מה המחיר?",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return PRICE


async def got_price_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == PRICE_FREE_CB:
        ctx.user_data["price"] = "חינם"
        await query.edit_message_text("תמונה או GIF של הכלי (אופציונלי):", reply_markup=_skip_kb())
        return IMAGE
    else:
        await query.edit_message_text("כמה עולה? (לדוגמה: $9/חודש, $49 חד-פעמי):")
        return PRICE_AMOUNT


async def got_price_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["price"] = update.message.text.strip()
    await update.message.reply_text("תמונה או GIF של הכלי (אופציונלי):", reply_markup=_skip_kb())
    return IMAGE


async def got_image(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        ctx.user_data["image_file_id"] = update.message.photo[-1].file_id
        ctx.user_data["image_type"] = "photo"
    elif update.message.animation:
        ctx.user_data["image_file_id"] = update.message.animation.file_id
        ctx.user_data["image_type"] = "animation"
    elif update.message.document and update.message.document.mime_type and "image" in update.message.document.mime_type:
        ctx.user_data["image_file_id"] = update.message.document.file_id
        ctx.user_data["image_type"] = "document"
    else:
        await update.message.reply_text("שלח תמונה/GIF, או דלג:", reply_markup=_skip_kb())
        return IMAGE

    return await show_summary(update, ctx)


async def skip_image(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["image_file_id"] = None
    ctx.user_data["image_type"] = None
    return await show_summary(update, ctx, via_query=True)


async def show_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE, via_query=False):
    d = ctx.user_data
    price_str = d.get("price", "לא צוין")
    image_str = "✅ צורפה" if d.get("image_file_id") else "❌ לא צורפה"

    text = (
        f"📋 *סיכום ההגשה:*\n\n"
        f"🏷 *שם:* {d.get('name')}\n"
        f"📝 *תיאור:* {d.get('description')}\n"
        f"🔗 *לינק:* {d.get('link')}\n"
        f"💵 *מחיר:* {price_str}\n"
        f"🖼 *תמונה:* {image_str}\n\n"
        f"לשלוח?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ שלח", callback_data=CONFIRM_YES_CB),
         InlineKeyboardButton("❌ ביטול", callback_data=CONFIRM_NO_CB)]
    ])

    if via_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

    return CONFIRM


async def confirmed(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == CONFIRM_NO_CB:
        await query.edit_message_text("❌ ההגשה בוטלה. שלח /הגש כשתרצה להתחיל מחדש.")
        ctx.user_data.clear()
        return ConversationHandler.END

    user = update.effective_user
    d = ctx.user_data

    submission = {
        "user_id": user.id,
        "username": user.username or "",
        "tool_name": d.get("name"),
        "description": d.get("description"),
        "link": d.get("link"),
        "price": d.get("price"),
        "image_file_id": d.get("image_file_id"),
        "image_type": d.get("image_type"),
        "status": "pending",
        "submitted_at": datetime.now(timezone.utc),
        "reviewed_at": None,
        "reject_reason": None,
    }

    submission_id = await save_submission(submission)

    await query.edit_message_text(
        "✅ *ההגשה התקבלה!*\n\nהכלי שלך ממתין לאישור ונשלח לערוץ בקרוב 🚀",
        parse_mode="Markdown",
    )

    # שליחה לאדמינים
    await _notify_admins(ctx, submission, submission_id)

    ctx.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("❌ ההגשה בוטלה.")
    return ConversationHandler.END


async def _notify_admins(ctx: ContextTypes.DEFAULT_TYPE, submission: dict, submission_id: str):
    from config import ADMIN_IDS
    price_str = submission.get("price", "לא צוין")
    username_str = f"@{submission['username']}" if submission.get("username") else f"id:{submission['user_id']}"

    text = (
        f"🆕 *הגשה חדשה לאישור*\n\n"
        f"👤 {username_str}\n"
        f"🏷 *שם:* {submission['tool_name']}\n"
        f"📝 *תיאור:* {submission['description']}\n"
        f"🔗 *לינק:* {submission['link']}\n"
        f"💵 *מחיר:* {price_str}\n"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ אשר ופרסם", callback_data=f"approve:{submission_id}"),
         InlineKeyboardButton("❌ דחה", callback_data=f"reject:{submission_id}")]
    ])

    for admin_id in ADMIN_IDS:
        try:
            if submission.get("image_file_id"):
                itype = submission.get("image_type", "photo")
                if itype == "photo":
                    await ctx.bot.send_photo(admin_id, submission["image_file_id"], caption=text,
                                             parse_mode="Markdown", reply_markup=kb)
                elif itype == "animation":
                    await ctx.bot.send_animation(admin_id, submission["image_file_id"], caption=text,
                                                 parse_mode="Markdown", reply_markup=kb)
                else:
                    await ctx.bot.send_document(admin_id, submission["image_file_id"], caption=text,
                                                parse_mode="Markdown", reply_markup=kb)
            else:
                await ctx.bot.send_message(admin_id, text, parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            print(f"[WARN] לא הצלחתי לשלוח לאדמין {admin_id}: {e}")


def _skip_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("דלג ⏭", callback_data=SKIP_IMAGE_CB)]])


def build_submit_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^/הגש"), start_submit),
            CommandHandler("start", start_submit),
            CommandHandler("submit", start_submit),
        ],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_name)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_description)],
            LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_link)],
            PRICE: [CallbackQueryHandler(got_price_type, pattern=f"^({PRICE_FREE_CB}|{PRICE_PAID_CB})$")],
            PRICE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_price_amount)],
            IMAGE: [
                MessageHandler(filters.PHOTO | filters.ANIMATION | filters.Document.IMAGE, got_image),
                CallbackQueryHandler(skip_image, pattern=f"^{SKIP_IMAGE_CB}$"),
            ],
            CONFIRM: [CallbackQueryHandler(confirmed, pattern=f"^({CONFIRM_YES_CB}|{CONFIRM_NO_CB})$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
