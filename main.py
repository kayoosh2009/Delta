import os
import asyncio
import logging
import random
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.chat_action import ChatActionSender
from ollama import AsyncClient

from memory import (
    get_personal_history,
    get_group_history,
    get_random_dead_memory,
    save_personal_message,
    save_group_message,
    add_dead_memory,
)
from ai import generate_personal_reply, generate_group_reply
from diary import publish_diary_post, read_diary_comments, CHANNEL_CHAT_ID

# ──────────────────────────────────────────────
#  ИНИЦИАЛИЗАЦИЯ
# ──────────────────────────────────────────────

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ──────────────────────────────────────────────
#  ТАЙМИНГИ (имитация живого человека)
# ──────────────────────────────────────────────

async def human_delay(text: str):
    """
    Двухфазная задержка:
    1. Пауза 'заметила сообщение' (1-5 сек)
    2. Пауза 'набирает текст' (зависит от длины ответа)
    """
    read_delay = random.uniform(1.5, 5.0)
    await asyncio.sleep(read_delay)

    typing_delay = min(len(text) * 0.04, 8.0)
    await asyncio.sleep(typing_delay)


# ──────────────────────────────────────────────
#  ХЭНДЛЕР: /start
# ──────────────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await asyncio.sleep(random.uniform(1.0, 3.0))
    await message.answer(
        random.choice([
            "а, привет... не ожидала",
            "о, ты написал. привет",
            "привет) давно не общались",
        ])
    )


# ──────────────────────────────────────────────
#  ХЭНДЛЕР: текст в личке
# ──────────────────────────────────────────────

@dp.message(F.text & F.chat.type == "private")
async def handle_personal_message(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)

    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        reply = await generate_personal_reply(user_id, username, message.text)
        await human_delay(reply)

    await message.answer(reply)


# ──────────────────────────────────────────────
#  ХЭНДЛЕР: текст в группе
# ──────────────────────────────────────────────

@dp.message(F.text & F.chat.type.in_({"group", "supergroup"}))
async def handle_group_message(message: types.Message):
    # В группе отвечаем только если упомянули бота или ответили на его сообщение
    bot_info = await bot.get_me()
    bot_username = f"@{bot_info.username}"

    is_reply_to_bot = (
        message.reply_to_message and
        message.reply_to_message.from_user.id == bot_info.id
    )
    is_mentioned = bot_username.lower() in (message.text or "").lower()

    if not is_reply_to_bot and not is_mentioned:
        # Иногда (5%) реагируем без упоминания — как живой человек
        if random.random() > 0.05:
            return

    chat_id = message.chat.id
    chat_title = message.chat.title or str(chat_id)
    username = message.from_user.username or message.from_user.first_name

    async with ChatActionSender.typing(bot=bot, chat_id=chat_id):
        reply = await generate_group_reply(chat_id, chat_title, username, message.text)
        await human_delay(reply)

    await message.answer(reply)


# ──────────────────────────────────────────────
#  ХЭНДЛЕР: фото в личке
# ──────────────────────────────────────────────

@dp.message(F.photo & F.chat.type == "private")
async def handle_photo(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)

    caption = message.caption or ""
    fake_content = f"[пользователь прислал фото] {caption}".strip()

    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        reply = await generate_personal_reply(user_id, username, fake_content)
        await human_delay(reply)

    await message.answer(reply)


# ──────────────────────────────────────────────
#  ХЭНДЛЕР: стикер в личке
# ──────────────────────────────────────────────

@dp.message(F.sticker & F.chat.type == "private")
async def handle_sticker(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)

    emoji = message.sticker.emoji or "стикер"
    fake_content = f"[пользователь прислал стикер: {emoji}]"

    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        reply = await generate_personal_reply(user_id, username, fake_content)
        await human_delay(reply)

    await message.answer(reply)


# ──────────────────────────────────────────────
#  ХЭНДЛЕР: комментарии в дневнике (ТГК)
# ──────────────────────────────────────────────

@dp.message(F.text & F.chat.id == CHANNEL_CHAT_ID)
async def handle_diary_comment(message: types.Message):
    """Бот читает комментарии в своём канале и иногда отвечает"""
    if random.random() > 0.4:  # отвечает в 40% случаев
        return

    username = message.from_user.username or message.from_user.first_name
    user_id = message.from_user.id

    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        reply = await generate_personal_reply(user_id, username, message.text)
        await human_delay(reply)

    await message.reply(reply)


# ──────────────────────────────────────────────
#  ФОНОВАЯ ЗАДАЧА: дневник + "вспомнила написать"
# ──────────────────────────────────────────────

async def background_tasks():
    """
    Запускается при старте сервера (cold start на Render).
    Бот 'вспоминает' что хотела написать или публикует в дневник.
    """
    await asyncio.sleep(5)  # дать боту прогрузиться

    # С вероятностью 60% публикует пост в дневник при старте сервера
    if random.random() < 0.6:
        logger.info("Publishing diary post on startup...")
        await publish_diary_post(bot)

    # Периодически пишем в дневник пока сервер живёт
    while True:
        # Ждём от 30 до 90 минут
        wait_minutes = random.uniform(30, 90)
        await asyncio.sleep(wait_minutes * 60)

        if random.random() < 0.5:
            logger.info("Scheduled diary post...")
            await publish_diary_post(bot)


# ──────────────────────────────────────────────
#  ЗАПУСК
# ──────────────────────────────────────────────

async def main():
    logger.info("Bot starting...")
    asyncio.create_task(background_tasks())
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped.")