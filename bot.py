import logging
import os
import random
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).with_name("userdata.txt")

SEARCH_MODE_EXACT = "exact"
SEARCH_MODE_PARTIAL = "partial"

user_modes: Dict[int, str] = {}


def get_main_keyboard():
    return ReplyKeyboardMarkup(
        [["Рандом", "Настройки"]],
        resize_keyboard=True,
    )


def get_settings_keyboard():
    return ReplyKeyboardMarkup(
        [["Точный поиск", "Частичный поиск"], ["Назад"]],
        resize_keyboard=True,
    )


def read_lines():
    if not DATA_FILE.exists():
        return []

    with DATA_FILE.open("r", encoding="utf-8", errors="ignore") as f:
        lines = [line.strip() for line in f if line.strip()]

    return lines


def normalize_site(raw_site: str):
    s = raw_site.strip()

    if s.startswith("https://"):
        s = s[8:]
    elif s.startswith("http://"):
        s = s[7:]

    for suffix in ("/register(login)", "/register", "/login"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break

    return s.strip("/")


def parse_line(line: str):
    parts = line.rsplit(":", 2)

    if len(parts) == 3:
        raw_site, nick, other = parts
        return normalize_site(raw_site), nick.strip(), other.strip()

    if len(parts) == 2:
        nick, other = parts
        return "", nick.strip(), other.strip()

    return "", "", ""


def extract_nick(line: str):
    _, nick, _ = parse_line(line)
    return nick


def format_line(line: str):
    site, nick, other = parse_line(line)

    if site:
        return f"{site}:{nick}:{other}"
    return f"{nick}:{other}"


def get_all_nicks(lines):
    return list({extract_nick(line) for line in lines if extract_nick(line)})


def search(lines, query, mode):
    q = query.lower()
    result = []

    for line in lines:
        nick = extract_nick(line).lower()

        if mode == SEARCH_MODE_EXACT:
            if nick == q:
                result.append(format_line(line))
        else:
            if q in nick:
                result.append(format_line(line))

    return result


def get_random(lines):
    nicks = get_all_nicks(lines)
    if not nicks:
        return None

    nick = random.choice(nicks)
    found = [format_line(l) for l in lines if extract_nick(l) == nick]

    return nick, found


async def send(update, title, lines):
    if not lines:
        await update.message.reply_text("Ничего не найдено.", reply_markup=get_main_keyboard())
        return

    text = title + "\n\n" + "\n".join(lines)

    if len(text) < 3500:
        await update.message.reply_text(text, reply_markup=get_main_keyboard())
    else:
        bio = BytesIO("\n".join(lines).encode())
        bio.name = "results.txt"
        await update.message.reply_document(bio, caption=title, reply_markup=get_main_keyboard())


def get_mode(uid):
    return user_modes.get(uid, SEARCH_MODE_PARTIAL)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Бот запущен.\n\n"
        "Отправь nickname для поиска.\n\n"
        "📌 Список сайтов:\n"
        "celka.xyz\nnursultan.fun\npulsevisuals.pro\nwexside.ru\n"
        "deltaclient.site\narbuz.cc\nbritva.ru\ndimasikclient.ru\n"
        "rockstar.pub\nrich-dlc.tech\ncortexclient.com\nneverlose.tech\n"
        "monotondlc.space\nquickclient.cc\narcadeclient.xyz\nprivatedlc.xyz\n"
        "alphadlc.ru\ngr﻿imclient.pl\nakrien.wtf\nnewcode.cc\nenergyclient.su\n"
        "catlavan.xyz\nmc.fringeworld.ru\n\n"
        f"Текущий режим: {'Точный' if get_mode(update.effective_user.id)==SEARCH_MODE_EXACT else 'Частичный'}",
        reply_markup=get_main_keyboard()
    )


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id
    mode = get_mode(uid)

    if text == "Настройки":
        await update.message.reply_text("Настройки:", reply_markup=get_settings_keyboard())
        return

    if text == "Назад":
        await update.message.reply_text("Меню", reply_markup=get_main_keyboard())
        return

    if text == "Точный поиск":
        user_modes[uid] = SEARCH_MODE_EXACT
        await update.message.reply_text("Ок", reply_markup=get_settings_keyboard())
        return

    if text == "Частичный поиск":
        user_modes[uid] = SEARCH_MODE_PARTIAL
        await update.message.reply_text("Ок", reply_markup=get_settings_keyboard())
        return

    lines = read_lines()

    if text == "Рандом":
        res = get_random(lines)
        if not res:
            await update.message.reply_text("База пуста.", reply_markup=get_main_keyboard())
            return

        nick, found = res
        await send(update, f"Рандом: {nick}", found)
        return

    found = search(lines, text, mode)
    await send(update, f"Поиск: {text}", found)


def main():
    token = os.getenv("BOT_TOKEN")
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    app.run_polling()


if __name__ == "__main__":
    main()
