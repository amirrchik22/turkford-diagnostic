"""Загрузка банков вопросов и безопасная выдача клиенту (без правильных ответов)."""
from __future__ import annotations

import json
from functools import lru_cache

from .config import DATA_DIR
from .errors import BankError, QuestionNotFound
from .schemas import Level, Passage, Question, QuestionOut

_BANK_FILES = {
    Level.A1: "questions_a1.json",
    Level.A2: "questions_a2.json",
    Level.B1: "questions_b1.json",
}


class QuestionBank:
    """Единый банк по всем уровням: индекс вопросов + текстов для чтения."""

    def __init__(self, questions: list[Question], passages: dict[str, Passage]) -> None:
        self.questions = questions
        self._by_id = {q.id: q for q in questions}
        self._passages = passages

    # --- доступ ---
    def get(self, qid: str) -> Question:
        try:
            return self._by_id[qid]
        except KeyError as exc:
            raise QuestionNotFound(f"Вопрос {qid} не найден") from exc

    def exists(self, qid: str) -> bool:
        return qid in self._by_id

    def passage_text(self, passage_id: str | None) -> str | None:
        if not passage_id:
            return None
        p = self._passages.get(passage_id)
        return p.text if p else None

    def to_out(self, q: Question) -> QuestionOut:
        """Безопасное представление: без correct / expected_answer / note."""
        return QuestionOut(
            id=q.id,
            level=q.level,
            skill=q.skill,
            difficulty=q.difficulty,
            type=q.type,
            question=q.question,
            options=q.options,
            passage_text=self.passage_text(q.passage_id),
        )

    def by_level(self, level: Level) -> list[Question]:
        return [q for q in self.questions if q.level == level]


@lru_cache(maxsize=1)
def get_bank() -> QuestionBank:
    """Загружает и кэширует банк из JSON-файлов data/."""
    questions: list[Question] = []
    passages: dict[str, Passage] = {}
    for level, fname in _BANK_FILES.items():
        path = DATA_DIR / fname
        if not path.exists():
            raise BankError(f"Файл банка не найден: {fname}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise BankError(f"Некорректный JSON в {fname}: {exc}") from exc
        for p in raw.get("passages", []):
            passage = Passage.model_validate(p)
            passages[passage.id] = passage
        for q in raw.get("questions", []):
            questions.append(Question.model_validate(q))
    if not questions:
        raise BankError("Банк вопросов пуст")
    return QuestionBank(questions, passages)
