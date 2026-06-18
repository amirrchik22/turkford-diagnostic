"""Подсчёт результатов закрытых вопросов по уровням и навыкам.

Только closed-вопросы участвуют в % верных, который управляет порогами адаптивности.
open_meaning / production оцениваются моделью в конце, не во время прохождения.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .bank import QuestionBank
from .schemas import AnswerIn, Level, QuestionType, Skill


def is_correct_closed(given: str | None, correct: str | None) -> bool:
    """Строгое сравнение для закрытых вопросов (без учёта регистра/пробелов по краям)."""
    if given is None or correct is None:
        return False
    return given.strip().casefold() == correct.strip().casefold()


@dataclass
class LevelStat:
    correct: int = 0
    total: int = 0  # только closed-вопросы данного уровня

    @property
    def ratio(self) -> float:
        return self.correct / self.total if self.total else 0.0


@dataclass
class ScoreState:
    """Агрегированное состояние по ответам: статистика по уровням и счётчики навыков."""
    levels: dict[Level, LevelStat] = field(default_factory=dict)
    skill_answered: dict[Skill, int] = field(default_factory=dict)
    level_skill: dict[tuple[Level, Skill], int] = field(default_factory=dict)
    asked_ids: set[str] = field(default_factory=set)

    def level(self, lv: Level) -> LevelStat:
        return self.levels.setdefault(lv, LevelStat())

    def skill_count(self, sk: Skill) -> int:
        return self.skill_answered.get(sk, 0)

    def level_skill_count(self, lv: Level, sk: Skill) -> int:
        return self.level_skill.get((lv, sk), 0)


def build_score_state(answers: list[AnswerIn], bank: QuestionBank) -> ScoreState:
    """Пересчитывает состояние из накопленного списка ответов (сервер stateless)."""
    state = ScoreState()
    for ans in answers:
        if not bank.exists(ans.id):
            continue
        q = bank.get(ans.id)
        state.asked_ids.add(q.id)
        state.skill_answered[q.skill] = state.skill_answered.get(q.skill, 0) + 1
        state.level_skill[(q.level, q.skill)] = state.level_skill.get((q.level, q.skill), 0) + 1
        # Закрытые вопросы участвуют в % верных только если у них есть ключ.
        # Вопросы без правильного ответа (ждут Юлю) не оцениваются, но учитываются в покрытии навыков.
        if q.type == QuestionType.closed and q.correct is not None:
            st = state.level(q.level)
            st.total += 1
            if is_correct_closed(ans.given, q.correct):
                st.correct += 1
    return state
