#!/usr/bin/env python3
"""
3x-ui Release Notifier Bot
Периодически проверяет новые релизы 3x-ui и отправляет уведомление в Telegram.
"""

import html
import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = int(os.environ["CHAT_ID"])
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "3600"))
GITHUB_REPO = os.getenv("GITHUB_REPO", "MHSanaei/3x-ui")

_data_dir = Path(os.getenv("DATA_DIR", "."))
_data_dir.mkdir(parents=True, exist_ok=True)
VERSION_FILE = _data_dir / "last_version.txt"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"


def load_last_version() -> str | None:
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text().strip() or None
    return None


def save_version(version: str) -> None:
    VERSION_FILE.write_text(version)


async def fetch_latest_release() -> dict:
    """Получить информацию о последнем релизе через GitHub API."""
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            GITHUB_API_URL,
            headers={"Accept": "application/vnd.github+json"},
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.json()


def format_release_message(release: dict) -> str:
    tag = html.escape(release.get("tag_name", "unknown"))
    name = html.escape(release.get("name") or release.get("tag_name", ""))
    html_url = release.get("html_url", GITHUB_RELEASES_URL)
    published = release.get("published_at", "")[:10]

    body = (release.get("body") or "").strip()
    if len(body) > 800:
        body = body[:800] + "…"

    lines = [
        f"🚀 <b>Новый релиз {html.escape(GITHUB_REPO)}</b>",
        "",
        f"<b>Версия:</b> <code>{tag}</code>",
        f"<b>Название:</b> {name}",
        f"<b>Дата:</b> {published}",
    ]

    if body:
        lines += ["", "<b>Что нового:</b>", f"<pre>{html.escape(body)}</pre>"]

    lines += ["", f'<a href="{html_url}">Открыть релиз на GitHub</a>']

    return "\n".join(lines)


async def check_for_update(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Задача планировщика: проверить новый релиз и уведомить."""
    logger.info("Проверяем новый релиз...")
    try:
        release = await fetch_latest_release()
        latest = release["tag_name"]
        last = load_last_version()

        if last is None:
            save_version(latest)
            logger.info("Первый запуск, запомнили версию: %s", latest)
            return

        if latest != last:
            logger.info("Новая версия найдена: %s → %s", last, latest)
            save_version(latest)
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=format_release_message(release),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False,
            )
        else:
            logger.info("Версия не изменилась: %s", latest)

    except httpx.HTTPStatusError as e:
        logger.error("HTTP ошибка при запросе GitHub API: %s", e)
    except Exception as e:
        logger.exception("Неожиданная ошибка при проверке релиза: %s", e)


# ---------------------------------------------------------------------------
# Команды бота
# ---------------------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    last = load_last_version()
    version_info = (
        f"Отслеживаемая версия: <code>{html.escape(last)}</code>"
        if last
        else "Версия ещё не определена."
    )
    text = (
        f"<b>3x-ui Release Notifier</b> запущен.\n\n"
        f"{version_info}\n\n"
        f"Уведомления → чат <code>{CHAT_ID}</code>\n"
        f"Интервал проверки: <b>{CHECK_INTERVAL // 60} мин.</b>\n\n"
        f"Команды:\n"
        f"/check — проверить прямо сейчас\n"
        f"/version — текущая отслеживаемая версия"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_version(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    last = load_last_version()
    if last:
        await update.message.reply_text(
            f"Последняя известная версия: <code>{html.escape(last)}</code>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text("Версия ещё не определена. Подожди первой проверки.")


async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Проверяю GitHub…")
    try:
        release = await fetch_latest_release()
        latest = release["tag_name"]
        last = load_last_version()

        if last is None:
            save_version(latest)
            await update.message.reply_text(
                f"Первая проверка. Запомнил версию: <code>{html.escape(latest)}</code>",
                parse_mode=ParseMode.HTML,
            )
        elif latest != last:
            save_version(latest)
            await update.message.reply_text(
                format_release_message(release),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False,
            )
        else:
            await update.message.reply_text(
                f"Новых версий нет. Текущая: <code>{html.escape(latest)}</code>",
                parse_mode=ParseMode.HTML,
            )
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {html.escape(str(e))}", parse_mode=ParseMode.HTML)


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------


def main() -> None:
    logger.info("Запуск бота (репо: %s, интервал: %ds)", GITHUB_REPO, CHECK_INTERVAL)

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("version", cmd_version))
    app.add_handler(CommandHandler("check", cmd_check))

    # Периодическая проверка
    app.job_queue.run_repeating(
        check_for_update,
        interval=CHECK_INTERVAL,
        first=10,  # первый запуск через 10 секунд после старта
    )

    logger.info("Бот запущен. Ctrl+C для остановки.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
