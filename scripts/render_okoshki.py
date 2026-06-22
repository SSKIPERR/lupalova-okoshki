"""
Генератор сторис "Свободные окошки" для Студии красоты «Лупалова».
Стиль строго по брифу (lupalova_brief.md, раздел 7.1).

Кириллический и латинский (цифры/пунктуация) наборы Lora — это разные файлы
шрифта (Google Fonts subset), поэтому текст рисуется по символам: кириллица —
из cyr-файла, всё остальное (цифры, ":", "-", "·", "," и т.п.) — из lat-файла
той же насыщенности/наклона.
"""

import os
from PIL import Image, ImageDraw, ImageFont

CREAM = (244, 239, 229)
GOLD = (196, 160, 96)
DARK = (42, 34, 24)
DARK_SECOND = (90, 78, 62)

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fonts")
S = 2  # supersample factor
W, H = 1080 * S, 1920 * S

_FONT_CACHE = {}

def _load(style, size_px):
    key = (style, size_px)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    cyr = ImageFont.truetype(f"{FONT_DIR}/lora-cyrillic-{style}.ttf", size_px)
    lat = ImageFont.truetype(f"{FONT_DIR}/lora-latin-{style}.ttf", size_px)
    _FONT_CACHE[key] = (cyr, lat)
    return cyr, lat

def is_cyr(ch):
    o = ord(ch)
    return 0x0400 <= o <= 0x04FF

def font_pair(style, size):
    return _load(style, int(size * S))

def char_font(ch, pair):
    cyr, lat = pair
    return cyr if is_cyr(ch) else lat

def text_width(text, pair, tracking=0):
    if not text:
        return 0
    total = 0
    for ch in text:
        f = char_font(ch, pair)
        total += f.getlength(ch)
    total += tracking * S * max(0, len(text) - 1)
    return total

def draw_mixed(draw, xy, text, pair, fill, tracking=0, anchor="mm"):
    x, y = xy
    total_w = text_width(text, pair, tracking)
    if anchor[0] == "m":
        cursor = x - total_w / 2
    elif anchor[0] == "r":
        cursor = x - total_w
    else:
        cursor = x
    for ch in text:
        f = char_font(ch, pair)
        draw.text((cursor, y), ch, font=f, fill=fill, anchor="lm")
        cursor += f.getlength(ch) + tracking * S
    return total_w

def line_metrics(pair):
    cyr, lat = pair
    a1, d1 = cyr.getmetrics()
    a2, d2 = lat.getmetrics()
    return max(a1, a2), max(d1, d2)

def diamond(draw, cx, cy, r, fill):
    draw.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=fill)

def divider(draw, cx, cy, line_len=78, gap=18, diam_r=6):
    line_len *= S; gap *= S; diam_r *= S
    w = max(1, int(1.4 * S))
    draw.line([(cx - gap - line_len, cy), (cx - gap, cy)], fill=GOLD, width=w)
    draw.line([(cx + gap, cy), (cx + gap + line_len, cy)], fill=GOLD, width=w)
    diamond(draw, cx, cy, diam_r, GOLD)

def corner_accents(draw, margin, length=32, thickness=3):
    m = margin * S
    l = length * S
    t = max(1, int(thickness * S))
    for tag, x, y in [("tl", m, m), ("tr", W - m, m), ("bl", m, H - m), ("br", W - m, H - m)]:
        dx = -1 if "r" in tag else 1
        dy = -1 if "b" in tag else 1
        draw.line([(x, y), (x + dx * l, y)], fill=GOLD, width=t)
        draw.line([(x, y), (x, y + dy * l)], fill=GOLD, width=t)

def rounded_rect_rgba(size, radius, fill, outline, width):
    img = Image.new("RGBA", (max(1, int(size[0])), max(1, int(size[1]))), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([(0, 0), (img.width - 1, img.height - 1)], radius=radius, fill=fill, outline=outline, width=width)
    return img

def wrap_capsules(slots, pair, max_width, pad_x=28, pad_y=10, gap=14):
    pad_x *= S; pad_y *= S; gap *= S
    asc, desc = line_metrics(pair)
    cap_h = asc + desc + pad_y * 2
    rows, current, current_w = [], [], 0
    for slot in slots:
        w = text_width(slot, pair) + pad_x * 2
        candidate_w = w if not current else current_w + gap + w
        if current and candidate_w > max_width:
            rows.append(current)
            current, current_w = [(slot, w)], w
        else:
            current.append((slot, w))
            current_w = candidate_w
    if current:
        rows.append(current)
    return rows, cap_h, gap

def render(services, subtitle="на сегодня", out_path="okoshki.png"):
    img = Image.new("RGB", (W, H), CREAM)
    draw = ImageDraw.Draw(img)

    margin = 44
    draw.rectangle([(margin * S, margin * S), (W - margin * S, H - margin * S)],
                   outline=GOLD, width=max(1, int(1.8 * S)))
    corner_accents(draw, margin)

    cx = W // 2

    p_label = font_pair("400-normal", 25)
    p_logo = font_pair("700-italic", 66)
    p_title = font_pair("600-normal", 60)
    p_sub = font_pair("500-italic", 38)
    p_master = font_pair("600-normal", 36)
    p_capsule = font_pair("400-normal", 30)
    p_phone = font_pair("700-normal", 42)
    p_addr = font_pair("400-italic", 28)

    draw_mixed(draw, (cx, 168 * S), "СТУДИЯ КРАСОТЫ", p_label, GOLD, tracking=6)
    draw_mixed(draw, (cx, 268 * S), "Лупалова", p_logo, DARK)
    divider(draw, cx, 335 * S)

    draw_mixed(draw, (cx, 450 * S), "Свободные окошки", p_title, DARK)
    draw_mixed(draw, (cx, 522 * S), subtitle, p_sub, GOLD)

    panel_margin_x = 84 * S
    panel_w = W - 2 * panel_margin_x
    pad = 30 * S
    inner_w = panel_w - 2 * pad

    y = 700 * S
    gap_between_panels = 34 * S
    label_asc, label_desc = line_metrics(p_label)
    master_asc, master_desc = line_metrics(p_master)

    for svc in services:
        master_blocks = []
        h = pad
        h += label_asc + label_desc
        h += 26 * S
        for mi, m in enumerate(svc["masters"]):
            rows, cap_h, cap_gap = wrap_capsules(m["slots"], p_capsule, inner_w)
            name_h = master_asc + master_desc
            block_h = name_h + 16 * S + len(rows) * cap_h + max(0, len(rows) - 1) * (10 * S)
            master_blocks.append((m, rows, cap_h, cap_gap, name_h))
            h += block_h
            if mi != len(svc["masters"]) - 1:
                h += 30 * S
        h += pad

        panel_top = y
        panel_layer = rounded_rect_rgba(
            (panel_w, h), radius=4 * S,
            fill=(GOLD[0], GOLD[1], GOLD[2], int(0.06 * 255)),
            outline=(GOLD[0], GOLD[1], GOLD[2], int(0.55 * 255)),
            width=max(1, int(1.5 * S)),
        )
        img.paste(panel_layer, (int(panel_margin_x), int(panel_top)), panel_layer)

        cursor_y = panel_top + pad
        draw_mixed(draw, (cx, cursor_y + label_asc / 2), svc["label"], p_label, GOLD, tracking=5)
        cursor_y += label_asc + label_desc + 26 * S

        for m, rows, cap_h, cap_gap, name_h in master_blocks:
            draw_mixed(draw, (cx, cursor_y + name_h / 2), m["name"], p_master, DARK)
            cursor_y += name_h + 16 * S
            for row in rows:
                row_w = sum(w for _, w in row) + cap_gap * (len(row) - 1)
                rx = cx - row_w / 2
                for text, w in row:
                    cap_layer = rounded_rect_rgba(
                        (w, cap_h), radius=int(40 * S),
                        fill=(CREAM[0], CREAM[1], CREAM[2], 255),
                        outline=(GOLD[0], GOLD[1], GOLD[2], 255),
                        width=max(1, int(1.5 * S)),
                    )
                    img.paste(cap_layer, (int(rx), int(cursor_y)), cap_layer)
                    draw_mixed(draw, (rx + w / 2, cursor_y + cap_h / 2), text, p_capsule, DARK)
                    rx += w + cap_gap
                cursor_y += cap_h + 10 * S
            cursor_y += 20 * S

        y = panel_top + h + gap_between_panels

    foot_divider_y = H - 270 * S
    divider(draw, cx, foot_divider_y)
    draw_mixed(draw, (cx, H - 225 * S), "ЗАПИСЬ ПО ТЕЛЕФОНУ", p_label, GOLD, tracking=5)
    draw_mixed(draw, (cx, H - 168 * S), "+7 (905) 523-77-29", p_phone, DARK)
    draw_mixed(draw, (cx, H - 122 * S), "Химки, кв. Ивакино, к. 1", p_addr, DARK_SECOND)

    final = img.resize((1080, 1920), Image.LANCZOS)
    final.save(out_path)
    print("saved", out_path)


if __name__ == "__main__":
    import sys, json
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            data = json.load(f)
        out = sys.argv[2] if len(sys.argv) > 2 else "okoshki_test.png"
        render(data["services"], subtitle=data.get("subtitle", "на сегодня"), out_path=out)
    else:
        print("Использование: python render_okoshki.py services.json [out.png]")
