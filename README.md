# footy

Football analytics pet project — and a DevOps learning playground.

## Что внутри

Парсинг и анализ футбольных данных (составы, форма, травмы, трансферы, результаты).
Главная цель проекта — пройти полный DevOps-стек: Docker → CI/CD → Kubernetes (k3s) → мониторинг → IaC.

## Требования

- [uv](https://docs.astral.sh/uv/) — менеджер пакетов Python (поставит сам нужный Python 3.12)
- [just](https://github.com/casey/just) — запускалка команд (аналог make)
- Docker — на следующей фазе

## Быстрый старт

```bash
just install          # синхронизировать окружение
just hooks-install    # включить pre-commit хуки в .git/hooks
just                  # показать все доступные команды
```

## Дорожная карта

- [x] **Фаза 0** — основа репо: uv, ruff, pre-commit, Justfile
- [ ] **Фаза 1** — локальный Docker-стек (Compose + PostgreSQL)
- [ ] **Фаза 2** — парсер + FastAPI + миграции (Alembic) + тесты (pytest)
- [ ] **Фаза 3** — CI/CD на GitHub Actions
- [ ] **Фаза 4** — деплой через Ansible на bare-metal Linux
- [ ] **Фаза 5** — k3s + Helm
- [ ] **Фаза 6** — Prometheus / Grafana / Loki / IaC

## Структура

```
footy/
├── src/footy/                 # код приложения
├── pyproject.toml             # зависимости + конфиг ruff
├── Justfile                   # команды разработчика
└── .pre-commit-config.yaml    # хуки качества кода
```
