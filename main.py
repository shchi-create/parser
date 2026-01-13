from flask import Flask, jsonify
from telethon import TelegramClient
import os

# Настройки Telethon
API_ID = int(os.environ.get("API_ID", 123456))         # твой api_id
API_HASH = os.environ.get("API_HASH", "your_api_hash") # твой api_hash
SESSION_FILE = "session.session"                       # имя файла сессии

app = Flask(__name__)

# Асинхронная функция для получения сообщений
async def fetch_history(channel_username, limit=10):
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.start()
    try:
        entity = await client.get_entity(channel_username)
        messages = await client.get_messages(entity, limit=limit)
        result = [{"id": m.id, "text": m.text} for m in messages]
    finally:
        await client.disconnect()
    return result

# Flask маршрут
@app.route("/run")
def run():
    channel = os.environ.get("CHANNEL_USERNAME", "@test_channel")  # канал из переменной окружения
    try:
        messages = asyncio.run(fetch_history(channel))
        return jsonify({"messages": messages})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
