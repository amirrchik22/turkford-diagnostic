# TÜrkford — AI-диагностика турецкого

Адаптивный веб-тест уровня турецкого: фронтенд (все экраны) + FastAPI-сервер
(адаптивный движок, оценка через GPT, расшифровка аудио через Whisper).

## Локальный запуск

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt        # сервер + локальный Whisper + тесты
cp .env.example .env                        # впиши OPENAI_API_KEY (необязательно)
uvicorn backend.main:app --reload --port 8077
```

Открой **http://127.0.0.1:8077/**

- Без ключа OpenAI — **мок-режим**: отчёт-заглушка, расшифровка локально (faster-whisper, бесплатно).
- С ключом — отчёт пишет gpt-4o, расшифровку делает OpenAI Whisper.

## Тесты
```bash
pytest tests/ -q     # 30 тестов, всегда в мок-режиме (быстро, без обращений к OpenAI)
```

## Деплой на Render (публичная ссылка для клиента)
1. Repo → render.com → **New → Blueprint** → выбрать этот репозиторий (Render прочитает `render.yaml`).
2. В дашборде задать секрет **OPENAI_API_KEY** (он НЕ хранится в репозитории).
3. Deploy → получишь ссылку вида `https://turkford-diagnostic.onrender.com` — её и отправляешь клиенту.

> На деплое ставится только `requirements.txt` (лёгкий, без локальных моделей): оценка и
> расшифровка идут через OpenAI API.

## Структура
- `backend/` — сервер (adaptive, scoring, evaluator, transcribe, bank, errors, schemas)
- `backend/data/` — банки вопросов (229), `privacy.md`
- `backend/prompts/system_gpt.md` — системный промпт оценки
- `frontend/` — index.html + styles.css + app.js + logo.png + audio/
- `tests/` — pytest · `render.yaml` — конфиг деплоя

## Эндпоинты
`/` фронт · `/health` · `/privacy` · `/api/start` · `/api/next` · `/api/audio` · `/api/finish`
