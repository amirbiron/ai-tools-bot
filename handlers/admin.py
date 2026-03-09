from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
from datetime import datetime, timezone
from models.db import get_submission, update_submission_status, update_last_published
from config import ADMIN_IDS, CHANNEL_ID

# State לדחייה עם סיבה
WAITING_REJECT_REASON = 10


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def handle_approve(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("אין לך הרשאה.", show_alert=True)
        return

    submission_id = query.data.split(":")[1]
    submission = await get_submission(submission_id)

    if not submission:
        await query.answer("ההגשה לא נמצאה.", show_alert=True)
        return

    if submission["status"] != "pending":
        await query.answer("ההגשה כבר טופלה.", show_alert=True)
        return

    # פרסום בערוץ
    post_url = await _publish_to_channel(ctx, submission)

    # עדכון DB
    await update_submission_status(submission_id, "approved")
    await update_last_published(submission["user_id"], datetime.now(timezone.utc))

    # עדכון הודעת האדמין
    await query.edit_message_caption(
        caption=query.message.caption + "\n\n✅ *אושר ופורסם*",
        parse_mode="Markdown",
    ) if query.message.caption else await query.edit_message_text(
        text=query.message.text + "\n\n✅ *אושר ופורסם*",
        parse_mode="Markdown",
    )

    # הודעה למשתמש
    try:
        msg = f"🎉 הכלי שלך *{submission['tool_name']}* אושר ופורסם בערוץ!"
        if post_url:
            msg += f"\n\n🔗 [צפה בפוסט]({post_url})"
        await ctx.bot.send_message(submission["user_id"], msg, parse_mode="Markdown")
    except Exception as e:
        print(f"[WARN] לא הצלחתי להודיע למשתמש: {e}")

    await query.answer("✅ פורסם!")


async def handle_reject_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("אין לך הרשאה.", show_alert=True)
        return

    submission_id = query.data.split(":")[1]
    submission = await get_submission(submission_id)

    if not submission or submission["status"] != "pending":
        await query.answer("ההגשה כבר טופלה או לא נמצאה.", show_alert=True)
        return

    ctx.user_data["rejecting_submission_id"] = submission_id
    ctx.user_data["rejecting_user_id"] = submission["user_id"]
    ctx.user_data["rejecting_tool_name"] = submission["tool_name"]

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("דלג — דחה ללא סיבה", callback_data="reject_no_reason")
    ]])

    await query.answer()
    await ctx.bot.send_message(
        query.from_user.id,
        f"❌ דחיית *{submission['tool_name']}*\n\nכתוב סיבת הדחייה (תישלח למשתמש), או דלג:",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    return WAITING_REJECT_REASON


async def handle_reject_reason(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reason = update.message.text.strip()
    return await _do_reject(update, ctx, reason)


async def handle_reject_no_reason(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    return await _do_reject(update, ctx, reason=None)


async def _do_reject(update: Update, ctx: ContextTypes.DEFAULT_TYPE, reason: str | None):
    submission_id = ctx.user_data.get("rejecting_submission_id")
    target_user_id = ctx.user_data.get("rejecting_user_id")
    tool_name = ctx.user_data.get("rejecting_tool_name")

    if not submission_id:
        return ConversationHandler.END

    await update_submission_status(submission_id, "rejected", reason)

    # הודעה למשתמש
    try:
        msg = f"❌ הכלי *{tool_name}* לא אושר לפרסום."
        if reason:
            msg += f"\n\n📋 סיבה: {reason}"
        await ctx.bot.send_message(target_user_id, msg, parse_mode="Markdown")
    except Exception as e:
        print(f"[WARN] לא הצלחתי להודיע למשתמש: {e}")

    reply_fn = update.message.reply_text if update.message else update.callback_query.message.reply_text
    await reply_fn("✅ ההגשה נדחתה והמשתמש קיבל הודעה.")

    ctx.user_data.clear()
    return ConversationHandler.END


async def _publish_to_channel(ctx: ContextTypes.DEFAULT_TYPE, submission: dict) -> str | None:
    """מפרסם בערוץ ומחזיר URL לפוסט."""
    username_str = f"@{submission['username']}" if submission.get("username") else "משתמש"
    price_str = submission.get("price", "לא צוין")

    caption = (
        f"🛠 *{submission['tool_name']}*\n\n"
        f"{submission['description']}\n\n"
        f"💵 מחיר: {price_str}\n"
        f"🔗 [לינק לכלי / לדף נחיתה]({submission['link']})\n\n"
        f"_הוגש על ידי {username_str}_"
    )

    try:
        if submission.get("image_file_id"):
            itype = submission.get("image_type", "photo")
            if itype == "photo":
                msg = await ctx.bot.send_photo(CHANNEL_ID, submission["image_file_id"],
                                               caption=caption, parse_mode="Markdown")
            elif itype == "animation":
                msg = await ctx.bot.send_animation(CHANNEL_ID, submission["image_file_id"],
                                                   caption=caption, parse_mode="Markdown")
            else:
                msg = await ctx.bot.send_document(CHANNEL_ID, submission["image_file_id"],
                                                  caption=caption, parse_mode="Markdown")
        else:
            msg = await ctx.bot.send_message(CHANNEL_ID, caption, parse_mode="Markdown")

        # בניית URL לפוסט
        channel_id_str = str(CHANNEL_ID)
        if channel_id_str.startswith("-100"):
            channel_numeric = channel_id_str[4:]
            return f"https://t.me/c/{channel_numeric}/{msg.message_id}"
        elif channel_id_str.startswith("@"):
            return f"https://t.me/{channel_id_str[1:]}/{msg.message_id}"
        return None

    except Exception as e:
        print(f"[ERROR] פרסום בערוץ נכשל: {e}")
        return None


def build_admin_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(handle_reject_start, pattern=r"^reject:\w+$"),
        ],
        states={
            WAITING_REJECT_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reject_reason),
                CallbackQueryHandler(handle_reject_no_reason, pattern="^reject_no_reason$"),
            ]
        },
        fallbacks=[],
        per_message=False,
    )
