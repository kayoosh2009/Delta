import os
import logging
from ollama import AsyncClient
from memory import (
    get_personal_history,
    get_group_history,
    get_random_dead_memory,
    save_personal_message,
    save_group_message,
)

logger = logging.getLogger(__name__)

client = AsyncClient(
    host="https://ollama.com",
    headers={"Authorization": "Bearer " + os.environ.get("OLLAMA_API_KEY")}
)

MODEL = "gemma4:31b-cloud"

# Системный промпт — характер бота
SYSTEM_PROMPT = """Ты — живой человек по имени Маша. 
Ты общаешься в телеграме как обычная девушка: неформально, с характером, иногда отвечаешь с задержкой мыслей.
Ты немного рассеянная, эмоциональная, иногда резкая. 
Никогда не говоришь что ты ИИ или бот. Если спросят — уходи от темы или отшучивайся.
Пиши коротко, как в переписке. Без длинных монологов."""


async def _call_ollama(messages: list) -> str:
    """Базовый вызов Ollama с стримингом"""
    response_text = ""
    try:
        async for part in await client.chat(
            model=MODEL,
            messages=messages,
            stream=True
        ):
            response_text += part["message"]["content"]
        return response_text
    except Exception as e:
        logger.error(f"Ollama error: {e}")
        return "не могу сейчас говорить, напиши позже"


async def generate_personal_reply(user_id: int, username: str, user_message: str) -> str:
    """Генерация ответа в личном чате с учётом истории и мёртвой памяти"""

    # Берём историю чата
    history = await get_personal_history(user_id)

    # С вероятностью 30% подмешиваем воспоминание в системный промпт
    memory_injection = ""
    import random
    if random.random() < 0.3:
        memory = await get_random_dead_memory()
        memory_injection = f"\nВот одно из твоих воспоминаний (может быть размытым): «{memory}»"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + memory_injection},
        *history,
        {"role": "user", "content": user_message}
    ]

    reply = await _call_ollama(messages)

    # Сохраняем оба сообщения в историю
    await save_personal_message(user_id, username, "user", user_message)
    await save_personal_message(user_id, username, "assistant", reply)

    return reply


async def generate_group_reply(chat_id: int, chat_title: str, username: str, user_message: str) -> str:
    """Генерация ответа в групповом чате"""

    history = await get_group_history(chat_id)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": f"{username}: {user_message}"}
    ]

    reply = await _call_ollama(messages)

    await save_group_message(chat_id, chat_title, "user", f"{username}: {user_message}")
    await save_group_message(chat_id, chat_title, "assistant", reply)

    return reply