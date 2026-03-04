# GitHub Release Notifier Bot

Telegram-бот для отслеживания новых релизов GitHub-репозиториев. Периодически проверяет GitHub API и отправляет уведомление с описанием релиза, как только появляется новая версия.

## Возможности

- Отслеживание неограниченного количества репозиториев
- Управление списком репозиториев прямо из Telegram (`/add`, `/remove`, `/list`)
- Показывает полное описание релиза (changelog от разработчика)
- Отмечает pre-release версии
- Показывает предыдущую версию рядом с новой
- Все команды доступны только для указанного `CHAT_ID` — посторонние игнорируются
- Хранит состояние между перезапусками (JSON-файлы)
- Запуск через Docker или напрямую

## Быстрый старт (Docker)

**1. Клонировать репозиторий**

```bash
git clone https://github.com/your-username/github-release-notifier-bot
cd github-release-notifier-bot
```

**2. Создать конфиг**

```bash
cp .env.example .env
```

Открыть `.env` и заполнить:

```env
BOT_TOKEN=токен_от_BotFather
CHAT_ID=ваш_id_в_телеграме
```

> Токен бота — у [@BotFather](https://t.me/BotFather).
> Ваш chat\_id — у [@userinfobot](https://t.me/userinfobot).

**3. Запустить**

```bash
mkdir -p data
docker compose up -d
```

Проверить логи:

```bash
docker compose logs -f
```

## Запуск без Docker

Требуется Python 3.12+.

```bash
python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# заполнить .env

python bot.py
```

## Конфигурация

Все параметры задаются в файле `.env`:

| Переменная | Обязательно | По умолчанию | Описание |
|---|---|---|---|
| `BOT_TOKEN` | да | — | Токен бота от @BotFather |
| `CHAT_ID` | да | — | ID чата для уведомлений |
| `CHECK_INTERVAL` | нет | `3600` | Интервал проверки в секундах |
| `GITHUB_REPO` | нет | `MHSanaei/3x-ui` | Репозиторий по умолчанию (добавляется при первом запуске) |
| `DATA_DIR` | нет | `.` | Папка для хранения `repos.json` и `versions.json` |

## Команды бота

| Команда | Описание |
|---|---|
| `/start` | Статус бота: количество репозиториев, интервал проверки |
| `/list` | Список отслеживаемых репозиториев с текущими версиями |
| `/add owner/repo` | Добавить репозиторий (проверяет существование через GitHub API) |
| `/remove owner/repo` | Удалить репозиторий из отслеживания |
| `/check` | Немедленно проверить все репозитории и показать сводку |

## Как это работает

1. При старте бот загружает список репозиториев из `data/repos.json`.
2. Каждые `CHECK_INTERVAL` секунд фоновая задача запрашивает `GET /repos/{owner}/{repo}/releases/latest` для каждого репозитория.
3. Если тег версии изменился — отправляет сообщение в `CHAT_ID` с описанием релиза.
4. Текущие версии хранятся в `data/versions.json` и сохраняются между перезапусками.
5. При первом добавлении репозитория версия только запоминается — уведомление не шлётся.

## Структура проекта

```
.
├── bot.py               # основной код бота
├── requirements.txt     # зависимости Python
├── Dockerfile
├── docker-compose.yml
├── .env.example         # шаблон конфига
└── data/                # создаётся автоматически
    ├── repos.json       # список отслеживаемых репозиториев
    └── versions.json    # последние известные версии
```

## Стек

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) v22 — Telegram Bot API
- [httpx](https://github.com/encode/httpx) — HTTP-клиент для GitHub API
- [python-dotenv](https://github.com/theskumar/python-dotenv) — загрузка `.env`
