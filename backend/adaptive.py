"""Адаптивный движок: стартовый зонд → 3 порога → балансир навыков → матрица уровней.

Сервер stateless: вся логика — чистые функции над (накопленные ответы, банк).
LLM здесь НЕ участвует — только правила. Модель вызывается один раз в конце.
"""
from __future__ import annotations

from .bank import QuestionBank
from .config import Settings
from .scoring import ScoreState, build_score_state
from .schemas import AnswerIn, Level, Question, QuestionOut, QuestionType, Skill, Zone

# Порядок уровней снизу вверх
LEVEL_ORDER: list[Level] = [Level.A1, Level.A2, Level.B1]
# 5 навыков для радара и балансировки
GRADED_SKILLS: list[Skill] = [Skill.grammar, Skill.reading, Skill.listening, Skill.writing, Skill.speaking]
PRODUCTION_SKILLS = {Skill.writing, Skill.speaking}

# Пороги (доля верных закрытых)
T_NOT_MASTERED = 0.60   # <60% — уровень не освоен
T_MASTERED = 0.80       # ≥80% — освоен
CORE_CLOSED = 5         # сколько закрытых нужно на фокус-уровне для надёжного решения


# --------------------------------------------------------------------------- #
#  Фаза 1 — стартовый зонд (детерминированный)
# --------------------------------------------------------------------------- #
def probe_ids(bank: QuestionBank, size: int) -> list[str]:
    """size вопросов: поровну с каждого уровня, разные навыки, закрытого типа."""
    per_level = max(1, size // len(LEVEL_ORDER))
    ids: list[str] = []
    for lv in LEVEL_ORDER:
        closed = sorted(
            (q for q in bank.by_level(lv) if q.type == QuestionType.closed),
            key=lambda q: (q.difficulty, q.id),
        )
        picked: list[Question] = []
        seen: set[Skill] = set()
        for q in closed:                      # сперва разные навыки
            if q.skill not in seen:
                picked.append(q)
                seen.add(q.skill)
            if len(picked) >= per_level:
                break
        for q in closed:                      # добор, если навыков не хватило
            if len(picked) >= per_level:
                break
            if q not in picked:
                picked.append(q)
        ids.extend(q.id for q in picked)
    return ids


# --------------------------------------------------------------------------- #
#  Фаза 2 — выбор следующего вопроса
# --------------------------------------------------------------------------- #
def _skill_satisfied(state: ScoreState, sk: Skill, settings: Settings) -> bool:
    if sk in PRODUCTION_SKILLS:
        return state.skill_count(sk) >= 1            # 1 продакшн-задание = покрыт навык
    return state.skill_count(sk) >= settings.min_per_skill


def _focus_level(state: ScoreState, settings: Settings) -> Level:
    """Нижний уровень, который ещё не освоен уверенно (или верхний, если все освоены)."""
    for lv in LEVEL_ORDER:
        st = state.level(lv)
        if st.total < CORE_CLOSED:
            return lv                                # сначала набрать данные тут
        if st.ratio < T_MASTERED:
            return lv                                # не освоен уверенно — фокус здесь
    return LEVEL_ORDER[-1]


def _choose(cands: list[Question]) -> Question:
    """Детерминированный выбор: по возрастанию сложности, затем по id."""
    return sorted(cands, key=lambda q: (q.difficulty, q.id))[0]


def _pick_next(state: ScoreState, bank: QuestionBank, focus: Level, settings: Settings) -> Question | None:
    avail = [q for q in bank.questions if q.id not in state.asked_ids]
    if not avail:
        return None

    # 1) Закрыть непокрытые навыки (балансир), начиная с наименее покрытого
    unsatisfied = sorted(
        (sk for sk in GRADED_SKILLS if not _skill_satisfied(state, sk, settings)),
        key=lambda sk: state.skill_count(sk),
    )
    for sk in unsatisfied:
        order = [focus] + [lv for lv in LEVEL_ORDER if lv != focus]
        for lv in order:
            cands = [q for q in avail if q.skill == sk and q.level == lv]
            if cands:
                return _choose(cands)

    # 2) Добрать закрытых на фокус-уровне для надёжного порога
    st = state.level(focus)
    if st.total < CORE_CLOSED:
        cands = [q for q in avail if q.level == focus and q.type == QuestionType.closed]
        if cands:
            return _choose(cands)

    return None  # всё нужное собрано → тест завершён


def next_question(answers: list[AnswerIn], bank: QuestionBank, settings: Settings) -> QuestionOut | None:
    """Главная функция адаптивности. None → тест завершён."""
    state = build_score_state(answers, bank)
    answered = len(state.asked_ids)

    # Фаза 1: стартовый зонд
    probe = probe_ids(bank, settings.probe_size)
    if answered < len(probe):
        for qid in probe:
            if qid not in state.asked_ids and bank.exists(qid):
                return bank.to_out(bank.get(qid))

    # Стоп: лимит вопросов
    if answered >= settings.max_questions:
        return None
    # Стоп: завалила А1 (<60% при достаточной выборке)
    a1 = state.level(Level.A1)
    if a1.total >= 3 and a1.ratio < T_NOT_MASTERED:
        return None

    focus = _focus_level(state, settings)
    nxt = _pick_next(state, bank, focus, settings)
    return bank.to_out(nxt) if nxt else None


# --------------------------------------------------------------------------- #
#  Матрица присвоения финального уровня (снизу вверх)
# --------------------------------------------------------------------------- #
def level_from_ratios(a1: float, a2: float, b1: float, a1_total: int) -> tuple[Level, Zone]:
    """Чистая матрица уровней (легко тестируется отдельно от банка)."""
    if a1_total == 0 or a1 < T_NOT_MASTERED:
        return Level.A0, Zone.in_progress
    if a1 < T_MASTERED:
        return Level.A1, Zone.in_progress
    # A1 освоен уверенно
    if a2 < T_NOT_MASTERED:
        return Level.A1, Zone.confident
    if a2 < T_MASTERED:
        return Level.A2, Zone.in_progress
    # A2 освоен уверенно
    if b1 < T_NOT_MASTERED:
        return Level.A2, Zone.confident
    if b1 < T_MASTERED:
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
