import os
import requests

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def send_message(text, chat_id=None, reply_to_message_id=None):
    data = {"chat_id": chat_id or CHAT_ID, "text": text}
    if reply_to_message_id:
        data["reply_to_message_id"] = reply_to_message_id
    r = requests.post(f"{API}/sendMessage", data=data, timeout=20)
    r.raise_for_status()
    return r.json()


def send_photo(path, caption="", chat_id=None):
    with open(path, "rb") as f:
        r = requests.post(
            f"{API}/sendPhoto",
            data={"chat_id": chat_id or CHAT_ID, "caption": caption},
            files={"photo": f},
            timeout=60,
        )
    r.raise_for_status()
    return r.json()


def send_document(path, caption="", chat_id=None):
    """Отправляет файл как документ — без пережатия/ресайза, в отличие от sendPhoto."""
    with open(path, "rb") as f:
        r = requests.post(
            f"{API}/sendDocument",
            data={"chat_id": chat_id or CHAT_ID, "caption": caption},
            files={"document": f},
            timeout=60,
        )
    r.raise_for_status()
    return r.json()


def get_updates(offset=0):
    r = requests.get(f"{API}/getUpdates", params={"offset": offset, "timeout": 0}, timeout=20)
    r.raise_for_status()
    return r.json()["result"]
