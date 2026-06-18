"""Адаптивный движок — ЛЕСЕНКА по уровням (А1 → А2 → B1).

Логика (по требованию методиста):
- Начинаем с А1 и идём СНИЗУ ВВЕРХ. Вопросы более высокого уровня НЕ показываем,
  пока текущий не сдан уверенно.
- На каждом уровне набираем закрытые вопросы по навыкам (грамматика/лексика/чтение/
  аудирование). Если уровень сдан на ≥80% — поднимаемся выше. Если нет — останавливаемся
  и «докапываемся» на этом уровне (добираем по навыкам для точного разбора), затем продакшн.
- Продакшн (письмо + говорение) — 1 задание каждое, на уровне остановки.

Сервер stateless: чистые функции над (накопленные ответы, банк). LLM не участвует.
"""
from __future__ import annotations

from .bank import QuestionBank
from .config import Settings
from .scoring import ScoreState, build_score_state
from .schemas import AnswerIn, Level, Question, QuestionOut, QuestionType, Skill, Zone

LEVEL_ORDER: list[Level] = [Level.A1, Level.A2, Level.B1]
CLOSED_SKILLS: list[Skill] = [Skill.grammar, Skill.vocabulary, Skill.reading, Skill.listening]

# Пороги
PASS = 0.80            # сдан уверенно → поднимаемся выше
T_NOT_MASTERED = 0.60  # ниже — уровень не освоен
DECIDE_AT = 5          # минимум закрытых на уровне, чтобы принять решение
# Покрытие навыков на уровне остановки (для радара нужно ≥3 ответов на навык)
COVER = {Skill.grammar: 3, Skill.reading: 3, Skill.listening: 3}


# --------------------------------------------------------------------------- #
#  Выбор вопросов
# --------------------------------------------------------------------------- #
def _choose(cands: list[Question]) -> Question:
    return sorted(cands, key=lambda q: (q.difficulty, q.id))[0]


def _covered(state: ScoreState, bank: QuestionBank, lv: Level) -> bool:
    """На уровне остановки набрано достаточно по ключевым навыкам (или вопросы кончились)."""
    for sk, target in COVER.items():
        if state.level_skill_count(lv, sk) >= target:
            continue
        more = any(
            q.level == lv and q.skill == sk and q.type == QuestionType.closed
            and q.correct is not None and q.id not in state.asked_ids
            for q in bank.questions
        )
        if more:
            return False
    return True


def _pick_closed(state: ScoreState, bank: QuestionBank, lv: Level) -> Question | None:
    """Следующий закрытый вопрос уровня lv — балансируя навыки (грамматика/чтение/аудир.)."""
    avail = [
        q for q in bank.questions
        if q.level == lv and q.type == QuestionType.closed
        and q.correct is not None and q.id not in state.asked_ids
    ]
    if not avail:
        return None
    skills_present = {q.skill for q in avail}

    def deficit(sk: Skill) -> int:
        return COVER.get(sk, 1) - state.level_skill_count(lv, sk)

    best = max(skills_present, key=lambda sk: (deficit(sk), -state.level_skill_count(lv, sk)))
    return _choose([q for q in avail if q.skill == best])


def _pick_production(state: ScoreState, bank: QuestionBank, lv: Level) -> Question | None:
    """1 письмо + 1 говорение на уровне остановки (или ближайшем доступном)."""
    for sk in (Skill.writing, Skill.speaking):
        if state.skill_count(sk) > 0:
            continue
        order = [lv] + [x for x in LEVEL_ORDER if x != lv]
        for level in order:
            cands = [
                q for q in bank.questions
                if q.level == level and q.skill == sk and q.id not in state.asked_ids
            ]
            if cands:
                return _choose(cands)
    return None


def _current_stage(state: ScoreState, bank: QuestionBank) -> tuple[str, Level]:
    """Где мы: ('closed'|'production', уровень). Идём снизу вверх, не пуская выше неосвоенного."""
    for lv in LEVEL_ORDER:
        st = state.level(lv)
        if st.total < DECIDE_AT:
            return ("closed", lv)               # ещё набираем, чтобы решить
        if st.ratio >= PASS and lv != LEVEL_ORDER[-1]:
            continue                            # сдан → следующий уровень
        if not _covered(state, bank, lv):
            return ("closed", lv)               # уровень остановки — докапываем по навыкам
        return ("production", lv)
    return ("production", LEVEL_ORDER[-1])


def next_question(answers: list[AnswerIn], bank: QuestionBank, settings: Settings) -> QuestionOut | None:
    """Главная функция. None → тест завершён."""
    state = build_score_state(answers, bank)
    if len(state.asked_ids) >= settings.max_questions:
        return None
    phase, lv = _current_stage(state, bank)
    if phase == "closed":
        q = _pick_closed(state, bank, lv)
        if q:
            return bank.to_out(q)
        phase = "production"                     # закрытые кончились → продакшн
    q = _pick_production(state, bank, lv)
    return bank.to_out(q) if q else None


# --------------------------------------------------------------------------- #
#  Матрица присвоения финального уровня (снизу вверх)
# --------------------------------------------------------------------------- #
def level_from_ratios(a1: float, a2: float, b1: float, a1_total: int) -> tuple[Level, Zone]:
    """Чистая матрица уровней (легко тестируется отдельно от банка)."""
    if a1_total == 0 or a1 < T_NOT_MASTERED:
        return Level.A0, Zone.in_progress
    if a1 < PASS:
        return Level.A1, Zone.in_progress
    if a2 < T_NOT_MASTERED:
        return Level.A1, Zone.confident
    if a2 < PASS:
        return Level.A2, Zone.in_progress
    if b1 < T_NOT_MASTERED:
        return Level.A2, Zone.confident
    if b1 < PASS:
        return Level.B1, Zone.in_progress
    return Level.B1, Zone.confident


def assign_level(answers: list[AnswerIn], bank: QuestionBank) -> tuple[Level, Zone]:
    state = build_score_state(answers, bank)
    return level_from_ratios(
        state.level(Level.A1).ratio,
        state.level(Level.A2).ratio,
        state.level(Level.B1).ratio,
        state.level(Level.A1).total,
    )
