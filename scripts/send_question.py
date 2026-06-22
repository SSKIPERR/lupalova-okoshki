import json
import os
import time

from telegram_api import send_message, CHAT_ID

MESSAGE_TEXT = os.environ.get(
    "MORNING_MESSAGE",
    "Доброе утро, жду свободные окошки на сегодня, пришлите имена + какая услуга",
)

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "state", "last_question.json")


def main():
    send_message(MESSAGE_TEXT)
    state = {"ts": time.time(), "chat_id": CHAT_ID}
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print("question sent, state saved:", state)


if __name__ == "__main__":
    main()
