"""Расшифровка аудио (говорение) с ОПРЕДЕЛЕНИЕМ ЯЗЫКА.

Язык НЕ форсируется: модель сама определяет, на каком языке говорил человек.
Если задание турецкое, а речь не на турецком — фронт попросит ответить по-турецки
(а не молча «переводит» русскую речь в турецкий текст).

Два режима:
- с ключом OpenAI → Whisper API (verbose_json даёт язык);
- без ключа → локальный faster-whisper (large-v3) — бесплатно, без сети.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .config import settings
from .errors import TranscriptionError, log

_LOCAL_MODEL_SIZE = "large-v3"
# Азербайджанский — почти как турецкий, Whisper их часто путает → принимаем как турецкий.
_TURKISH = {"tr", "turkish", "az", "azerbaijani", "azerbaijani"}


@dataclass
class Transcription:
    text: str
    language: str           # код/название языка, как вернула модель

    @property
    def is_turkish(self) -> bool:
        return self.language.lower() in _TURKISH


@lru_cache(maxsize=1)
def _local_model():
    from faster_whisper import WhisperModel

    log.info("loading_local_whisper", size=_LOCAL_MODEL_SIZE)
    return WhisperModel(_LOCAL_MODEL_SIZE, device="cpu", compute_type="int8")


def _transcribe_local(path: Path) -> Transcription:
    # без language= → авто-определение языка
    segments, info = _local_model().transcribe(str(path), beam_size=5, vad_filter=True)
    text = " ".join(s.text.strip() for s in segments).strip()
    return Transcription(text=text, language=info.language or "")


def _transcribe_openai(path: Path) -> Transcription:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    with path.open("rb") as f:
        resp = client.audio.transcriptions.create(
            model=settings.whisper_model, file=f, response_format="verbose_json"
        )
    return Transcription(text=(resp.text or "").strip(), language=getattr(resp, "language", "") or "")


def transcribe(data: bytes, suffix: str = ".webm") -> Transcription:
    """Расшифровывает аудио-байты, возвращает текст + определённый язык."""
    if not data:
        raise TranscriptionError("Пустой аудиофайл")
    tmp = Path(tempfile.mkstemp(suffix=suffix)[1])
    try:
        tmp.write_bytes(data)
        try:
            res = _transcribe_openai(tmp) if settings.has_openai else _transcribe_local(tmp)
        except TranscriptionError:
            raise
        except Exception as exc:
            raise TranscriptionError(f"Ошибка расшифровки: {exc}") from exc
        log.info("audio_transcribed", chars=len(res.text), lang=res.language,
                 mode="openai" if settings.has_openai else "local")
        return res
    finally:
        tmp.unlink(missing_ok=True)
