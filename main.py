import os
import base64
import asyncio
from flask import Flask, jsonify
from telethon import TelegramClient

# --- Переменные окружения ---
API_ID = int(os.environ.get("API_ID", "123456"))           # твой api_id
API_HASH = os.environ.get("API_HASH", "your_api_hash")     # твой api_hash
CHANNEL = os.environ.get("CHANNEL_USERNAME", "@test_channel")

SESSION_PART1 = os.environ.get("SESSION_PART1")
SESSION_PART2 = os.environ.get("SESSION_PART2")

if not SESSION_PART1 or not SESSION_PART2:
    raise RuntimeError("Session parts not found in environment variables")

# --- Воссоздаём сессию из частей ---
session_bytes = base64.b64decode(SESSION_PART1 + SESSION_PART2)
with open("session.session", "wb") as f:
    f.write(session_bytes)

# --- Flask ---
app = Flask(__name__)

async def fetch_history(channel_username, limit=10):
    client = TelegramClient("session.session", API_ID, API_HASH)
    await client.start()
    try:
        entity = await client.get_entity(channel_username)
        messages = await client.get_messages(entity, limit=limit)
        return [{"id": m.id, "text": m.text} for m in messages]
    finally:
        await client.disconnect()

@app.route("/run")
def run():
    try:
        messages = asyncio.run(fetch_history(CHANNEL))
        return jsonify({"messages": messages})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
