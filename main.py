import os
import json
import asyncio
from google.oauth2 import service_account
from googleapiclient.discovery import build
from telethon import TelegramClient, events

# =========================
# Переменные окружения
# =========================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")
DOC_ID = os.getenv("DOC_ID")
GDRIVE_CREDENTIALS_JSON = os.getenv("GDRIVE_CREDENTIALS_JSON")  # JSON строка

# =========================
# Google Sheets
# =========================
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

# Преобразуем JSON-строку в словарь
credentials_info = json.loads(GDRIVE_CREDENTIALS_JSON)

credentials = service_account.Credentials.from_service_account_info(
    credentials_info, scopes=SCOPES
)

service = build('sheets', 'v4', credentials=credentials)
sheet = service.spreadsheets()

# =========================
# Telegram Client
# =========================
client = TelegramClient('bot_session', API_ID, API_HASH)

async def main():
    await client.start()
    print("Бот запущен")

    # Получаем данные из Google Sheets (пример: первый лист, A1:A10)
    result = sheet.values().get(spreadsheetId=DOC_ID, range='A1:A10').execute()
    values = result.get('values', [])
    print("Данные из Google Sheets:", values)

    # Отправляем каждую строку в канал
    for row in values:
        text = row[0] if row else ''
        if text:
            await client.send_message(CHANNEL_USERNAME, text)
            print(f"Отправлено в канал: {text}")

    print("Все данные отправлены")

# Запуск асинхронного цикла
asyncio.run(main())
