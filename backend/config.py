"""Конфигурация сервиса. Все секреты — только из окружения (.env), не в коде."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PROMPTS_DIR = BASE_DIR / "prompts"


class Settings(BaseSettings):
    """Настройки приложения, читаются из переменных окружения / .env."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- OpenAI (для всего: оценка уровня + Whisper) ---
    openai_api_key: str = Field(default="", description="Ключ OpenAI API")
    eval_model: str = Field(default="gpt-4o", description="Модель для оценки уровня и отчёта")
    whisper_model: str = Field(default="whisper-1", description="Модель расшифровки аудио")

    # --- Поведение теста ---
    probe_size: int = Field(default=6, description="Вопросов в стартовом зонде (Фаза 1)")
    max_questions: int = Field(default=22, description="Жёсткий лимит вопросов")
    min_per_skill: int = Field(default=4, description="Минимум баллов на каждый из 5 навыков")

    # --- Прочее ---
    cors_origins: str = Field(default="*", description="Разрешённые origins через запятую")
    results_log_path: Path = Field(default=BASE_DIR.parent / "results.log.jsonl")

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key)


settings = Settings()
