import os
import asyncio
import logging
import random
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.chat_action import ChatActionSender

from ai import generate_personal_reply, generate_group_reply
from diary import publish_diary_post, publish_diary_event, CHANNEL_CHAT_ID

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
#  ОЧЕРЕДЬ: бот не пишет двум сразу
# ──────────────────────────────────────────────

_active_chat: int | None = None  # ID чата который сейчас обрабатывается
_active_lock = asyncio.Lock()

# ──────────────────────────────────────────────
#  БУФЕР: ждём конца печатания пользователя
# ──────────────────────────────────────────────

# user_id -> последнее сообщение + таймер
_user_buffers: dict[int, list[str]] = {}
_user_timers: dict[int, asyncio.Task] = {}
TYPING_WAIT = 4.0  # секунд ждём после последнего сообщения


async def _send_reply_parts(chat_id: int, parts: list[str], reply_to: int | None = None):
    """Отправляет список сообщений с паузами между ними"""
    for i, part in enumerate(parts):
        async with ChatActionSender.typing(bot=bot, chat_id=chat_id):
            # Пауза имитирует набор текста
            typing_delay = min(len(part) * 0.04, 6.0)
            await asyncio.sleep(typing_delay)

        if i == 0 and reply_to:
            await bot.send_message(chat_id, part, reply_to_message_id=reply_to)
        else:
            await bot.send_message(chat_id, part)

        # Пауза между сообщениями как у живого человека
        if i < len(parts) - 1:
            await asyncio.sleep(random.uniform(0.8, 2.5))


async def _process_personal(
    user_id: int,
    username: str,
    chat_id: int,
    messages: list[str],
    reply_to: int | None
):
    """Обрабатывает накопленные сообщения пользователя"""
    global _active_chat

    # Ждём пока бот освободится
    async with _active_lock:
        _active_chat = chat_id
        try:
            combined = " ".join(messages)
            parts, should_post = await generate_personal_reply(user_id, username, combined)
            await _send_reply_parts(chat_id, parts, reply_to)

            if should_post:
                logger.info(f"Interesting conversation with {username}, posting to diary...")
                await publish_diary_event(bot, combined, " ".join(parts))
        finally:
            _active_chat = None


async def _flush_user_buffer(
    user_id: int,
    username: str,
    chat_id: int,
    reply_to: int | None
):
    """Вызывается когда таймер истёк — пользователь перестал печатать"""
    messages = _user_buffers.pop(user_id, [])
    _user_timers.pop(user_id, None)

    if not messages:
        return

    await _process_personal(user_id, username, chat_id, messages, reply_to)


# ──────────────────────────────────────────────
#  ХЭНДЛЕРЫ
# ──────────────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await asyncio.sleep(random.uniform(1.0, 3.0))
    await message.answer(random.choice([
        "а, привет... не ожидала",
        "о, ты написал. привет",
        "привет) давно не общались",
    ]))


@dp.message(F.text & F.chat.type == "private")
async def handle_personal_message(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)
    chat_id = message.chat.id

    # Добавляем сообщение в буфер
    if user_id not in _user_buffers:
        _user_buffers[user_id] = []
    _user_buffers[user_id].append(message.text)

    # Сбрасываем таймер если уже был
    if user_id in _user_timers:
        _user_timers[user_id].cancel()

    # Запускаем новый таймер
    _user_timers[user_id] = asyncio.create_task(
        _wait_and_flush(user_id, username, chat_id, message.message_id)
    )


async def _wait_and_flush(user_id: int, username: str, chat_id: int, reply_to: int):
    """Ждёт TYPING_WAIT секунд и запускает обработку"""
    await asyncio.sleep(TYPING_WAIT)
    await _flush_user_buffer(user_id, username, chat_id, reply_to)


@dp.message(F.photo & F.chat.type == "private")
async def handle_photo(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)
    caption = message.caption or ""
    fake_content = f"[прислал фото] {caption}".strip()

    async with _active_lock:
        parts, should_post = await generate_personal_reply(user_id, username, fake_content)
        await _send_reply_parts(message.chat.id, parts, message.message_id)


@dp.message(F.sticker & F.chat.type == "private")
async def handle_sticker(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)
    emoji = message.sticker.emoji or "стикер"
    fake_content = f"[прислал стикер: {emoji}]"

    async with _active_lock:
        parts, _ = await generate_personal_reply(user_id, username, fake_content)
        await _send_reply_parts(message.chat.id, parts, message.message_id)


@dp.message(F.text & F.chat.type.in_({"group", "supergroup"}))
async def handle_group_message(message: types.Message):
    bot_info = await bot.get_me()
    bot_username = f"@{bot_info.username}"

    is_reply_to_bot = (
        message.reply_to_message and
        message.reply_to_message.from_user.id == bot_info.id
    )
    is_mentioned = bot_username.lower() in (message.text or "").lower()

    if not is_reply_to_bot and not is_mentioned:
        if random.random() > 0.05:
            return

    chat_id = message.chat.id
    chat_title = message.chat.title or str(chat_id)
    username = message.from_user.username or message.from_user.first_name

    async with _active_lock:
        parts, _ = await generate_group_reply(chat_id, chat_title, username, message.text)
        await _send_reply_parts(chat_id, parts, message.message_id)


@dp.message(F.text & F.chat.id == CHANNEL_CHAT_ID)
async def handle_diary_comment(message: types.Message):
    if random.random() > 0.4:
        return
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name

    async with _active_lock:
        parts, _ = await generate_personal_reply(user_id, username, message.text)
        await _send_reply_parts(message.chat.id, parts, message.message_id)


# ──────────────────────────────────────────────
#  ФОНОВЫЕ ЗАДАЧИ
# ──────────────────────────────────────────────

async def background_tasks():
    await asyncio.sleep(5)

    if random.random() < 0.6:
        logger.info("Publishing diary post on startup...")
        await publish_diary_post(bot)

    while True:
        wait_minutes = random.uniform(30, 90)
        await asyncio.sleep(wait_minutes * 60)
        if random.random() < 0.5:
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