/* TÜrkford — клиент адаптивной диагностики. Общается с FastAPI (/api/*). */
const App = (() => {
  const LS_KEY = "turkford_diag_v1";
  const SEGMENTS = [
    { v: "семья", t: "💚 Семья / жизнь в Турции" },
    { v: "путешествия", t: "✈️ Путешествия" },
    { v: "работа", t: "💼 Работа / карьера" },
    { v: "культура", t: "📺 Для себя / культура" },
  ];
  const GOALS = [
    "Свободно говорить с семьёй / в Турции",
    "Уверенно общаться в быту (врач, документы, магазин)",
    "Понимать сериалы и музыку в оригинале",
    "Работать с турецкими партнёрами / клиентами",
    "Путешествовать по Турции свободно",
    "Развиваться для себя, учить в удовольствие",
  ];

  let s = { screen: "intro", contact: {}, segment: null, goal: null,
            answers: [], current: null, report: null, selected: null };

  // ---- сохранение прогресса ----
  function save() {
    localStorage.setItem(LS_KEY, JSON.stringify({
      contact: s.contact, segment: s.segment, goal: s.goal, answers: s.answers,
    }));
  }
  function restore() {
    try {
      const d = JSON.parse(localStorage.getItem(LS_KEY) || "{}");
      if (d.contact) s.contact = d.contact;
      if (d.segment) s.segment = d.segment;
      if (d.goal) s.goal = d.goal;
      if (Array.isArray(d.answers)) s.answers = d.answers;
    } catch (e) {}
  }

  // ---- навигация ----
  const SCREENS = ["intro","contact","segment","goal","test","loading","report","nps","done"];
  function go(name) {
    s.screen = name;
    SCREENS.forEach(n => {
      const el = document.getElementById("screen-" + n);
      if (el) el.classList.toggle("hidden", n !== name);
    });
    document.getElementById("progress-wrap").classList.toggle("hidden", name !== "test");
  }

  // ---- API ----
  async function api(path, body, isForm) {
    const opt = { method: "POST" };
    if (isForm) { opt.body = body; }
    else { opt.headers = { "Content-Type": "application/json" }; opt.body = JSON.stringify(body); }
    const r = await fetch(path, opt);
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error((err.error && err.error.message) || ("Ошибка " + r.status));
    }
    return r.json();
  }

  // ---- Экран 1: контакты ----
  function toggleConsent() {
    document.getElementById("btn-contact").disabled = !document.getElementById("f-consent").checked;
  }
  function submitContact() {
    s.contact = {
      name: val("f-name"), email: val("f-email"), phone: val("f-phone"),
      telegram: val("f-telegram"), self_assessment: val("f-self"),
      consent_pd: document.getElementById("f-consent").checked,
    };
    if (!s.contact.name || !s.contact.email || !s.contact.phone) {
      alert("Заполни имя, email и телефон."); return;
    }
    save(); renderSegments(); go("segment");
  }
  const val = id => document.getElementById(id).value.trim();

  // ---- Экран 2: сегмент ----
  function renderSegments() {
    const box = document.getElementById("segment-cards");
    box.innerHTML = "";
    SEGMENTS.forEach(seg => {
      const c = document.createElement("div");
      c.className = "card"; c.textContent = seg.t;
      c.onclick = () => { s.segment = seg.v; save(); renderGoals(); go("goal"); };
      box.appendChild(c);
    });
  }

  // ---- Экран 2.5: цель ----
  function renderGoals() {
    const box = document.getElementById("goal-cards");
    box.innerHTML = "";
    GOALS.forEach(g => {
      const c = document.createElement("div");
      c.className = "card"; c.textContent = g;
      c.onclick = () => { document.querySelectorAll("#goal-cards .card").forEach(x => x.classList.remove("selected"));
        c.classList.add("selected"); s.goal = g; };
      box.appendChild(c);
    });
  }
  async function submitGoal() {
    const other = val("f-goal-other");
    if (other) s.goal = other;
    if (!s.goal) { alert("Выбери цель или напиши свою."); return; }
    save();
    try {
      const res = await api("/api/start", { contact: s.contact, segment: s.segment, goal: s.goal });
      s.answers = []; save();
      go("test"); renderStep(res);
    } catch (e) { alert(e.message); }
  }

  // ---- Экран 3: шаг (одиночный вопрос или блок) ----
  function renderStep(data) {
    setProgress(data.progress, data.asked);
    if (data.done) { finish(); return; }
    if (data.block) { showBlock(data.block); } else { showQuestion(data.question); }
  }

  function submit() { if (s.mode === "block") submitBlock(); else submitAnswer(); }

  // Блок: текст/аудио + несколько вопросов на одном экране
  function showBlock(block) {
    s.mode = "block"; s.block = block; s.blockSel = {};
    const passage = document.getElementById("q-passage");
    passage.classList.toggle("hidden", !block.passage_text);
    if (block.passage_text) passage.textContent = block.passage_text;
    const audio = document.getElementById("q-audio");
    if (block.audio_level) {
      audio.classList.remove("hidden");
      document.getElementById("q-audio-el").src = "/static/audio/" + block.audio_level + ".m4a";
    } else { audio.classList.add("hidden"); }
    document.getElementById("q-meta").textContent = `${block.level} · ${skillRu(block.skill)}`;
    document.getElementById("q-text").textContent = block.skill === "listening"
      ? "Прослушай аудио и ответь на все вопросы:" : "Прочитай текст и ответь на все вопросы:";
    const ans = document.getElementById("q-answer"); ans.innerHTML = "";
    block.questions.forEach((q, i) => {
      const wrap = document.createElement("div"); wrap.className = "q-sub";
      const t = document.createElement("div"); t.className = "q-sub-text";
      t.textContent = (i + 1) + ". " + q.question; wrap.appendChild(t);
      if (q.type === "closed") {
        q.options.forEach(o => {
          const b = document.createElement("button"); b.className = "opt"; b.textContent = o;
          b.onclick = () => { wrap.querySelectorAll(".opt").forEach(x => x.classList.remove("selected"));
            b.classList.add("selected"); s.blockSel[q.id] = { given: o }; };
          wrap.appendChild(b);
        });
      } else {
        const inp = document.createElement("textarea"); inp.rows = 2; inp.placeholder = "Твой ответ…";
        inp.className = "block-open"; inp.dataset.qid = q.id; wrap.appendChild(inp);
      }
      ans.appendChild(wrap);
    });
  }

  async function submitBlock() {
    for (const q of s.block.questions) {
      const a = { id: q.id };
      if (q.type === "closed") {
        if (!s.blockSel[q.id]) { alert("Ответь на все вопросы блока."); return; }
        a.given = s.blockSel[q.id].given;
      } else {
        const inp = document.querySelector('.block-open[data-qid="' + q.id + '"]');
        a.given = (inp && inp.value.trim()) || "";
      }
      s.answers.push(a);
    }
    save();
    try { renderStep(await api("/api/next", { answers: s.answers })); }
    catch (e) { alert(e.message); }
  }

  // ---- одиночный вопрос ----
  function showQuestion(q) {
    s.mode = "single"; s.block = null;
    s.current = q; s.selected = null;
    const passage = document.getElementById("q-passage");
    passage.classList.toggle("hidden", !q.passage_text);
    if (q.passage_text) passage.textContent = q.passage_text;

    const audio = document.getElementById("q-audio");
    if (q.skill === "listening") {
      audio.classList.remove("hidden");
      document.getElementById("q-audio-el").src = "/static/audio/" + q.level.toLowerCase() + ".m4a";
    } else { audio.classList.add("hidden"); }

    document.getElementById("q-meta").textContent = `${q.level} · ${skillRu(q.skill)}`;
    document.getElementById("q-text").textContent = q.question;
    const ans = document.getElementById("q-answer");
    ans.innerHTML = "";

    if (q.type === "closed") {
      q.options.forEach(o => {
        const b = document.createElement("button");
        b.className = "opt"; b.textContent = o;
        b.onclick = () => { ans.querySelectorAll(".opt").forEach(x => x.classList.remove("selected"));
          b.classList.add("selected"); s.selected = { given: o }; };
        ans.appendChild(b);
      });
    } else if (q.type === "open_meaning") {
      const inp = document.createElement("textarea");
      inp.rows = 2; inp.id = "open-input"; inp.placeholder = "Твой ответ…";
      ans.appendChild(inp);
    } else if (q.skill === "writing") {
      const ta = document.createElement("textarea");
      ta.rows = 5; ta.id = "write-input"; ta.placeholder = "Напиши 4–5 предложений по-турецки…";
      ans.appendChild(ta);
    } else if (q.skill === "speaking") {
      renderRecorder(ans);
    }
  }

  // ---- запись говорения ----
  let mediaRec = null, chunks = [], recTimer = null, recSecs = 0, lastBlobUrl = null;
  const LANG_RU = { tr: "турецкий", ru: "русский", en: "английский", de: "немецкий",
    fr: "французский", ar: "арабский", uk: "украинский", kk: "казахский" };
  const MAX_SEC = 90;

  function renderRecorder(ans) {
    ans.innerHTML = `
      <div class="recorder">
        <div class="rec-hint">🎤 Ответь на это задание <b>по-турецки</b>. Нажми на микрофон и говори.</div>
        <button id="mic-btn" class="mic-btn">🎤</button>
        <div id="rec-timer" class="rec-timer hidden">0:00</div>
        <div id="rec-area"></div>
      </div>`;
    document.getElementById("mic-btn").onclick = () =>
      (mediaRec && mediaRec.state === "recording") ? stopRec() : startRec();
  }

  async function startRec() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRec = new MediaRecorder(stream); chunks = [];
      mediaRec.ondataavailable = e => chunks.push(e.data);
      mediaRec.onstop = onRecStop;
      mediaRec.start();
      const btn = document.getElementById("mic-btn");
      btn.classList.add("recording"); btn.textContent = "⏹";
      document.getElementById("rec-area").innerHTML = "";
      recSecs = 0;
      const t = document.getElementById("rec-timer");
      t.classList.remove("hidden"); t.textContent = "0:00";
      recTimer = setInterval(() => {
        recSecs++;
        t.textContent = "0:" + String(recSecs).padStart(2, "0");
        if (recSecs >= MAX_SEC) stopRec();
      }, 1000);
    } catch (e) { alert("Не удалось получить доступ к микрофону. Разреши доступ в браузере.\n" + e.message); }
  }

  function stopRec() {
    if (recTimer) { clearInterval(recTimer); recTimer = null; }
    if (mediaRec && mediaRec.state === "recording") {
      mediaRec.stop(); mediaRec.stream.getTracks().forEach(t => t.stop());
    }
    const btn = document.getElementById("mic-btn");
    btn.classList.remove("recording"); btn.textContent = "🎤";
    document.getElementById("rec-timer").classList.add("hidden");
  }

  async function onRecStop() {
    const blob = new Blob(chunks, { type: "audio/webm" });
    if (lastBlobUrl) URL.revokeObjectURL(lastBlobUrl);
    lastBlobUrl = URL.createObjectURL(blob);
    const area = document.getElementById("rec-area");
    area.innerHTML = '<div class="muted" style="margin-top:12px">⏳ Распознаём речь…</div>';
    try {
      const fd = new FormData();
      fd.append("file", blob, "rec.webm");
      fd.append("question_id", s.current.id);
      const res = await api("/api/audio", fd, true);

      if (!res.is_turkish) {
        // речь не на турецком — не принимаем, просим переговорить
        s.selected = null;
        const lang = LANG_RU[res.language] || res.language || "не турецкий";
        area.innerHTML = `<div class="rec-warn">🇹🇷 Похоже, ты говоришь не по-турецки (распознали: <b>${lang}</b>).
          Это задание нужно выполнить <b>на турецком языке</b>:
          <div class="task">${s.current.question}</div>
          Нажми на микрофон и попробуй ещё раз.</div>`;
        return;
      }
      // ок — турецкий: воспроизведение + транскрипт + перезапись
      s.selected = { transcript: res.transcript, user_text: res.transcript };
      area.innerHTML = `<div class="rec-result">
          <b>✅ Записано (турецкий):</b>
          <audio controls src="${lastBlobUrl}"></audio>
          <div class="rec-transcript">«${res.transcript || "…"}»</div>
          <button class="btn-ghost" id="rerec">🔄 Перезаписать</button>
        </div>`;
      document.getElementById("rerec").onclick = () => { s.selected = null; startRec(); };
    } catch (e) {
      area.innerHTML = `<div class="rec-warn">Ошибка распознавания: ${e.message}<br>
        <button class="btn-ghost" onclick="App._rerec()">🔄 Попробовать снова</button></div>`;
    }
  }

  // ---- отправка ответа ----
  async function submitAnswer() {
    const q = s.current; let a = { id: q.id };
    if (q.type === "closed") {
      if (!s.selected) { alert("Выбери вариант."); return; }
      a.given = s.selected.given;
    } else if (q.type === "open_meaning") {
      a.given = document.getElementById("open-input").value.trim();
    } else if (q.skill === "writing") {
      a.user_text = document.getElementById("write-input").value.trim();
    } else if (q.skill === "speaking") {
      if (!s.selected) { alert("Сначала запиши ответ."); return; }
      a.user_text = s.selected.user_text; a.transcript = s.selected.transcript;
    }
    s.answers.push(a); save();
    try { renderStep(await api("/api/next", { answers: s.answers })); }
    catch (e) { alert(e.message); }
  }

  function setProgress(p, asked) {
    document.getElementById("progress-bar").style.width = Math.round(p * 100) + "%";
    document.getElementById("progress-text").textContent = "Вопрос " + (asked + 1);
  }
  function finishEarly() {
    if (confirm("Можно завершить, но чем больше вопросов — тем точнее результат. Завершить?")) finish();
  }

  // ---- финал → отчёт ----
  async function finish() {
    go("loading");
    try {
      s.report = await api("/api/finish", {
        contact: s.contact, segment: s.segment, goal: s.goal, answers: s.answers,
      });
      renderReport(s.report); go("report");
    } catch (e) { alert(e.message); go("test"); }
  }

  // ---- Экран 5: отчёт ----
  function renderReport(r) {
    const el = document.getElementById("screen-report");
    const levels = ["A0", "A1", "A2", "B1"];
    const scale = levels.map(l => `<span class="${l === r.level ? "active" : ""}">${l}</span>`).join("");
    const skills = Object.entries(r.skills).map(([k, v]) =>
      `<div class="skill-row"><span>${skillRu(k)}</span><span>${v.status} — ${v.note}</span></div>`).join("");
    el.innerHTML = `
      <div class="level-badge">
        <div class="level-big">${r.level}</div>
        <div class="level-label">${r.level_label} · ${r.level_zone === "confident" ? "уверенно" : "в процессе освоения"}</div>
      </div>
      <div class="level-scale">${scale}</div>
      <p class="lead" style="text-align:center">${r.level_short}</p>
      ${radarSVG(r.skills_chart)}
      <div class="report-block"><h3>Твои навыки</h3>${skills}</div>
      <div class="report-block"><h3>Комментарий</h3><p>${r.feedback}</p></div>
      <div class="report-block"><h3>💚 ${r.target_solution.goal_echo}</h3><p>${r.target_solution.paragraph}</p></div>
      <div class="report-block"><h3>История выпускницы — ${r.recommended_case.name}</h3>
        <p>${r.recommended_case.story_before}<br>→ ${r.recommended_case.story_after}</p></div>
      <div class="report-block"><h3>План: ${r.plan.target_level}</h3>
        <p class="muted">${r.plan.estimated}</p>
        <ul>${r.plan.topics.map(t => `<li>${t}</li>`).join("")}</ul>
        <p><b>Режим:</b> ${r.plan.schedule}</p></div>
      <div class="report-block"><h3>Подходящий курс</h3>
        <p>${r.recommended_course.name} — ${r.recommended_course.why}</p>
        <a class="btn-ghost" href="${r.recommended_course.url}" target="_blank">Посмотреть курс</a></div>
      <div class="promo">🎁 ${r.promo_code} · −5000 ₽ на 24 часа</div>
      <button class="btn-primary" onclick="App.go('nps')">Дальше</button>`;
  }

  // ---- радар (5 шкал) ----
  function radarSVG(chart) {
    const order = ["audirovanie", "grammatika", "chtenie", "govorenie", "pismo"];
    const labels = { audirovanie: "Аудир.", grammatika: "Грамм.", chtenie: "Чтение", govorenie: "Говор.", pismo: "Письмо" };
    const cx = 150, cy = 140, R = 100, n = 5;
    const pt = (i, r) => {
      const ang = -Math.PI / 2 + i * 2 * Math.PI / n;
      return [cx + r * Math.cos(ang), cy + r * Math.sin(ang)];
    };
    let grid = "";
    [0.25, 0.5, 0.75, 1].forEach(f => {
      grid += `<polygon points="${order.map((_, i) => pt(i, R * f).join(",")).join(" ")}" fill="none" stroke="#ece7fb"/>`;
    });
    let axes = "", lbls = "";
    order.forEach((k, i) => {
      const [x, y] = pt(i, R); axes += `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="#ece7fb"/>`;
      const [lx, ly] = pt(i, R + 22);
      lbls += `<text x="${lx}" y="${ly}" font-size="11" fill="#8a8398" text-anchor="middle">${labels[k]}</text>`;
    });
    const vals = order.map((k, i) => {
      const v = chart[k] == null ? 0 : chart[k];
      return pt(i, R * (v / 100)).join(",");
    }).join(" ");
    return `<svg class="radar" width="300" height="290" viewBox="0 0 300 290">
      ${grid}${axes}
      <polygon points="${vals}" fill="rgba(184,167,232,.45)" stroke="#6a4fb3" stroke-width="2"/>
      ${lbls}</svg>`;
  }

  // ---- Экран 6: NPS ----
  function submitNps() {
    const nps = { score: +document.getElementById("nps-score").value,
      agree: document.getElementById("nps-agree").value, text: val("nps-text") };
    // запись NPS в общий лог результатов — на Этапе 6 (интеграция). Пока сохраняем локально.
    localStorage.setItem(LS_KEY + "_nps", JSON.stringify(nps));
    go("done");
  }

  function restart() { localStorage.removeItem(LS_KEY); location.reload(); }
  function skillRu(k) {
    return { grammar: "Грамматика", vocabulary: "Лексика", reading: "Чтение",
      listening: "Аудирование", writing: "Письмо", speaking: "Говорение",
      production: "Речь" }[k] || k;
  }

  restore();
  return { go, toggleConsent, submitContact, submitGoal, submit, submitAnswer, finishEarly, submitNps, restart, _rerec: startRec };
})();
