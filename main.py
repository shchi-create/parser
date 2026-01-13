import os
import asyncio
from datetime import datetime, timedelta, timezone
from flask import Flask
from telethon import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.service_account import Credentials

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
CHANNEL = os.environ.get("CHANNEL")
GDRIVE_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID")

client = TelegramClient("session", API_ID, API_HASH)

SCOPES = ['https://www.googleapis.com/auth/drive.file']
creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

app = Flask(__name__)

async def run_parser():
    await client.start()
    entity = await client.get_entity(CHANNEL)
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    offset_id = 0
    limit = 100
    filename = "/tmp/weekly_news.txt"

    with open(filename, "w", encoding="utf-8") as f:
        while True:
            history = await client(GetHistoryRequest(
                peer=entity,
                offset_id=offset_id,
                offset_date=None,
                add_offset=0,
                limit=limit,
                max_id=0,
                min_id=0,
                hash=0
            ))
            if not history.messages:
                break

            for msg in history.messages:
                if not msg.date or msg.date < week_ago:
                    return upload_file(filename)
                if msg.text:
                    link = f"https://t.me/{entity.username}/{msg.id}"
                    f.write(link + "\n")
                    f.write(msg.text + "\n\n")

            offset_id = history.messages[-1].id

def upload_file(filename):
    media = MediaFileUpload(filename, mimetype='text/plain')
    file_metadata = {'name': 'weekly_news.txt', 'parents': [GDRIVE_FOLDER_ID]}
    drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()

@app.route("/run")
def run():
    asyncio.run(run_parser())
    return "weekly_news.txt uploaded to Google Drive"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
