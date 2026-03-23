import logging
import os
import random
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

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
    return ReplyKeyboardMarkup([["Рандом", "Настройки"]], resize_keyboard=True, is_persistent=True)


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
        return [line.rstrip("\n\r") for line in f if line.strip()]


def parse_line(line: str) -> Tuple[str, str, str]:
    parts = line.split(":", 2)
    if len(parts) == 3:
        site, nick, rest = parts
        return site.strip(), nick.strip(), rest.strip()
    if len(parts) == 2:
        site, nick = parts
        return site.strip(), nick.strip(), ""
    return "", "", line.strip()


def extract_nick(line: str) -> str:
    _, nick, _ = parse_line(line)
    return nick


def extract_rest(line: str) -> str:
    _, _, rest = parse_line(line)
    return rest


def get_all_nicks(lines: List[str]) -> List[str]:
    nicks: Set[str] = set()
    for line in lines:
        nick = extract_nick(line)
        if nick:
            nicks.add(nick)
    return list(nicks)


def search_lines_by_rest(lines: List[str], query: str, mode: str) -> List[str]:
    query = query.strip().lower()
    if not query:
        return []

    results: List[str] = []
    for line in lines:
        rest = extract_rest(line).lower()
        if mode == SEARCH_MODE_EXACT:
            if rest == query:
                results.append(line)
        else:
            if query in rest:
                results.append(line)
    return results


def get_random_nick_with_lines(lines: List[str]) -> Optional[Tuple[str, List[str]]]:
    nicks = get_all_nicks(lines)
    if not nicks:
        return None
    chosen_nick = random.choice(nicks)
    chosen_lines = [line for line in lines if extract_nick(line).lower() == chosen_nick.lower()]
    return chosen_nick, chosen_lines


async def send_results(update: Update, title: str, lines: List[str]) -> None:
    if not update.message:
        return

    if not lines:
        await update.message.reply_text("Ничего не найдено.", reply_markup=get_main_keyboard())
        return

    text = title + "\n\n" + "\n".join(lines)
    if len(text) <= 3500:
        await update.message.reply_text(text, reply_markup=get_main_keyboard())
        return

    payload = "\n".join(lines).encode("utf-8", errors="ignore")
    bio = BytesIO(payload)
    bio.name = "results.txt"
    await update.message.reply_document(document=bio, caption=title, reply_markup=get_main_keyboard())


def get_user_mode(user_id: int) -> str:
    return user_modes.get(user_id, SEARCH_MODE_PARTIAL)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    mode = get_user_mode(update.effective_user.id)
    mode_name = "Точный поиск" if mode == SEARCH_MODE_EXACT else "Частичный поиск"
    await update.message.reply_text(
        "Бот запущен.\n\n"
        "Отправь запрос — поиск пойдёт по части после второго двоеточия.\n"
        "Формат строки: сайт:ник:остальная инфа\n"
        "Кнопка «Рандом» выбирает случайный ник и показывает все строки этого ника.\n\n"
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
        await update.message.reply_text("Режим поиска переключён: Точный поиск", reply_markup=get_settings_keyboard())
        return

    if text == "Частичный поиск":
        user_modes[user_id] = SEARCH_MODE_PARTIAL
        await update.message.reply_text("Режим поиска переключён: Частичный поиск", reply_markup=get_settings_keyboard())
        return

    try:
        lines = read_lines()
    except Exception as e:
        logger.exception("Ошибка чтения базы")
        await update.message.reply_text(f"Ошибка чтения файла базы:\n{e}", reply_markup=get_main_keyboard())
        return

    if text == "Рандом":
        result = get_random_nick_with_lines(lines)
        if not result:
            await update.message.reply_text("База пуста.", reply_markup=get_main_keyboard())
            return
        nick, found_lines = result
        await send_results(update, f"Рандомный ник: {nick}\nНайдено строк: {len(found_lines)}", found_lines)
        return

    found_lines = search_lines_by_rest(lines, text, mode)
    mode_name = "точный" if mode == SEARCH_MODE_EXACT else "частичный"
    await send_results(
        update,
        f"Поиск по остальной инфе: {text}\nРежим: {mode_name}\nНайдено строк: {len(found_lines)}",
        found_lines,
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
