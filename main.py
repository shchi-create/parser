import os
import base64
import asyncio
import nest_asyncio
from telethon import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
from flask import Flask, jsonify

# --- Настройка Flask ---
app = Flask(__name__)

# --- Настройка nest_asyncio для работы внутри Flask ---
nest_asyncio.apply()

# --- Получение session из двух переменных окружения ---
SESSION_PART1 = os.environ.get("SESSION_PART1")
SESSION_PART2 = os.environ.get("SESSION_PART2")

if not SESSION_PART1 or not SESSION_PART2:
    raise RuntimeError("Session parts not found in environment variables")

# Объединяем и декодируем session
session_bytes = base64.b64decode(SESSION_PART1 + SESSION_PART2)
SESSION_FILE = "session.session"
with open(SESSION_FILE, "wb") as f:
    f.write(session_bytes)

# --- Настройки TelegramClient ---
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")

client = TelegramClient(SESSION_FILE, API_ID, API_HASH)

# --- Асинхронная функция для парсинга ---
async def run_parser():
    await client.start()
    try:
        # Пример получения истории сообщений из канала/чата
        entity = await client.get_entity('some_channel_or_user')
        history = await client(GetHistoryRequest(
            peer=entity,
            limit=5,
            offset_date=None,
            offset_id=0,
            max_id=0,
            min_id=0,
            add_offset=0,
            hash=0
        ))
        return [msg.to_dict() for msg in history.messages]
    except Exception as e:
        print("ERROR fetching history:", e)
        return {"error": str(e)}

# --- Flask route для запуска парсера ---
@app.route("/run", methods=["GET"])
def run():
    try:
        # Запуск асинхронного парсера внутри Flask
        data = asyncio.run(run_parser())
        return jsonify(data)
    except Exception as e:
        print("ERROR in /run:", e)
        return jsonify({"error": str(e)}), 500

# --- Запуск Flask ---
if __name__ == "__main__":
    print(f"SESSION_PART1 length: {len(SESSION_PART1)}")
    print(f"SESSION_PART2 length: {len(SESSION_PART2)}")
    app.run(host="0.0.0.0", port=8080)
