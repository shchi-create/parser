from telethon import TelegramClient

api_id = 33360120
api_hash = a61d4ff80e78b4fe12331ed373d3b362

with TelegramClient("session", api_id, api_hash) as client:
    print("Session created")
