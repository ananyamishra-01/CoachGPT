// CoachGPT frontend. Talks to the FastAPI backend; no API keys live here.

const API_BASE = window.location.port === "8000"
  ? ""                                                    // backend serves this page
  : `http://${window.location.hostname || "localhost"}:8000`;  // e.g. python -m http.server 5500
const CUR = "\u20b9";

const state = {
  token: null, username: null, profile: null, targets: null,
  progress: null, chatHistory: [], authMode: "login", hadProfile: false,
};

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const withArticle = (word) => (/^[aeiou]/i.test(word) ? "an " : "a ") + word;
const num = (n, d = 0) => Number(n).toLocaleString("en-IN", { maximumFractionDigits: d });

const LABELS = {
  weight_loss: "Weight loss", weight_gain: "Weight gain", maintenance: "Maintenance",
  vegan: "Vegan", vegetarian: "Vegetarian", eggetarian: "Eggetarian", non_vegetarian: "Non-veg",
  beginner: "Beginner", intermediate: "Intermediate", advanced: "Advanced",
};
const WORKOUT_LABELS = {
  strength: "Strength", cardio: "Cardio", hiit: "HIIT", yoga_mobility: "Yoga / mobility",
  sports: "Sports", walk: "Walk / run", other: "Other",
};

// ---------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------
function store(key, value) {
  try { value === null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch (_) {}
}
function load(key) {
  try { return localStorage.getItem(key); } catch (_) { return null; }
}
function todayStr() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function fmtDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}
function setError(id, message) { $(id).textContent = message || ""; }

async function api(path, { method = "GET", body } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (state.token) headers["Authorization"] = `Bearer ${state.token}`;
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method, headers, body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (_) {
    throw new Error("Can't reach the CoachGPT server. Is the backend running?");
  }
  let data = null;
  try { data = await res.json(); } catch (_) {}
  if (!res.ok) {
    if (res.status === 401 && state.token) { await logout(false); }
    throw new Error((data && data.detail) || `Something went wrong (${res.status}).`);
  }
  return data;
}

// Lightweight, safe formatting for chat replies (bold, italics, bullets, headings).
function renderChatText(text) {
  let h = esc(text);
  h = h.replace(/^#{1,4}\s*(.+)$/gm, "<strong>$1</strong>");
  h = h.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  h = h.replace(/(^|\s)_([^_\n]+)_(?=\s|$|[.,;:!?])/g, "$1<em>$2</em>");
  h = h.replace(/^\s*[-*]\s+/gm, "\u2022 ");
  return h;
}

// ---------------------------------------------------------------------
// Theme
// ---------------------------------------------------------------------
const SUN = '<svg class="icon-sun" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="4.5" stroke="currentColor" stroke-width="1.8"/><path d="M12 2v2.2M12 19.8V22M4.2 4.2l1.55 1.55M18.25 18.25l1.55 1.55M2 12h2.2M19.8 12H22M4.2 19.8l1.55-1.55M18.25 5.75l1.55-1.55" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
const MOON = '<svg class="icon-moon" viewBox="0 0 24 24" fill="none"><path d="M20 14.5A8.5 8.5 0 019.5 4 8.5 8.5 0 1020 14.5z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>';

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  store("coachgpt_theme", theme);
}
document.querySelectorAll(".theme-toggle").forEach((btn) => {
  btn.innerHTML = SUN + MOON;
  btn.addEventListener("click", () => {
    applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark");
  });
});
applyTheme(load("coachgpt_theme") ||
  (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"));

// ---------------------------------------------------------------------
// Screens
// ---------------------------------------------------------------------
function showScreen(name) {
  $("auth-screen").classList.toggle("hidden", name !== "auth");
  $("profile-screen").classList.toggle("hidden", name !== "profile");
  $("app").classList.toggle("hidden", name !== "app");
  window.scrollTo(0, 0);
}

// ---------------------------------------------------------------------
// Login / register
// ---------------------------------------------------------------------
function setAuthMode(mode) {
  state.authMode = mode;
  const register = mode === "register";
  $("auth-title").textContent = register ? "Create your account" : "Welcome back";
  $("auth-sub").textContent = register
    ? "Your plan and progress are saved to your account."
    : "Log in to pick up your plan and progress.";
  $("auth-submit").textContent = register ? "Create account" : "Log in";
  $("auth-switch-text").textContent = register ? "Already have an account?" : "New here?";
  $("auth-switch").textContent = register ? "Log in" : "Create an account";
  $("auth-hint").textContent = register ? "At least 6 characters." : "";
  $("auth-password").autocomplete = register ? "new-password" : "current-password";
  setError("auth-error", "");
}
$("auth-switch").addEventListener("click", () =>
  setAuthMode(state.authMode === "login" ? "register" : "login"));

$("auth-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = $("auth-username").value.trim();
  const password = $("auth-password").value;
  if (!username || !password) return setError("auth-error", "Please enter a username and password.");
  if (state.authMode === "register") {
    if (username.length < 3) return setError("auth-error", "Username needs at least 3 characters.");
    if (password.length < 6) return setError("auth-error", "Password needs at least 6 characters.");
  }
  $("auth-submit").disabled = true;
  try {
    const res = await api(`/api/auth/${state.authMode}`, { method: "POST", body: { username, password } });
    state.token = res.token;
    state.username = res.username;
    state.profile = res.profile;
    state.targets = res.targets;
    store("coachgpt_token", res.token);
    $("auth-password").value = "";
    setError("auth-error", "");
    state.profile ? enterApp() : openProfileForm(false);
  } catch (err) {
    setError("auth-error", err.message);
  } finally {
    $("auth-submit").disabled = false;
  }
});

async function logout(callServer = true) {
  if (callServer && state.token) { try { await api("/api/auth/logout", { method: "POST" }); } catch (_) {} }
  state.token = state.username = state.profile = state.targets = state.progress = null;
  state.chatHistory = [];
  store("coachgpt_token", null);
  $("chat-window").innerHTML = "";
  $("meal-plan-output").innerHTML = "";
  setAuthMode("login");
  showScreen("auth");
}
$("logout").addEventListener("click", () => logout(true));

// ---------------------------------------------------------------------
// Profile form
// ---------------------------------------------------------------------
document.querySelectorAll(".pill-select").forEach((group) => {
  group.addEventListener("click", (e) => {
    const btn = e.target.closest(".pill");
    if (!btn) return;
    group.querySelectorAll(".pill").forEach((p) => p.classList.remove("selected"));
    btn.classList.add("selected");
  });
});
const getPill = (name) => {
  const sel = document.querySelector(`.pill-select[data-name="${name}"] .pill.selected`);
  return sel ? sel.dataset.value : null;
};
const setPill = (name, value) => {
  document.querySelectorAll(`.pill-select[data-name="${name}"] .pill`)
    .forEach((p) => p.classList.toggle("selected", p.dataset.value === value));
};

function openProfileForm(editing) {
  state.hadProfile = editing;
  const p = state.profile || {};
  ["goal", "diet", "experience", "equipment"].forEach((k) => setPill(k, p[k] || null));
  $("p-height").value = p.height_cm ?? "";
  $("p-weight").value = p.current_weight_kg ?? "";
  $("p-goal-weight").value = p.goal_weight_kg ?? "";
  $("p-budget").value = p.daily_budget ?? "";
  $("p-calories").value = p.daily_calorie_target ?? "";
  $("profile-title").textContent = editing ? "Edit your profile" : "Set up your coach";
  $("profile-sub").textContent = editing
    ? "Update your details and your targets will be recalculated."
    : "A few details so every plan is built for your body, diet and budget. For adults (18+).";
  $("profile-submit").textContent = editing ? "Save changes" : "Start coaching \u2192";
  $("profile-cancel").classList.toggle("hidden", !editing);
  setError("profile-error", "");
  showScreen("profile");
}
["input", "click"].forEach((evt) =>
  $("profile-form").addEventListener(evt, () => setError("profile-error", "")));
$("edit-profile").addEventListener("click", () => openProfileForm(true));
$("profile-cancel").addEventListener("click", () => showScreen("app"));

$("profile-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = {
    goal: getPill("goal"), diet: getPill("diet"),
    experience: getPill("experience"), equipment: getPill("equipment"),
    height_cm: parseFloat($("p-height").value),
    current_weight_kg: parseFloat($("p-weight").value),
    goal_weight_kg: parseFloat($("p-goal-weight").value),
    daily_budget: parseFloat($("p-budget").value),
    daily_calorie_target: $("p-calories").value ? parseInt($("p-calories").value, 10) : null,
  };
  if (!body.goal || !body.diet || !body.experience || !body.equipment)
    return setError("profile-error", "Please choose an option for goal, diet, experience and equipment.");
  const checks = [
    [body.height_cm, 120, 230, "Height should be between 120 and 230 cm."],
    [body.current_weight_kg, 35, 250, "Current weight should be between 35 and 250 kg."],
    [body.goal_weight_kg, 35, 250, "Goal weight should be between 35 and 250 kg."],
    [body.daily_budget, 40, 20000, `Daily budget should be between ${CUR}40 and ${CUR}20,000.`],
  ];
  for (const [v, lo, hi, msg] of checks) if (!(v >= lo && v <= hi)) return setError("profile-error", msg);
  if (body.goal === "weight_loss" && body.goal_weight_kg >= body.current_weight_kg)
    return setError("profile-error", "For weight loss, your goal weight must be lower than your current weight.");
  if (body.goal === "weight_gain" && body.goal_weight_kg <= body.current_weight_kg)
    return setError("profile-error", "For weight gain, your goal weight must be higher than your current weight.");

  $("profile-submit").disabled = true;
  try {
    const res = await api("/api/profile", { method: "PUT", body });
    state.profile = res.profile;
    state.targets = res.targets;
    enterApp(state.hadProfile);
  } catch (err) {
    setError("profile-error", err.message);
  } finally {
    $("profile-submit").disabled = false;
  }
});

// ---------------------------------------------------------------------
// Entering the app
// ---------------------------------------------------------------------
function renderSidebar() {
  $("user-name").textContent = state.username || "";
  const p = state.profile;
  $("profile-summary").innerHTML = p
    ? `${LABELS[p.goal]}<br>${LABELS[p.diet]} \u00b7 ${LABELS[p.experience]}`
    : "";
}

function renderTargets() {
  const t = state.targets, p = state.profile;
  if (!t || !p) { $("target-strip").innerHTML = ""; return; }
  $("target-strip").innerHTML = `
    <div class="target-chip"><div class="tc-label">Calories</div>
      <div class="tc-value">${num(t.calories)} kcal</div><div class="tc-sub">${esc(t.calorie_source)}</div></div>
    <div class="target-chip accent"><div class="tc-label">Protein</div>
      <div class="tc-value">${num(t.protein_g)} g</div><div class="tc-sub">range ${t.protein_low_g}\u2013${t.protein_high_g} g</div></div>
    <div class="target-chip"><div class="tc-label">Water</div>
      <div class="tc-value">${t.water_litres} L</div><div class="tc-sub">through the day</div></div>
    <div class="target-chip"><div class="tc-label">Budget</div>
      <div class="tc-value">${CUR}${num(p.daily_budget)}</div><div class="tc-sub">per day</div></div>`;
}

function resetChat() {
  const t = state.targets, p = state.profile;
  state.chatHistory = [];
  $("chat-window").innerHTML = "";
  let welcome = `Hi ${state.username}! I've set things up for ${LABELS[p.goal].toLowerCase()} on ` +
    `${withArticle(LABELS[p.diet].toLowerCase())} diet. Your targets are about ${num(t.calories)} kcal and ` +
    `${t.protein_g} g of protein a day`;
  if (t.weeks_to_goal) {
    welcome += `, and at a steady pace of roughly ${t.weekly_rate_kg} kg a week you could reach ` +
      `${p.goal_weight_kg} kg in around ${t.weeks_to_goal} weeks`;
  }
  welcome += `. Ask me for a workout, a form check, cheap protein ideas, or a pep talk.`;
  appendMessage("assistant", welcome);
}

function enterApp(keepChat = false) {
  showScreen("app");
  renderSidebar();
  renderTargets();
  if (!keepChat || !$("chat-window").children.length) resetChat();
  $("meal-diet").value = state.profile.diet;
  $("meal-goal").value = state.profile.goal;
  $("meal-budget").value = state.profile.daily_budget;
  loadProgress();
}

// ---------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------
document.querySelectorAll(".nav-item").forEach((item) => {
  item.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((i) => i.classList.remove("active"));
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    item.classList.add("active");
    $(`view-${item.dataset.view}`).classList.add("active");
  });
});

// ---------------------------------------------------------------------
// Chat (streamed)
// ---------------------------------------------------------------------
function appendMessage(role, text) {
  const msg = document.createElement("div");
  msg.className = `msg msg-${role}`;
  msg.innerHTML = `<div class="avatar">${role === "user" ? "You" : "CG"}</div><div class="bubble"></div>`;
  const bubble = msg.querySelector(".bubble");
  role === "user" ? (bubble.textContent = text) : (bubble.innerHTML = renderChatText(text));
  $("chat-window").appendChild(msg);
  $("chat-window").scrollTop = $("chat-window").scrollHeight;
  return bubble;
}

$("chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("chat-input").value.trim();
  if (!text) return;
  appendMessage("user", text);
  state.chatHistory.push({ role: "user", content: text });
  $("chat-input").value = "";
  const bubble = appendMessage("assistant", "");
  $("chat-send").disabled = true;

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${state.token}` },
      body: JSON.stringify({ messages: state.chatHistory.slice(-30) }),
    });
    if (res.status === 401) { await logout(false); return; }
    if (!res.ok) {
      let detail = "The coach couldn't answer right now.";
      try { detail = (await res.json()).detail || detail; } catch (_) {}
      bubble.textContent = `\u26a0\ufe0f ${detail}`;
      state.chatHistory.pop();
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let full = "", buffer = "", failed = false;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop();
      for (const part of parts) {
        if (!part.startsWith("data: ")) continue;
        const evt = JSON.parse(part.slice(6));
        if (evt.delta) {
          full += evt.delta;
          bubble.innerHTML = renderChatText(full);
          $("chat-window").scrollTop = $("chat-window").scrollHeight;
        } else if (evt.error) {
          failed = true;
          bubble.textContent = `\u26a0\ufe0f ${evt.error}`;
        }
      }
    }
    if (failed) state.chatHistory.pop();
    else state.chatHistory.push({ role: "assistant", content: full });
    $("conn-status").style.background = failed ? "var(--ember)" : "var(--mint)";
  } catch (_) {
    bubble.textContent = "\u26a0\ufe0f Couldn't reach the server. Is the backend running?";
    state.chatHistory.pop();
    $("conn-status").style.background = "var(--ember)";
  } finally {
    $("chat-send").disabled = false;
  }
});

// ---------------------------------------------------------------------
// Meal planner
// ---------------------------------------------------------------------
$("generate-meal-plan").addEventListener("click", async () => {
  const out = $("meal-plan-output");
  const budget = parseFloat($("meal-budget").value);
  if (!(budget >= 40 && budget <= 20000)) {
    out.innerHTML = `<p class="warn-card">Please enter a daily budget between ${CUR}40 and ${CUR}20,000.</p>`;
    return;
  }
  out.innerHTML = `<p class="muted">Building your plan\u2026</p>`;
  $("generate-meal-plan").disabled = true;
  try {
    const plan = await api("/api/meal-plan", {
      method: "POST",
      body: { diet: $("meal-diet").value, goal: $("meal-goal").value, daily_budget: budget },
    });
    renderMealPlan(plan);
  } catch (err) {
    out.innerHTML = `<p class="warn-card">\u26a0\ufe0f ${esc(err.message)}</p>`;
  } finally {
    $("generate-meal-plan").disabled = false;
  }
});

function renderMealPlan(plan) {
  const budgetBadge = plan.within_budget
    ? `<span class="badge good">Within ${CUR}${num(plan.budget)} budget</span>`
    : `<span class="badge warn">Over ${CUR}${num(plan.budget)} budget</span>`;
  const proteinBadge = plan.protein_met
    ? `<span class="badge good">Protein target met</span>`
    : `<span class="badge warn">Below protein target</span>`;

  $("meal-plan-output").innerHTML = `
    <div class="meal-summary">
      <span class="sum-main"><strong>${num(plan.calories_total)} kcal</strong> (target ${num(plan.calorie_target)})
        \u00b7 <strong>${plan.protein_total_g} g protein</strong> (target ${plan.protein_target_g} g)
        \u00b7 <strong>${CUR}${num(plan.cost_total)}</strong></span>
      <span class="badges">${budgetBadge}${proteinBadge}</span>
    </div>
    ${plan.meals.map((m) => `
      <div class="meal-card">
        <h4>${esc(m.name)}</h4>
        <ul>${m.items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>
        <div class="meal-meta">
          <span>${m.calories} kcal \u00b7 ${m.protein_g} g protein</span>
          <span class="meal-cost">${CUR}${m.cost}</span>
        </div>
      </div>`).join("")}
    ${plan.warnings.map((w) => `<div class="warn-card">${esc(w)}</div>`).join("")}
    <div class="note-card">
      <h4>Coach's note${plan.note_source === "ai" ? " (AI-written)" : ""}</h4>
      ${esc(plan.coach_note)}
      <div class="muted" style="margin-top:8px">Hydration: ${esc(plan.hydration_tip)} Aim for about ${plan.water_litres} L.</div>
    </div>
    <p class="plan-footnote">${esc(plan.cost_note)}</p>`;
}

// ---------------------------------------------------------------------
// Daily progress
// ---------------------------------------------------------------------
const CIRCUMFERENCE = 377; // 2 * PI * 60
function updateRing(pct) {
  $("ring-fill").style.strokeDashoffset = CIRCUMFERENCE - (CIRCUMFERENCE * pct) / 100;
  $("ring-percent").textContent = `${pct}%`;
  $("ring-fill").style.stroke = pct >= 100 ? "var(--mint)" : "var(--ember)";
}
$("progress-slider").addEventListener("input", () => updateRing(parseInt($("progress-slider").value, 10)));
$("workout-done").addEventListener("change", () =>
  $("workout-details").classList.toggle("hidden", !$("workout-done").checked));

function fillLogForm(dateStr) {
  const entry = (state.progress?.entries || []).find((e) => e.date === dateStr);
  const latest = state.progress?.summary?.latest_weight_kg;
  $("log-weight").value = entry?.weight_kg ?? "";
  $("log-weight").placeholder = latest ? `e.g. ${latest}` : "";
  $("log-protein").value = entry?.protein_g ?? "";
  $("log-water").value = entry?.water_glasses ?? "";
  $("progress-slider").value = entry?.goal_percent_complete ?? 0;
  updateRing(entry?.goal_percent_complete ?? 0);
  $("workout-done").checked = !!entry?.workout_done;
  $("workout-details").classList.toggle("hidden", !entry?.workout_done);
  $("workout-type").value = entry?.workout_type || "strength";
  $("workout-minutes").value = entry?.workout_minutes ?? "";
  $("meal-followed").checked = !!entry?.meal_plan_followed;
  $("mood-note").value = entry?.mood_note || "";
  $("save-progress").textContent = entry ? "Update this day" : "Save this day";
}

$("log-date").max = todayStr();
$("log-date").value = todayStr();
$("log-date").addEventListener("change", () => {
  if (!$("log-date").value) $("log-date").value = todayStr();
  fillLogForm($("log-date").value);
  $("save-confirm").textContent = "";
});

async function loadProgress() {
  try {
    const res = await api("/api/progress");
    applyProgress(res, true);
  } catch (err) {
    console.error(err);
  }
}

function applyProgress(res, refillForm) {
  state.progress = res;
  if (res.profile) state.profile = res.profile;
  if (res.targets) state.targets = res.targets;
  renderSidebar();
  renderTargets();
  renderGoalCard();
  renderWeightChart();
  renderHistory();
  if (refillForm) fillLogForm($("log-date").value || todayStr());
}

function renderGoalCard() {
  const s = state.progress?.summary, p = state.profile, t = state.targets;
  if (!s || !p || !t) return;
  const change = s.weight_change_kg;
  const sign = change > 0 ? "+" : change < 0 ? "\u2212" : "";
  const changeText = `${sign}${Math.abs(change)} kg since you started`;
  let bar = "";
  let remaining = "";
  if (s.percent_to_goal !== null) {
    bar = `<div class="goal-bar"><span style="width:${s.percent_to_goal}%"></span></div>
      <div class="goal-labels"><span>Start ${s.start_weight_kg} kg</span>
      <span>${s.percent_to_goal}% of the way</span><span>Goal ${s.goal_weight_kg} kg</span></div>`;
    remaining = t.weeks_to_goal
      ? `At a steady pace (~${t.weekly_rate_kg} kg/week), roughly ${t.weeks_to_goal} weeks to go.`
      : "You've reached your goal weight \u2014 time to maintain it!";
  } else {
    remaining = `Maintenance goal: stay around ${s.goal_weight_kg} kg.`;
  }
  $("goal-card").innerHTML = `
    <h3>Goal progress</h3>
    <div class="goal-headline">${s.latest_weight_kg} kg <small>${changeText}</small></div>
    ${bar}
    <p class="muted" style="margin-top:10px">${esc(remaining)}
      BMI ${t.bmi} (${esc(t.bmi_category)}).</p>
    <div class="stat-row">
      <div class="stat"><div class="s-value">${s.streak_days}</div><div class="s-label">day streak</div></div>
      <div class="stat"><div class="s-value">${s.workouts_logged}</div><div class="s-label">workouts logged</div></div>
      <div class="stat"><div class="s-value">${s.avg_plan_percent_7d === null ? "\u2013" : s.avg_plan_percent_7d + "%"}</div>
        <div class="s-label">avg plan done (7 days)</div></div>
    </div>`;
}

function renderWeightChart() {
  const holder = $("weight-chart");
  const entries = (state.progress?.entries || []).filter((e) => e.weight_kg).slice().reverse();
  if (entries.length < 2) {
    holder.innerHTML = `<p class="muted">Log your weight on at least two different days to see your trend.</p>`;
    return;
  }
  const goal = state.profile.goal_weight_kg;
  const W = 460, H = 190, L = 42, R = 14, T = 14, B = 30;
  const times = entries.map((e) => { const [y, m, d] = e.date.split("-").map(Number); return new Date(y, m - 1, d).getTime(); });
  const ws = entries.map((e) => e.weight_kg);
  const lo = Math.min(...ws, goal) - 1, hi = Math.max(...ws, goal) + 1;
  const t0 = times[0], t1 = times[times.length - 1] || t0 + 1;
  const x = (t) => L + ((t - t0) / Math.max(t1 - t0, 1)) * (W - L - R);
  const y = (w) => T + (1 - (w - lo) / (hi - lo)) * (H - T - B);
  const pts = entries.map((e, i) => [x(times[i]), y(e.weight_kg)]);
  const grid = [0, 0.5, 1].map((f) => {
    const w = lo + f * (hi - lo), yy = y(w);
    return `<line class="grid" x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}"/>
            <text class="axis-label" x="${L - 6}" y="${yy + 3}" text-anchor="end">${w.toFixed(1)}</text>`;
  }).join("");
  holder.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Weight over time">
      ${grid}
      <line class="goal-line" x1="${L}" x2="${W - R}" y1="${y(goal)}" y2="${y(goal)}"/>
      <text class="goal-label" x="${W - R}" y="${y(goal) - 5}" text-anchor="end">Goal ${goal} kg</text>
      <polyline class="w-line" points="${pts.map((p) => p.join(",")).join(" ")}"/>
      ${pts.map((p) => `<circle class="w-dot" cx="${p[0]}" cy="${p[1]}" r="3.5"/>`).join("")}
      <text class="axis-label" x="${L}" y="${H - 8}">${fmtDate(entries[0].date)}</text>
      <text class="axis-label" x="${W - R}" y="${H - 8}" text-anchor="end">${fmtDate(entries[entries.length - 1].date)}</text>
    </svg>`;
}

function renderHistory() {
  const list = $("history-list");
  const entries = state.progress?.entries || [];
  if (!entries.length) {
    list.innerHTML = `<li class="muted">No entries yet \u2014 log today to start your streak.</li>`;
    return;
  }
  list.innerHTML = entries.slice(0, 14).map((e) => {
    const workout = e.workout_done
      ? `${WORKOUT_LABELS[e.workout_type] || "Workout"}${e.workout_minutes ? ` \u00b7 ${e.workout_minutes} min` : ""}`
      : "No workout";
    const bits = [workout];
    if (e.protein_g !== null && e.protein_g !== undefined) bits.push(`${e.protein_g} g protein`);
    if (e.water_glasses !== null && e.water_glasses !== undefined) bits.push(`${e.water_glasses} glasses water`);
    return `<li>
      <span class="hist-main"><span>${fmtDate(e.date)}${e.weight_kg ? ` \u00b7 ${e.weight_kg} kg` : ""}</span>
        <span class="hist-sub">${esc(bits.join(" \u00b7 "))}</span></span>
      <span class="hist-right hist-pct">${e.goal_percent_complete}%</span></li>`;
  }).join("");
}

function intOrNull(id) { const v = $(id).value; return v === "" ? null : parseInt(v, 10); }

$("save-progress").addEventListener("click", async () => {
  const weight = $("log-weight").value === "" ? null : parseFloat($("log-weight").value);
  if (weight !== null && !(weight >= 35 && weight <= 250))
    return setError("progress-error", "Weight should be between 35 and 250 kg.");
  const done = $("workout-done").checked;
  const body = {
    entry_date: $("log-date").value || todayStr(),
    weight_kg: weight,
    goal_percent_complete: parseInt($("progress-slider").value, 10),
    workout_done: done,
    workout_type: done ? $("workout-type").value : null,
    workout_minutes: done ? intOrNull("workout-minutes") : null,
    protein_g: intOrNull("log-protein"),
    water_glasses: intOrNull("log-water"),
    meal_plan_followed: $("meal-followed").checked,
    mood_note: $("mood-note").value.trim() || null,
  };
  setError("progress-error", "");
  $("save-progress").disabled = true;
  try {
    const res = await api("/api/progress", { method: "POST", body });
    applyProgress(res, false);
    $("save-progress").textContent = "Update this day";
    $("save-confirm").textContent = `Saved for ${fmtDate(res.date)} \u2713`;
  } catch (err) {
    setError("progress-error", err.message);
    $("save-confirm").textContent = "";
  } finally {
    $("save-progress").disabled = false;
  }
});

// ---------------------------------------------------------------------
// Start-up: resume a saved session if there is one
// ---------------------------------------------------------------------
(async function init() {
  setAuthMode("login");
  state.token = load("coachgpt_token");
  if (!state.token) return showScreen("auth");
  try {
    const me = await api("/api/me");
    state.username = me.username;
    state.profile = me.profile;
    state.targets = me.targets;
    me.profile ? enterApp() : openProfileForm(false);
  } catch (_) {
    showScreen("auth");
  }
})();
