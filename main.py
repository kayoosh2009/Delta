import os
import asyncio
import logging
import random
from dotenv import load_dotenv

# Библиотеки для бота и ИИ
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.chat_action import ChatActionSender
from ollama import AsyncClient # Используем асинхронную версию

# Загрузка переменных из .env
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
OLLAMA_KEY = os.getenv("OLLAMA_API_KEY")

# Инициализация объектов
bot = Bot(token=TOKEN)
dp = Dispatcher()
# Указываем хост и заголовки для Ollama Cloud
client = AsyncClient(
    host="https://ollama.com",
    headers={'Authorization': f'Bearer {OLLAMA_KEY}'}
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)

async def get_ai_response(context_messages):
    """Функция для общения с Gemma 4"""
    response_text = ""
    async for part in await client.chat(
        model='gemma4:31b-cloud', 
        messages=context_messages, 
        stream=True
    ):
        response_text += part['message']['content']
    return response_text

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("... (бот медленно открывает глаза) ... Привет. Кажется, я тебя помню. Или нет?")

@dp.message(F.text)
async def handle_message(message: types.Message):
    # Имитация "чтения" и "обдумывания"
    # На Render сервер уже проснулся, теперь делаем вид, что мы человек
    read_delay = random.uniform(1.5, 4.0)
    await asyncio.sleep(read_delay)
    
    # Включаем статус "печатает"
    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        # Формируем контекст (пока базовый, без БД)
        # В будущем сюда добавим вызовы из Supabase (Общая, Личная, Мертвая базы)
        context = [
            {"role": "system", "content": "Ты живой человек со сложным характером. Ты слегка забывчива и эмоциональна."},
            {"role": "user", "content": message.text}
        ]
        
        # Получаем ответ от нейронки
        reply = await get_ai_response(context)
        
        # Дополнительная задержка перед отправкой, имитирующая набор текста
        typing_delay = len(reply) * 0.05 # 0.05 сек на каждый символ
        await asyncio.sleep(min(typing_delay, 7.0)) # Но не более 7 секунд
        
        await message.answer(reply)

async def main():
    # Запуск бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот ушел спать...")