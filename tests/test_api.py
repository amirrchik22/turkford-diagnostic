"""Сквозные тесты API: старт → адаптивный next-цикл → finish (мок-режим без ключа OpenAI)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.bank import get_bank
from backend.main import app
from backend.schemas import QuestionType

client = TestClient(app)
BANK = get_bank()

CONTACT = {
    "name": "Алина",
    "email": "alina@example.com",
    "phone": "+70000000000",
    "telegram": "@alina",
    "self_assessment": "начинающий",
    "consent_pd": True,
}


def _answer_for(qid: str) -> dict:
    """Симулируем верный ответ (тест знает банк)."""
    q = BANK.get(qid)
    if q.type == QuestionType.closed:
        return {"id": qid, "given": q.correct or (q.options[0] if q.options else "x")}
    return {"id": qid, "given": "ответ", "user_text": "Benim ailem büyük ve güzel."}


def _step_questions(data: dict) -> list[dict]:
    """Вопросы текущего шага: одиночный вопрос или блок (чтение/аудирование)."""
    if data.get("block"):
        return data["block"]["questions"]
    if data.get("question"):
        return [data["question"]]
    return []


def _run_full_test() -> list[dict]:
    r = client.post("/api/start", json={"contact": CONTACT, "segment": "семья", "goal": "говорить с семьёй мужа"})
    assert r.status_code == 200
    data = r.json()
    answers: list[dict] = []
    guard = 0
    while not data.get("done") and guard < 100:
        qs = _step_questions(data)
        if not qs:
            break
        for q in qs:
            answers.append(_answer_for(q["id"]))
        data = client.post("/api/next", json={"answers": answers}).json()
        guard += 1
    return answers


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["questions"] > 0


def test_start_requires_consent():
    bad = {**CONTACT, "consent_pd": False}
    r = client.post("/api/start", json={"contact": bad})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "consent_required"


def test_start_returns_first_question():
    r = client.post("/api/start", json={"contact": CONTACT})
    assert r.status_code == 200
    assert r.json()["question"] is not None
    # правильный ответ не утекает клиенту
    assert "correct" not in r.json()["question"]


def test_full_flow_and_finish_mock():
    answers = _run_full_test()
    assert len(answers) > 6  # зонд + прогон
    r = client.post("/api/finish", json={
        "contact": CONTACT, "segment": "семья", "goal": "говорить с семьёй мужа", "answers": answers,
    })
    assert r.status_code == 200
    report = r.json()
    assert report["level"] in ("A0", "A1", "A2", "B1")
    assert report["level_zone"] in ("in_progress", "confident")
    assert set(report["skills_chart"].keys()) == {"audirovanie", "grammatika", "pismo", "govorenie", "chtenie"}
    assert report["recommended_course"]["url"].startswith("https://turkford.com")
    assert report["promo_code"].startswith("TURK-")
    assert "_" in report["referral_code"]
    assert report["certificate_line"].startswith("Сертификат прохождения диагностики")


def test_finish_requires_consent():
    bad = {**CONTACT, "consent_pd": False}
    r = client.post("/api/finish", json={"contact": bad, "answers": []})
    assert r.status_code == 400


def test_audio_empty_file_rejected():
    r = client.post("/api/audio", files={"file": ("rec.webm", b"", "audio/webm")})
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "transcription_error"
