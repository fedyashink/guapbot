# Дедлайн-бот

Телеграм-бот для студентов: запоминает дедлайны по лабораторным, курсовым и контрольным
и напоминает о них **до** сдачи, а не после.

## Возможности

- Добавление работы одной фразой: `/add Лаба 5 по БД, дедлайн в четверг в 18:00`
- Понимает русские даты: `завтра в 18:00`, `послезавтра`, `через 3 дня`, `через две недели`,
  `в пятницу к 15:00`, `25.10 в 14:00`, `25 октября`, `2026-10-25 09:00`, `в 3 часа`
- Свои интервалы напоминаний: `/remind 48,24,6,1` (0 — ровно в момент дедлайна)
- Утренний дайджест со сводкой: что просрочено, что сдаётся сегодня
- Статистика и оценка загрузки по дням с предупреждением о перегрузе
- Отметка «сделал», откат, перенос дедлайна на день/неделю прямо в сообщении
- Часовой пояс студента: `/tz Asia/Almaty` — дедлайны считаются в его времени

## Команды

| Команда | Что делает |
|---|---|
| `/add` | добавить работу |
| `/list` | список активных дедлайнов |
| `/done` | отметить выполненной (`/done 1` или `/done БД`) |
| `/undo` | вернуть последнюю работу в активные |
| `/next` | три ближайших дедлайна |
| `/stats` | сводка и загрузка по дням |
| `/remind` | интервалы напоминаний в часах |
| `/digest` | вкл/выкл утреннюю сводку и её час |
| `/tz` | часовой пояс |
| `/help` | справка |

## Запуск

```bash
cd deadline-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # вставить токен от @BotFather
python -m bot
```

`DATABASE_URL` можно не задавать — тогда бот работает на SQLite в `data/bot.db`.

## Деплой: Railway + Neon Postgres

Файловая система на Railway **эфемерная** — SQLite с дедлайнами стирается при
каждом редеплое. Поэтому в проде нужна внешняя БД.

**1. Создай базу в Neon** (бесплатно, без карты, 0.5 GB):
https://console.neon.tech → Create a project → **Connection string** → скопируй строку
вида `postgresql://user:pass@ep-xxx.aws.neon.tech/neondb?sslmode=require`

**2. Задеплой на Railway**:
https://railway.com/new → **Deploy from GitHub repo** → выбери свой репозиторий.
Railway сам соберёт `Dockerfile` из корня.

**3. Задай переменные** (Variables → Raw editor):

| Переменная | Значение |
|---|---|
| `BOT_TOKEN` | токен от @BotFather |
| `DATABASE_URL` | строка подключения Neon из шага 1 |
| `DEFAULT_TZ` | `Europe/Moscow` |

Таблицы создаются автоматически при первом старте.

**4. Проверь логи** — должна быть строка:
```
БД: postgresql+asyncpg://ep-xxx.aws.neon.tech/neondb
Бот запущен
```

### Нюансы, которые уже обработаны в коде

- `postgresql://` автоматически превращается в `postgresql+asyncpg://` — синхронные
  драйверы (`psycopg2`, `psycopg`) не нужны и не ставятся
- `?sslmode=require` из Neon-строки убирается и превращается в `ssl=True` для asyncpg
  (параметр `sslmode` в `asyncpg.connect()` не существует и вызвал бы `TypeError`)
- `pooler=transaction`, `pgbouncer` и `channel_binding` тоже вырезаются — asyncpg их не понимает
- на Neon **pooled** endpoint (хост с `-pooler`) автоматически ставится
  `statement_cache_size=0`, иначе PgBouncer ругается на `prepared statement already exists`
- `build_engine()` сам приводит схему к `postgresql+asyncpg`, даже если в переменной
  окружения она записана как `postgresql://` или `postgres://`
- `pool_pre_ping=True` переживает разрывы соединений
- `init_db()` делает 5 попыток с backoff: Neon после паузы засыпает (scale-to-zero)
  и первое соединение может не пройти
- пароль из `DATABASE_URL` не попадает в логи (`describe_backend`)

## Настройки (.env)

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `BOT_TOKEN` | — | токен от @BotFather, обязателен |
| `DATABASE_URL` | — | Postgres; пусто = SQLite |
| `DEFAULT_TZ` | `Europe/Moscow` | пояс для новых пользователей |
| `DEFAULT_REMINDER_OFFSETS` | `24,6,1` | напоминания за N часов |
| `DEFAULT_DEADLINE_TIME` | `23:59` | время, если не указано |
| `DIGEST_HOUR` | `9` | час утренней сводки |
| `DB_POOL_SIZE` | `5` | размер пула соединений |
| `DB_PATH` | `data/bot.db` | путь к файлу SQLite |

## Тесты

```bash
pytest -q
```

Покрыты парсер дат, сервисный слой, статистика, хендлеры (через фейковую Telegram-сессию),
планировщик напоминаний и логика подключения к БД (в т.ч. несовместимые параметры Neon).

## Архитектура

```
bot/
  main.py          точка входа, диспетчер, middlewares
  config.py        конфиг из .env
  db.py            движок: SQLite или Postgres по DATABASE_URL
  models.py        User, Assignment (SQLAlchemy 2.0)
  scheduler.py     APScheduler: напоминания + дайджест
  keyboards.py     инлайн-клавиатуры
  texts.py         тексты ответов
  middlewares.py   сессия БД на апдейт, автосоздание юзера
  handlers/        start, assignments, stats, settings
  services/        бизнес-логика: users, assignments, stats
  utils/           парсер дат, форматирование, работа со временем
```

Одна кодовая база работает и на SQLite (локально), и на Postgres (прод) — разница
только в `DATABASE_URL`. Время в БД хранится в UTC, пользователю показывается в его
часовом поясе. Планировщик ходит по базе раз в 30 секунд, поэтому перезапуски бота
не приводят к потере напоминаний, а отметки об отправке хранятся в `reminded_offsets`.
# guapbot
