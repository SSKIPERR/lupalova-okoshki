import json
import os
import re

from telegram_api import get_updates, send_message, send_document, CHAT_ID
from render_okoshki import render

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(BASE, "..", "state")
Q_STATE_PATH = os.path.join(STATE_DIR, "last_question.json")
OFFSET_PATH = os.path.join(STATE_DIR, "offset.json")
OUT_PATH = os.path.join(BASE, "..", "okoshki.png")

# мастер -> ярлык услуги (как в брифе)
MASTERS = {
    "вера": "БРОВИ · РЕСНИЦЫ",
    "оля": "МАНИКЮР · ПЕДИКЮР",
    "ольга": "МАНИКЮР · ПЕДИКЮР",
    "яна": "МАНИКЮР · ПЕДИКЮР",
    "ирина": "МАНИКЮР · ПЕДИКЮР",
    "ксения": "СТРИЖКИ · ОКРАШИВАНИЕ",
    "галя": "СТРИЖКИ · ОКРАШИВАНИЕ",
    "галина": "СТРИЖКИ · ОКРАШИВАНИЕ",
}
# каноничное имя для отображения в сторис
DISPLAY_NAME = {
    "вера": "Вера", "оля": "Оля", "ольга": "Ольга", "яна": "Яна",
    "ирина": "Ирина", "ксения": "Ксения", "галя": "Галя", "галина": "Галина",
}

TIME_RE = re.compile(r"\d{1,2}:\d{2}(?:\s*-\s*\d{1,2}:\d{2})?")
NAME_RE = re.compile(r"[А-Яа-яёЁ]+")


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_message(text):
    """Возвращает список (master_key, [слоты]) найденных в сообщении."""
    found = []
    matches = list(NAME_RE.finditer(text))
    for i, m in enumerate(matches):
        key = m.group(0).lower()
        if key not in MASTERS:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) and matches[i + 1].group(0).lower() in MASTERS else len(text)
        segment = text[start:end]
        slots = TIME_RE.findall(segment)
        slots = [re.sub(r"\s*-\s*", " - ", s) for s in slots]
        if slots:
            found.append((key, slots))
    return found


def main():
    q_state = load_json(Q_STATE_PATH, None)
    if not q_state:
        print("Нет состояния вопроса (state/last_question.json) — пропускаю.")
        return
    since_ts = q_state["ts"]

    off_state = load_json(OFFSET_PATH, {"offset": 0})
    offset = off_state["offset"]

    updates = get_updates(offset)
    collected = {}  # master_key -> [слоты], последний ответ мастера побеждает
    max_update_id = offset - 1

    for upd in updates:
        max_update_id = max(max_update_id, upd["update_id"])
        msg = upd.get("message")
        if not msg:
            continue
        if str(msg.get("chat", {}).get("id")) != str(CHAT_ID):
            continue
        if msg.get("date", 0) < since_ts:
            continue
        text = msg.get("text", "")
        if not text:
            continue
        for key, slots in parse_message(text):
            # последнее сообщение от мастера полностью заменяет предыдущее —
            # так исправления ("нет, на самом деле...") учитываются корректно
            collected[key] = slots

    save_json(OFFSET_PATH, {"offset": max_update_id + 1})

    if not collected:
        send_message("Пока нет ответов на утренний вопрос про окошки — сторис не собрана.")
        print("no replies, nothing rendered")
        return

    label_order = []
    by_label = {}
    for key, slots in collected.items():
        label = MASTERS[key]
        if label not in by_label:
            by_label[label] = []
            label_order.append(label)
        by_label[label].append({"name": DISPLAY_NAME[key], "slots": slots})

    services = [{"label": label, "masters": by_label[label]} for label in label_order]

    render(services, subtitle="на сегодня", out_path=OUT_PATH)
    send_document(OUT_PATH, caption="Свободные окошки на сегодня готовы. Можно публиковать в Stories.")
    print("rendered and sent:", services)


if __name__ == "__main__":
    main()
