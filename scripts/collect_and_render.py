import json
import os
import re
import time

from telegram_api import get_updates, send_message, send_document, CHAT_ID
from render_okoshki import render

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(BASE, "..", "state")
Q_STATE_PATH = os.path.join(STATE_DIR, "last_question.json")
OFFSET_PATH = os.path.join(STATE_DIR, "offset.json")
COLLECTED_PATH = os.path.join(STATE_DIR, "collected_today.json")
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

# триггеры, по которым можно попросить бота собрать окошки прямо сейчас,
# не дожидаясь автоотправки. Поддерживаем кириллицу, латиницу и слово без слэша,
# потому что Telegram считает «настоящей командой» только латиницу (/okoshki),
# а /окошки кириллицей — нет.
COMMAND_PREFIXES = ("/окошки", "/okoshki", "окошки")

# через сколько минут после вопроса бот сам присылает сторис, если её не попросили раньше командой
AUTO_SEND_AFTER_MIN = 30

NOT_UNDERSTOOD_TEXT = (
    "Я не понял вас 🙈 Пожалуйста, напишите имя и свободное время для окошек "
    "(например: Оля 12:00, 15:00). По возможности укажите и услугу мастера."
)
NOTHING_COLLECTED_TEXT = "Пока нет ответов на утренний вопрос про окошки — сторис не собрана."


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
    """Возвращает список (master_key, [слоты]) найденных в сообщении.

    Если в одном сообщении упомянуто несколько мастеров (например,
    администратор пишет за всех сразу), границей блока каждого мастера
    служит СЛЕДУЮЩЕЕ найденное имя мастера — даже если между ними есть
    посторонние слова ("и", "также" и т.п.), а не только если оно идёт
    сразу следующим словом."""
    found = []
    matches = list(NAME_RE.finditer(text))
    master_idx = [i for i, m in enumerate(matches) if m.group(0).lower() in MASTERS]
    for pos, i in enumerate(master_idx):
        m = matches[i]
        key = m.group(0).lower()
        start = m.end()
        end = matches[master_idx[pos + 1]].start() if pos + 1 < len(master_idx) else len(text)
        segment = text[start:end]
        slots = TIME_RE.findall(segment)
        slots = [re.sub(r"\s*-\s*", " - ", s) for s in slots]
        if slots:
            found.append((key, slots))
    return found


def parse_command(text):
    """Если text начинается с триггера-команды — возвращает (True, остаток_после_команды),
    иначе (False, text). Поддерживает '/окошки', '/okoshki', слово 'окошки',
    вариант с @имя_бота и данные в том же сообщении ('/окошки Оля 12:00')."""
    t = text.strip()
    low = t.lower()
    for p in COMMAND_PREFIXES:
        if not low.startswith(p):
            continue
        after = t[len(p):]
        # слово без слэша ('окошки') считаем командой только как отдельное слово,
        # чтобы не реагировать на случайный текст вроде 'окошкина'
        if not p.startswith("/") and after and not after[0].isspace() and after[0] != "@":
            continue
        # убрать возможный '@имя_бота' сразу после команды
        after = re.sub(r"^@\S+\s*", "", after.lstrip())
        return True, after.strip()
    return False, t


def render_and_send(collected):
    """Рендерит и отправляет сторис, если есть данные; иначе шлёт уведомление.
    Возвращает True, если реально отправлена картинка."""
    if not collected:
        send_message(NOTHING_COLLECTED_TEXT)
        print("nothing collected, sent fallback text")
        return False

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
    return True


def main():
    q_state = load_json(Q_STATE_PATH, None)
    if not q_state:
        print("Вопрос сегодня ещё не отправлен (state/last_question.json) — пропускаю.")
        return
    since_ts = q_state["ts"]
    question_mid = q_state.get("message_id")

    coll_state = load_json(COLLECTED_PATH, None)
    if not coll_state or coll_state.get("for_ts") != since_ts:
        # новый день / новый вопрос — начинаем сбор с нуля
        coll_state = {"for_ts": since_ts, "sent": False, "notified_empty": False, "data": {}}

    off_state = load_json(OFFSET_PATH, {"offset": 0})
    offset = off_state["offset"]

    updates = get_updates(offset)
    max_update_id = offset - 1
    command_requested = False

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

        is_cmd, remainder = parse_command(text)
        if is_cmd:
            command_requested = True
            # после команды в том же сообщении могут быть указаны имена и время
            # (например: "/окошки Оля 12:00, 15:00") — разбираем и их
            for key, slots in parse_message(remainder):
                coll_state["data"][key] = slots
            continue

        matches = parse_message(text)
        if matches:
            for key, slots in matches:
                # последнее сообщение от мастера полностью заменяет предыдущее —
                # так исправления ("нет, на самом деле...") учитываются корректно
                coll_state["data"][key] = slots
        else:
            reply_to = msg.get("reply_to_message")
            if question_mid and reply_to and reply_to.get("message_id") == question_mid:
                send_message(NOT_UNDERSTOOD_TEXT, reply_to_message_id=msg.get("message_id"))

    save_json(OFFSET_PATH, {"offset": max_update_id + 1})

    elapsed_min = (time.time() - since_ts) / 60

    if command_requested:
        # явная просьба — отвечаем всегда, даже если пока ничего не собрано
        if render_and_send(coll_state["data"]):
            coll_state["sent"] = True
    elif not coll_state["sent"] and elapsed_min >= AUTO_SEND_AFTER_MIN:
        # прошло достаточно времени и сторис ещё не отправляли
        if coll_state["data"]:
            # есть ответы — собираем и шлём. Даже если раньше уже писали «нет ответов»:
            # ответы могли прийти позже, и мы всё равно обязаны прислать картинку.
            if render_and_send(coll_state["data"]):
                coll_state["sent"] = True
        elif not coll_state["notified_empty"]:
            # ответов нет — один раз сообщаем об этом, но НЕ блокируем будущую отправку
            send_message(NOTHING_COLLECTED_TEXT)
            coll_state["notified_empty"] = True

    save_json(COLLECTED_PATH, coll_state)


if __name__ == "__main__":
    main()
