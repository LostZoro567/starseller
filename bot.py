"""
bot.py — Telegram Business Bot
Auto-replies only to a user's FIRST ever message,
with realistic typing simulation before each message.
"""

import asyncio
import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import TelegramError, Forbidden
from telegram.ext import (
    Application,
    ApplicationBuilder,
    BusinessConnectionHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import (
    MSG_1_DELAY,
    MSG_2_DELAY,
    MESSAGE_1,
    MESSAGE_2,
    TYPING_SPEED,
)
from database import Database

load_dotenv()
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── In-memory: bc_id → owner_id ───────────────────────────────────────────────
active_connections: dict[str, int] = {}


# ════════════════════════════════════════════════════════════════════════
#  STARTUP — restore connections from DB
# ════════════════════════════════════════════════════════════════════════

async def on_startup(app: Application):
    db: Database = app.bot_data["db"]
    rows = db.get_active_connections()
    for row in rows:
        active_connections[row["id"]] = row["owner_id"]
    logger.info(f"🔄 Restored {len(rows)} business connection(s) from DB")


# ════════════════════════════════════════════════════════════════════════
#  BUSINESS CONNECTION
# ════════════════════════════════════════════════════════════════════════

async def handle_business_connection(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    bc = update.business_connection
    db: Database = context.bot_data["db"]

    if bc.is_enabled:
        active_connections[bc.id] = bc.user.id
        db.save_business_connection(bc.id, bc.user.id, is_enabled=True)
        logger.info(f"✅ Business connected | bc_id={bc.id} | owner={bc.user.id}")
    else:
        active_connections.pop(bc.id, None)
        db.save_business_connection(bc.id, bc.user.id, is_enabled=False)
        logger.info(f"❌ Business disconnected | bc_id={bc.id}")


# ════════════════════════════════════════════════════════════════════════
#  TYPING SIMULATOR
#  Shows "typing…" indicator for a duration based on message length,
#  refreshing every 4s (Telegram clears it after 5s automatically).
# ════════════════════════════════════════════════════════════════════════

async def simulate_typing(context, chat_id: int, bc_id: str, text: str):
    """
    Show a realistic typing indicator before sending a message.
    Duration = len(text) / TYPING_SPEED seconds, minimum 1.5s.
    """
    duration = max(len(text) / TYPING_SPEED, 1.5)
    elapsed = 0.0

    while elapsed < duration:
        await context.bot.send_chat_action(
            chat_id=chat_id,
            action=ChatAction.TYPING,
            business_connection_id=bc_id,
        )
        tick = min(4.0, duration - elapsed)   # refresh before 5s expiry
        await asyncio.sleep(tick)
        elapsed += tick


# ════════════════════════════════════════════════════════════════════════
#  SEND HELPER — typing then message
# ════════════════════════════════════════════════════════════════════════

async def type_and_send(context, chat_id: int, bc_id: str, text: str):
    """Simulate typing then send the message."""
    await simulate_typing(context, chat_id, bc_id, text)
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        business_connection_id=bc_id,
        parse_mode=ParseMode.HTML,
    )


# ════════════════════════════════════════════════════════════════════════
#  BUSINESS MESSAGE HANDLER
# ════════════════════════════════════════════════════════════════════════

async def handle_business_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    message = update.business_message
    if not message:
        return

    bc_id  = message.business_connection_id
    sender = message.from_user

    # ── Ignore messages sent by the business owner themselves ────────────
    owner_id = active_connections.get(bc_id)
    if owner_id and sender.id == owner_id:
        return

    db: Database = context.bot_data["db"]

    # ── Upsert user — returns new message_count ───────────────────────────
    msg_count = db.upsert_user(sender, bc_id)
    logger.info(
        f"💬 User {sender.id} (@{sender.username}) | "
        f"msg #{msg_count} | chat {message.chat_id}"
    )

    # ── Only auto-reply on their VERY FIRST message ───────────────────────
    if msg_count != 1:
        return   # repeat message — you handle it manually

    chat_id = message.chat_id
    name    = sender.first_name or "there"

    try:
        # ── Wait MSG_1_DELAY, then show typing + send message 1 ──────────
        await asyncio.sleep(MSG_1_DELAY)
        msg1 = MESSAGE_1.format(name=name)
        await type_and_send(context, chat_id, bc_id, msg1)

        # ── Wait MSG_2_DELAY, then show typing + send message 2 ──────────
        await asyncio.sleep(MSG_2_DELAY)
        msg2 = MESSAGE_2.format(name=name)
        await type_and_send(context, chat_id, bc_id, msg2)

        logger.info(f"✅ Auto-reply sequence complete for user {sender.id}")

    except TelegramError as e:
        logger.error(f"Failed to send auto-reply to {sender.id}: {e}")


# ════════════════════════════════════════════════════════════════════════
#  ADMIN COMMANDS
# ════════════════════════════════════════════════════════════════════════

def is_admin(user_id: int) -> bool:
    return str(user_id) == os.getenv("ADMIN_ID", "")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 <b>Business Bot is live!</b>\n\n"
        "Connect via: <i>Settings → Business → Chatbots</i>\n\n"
        "Commands:\n"
        "• /stats — view statistics\n"
        "• /broadcast — message all users",
        parse_mode=ParseMode.HTML,
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Access denied.")
        return

    db: Database = context.bot_data["db"]
    s = db.get_stats()

    await update.message.reply_text(
        "📊 <b>Bot Statistics</b>\n"
        "─────────────────────\n"
        f"👥 Total users:        <b>{s['total_users']:,}</b>\n"
        f"🆕 New today:          <b>{s['new_today']:,}</b>\n"
        f"📅 New this week:      <b>{s['new_this_week']:,}</b>\n"
        f"💬 Total messages:     <b>{s['total_messages']:,}</b>\n"
        f"📣 Broadcasts sent:    <b>{s['total_broadcasts']:,}</b>\n"
        f"🔗 Active connections: <b>{len(active_connections)}</b>",
        parse_mode=ParseMode.HTML,
    )


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Access denied.")
        return

    if not context.args:
        await update.message.reply_text(
            "📣 <b>Usage:</b> <code>/broadcast Your message here</code>\n\n"
            "Supports HTML: <code>&lt;b&gt;bold&lt;/b&gt;</code>, "
            "<code>&lt;i&gt;italic&lt;/i&gt;</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    text = " ".join(context.args)
    db: Database = context.bot_data["db"]
    user_ids = db.get_all_user_ids()

    if not user_ids:
        await update.message.reply_text("📭 No users yet.")
        return

    status = await update.message.reply_text(
        f"📣 Broadcasting to <b>{len(user_ids):,}</b> users...",
        parse_mode=ParseMode.HTML,
    )

    sent, failed = 0, 0
    for uid in user_ids:
        try:
            await context.bot.send_message(
                chat_id=uid, text=text, parse_mode=ParseMode.HTML
            )
            sent += 1
        except Forbidden:
            failed += 1
        except TelegramError as e:
            logger.warning(f"Broadcast failed for {uid}: {e}")
            failed += 1
        await asyncio.sleep(0.05)   # ~20 msg/sec — safe rate limit

    db.log_broadcast(update.effective_user.id, text, sent, failed)

    await status.edit_text(
        f"✅ <b>Broadcast complete!</b>\n\n"
        f"📤 Sent:   <b>{sent:,}</b>\n"
        f"❌ Failed: <b>{failed:,}</b>",
        parse_mode=ParseMode.HTML,
    )


# ════════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════════

def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN not set in .env")

    db  = Database()
    app = ApplicationBuilder().token(token).post_init(on_startup).build()
    app.bot_data["db"] = db

    app.add_handler(BusinessConnectionHandler(handle_business_connection))
    app.add_handler(
        MessageHandler(filters.UpdateType.BUSINESS_MESSAGE, handle_business_message)
    )
    app.add_handler(CommandHandler("start",     start_command))
    app.add_handler(CommandHandler("stats",     stats_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))

    logger.info("🤖 Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
