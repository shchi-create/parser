import os
import base64
import json
from flask import Flask, jsonify
import nest_asyncio
import asyncio

from telethon import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.types import InputPeerChannel

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ─────────────── Настройка ───────────────
nest_asyncio.apply()  # позволяет использовать Telethon в Flask

app = Flask(__name__)

# Telegram API
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]

# Воссоздаём сессию из двух переменных
session_data = base64.b64decode(os.environ["SESSION_PART1"] + os.environ["SESSION_PART2"])
with open("session.session", "wb") as f:
    f.write(session_data)

client = TelegramClient("session.session", API_ID, API_HASH)

# Google Drive
GDRIVE_CREDS_JSON = os.environ["GDRIVE_CREDENTIALS_JSON"]
creds_dict = json.loads(GDRIVE_CREDS_JSON)
SCOPES = ['https://www.googleapis.com/auth/drive.file']
credentials = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=credentials)
GDRIVE_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID")  # папка, куда грузим

# ─────────────── Функции ───────────────
async def fetch_posts(channel_username, limit=100):
    try:
        entity = await client.get_entity(channel_username)
        history = await client(GetHistoryRequest(
            peer=entity,
            limit=limit,
            offset_date=None,
            offset_id=0,
            max_id=0,
            min_id=0,
            add_offset=0,
            hash=0
        ))
        posts = []
        for msg in reversed(history.messages):
            if msg.message:
                posts.append(f"https://t.me/{channel_username}/{msg.id}, {msg.message}")
        return "\n".join(posts)
    except Exception as e:
        print("ERROR fetching history:", e)
        return ""

def upload_to_gdrive(filename, folder_id):
    file_metadata = {"name": filename, "parents": [folder_id]} if folder_id else {"name": filename}
    media = MediaFileUpload(filename, mimetype="text/plain")
    file = drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    print(f"Uploaded file ID: {file.get('id')}")
    return file.get("id")

# ─────────────── Маршрут ───────────────
@app.route("/run")
async def run_parser():
    await client.start()
    channel = os.environ.get("CHANNEL_USERNAME")  # имя канала без @
    if not channel:
        return "CHANNEL_USERNAME not set", 400

    text = await fetch_posts(channel, limit=100)
    if not text:
        return "No posts fetched", 500

    filename = "posts.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(text)

    file_id = upload_to_gdrive(filename, GDRIVE_FOLDER_ID)
    return jsonify({"status": "ok", "file_id": file_id})

# ─────────────── Запуск ───────────────
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(client.start())
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
