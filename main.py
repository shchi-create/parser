import requests
import re
import os
import json
import logging
from bs4 import BeautifulSoup
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta

# --- НАСТРОЙКИ ЛОГИРОВАНИЯ ---
# Логи будут писаться в файл app.log
logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

# --- ЗАГРУЗКА ПЕРЕМЕННЫХ ИЗ ОКРУЖЕНИЯ ---
CHANNEL_NAME = os.getenv("CHANNEL_NAME")
DOCUMENT_ID = os.getenv("DOCUMENT_ID")
# Вместо пути к файлу, мы ожидаем содержимое JSON-ключа в переменной
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")

EXCLUDE_TAGS = ["#События", "#ВекторыДня", "#ЕстьМнение"]

def get_google_docs_service():
    scopes = ['https://www.googleapis.com/auth/documents']
    
    if not GOOGLE_CREDS_JSON:
        logging.error("Не найдена переменная окружения GOOGLE_APPLICATION_CREDENTIALS_JSON")
        raise ValueError("Google Credentials not found in env vars")

    try:
        # Преобразуем JSON-строку из переменной в словарь
        creds_dict = json.loads(GOOGLE_CREDS_JSON)
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=scopes)
        return build('docs', 'v1', credentials=creds)
    except json.JSONDecodeError as e:
        logging.error(f"Ошибка парсинга JSON ключа: {e}")
        raise
    except Exception as e:
        logging.error(f"Ошибка создания сервиса Google: {e}")
        raise

def get_doc_content(service):
    """Получает структуру документа."""
    try:
        doc = service.documents().get(documentId=DOCUMENT_ID).execute()
        return doc.get('body').get('content', []), doc.get('documentId')
    except Exception as e:
        logging.error(f"Ошибка получения контента документа: {e}")
        raise

def get_existing_links(content):
    """Парсит ссылки из структуры документа."""
    full_text = ""
    for element in content:
        if 'paragraph' in element:
            for text_run in element.get('paragraph').get('elements'):
                full_text += text_run.get('textRun', {}).get('content', '')
    return full_text

def append_to_doc(service, text):
    """Вставляет текст в начало документа (индекс 1)."""
    requests_body = [
        {
            'insertText': {
                'location': {'index': 1},
                'text': text
            }
        }
    ]
    try:
        service.documents().batchUpdate(
            documentId=DOCUMENT_ID, body={'requests': requests_body}).execute()
    except Exception as e:
        logging.error(f"Ошибка записи в документ: {e}")
        raise

def clean_old_posts(service):
    """Удаляет контент старше 7 дней."""
    content, _ = get_doc_content(service)
    cutoff_index = None
    
    # Регулярка для поиска наших заголовков даты
    date_pattern = re.compile(r"--- ЗАГРУЗКА ОТ (\d{2}\.\d{2}\.\d{4}) ---")
    week_ago = datetime.now() - timedelta(days=7)

    # Ищем, где начинается старый контент
    for element in content:
        if 'paragraph' in element:
            start_index = element.get('startIndex')
            para_text = ""
            for text_run in element.get('paragraph').get('elements'):
                para_text += text_run.get('textRun', {}).get('content', '')
            
            match = date_pattern.search(para_text)
            if match:
                post_date_str = match.group(1)
                try:
                    post_date = datetime.strptime(post_date_str, "%d.%m.%Y")
                    if post_date < week_ago:
                        cutoff_index = start_index
                        logging.info(f"Найден старый блок от {post_date_str}. Удаляем всё, что ниже.")
                        break 
                except ValueError:
                    continue

    if cutoff_index:
        end_index = content[-1].get('endIndex') - 1
        requests_body = [{
            'deleteContentRange': {
                'range': {
                    'startIndex': cutoff_index,
                    'endIndex': end_index
                }
            }
        }]
        try:
            service.documents().batchUpdate(
                documentId=DOCUMENT_ID, body={'requests': requests_body}).execute()
        except Exception as e:
            logging.error(f"Ошибка при удалении старого контента: {e}")

def parse_to_google_doc():
    logging.info("Запуск скрипта парсинга...")
    
    try:
        service = get_google_docs_service()
    except Exception as e:
        logging.critical("Не удалось инициализировать сервис Google. Остановка.")
        return

    # 1. Сначала чистим старое
    try:
        clean_old_posts(service)
    except Exception as e:
        logging.error(f"Ошибка при очистке: {e}")

    # 2. Получаем актуальный контент
    try:
        content, _ = get_doc_content(service)
        existing_text = get_existing_links(content)
    except Exception:
        return # Ошибка уже залогирована в get_doc_content

    url = f"https://t.me/s/{CHANNEL_NAME}"
    logging.info(f"Парсинг URL: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except Exception as e:
        logging.error(f"Ошибка доступа к Telegram: {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    messages = soup.find_all('div', class_='tgme_widget_message_wrap')
    
    new_entries = ""
    new_count = 0
    
    for msg in messages:
        link_tag = msg.find('a', class_='tgme_widget_message_date')
        if not link_tag: continue
        link = link_tag['href']
        
        if link in existing_text:
            continue
            
        text_area = msg.find('div', class_='tgme_widget_message_text')
        text = text_area.get_text(separator='\n').strip() if text_area else ""
        
        if any(text.startswith(tag) for tag in EXCLUDE_TAGS):
            continue
            
        entry = f"{link}\n{text if text else '[Медиа]'}\n\n"
        new_entries = entry + new_entries 
        new_count += 1
        
    if new_entries:
        today_date = datetime.now().strftime("%d.%m.%Y")
        final_text = f"--- ЗАГРУЗКА ОТ {today_date} ---\n\n{new_entries}"
        
        try:
            append_to_doc(service, final_text)
            logging.info(f"Успешно добавлено постов: {new_count}. Дата: {today_date}")
        except Exception:
            logging.error("Не удалось добавить посты в документ.")
    else:
        logging.info("Новых постов не найдено.")

if __name__ == "__main__":
    parse_to_google_doc()
