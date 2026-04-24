import os
import logging
import random
from aiogram import Bot
from ollama import AsyncClient
from memory import get_random_dead_memory, add_dead_memory

logger = logging.getLogger(__name__)

CHANNEL_ID = -1003541940435    # сам канал (публикация постов)
CHANNEL_CHAT_ID = -1003908998969  # чат канала (комментарии)

client = AsyncClient(
    host="https://ollama.com",
    headers={"Authorization": "Bearer " + os.environ.get("OLLAMA_API_KEY")}
)

MODEL = "gemma4:31b-cloud"

DIARY_SYSTEM_PROMPT = """Ты — живая девушка по имени Маша. 
Это твой личный телеграм-канал где ты пишешь о своей жизни, мыслях, настроении.
Пиши как обычный человек ведёт канал: коротко, лично, иногда с эмоциями.
Без хэштегов, без официоза. Это дневник, не блог."""

DIARY_TRIGGERS = [
    "что-то сегодня странное настроение",
    "думаю о том что было раньше",
    "хочу написать кое-что важное",
    "не могу перестать думать об одном",
    "вспомнила кое-что из прошлого",
    "сегодня случилось кое-что интересное",
]


async def _generate_diary_post(trigger: str, memory: str) -> str:
    """Генерация поста для дневника"""
    messages = [
        {"role": "system", "content": DIARY_SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"Напиши короткий пост в свой канал. "
            f"Настроение/мысль: «{trigger}». "
            f"Вот одно из твоих воспоминаний (используй если подходит): «{memory}»"
        )}
    ]
    response_text = ""
    try:
        async for part in await client.chat(model=MODEL, messages=messages, stream=True):
            response_text += part["message"]["content"]
        return response_text
    except Exception as e:
        logger.error(f"Diary generation error: {e}")
        return None


async def publish_diary_post(bot: Bot):
    """Публикует пост в канал и сохраняет его как воспоминание"""
    trigger = random.choice(DIARY_TRIGGERS)
    memory = await get_random_dead_memory()

    post_text = await _generate_diary_post(trigger, memory)
    if not post_text:
        return

    try:
        await bot.send_message(chat_id=CHANNEL_ID, text=post_text)
        logger.info("Diary post published")

        # Сам пост становится новым воспоминанием
        await add_dead_memory(post_text)
    except Exception as e:
        logger.error(f"Failed to publish diary post: {e}")


async def read_diary_comments(bot: Bot) -> list[dict]:
    """
    Читает последние комментарии в чате канала.
    Возвращает список {user, text} для обработки в main.py
    """
    try:
        updates = await bot.get_updates()
        comments = []
        for update in updates:
            if update.message and update.message.chat.id == CHANNEL_CHAT_ID:
                comments.append({
                    "user": update.message.from_user.username or "аноним",
                    "text": update.message.text or ""
                })
        return comments
    except Exception as e:
        logger.error(f"read_diary_comments error: {e}")
        return []