# footy

Football analytics pet project — and a DevOps learning playground.

## Что внутри

Парсинг и анализ футбольных данных (составы, форма, травмы, трансферы, результаты).
Главная цель проекта — пройти полный DevOps-стек: Docker → CI/CD → Kubernetes (k3s) → мониторинг → IaC.

## Требования

- [uv](https://docs.astral.sh/uv/) — менеджер пакетов Python (поставит сам нужный Python 3.12)
- [just](https://github.com/casey/just) — запускалка команд (аналог make)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) — для локального стека из Фазы 1

## Быстрый старт

```bash
just install          # синхронизировать окружение
just hooks-install    # включить pre-commit хуки в .git/hooks
cp .env.example .env  # креденшелы для локального Postgres
just db-up            # поднять Postgres в контейнере (порт 15432)
just migrate          # применить миграции Alembic
just dev              # FastAPI dev-сервер на http://127.0.0.1:8000
just test             # прогнать pytest
just                  # показать все доступные команды
```

После `just dev`:
- `GET /health` → `{"status":"ok"}`
- `GET /competitions` → список соревнований из БД

## CI

GitHub Actions при каждом push'е и PR в `main`/`master`:
поднимает Postgres-сервис, `uv sync --frozen`, `ruff check`, `ruff format --check`,
`alembic upgrade head`, `pytest`. Конфиг — `.github/workflows/ci.yml`.

## Дорожная карта

- [x] **Фаза 0** — основа репо: uv, ruff, pre-commit, Justfile
- [x] **Фаза 1** — локальный Docker-стек (Compose + PostgreSQL)
- [x] **Фаза 2** — парсер + FastAPI + миграции (Alembic) + тесты (pytest)
- [x] **Фаза 3** — CI/CD на GitHub Actions
- [ ] **Фаза 4** — деплой через Ansible на bare-metal Linux
- [ ] **Фаза 5** — k3s + Helm
- [ ] **Фаза 6** — Prometheus / Grafana / Loki / IaC

## Структура

```
footy/
├── src/footy/                 # код приложения
│   ├── api.py                 # FastAPI приложение (роуты)
│   ├── config.py              # pydantic-settings, читает .env
│   ├── db.py                  # SQLAlchemy engine + session + Base
│   ├── models.py              # ORM-модели
│   └── parser.py              # ингест из football-data.org
├── migrations/                # Alembic
│   ├── env.py                 # читает DATABASE_URL и Base.metadata
│   └── versions/              # сами миграции
├── tests/                     # pytest (SQLite in-memory)
├── compose.yaml               # локальный стек (Postgres сейчас, дальше API)
├── alembic.ini                # конфиг миграций
├── .env.example               # шаблон креденшелов
├── pyproject.toml             # зависимости + конфиг ruff
├── Justfile                   # команды разработчика
└── .pre-commit-config.yaml    # хуки качества кода
```
