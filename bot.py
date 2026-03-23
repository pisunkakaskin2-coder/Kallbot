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
user_site_filters: Dict[int, str] = {}
waiting_for_site_input: Set[int] = set()


def get_main_keyboard():
    return ReplyKeyboardMarkup(
        [["Рандом", "По сайту"], ["Клиенты", "Настройки"]],
        resize_keyboard=True,
        is_persistent=True,
    )


def get_settings_keyboard():
    return ReplyKeyboardMarkup(
        [["Точный поиск", "Частичный поиск"], ["Сбросить сайт", "Назад"]],
        resize_keyboard=True,
        is_persistent=True,
    )


def read_lines():
    if not DATA_FILE.exists():
        return []

    with DATA_FILE.open("r", encoding="utf-8", errors="ignore") as f:
        return [line.strip() for line in f if line.strip()]


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


def extract_site(line: str):
    site, _, _ = parse_line(line)
    return site


def format_line(line: str):
    site, nick, other = parse_line(line)

    if site:
        return f"{site}:{nick}:{other}"
    return f"{nick}:{other}"


def get_all_nicks(lines):
    return list({extract_nick(line) for line in lines if extract_nick(line)})


def get_all_clients(lines):
    clients = {extract_site(line) for line in lines if extract_site(line)}
    return sorted(clients)


def filter_lines_by_site(lines, site_filter: str):
    if not site_filter:
        return lines

    s = site_filter.strip().lower()
    result = []

    for line in lines:
        site = extract_site(line).lower()
        if s in site:
            result.append(line)

    return result


def search(lines, query, mode, site_filter=""):
    filtered = filter_lines_by_site(lines, site_filter)
    q = query.lower()
    result = []

    for line in filtered:
        nick = extract_nick(line).lower()

        if mode == SEARCH_MODE_EXACT:
            if nick == q:
                result.append(format_line(line))
        else:
            if q in nick:
                result.append(format_line(line))

    return result


def get_random(lines, site_filter=""):
    filtered = filter_lines_by_site(lines, site_filter)
    nicks = get_all_nicks(filtered)

    if not nicks:
        return None

    nick = random.choice(nicks)
    found = [format_line(l) for l in filtered if extract_nick(l).lower() == nick.lower()]
    return nick, found


async def send(update, title, lines):
    if not lines:
        await update.message.reply_text("Ничего не найдено.", reply_markup=get_main_keyboard())
        return

    text = title + "\n\n" + "\n".join(lines)

    if len(text) < 3500:
        await update.message.reply_text(text, reply_markup=get_main_keyboard())
    else:
        bio = BytesIO("\n".join(lines).encode("utf-8"))
        bio.name = "results.txt"
        await update.message.reply_document(bio, caption=title, reply_markup=get_main_keyboard())


async def send_clients(update, clients):
    if not clients:
        await update.message.reply_text("Клиенты не найдены.", reply_markup=get_main_keyboard())
        return

    text = "Список клиентов:\n\n" + "\n".join(clients)

    if len(text) < 3500:
        await update.message.reply_text(text, reply_markup=get_main_keyboard())
    else:
        bio = BytesIO("\n".join(clients).encode("utf-8"))
        bio.name = "clients.txt"
        await update.message.reply_document(
            bio,
            caption=f"Список клиентов: {len(clients)}",
            reply_markup=get_main_keyboard(),
        )


def get_mode(uid):
    return user_modes.get(uid, SEARCH_MODE_PARTIAL)


def get_site_filter(uid):
    return user_site_filters.get(uid, "")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    mode_text = "Точный" if get_mode(uid) == SEARCH_MODE_EXACT else "Частичный"
    site_filter = get_site_filter(uid) or "не выбран"

    await update.message.reply_text(
        "Бот запущен.\n\n"
        "Отправь nickname для поиска.\n"
        "Кнопка «Рандом» выбирает случайный nickname.\n"
        "Кнопка «По сайту» задаёт фильтр сайта.\n"
        "Кнопка «Клиенты» показывает список сайтов из базы.\n\n"
        "Формат базы:\n"
        "https://site/register(login):nickname:other\n"
        "или\n"
        "nickname:other\n\n"
        f"Текущий режим: {mode_text}\n"
        f"Текущий сайт: {site_filter}",
        reply_markup=get_main_keyboard()
    )


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id
    mode = get_mode(uid)
    site_filter = get_site_filter(uid)

    if uid in waiting_for_site_input:
        waiting_for_site_input.remove(uid)
        normalized = normalize_site(text)
        user_site_filters[uid] = normalized
        await update.message.reply_text(
            f"Фильтр сайта установлен: {normalized}",
            reply_markup=get_main_keyboard(),
        )
        return

    if text == "По сайту":
        await update.message.reply_text(
            "Введи часть сайта, например:\ncelka",
            reply_markup=get_main_keyboard(),
        )
        waiting_for_site_input.add(uid)
        return

    if text == "Клиенты":
        lines = read_lines()
        clients = get_all_clients(lines)
        await send_clients(update, clients)
        return

    if text == "Настройки":
        current_site = site_filter or "не выбран"
        current_mode = "Точный поиск" if mode == SEARCH_MODE_EXACT else "Частичный поиск"
        await update.message.reply_text(
            f"Открыты настройки.\nТекущий режим: {current_mode}\nТекущий сайт: {current_site}",
            reply_markup=get_settings_keyboard(),
        )
        return

    if text == "Назад":
        await update.message.reply_text("Возврат в меню.", reply_markup=get_main_keyboard())
        return

    if text == "Точный поиск":
        user_modes[uid] = SEARCH_MODE_EXACT
        await update.message.reply_text("Режим поиска переключён: Точный поиск", reply_markup=get_settings_keyboard())
        return

    if text == "Частичный поиск":
        user_modes[uid] = SEARCH_MODE_PARTIAL
        await update.message.reply_text("Режим поиска переключён: Частичный поиск", reply_markup=get_settings_keyboard())
        return

    if text == "Сбросить сайт":
        user_site_filters.pop(uid, None)
        await update.message.reply_text("Фильтр сайта сброшен.", reply_markup=get_settings_keyboard())
        return

    lines = read_lines()

    if text == "Рандом":
        res = get_random(lines, site_filter)
        if not res:
            await update.message.reply_text("База пуста.", reply_markup=get_main_keyboard())
            return

        nick, found = res
        title = f"Рандом: {nick}"
        if site_filter:
            title += f"\nСайт: {site_filter}"

        await send(update, title, found)
        return

    found = search(lines, text, mode, site_filter)
    title = f"Поиск: {text}"
    if site_filter:
        title += f"\nСайт: {site_filter}"

    await send(update, title, found)


def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Не найден BOT_TOKEN")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    app.run_polling()


if __name__ == "__main__":
    main()
