"""Оценщик: payload для GPT → вызов gpt-4o → валидированный Report.

Без ключа OpenAI работает мок-режим (детерминированный валидный отчёт),
чтобы весь поток теста проходил локально до получения ключа.
"""
from __future__ import annotations

import json

from pydantic import ValidationError

from .adaptive import assign_level
from .artifacts import generate_promo_code, generate_referral_code
from .bank import QuestionBank
from .config import PROMPTS_DIR, settings
from .errors import EvaluationError, log
from .schemas import (
    AnswerIn,
    Level,
    QuestionType,
    RecommendedCase,
    RecommendedCourse,
    Report,
    SkillNote,
    StartRequest,
    StudyPlan,
    TargetSolution,
    Zone,
)
from .scoring import ScoreState, build_score_state, is_correct_closed

_COURSES = {
    Level.A0: ("A1", "Курс Türkford А1", "https://turkford.com/kurs_a1"),
    Level.A1: ("A2", "Курс Türkford А2", "https://turkford.com/kurs_a2"),
    Level.A2: ("B1", "Курс Türkford B1", "https://turkford.com/kurs_b1"),
    Level.B1: ("B1", "Курс Türkford B1", "https://turkford.com/kurs_b1"),
}
_LABELS = {Level.A0: "Самое начало", Level.A1: "Базовый", Level.A2: "Средний", Level.B1: "Уверенный"}


def _course_for(level: Level, zone: Zone) -> RecommendedCourse:
    """Рекомендуемый курс по матрице: освоенный уровень → курс следующего."""
    if level == Level.B1 and zone == Zone.confident:
        return RecommendedCourse(
            level="B1", name="Созвон с куратором (B2)", url="https://turkford.com",
            why="Ты уверенно держишь B1 — обсуди с куратором переход к B2.",
        )
    if zone == Zone.confident and level in (Level.A1, Level.A2):
        nxt, name, url = _COURSES[level]
        return RecommendedCourse(level=nxt, name=name, url=url, why="Уровень освоен — пора на следующий курс.")
    nxt, name, url = _COURSES[level]
    cur = level.value if level != Level.A0 else "A1"
    return RecommendedCourse(level=cur, name=name, url=url, why="Закрепи текущий уровень на курсе.")


# --------------------------------------------------------------------------- #
#  Построение входного payload для GPT
# --------------------------------------------------------------------------- #
def build_eval_payload(
    req: StartRequest, answers: list[AnswerIn], bank: QuestionBank,
    level: Level, zone: Zone, stats: ScoreState,
) -> dict:
    items: list[dict] = []
    for a in answers:
        if not bank.exists(a.id):
            continue
        q = bank.get(a.id)
        if q.type == QuestionType.closed:
            ic = is_correct_closed(a.given, q.correct) if q.correct is not None else None
            items.append({"type": "closed", "level": q.level.value, "skill": q.skill.value,
                          "question": q.question, "is_correct": ic})
        elif q.type == QuestionType.open_meaning:
            items.append({"type": "open_meaning", "level": q.level.value, "skill": q.skill.value,
                          "question": q.question, "expected_answer": q.expected_answer,
                          "user_answer": a.given})
        else:  # production
            text = a.user_text or a.transcript or a.given
            items.append({"type": "production", "task_level": q.level.value, "skill": q.skill.value,
                          "task_prompt": q.question, "user_text": text})
    return {
        "contact": {"name": req.contact.name, "self_assessment": req.contact.self_assessment},
        "segment": req.segment,
        "goal": req.goal,
        "computed": {
            "assigned_level": level.value,
            "assigned_zone": zone.value,
            "level_stats": {lv.value: {"correct": s.correct, "total": s.total}
                            for lv, s in stats.levels.items()},
        },
        "answers": items,
    }


# --------------------------------------------------------------------------- #
#  Вызов GPT
# --------------------------------------------------------------------------- #
def _load_prompt() -> str:
    return (PROMPTS_DIR / "system_gpt.md").read_text(encoding="utf-8")


def _call_gpt(payload: dict) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    try:
        resp = client.chat.completions.create(
            model=settings.eval_model,
            messages=[
                {"role": "system", "content": _load_prompt()},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
        )
        return json.loads(resp.choices[0].message.content or "{}")
    except Exception as exc:  # сетевые/квота/парсинг — в доменную ошибку
        raise EvaluationError(f"Ошибка вызова модели: {exc}") from exc


# --------------------------------------------------------------------------- #
#  Мок-отчёт (без ключа OpenAI)
# --------------------------------------------------------------------------- #
def _mock_report(req: StartRequest, level: Level, zone: Zone, stats: ScoreState) -> Report:
    base = {Level.A0: 25, Level.A1: 55, Level.A2: 70, Level.B1: 85}[level]
    chart = {k: base for k in ("audirovanie", "grammatika", "pismo", "govorenie", "chtenie")}
    course = _course_for(level, zone)
    goal = req.goal or "освоить турецкий"
    return Report(
        level=level,
        level_label=_LABELS[level],
        level_zone=zone,
        level_short=f"Твой уровень — {level.value} ({'уверенно' if zone == Zone.confident else 'в процессе освоения'}).",
        skills={k: SkillNote(status="средне", note="предварительная оценка (мок-режим без ИИ)")
                for k in ("grammar", "vocabulary", "reading", "listening", "production")},
        skills_chart=chart,
        feedback="Это предварительный результат (ИИ-оценка появится после подключения ключа OpenAI). "
                 "Ты сделала хороший шаг — прошла диагностику до конца.",
        target_solution=TargetSolution(
            goal_echo=goal[:60],
            paragraph=f"Ты хочешь {goal}. В Türkford под эту задачу подбирают практику и куратора, "
                      f"которые ведут к результату шаг за шагом.",
        ),
        recommended_case=RecommendedCase(
            id="anon_speaking", name="Выпускница Türkford",
            story_before="Начинала с базового уровня и страха говорить.",
            story_after="Через системную практику начала свободно общаться.",
        ),
        plan=StudyPlan(
            target_level=course.level,
            estimated="примерно 4–5 месяцев при занятиях 2–3 раза в неделю",
            topics=["Закрепление грамматики уровня", "Расширение лексики", "Аудирование", "Разговорная практика"],
            schedule="2–3 занятия в неделю + ежедневно 15 минут на повторение лексики",
            extra=["Смотри турецкий сериал с субтитрами", "Слушай подкаст по 10 минут в день"],
        ),
        recommended_course=course,
        certificate_line=f"Сертификат прохождения диагностики уровня турецкого языка в школе Türkford. "
                         f"{req.contact.name}. Уровень: {level.value}.",
        manager_note=f"Сегмент: {req.segment or '—'}. Цель: {goal}. Уровень {level.value} ({zone.value}).",
    )


# --------------------------------------------------------------------------- #
#  Главная точка входа
# --------------------------------------------------------------------------- #
def evaluate(req: StartRequest, answers: list[AnswerIn], bank: QuestionBank) -> Report:
    stats = build_score_state(answers, bank)
    level, zone = assign_level(answers, bank)

    if settings.has_openai:
        payload = build_eval_payload(req, answers, bank, level, zone, stats)
        raw = _call_gpt(payload)
        try:
            report = Report.model_validate(raw)
        except ValidationError as exc:
            log.warning("report_validation_failed", error=str(exc))
            raise EvaluationError("Модель вернула отчёт неверного формата") from exc
    else:
        log.info("eval_mock_mode", reason="no_openai_key")
        report = _mock_report(req, level, zone, stats)

    # Рекомендацию курса фиксируем детерминированно (модель иногда выдумывает несуществующий kurs_b2)
    report.recommended_course = _course_for(level, zone)
    # Коды генерируются на сервере, не моделью
    report.promo_code = generate_promo_code()
    report.referral_code = generate_referral_code(req.contact.name)
    return report
