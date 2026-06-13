"""Тесты адаптивного движка: зонд, прогон-симуляция, матрица уровней, отсутствие утечки ответов."""
from __future__ import annotations

import pytest

from backend.adaptive import (
    LEVEL_ORDER,
    assign_level,
    level_from_ratios,
    next_question,
    probe_ids,
)
from backend.bank import get_bank
from backend.config import settings
from backend.schemas import AnswerIn, Level, QuestionType, Zone

BANK = get_bank()


# --------------------------------------------------------------------------- #
#  Зонд
# --------------------------------------------------------------------------- #
def test_probe_size_and_levels():
    ids = probe_ids(BANK, settings.probe_size)
    assert len(ids) == settings.probe_size
    levels = [BANK.get(i).level for i in ids]
    for lv in LEVEL_ORDER:
        assert levels.count(lv) == settings.probe_size // len(LEVEL_ORDER)


def test_probe_is_deterministic():
    assert probe_ids(BANK, 6) == probe_ids(BANK, 6)


def test_probe_questions_are_closed():
    for qid in probe_ids(BANK, settings.probe_size):
        assert BANK.get(qid).type == QuestionType.closed


# --------------------------------------------------------------------------- #
#  Симуляция ученицы
# --------------------------------------------------------------------------- #
def _wrong_option(q) -> str:
    for o in q.options:
        if o != q.correct:
            return o
    return "__WRONG__"


def simulate(mastered_upto: Level | None) -> list[AnswerIn]:
    """Ученица отвечает верно на уровни <= mastered_upto, неверно — выше."""
    order = {Level.A1: 1, Level.A2: 2, Level.B1: 3}
    cap = order.get(mastered_upto, 0) if mastered_upto else 0
    answers: list[AnswerIn] = []
    for _ in range(200):  # предохранитель
        q = next_question(answers, BANK, settings)
        if q is None:
            break
        full = BANK.get(q.id)
        if full.type == QuestionType.closed:
            correct = order.get(full.level, 9) <= cap
            given = full.correct if correct else _wrong_option(full)
        else:
            given = "текст ответа"
        answers.append(AnswerIn(id=q.id, given=given))
    else:
        pytest.fail("Тест не завершился — возможно зацикливание")
    return answers


def test_all_correct_gives_b1_confident():
    lvl, zone = assign_level(simulate(Level.B1), BANK)
    assert (lvl, zone) == (Level.B1, Zone.confident)


def test_all_wrong_gives_a0():
    lvl, _ = assign_level(simulate(None), BANK)
    assert lvl == Level.A0


def test_a1_only_gives_a1_confident():
    lvl, zone = assign_level(simulate(Level.A1), BANK)
    assert lvl == Level.A1 and zone == Zone.confident


def test_a2_mastery_gives_a2_confident():
    lvl, zone = assign_level(simulate(Level.A2), BANK)
    assert lvl == Level.A2 and zone == Zone.confident


def test_simulation_respects_max_questions():
    answers = simulate(Level.B1)
    assert len(answers) <= settings.max_questions


def test_no_repeated_questions():
    answers = simulate(Level.A2)
    ids = [a.id for a in answers]
    assert len(ids) == len(set(ids))


# --------------------------------------------------------------------------- #
#  Матрица уровней (чистая функция)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "a1,a2,b1,total,expected",
    [
        (0.0, 0.0, 0.0, 0, (Level.A0, Zone.in_progress)),
        (0.5, 0.0, 0.0, 6, (Level.A0, Zone.in_progress)),
        (0.7, 0.0, 0.0, 6, (Level.A1, Zone.in_progress)),
        (0.9, 0.4, 0.0, 6, (Level.A1, Zone.confident)),
        (0.9, 0.7, 0.0, 6, (Level.A2, Zone.in_progress)),
        (0.9, 0.9, 0.4, 6, (Level.A2, Zone.confident)),
        (0.9, 0.9, 0.7, 6, (Level.B1, Zone.in_progress)),
        (1.0, 1.0, 1.0, 6, (Level.B1, Zone.confident)),
    ],
)
def test_level_matrix(a1, a2, b1, total, expected):
    assert level_from_ratios(a1, a2, b1, total) == expected


# --------------------------------------------------------------------------- #
#  Безопасность: клиенту не уходит правильный ответ
# --------------------------------------------------------------------------- #
def test_question_out_hides_correct_answer():
    q = BANK.questions[0]
    out = BANK.to_out(q)
    dumped = out.model_dump()
    assert "correct" not in dumped
    assert "expected_answer" not in dumped
