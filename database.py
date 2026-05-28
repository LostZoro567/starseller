"""
database.py — Supabase integration for the Telegram Business Bot
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client

logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("sb_publishable_NDEYUgrlMjBnXAbsVBAnoQ_cKiE275D")
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
        self.client: Client = create_client(url, key)
        logger.info("✅ Supabase connected")

    # ─── Users ───────────────────────────────────────────────────────────────

    def upsert_user(self, user, business_connection_id: str = None) -> int:
        """
        Insert or update a user record.
        Returns the NEW message_count after incrementing.
        """
        now = datetime.now(timezone.utc).isoformat()

        # Try to fetch existing user
        result = (
            self.client.table("users")
            .select("id, message_count")
            .eq("id", user.id)
            .execute()
        )

        if result.data:
            new_count = result.data[0]["message_count"] + 1
            self.client.table("users").update(
                {
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "message_count": new_count,
                    "last_message_at": now,
                }
            ).eq("id", user.id).execute()
        else:
            new_count = 1
            self.client.table("users").insert(
                {
                    "id": user.id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "message_count": 1,
                    "business_connection_id": business_connection_id,
                    "last_message_at": now,
                    "created_at": now,
                }
            ).execute()
            logger.info(f"🆕 New user: {user.id} (@{user.username})")

        return new_count

    def get_all_user_ids(self) -> list[int]:
        """Return list of all user IDs for broadcast."""
        result = self.client.table("users").select("id").execute()
        return [row["id"] for row in result.data]

    def get_user(self, user_id: int) -> dict | None:
        result = (
            self.client.table("users").select("*").eq("id", user_id).execute()
        )
        return result.data[0] if result.data else None

    # ─── Business Connections ─────────────────────────────────────────────────

    def save_business_connection(self, bc_id: str, owner_id: int, is_enabled: bool):
        now = datetime.now(timezone.utc).isoformat()
        self.client.table("business_connections").upsert(
            {
                "id": bc_id,
                "owner_id": owner_id,
                "is_enabled": is_enabled,
                "updated_at": now,
            }
        ).execute()

    def get_active_connections(self) -> list[dict]:
        """Load all active business connections on startup."""
        result = (
            self.client.table("business_connections")
            .select("*")
            .eq("is_enabled", True)
            .execute()
        )
        return result.data

    # ─── Broadcast Logs ───────────────────────────────────────────────────────

    def log_broadcast(self, admin_id: int, message: str, sent: int, failed: int):
        self.client.table("broadcasts").insert(
            {
                "admin_id": admin_id,
                "message": message[:500],
                "sent_count": sent,
                "failed_count": failed,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ).execute()

    # ─── Stats ────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        week_start = (now - timedelta(days=7)).isoformat()

        total_result = (
            self.client.table("users").select("id", count="exact").execute()
        )
        today_result = (
            self.client.table("users")
            .select("id", count="exact")
            .gte("created_at", today_start)
            .execute()
        )
        week_result = (
            self.client.table("users")
            .select("id", count="exact")
            .gte("created_at", week_start)
            .execute()
        )
        msg_result = self.client.table("users").select("message_count").execute()
        broadcast_result = (
            self.client.table("broadcasts").select("id", count="exact").execute()
        )

        total_messages = sum(r["message_count"] for r in msg_result.data)

        return {
            "total_users": total_result.count or 0,
            "new_today": today_result.count or 0,
            "new_this_week": week_result.count or 0,
            "total_messages": total_messages,
            "total_broadcasts": broadcast_result.count or 0,
        }
