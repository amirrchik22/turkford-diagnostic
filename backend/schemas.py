"""Pydantic-схемы на всех границах API. Строгая типизация, никаких dict[str, Any]."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, EmailStr, Field, field_validator


# --------------------------------------------------------------------------- #
#  Перечисления
# --------------------------------------------------------------------------- #
class Level(str, Enum):
    A0 = "A0"
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"


class Skill(str, Enum):
    grammar = "grammar"
    vocabulary = "vocabulary"
    reading = "reading"
    listening = "listening"
    writing = "writing"
    speaking = "speaking"


class QuestionType(str, Enum):
    closed = "closed"            # выбор варианта — строгое сравнение
    open_meaning = "open_meaning"  # открытый по смыслу (чтение/аудирование)
    production = "production"    # письмо/говорение — оценка по рубрике


class Zone(str, Enum):
    in_progress = "in_progress"  # 60–80% — «в процессе освоения»
    confident = "confident"      # ≥80% — «уверенно»


# --------------------------------------------------------------------------- #
#  Банк вопросов (внутреннее представление — с правильными ответами)
# --------------------------------------------------------------------------- #
class Passage(BaseModel):
    id: str
    skill: Skill
    text: str


class Question(BaseModel):
    """Полный вопрос из банка — с правильным ответом (НЕ отдаётся клиенту целиком)."""
    id: str
    level: Level
    skill: Skill
    difficulty: int = Field(ge=1, le=3)
    type: QuestionType
    question: str
    options: list[str] = Field(default_factory=list)
    correct: str | None = None
    expected_answer: str | None = None
    passage_id: str | None = None
    confidence: str | None = None
    note: str | None = None

    @field_validator("options", mode="before")
    @classmethod
    def _none_to_list(cls, v: object) -> object:
        return v or []


class QuestionOut(BaseModel):
    """Безопасное представление вопроса для клиента — без правильного ответа."""
    id: str
    level: Level
    skill: Skill
    difficulty: int
    type: QuestionType
    question: str
    options: list[str] = Field(default_factory=list)
    passage_text: str | None = None


# --------------------------------------------------------------------------- #
#  Входные данные от клиента
# --------------------------------------------------------------------------- #
class Contact(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    phone: str = Field(min_length=3, max_length=40)
    telegram: str | None = Field(default=None, max_length=80)
    self_assessment: str | None = None
    consent_pd: bool = Field(description="Согласие на обработку ПД (152-ФЗ)")


class AnswerIn(BaseModel):
    """Ответ ученицы на один вопрос."""
    id: str
    given: str | None = None          # выбранный вариант / открытый ответ
    user_text: str | None = None       # для письма
    audio_url: str | None = None       # для говорения (после загрузки)
    transcript: str | None = None      # расшифровка Whisper (заполняет сервер)


class StartRequest(BaseModel):
    contact: Contact
    segment: str | None = None         # экран 2 (семья/путешествия/работа/...)
    goal: str | None = None            # экран 2.5 (цель)
    ref: str | None = None             # реферальный код из URL


class NextRequest(BaseModel):
    """Клиент присылает накопленные ответы; сервер детерминированно выдаёт следующий вопрос."""
    answers: list[AnswerIn] = Field(default_factory=list)


class QuestionBlock(BaseModel):
    """Несколько вопросов по одному тексту/аудио — показываются на одном экране."""
    skill: Skill
    level: Level
    passage_text: str | None = None   # текст для чтения
    audio_level: str | None = None    # уровень для подгрузки аудио (a1/a2/b1)
    questions: list[QuestionOut] = Field(default_factory=list)


class NextResponse(BaseModel):
    question: QuestionOut | None = None
    block: QuestionBlock | None = None
    done: bool = False
    asked: int = 0
    progress: float = Field(default=0.0, ge=0.0, le=1.0)


class FinishRequest(StartRequest):
    """Завершение теста: контакт/сегмент/цель + накопленные ответы → отчёт."""
    answers: list[AnswerIn] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
#  Отчёт (выход GPT) — детально валидируется на Этапе 3
# --------------------------------------------------------------------------- #
class SkillNote(BaseModel):
    status: str
    note: str


class TargetSolution(BaseModel):
    goal_echo: str
    paragraph: str


class RecommendedCase(BaseModel):
    id: str
    name: str
    story_before: str
    story_after: str
    video_url: str | None = None


class StudyPlan(BaseModel):
    target_level: str
    estimated: str
    topics: list[str]
    schedule: str
    extra: list[str] = Field(default_factory=list)


class RecommendedCourse(BaseModel):
    level: str
    name: str
    url: str
    why: str


class Report(BaseModel):
    level: Level
    level_label: str
    level_zone: Zone
    level_short: str
    skills: dict[str, SkillNote]
    skills_chart: dict[str, int | None]
    feedback: str
    target_solution: TargetSolution
    recommended_case: RecommendedCase
    plan: StudyPlan
    recommended_course: RecommendedCourse
    certificate_line: str
    manager_note: str
    promo_code: str | None = None
    referral_code: str | None = None
