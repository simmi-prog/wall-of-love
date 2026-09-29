#!/usr/bin/env python3
"""Fetch pinned messages from Firestore and export a styled two-column PDF."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

PROJECT_ID = "wall-of-love-f9f28"
COLLECTION = "messages"
RECIPIENT = "Dan"
FONTS_DIR = Path(__file__).parent / "fonts"
ASSETS_DIR = Path(__file__).parent
BOUQUET_CANDIDATES = (ASSETS_DIR / "flower.jpg", ASSETS_DIR / "bouquet.jpg")
CACHE_DIR = ASSETS_DIR / ".cache"
CLEAN_BOUQUET = CACHE_DIR / "bouquet-clean.png"

FONT_URLS = {
    "Caveat.ttf": (
        "https://raw.githubusercontent.com/google/fonts/main/ofl/caveat/"
        "Caveat%5Bwght%5D.ttf"
    ),
    "GreatVibes.ttf": (
        "https://raw.githubusercontent.com/google/fonts/main/ofl/greatvibes/"
        "GreatVibes-Regular.ttf"
    ),
    "GloriaHallelujah.ttf": (
        "https://raw.githubusercontent.com/google/fonts/main/ofl/gloriahallelujah/"
        "GloriaHallelujah.ttf"
    ),
}

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
COL_GAP = 8 * mm
CARD_GAP = 8 * mm
PAD_TOP = 20
PAD_H = 18
PAD_BOTTOM = 16
PIN_SIZE = 7

PAGE_BG = colors.HexColor("#12241f")
COVER_BG = colors.HexColor("#faf8f4")
CARD_BG = colors.HexColor("#f6efdd")
INK = colors.HexColor("#1c2a25")
CORAL = colors.HexColor("#d9714a")
DATE_COLOR = colors.HexColor("#a89a7a")
COVER_TITLE = colors.HexColor("#2c2c2c")
COVER_SUBTITLE = colors.HexColor("#888888")
GOLD = colors.HexColor("#c99a3b")
GOLD_BRIGHT = colors.HexColor("#e0b45c")
SHADOW = colors.Color(0, 0, 0, alpha=0.28)

MSG_FONT = "Caveat"
NAME_FONT = "GreatVibes"
DATE_FONT = "GloriaHallelujah"

MSG_SIZE = 16
MSG_LEADING = 19
NAME_SIZE = 22
DATE_SIZE = 11


def ensure_fonts() -> None:
    FONTS_DIR.mkdir(exist_ok=True)
    for filename, url in FONT_URLS.items():
        font_path = FONTS_DIR / filename
        if not font_path.exists():
            print(f"Downloading {filename}...")
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            font_path.write_bytes(response.content)

    pdfmetrics.registerFont(TTFont(MSG_FONT, str(FONTS_DIR / "Caveat.ttf")))
    pdfmetrics.registerFont(TTFont(NAME_FONT, str(FONTS_DIR / "GreatVibes.ttf")))
    pdfmetrics.registerFont(TTFont(DATE_FONT, str(FONTS_DIR / "GloriaHallelujah.ttf")))


def fetch_messages(project_id: str, collection: str) -> list[dict]:
    url = (
        f"https://firestore.googleapis.com/v1/projects/{project_id}"
        f"/databases/(default)/documents/{collection}"
    )
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    docs = response.json().get("documents", [])
    messages = []
    for doc in docs:
        fields = doc.get("fields", {})
        messages.append(
            {
                "name": fields.get("name", {}).get("stringValue", "").strip(),
                "message": fields.get("message", {}).get("stringValue", "").strip(),
                "timestamp": fields.get("timestamp", {}).get("stringValue", ""),
            }
        )
    messages.sort(key=lambda item: item["timestamp"])
    return [m for m in messages if m["name"] and m["message"]]


def format_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return f"{dt.strftime('%b')} {dt.day}"
    except (TypeError, ValueError):
        return ""


def wrap_text(text: str, font_name: str, font_size: float, max_width: float) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            if pdfmetrics.stringWidth(trial, font_name, font_size) <= max_width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines or [""]


def measure_card_height(message: dict, col_width: float) -> float:
    text_width = col_width - (2 * PAD_H)
    body_lines = wrap_text(message["message"], MSG_FONT, MSG_SIZE, text_width)
    line_count = max(1, len(body_lines))
    body_height = line_count * MSG_LEADING
    meta_height = 14 + NAME_SIZE + 4 + DATE_SIZE
    return PAD_TOP + 6 + body_height + meta_height + PAD_BOTTOM


def find_bouquet_image() -> Path:
    for path in BOUQUET_CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError("No bouquet image found (flower.jpg or bouquet.jpg).")


def _is_background_pixel(r: int, g: int, b: int) -> bool:
    spread = max(r, g, b) - min(r, g, b)
    avg = (r + g + b) / 3
    return spread <= 30 and avg >= 165


def prepare_bouquet_image(source: Path) -> Path:
    CACHE_DIR.mkdir(exist_ok=True)
    if CLEAN_BOUQUET.exists() and CLEAN_BOUQUET.stat().st_mtime >= source.stat().st_mtime:
        return CLEAN_BOUQUET

    img = Image.open(source).convert("RGBA")
    pixels = [
        (r, g, b, 0 if _is_background_pixel(r, g, b) else 255)
        for r, g, b, _ in img.getdata()
    ]
    img.putdata(pixels)
    img.save(CLEAN_BOUQUET, "PNG")
    return CLEAN_BOUQUET


def draw_page_background(c: canvas.Canvas) -> None:
    c.setFillColor(PAGE_BG)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    c.setFillColor(colors.Color(0.78, 0.6, 0.23, alpha=0.08))
    c.circle(-20, PAGE_H + 20, 90, fill=1, stroke=0)
    c.circle(PAGE_W + 30, -30, 110, fill=1, stroke=0)


def draw_cover_page(c: canvas.Canvas) -> None:
    c.setFillColor(COVER_BG)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    center_x = PAGE_W / 2
    bouquet = prepare_bouquet_image(find_bouquet_image())
    img_w, img_h = ImageReader(str(bouquet)).getSize()
    display_w = min(120 * mm, PAGE_W - (2 * MARGIN))
    display_h = display_w * img_h / img_w

    title_size = 42
    subtitle_size = 19
    gap_after_img = 14 * mm
    gap_after_title = 10 * mm
    block_h = display_h + gap_after_img + title_size + gap_after_title + subtitle_size + 28 * mm
    block_top = (PAGE_H + block_h) / 2

    img_y = block_top - display_h
    c.drawImage(
        str(bouquet),
        center_x - display_w / 2,
        img_y,
        width=display_w,
        height=display_h,
        preserveAspectRatio=True,
        mask="auto",
    )

    title_y = img_y - gap_after_img
    c.setFillColor(COVER_TITLE)
    c.setFont(MSG_FONT, title_size)
    c.drawCentredString(center_x, title_y, f"For {RECIPIENT}")

    subtitle_y = title_y - gap_after_title - subtitle_size
    c.setFillColor(COVER_SUBTITLE)
    c.setFont(MSG_FONT, subtitle_size)
    c.drawCentredString(
        center_x,
        subtitle_y,
        "A little bouquet of appreciation from your colleagues",
    )

    line_y = subtitle_y - 14 * mm
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.2)
    c.line(center_x - 38 * mm, line_y, center_x + 38 * mm, line_y)

    note_label = "Notes pinned with love"
    c.setFillColor(GOLD_BRIGHT)
    c.setFont(DATE_FONT, 13)
    c.drawCentredString(center_x, line_y - 8 * mm, note_label)


def draw_wall_opener(c: canvas.Canvas) -> float:
    center_x = PAGE_W / 2
    top_y = PAGE_H - MARGIN

    c.setStrokeColor(colors.Color(0.78, 0.6, 0.23, alpha=0.45))
    c.setLineWidth(1)
    c.line(center_x - 42 * mm, top_y - 4, center_x + 42 * mm, top_y - 4)

    c.setFillColor(GOLD_BRIGHT)
    c.setFont(DATE_FONT, 12)
    c.drawCentredString(center_x, top_y - 18, "Messages from your colleagues")

    return top_y - 32


def draw_pin(c: canvas.Canvas, cx: float, cy: float) -> None:
    c.setFillColor(colors.HexColor("#8a6a24"))
    c.circle(cx, cy, PIN_SIZE, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#c99a3b"))
    c.circle(cx - 1.5, cy + 1.5, PIN_SIZE * 0.82, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#e0b45c"))
    c.circle(cx - 2, cy + 2, PIN_SIZE * 0.48, fill=1, stroke=0)


def draw_card(
    c: canvas.Canvas,
    message: dict,
    x: float,
    top_y: float,
    col_width: float,
    card_height: float,
) -> None:
    bottom_y = top_y - card_height
    radius = 3

    c.setFillColor(SHADOW)
    c.roundRect(x + 1, bottom_y - 6, col_width, card_height, radius, fill=1, stroke=0)

    c.setFillColor(CARD_BG)
    c.setStrokeColor(CARD_BG)
    c.roundRect(x, bottom_y, col_width, card_height, radius, fill=1, stroke=0)

    pin_y = top_y + 2
    draw_pin(c, x + (col_width / 2), pin_y)

    text_x = x + PAD_H
    text_width = col_width - (2 * PAD_H)
    cursor_y = top_y - PAD_TOP - 6

    c.setFillColor(INK)
    c.setFont(MSG_FONT, MSG_SIZE)
    for line in wrap_text(message["message"], MSG_FONT, MSG_SIZE, text_width):
        c.drawString(text_x, cursor_y - MSG_SIZE, line)
        cursor_y -= MSG_LEADING

    cursor_y -= 14
    c.setFillColor(CORAL)
    c.setFont(NAME_FONT, NAME_SIZE)
    c.drawString(text_x, cursor_y - NAME_SIZE, message["name"])

    date_text = format_date(message["timestamp"])
    if date_text:
        cursor_y -= NAME_SIZE + 4
        c.setFillColor(DATE_COLOR)
        c.setFont(DATE_FONT, DATE_SIZE)
        c.drawString(text_x, cursor_y - DATE_SIZE, date_text)


def generate_pdf(messages: list[dict], output_path: Path) -> None:
    col_width = (PAGE_W - (2 * MARGIN) - COL_GAP) / 2
    left_x = MARGIN
    right_x = MARGIN + col_width + COL_GAP
    min_y = MARGIN
    top_y = PAGE_H - MARGIN

    c = canvas.Canvas(str(output_path), pagesize=A4)
    c.setTitle(f"For {RECIPIENT} — Wall of Love")

    draw_cover_page(c)
    c.showPage()
    draw_page_background(c)

    left_y = draw_wall_opener(c)
    right_y = left_y

    def card_fits(y: float, card_height: float) -> bool:
        return y - card_height >= min_y

    def start_new_page() -> None:
        nonlocal left_y, right_y
        c.showPage()
        draw_page_background(c)
        left_y = top_y
        right_y = top_y

    for message in messages:
        card_height = measure_card_height(message, col_width)

        if not card_fits(left_y, card_height) and not card_fits(right_y, card_height):
            start_new_page()

        left_fits = card_fits(left_y, card_height)
        right_fits = card_fits(right_y, card_height)

        if left_fits and right_fits:
            use_left = left_y >= right_y
        elif left_fits:
            use_left = True
        elif right_fits:
            use_left = False
        else:
            start_new_page()
            use_left = True

        if use_left:
            draw_card(c, message, left_x, left_y, col_width, card_height)
            left_y -= card_height + CARD_GAP
        else:
            draw_card(c, message, right_x, right_y, col_width, card_height)
            right_y -= card_height + CARD_GAP

    c.save()


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Wall of Love messages to PDF.")
    parser.add_argument(
        "-o",
        "--output",
        default="for-dan-messages.pdf",
        help="Output PDF path (default: for-dan-messages.pdf)",
    )
    parser.add_argument(
        "--project-id",
        default=PROJECT_ID,
        help=f"Firebase project ID (default: {PROJECT_ID})",
    )
    args = parser.parse_args()

    ensure_fonts()
    print("Fetching messages from Firestore...")
    messages = fetch_messages(args.project_id, COLLECTION)
    if not messages:
        raise SystemExit("No messages found on the wall.")

    output_path = Path(args.output)
    print(f"Generating PDF with {len(messages)} message(s)...")
    generate_pdf(messages, output_path)
    print(f"Saved: {output_path.resolve()}")


if __name__ == "__main__":
    main()
