"""Тесты подсчёта: сравнение закрытых ответов и агрегация по уровням/навыкам."""
from __future__ import annotations

from backend.bank import get_bank
from backend.schemas import AnswerIn, Level, QuestionType
from backend.scoring import build_score_state, is_correct_closed

BANK = get_bank()


def test_is_correct_closed_exact():
    assert is_correct_closed("mı", "mı") is True
    assert is_correct_closed("mı", "mi") is False


def test_is_correct_closed_normalizes_case_and_space():
    assert is_correct_closed("  Gider ", "gider") is True


def test_is_correct_closed_none():
    assert is_correct_closed(None, "x") is False
    assert is_correct_closed("x", None) is False


def test_build_score_state_counts_only_closed():
    closed = [q for q in BANK.questions if q.type == QuestionType.closed][:3]
    answers = [AnswerIn(id=q.id, given=q.correct) for q in closed]
    state = build_score_state(answers, BANK)
    total = sum(s.total for s in state.levels.values())
    assert total == 3
    correct = sum(s.correct for s in state.levels.values())
    assert correct == 3


def test_build_score_state_tracks_skills_and_ids():
    q = BANK.questions[0]
    state = build_score_state([AnswerIn(id=q.id, given="x")], BANK)
    assert q.id in state.asked_ids
    assert state.skill_count(q.skill) == 1


def test_unknown_answer_id_ignored():
    state = build_score_state([AnswerIn(id="NOPE-999", given="x")], BANK)
    assert not state.asked_ids
