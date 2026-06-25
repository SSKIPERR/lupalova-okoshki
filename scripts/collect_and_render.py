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

# Все варианты имён (включая сокращения) -> каноничный ключ мастера.
# Добавляй сюда новые сокращения, если мастера начнут писать ещё как-то.
CANON = {
    # Вера — брови и ресницы
    "вера": "вера", "верочка": "вера",
    # Оля / Ольга — маникюр и педикюр (один человек)
    "оля": "оля", "ольга": "оля", "оленька": "оля", "оль": "оля",
    # Яна — маникюр и педикюр
    "яна": "яна", "яночка": "яна",
    # Ирина — маникюр и педикюр
    "ирина": "ирина", "ира": "ирина", "ириша": "ирина", "иришка": "ирина", "иринка": "ирина",
    # Ксения — стрижки и окрашивание
    "ксения": "ксения", "ксюша": "ксения", "ксю": "ксения", "ксюшка": "ксения",
    # Галя / Галина — стрижки и окрашивание (один человек)
    "галя": "галя", "галина": "галя", "галочка": "галя",
}
# каноничный ключ мастера -> ярлык услуги (как в брифе)
MASTERS = {
    "вера": "БРОВИ · РЕСНИЦЫ",
    "оля": "МАНИКЮР · ПЕДИКЮР",
    "яна": "МАНИКЮР · ПЕДИКЮР",
    "ирина": "МАНИКЮР · ПЕДИКЮР",
    "ксения": "СТРИЖКИ · ОКРАШИВАНИЕ",
    "галя": "СТРИЖКИ · ОКРАШИВАНИЕ",
}
# каноничный ключ мастера -> имя для отображения на сторис
DISPLAY_NAME = {
    "вера": "Вера", "оля": "Ольга", "яна": "Яна",
    "ирина": "Ирина", "ксения": "Ксения", "галя": "Галина",
}

TIME_RE = re.compile(r"\d{1,2}:\d{2}(?:\s*-\s*\d{1,2}:\d{2})?")
NAME_RE = re.compile(r"[А-Яа-яёЁ]+")

# триггеры, по которым можно попросить бота собрать окошки прямо сейчас,
# не дожидаясь автоотправки. Поддерживаем кириллицу, латиницу и слово без слэша,
# потому что Telegram считает «настоящей командой» только латиницу (/okoshki),
# а /окошки кириллицей — нет.
COMMAND_PREFIXES = ("/окошки", "/okoshki", "окошки")

# через сколько минут «тишины» после последнего сообщения с окошками бот сам присылает
# картинку (даём время дописать остальных мастеров). Команда «окошки» шлёт сразу, без ожидания.
SETTLE_AFTER_MIN = 2

NOT_UNDERSTOOD_TEXT = (
    "Я не понял вас 🙈 Пожалуйста, напишите имя и свободное время для окошек "
    "(например: Оля 12:00, 15:00). По возможности укажите и услугу мастера."
)
NOTHING_COLLECTED_TEXT = "Пока нет ответов на утренний вопрос про окошки — сторис не собрана."
# подтверждение, что бот принял команду и начал работу (чтобы не гадать, работает ли он)
WORKING_TEXT = "Принял запрос 👍 Собираю свободные окошки, картинка будет через несколько секунд…"

# слова, которыми просят УБРАТЬ мастера из списка (срабатывает, только если в строке нет времени)
REMOVE_WORDS = {
    "убрать", "убери", "уберите", "убрал", "убрала",
    "удалить", "удали", "удалите", "удалил", "удалила",
    "отмена", "отмени", "отменить", "снять", "сними",
    "нет", "занят", "занята", "занято",
}
# знаки, тоже означающие удаление (если в строке кроме имени только они)
DASH_CROSS = "-—–❌✖🚫×"


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

    Границей блока мастера служит следующее слово-имя, которое либо является
    известным мастером (в любом варианте написания), либо стоит в начале строки
    (новый мастер с новой строки). Благодаря этому время НЕ «утекает» от
    незнакомого имени к соседнему мастеру: если кто-то написан именем, которого
    нет в словаре, его блок просто пропускается, но времена не приклеиваются к
    другому. Поддерживает и один мастер на строку, и несколько в одной строке
    ("Оля 12:00 и Ксения 14:00")."""
    found = []
    name_matches = list(NAME_RE.finditer(text))
    boundaries = []
    for m in name_matches:
        word = m.group(0).lower()
        line_start = text.rfind("\n", 0, m.start()) + 1
        before = text[line_start:m.start()]
        is_line_leading = before.strip(" \t.,;:-–—•") == ""
        if word in CANON or is_line_leading:
            boundaries.append((m.start(), word))
    for i, (start, word) in enumerate(boundaries):
        seg_end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        key = CANON.get(word)
        if not key:
            # незнакомое имя в начале строки — не приклеиваем его времена к другим
            continue
        segment = text[start:seg_end]
        slots = TIME_RE.findall(segment)
        slots = [re.sub(r"\s*-\s*", " - ", s) for s in slots]
        # убрать дубли, сохранив порядок
        seen = set()
        slots = [s for s in slots if not (s in seen or seen.add(s))]
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


def parse_removals(text):
    """Возвращает множество каноничных ключей мастеров, которых просят убрать.
    Срабатывает построчно: в строке есть имя мастера и слово вроде
    'убрать/нет/удалить' (или знак '-' / '❌' рядом с именем), и при этом в строке
    НЕТ времени — иначе это обновление, а не удаление."""
    removals = set()
    for line in text.splitlines():
        if TIME_RE.search(line):
            continue  # есть время — это обновление, не удаление
        low = line.lower()
        present = [w for w in re.findall(r"[а-яёa-z]+", low) if w in CANON]
        if not present:
            continue
        words = set(re.findall(r"[а-яёa-z]+", low))
        is_remove = bool(words & REMOVE_WORDS)
        if not is_remove:
            # знак '-'/'❌' считаем удалением, только если в строке кроме имени(имён)
            # ничего больше нет (чтобы не путать с 'Галя — стрижки')
            leftover = low
            for w in present:
                leftover = leftover.replace(w, " ")
            leftover = leftover.strip()
            if leftover and all(ch in DASH_CROSS or ch.isspace() for ch in leftover):
                is_remove = True
        if is_remove:
            removals |= {CANON[w] for w in present}
    return removals


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
        coll_state = {"for_ts": since_ts, "sent": False, "data": {}, "last_change": None}

    off_state = load_json(OFFSET_PATH, {"offset": 0})
    offset = off_state["offset"]

    updates = get_updates(offset)
    max_update_id = offset - 1
    command_requested = False
    command_msg_id = None
    last_data_date = None  # дата последнего сообщения, изменившего список окошек (для «тишины»)

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
            command_msg_id = msg.get("message_id")
            # после команды в том же сообщении могут быть указаны имена и время
            # (например: "/окошки Оля 12:00, 15:00") — разбираем и их
            for key, slots in parse_message(remainder):
                coll_state["data"][key] = slots
            # ...и можно убрать мастера прямо в команде ("/окошки убрать Галя")
            for key in parse_removals(remainder):
                coll_state["data"].pop(key, None)
            continue

        matches = parse_message(text)
        removals = parse_removals(text)
        if matches or removals:
            for key, slots in matches:
                # последнее сообщение от мастера полностью заменяет предыдущее —
                # так исправления ("нет, на самом деле...") учитываются корректно
                coll_state["data"][key] = slots
            # удаление мастера из списка ("убрать Галя", "Галя нет")
            for key in removals:
                coll_state["data"].pop(key, None)
            last_data_date = max(last_data_date or 0, msg.get("date", 0))
        else:
            reply_to = msg.get("reply_to_message")
            if question_mid and reply_to and reply_to.get("message_id") == question_mid:
                send_message(NOT_UNDERSTOOD_TEXT, reply_to_message_id=msg.get("message_id"))

    save_json(OFFSET_PATH, {"offset": max_update_id + 1})

    if last_data_date is not None:
        coll_state["last_change"] = max(coll_state.get("last_change") or 0, last_data_date)

    now = time.time()
    if command_requested:
        # сразу подтверждаем приём — чтобы в группе не гадали, жив ли бот; картинку шлём следом
        send_message(WORKING_TEXT, reply_to_message_id=command_msg_id)
        if render_and_send(coll_state["data"]):
            coll_state["sent"] = True
    elif not coll_state["sent"] and coll_state["data"]:
        # картинку отправляем сами, когда после последних окошек прошла «тишина»
        # (вдруг кто-то ещё дописывает мастеров). 30-минутного таймера больше нет.
        last_change = coll_state.get("last_change") or 0
        if now - last_change >= SETTLE_AFTER_MIN * 60:
            if render_and_send(coll_state["data"]):
                coll_state["sent"] = True

    save_json(COLLECTED_PATH, coll_state)


if __name__ == "__main__":
    main()
