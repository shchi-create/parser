import os
import json
import base64
import asyncio
from flask import Flask, jsonify
from telethon import TelegramClient
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ---------- TELEGRAM SESSION ----------
session_part1 = os.environ.get("SESSION_PART1")
session_part2 = os.environ.get("SESSION_PART2")
api_id = int(os.environ.get("API_ID"))
api_hash = os.environ.get("API_HASH")

session_bytes = base64.b64decode(session_part1 + session_part2)
session_file = "session.session"
with open(session_file, "wb") as f:
    f.write(session_bytes)

client = TelegramClient(session_file, api_id, api_hash)

# ---------- GOOGLE DRIVE SETUP ----------
creds_dict = json.loads(os.environ["GDRIVE_CREDENTIALS_JSON"])
creds = Credentials.from_service_account_info(creds_dict)
drive_service = build('drive', 'v3', credentials=creds)

def upload_to_drive(filename, folder_id=None):
    file_metadata = {'name': filename}
    if folder_id:
        file_metadata['parents'] = [folder_id]

    media = MediaFileUpload(filename, mimetype='text/plain')
    created_file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()
    return created_file.get('id')

# ---------- FLASK APP ----------
app = Flask(__name__)

@app.route("/fetch_last_message", methods=["GET"])
def fetch_last_message():
    try:
        async def main():
            await client.start()
            channel = await client.get_entity("@nebrexnya")  # твой канал
            messages = await client.get_messages(channel, limit=1)
            if not messages:
                return {"success": False, "message": "Сообщений нет"}
            last_message = messages[0].message
            with open("last_message.txt", "w", encoding="utf-8") as f:
                f.write(last_message)
            file_id = upload_to_drive("last_message.txt")
            await client.disconnect()
            return {"success": True, "message": "Сообщение загружено и сохранено на Google Drive", "file_id": file_id}

        result = asyncio.run(main())
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
