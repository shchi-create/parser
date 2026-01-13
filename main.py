import os
import asyncio
from telethon import TelegramClient
from flask import Flask, jsonify
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import nest_asyncio

# === Apply nest_asyncio to allow Flask + Telethon coexistence ===
nest_asyncio.apply()

# === Telegram credentials ===
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME")

# === Google Docs credentials ===
DOC_ID = os.environ.get("DOC_ID")
GDRIVE_CREDENTIALS_JSON = os.environ.get("GDRIVE_CREDENTIALS_JSON")
SCOPES = ["https://www.googleapis.com/auth/documents"]

if not all([API_ID, API_HASH, CHANNEL_USERNAME, DOC_ID, GDRIVE_CREDENTIALS_JSON]):
    raise ValueError("Не все переменные окружения заданы: API_ID, API_HASH, CHANNEL_USERNAME, DOC_ID, GDRIVE_CREDENTIALS_JSON")

# === Initialize Google Docs API ===
credentials = service_account.Credentials.from_service_account_file(
    GDRIVE_CREDENTIALS_JSON, scopes=SCOPES
)
docs_service = build('docs', 'v1', credentials=credentials)

# === Initialize Telegram client ===
client = TelegramClient('session', API_ID, API_HASH)

# === Flask app ===
app = Flask(__name__)

async def fetch_last_message():
    async with client:
        async for message in client.iter_messages(CHANNEL_USERNAME, limit=1):
            return message.text
    return None

def append_text_to_google_doc(text: str):
    try:
        requests = [
            {
                "insertText": {
                    "location": {"index": 1},  # вставляем в начало документа
                    "text": text + "\n\n"
                }
            }
        ]
        docs_service.documents().batchUpdate(documentId=DOC_ID, body={"requests": requests}).execute()
        return True
    except HttpError as e:
        print(f"Ошибка Google Docs API: {e}")
        return False

@app.route("/run", methods=["GET"])
def run():
    try:
        text = asyncio.get_event_loop().run_until_complete(fetch_last_message())
        if not text:
            return jsonify({"success": False, "message": "Сообщение не найдено"})
        success = append_text_to_google_doc(text)
        if success:
            return jsonify({"success": True, "message": "Сообщение успешно сохранено в Google Docs"})
        else:
            return jsonify({"success": False, "message": "Ошибка при сохранении в Google Docs"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
