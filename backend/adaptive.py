"""Адаптивный движок — ЛЕСЕНКА по уровням (А1 → А2 → B1) с группировкой.

- Идём снизу вверх. Выше не показываем, пока текущий не сдан на ≥80%.
- Грамматику/лексику даём по одному вопросу (они определяют уровень).
- Чтение и аудирование — БЛОКАМИ: все вопросы по одному тексту/аудио на одном экране
  (чтобы не прыгать туда-сюда и не переслушивать).
- На уровне остановки — полное покрытие навыков (для радара) + продакшн (письмо/говорение).

Сервер stateless: чистые функции над (ответы, банк).
"""
from __future__ import annotations

from .bank import QuestionBank
from .config import Settings
from .scoring import ScoreState, build_score_state
from .schemas import AnswerIn, Level, Question, QuestionType, Skill, Zone

LEVEL_ORDER: list[Level] = [Level.A1, Level.A2, Level.B1]
PASS = 0.80
T_NOT_MASTERED = 0.60
GRAM_DECIDE = 4    # грамматики/лексики, чтобы решить — пройден ли уровень
GRAM_FULL = 6      # грамматики на уровне остановки (точный разбор)
BLOCK_CAP = 4      # макс. вопросов в блоке чтения/аудирования (один экран)
SINGLE_SKILLS = [Skill.grammar, Skill.vocabulary]


def _choose(cands: list[Question]) -> Question:
    return sorted(cands, key=lambda q: (q.difficulty, q.id))[0]


def _unasked(bank: QuestionBank, state: ScoreState, lv: Level, sk: Skill) -> list[Question]:
    return [
        q for q in bank.questions
        if q.level == lv and q.skill == sk and q.id not in state.asked_ids
    ]


def _pick_single(state: ScoreState, bank: QuestionBank, lv: Level) -> Question | None:
    """Грамматика/лексика — по одному вопросу, с лёгким балансом в пользу грамматики."""
    targets = {Skill.grammar: GRAM_FULL, Skill.vocabulary: 1}
    best: Question | None = None
    best_key = (-(10**9),)
    for sk in SINGLE_SKILLS:
        cands = _unasked(bank, state, lv, sk)
        if not cands:
            continue
        deficit = targets[sk] - state.level_skill_count(lv, sk)
        key = (deficit, -state.level_skill_count(lv, sk))
        if key > best_key:
            best_key, best = key, _choose(cands)
    return best


def _block(state: ScoreState, bank: QuestionBank, lv: Level, sk: Skill) -> list[Question]:
    """Блок вопросов по одному тексту/аудио (для чтения — по одному passage)."""
    avail = _unasked(bank, state, lv, sk)
    if not avail:
        return []
    if sk == Skill.listening:
        chosen = avail                                   # одно аудио на уровень
    else:  # reading — берём один текст (passage)
        pid = sorted(avail, key=lambda q: (q.passage_id or "", q.id))[0].passage_id
        chosen = [q for q in avail if q.passage_id == pid]
    chosen = sorted(chosen, key=lambda q: q.id)[:BLOCK_CAP]
    return chosen


def _need_block(state: ScoreState, bank: QuestionBank, lv: Level, sk: Skill) -> bool:
    return state.level_skill_count(lv, sk) == 0 and bool(_unasked(bank, state, lv, sk))


def next_step(answers: list[AnswerIn], bank: QuestionBank, settings: Settings) -> list[Question]:
    """Следующий шаг: [1 вопрос] для грамматики/продакшна или [N вопросов] блоком. [] → конец."""
    state = build_score_state(answers, bank)
    if len(state.asked_ids) >= settings.max_questions:
        return []

    for lv in LEVEL_ORDER:
        st = state.level(lv)
        # фаза решения: набираем грамматику/лексику
        if st.total < GRAM_DECIDE:
            q = _pick_single(state, bank, lv)
            if q:
                return [q]
        # уровень пройден уверенно → выше
        if st.total >= GRAM_DECIDE and st.ratio >= PASS and lv != LEVEL_ORDER[-1]:
            continue
        # уровень остановки → полное покрытие навыков
        if _need_block(state, bank, lv, Skill.listening):
            return _block(state, bank, lv, Skill.listening)
        if _need_block(state, bank, lv, Skill.reading):
            return _block(state, bank, lv, Skill.reading)
        if state.level_skill_count(lv, Skill.grammar) < GRAM_FULL:
            q = _pick_single(state, bank, lv)
            if q:
                return [q]
        # продакшн (письмо/говорение) на уровне остановки
        for sk in (Skill.writing, Skill.speaking):
            if state.skill_count(sk) == 0:
                cands = _unasked(bank, state, lv, sk) or [
                    q for q in bank.questions if q.skill == sk and q.id not in state.asked_ids
                ]
                if cands:
                    return [_choose(cands)]
        return []
    return []


# --------------------------------------------------------------------------- #
#  Матрица присвоения финального уровня
# --------------------------------------------------------------------------- #
def level_from_ratios(a1: float, a2: float, b1: float, a1_total: int) -> tuple[Level, Zone]:
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
