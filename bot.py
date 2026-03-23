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


def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["Рандом", "Настройки"]],
        resize_keyboard=True,
        is_persistent=True,
    )


def get_settings_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["Точный поиск", "Частичный поиск"], ["Назад"]],
        resize_keyboard=True,
        is_persistent=True,
    )


def ensure_data_file_exists() -> None:
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Файл базы не найден: {DATA_FILE}")


def read_lines() -> List[str]:
    ensure_data_file_exists()
    with DATA_FILE.open("r", encoding="utf-8", errors="ignore") as f:
        lines = [line.rstrip("\n\r") for line in f]
    return [line for line in lines if line.strip()]


def normalize_site(raw_site: str) -> str:
    s = raw_site.strip()

    if s.startswith("https://"):
        s = s[len("https://"):]
    elif s.startswith("http://"):
        s = s[len("http://"):]

    for suffix in ("/register(login)", "/register", "/login"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break

    return s.strip("/")


def parse_line(line: str) -> Tuple[str, str, str]:
    """
    Ожидаемый формат:
    https://site/register(login):nickname:other

    Разбираем СПРАВА, чтобы https:// не ломал split.
    """
    parts = line.rsplit(":", 2)

    if len(parts) != 3:
        return "", "", ""

    raw_site, nickname, other = parts
    site = normalize_site(raw_site)

    return site.strip(), nickname.strip(), other.strip()


def extract_nickname(line: str) -> str:
    _, nickname, _ = parse_line(line)
    return nickname


def format_line_for_output(line: str) -> str:
    site, nickname, other = parse_line(line)

    if site or nickname or other:
        return f"{site}:{nickname}:{other}"

    return line.strip()


def get_all_nicknames(lines: List[str]) -> List[str]:
    nicks: Set[str] = set()

    for line in lines:
        nick = extract_nickname(line)
        if nick:
            nicks.add(nick)

    return list(nicks)


def search_by_nickname(lines: List[str], query: str, mode: str) -> List[str]:
    q = query.strip().lower()
    if not q:
        return []

    found: List[str] = []

    for line in lines:
        nick = extract_nickname(line).lower()

        if mode == SEARCH_MODE_EXACT:
            if nick == q:
                found.append(format_line_for_output(line))
        else:
            if q in nick:
                found.append(format_line_for_output(line))

    return found


def get_random_nickname_with_lines(lines: List[str]) -> Optional[Tuple[str, List[str]]]:
    nicks = get_all_nicknames(lines)
    if not nicks:
        return None

    chosen_nick = random.choice(nicks)
    chosen_lines = []

    for line in lines:
        if extract_nickname(line).lower() == chosen_nick.lower():
            chosen_lines.append(format_line_for_output(line))

    return chosen_nick, chosen_lines


async def send_results(update: Update, title: str, lines: List[str]) -> None:
    if not update.message:
        return

    if not lines:
        await update.message.reply_text(
            "Ничего не найдено.",
            reply_markup=get_main_keyboard(),
        )
        return

    text = title + "\n\n" + "\n".join(lines)

    if len(text) <= 3500:
        await update.message.reply_text(
            text,
            reply_markup=get_main_keyboard(),
        )
        return

    payload = "\n".join(lines).encode("utf-8", errors="ignore")
    bio = BytesIO(payload)
    bio.name = "results.txt"

    await update.message.reply_document(
        document=bio,
        caption=title,
        reply_markup=get_main_keyboard(),
    )


def get_user_mode(user_id: int) -> str:
    return user_modes.get(user_id, SEARCH_MODE_PARTIAL)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    mode = get_user_mode(update.effective_user.id)
    mode_name = "Точный поиск" if mode == SEARCH_MODE_EXACT else "Частичный поиск"

    await update.message.reply_text(
        "Бот запущен.\n\n"
        "Отправь nickname для поиска.\n"
        "Кнопка «Рандом» выбирает случайный nickname.\n\n"
        "Формат базы:\n"
        "https://site/register(login):nickname:other\n\n"
        "В ответе будет:\n"
        "site:nickname:other\n\n"
        f"Текущий режим: {mode_name}",
        reply_markup=get_main_keyboard(),
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    text = (update.message.text or "").strip()
    user_id = update.effective_user.id
    mode = get_user_mode(user_id)

    if not text:
        return

    if text == "Настройки":
        mode_name = "Точный поиск" if mode == SEARCH_MODE_EXACT else "Частичный поиск"
        await update.message.reply_text(
            f"Открыты настройки.\nТекущий режим: {mode_name}",
            reply_markup=get_settings_keyboard(),
        )
        return

    if text == "Назад":
        mode_name = "Точный поиск" if mode == SEARCH_MODE_EXACT else "Частичный поиск"
        await update.message.reply_text(
            f"Возврат в меню.\nТекущий режим: {mode_name}",
            reply_markup=get_main_keyboard(),
        )
        return

    if text == "Точный поиск":
        user_modes[user_id] = SEARCH_MODE_EXACT
        await update.message.reply_text(
            "Режим поиска переключён: Точный поиск",
            reply_markup=get_settings_keyboard(),
        )
        return

    if text == "Частичный поиск":
        user_modes[user_id] = SEARCH_MODE_PARTIAL
        await update.message.reply_text(
            "Режим поиска переключён: Частичный поиск",
            reply_markup=get_settings_keyboard(),
        )
        return

    if text == "Рандом":
        try:
            lines = read_lines()
            result = get_random_nickname_with_lines(lines)
        except Exception as e:
            logger.exception("Ошибка при обработке рандома")
            await update.message.reply_text(
                f"Ошибка:\n{e}",
                reply_markup=get_main_keyboard(),
            )
            return

        if not result:
            await update.message.reply_text(
                "База пуста.",
                reply_markup=get_main_keyboard(),
            )
            return

        nickname, found_lines = result
        await send_results(
            update,
            title=f"Рандомный nickname: {nickname}\nНайдено строк: {len(found_lines)}",
            lines=found_lines,
        )
        return

    try:
        lines = read_lines()
        found_lines = search_by_nickname(lines, text, mode)
    except Exception as e:
        logger.exception("Ошибка поиска")
        await update.message.reply_text(
            f"Ошибка:\n{e}",
            reply_markup=get_main_keyboard(),
        )
        return

    mode_name = "точный" if mode == SEARCH_MODE_EXACT else "частичный"

    await send_results(
        update,
        title=f"Поиск по nickname: {text}\nРежим: {mode_name}\nНайдено строк: {len(found_lines)}",
        lines=found_lines,
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Произошла ошибка", exc_info=context.error)


def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Не найден BOT_TOKEN в переменных окружения Railway.")

    ensure_data_file_exists()

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(on_error)

    logger.info("Бот запущен...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
