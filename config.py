"""
╔══════════════════════════════════════════════════════════╗
║           REPLY SEQUENCE CONFIGURATION                   ║
║  Edit this file to customize your bot's auto-replies     ║
╚══════════════════════════════════════════════════════════╝

Each step fires when a user sends their Nth message to your business account.

STEP TYPES:
  "text"        → plain text message (supports {name} and {username} placeholders)
  "photo"       → single image (free)
  "paid_media"  → photo(s)/video(s) behind a Stars paywall

DELAY:
  delay (seconds) before sending — simulates human response time

PAID MEDIA NOTES:
  - star_count: how many Telegram Stars the user must pay (min 1)
  - media: list of Telegram file_ids OR public HTTPS image URLs
  - To get a file_id: send the photo to @RawDataBot and copy the file_id
  - Multiple items = a paid media bundle (up to 10 items)
"""

REPLY_SEQUENCE = [
    # ── STEP 1 ── First message user sends
    {
        "step": 1,
        "type": "text",
        "delay": 2,
        "content": (
            "Hey {name}! 👋 Thanks for reaching out.\n\n"
            "I'll get back to you shortly. In the meantime, here's what I offer:\n"
            "• Premium content & exclusives\n"
            "• Behind-the-scenes material\n"
            "• Direct Q&A\n\n"
            "Stay tuned! 🔥"
        ),
    },

    # ── STEP 2 ── Second message user sends
    {
        "step": 2,
        "type": "text",
        "delay": 3,
        "content": (
            "Still here, {name}! 😄\n\n"
            "I've got some exclusive content available — just for people like you.\n"
            "Send one more message to unlock a special preview 👇"
        ),
    },

    # ── STEP 3 ── Third message → paid content unlock
    {
        "step": 3,
        "type": "paid_media",
        "delay": 1,
        "star_count": 15,                      # Cost in Telegram Stars
        "caption": "🔒 Exclusive Bundle — Unlock with Stars!",
        "media": [
            # Add your Telegram file_ids or public image URLs here.
            # Example file_id (replace with your own):
            # "AgACAgIAAxkBAAIBZWXyR..."
            # Example public URL:
            "https://picsum.photos/800/600?random=1",
            "https://picsum.photos/800/600?random=2",
            "https://picsum.photos/800/600?random=3",
        ],
    },

    # ── STEP 4 ── Fourth message → free follow-up text
    {
        "step": 4,
        "type": "text",
        "delay": 2,
        "content": (
            "Hope you enjoyed the content, {name}! 🙌\n\n"
            "More drops coming soon. Follow me to stay updated!"
        ),
    },

    # Add more steps below as needed...
    # {
    #     "step": 5,
    #     "type": "paid_media",
    #     "delay": 0,
    #     "star_count": 50,
    #     "caption": "🎬 Premium Video Bundle",
    #     "media": [
    #         "AgACAgIAAxkBAAI...",   # video file_id
    #     ],
    # },
]

# ── After the sequence ends ──────────────────────────────────────────────────
# What to send when a user messages BEYOND the last defined step.
# Set to None to send nothing.
FALLBACK_REPLY = (
    "Hey {name}! Thanks for the message — I'll reply personally soon. 💬"
)

# ── Settings ─────────────────────────────────────────────────────────────────
MAX_DELAY_SECONDS = 30   # Hard cap on any single step's delay (safety)
