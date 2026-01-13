import os
import json
from flask import Flask, jsonify
from telethon import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
from google.oauth2 import service_account
from googleapiclient.discovery import build

# -------------------------
# Настройки Telegram
# -------------------------
API_ID = int(os.environ.get("API_ID", 123456))            # твой API ID
API_HASH = os.environ.get("API_HASH", "")                # твой API HASH
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "@nebrexnya")  # канал или юзер

# -------------------------
# Настройки Google Docs
# -------------------------
SERVICE_ACCOUNT_FILE = os.environ.get("GDRIVE_CREDENTIALS_JSON", "credentials.json")
DOCUMENT_ID = os.environ.get("DOC_ID", "")  # ID документа Google Docs

SCOPES = ['https://www.googleapis.com/auth/documents']

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
docs_service = build('docs', 'v1', credentials=credentials)

# -------------------------
# Flask
# -------------------------
app = Flask(__name__)

# -------------------------
# Telegram клиент
# -------------------------
client = TelegramClient('session', API_ID, API_HASH)

async def fetch_last_message():
    await client.start()
    entity = await client.get_entity(CHANNEL_USERNAME)
    history = await client(GetHistoryRequest(
        peer=entity,
        limit=1,
        offset_date=None,
        offset_id=0,
        max_id=0,
        min_id=0,
        add_offset=0,
        hash=0
    ))
    if history.messages:
        return history.messages[0].message
    return None

def append_to_doc(text: str):
    requests = [
        {
            'insertText': {
                'location': {'index': 1_000_000_000},  # конец документа
                'text': text + "\n\n"
            }
        }
    ]
    result = docs_service.documents().batchUpdate(
        documentId=DOCUMENT_ID,
        body={'requests': requests}
    ).execute()
    return result

# -------------------------
# Flask route
# -------------------------
@app.route("/run", methods=["GET"])
def run():
    import asyncio
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        last_message = loop.run_until_complete(fetch_last_message())
        if not last_message:
            return jsonify({"success": False, "message": "Нет сообщений в канале"})
        append_to_doc(last_message)
        return jsonify({"success": True, "message": "Сообщение успешно добавлено в Google Docs"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# -------------------------
# Старт Flask
# -------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
