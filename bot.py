#!/usr/bin/env python3
"""
GitHub Release Notifier Bot
Следит за релизами GitHub-репозиториев и уведомляет в Telegram.
"""

import html
import json
import logging
import os
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, filters

load_dotenv()

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = int(os.environ["CHAT_ID"])
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "3600"))

_data_dir = Path(os.getenv("DATA_DIR", "."))
_data_dir.mkdir(parents=True, exist_ok=True)

REPOS_FILE = _data_dir / "repos.json"
VERSIONS_FILE = _data_dir / "versions.json"

# owner/repo — допустимые символы для GitHub
REPO_RE = re.compile(r"^[a-zA-Z0-9_.\-]+/[a-zA-Z0-9_.\-]+$")


# ---------------------------------------------------------------------------
# Хранилище
# ---------------------------------------------------------------------------


def load_repos() -> list[str]:
    if REPOS_FILE.exists():
        data = json.loads(REPOS_FILE.read_text())
        return data if isinstance(data, list) else []
    # При первом запуске — берём значение из env (если есть)
    default = os.getenv("GITHUB_REPO", "MHSanaei/3x-ui")
    return [default]


def save_repos(repos: list[str]) -> None:
    REPOS_FILE.write_text(json.dumps(repos, ensure_ascii=False, indent=2))


def load_versions() -> dict[str, str]:
    if VERSIONS_FILE.exists():
        data = json.loads(VERSIONS_FILE.read_text())
        return data if isinstance(data, dict) else {}
    return {}


def save_versions(versions: dict[str, str]) -> None:
    VERSIONS_FILE.write_text(json.dumps(versions, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# GitHub API
# ---------------------------------------------------------------------------


async def fetch_latest_release(repo: str) -> dict:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            url,
            headers={"Accept": "application/vnd.github+json"},
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.json()


def format_release_message(repo: str, release: dict, *, old_version: str | None = None) -> str:
    tag = html.escape(release.get("tag_name", "unknown"))
    name = html.escape(release.get("name") or release.get("tag_name", ""))
    html_url = release.get("html_url", f"https://github.com/{repo}/releases")
    published = release.get("published_at", "")[:10]
    is_prerelease = release.get("prerelease", False)

    body = (release.get("body") or "").strip()
    if len(body) > 3000:
        body = body[:3000] + "\n…"

    header = "🔖 Pre-release" if is_prerelease else "🚀 Новый релиз"
    parts = [
        f"{header} <b>{html.escape(repo)}</b>",
        "",
        f"<b>Версия:</b> <code>{tag}</code>",
    ]

    if old_version:
        parts.append(f"<b>Предыдущая:</b> <code>{html.escape(old_version)}</code>")

    parts += [
        f"<b>Название:</b> {name}",
        f"<b>Дата:</b> {published}",
    ]

    if body:
        parts += ["", "<b>Описание релиза:</b>", f"<pre>{html.escape(body)}</pre>"]

    parts += ["", f'<a href="{html_url}">Открыть на GitHub</a>']

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Фоновая проверка
# ---------------------------------------------------------------------------


async def check_for_update(context: ContextTypes.DEFAULT_TYPE) -> None:
    repos = load_repos()
    if not repos:
        logger.info("Нет репозиториев для проверки.")
        return

    logger.info("Проверяем %d репозитори(ев)...", len(repos))
    versions = load_versions()
    changed = False

    for repo in repos:
        try:
            release = await fetch_latest_release(repo)
            latest = release["tag_name"]
            last = versions.get(repo)

            if last is None:
                versions[repo] = latest
                changed = True
                logger.info("[%s] Первый запуск, запомнили: %s", repo, latest)
                continue

            if latest != last:
                logger.info("[%s] Новая версия: %s → %s", repo, last, latest)
                versions[repo] = latest
                changed = True
                await context.bot.send_message(
                    chat_id=CHAT_ID,
                    text=format_release_message(repo, release, old_version=last),
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False,
                )
            else:
                logger.info("[%s] Без изменений: %s", repo, latest)

        except httpx.HTTPStatusError as e:
            logger.error("[%s] HTTP ошибка: %s", repo, e)
        except Exception as e:
            logger.exception("[%s] Ошибка: %s", repo, e)

    if changed:
        save_versions(versions)


# ---------------------------------------------------------------------------
# Команды бота
# ---------------------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    repos = load_repos()
    count = len(repos)
    text = (
        f"<b>GitHub Release Notifier</b> запущен.\n\n"
        f"Отслеживается репозиториев: <b>{count}</b>\n"
        f"Интервал проверки: <b>{CHECK_INTERVAL // 60} мин.</b>\n\n"
        f"Команды:\n"
        f"/list — список отслеживаемых репозиториев\n"
        f"/add owner/repo — добавить репозиторий\n"
        f"/remove owner/repo — удалить репозиторий\n"
        f"/check — проверить все репозитории прямо сейчас"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    repos = load_repos()
    versions = load_versions()

    if not repos:
        await update.message.reply_text("Список пуст. Добавь репозиторий: /add owner/repo")
        return

    lines = ["<b>Отслеживаемые репозитории:</b>", ""]
    for repo in repos:
        ver = versions.get(repo, "не проверялся")
        lines.append(f"• <code>{html.escape(repo)}</code> — <code>{html.escape(ver)}</code>")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Использование: /add owner/repo")
        return

    repo = context.args[0].strip().strip("/")

    if not REPO_RE.match(repo):
        await update.message.reply_text(
            f"Неверный формат. Ожидается: <code>owner/repo</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    repos = load_repos()
    if repo in repos:
        await update.message.reply_text(
            f"<code>{html.escape(repo)}</code> уже отслеживается.",
            parse_mode=ParseMode.HTML,
        )
        return

    await update.message.reply_text("Проверяю репозиторий на GitHub…")
    try:
        release = await fetch_latest_release(repo)
        latest = release["tag_name"]
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            await update.message.reply_text(
                f"Репозиторий <code>{html.escape(repo)}</code> не найден или у него нет релизов.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await update.message.reply_text(f"Ошибка GitHub API: {e.response.status_code}")
        return
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {html.escape(str(e))}", parse_mode=ParseMode.HTML)
        return

    repos.append(repo)
    save_repos(repos)

    versions = load_versions()
    versions[repo] = latest
    save_versions(versions)

    await update.message.reply_text(
        f"Добавлен <code>{html.escape(repo)}</code>.\n"
        f"Текущая версия: <code>{html.escape(latest)}</code>\n\n"
        f"Уведомление придёт при следующем релизе.",
        parse_mode=ParseMode.HTML,
    )


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Использование: /remove owner/repo")
        return

    repo = context.args[0].strip().strip("/")
    repos = load_repos()

    if repo not in repos:
        await update.message.reply_text(
            f"<code>{html.escape(repo)}</code> не найден в списке.",
            parse_mode=ParseMode.HTML,
        )
        return

    repos.remove(repo)
    save_repos(repos)

    versions = load_versions()
    versions.pop(repo, None)
    save_versions(versions)

    await update.message.reply_text(
        f"<code>{html.escape(repo)}</code> удалён из отслеживания.",
        parse_mode=ParseMode.HTML,
    )


async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    repos = load_repos()
    if not repos:
        await update.message.reply_text("Список пуст. Добавь репозиторий: /add owner/repo")
        return

    await update.message.reply_text(f"Проверяю {len(repos)} репозитори(ев)…")
    versions = load_versions()
    changed = False
    results: list[str] = []

    for repo in repos:
        try:
            release = await fetch_latest_release(repo)
            latest = release["tag_name"]
            last = versions.get(repo)

            if last is None:
                versions[repo] = latest
                changed = True
                results.append(f"• <code>{html.escape(repo)}</code> — запомнена версия <code>{html.escape(latest)}</code>")
            elif latest != last:
                versions[repo] = latest
                changed = True
                results.append(f"• <code>{html.escape(repo)}</code> — новая версия <code>{html.escape(latest)}</code>!")
                await update.message.reply_text(
                    format_release_message(repo, release, old_version=last),
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False,
                )
            else:
                results.append(f"• <code>{html.escape(repo)}</code> — без изменений (<code>{html.escape(latest)}</code>)")

        except httpx.HTTPStatusError as e:
            results.append(f"• <code>{html.escape(repo)}</code> — ошибка HTTP {e.response.status_code}")
        except Exception as e:
            results.append(f"• <code>{html.escape(repo)}</code> — ошибка: {html.escape(str(e))}")

    if changed:
        save_versions(versions)

    summary = "<b>Результат проверки:</b>\n\n" + "\n".join(results)
    await update.message.reply_text(summary, parse_mode=ParseMode.HTML)


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------


def main() -> None:
    logger.info("Запуск бота (интервал: %ds, chat_id: %d)", CHECK_INTERVAL, CHAT_ID)

    # Инициализируем repos.json при первом запуске
    if not REPOS_FILE.exists():
        save_repos(load_repos())

    app = Application.builder().token(BOT_TOKEN).build()

    only = filters.Chat(CHAT_ID)
    app.add_handler(CommandHandler("start", cmd_start, filters=only))
    app.add_handler(CommandHandler("list", cmd_list, filters=only))
    app.add_handler(CommandHandler("add", cmd_add, filters=only))
    app.add_handler(CommandHandler("remove", cmd_remove, filters=only))
    app.add_handler(CommandHandler("check", cmd_check, filters=only))

    app.job_queue.run_repeating(
        check_for_update,
        interval=CHECK_INTERVAL,
        first=10,
    )

    logger.info("Бот запущен. Ctrl+C для остановки.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
