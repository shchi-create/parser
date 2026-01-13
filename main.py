import os
import base64
import json
import nest_asyncio   # <-- новый импорт
from datetime import datetime, timedelta, timezone
from flask import Flask
from telethon import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.service_account import Credentials

nest_asyncio.apply()  # <-- применяем патч для Flask/Railway


# -------------------- Telegram session --------------------
session_b64 = os.environ.get("SESSION_PART1", "") + os.environ.get("SESSION_PART2", "")
if session_b64:
    with open("session.session", "wb") as f:
        f.write(base64.b64decode(session_b64))
else:
    raise RuntimeError("Session parts not found in environment variables")

# -------------------- Настройки --------------------
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
CHANNEL = os.environ["CHANNEL"]  # например: nebrexnya
GDRIVE_FOLDER_ID = os.environ["GDRIVE_FOLDER_ID"]

# -------------------- Google Drive --------------------
creds_dict = json.loads(os.environ["GDRIVE_CREDENTIALS_JSON"])
SCOPES = ['https://www.googleapis.com/auth/drive.file']
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

# -------------------- Telegram client --------------------
client = TelegramClient("session", API_ID, API_HASH)
client.start()

# Проверка подключения к каналу
try:
    entity = client.get_entity(CHANNEL)
except Exception as e:
    print("ERROR getting Telegram entity:", e)
    raise

# -------------------- Flask app --------------------
app = Flask(__name__)

@app.route("/run")
def run():
    async def fetch_and_upload():
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        offset_id = 0
        limit = 100
        filename = "/tmp/weekly_news.txt"

        with open(filename, "w", encoding="utf-8") as f:
            while True:
                try:
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
                except Exception as e:
                    print("ERROR fetching history:", e)
                    raise

                if not history.messages:
                    break

                for msg in history.messages:
                    if not msg.date or msg.date < week_ago:
                        break
                    if msg.text:
                        link = f"https://t.me/{entity.username}/{msg.id}"
                        f.write(link + "\n")
                        f.write(msg.text + "\n\n")

                offset_id = history.messages[-1].id

        # -------------------- Upload to Google Drive --------------------
        try:
            media = MediaFileUpload(filename, mimetype='text/plain')
            file_metadata = {'name': 'weekly_news.txt', 'parents': [GDRIVE_FOLDER_ID]}
            drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        except Exception as e:
            print("ERROR uploading to Google Drive:", e)
            raise

        return "weekly_news.txt uploaded to Google Drive"

    # Отлов ошибок при запуске Telethon внутри Flask
    try:
        return client.loop.run_until_complete(fetch_and_upload())
    except Exception as e:
        print("ERROR in /run:", e)
        return f"Error: {e}", 500

if __name__ == "__main__":
    print("SESSION_PART1 length:", len(os.environ.get("SESSION_PART1", "")))
    print("SESSION_PART2 length:", len(os.environ.get("SESSION_PART2", "")))
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
