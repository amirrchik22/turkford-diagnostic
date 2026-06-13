"""Иерархия исключений + единый exception-middleware + structlog. Никаких голых except."""
from __future__ import annotations

import logging
import sys

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


# --------------------------------------------------------------------------- #
#  Иерархия доменных исключений
# --------------------------------------------------------------------------- #
class DiagnosticError(Exception):
    """Базовое исключение сервиса диагностики."""

    status_code: int = 500
    code: str = "internal_error"
    message: str = "Внутренняя ошибка сервиса"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        if message:
            self.message = message


class BankError(DiagnosticError):
    status_code = 500
    code = "bank_error"
    message = "Ошибка банка вопросов"


class QuestionNotFound(DiagnosticError):
    status_code = 404
    code = "question_not_found"
    message = "Вопрос не найден в банке"


class ConsentRequired(DiagnosticError):
    status_code = 400
    code = "consent_required"
    message = "Требуется согласие на обработку персональных данных"


class EvaluationError(DiagnosticError):
    status_code = 502
    code = "evaluation_error"
    message = "Ошибка оценки ответов моделью"


class TranscriptionError(DiagnosticError):
    status_code = 502
    code = "transcription_error"
    message = "Ошибка расшифровки аудио"


# --------------------------------------------------------------------------- #
#  Логирование (structlog)
# --------------------------------------------------------------------------- #
def configure_logging() -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


log = structlog.get_logger("turkford")


# --------------------------------------------------------------------------- #
#  Middleware / handlers
# --------------------------------------------------------------------------- #
def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DiagnosticError)
    async def _handle_domain(request: Request, exc: DiagnosticError) -> JSONResponse:
        log.warning("domain_error", code=exc.code, path=request.url.path, detail=exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.error("unexpected_error", path=request.url.path, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "Внутренняя ошибка сервиса"}},
        )
