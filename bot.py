"""
bot.py — Telegram Business Bot
Handles auto-replies, paid content, broadcasts and stats
via Telegram Business API.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from telegram import (
    Update,
    InputPaidMediaPhoto,
    InputPaidMediaVideo,
    InputMediaPhoto,
)
from telegram.constants import ParseMode
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

from config import REPLY_SEQUENCE, FALLBACK_REPLY, MAX_DELAY_SECONDS
from database import Database

load_dotenv()
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── In-memory store: business_connection_id → owner_user_id ──────────────────
# Populated at startup from DB + updated live as connections arrive
active_connections: dict[str, int] = {}  # bc_id → owner_id


# ════════════════════════════════════════════════════════════════════════
#  STARTUP
# ════════════════════════════════════════════════════════════════════════

async def on_startup(app: Application):
    """Restore business connections from database on bot restart."""
    db: Database = app.bot_data["db"]
    rows = db.get_active_connections()
    for row in rows:
        active_connections[row["id"]] = row["owner_id"]
    logger.info(f"🔄 Restored {len(rows)} business connection(s) from DB")


# ════════════════════════════════════════════════════════════════════════
#  BUSINESS CONNECTION HANDLER
# ════════════════════════════════════════════════════════════════════════

async def handle_business_connection(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """
    Fires when a Telegram Business account connects or disconnects the bot.
    Telegram → Settings → Business → Chatbots → select this bot.
    """
    bc = update.business_connection
    db: Database = context.bot_data["db"]

    if bc.is_enabled:
        active_connections[bc.id] = bc.user.id
        db.save_business_connection(bc.id, bc.user.id, is_enabled=True)
        logger.info(f"✅ Business connected | bc_id={bc.id} owner={bc.user.id}")
    else:
        active_connections.pop(bc.id, None)
        db.save_business_connection(bc.id, bc.user.id, is_enabled=False)
        logger.info(f"❌ Business disconnected | bc_id={bc.id}")


# ════════════════════════════════════════════════════════════════════════
#  BUSINESS MESSAGE HANDLER  (auto-reply engine)
# ════════════════════════════════════════════════════════════════════════

async def handle_business_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """
    Fires for every message in a business chat.
    Only auto-replies to INCOMING messages from non-owners.
    """
    message = update.business_message
    if not message:
        return

    bc_id = message.business_connection_id
    sender = message.from_user

    # ── Skip messages sent BY the business owner themselves ──────────────
    owner_id = active_connections.get(bc_id)
    if owner_id and sender.id == owner_id:
        return  # Owner typed this — don't auto-reply

    db: Database = context.bot_data["db"]

    # ── Track user & get their message count ─────────────────────────────
    msg_count = db.upsert_user(sender, bc_id)
    logger.info(
        f"💬 User {sender.id} (@{sender.username}) | msg #{msg_count} "
        f"| chat {message.chat_id}"
    )

    # ── Find the matching reply step ──────────────────────────────────────
    step_config = next(
        (s for s in REPLY_SEQUENCE if s["step"] == msg_count), None
    )

    if step_config is None:
        # Beyond defined sequence — use fallback
        if FALLBACK_REPLY:
            await asyncio.sleep(1)
            await send_text(
                context,
                chat_id=message.chat_id,
                bc_id=bc_id,
                text=FALLBACK_REPLY.format(
                    name=sender.first_name or "there",
                    username=f"@{sender.username}" if sender.username else "",
                ),
            )
        return

    # ── Apply delay ───────────────────────────────────────────────────────
    delay = min(step_config.get("delay", 0), MAX_DELAY_SECONDS)
    if delay > 0:
        await asyncio.sleep(delay)

    # ── Dispatch reply by type ────────────────────────────────────────────
    reply_type = step_config.get("type", "text")

    try:
        if reply_type == "text":
            text = step_config["content"].format(
                name=sender.first_name or "there",
                username=f"@{sender.username}" if sender.username else "",
            )
            await send_text(context, message.chat_id, bc_id, text)

        elif reply_type == "photo":
            await send_photo(
                context,
                chat_id=message.chat_id,
                bc_id=bc_id,
                photo=step_config["media"],
                caption=step_config.get("caption", ""),
            )

        elif reply_type == "paid_media":
            await send_paid_media(
                context,
                chat_id=message.chat_id,
                bc_id=bc_id,
                star_count=step_config["star_count"],
                media_list=step_config["media"],
                caption=step_config.get("caption", "🔒 Unlock with Stars"),
            )

        else:
            logger.warning(f"Unknown reply type: {reply_type}")

    except TelegramError as e:
        logger.error(f"Failed to send reply to {sender.id}: {e}")


# ════════════════════════════════════════════════════════════════════════
#  SEND HELPERS
# ════════════════════════════════════════════════════════════════════════

async def send_text(context, chat_id, bc_id, text):
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        business_connection_id=bc_id,
        parse_mode=ParseMode.HTML,
    )


async def send_photo(context, chat_id, bc_id, photo, caption=""):
    await context.bot.send_photo(
        chat_id=chat_id,
        photo=photo,
        caption=caption,
        business_connection_id=bc_id,
        parse_mode=ParseMode.HTML,
    )


async def send_paid_media(context, chat_id, bc_id, star_count, media_list, caption):
    """
    Send a paid media bundle (photos or videos) gated by Telegram Stars.
    Users pay star_count Stars to unlock all items.
    """
    paid_items = []
    for item in media_list[:10]:  # Telegram cap: max 10 items
        # Detect video by file extension or explicit "video:" prefix
        if isinstance(item, str) and (
            item.startswith("video:") or item.lower().endswith((".mp4", ".mov", ".avi"))
        ):
            media_url = item.replace("video:", "")
            paid_items.append(InputPaidMediaVideo(media=media_url))
        else:
            paid_items.append(InputPaidMediaPhoto(media=item))

    await context.bot.send_paid_media(
        chat_id=chat_id,
        star_count=star_count,
        media=paid_items,
        caption=caption,
        business_connection_id=bc_id,
        parse_mode=ParseMode.HTML,
    )


# ════════════════════════════════════════════════════════════════════════
#  ADMIN COMMANDS
# ════════════════════════════════════════════════════════════════════════

def is_admin(user_id: int) -> bool:
    admin_id = os.getenv("ADMIN_ID", "")
    return str(user_id) == admin_id


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/stats — show bot statistics (admin only)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Access denied.")
        return

    db: Database = context.bot_data["db"]
    s = db.get_stats()

    text = (
        "📊 <b>Bot Statistics</b>\n"
        "─────────────────────\n"
        f"👥 Total users:       <b>{s['total_users']:,}</b>\n"
        f"🆕 New today:         <b>{s['new_today']:,}</b>\n"
        f"📅 New this week:     <b>{s['new_this_week']:,}</b>\n"
        f"💬 Total messages:    <b>{s['total_messages']:,}</b>\n"
        f"📣 Broadcasts sent:   <b>{s['total_broadcasts']:,}</b>\n"
        f"🔗 Active connections:<b>{len(active_connections)}</b>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /broadcast <message>
    Sends a message to every user who has ever messaged the business account.
    Admin only.
    """
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Access denied.")
        return

    if not context.args:
        await update.message.reply_text(
            "📣 <b>Broadcast Usage</b>\n\n"
            "<code>/broadcast Your message here</code>\n\n"
            "Supports HTML formatting:\n"
            "<code>/broadcast &lt;b&gt;Bold text&lt;/b&gt; — announcement!</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    broadcast_text = " ".join(context.args)
    db: Database = context.bot_data["db"]
    user_ids = db.get_all_user_ids()

    if not user_ids:
        await update.message.reply_text("📭 No users to broadcast to yet.")
        return

    status_msg = await update.message.reply_text(
        f"📣 Broadcasting to {len(user_ids):,} users..."
    )

    sent = 0
    failed = 0

    for uid in user_ids:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=broadcast_text,
                parse_mode=ParseMode.HTML,
            )
            sent += 1
        except Forbidden:
            failed += 1  # User blocked the bot
        except TelegramError as e:
            logger.warning(f"Broadcast failed for {uid}: {e}")
            failed += 1

        # Respect Telegram rate limits (30 msg/sec to different users)
        await asyncio.sleep(0.05)

    db.log_broadcast(
        admin_id=update.effective_user.id,
        message=broadcast_text,
        sent=sent,
        failed=failed,
    )

    await status_msg.edit_text(
        f"✅ <b>Broadcast complete!</b>\n\n"
        f"📤 Sent:   <b>{sent:,}</b>\n"
        f"❌ Failed: <b>{failed:,}</b>",
        parse_mode=ParseMode.HTML,
    )


async def sequence_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/sequence — show the current reply sequence (admin only)"""
    if not is_admin(update.effective_user.id):
        return

    lines = ["🔁 <b>Current Reply Sequence</b>\n"]
    for step in REPLY_SEQUENCE:
        t = step.get("type", "text")
        icon = {"text": "💬", "photo": "🖼️", "paid_media": "🔒"}.get(t, "❓")
        delay = step.get("delay", 0)
        extra = ""
        if t == "paid_media":
            extra = f" | ⭐ {step.get('star_count', '?')} Stars | {len(step.get('media', []))} item(s)"
        lines.append(
            f"{icon} Step {step['step']}: <b>{t}</b> (delay: {delay}s{extra})"
        )

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start — welcome message"""
    text = (
        "👋 <b>Business Bot is running!</b>\n\n"
        "Connect me to your Telegram Business account:\n"
        "<i>Settings → Business → Chatbots</i>\n\n"
        "Admin commands:\n"
        "• /stats — view statistics\n"
        "• /broadcast — message all users\n"
        "• /sequence — view reply sequence"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ════════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════════

def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN is not set in .env")

    db = Database()

    app = (
        ApplicationBuilder()
        .token(token)
        .post_init(on_startup)
        .build()
    )

    # Share DB instance across all handlers
    app.bot_data["db"] = db

    # ── Handlers ──────────────────────────────────────────────────────────
    app.add_handler(BusinessConnectionHandler(handle_business_connection))

    # Business messages (incoming messages from users to business account)
    app.add_handler(
        MessageHandler(filters.UpdateType.BUSINESS_MESSAGE, handle_business_message)
    )

    # Admin commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("sequence", sequence_command))

    logger.info("🤖 Bot starting — polling for updates...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
