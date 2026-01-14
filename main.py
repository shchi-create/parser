import os
import base64
import json
import pytz
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from telethon import TelegramClient
from telethon.sessions import SQLiteSession
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")
DOC_ID = os.getenv("DOC_ID")

SESSION_PART1 = os.getenv("SESSION_PART1")
SESSION_PART2 = os.getenv("SESSION_PART2")
SESSION_B64 = SESSION_PART1 + SESSION_PART2

GDRIVE_CREDENTIALS_JSON = os.getenv("GDRIVE_CREDENTIALS_JSON")

TIMEZONE = pytz.timezone("Europe/Moscow")

app = FastAPI()

# ---------- Telegram session restore ----------
def restore_session():
    session_bytes = base64.b64decode(SESSION_B64)
    with open("session.session", "wb") as f:
        f.write(session_bytes)
    return SQLiteSession("session")

# ---------- Google Docs ----------
def get_docs_service():
    creds_dict = json.loads(GDRIVE_CREDENTIALS_JSON)
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/documents"]
    )
    return build("docs", "v1", credentials=creds)

def clear_doc(service):
    doc = service.documents().get(documentId=DOC_ID).execute()
    length = doc["body"]["content"][-1]["endIndex"]
    service.documents().batchUpdate(
        documentId=DOC_ID,
        body={"requests":[{"deleteContentRange":{"range":{"startIndex":1,"endIndex":length-1}}}]}
    ).execute()

def write_doc(service, text):
    service.documents().batchUpdate(
        documentId=DOC_ID,
        body={"requests":[{"insertText":{"location":{"index":1},"text":text}}]}
    ).execute()

# ---------- Telegram parsing ----------
async def fetch_posts(mode):
    session = restore_session()
    client = TelegramClient(session, API_ID, API_HASH)
    await client.connect()

    posts = []
    now = datetime.now(TIMEZONE)

    if mode == "week":
        monday = (now - timedelta(days=now.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)

    async for msg in client.iter_messages(CHANNEL_USERNAME, limit=100):
        if not msg.text:
            continue

        msg_date = msg.date.astimezone(TIMEZONE)

        if mode == "last":
            link = f"https://t.me/{CHANNEL_USERNAME[1:]}/{msg.id}"
            posts.append(f"{link}\n{msg.text}\n\n")
            break

        if msg_date >= monday:
            link = f"https://t.me/{CHANNEL_USERNAME[1:]}/{msg.id}"
            posts.append(f"{link}\n{msg.text}\n\n")

    await client.disconnect()
    return posts[::-1], monday if mode=="week" else None, now

# ---------- UI ----------
@app.get("/run", response_class=HTMLResponse)
async def index():
    return """
    <html>
    <body style="font-family:Arial">
        <h2>Telegram Parser</h2>
        <form action="/run/last" method="post"><button>Last</button></form><br>
        <form action="/run/week" method="post"><button>Week</button></form>
    </body>
    </html>
    """

@app.post("/run/{mode}", response_class=HTMLResponse)
async def run(mode:str):
    posts, monday, now = await fetch_posts(mode)

    service = get_docs_service()
    clear_doc(service)

    if mode=="week":
        title = f"Посты за неделю {monday.strftime('%d.%m')}–{now.strftime('%d.%m')}\n\n"
    else:
        title = f"Последний пост на {now.strftime('%d.%m.%Y %H:%M')}\n\n"

    write_doc(service, title + "".join(posts))
    return "<h3>Готово. Документ обновлен.</h3>"
