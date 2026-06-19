"""Тесты адаптивной лесенки: А1→А2→B1, не пускаем выше неосвоенного, матрица уровней."""
from __future__ import annotations

import pytest

from backend.adaptive import assign_level, level_from_ratios, next_step
from backend.bank import get_bank
from backend.config import settings
from backend.schemas import AnswerIn, Level, QuestionType, Skill, Zone

BANK = get_bank()


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
    for _ in range(200):
        step = next_step(answers, BANK, settings)
        if not step:
            break
        for full in step:
            if full.type == QuestionType.closed:
                correct = order.get(full.level, 9) <= cap
                given = full.correct if correct else _wrong_option(full)
                answers.append(AnswerIn(id=full.id, given=given))
            else:
                answers.append(AnswerIn(id=full.id, given="ответ", user_text="Benim ailem güzel."))
    else:
        pytest.fail("Тест не завершился — возможно зацикливание")
    return answers


def _levels_asked(answers: list[AnswerIn]) -> set[Level]:
    return {BANK.get(a.id).level for a in answers}


# --------------------------------------------------------------------------- #
#  Старт и лесенка
# --------------------------------------------------------------------------- #
def test_first_step_is_a1():
    step = next_step([], BANK, settings)
    assert step and step[0].level == Level.A1


def test_listening_comes_as_block():
    """Аудирование выдаётся блоком (несколько вопросов по одному аудио сразу)."""
    answers: list[AnswerIn] = []
    saw_block = False
    for _ in range(200):
        step = next_step(answers, BANK, settings)
        if not step:
            break
        if step[0].skill == Skill.listening and len(step) > 1:
            saw_block = True
        for full in step:
            given = full.correct if full.type == QuestionType.closed else "x"
            answers.append(AnswerIn(id=full.id, given=given or "x", user_text="x"))
    assert saw_block


def test_failing_a1_never_shows_higher_levels():
    """Если в А1 ошибки — выше не поднимаемся (никаких А2/B1)."""
    answers = simulate(None)
    assert _levels_asked(answers) == {Level.A1}


def test_a1_pass_tests_a2_but_not_b1():
    """Сдал А1, валит А2 → показываем А1 и А2, но НЕ B1."""
    answers = simulate(Level.A1)
    asked = _levels_asked(answers)
    assert Level.A2 in asked
    assert Level.B1 not in asked


def test_full_mastery_reaches_b1():
    answers = simulate(Level.B1)
    assert Level.B1 in _levels_asked(answers)


def test_failing_a1_digs_deeper_than_six():
    """При провале А1 — не 6 вопросов, а полноценный разбор А1 (покрытие навыков)."""
    answers = simulate(None)
    assert len(answers) >= 8


def test_respects_max_questions_and_no_repeats():
    answers = simulate(Level.B1)
    ids = [a.id for a in answers]
    assert len(ids) == len(set(ids))
    assert len(answers) <= settings.max_questions


# --------------------------------------------------------------------------- #
#  Финальный уровень
# --------------------------------------------------------------------------- #
def test_all_wrong_gives_a0():
    assert assign_level(simulate(None), BANK)[0] == Level.A0


def test_a1_only_gives_a1_confident():
    lvl, zone = assign_level(simulate(Level.A1), BANK)
    assert lvl == Level.A1 and zone == Zone.confident


def test_a2_mastery_gives_a2_confident():
    lvl, zone = assign_level(simulate(Level.A2), BANK)
    assert lvl == Level.A2 and zone == Zone.confident


def test_all_correct_gives_b1_confident():
    assert assign_level(simulate(Level.B1), BANK) == (Level.B1, Zone.confident)


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


def test_question_out_hides_correct_answer():
    out = BANK.to_out(BANK.questions[0])
    dumped = out.model_dump()
    assert "correct" not in dumped and "expected_answer" not in dumped


def test_listening_question_has_no_transcript_text():
    """Для аудирования транскрипт клиенту НЕ отдаётся (это ответ)."""
    listening = [q for q in BANK.questions if q.skill.value == "listening" and q.passage_id]
    assert listening, "нет аудиовопросов с пассажем для проверки"
    assert BANK.to_out(listening[0]).passage_text is None
