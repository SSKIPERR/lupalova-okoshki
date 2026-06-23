import datetime
import json
import os
import time

from telegram_api import send_message, CHAT_ID

MESSAGE_TEXT = os.environ.get(
    "MORNING_MESSAGE",
    "Доброе утро, жду свободные окошки на сегодня, пришлите имена + какая услуга",
)

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "state", "last_question.json")

# часовой пояс Москвы (UTC+3, без перевода времени) — по нему считаем «сегодня»
MSK = datetime.timezone(datetime.timedelta(hours=3))


def already_asked_today():
    """True, если вопрос уже отправлялся сегодня (по московской дате).
    Защита от дублей: утренний вопрос могут запускать сразу два источника —
    внешний планировщик (точно в 9:00) и резервное расписание GitHub.
    Второй запуск в тот же день не должен слать вопрос повторно."""
    if not os.path.exists(STATE_PATH):
        return False
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            state = json.load(f)
        ts = state.get("ts")
        if not ts:
            return False
        prev_day = datetime.datetime.fromtimestamp(ts, MSK).date()
        today = datetime.datetime.now(MSK).date()
        return prev_day == today
    except (ValueError, OSError):
        return False


def main():
    if already_asked_today():
        print("Вопрос уже отправлен сегодня — пропускаю (защита от дублей).")
        return

    resp = send_message(MESSAGE_TEXT)
    message_id = resp.get("result", {}).get("message_id")
    state = {"ts": time.time(), "chat_id": CHAT_ID, "message_id": message_id}
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print("question sent, state saved:", state)


if __name__ == "__main__":
    main()
