// Script Bench front end: compose -> pick a direction -> edit the script.

const $ = (id) => document.getElementById(id);

const CHECK_GROUPS = [
  { label: "Length within ±10% of target", codes: ["too_long", "too_short"] },
  { label: "Hook: one sentence, ≤15 words, no greeting", codes: ["hook_too_long", "hook_multi_sentence", "hook_weak_opener"] },
  { label: "No clichés or filler", codes: ["banned_phrase"] },
  { label: "Every sentence sayable in one breath", codes: ["long_sentence"] },
  { label: "Spoken words only", codes: ["emoji", "hashtag", "stage_direction", "formatting"] },
  { label: "One short, clear CTA", codes: ["cta_missing", "cta_too_long"] },
  { label: "Numbered list matches the topic", codes: ["list_count"] },
];

const ISSUE_LABELS = {
  too_long: "length", too_short: "length", hook_too_long: "hook rules", hook_multi_sentence: "hook rules",
  hook_weak_opener: "hook rules", banned_phrase: "clichés", long_sentence: "long sentences", emoji: "unspeakable text",
  hashtag: "unspeakable text", stage_direction: "unspeakable text", formatting: "unspeakable text", cta_missing: "CTA",
  cta_too_long: "CTA", weak_hook: "hook strength", no_payoff: "payoff", weak_body: "body", off_tone: "tone", weak_cta: "CTA", list_count: "numbered list", unsupported_fact: "unsourced facts", niche_miss: "niche checks",
};
const labelsFor = (codes) => [...new Set(codes.map((c) => ISSUE_LABELS[c] || c))].join(", ");

const state = {
  brief: null,       // {niche, topic, target_seconds, tone}
  budget: null,      // from /api/directions
  directions: null,  // {directions, recommended_index, recommendation_reason}
  chosen: null,      // Direction
  facts: [],         // researched facts with sources, shared by every script for this topic
  jobs: {},          // direction index -> Promise<job id>; the ★ one starts before it's picked
  stream: null,      // open EventSource
};

// ---------- helpers ----------

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// Mirrors engine/checks.py paragraphs(): one beat per paragraph, each "Number N" item on its own line.
const ITEM_START = /(?<=[.!?])\s+(?=Number\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b)/i;
function scriptParagraphs(text) {
  return text.trim().split(/\n\s*\n/).flatMap((block) => block.replace(/\n/g, " ").split(ITEM_START)).map((p) => p.trim()).filter(Boolean);
}
const asScriptText = (text) => scriptParagraphs(text).join("\n\n");
const timecode = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

function countWords(text) {
  // Mirrors engine/checks.py count_words: whitespace tokens containing a letter or digit.
  return text.split(/\s+/).filter((t) => /[\p{L}\p{N}]/u.test(t)).length;
}

async function api(path, body) {
  const res = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join("; ") : data.detail;
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return data;
}

function show(section) {
  for (const id of ["directions", "editor", "samples"]) $(id).hidden = id !== section;
  $("compose").hidden = section === "editor" || section === "samples";
  document.body.classList.toggle("compact", section !== null);
  $("new-btn").hidden = section === null;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function toast(message) {
  const t = $("toast");
  t.textContent = message;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), 1800);
}

function autosize(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = textarea.scrollHeight + "px";
}

// ---------- dropdown ----------

// A small accessible listbox: button + popover, keyboard-driven (arrows, Enter, Esc, type-ahead).
class Dropdown {
  constructor(root, { label, options, value, onChange }) {
    this.root = root;
    this.options = options; // [{value, label, hint?}]
    this.onChange = onChange;
    this.active = 0;

    this.button = el("button", "dd-btn");
    this.button.type = "button";
    this.button.setAttribute("aria-haspopup", "listbox");
    this.button.setAttribute("aria-expanded", "false");
    this.valueEl = el("b");
    this.button.append(el("small", "", label), this.valueEl, el("span", "dd-chev"));

    this.list = el("ul", "dd-list");
    this.list.setAttribute("role", "listbox");
    this.list.setAttribute("aria-label", label);
    this.list.tabIndex = -1;
    this.list.hidden = true;
    this.items = options.map((opt, i) => {
      const li = el("li", "dd-item");
      li.setAttribute("role", "option");
      li.append(el("span", "dd-label", opt.label));
      if (opt.hint) li.append(el("span", "dd-hint", opt.hint));
      li.addEventListener("mousemove", () => this.highlight(i));
      li.addEventListener("click", () => this.choose(i));
      return li;
    });
    this.list.append(...this.items);
    root.append(this.button, this.list);

    this.button.addEventListener("click", () => (this.list.hidden ? this.open() : this.close()));
    this.button.addEventListener("keydown", (e) => {
      if (["ArrowDown", "ArrowUp"].includes(e.key)) { e.preventDefault(); this.open(); }
    });
    this.list.addEventListener("keydown", (e) => this.onKey(e));
    document.addEventListener("mousedown", (e) => { if (!root.contains(e.target)) this.close(); });

    this.set(value, false);
  }

  get value() { return this.options[this.selected].value; }

  set(value, notify = true) {
    this.selected = Math.max(0, this.options.findIndex((o) => o.value === value));
    this.valueEl.textContent = this.options[this.selected].label;
    this.items.forEach((li, i) => li.setAttribute("aria-selected", String(i === this.selected)));
    if (notify && this.onChange) this.onChange(this.value);
  }

  open() {
    Dropdown.openOne?.close();
    Dropdown.openOne = this;
    this.list.hidden = false;
    this.button.setAttribute("aria-expanded", "true");
    this.highlight(this.selected);
    this.list.focus();
  }

  close(focusButton = false) {
    if (this.list.hidden) return;
    this.list.hidden = true;
    this.button.setAttribute("aria-expanded", "false");
    if (Dropdown.openOne === this) Dropdown.openOne = null;
    if (focusButton) this.button.focus();
  }

  highlight(i) {
    this.active = i;
    this.items.forEach((li, j) => li.classList.toggle("active", i === j));
    this.items[i].scrollIntoView({ block: "nearest" });
  }

  choose(i) {
    this.set(this.options[i].value);
    this.close(true);
  }

  onKey(e) {
    const n = this.items.length;
    if (e.key === "ArrowDown") this.highlight((this.active + 1) % n);
    else if (e.key === "ArrowUp") this.highlight((this.active - 1 + n) % n);
    else if (e.key === "Home") this.highlight(0);
    else if (e.key === "End") this.highlight(n - 1);
    else if (e.key === "Enter" || e.key === " ") this.choose(this.active);
    else if (e.key === "Escape") this.close(true);
    else if (e.key === "Tab") return this.close();
    else if (e.key.length === 1) {
      const i = this.options.findIndex((o) => o.label.toLowerCase().startsWith(e.key.toLowerCase()));
      if (i >= 0) this.highlight(i);
      return;
    } else return;
    e.preventDefault();
  }
}

// ---------- step 1: compose ----------

const dropdowns = {};
const capitalise = (s) => s[0].toUpperCase() + s.slice(1);

async function loadOptions() {
  const { lengths, niches, tones } = await api("/api/options");
  dropdowns.length = new Dropdown($("length-dd"), {
    label: "Length",
    options: lengths.map((l) => ({ value: l.value, label: `${l.value}s`, hint: `about ${l.words} words` })),
    value: 45,
  });
  dropdowns.niche = new Dropdown($("niche-dd"), {
    label: "Niche",
    options: niches.map((n) => ({ value: n, label: n })),
    value: niches[0],
  });
  dropdowns.tone = new Dropdown($("tone-dd"), {
    label: "Tone",
    options: tones.map((t) => ({ value: t.value, label: capitalise(t.value), hint: t.description.split(". ")[0].replace(/\.?$/, ".") })),
    value: "conversational",
  });
}

function readBrief() {
  return {
    niche: dropdowns.niche.value,
    topic: $("topic").value.trim(),
    target_seconds: dropdowns.length.value,
    tone: dropdowns.tone.value,
  };
}

$("topic").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    $("compose-form").requestSubmit();
  }
});

$("compose-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const brief = readBrief();
  if (brief.topic.length < 3) return $("topic").focus();
  findDirections(brief);
});

// ---------- step 2: directions ----------

function renderChips(brief) {
  $("query-topic").textContent = brief.topic;
  const chips = $("query-chips");
  chips.replaceChildren(
    el("span", "chip", `${brief.target_seconds}s`),
    el("span", "chip", brief.niche),
    el("span", "chip", brief.tone),
  );
}

function skeletonCards() {
  return [0, 1, 2].map(() => {
    const card = el("div", "card skeleton");
    card.append(el("div", "bar w40"), el("div", "bar w70"), el("div", "bar tall"), el("div", "bar"), el("div", "bar w70"));
    return card;
  });
}

function directionCard(direction, index, recommended) {
  const card = el("button", "card" + (recommended ? " rec" : ""));
  card.type = "button";
  if (recommended) card.append(el("span", "badge", "★ Recommended"));
  card.append(
    el("span", "kind", direction.kind),
    el("span", "format", direction.format),
    el("span", "hookline", `“${direction.hook}”`),
    el("span", "angle", direction.angle),
    el("span", "brief", direction.brief),
    el("span", "use", "Use this direction →"),
  );
  card.addEventListener("click", () => writeScript(index));
  return card;
}

async function findDirections(brief) {
  state.brief = brief;
  renderChips(brief);
  $("cards").replaceChildren(...skeletonCards());
  $("why").textContent = "";
  $("directions-sub").textContent = "Researching the topic and finding three different ways to make this video…";
  $("send-btn").disabled = $("retry-directions").disabled = true;
  show("directions");

  try {
    const data = await api("/api/directions", brief);
    state.budget = data.budget;
    state.directions = data;
    state.facts = data.facts || [];
    state.jobs = {};
    const order = [data.recommended_index, ...[0, 1, 2].filter((i) => i !== data.recommended_index)];
    $("cards").replaceChildren(...order.map((i) => directionCard(data.directions[i], i, i === data.recommended_index)));
    // Head start on the ★ script while the user reads the cards. (Writing all three
    // was faster for non-★ picks but tripled the cost of every session.)
    startJob(data.recommended_index).catch(() => {});
    const researched = state.facts.length ? ` Built on ${state.facts.length} sourced facts.` : "";
    $("directions-sub").textContent = `Pick the direction you want to film. Target: about ${data.budget.total} words.${researched}`;
    $("why").textContent = `Why ★: ${data.recommendation_reason}`;
  } catch (err) {
    $("cards").replaceChildren(el("div", "error", `Couldn't get directions: ${err.message}`));
    $("directions-sub").textContent = "";
  } finally {
    $("send-btn").disabled = $("retry-directions").disabled = false;
  }
}

$("retry-directions").addEventListener("click", () => state.brief && findDirections(state.brief));

// ---------- step 3: script + editor ----------

const editors = { hook: $("ed-hook"), body: $("ed-body"), cta: $("ed-cta") };

function startJob(index) {
  if (!state.jobs[index]) {
    const direction = state.directions.directions[index];
    state.jobs[index] = api("/api/jobs", { ...state.brief, direction, facts: state.facts }).then((d) => d.job_id);
    state.jobs[index].catch(() => delete state.jobs[index]);
  }
  return state.jobs[index];
}

function progressItem(kind, icon, text, detail) {
  const li = el("li", kind);
  li.append(el("span", "icon", icon), el("span", "", text));
  if (detail) li.append(el("small", "", detail));
  $("progress").append(li);
  return li;
}

const SCOPE_LABELS = { full: "the script", hook: "the hook", cta: "the CTA", "cta+hook": "the hook and CTA" };

function setImproving(title, detail) {
  $("improving").hidden = false;
  $("improving-title").textContent = title;
  $("improving-detail").textContent = detail || "";
}

// Show a draft as soon as it exists, read-only, while the pipeline keeps improving it.
function showPreview(event) {
  $("script-loading").hidden = true;
  $("editor-grid").hidden = false;
  $("doc-title").textContent = `${state.chosen.format} · ${state.brief.topic}`;
  $("doc-meta").textContent = `${state.brief.niche} · ${state.brief.tone} · ${state.brief.target_seconds}s · draft ${event.draft}`;
  for (const [part, box] of Object.entries(editors)) {
    box.value = part === "body" ? asScriptText(event.script[part]) : event.script[part];
    box.readOnly = true;
    autosize(box);
  }
  renderCounts();
  renderChecks(event.issues);
  renderSources();
  if (event.type === "draft_written") {
    setImproving(`Draft ${event.draft} is written. An editor is reading it…`, "Checking the hook, body, tone and CTA. Editing unlocks when it's done.");
  } else if (event.issues.length) {
    setImproving(`Draft ${event.draft} is ready. Improving it now…`, `Fixing ${labelsFor(event.issues.map((i) => i.code))}. Editing unlocks when it's done.`);
  } else {
    setImproving("Passed every check. Finishing up…");
  }
}

function onJobEvent(event) {
  const working = $("progress").querySelector("li.work:last-child");
  if (event.type === "draft_started" && event.draft > 1 && !$("editor-grid").hidden) {
    setImproving(`Rewriting ${SCOPE_LABELS[event.scope] || "the script"} (draft ${event.draft})…`, `Fixing ${labelsFor(event.fixing)}. Editing unlocks when it's done.`);
  }
  if ((event.type === "draft_written" || event.type === "draft_checked") && event.script) showPreview(event);
  if (event.type === "stalled" && !$("editor-grid").hidden) setImproving("Keeping the strongest draft…");
  if (event.type === "draft_started") {
    const text = event.draft === 1 ? "Writing the first draft" : `Rewriting: draft ${event.draft}`;
    progressItem("work", "…", text, event.fixing.length ? `Fixing ${labelsFor(event.fixing)}` : null);
  } else if (event.type === "draft_checked") {
    working?.remove();
    const r = event.review;
    const scores = r ? ` · hook ${r.hook_score} · body ${r.body_score} · tone ${r.tone_score} · CTA ${r.cta_score}` : "";
    const passed = event.issues.length === 0;
    progressItem(
      passed ? "ok" : "fix", passed ? "✓" : "!",
      `Draft ${event.draft}: ${event.words} words ≈ ${event.seconds}s${scores}`,
      passed ? "Passed every check" : `Needs work on ${labelsFor(event.issues.map((i) => i.code))}`,
    );
  } else if (event.type === "stalled") {
    progressItem("fix", "→", `${capitalise(labelsFor(event.codes))} isn't improving with rewrites`, "Keeping the strongest draft");
  }
}

async function writeScript(index) {
  state.chosen = state.directions.directions[index];
  state.stream?.close();
  show("editor");
  $("editor-grid").hidden = true;
  $("improving").hidden = true;
  $("copy-btn").hidden = true;
  $("script-error").hidden = true;
  $("progress").replaceChildren();
  $("script-loading").hidden = false;

  const fail = (message) => {
    state.stream?.close();
    $("script-loading").hidden = true;
    $("script-error").textContent = `Couldn't write the script: ${message}`;
    $("script-error").hidden = false;
  };

  let jobId;
  try {
    jobId = await startJob(index);
  } catch (err) {
    return fail(err.message);
  }
  if (state.chosen !== state.directions.directions[index]) return; // user moved on

  const stream = new EventSource(`/api/jobs/${jobId}/events`);
  state.stream = stream;
  // Every (re)connection replays the job from the start; skip what we've already handled.
  let handled = 0, seenThisConnection = 0;
  stream.onopen = () => (seenThisConnection = 0);
  stream.onmessage = (msg) => {
    if (++seenThisConnection <= handled) return;
    handled++;
    const event = JSON.parse(msg.data);
    if (event.type === "done") {
      stream.close();
      renderEditor(event.result);
    } else if (event.type === "error") {
      delete state.jobs[index];
      fail(event.message);
    } else {
      onJobEvent(event);
    }
  };
  stream.onerror = () => {
    if (stream.readyState === EventSource.CLOSED) fail("lost connection to the server");
  };
}

function renderEditor(data) {
  $("script-loading").hidden = true;
  $("editor-grid").hidden = false;
  $("doc-title").textContent = `${state.chosen.format} · ${state.brief.topic}`;
  const revised = data.drafts === 1 ? "passed first draft" : `revised ${data.drafts - 1}×`;
  $("doc-meta").textContent = `${state.brief.niche} · ${state.brief.tone} · ${state.brief.target_seconds}s · ${revised}`;
  $("copy-btn").hidden = false;
  $("improving").hidden = true;
  for (const [part, box] of Object.entries(editors)) {
    box.value = part === "body" ? asScriptText(data.script[part]) : data.script[part];
    box.readOnly = false;
    autosize(box);
  }
  renderCounts();
  renderChecks(data.issues);
  renderSources();
}

function renderSources() {
  $("sources-panel").hidden = state.facts.length === 0;
  $("sources").replaceChildren(...state.facts.map((f) => {
    const li = el("li", "", f.claim);
    const link = el("a", "", new URL(f.source_url).hostname.replace(/^www\./, ""));
    link.href = f.source_url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    li.append(link);
    return li;
  }));
}

function renderCounts() {
  const b = state.budget;
  const words = Object.fromEntries(Object.entries(editors).map(([k, box]) => [k, countWords(box.value)]));
  const total = words.hook + words.body + words.cta;
  const secs = (n) => (n / b.words_per_second).toFixed(1);
  const targets = { hook: b.hook_max, body: b.body, cta: b.cta };
  const labels = { hook: "max", body: "target", cta: "target" };

  let elapsed = 0;
  for (const part of Object.keys(editors)) {
    const duration = words[part] / b.words_per_second;
    $(`tc-${part}`).textContent = `${timecode(elapsed)}–${timecode(elapsed + duration)}`;
    elapsed += duration;
  }

  for (const part of Object.keys(editors)) {
    const over = part === "hook" && words.hook > b.hook_max;
    const counter = $(`count-${part}`);
    counter.replaceChildren(
      el("span", over ? "over" : "ok", String(words[part])),
      document.createTextNode(` / ${targets[part]} ${labels[part]} · ${secs(words[part])}s`),
    );
  }

  const inRange = total >= b.total_min && total <= b.total_max;
  const big = $("rt-seconds");
  big.className = "big" + (inRange ? "" : " off");
  big.replaceChildren(document.createTextNode(`${secs(total)}s `), el("small", "", `/ ${b.seconds}s`));

  const scale = b.total_max * 1.25;
  $("rt-fill").style.width = `${Math.min(total / scale, 1) * 100}%`;
  $("rt-band").style.left = `${(b.total_min / scale) * 100}%`;
  $("rt-band").style.width = `${((b.total_max - b.total_min) / scale) * 100}%`;
  $("rt-words").textContent = `${total} words`;
  $("rt-range").textContent = `target ${b.total_min}–${b.total_max}`;
  const [h, bo, c] = $("rt-split").children;
  h.style.flex = words.hook || 0.01;
  bo.style.flex = words.body || 0.01;
  c.style.flex = words.cta || 0.01;
}

function renderChecks(issues) {
  const list = $("checks");
  list.replaceChildren();
  for (const group of CHECK_GROUPS) {
    const failures = issues.filter((i) => group.codes.includes(i.code));
    const li = el("li", failures.length ? "fail" : "");
    li.append(el("span", "dot", failures.length ? "!" : "✓"), el("span", "", group.label));
    for (const f of failures) li.append(el("span", "msg", f.message));
    list.append(li);
  }
}


let checkTimer;
function onEdit(e) {
  autosize(e.target);
  renderCounts();
  clearTimeout(checkTimer);
  checkTimer = setTimeout(async () => {
    const script = Object.fromEntries(Object.entries(editors).map(([k, box]) => [k, box.value]));
    try {
      const data = await api("/api/check", { ...state.brief, script });
      renderChecks(data.issues);
    } catch { /* keep the last results; live checks are best-effort */ }
  }, 400);
}

for (const box of Object.values(editors)) box.addEventListener("input", onEdit);
window.addEventListener("resize", () => Object.values(editors).forEach(autosize));

$("back-btn").addEventListener("click", () => {
  state.stream?.close();
  state.chosen = null;
  show("directions");
});

$("copy-btn").addEventListener("click", async () => {
  const text = [editors.hook.value, editors.body.value, editors.cta.value].join("\n\n");
  try {
    await navigator.clipboard.writeText(text);
    toast("Script copied");
  } catch {
    toast("Couldn't access the clipboard");
  }
});

$("new-btn").addEventListener("click", () => {
  $("topic").value = "";
  show(null);
  $("compose").hidden = false;
  $("topic").focus();
});

// ---------- samples ----------

let samplesCache = null;
let returnTo = null; // the view to go back to from the samples page

async function openSamples() {
  returnTo = !$("editor").hidden ? "editor" : !$("directions").hidden ? "directions" : null;
  show("samples");
  $("sample-detail").hidden = true;
  $("sample-list").hidden = false;
  if (!samplesCache) {
    $("sample-list").replaceChildren(el("p", "subtle", "Loading samples…"));
    try {
      samplesCache = await api("/api/samples");
    } catch (err) {
      return $("sample-list").replaceChildren(el("div", "error", `Couldn't load samples: ${err.message}`));
    }
  }
  if (!samplesCache.length) {
    return $("sample-list").replaceChildren(el("p", "subtle", "No samples yet. Run python make_samples.py to generate them."));
  }
  $("sample-list").replaceChildren(...samplesCache.map((sample) => {
    const card = el("button", "sample-card");
    card.type = "button";
    const chips = el("div");
    chips.append(el("span", "chip", sample.input.niche), el("span", "chip", `${sample.input.target_seconds}s`), el("span", "chip", sample.input.tone));
    card.append(chips, el("span", "topic", sample.input.topic), el("span", "preview", `“${sample.output.hook}”`));
    card.addEventListener("click", () => showSample(sample));
    return card;
  }));
}

function panel(title, ...children) {
  const box = el("div", "panel");
  box.append(el("h3", "", title), ...children);
  return box;
}

function statLine(label, value) {
  const row = el("div", "stat-line");
  row.append(el("span", "", label), el("b", "", value));
  return row;
}

function showSample(sample) {
  const { input, output, stats, budget } = sample;
  const words = stats.words;
  const secs = (n) => `${(n / 2.5).toFixed(1)}s`;

  // Left: the prompt, the script, the directions and how it got there.
  const doc = el("div", "doc");
  doc.append(el("h2", "", input.topic));
  const prompt = el("dl", "prompt-box");
  for (const [k, v] of [["Niche", input.niche], ["Topic", input.topic], ["Length", `${input.target_seconds}s`], ["Tone", input.tone]]) {
    prompt.append(el("dt", "", k), el("dd", "", v));
  }
  doc.append(prompt);
  let elapsed = 0;
  for (const [part, label, target] of [["hook", "Hook", `/ ${budget.hook_max ?? 15} max`], ["body", "Body", `/ ${budget.body} target`], ["cta", "CTA", `/ ${budget.cta} target`]]) {
    const section = el("div", "section");
    const head = el("div", "section-head");
    const name = el("span", "section-name" + (part === "hook" ? " hook" : ""), label);
    const duration = words[part] / 2.5;
    name.append(el("span", "tc", `${timecode(elapsed)}–${timecode(elapsed + duration)}`));
    elapsed += duration;
    head.append(name, el("span", "count", `${words[part]} ${target} · ${secs(words[part])}`));
    const text = el("div", "static-text" + (part === "hook" ? " hook" : ""));
    for (const line of scriptParagraphs(output[part])) {
      const p = el("p", "script-line");
      const item = line.match(/^(Number\s+\S+?:)\s*(.*)$/i);
      if (item) p.append(el("b", "", item[1] + " "), document.createTextNode(item[2]));
      else p.textContent = line;
      text.append(p);
    }
    section.append(head, text);
    doc.append(section);
  }

  const dirs = el("div", "detail-section");
  dirs.append(el("h3", "", "Directions it considered"));
  const minis = el("div", "mini-cards");
  sample.directions.forEach((d, i) => {
    const card = el("div", "mini-card" + (i === sample.chosen_index ? " chosen" : ""));
    card.append(el("b", "", `${i === sample.chosen_index ? "★ " : ""}${d.kind} · ${d.format}`), el("p", "", `“${d.hook}”`), el("p", "", d.brief));
    minis.append(card);
  });
  dirs.append(minis, el("p", "why", `Why ★: ${sample.recommendation_reason}`));
  doc.append(dirs);

  const trail = el("div", "detail-section");
  trail.append(el("h3", "", "How it got here"));
  const list = el("ol", "trail");
  sample.drafts.forEach((d, i) => {
    const r = d.review;
    const li = el("li", d.issues.length ? "" : "pass");
    const scores = r ? ` · hook ${r.hook_score} · body ${r.body_score} · tone ${r.tone_score} · CTA ${r.cta_score}` : "";
    li.append(el("span", "", `Draft ${i + 1}${scores}`));
    li.append(el("small", "", d.issues.length ? d.issues.join(" ") : "Passed every check."));
    list.append(li);
  });
  trail.append(list);
  doc.append(trail);

  // Right: numbers, research sources.
  const side = el("aside", "side");
  side.append(panel("Result",
    statLine("Runtime", `${stats.seconds}s / ${input.target_seconds}s`),
    statLine("Words", `${words.total} (target ${budget.total_min ?? Math.round(budget.total * 0.9)}–${budget.total_max ?? Math.round(budget.total * 1.1)})`),
    statLine("Drafts", String(sample.drafts.length)),
    statLine("Generated in", sample.generation_seconds ? `${sample.generation_seconds}s` : "n/a"),
    statLine("Model", sample.model || "n/a"),
  ));
  if (sample.review) {
    const r = sample.review;
    side.append(panel("Editor's final scores",
      statLine("Hook", `${r.hook_score}/5`), statLine("Body", `${r.body_score}/5`),
      statLine("Tone", `${r.tone_score}/5`), statLine("CTA", `${r.cta_score}/5`),
    ));
  }
  if (sample.remaining_issues.length) {
    const ul = el("ul", "checks");
    for (const issue of sample.remaining_issues) {
      const li = el("li", "fail");
      li.append(el("span", "dot", "!"), el("span", "", issue));
      ul.append(li);
    }
    side.append(panel("Left unresolved", ul));
  }
  if (sample.research?.length) {
    const ul = el("ul", "sources");
    for (const f of sample.research) {
      const li = el("li", "", f.claim);
      const link = el("a", "", new URL(f.source_url).hostname.replace(/^www\./, ""));
      link.href = f.source_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      li.append(link);
      ul.append(li);
    }
    side.append(panel("Researched facts", ul));
  }

  $("sample-detail").replaceChildren(doc, side);
  $("sample-list").hidden = true;
  $("sample-detail").hidden = false;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

$("samples-btn").addEventListener("click", openSamples);
$("samples-back").addEventListener("click", () => {
  if (!$("sample-detail").hidden) {
    $("sample-detail").hidden = true;
    $("sample-list").hidden = false;
    return;
  }
  show(returnTo);
  if (returnTo === null) $("compose").hidden = false;
});

loadOptions().catch((err) => toast(`Couldn't load options: ${err.message}`));
