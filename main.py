import os
import asyncio
import base64
import json
from flask import Flask, jsonify
from telethon import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.types import InputPeerChannel
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ───── Настройка Flask ─────
app = Flask(__name__)

# ───── Чтение и сборка session ─────
SESSION_PART1 = os.environ.get("SESSION_PART1")
SESSION_PART2 = os.environ.get("SESSION_PART2")

if not SESSION_PART1 or not SESSION_PART2:
    raise RuntimeError("Session parts not found in environment variables")

session_bytes = base64.b64decode(SESSION_PART1 + SESSION_PART2)
with open("session.session", "wb") as f:
    f.write(session_bytes)

# ───── Настройка Telethon ─────
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
client = TelegramClient("session.session", API_ID, API_HASH)

# ───── Настройка Google Drive ─────
GDRIVE_CREDENTIALS_JSON = os.environ.get("GDRIVE_CREDENTIALS_JSON")
GDRIVE_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID")

if not GDRIVE_CREDENTIALS_JSON or not GDRIVE_FOLDER_ID:
    raise RuntimeError("Google Drive credentials not set")

creds_dict = json.loads(GDRIVE_CREDENTIALS_JSON)
credentials = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/drive.file"])
drive_service = build('drive', 'v3', credentials=credentials)

# ───── Функция для выгрузки на Google Drive ─────
def upload_to_gdrive(file_path, folder_id):
    file_metadata = {'name': os.path.basename(file_path), 'parents': [folder_id]}
    media = MediaFileUpload(file_path, resumable=True)
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    return file.get('id')

# ───── Функция для получения истории канала ─────
async def fetch_posts(channel_username, limit=100):
    entity = await client.get_entity(channel_username)
    history = await client(GetHistoryRequest(
        peer=entity,
        offset_id=0,
        offset_date=None,
        add_offset=0,
        limit=limit,
        max_id=0,
        min_id=0,
        hash=0
    ))
    result = []
    for msg in history.messages:
        if msg.message:
            result.append(f"https://t.me/{channel_username}/{msg.id}, {msg.message}")
    return "\n".join(result)

# ───── Старт клиента один раз при запуске ─────
loop = asyncio.get_event_loop()
loop.run_until_complete(client.start())

# ───── Flask маршрут ─────
@app.route("/run")
async def run_parser():
    channel = os.environ.get("CHANNEL_USERNAME")
    if not channel:
        return "CHANNEL_USERNAME not set", 400
    try:
        text = await fetch_posts(channel, limit=100)
        if not text:
            return "No posts fetched", 500
        filename = "posts.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(text)
        file_id = upload_to_gdrive(filename, GDRIVE_FOLDER_ID)
        return jsonify({"status": "ok", "file_id": file_id})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

# ───── Запуск Flask ─────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
