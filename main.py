import os
import base64
import json
import pytz
import re
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from telethon import TelegramClient
from telethon.sessions import SQLiteSession
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

TIMEZONE = pytz.timezone("Europe/Moscow")
app = FastAPI()

# ---------- ignore rules ----------
IGNORE_FIRST_WORDS = {
    "#ВекторыДня",
    "#ЕстьМнение",
    "#События",
}

ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\u2060\uFEFF]")

def normalize_text(text: str) -> str:
    text = ZERO_WIDTH_RE.sub("", text)
    return text.lstrip()

def should_ignore(text: str) -> bool:
    if not text:
        return True

    clean = normalize_text(text)

    first_line = clean.splitlines()[0]
    first_word = first_line.split(maxsplit=1)[0]

    return first_word in IGNORE_FIRST_WORDS

# ---------- env helper ----------
def env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing env var: {name}")
    return value

# ---------- Telegram session restore ----------
def restore_session():
    session_b64 = env("SESSION_PART1") + env("SESSION_PART2")
    session_bytes = base64.b64decode(session_b64)
    with open("session.session", "wb") as f:
        f.write(session_bytes)
    return SQLiteSession("session")

# ---------- Google Docs ----------
def get_docs_service():
    creds_dict = json.loads(env("GDRIVE_CREDENTIALS_JSON"))
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/documents"]
    )
    return build("docs", "v1", credentials=creds)

def clear_doc(service, doc_id):
    doc = service.documents().get(documentId=doc_id).execute()
    content = doc.get("body", {}).get("content", [])

    if len(content) < 2:
        return

    end_index = content[-1].get("endIndex", 1)
    if end_index <= 1:
        return

    service.documents().batchUpdate(
        documentId=doc_id,
        body={
            "requests": [
                {
                    "deleteContentRange": {
                        "range": {
                            "startIndex": 1,
                            "endIndex": end_index - 1
                        }
                    }
                }
            ]
        }
    ).execute()

def write_doc(service, doc_id, text):
    service.documents().batchUpdate(
        documentId=doc_id,
        body={
            "requests": [
                {
                    "insertText": {
                        "location": {"index": 1},
                        "text": text
                    }
                }
            ]
        }
    ).execute()

# ---------- Telegram parsing ----------
async def fetch_posts(mode):
    api_id = int(env("API_ID"))
    api_hash = env("API_HASH")
    channel = env("CHANNEL_USERNAME")

    session = restore_session()
    client = TelegramClient(session, api_id, api_hash)
    await client.connect()

    posts = []
    now = datetime.now(TIMEZONE)

    if mode == "week":
        monday = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    async for msg in client.iter_messages(channel, limit=100):
        if not msg.text:
            continue

        if should_ignore(msg.text):
            continue

        msg_date = msg.date.astimezone(TIMEZONE)

        if mode == "last":
            link = f"https://t.me/{channel[1:]}/{msg.id}"
            posts.append(f"{link}\n{msg.text}\n\n")
            break

        if msg_date >= monday:
            link = f"https://t.me/{channel[1:]}/{msg.id}"
            posts.append(f"{link}\n{msg.text}\n\n")

    await client.disconnect()
    return posts[::-1], monday if mode == "week" else None, now

# ---------- UI ----------
@app.get("/run", response_class=HTMLResponse)
async def index():
    return """
    <html>
      <body style="font-family:Arial">
        <h2>Telegram Parser</h2>
        <form action="/run/last" method="post">
            <button>Last</button>
        </form><br>
        <form action="/run/week" method="post">
            <button>Week</button>
        </form>
      </body>
    </html>
    """

@app.api_route("/run/{mode}", methods=["GET", "POST"], response_class=HTMLResponse)
async def run(mode: str):
    doc_id = env("DOC_ID")

    posts, monday, now = await fetch_posts(mode)
    service = get_docs_service()
    clear_doc(service, doc_id)

    if mode == "week":
        title = (
            f"Посты за неделю "
            f"{monday.strftime('%d.%m')}–{now.strftime('%d.%m')}\n\n"
        )
    else:
        title = f"Последний пост на {now.strftime('%d.%m.%Y %H:%M')}\n\n"

    write_doc(service, doc_id, title + "".join(posts))
    return "<h3>Готово. Документ обновлен.</h3>"
