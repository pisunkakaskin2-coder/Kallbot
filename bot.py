import logging
import os
import random
from io import BytesIO
from pathlib import Path
from typing import Dict, Set

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).with_name("userdata.txt")

SEARCH_MODE_EXACT = "exact"
SEARCH_MODE_PARTIAL = "partial"

user_modes: Dict[int, str] = {}
user_site_filters: Dict[int, str] = {}
waiting_for_site_input: Set[int] = set()

# 🔥 список клиентов
CLIENTS_TEXT = """celka.xyz
nursultan.fun
pulsevisuals.pro
wexside.ru
deltaclient.site
arbuz.cc
britva.ru
dimasikclient.ru
rockstar.pub
rich-dlc.tech
cortexclient.com
neverlose.tech
monotondlc.space
quickclient.cc
arcadeclient.xyz
privatedlc.xyz
alphadlc.ru
grimclient.pl
akrien.wtf
newcode.cc
energyclient.su
catlavan.xyz
mc.fringeworld.ru"""


def get_main_keyboard():
    return ReplyKeyboardMarkup(
        [["Рандом", "По сайту"], ["Клиенты", "Настройки"]],
        resize_keyboard=True,
    )


def get_settings_keyboard():
    return ReplyKeyboardMarkup(
        [["Точный поиск", "Частичный поиск"], ["Сбросить сайт", "Назад"]],
        resize_keyboard=True,
    )


def read_lines():
    if not DATA_FILE.exists():
        return []
    with DATA_FILE.open("r", encoding="utf-8", errors="ignore") as f:
        return [line.strip() for line in f if line.strip()]


def normalize_site(s: str):
    s = s.replace("https://", "").replace("http://", "")
    for x in ("/register(login)", "/register", "/login"):
        if s.endswith(x):
            s = s[: -len(x)]
    return s.strip("/")


def parse_line(line: str):
    parts = line.rsplit(":", 2)

    if len(parts) == 3:
        site, nick, other = parts
        return normalize_site(site), nick.strip(), other.strip()

    if len(parts) == 2:
        nick, other = parts
        return "", nick.strip(), other.strip()

    return "", "", ""


def extract_nick(line):
    return parse_line(line)[1]


def extract_site(line):
    return parse_line(line)[0]


def format_line(line):
    site, nick, other = parse_line(line)
    return f"{site}:{nick}:{other}" if site else f"{nick}:{other}"


def filter_by_site(lines, site_filter):
    if not site_filter:
        return lines
    s = site_filter.lower()
    return [l for l in lines if s in extract_site(l).lower()]


def search(lines, query, mode, site_filter):
    lines = filter_by_site(lines, site_filter)
    q = query.lower()
    result = []

    for l in lines:
        nick = extract_nick(l).lower()
        if (mode == SEARCH_MODE_EXACT and nick == q) or (
            mode == SEARCH_MODE_PARTIAL and q in nick
        ):
            result.append(format_line(l))

    return result


def get_random(lines, site_filter):
    lines = filter_by_site(lines, site_filter)
    nicks = list({extract_nick(l) for l in lines if extract_nick(l)})

    if not nicks:
        return None

    nick = random.choice(nicks)
    return nick, [format_line(l) for l in lines if extract_nick(l) == nick]


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
        await update.message.reply_document(bio, caption=title)


def get_mode(uid):
    return user_modes.get(uid, SEARCH_MODE_PARTIAL)


def get_site(uid):
    return user_site_filters.get(uid, "")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    await update.message.reply_text(
        "Бот запущен.\n\n"
        "Отправь nickname для поиска.\n\n"
        "📌 Список сайтов:\n"
        f"{CLIENTS_TEXT}\n",
        reply_markup=get_main_keyboard(),
    )


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id

    if uid in waiting_for_site_input:
        waiting_for_site_input.remove(uid)
        user_site_filters[uid] = normalize_site(text)
        await update.message.reply_text("Сайт установлен", reply_markup=get_main_keyboard())
        return

    if text == "Клиенты":
        await update.message.reply_text(
            "Список клиентов:\n\n" + CLIENTS_TEXT,
            reply_markup=get_main_keyboard(),
        )
        return

    if text == "По сайту":
        waiting_for_site_input.add(uid)
        await update.message.reply_text("Введи часть сайта (пример: celka)")
        return

    if text == "Настройки":
        await update.message.reply_text("Настройки", reply_markup=get_settings_keyboard())
        return

    if text == "Назад":
        await update.message.reply_text("Меню", reply_markup=get_main_keyboard())
        return

    if text == "Точный поиск":
        user_modes[uid] = SEARCH_MODE_EXACT
        await update.message.reply_text("Ок")
        return

    if text == "Частичный поиск":
        user_modes[uid] = SEARCH_MODE_PARTIAL
        await update.message.reply_text("Ок")
        return

    if text == "Сбросить сайт":
        user_site_filters.pop(uid, None)
        await update.message.reply_text("Сайт сброшен")
        return

    lines = read_lines()

    if text == "Рандом":
        res = get_random(lines, get_site(uid))
        if not res:
            await update.message.reply_text("База пуста")
            return

        nick, found = res
        await send(update, f"Рандом: {nick}", found)
        return

    found = search(lines, text, get_mode(uid), get_site(uid))
    await send(update, f"Поиск: {text}", found)


def main():
    token = os.getenv("BOT_TOKEN")
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    app.run_polling()


if __name__ == "__main__":
    main()
