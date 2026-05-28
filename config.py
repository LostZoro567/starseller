"""
╔══════════════════════════════════════════════════════════╗
║              AUTO-REPLY CONFIGURATION                    ║
║  Edit the messages below — nothing else needs changing   ║
╚══════════════════════════════════════════════════════════╝

Only fires on a user's VERY FIRST message ever.
All repeat messages are ignored (you reply manually).

TIMING:
  MSG_1_DELAY  → seconds after user's message before first reply appears
  MSG_2_DELAY  → seconds after first reply before second reply appears

TYPING SIMULATION:
  TYPING_SPEED → fake "characters per second" while typing indicator shows
                 higher = shorter typing animation (default 20 is natural)

PLACEHOLDERS you can use in message text:
  {name}      → user's first name
  {username}  → @username (empty string if they have none)
"""

# ── Delays (seconds) ──────────────────────────────────────────────────────────
MSG_1_DELAY   = 10   # wait before first message appears
MSG_2_DELAY   = 6    # wait after first message before second

# ── Typing speed (chars/sec) — controls how long "typing…" shows ─────────────
TYPING_SPEED  = 18   # lower = slower typer, higher = faster

# ── Message 1 — warm, human acknowledgment ───────────────────────────────────
MESSAGE_1 = "Hey! Got your message 👋"

# ── Message 2 — casual redirect (add your bot link below) ────────────────────
MESSAGE_2 = (
    "Btw just dropped something new — Best collection in telergam\n"
    "→ https://t.me/Bestcollectionstuff_bot\n"
    "Lmk if you grab it 🔥"
)
