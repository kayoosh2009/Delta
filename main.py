import os
import logging
from dotenv import load_dotenv
from supabase import create_client, Client
import random

# --- Загрузка ключей ---
load_dotenv()

supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  ЛИЧНАЯ ПАМЯТЬ (приватные чаты)
# ──────────────────────────────────────────────

async def get_personal_history(user_id: int) -> list:
    try:
        response = supabase.table("personal_chats") \
            .select("chat_history") \
            .eq("user_id", user_id) \
            .execute()
        if response.data:
            return response.data[0]["chat_history"]
        return []
    except Exception as e:
        logger.error(f"get_personal_history error: {e}")
        return []

async def save_personal_message(user_id: int, username: str, role: str, content: str):
    try:
        history = await get_personal_history(user_id)
        history.append({"role": role, "content": content})
        history = history[-20:]  # Скользящее окно

        supabase.table("personal_chats").upsert({
            "user_id": user_id,
            "username": username,
            "chat_history": history,
            "updated_at": "now()"
        }).execute()
    except Exception as e:
        logger.error(f"save_personal_message error: {e}")


# ──────────────────────────────────────────────
#  ОБЩАЯ ПАМЯТЬ (групповые чаты)
# ──────────────────────────────────────────────

async def get_group_history(chat_id: int) -> list:
    try:
        response = supabase.table("group_chats") \
            .select("chat_history") \
            .eq("chat_id", chat_id) \
            .execute()
        if response.data:
            return response.data[0]["chat_history"]
        return []
    except Exception as e:
        logger.error(f"get_group_history error: {e}")
        return []

async def save_group_message(chat_id: int, chat_title: str, role: str, content: str):
    try:
        history = await get_group_history(chat_id)
        history.append({"role": role, "content": content})
        history = history[-30:]

        supabase.table("group_chats").upsert({
            "chat_id": chat_id,
            "chat_title": chat_title,
            "chat_history": history,
            "updated_at": "now()"
        }).execute()
    except Exception as e:
        logger.error(f"save_group_message error: {e}")


# ──────────────────────────────────────────────
#  МЁРТВАЯ ПАМЯТЬ (деградирующие воспоминания)
# ──────────────────────────────────────────────

def _decay_text(text: str, decay: float) -> str:
    if decay >= 1.0:
        return text
    words = text.split()
    result = []
    for word in words:
        if random.random() < decay:
            result.append(word)
        else:
            result.append("...")
    return " ".join(result)

async def get_random_dead_memory() -> str:
    try:
        response = supabase.table("dead_memory") \
            .select("id, content, decay") \
            .execute()
        if not response.data:
            return "Я ничего не помню о своём прошлом..."

        memory = random.choice(response.data)
        decayed = _decay_text(memory["content"], memory["decay"])

        new_decay = max(0.05, memory["decay"] - random.uniform(0.03, 0.08))
        supabase.table("dead_memory").update({"decay": new_decay}) \
            .eq("id", memory["id"]) \
            .execute()

        return decayed
    except Exception as e:
        logger.error(f"get_random_dead_memory error: {e}")
        return "Что-то мелькнуло в памяти, но я не могу вспомнить..."

async def add_dead_memory(content: str):
    try:
        supabase.table("dead_memory").insert({
            "content": content,
            "decay": 1.0
        }).execute()
    except Exception as e:
        logger.error(f"add_dead_memory error: {e}")