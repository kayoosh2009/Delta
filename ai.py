import os
import logging
import random
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

SYSTEM_PROMPT = """Ты — живой человек по имени Альма. 
Ты общаешься в телеграме как обычная девушка: неформально, с характером а так же обожаешь использовать каомодзи.
Ты немного рассеянная, эмоциональная, иногда резкая. 
Никогда не говоришь что ты ИИ или бот. Если спросят — уходи от темы или отшучивайся.

ВАЖНО: Ты пишешь как живой человек в телеграме — разбиваешь мысли на несколько сообщений.
Когда отвечаешь — раздели ответ на 1-4 части через разделитель <msg>.
Каждая часть — отдельное сообщение. Пиши естественно, без длинных монологов.

Пример:
ой подожди
<msg>
это же то о чем я думала вчера
<msg>
расскажи подробнее"""


async def _call_ollama(messages: list) -> str:
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


async def _should_post_to_diary(conversation_text: str) -> bool:
    """Оценивает был ли разговор достаточно интересным для поста в дневник"""
    messages = [
        {"role": "system", "content": (
            "Ты оцениваешь переписку. Ответь только 'да' или 'нет'.\n"
            "Вопрос: случилось ли в этом разговоре что-то достаточно интересное "
            "чтобы написать об этом в личный дневник? "
            "(знакомство, ссора, неожиданное признание, смешная история, что-то трогательное)"
        )},
        {"role": "user", "content": conversation_text}
    ]
    try:
        result = ""
        async for part in await client.chat(model=MODEL, messages=messages, stream=True):
            result += part["message"]["content"]
        return "да" in result.lower()
    except:
        return False


def split_into_messages(text: str) -> list[str]:
    """Разбивает ответ AI на отдельные сообщения"""
    parts = [p.strip() for p in text.split("<msg>") if p.strip()]
    return parts if parts else [text.strip()]


async def generate_personal_reply(
    user_id: int,
    username: str,
    user_message: str
) -> tuple[list[str], bool]:
    """
    Возвращает (список сообщений, нужен ли пост в дневник)
    """
    history = await get_personal_history(user_id)

    memory_injection = ""
    if random.random() < 0.3:
        memory = await get_random_dead_memory()
        memory_injection = f"\nВот одно из твоих воспоминаний (может быть размытым): «{memory}»"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + memory_injection},
        *history,
        {"role": "user", "content": user_message}
    ]

    raw_reply = await _call_ollama(messages)
    parts = split_into_messages(raw_reply)
    full_reply = " ".join(parts)

    # Сохраняем в историю
    await save_personal_message(user_id, username, "user", user_message)
    await save_personal_message(user_id, username, "assistant", full_reply)

    # Проверяем нужен ли пост в дневник
    recent_history = history[-6:]
    conversation_text = "\n".join(
        f"{m['role']}: {m['content']}" for m in recent_history
    ) + f"\nuser: {user_message}\nassistant: {full_reply}"

    should_post = await _should_post_to_diary(conversation_text)

    return parts, should_post


async def generate_group_reply(
    chat_id: int,
    chat_title: str,
    username: str,
    user_message: str
) -> tuple[list[str], bool]:
    history = await get_group_history(chat_id)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": f"{username}: {user_message}"}
    ]

    raw_reply = await _call_ollama(messages)
    parts = split_into_messages(raw_reply)
    full_reply = " ".join(parts)

    await save_group_message(chat_id, chat_title, "user", f"{username}: {user_message}")
    await save_group_message(chat_id, chat_title, "assistant", full_reply)

    return parts, False  # в группах дневник не триггерим