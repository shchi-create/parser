import requests
import re
import os
import json
from bs4 import BeautifulSoup
from google.oauth2 import service_account
import google.auth.transport.requests
from datetime import datetime, timedelta

# --- НАСТРОЙКИ ---
CHANNEL_NAME = os.getenv("CHANNEL_NAME")
DOCUMENT_ID = os.getenv("DOCUMENT_ID")
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
EXCLUDE_TAGS = ["#События", "#ВекторыДня", "#ЕстьМнение"]

# Вместо логов в файл используем простые принты (Railway их видит в консоли)
def log(message):
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {message}")

def get_access_token():
    if not GOOGLE_CREDS_JSON:
        raise ValueError("Google Credentials not found in env vars")
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    creds = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=['https://www.googleapis.com/auth/documents']
    )
    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)
    return creds.token

def google_api_request(method, url_suffix, token, body=None):
    url = f"https://docs.googleapis.com/v1/documents/{DOCUMENT_ID}{url_suffix}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if method == "POST":
        resp = requests.post(url, headers=headers, json=body)
    else:
        resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json() if resp.text else {}

def get_existing_links(content):
    full_text = []
    for element in content:
        if 'paragraph' in element:
            for text_run in element.get('paragraph').get('elements'):
                full_text.append(text_run.get('textRun', {}).get('content', ''))
    return "".join(full_text)

def clean_old_posts(token, content):
    date_pattern = re.compile(r"--- ЗАГРУЗКА ОТ (\d{2}\.\d{2}\.\d{4}) ---")
    week_ago = datetime.now() - timedelta(days=7)
    cutoff_index = None

    for element in content:
        if 'paragraph' in element:
            para_text = "".join([tr.get('textRun', {}).get('content', '') 
                                 for tr in element.get('paragraph').get('elements')])
            match = date_pattern.search(para_text)
            if match:
                try:
                    post_date = datetime.strptime(match.group(1), "%d.%m.%Y")
                    if post_date < week_ago:
                        cutoff_index = element.get('startIndex')
                        log(f"Найден старый блок от {match.group(1)}. Удаляем.")
                        break
                except ValueError: continue

    if cutoff_index:
        end_index = content[-1].get('endIndex') - 1
        body = {'requests': [{'deleteContentRange': {'range': {'startIndex': cutoff_index, 'endIndex': end_index}}}]}
        google_api_request("POST", ":batchUpdate", token, body)

def parse_to_google_doc():
    log("Запуск парсинга...")
    try:
        token = get_access_token()
        # 1. Получаем контент
        doc_data = google_api_request("GET", "", token)
        content = doc_data.get('body').get('content', [])
        
        # 2. Чистим старое (прошлые 7 дней)
        clean_old_posts(token, content)
        
        # 3. Собираем ссылки для проверки дублей
        existing_text = get_existing_links(content)
        
        # 4. Парсим Telegram
        url = f"https://t.me/s/{CHANNEL_NAME}"
        response = requests.get(url, timeout=10)
        # lxml потребляет меньше памяти
        soup = BeautifulSoup(response.text, 'lxml') 
        messages = soup.find_all('div', class_='tgme_widget_message_wrap')
        
        new_entries = ""
        new_count = 0
        
        for msg in messages:
            link_tag = msg.find('a', class_='tgme_widget_message_date')
            if not link_tag or link_tag['href'] in existing_text:
                continue
                
            text_area = msg.find('div', class_='tgme_widget_message_text')
            text = text_area.get_text(separator='\n').strip() if text_area else ""
            
            if any(text.startswith(tag) for tag in EXCLUDE_TAGS):
                continue
                
            new_entries = f"{link_tag['href']}\n{text if text else '[Медиа]'}\n\n" + new_entries
            new_count += 1
            
        if new_entries:
            today_date = datetime.now().strftime("%d.%m.%Y")
            final_text = f"--- ЗАГРУЗКА ОТ {today_date} ---\n\n{new_entries}"
            body = {'requests': [{'insertText': {'location': {'index': 1}, 'text': final_text}}]}
            google_api_request("POST", ":batchUpdate", token, body)
            log(f"Добавлено постов: {new_count}")
        else:
            log("Новых постов нет.")

    except Exception as e:
        log(f"Критическая ошибка: {e}")

if __name__ == "__main__":
    parse_to_google_doc()
