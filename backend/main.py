"""FastAPI-приложение: запуск теста и адаптивная выдача вопросов.

Этап 2: /start, /next (движок без LLM). /finish (оценка GPT) добавляется на Этапе 3.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .adaptive import next_step
from .bank import get_bank
from .config import settings
from .errors import ConsentRequired, configure_logging, install_error_handlers, log
from .evaluator import evaluate
from .schemas import (
    FinishRequest,
    NextRequest,
    NextResponse,
    QuestionBlock,
    Report,
    Skill,
    StartRequest,
)
from .transcribe import transcribe

_PASSAGE_SKILLS = {Skill.reading, Skill.listening}


def _build_next(answers: list, bank, asked: int) -> NextResponse:
    """Собирает ответ: одиночный вопрос или блок (чтение/аудирование на одном экране)."""
    step = next_step(answers, bank, settings)
    progress = min(1.0, asked / settings.max_questions)
    if not step:
        return NextResponse(done=True, asked=asked, progress=1.0)
    first = step[0]
    if first.skill in _PASSAGE_SKILLS:
        block = QuestionBlock(
            skill=first.skill,
            level=first.level,
            passage_text=bank.passage_text(first.passage_id) if first.skill == Skill.reading else None,
            audio_level=first.level.value.lower() if first.skill == Skill.listening else None,
            questions=[bank.to_out(q) for q in step],
        )
        return NextResponse(block=block, asked=asked, progress=progress)
    return NextResponse(question=bank.to_out(first), asked=asked, progress=progress)

configure_logging()

app = FastAPI(title="TÜrkford AI-диагностика", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)
install_error_handlers(app)


@app.middleware("http")
async def no_cache_static(request, call_next):
    """Страница и статика не кэшируются браузером — после деплоя клиент сразу видит свежую версию."""
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent.parent / "frontend"), name="static")


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
PRIVACY_FILE = Path(__file__).resolve().parent / "data" / "privacy.md"


@app.get("/health")
def health() -> dict[str, object]:
    bank = get_bank()
    return {"status": "ok", "questions": len(bank.questions), "has_openai": settings.has_openai}


@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/privacy", response_class=HTMLResponse)
def privacy() -> HTMLResponse:
    text = PRIVACY_FILE.read_text(encoding="utf-8") if PRIVACY_FILE.exists() else "Политика обработки ПД."
    body = text.replace("&", "&amp;").replace("<", "&lt;")
    return HTMLResponse(
        f"<!doctype html><meta charset=utf-8><title>Политика обработки ПД</title>"
        f"<body style='max-width:760px;margin:40px auto;padding:0 20px;font-family:system-ui;"
        f"line-height:1.6;white-space:pre-wrap'>{body}</body>"
    )


@app.post("/api/start", response_model=NextResponse)
def start(req: StartRequest) -> NextResponse:
    """Старт теста: проверяем согласие ПД и выдаём первый шаг (А1, лесенка снизу вверх)."""
    if not req.contact.consent_pd:
        raise ConsentRequired()
    bank = get_bank()
    log.info("test_started", email=req.contact.email, segment=req.segment)
    return _build_next([], bank, asked=0)


@app.post("/api/next", response_model=NextResponse)
def next_(req: NextRequest) -> NextResponse:
    """Следующий шаг (вопрос или блок) по накопленным ответам, либо сигнал завершения."""
    bank = get_bank()
    asked = len({a.id for a in req.answers if bank.exists(a.id)})
    return _build_next(req.answers, bank, asked=asked)


@app.post("/api/audio")
async def audio(file: UploadFile = File(...), question_id: str = Form("")) -> dict[str, object]:
    """Принимает запись говорения, расшифровывает и определяет язык.

    Задания на говорение — турецкие. Если речь не на турецком, фронт попросит
    переговорить по-турецки (мы не «переводим» чужой язык в турецкий молча).
    """
    data = await file.read()
    suffix = "." + (file.filename or "rec.webm").rsplit(".", 1)[-1]
    res = transcribe(data, suffix=suffix)
    return {
        "question_id": question_id,
        "transcript": res.text,
        "language": res.language,
        "is_turkish": res.is_turkish,
    }


@app.post("/api/finish", response_model=Report)
def finish(req: FinishRequest) -> Report:
    """Финал: по всем ответам генерируем отчёт (GPT при наличии ключа, иначе мок)."""
    if not req.contact.consent_pd:
        raise ConsentRequired()
    bank = get_bank()
    report = evaluate(req, req.answers, bank)
    log.info("test_finished", email=req.contact.email, level=report.level.value,
             zone=report.level_zone.value, mock=not settings.has_openai)
    return report
