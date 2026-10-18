const $ = (s) => document.querySelector(s);
const STORE_KEY = "voiceclone.profile";
let voice = null; // { profile, traits, signature_phrases }
let sampleAI = "";

function store(v) {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(v)); } catch (_) {}
}
function restore() {
  try { return JSON.parse(localStorage.getItem(STORE_KEY)); } catch (_) { return null; }
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add("hidden"), 4000);
}

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `Request failed (${r.status})`);
  return data;
}

async function busy(btn, label, fn) {
  const old = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span>${label}`;
  try { return await fn(); }
  catch (e) { toast(e.message); }
  finally { btn.disabled = false; btn.innerHTML = old; }
}

function esc(s) {
  return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function highlight(text, flags) {
  let out = "", pos = 0;
  for (const f of flags) {
    if (f.start < pos) continue;
    out += esc(text.slice(pos, f.start));
    out += `<mark title="${esc(f.label)}">${esc(text.slice(f.start, f.end))}</mark>`;
    pos = f.end;
  }
  return out + esc(text.slice(pos));
}

function color(v, goodHigh) {
  const good = goodHigh ? v >= 70 : v <= 20;
  const ok = goodHigh ? v >= 45 : v <= 45;
  return good ? "var(--good)" : ok ? "var(--warn)" : "var(--bad)";
}

function gauge(label, v, goodHigh) {
  const c = color(v, goodHigh);
  return `<div class="gauge">
    <svg viewBox="0 0 52 52" aria-hidden="true"><circle class="track" cx="26" cy="26" r="21"/>
      <circle class="arc" cx="26" cy="26" r="21" pathLength="100" style="stroke:${c};--v:${Math.max(v, 1)}"/></svg>
    <div><div class="g-val" style="color:${c}">${v}<span>/100</span></div><div class="g-label">${label}</div></div>
  </div>`;
}

function meters(d) {
  return `<div class="scores">${gauge("Sounds like you", d.voice_match, true)}${gauge("AI slop", d.slop, false)}</div>`;
}

function skeleton(n) {
  return Array.from({ length: n }, () => '<div class="card"><div class="skeleton"><i></i><i></i><i></i></div></div>').join("");
}

function flagList(flags) {
  const labels = [...new Set(flags.map((f) => f.label))];
  return labels.length ? `<ul class="flags">${labels.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>` : "";
}

function setVoice(v) {
  voice = v;
  store(v);
  $("#profile-empty").classList.add("hidden");
  $("#profile-body").classList.remove("hidden");
  $("#profile-name").textContent = `${v.profile.name} · ${v.profile.n_posts} posts`;
  $("#traits").innerHTML = v.traits.map((t) => `<li>${esc(t)}</li>`).join("");
  $("#phrases").innerHTML = (v.signature_phrases.length ? v.signature_phrases : ["(add more posts to find these)"])
    .map((p) => `<span class="chip">${esc(p)}</span>`).join("");
  const pill = $("#voice-pill");
  pill.textContent = `Voice: ${v.profile.name}`;
  pill.classList.remove("hidden");
}

function needVoice() {
  if (!voice) { toast("Teach a voice first, or try the demo voice."); switchTab("teach"); return true; }
  return false;
}

const TABS = ["teach", "write", "check"];
function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === name));
  $(".seg-thumb").style.transform = `translateX(${TABS.indexOf(name) * 100}%)`;
}

// Appearance: light (default), dark, or follow the system.
const THEME_KEY = "voiceclone.theme";
const darkQuery = matchMedia("(prefers-color-scheme: dark)");
function applyTheme(pref) {
  const dark = pref === "dark" || (pref === "system" && darkQuery.matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.documentElement.dataset.themePref = pref;
  document.querySelector('meta[name="theme-color"]').content = dark ? "#000000" : "#f5f5f7";
  document.querySelectorAll("[data-theme-set]").forEach((b) => b.setAttribute("aria-checked", b.dataset.themeSet === pref));
}
document.querySelectorAll("[data-theme-set]").forEach((b) => b.addEventListener("click", () => {
  try { localStorage.setItem(THEME_KEY, b.dataset.themeSet); } catch (_) {}
  applyTheme(b.dataset.themeSet);
}));
darkQuery.addEventListener("change", () => {
  if (document.documentElement.dataset.themePref === "system") applyTheme("system");
});
applyTheme(document.documentElement.dataset.themePref || "light");
document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => switchTab(t.dataset.tab)));

$("#learn").addEventListener("click", (e) => busy(e.currentTarget, "Learning…", async () => {
  const v = await api("/api/profile", { text: $("#posts").value, name: $("#voice-name").value || "My voice" });
  setVoice(v);
  toast("Voice learned. Head to Write.");
}));

async function loadDemo(e) { return busy(e.currentTarget, "Loading…", async () => {
  const d = await api("/api/demo");
  sampleAI = d.sample_ai_text;
  $("#posts").value = d.profile.posts.join("\n---\n");
  $("#voice-name").value = d.profile.name;
  setVoice(d);
  toast("Demo voice loaded: a lowercase, short-sentence indie maker.");
}); }
$("#demo").addEventListener("click", loadDemo);
$("#hero-demo").addEventListener("click", async (e) => {
  await loadDemo(e);
  switchTab("teach");
  $("#app").scrollIntoView({ behavior: "smooth" });
});

$("#file").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (f) $("#posts").value = await f.text();
});

$("#export").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify(voice)], { type: "application/json" });
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: "voice.json" });
  a.click();
});
$("#import").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  try { setVoice(JSON.parse(await f.text())); toast("Voice imported."); }
  catch (_) { toast("That file isn't a VoiceClone voice."); }
});

function draftCard(d, i) {
  return `<div class="card draft${i === 0 ? " best" : ""}">
    ${i === 0 ? '<span class="badge">★ Best match</span>' : ""}
    <p class="text">${highlight(d.text, d.flags)}</p>
    ${meters(d)}
    ${flagList(d.flags)}
    <div class="actions">
      <button class="ghost small" data-copy="${i}">Copy</button>
      ${d.flags.length ? `<button class="ghost small" data-fix="${i}">Fix flagged parts</button>` : ""}
    </div>
  </div>`;
}

let lastDrafts = [];
function renderDrafts(res) {
  lastDrafts = res.drafts;
  $("#drafts").innerHTML = res.drafts.map(draftCard).join("") +
    `<p class="hint">Written by ${esc(res.model)}. Drafts are ranked by voice match minus slop.</p>`;
}

$("#generate").addEventListener("click", (e) => {
  if (needVoice()) return;
  if (!$("#topic").value.trim()) { toast("Add a topic first."); return; }
  const prev = $("#drafts").innerHTML;
  $("#drafts").innerHTML = skeleton(2);
  busy(e.currentTarget, "Writing and scoring drafts…", async () => {
    try {
      renderDrafts(await api("/api/generate", {
        profile: voice.profile, topic: $("#topic").value, format: $("#format").value, notes: $("#notes").value,
      }));
    } catch (err) { $("#drafts").innerHTML = prev; throw err; }
  });
});

$("#drafts").addEventListener("click", async (e) => {
  const copy = e.target.dataset.copy, fix = e.target.dataset.fix;
  if (copy !== undefined) {
    await navigator.clipboard.writeText(lastDrafts[copy].text);
    toast("Copied.");
  } else if (fix !== undefined) {
    busy(e.target, "Fixing…", async () => {
      const r = await api("/api/humanize", { profile: voice.profile, text: lastDrafts[fix].text });
      lastDrafts[fix] = r.after;
      lastDrafts.sort((a, b) => b.rank_score - a.rank_score);
      renderDrafts({ drafts: lastDrafts, model: r.model });
    });
  }
});

function scoreCard(title, d) {
  return `<div class="card"><h3>${title}</h3><p class="text" style="white-space:pre-wrap">${highlight(d.text, d.flags)}</p>${meters(d)}${flagList(d.flags)}</div>`;
}

$("#score-btn").addEventListener("click", (e) => {
  if (needVoice()) return;
  const text = $("#check-text").value;
  if (!text.trim()) { toast("Paste some text first."); return; }
  busy(e.currentTarget, "Scoring…", async () => {
    const r = await api("/api/score", { profile: voice.profile, text });
    $("#check-out").innerHTML = scoreCard("Your text", { text, ...r });
  });
});

$("#humanize-btn").addEventListener("click", (e) => {
  if (needVoice()) return;
  const text = $("#check-text").value;
  if (!text.trim()) { toast("Paste some text first."); return; }
  busy(e.currentTarget, "Rewriting in your voice…", async () => {
    const r = await api("/api/humanize", { profile: voice.profile, text });
    $("#check-out").innerHTML = `<div class="compare">${scoreCard("Before", r.before)}${scoreCard("After, in your voice", r.after)}</div>`;
  });
});

$("#sample-btn").addEventListener("click", async () => {
  if (!sampleAI) sampleAI = (await api("/api/demo")).sample_ai_text;
  $("#check-text").value = sampleAI;
});

(async function init() {
  const saved = restore();
  if (saved && saved.profile) setVoice(saved);
  try {
    const h = await api("/api/health");
    $("#model-info").textContent = `model: ${h.model}`;
  } catch (_) {}
})();
