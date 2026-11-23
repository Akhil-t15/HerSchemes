import "./style.css";
import { t } from "./i18n.js";
import { renderPrivacyBanner } from "./privacy-banner.js";
import { resumeVoiceAudio, startVoice, stopVoice } from "./voice.js";

const LANG_STORAGE_KEY = "herscheme.lang";
// Module 7: admin token lives in sessionStorage only (never localStorage).
const ADMIN_TOKEN_KEY = "herscheme.adminToken";
const DEMO_ADMIN_TOKEN = "judge-admin-demo";
const VARIANTS = ["card--indigo", "card--emerald", "card--sky", "card--indigo"];
// Module 8: bank-loan schemes are picked by the lane label the API returns, not by hardcoded rules.
const BANK_LOAN_LANE = /loan/i;
// Profile answer fields shown in the summary: [answer field, i18n label key]
const ANSWER_FIELDS = [
  ["business_type", "fieldBusinessType"],
  ["location", "fieldLocation"],
  ["district", "fieldDistrict"],
  ["shg_member", "fieldShg"],
];

const state = {
  lang: readLang(),
  profile: {},
  health: "pending", // pending | ok | error
  quick: null, // null (loading) | array | "error"
  messages: [], // {role: "user", text} | {role: "assistant", reply, question, matches, error, sourceText, questionKey}
  roundsAsked: 0, // assistant question rounds shown so far, sent as rounds_asked
  knownFacts: {}, // accumulated facts extracted by the LLM across turns
  lastQuestionKey: null, // the fact key the last assistant question was about (for fallback)
  voiceOk: true, // false while live voice is unavailable (text-mode banner shown)
  checking: false, // true while a message is waiting for the privacy check
  notice: null, // i18n key of the privacy notice shown in the conversation, or null
  checklist: null, // null | {slug, status: "loading" | "ready" | "error", data}
  admin: {
    open: false, // admin console visible
    token: readAdminToken(), // sessionStorage only; defaults to demo token for judges
    proposals: null, // null (loading) | array | "error"
    message: null, // null | {key, error} shown in the admin panel
    preview: null, // last changed proposal returned by the submit form, or null
  },
  partner: {
    open: false, // partner/sponsor panel visible
    token: DEMO_ADMIN_TOKEN, // in memory only; defaults to demo token for judges
    role: "partner", // "partner" | "sponsor"
    org: "State Bank of India (Demo)",
    leads: null, // null (loading) | array | "error"
    impact: null, // null (loading) | object | "error"
    message: null, // null | {key, error}
    contactedLeads: new Set(),
  },
  banks: {
    schemes: null, // null (loading) | array of bank-loan schemes | "error"
    forms: {}, // per-scheme call-request form state, keyed by slug
  },
};

let liveVoiceOn = false; // Module 9: LiveKit session running
let voiceStatusKey = ""; // i18n key shown in the live voice status line, "" for none
let voiceStatusClass = "";

// Module 7: sessionStorage access for the admin token; defaults to demo token for evaluators.
function readAdminToken() {
  try {
    const val = sessionStorage.getItem(ADMIN_TOKEN_KEY);
    return val !== null && val !== "" ? val : DEMO_ADMIN_TOKEN;
  } catch {
    return DEMO_ADMIN_TOKEN;
  }
}

function writeAdminToken(token) {
  try {
    if (token) sessionStorage.setItem(ADMIN_TOKEN_KEY, token);
    else sessionStorage.removeItem(ADMIN_TOKEN_KEY);
  } catch {
    // storage unavailable; the in-memory token still works for this session
  }
}

function readLang() {
  try {
    return localStorage.getItem(LANG_STORAGE_KEY) === "te" ? "te" : "en";
  } catch {
    return "en";
  }
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// Element whose text is filled from i18n key by applyStatic().
function tEl(tag, className, key) {
  const node = el(tag, className);
  node.dataset.i18n = key;
  return node;
}

// Picks the Telugu or English field of a data item, falling back to English.
function localized(item, base) {
  if (state.lang === "te") return item[`${base}_te`] || item[`${base}_en`] || "";
  return item[`${base}_en`] || "";
}

function formatAnswer(value) {
  if (value === true) return t(state.lang, "ansYes");
  if (value === false) return t(state.lang, "ansNo");
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return value.trim();
  return "";
}

// ---------- Build DOM ----------
const mesh = el("div", "mesh");
mesh.append(
  el("div", "blob blob--indigo"),
  el("div", "blob blob--violet"),
  el("div", "blob blob--emerald")
);

const topbar = el("header", "topbar");
const langGroup = el("div", "lang-toggle");
langGroup.setAttribute("role", "group");
langGroup.dataset.i18nAria = "langGroup";
const langButtons = ["en", "te"].map((code) => {
  const btn = tEl("button", "lang-btn", code === "en" ? "langEn" : "langTe");
  btn.type = "button";
  btn.dataset.lang = code;
  btn.setAttribute("aria-pressed", "false");
  btn.addEventListener("click", () => setLang(code));
  return btn;
});
langGroup.append(...langButtons);
// Module 7: admin console link in topbar
const adminBtn = el("a", "btn-admin", "🏛️ Admin Console");
adminBtn.href = "/admin.html";
const topActions = el("div", "topbar-actions");
topActions.append(langGroup);
topbar.append(el("span", "brand", "HerScheme"), topActions);

const main = el("main", "glass");

// Section 1: hero with mic, spoken transcript box, and voice agent waveform
const heroSection = el("section", "home-section hero");
const micPrompt = tEl("p", "hero-prompt", "micPrompt");
const textNotice = tEl("p", "caption", "textNotice");

// Voice agent waveform bar (animates while voice agent is speaking)
const agentBar = el("div", "agent-wave-bar");
const agentBadge = el("div", "agent-badge");
const agentDot = el("span", "agent-dot");
const agentTitle = tEl("span", "agent-title", "agentVoiceTitle");
agentBadge.append(agentDot, agentTitle);

const waveformEl = el("div", "waveform");
waveformEl.setAttribute("aria-hidden", "true");
const waveBars = [];
for (let i = 0; i < 16; i++) {
  const bar = el("span", `wave-bar wave-bar-${i + 1}`);
  waveBars.push(bar);
  waveformEl.append(bar);
}

const agentStatusText = tEl("span", "agent-status-text", "agentReady");
agentBar.append(agentBadge, waveformEl, agentStatusText);

// Mic button and status
const micBtn = el("button", "mic-btn");
micBtn.type = "button";
micBtn.setAttribute("aria-pressed", "false");
micBtn.append(buildMicIcon());
micBtn.addEventListener("click", toggleMic);
const voiceStatus = el("p", "caption voice-status");
voiceStatus.setAttribute("aria-live", "polite");

// Spoken transcript section (blended directly into the glass UI, matching composer)
const spokenSection = el("div", "spoken-section");

const spokenHeader = el("div", "spoken-header");
const spokenLabelRow = el("div", "spoken-label-row");
const spokenLabel = tEl("label", "label", "spokenBoxTitle");
spokenLabel.setAttribute("for", "spoken-message");

const clearSpokenBtn = tEl("button", "btn-clear-text", "spokenClear");
clearSpokenBtn.type = "button";
clearSpokenBtn.hidden = true;
clearSpokenBtn.addEventListener("click", () => {
  spokenBase = "";
  spokenSegments.clear();
  renderSpokenBox();
});
spokenLabelRow.append(spokenLabel, clearSpokenBtn);

const micMeta = el("div", "mic-meta");
const micHint = tEl("span", "mic-hint", "tapToSpeak");
micMeta.append(micHint, voiceStatus);
spokenHeader.append(spokenLabelRow, micMeta);

// Unified input box with embedded mic button on the right
const spokenInput = el("div", "field-input spoken-input");
spokenInput.id = "spoken-message";
spokenInput.setAttribute("tabindex", "0");
spokenInput.setAttribute("role", "textbox");
spokenInput.setAttribute("aria-multiline", "true");
spokenInput.setAttribute("aria-live", "polite");

const spokenTextFlow = el("div", "spoken-text-flow");
const spokenPlaceholder = tEl("span", "spoken-placeholder", "spokenPlaceholder");
const spokenContent = el("span", "spoken-text is-empty");
spokenTextFlow.append(spokenPlaceholder, spokenContent);

spokenInput.append(spokenTextFlow, micBtn);

spokenSection.append(spokenHeader, spokenInput);

const voiceBanner = el("div", "banner");
voiceBanner.setAttribute("role", "status");
voiceBanner.setAttribute("aria-live", "polite");

heroSection.append(micPrompt, textNotice, agentBar, spokenSection, voiceBanner);

// Section 2: conversation + text box
const chatSection = el("section", "home-section");
const conversation = el("div", "conversation");
conversation.setAttribute("aria-live", "polite");
const form = el("form", "composer");
const textareaLabel = tEl("label", "label", "textareaLabel");
textareaLabel.setAttribute("for", "message");
const textarea = el("textarea", "field-input");
textarea.id = "message";
textarea.rows = 2;
textarea.dataset.i18nPlaceholder = "placeholder";
const sendBtn = tEl("button", "btn-primary", "send");
sendBtn.type = "submit";

function updateSendButton() {
  const hasText = Boolean(textarea.value.trim());
  sendBtn.classList.toggle("btn-primary--active", hasText);
}

textarea.addEventListener("input", updateSendButton);
textarea.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

form.append(textareaLabel, textarea, sendBtn);
// Module 5: scheme checklist panel, shown above the composer when a match is opened.
const checklistPanel = el("section", "checklist-panel");
checklistPanel.hidden = true;
chatSection.append(conversation, checklistPanel, form);

// Section 3: quick queries
const quickSection = el("section", "home-section");
const quickTitle = tEl("h2", "", "quickTitle");
const quickList = el("div", "chip-row");
const quickNote = el("p", "body");
quickNote.setAttribute("aria-live", "polite");
quickSection.append(quickTitle, quickList, quickNote);

// Section 5: current profile summary
const profileSection = el("section", "home-section");
const profileSummary = el("div", "profile-summary");
const profileTitle = tEl("span", "label", "profileTitle");
const profileLine = el("p", "body");
profileSummary.append(profileTitle, profileLine);
profileSection.append(profileSummary);


// Module 7: admin console panel (hidden until the top-bar button opens it).
const adminPanel = el("section", "admin-panel");
adminPanel.id = "admin-panel";
adminPanel.hidden = true;
const adminHeader = el("div", "checklist-header");
const adminLogoutBtn = tEl("button", "btn-skip", "adminLogout");
adminLogoutBtn.type = "button";
adminLogoutBtn.addEventListener("click", logoutAdmin);
adminHeader.append(tEl("h2", "", "adminTitle"), adminLogoutBtn);
const adminMessage = el("p", "admin-message");
adminMessage.setAttribute("role", "status");
adminMessage.setAttribute("aria-live", "polite");

const adminJudgeBanner = el("div", "judge-banner");
adminJudgeBanner.innerHTML = `
  <span class="judge-badge">⚖️ Judge & Evaluator Mode</span>
  <p class="judge-desc"><strong>Admin Console Purpose:</strong> Official Government Order (G.O.) Ingestion & Rule Audit Trail. Scheme eligibility rules, caps, and subsidies are verified here before publishing, guaranteeing the AI scheme finder never makes up rules from thin air. Inspect pending proposals below, approve them to update live rules, or simulate a new G.O. notice.</p>
`;

// Login gate: the password field is only used to set the token in sessionStorage.
const adminLoginForm = el("form", "admin-form");
const adminTokenLabel = tEl("label", "label", "adminTokenLabel");
adminTokenLabel.setAttribute("for", "admin-token");
const adminTokenInput = el("input", "admin-input");
adminTokenInput.type = "password";
adminTokenInput.id = "admin-token";
adminTokenInput.autocomplete = "current-password";
adminTokenInput.spellcheck = false;
const adminTokenHint = tEl("p", "caption", "adminTokenHint");
const adminLoginBtn = tEl("button", "btn-primary", "adminLogin");
adminLoginBtn.type = "submit";
const adminQuickLoginBtn = el("button", "btn-quick-fill", "🔑 Open with Judge Demo Credentials");
adminQuickLoginBtn.type = "button";
adminQuickLoginBtn.addEventListener("click", () => {
  adminTokenInput.value = DEMO_ADMIN_TOKEN;
  state.admin.token = DEMO_ADMIN_TOKEN;
  writeAdminToken(DEMO_ADMIN_TOKEN);
  renderAdmin();
  loadProposals();
});
adminLoginForm.append(adminTokenLabel, adminTokenInput, adminTokenHint, adminLoginBtn, adminQuickLoginBtn);
adminLoginForm.addEventListener("submit", loginAdmin);

// Console: proposal form, last submit result, and the pending list.
const adminConsole = el("div", "admin-console");
const adminForm = el("form", "admin-form");
const adminSlugLabel = tEl("label", "label", "adminSchemeLabel");
adminSlugLabel.setAttribute("for", "admin-slug");
const adminSlugInput = el("input", "admin-input");
adminSlugInput.type = "text";
adminSlugInput.id = "admin-slug";
const adminNoticeLabel = tEl("label", "label", "adminNoticeLabel");
adminNoticeLabel.setAttribute("for", "admin-notice");
const adminNoticeInput = el("textarea", "field-input");
adminNoticeInput.id = "admin-notice";
adminNoticeInput.maxLength = 20000;
const adminChangesLabel = tEl("label", "label", "adminChangesLabel");
adminChangesLabel.setAttribute("for", "admin-changes");
const adminChangesInput = el("textarea", "field-input admin-json");
adminChangesInput.id = "admin-changes";
adminChangesInput.dataset.i18nPlaceholder = "adminChangesPlaceholder";
const adminSubmitBtn = tEl("button", "btn-primary", "adminSubmit");
adminSubmitBtn.type = "submit";

const adminQuickFillBtn = el("button", "btn-quick-fill", "⚡ Pre-fill Sample G.O. Notice (PMEGP)");
adminQuickFillBtn.type = "button";
adminQuickFillBtn.addEventListener("click", () => {
  adminSlugInput.value = "pmegp";
  adminNoticeInput.value = "Ministry of MSME Gazette Notification 2026: Enhancing maximum subsidy for women entrepreneurs in rural areas to 35% with expedited 15-day processing.";
  adminChangesInput.value = JSON.stringify([
    { rule_key: "subsidy_rural_women", new_value: "35%" },
    { rule_key: "processing_days_limit", new_value: 15 }
  ], null, 2);
  adminMessage.textContent = "Sample G.O. notice loaded. Click 'Submit proposal' to test ingestion.";
  adminMessage.hidden = false;
  adminMessage.classList.remove("admin-message--error");
});

adminForm.append(
  adminSlugLabel,
  adminSlugInput,
  adminNoticeLabel,
  adminNoticeInput,
  adminChangesLabel,
  adminChangesInput,
  adminSubmitBtn,
  adminQuickFillBtn
);
adminForm.addEventListener("submit", submitProposal);
const adminPreview = el("div", "admin-proposal admin-preview");
adminPreview.hidden = true;
const adminPendingTitle = tEl("h2", "", "adminPendingTitle");
const adminList = el("div", "admin-proposals");
adminConsole.append(adminForm, adminPreview, adminPendingTitle, adminList);

adminPanel.append(adminHeader, adminJudgeBanner, adminMessage, adminLoginForm, adminConsole);

// Module 8: bank-loan cards, one per scheme, each with an opt-in call switch.
const bankSection = el("section", "home-section");
const bankTitle = tEl("h2", "", "bankTitle");
const bankGrid = el("div", "demo-grid");
const bankNote = el("p", "body");
bankNote.setAttribute("aria-live", "polite");
bankSection.append(bankTitle, bankGrid, bankNote);

// Module 8: partner and sponsor login panel, opened from the footer link.
const partnerPanel = el("section", "admin-panel partner-panel");
partnerPanel.id = "partner-panel";
partnerPanel.hidden = true;
const partnerHeader = el("div", "checklist-header");
const partnerLogoutBtn = tEl("button", "btn-skip", "partnerLogout");
partnerLogoutBtn.type = "button";
partnerLogoutBtn.addEventListener("click", logoutPartner);
partnerHeader.append(tEl("h2", "", "partnerTitle"), partnerLogoutBtn);
const partnerMessage = el("p", "admin-message");
partnerMessage.setAttribute("role", "status");
partnerMessage.setAttribute("aria-live", "polite");

const partnerJudgeBanner = el("div", "judge-banner");
partnerJudgeBanner.innerHTML = `
  <span class="judge-badge">🤝 Module 8: Partner & Sponsor Portals</span>
  <p class="judge-desc"><strong>Ethical Sustainability:</strong> HerScheme remains ₹0 for women forever. Partner banks connect with women who explicitly requested a loan callback, while CSR sponsors monitor aggregate reach with zero access to personal citizen data.</p>
`;

const partnerTabs = el("div", "portal-tabs");
const tabPartnerBtn = el("button", "portal-tab-btn active", "🏦 Partner Bank Portal (Leads)");
tabPartnerBtn.type = "button";
const tabSponsorBtn = el("button", "portal-tab-btn", "📊 CSR Sponsor Impact (Metrics)");
tabSponsorBtn.type = "button";

tabPartnerBtn.addEventListener("click", () => {
  state.partner.role = "partner";
  tabPartnerBtn.classList.add("active");
  tabSponsorBtn.classList.remove("active");
  loadPartnerView();
});
tabSponsorBtn.addEventListener("click", () => {
  state.partner.role = "sponsor";
  tabSponsorBtn.classList.add("active");
  tabPartnerBtn.classList.remove("active");
  loadPartnerView();
});
partnerTabs.append(tabPartnerBtn, tabSponsorBtn);

const partnerLoginForm = el("form", "admin-form");
const partnerUserLabel = tEl("label", "label", "partnerUsername");
partnerUserLabel.setAttribute("for", "partner-user");
const partnerUserInput = el("input", "admin-input");
partnerUserInput.type = "text";
partnerUserInput.id = "partner-user";
partnerUserInput.autocomplete = "username";
partnerUserInput.spellcheck = false;
const partnerPassLabel = tEl("label", "label", "partnerPassword");
partnerPassLabel.setAttribute("for", "partner-pass");
const partnerPassInput = el("input", "admin-input");
partnerPassInput.type = "password";
partnerPassInput.id = "partner-pass";
partnerPassInput.autocomplete = "current-password";
const partnerLoginBtn = tEl("button", "btn-primary", "partnerLogin");
partnerLoginBtn.type = "submit";
const partnerQuickLoginBtn = el("button", "btn-quick-fill", "🔑 Open with Judge Demo Credentials");
partnerQuickLoginBtn.type = "button";
partnerQuickLoginBtn.addEventListener("click", () => {
  state.partner.token = DEMO_ADMIN_TOKEN;
  state.partner.role = state.partner.role || "partner";
  renderPartner();
  loadPartnerView();
});
partnerLoginForm.append(
  partnerUserLabel,
  partnerUserInput,
  partnerPassLabel,
  partnerPassInput,
  partnerLoginBtn,
  partnerQuickLoginBtn
);
partnerLoginForm.addEventListener("submit", loginPartner);

// Role-specific view: opt-in leads (partner) or the impact dashboard (sponsor).
const partnerView = el("div", "partner-view");
partnerPanel.append(partnerHeader, partnerJudgeBanner, partnerTabs, partnerMessage, partnerLoginForm, partnerView);

// Footer with link to the dedicated partner and sponsor portal.
const footer = el("footer", "site-footer");
const footerNote = tEl("p", "footer-note", "footerDisclaimer");
const partnerLinkBtn = el("a", "btn-skip", "🤝 Partners & Impact");
partnerLinkBtn.href = "/partners.html";
// Footer right-side actions: Admin Console sits beside Partners & Impact.
const footerActions = el("div", "footer-actions");
footerActions.style.display = "flex";
footerActions.style.alignItems = "center";
footerActions.style.gap = "0.75rem";
footerActions.append(adminBtn, partnerLinkBtn);
footer.append(footerNote, footerActions);

main.append(
  heroSection,
  chatSection,
  quickSection,
  bankSection,
  profileSection
);

// Privacy notice sits above the hero; replaced on every language change.
let privacyBanner = renderPrivacyBanner(state.lang);
main.prepend(privacyBanner);

const page = el("div", "page");
page.append(main, footer);

const app = document.getElementById("app");
app.append(mesh, topbar, page);

function buildMicIcon() {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", "22");
  svg.setAttribute("height", "22");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const capsule = document.createElementNS(NS, "rect");
  capsule.setAttribute("x", "9");
  capsule.setAttribute("y", "2");
  capsule.setAttribute("width", "6");
  capsule.setAttribute("height", "12");
  capsule.setAttribute("rx", "3");
  const arc = document.createElementNS(NS, "path");
  arc.setAttribute("d", "M5 11a7 7 0 0 0 14 0");
  const stem = document.createElementNS(NS, "path");
  stem.setAttribute("d", "M12 18v4M8 22h8");
  svg.append(capsule, arc, stem);
  return svg;
}

function buildTranscriptIcon() {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", "15");
  svg.setAttribute("height", "15");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("spoken-icon");
  const bubble = document.createElementNS(NS, "path");
  bubble.setAttribute("d", "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z");
  const line1 = document.createElementNS(NS, "path");
  line1.setAttribute("d", "M8 9h8");
  const line2 = document.createElementNS(NS, "path");
  line2.setAttribute("d", "M8 13h5");
  svg.append(bubble, line1, line2);
  return svg;
}

// ---------- Language & static text ----------
function applyStatic() {
  document.documentElement.lang = state.lang;
  for (const node of document.querySelectorAll("[data-i18n]")) {
    node.textContent = t(state.lang, node.dataset.i18n);
  }
  for (const node of document.querySelectorAll("[data-i18n-placeholder]")) {
    node.setAttribute("placeholder", t(state.lang, node.dataset.i18nPlaceholder));
  }
  for (const node of document.querySelectorAll("[data-i18n-aria]")) {
    node.setAttribute("aria-label", t(state.lang, node.dataset.i18nAria));
  }
  for (const btn of langButtons) {
    btn.setAttribute("aria-pressed", String(btn.dataset.lang === state.lang));
  }
}

function setLang(code) {
  if (code !== "en" && code !== "te") return;
  state.lang = code;
  try {
    localStorage.setItem(LANG_STORAGE_KEY, code);
  } catch {
    // storage unavailable; keep the in-memory choice
  }
  renderAll();
}

function renderPrivacyNotice() {
  const next = renderPrivacyBanner(state.lang);
  privacyBanner.replaceWith(next);
  privacyBanner = next;
}

function renderAll() {
  applyStatic();
  renderPrivacyNotice();
  renderHealth();
  renderVoice();
  renderMic();
  renderQuick();
  renderProfile();
  renderConversation();
  renderChecklist();
  renderAdmin();
  renderBank();
  renderPartner();
}

// ---------- Health ----------
// Status line was removed from the top bar; the health fetch in loadHealth still runs.
function renderHealth() { }

async function loadHealth() {
  try {
    const res = await fetch("/api/health");
    if (!res.ok) throw new Error("bad status");
    const data = await res.json();
    state.health = data && data.status === "ok" ? "ok" : "error";
  } catch {
    state.health = "error";
  }
  renderHealth();
}

// ---------- Lists ----------
async function fetchList(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error("bad status");
  const data = await res.json();
  if (!Array.isArray(data)) throw new Error("bad shape");
  return data;
}

async function loadQuick() {
  try {
    state.quick = await fetchList("/api/quick-queries");
  } catch {
    state.quick = "error";
  }
  renderQuick();
}


function renderQuick() {
  quickList.replaceChildren();
  quickNote.textContent = "";
  if (state.quick === null) {
    quickNote.textContent = t(state.lang, "loading");
    return;
  }
  if (state.quick === "error") {
    quickNote.textContent = t(state.lang, "quickError");
    return;
  }
  for (const q of state.quick) {
    const chip = el("button", "chip", localized(q, "text"));
    chip.type = "button";
    chip.addEventListener("click", () => {
      textarea.value = localized(q, "text");
      Object.assign(state.profile, q.answers || {});
      Object.assign(state.knownFacts, q.answers || {});
      state.lastQuestionKey = null;
      renderProfile();
      updateSendButton();
      textarea.focus();
    });
    quickList.append(chip);
  }
}


function renderProfile() {
  const parts = ANSWER_FIELDS.map(([field, key]) => [
    t(state.lang, key),
    formatAnswer(state.profile[field]),
  ]).filter(([, value]) => value !== "");
  if (parts.length === 0) {
    profileLine.textContent = "";
    profileSummary.hidden = true;
    return;
  }
  profileLine.textContent = parts.map(([label, value]) => `${label}: ${value}`).join("  ·  ");
  profileSummary.hidden = false;
}

// ---------- Voice ----------
function renderVoice() {
  voiceBanner.hidden = state.voiceOk;
  voiceBanner.textContent = state.voiceOk ? "" : t(state.lang, "voiceTextMode");
}

function renderMic() {
  micBtn.setAttribute("aria-pressed", String(liveVoiceOn));
  micBtn.setAttribute("aria-label", t(state.lang, liveVoiceOn ? "micStop" : "micStart"));
  spokenSection.classList.toggle("is-listening", liveVoiceOn);
  micHint.textContent = t(state.lang, liveVoiceOn ? "tapToStop" : "tapToSpeak");
  if (!liveVoiceOn) {
    setAgentSpeaking(false);
  } else if (!agentIsSpeaking) {
    agentStatusText.textContent = t(state.lang, "agentListening");
  }
  renderVoiceStatus();
}

let agentIsSpeaking = false;

function setAgentSpeaking(speaking, freqData) {
  agentIsSpeaking = Boolean(speaking);
  agentBar.classList.toggle("is-speaking", agentIsSpeaking);
  waveformEl.classList.toggle("is-speaking", agentIsSpeaking);

  if (agentIsSpeaking) {
    agentStatusText.textContent = t(state.lang, "agentSpeaking");
    if (freqData && freqData.length) {
      for (let i = 0; i < waveBars.length; i++) {
        const idx = Math.min(i * 2, freqData.length - 1);
        const amp = freqData[idx] || 0;
        const h = Math.max(4, Math.min(28, Math.round((amp / 255) * 28)));
        waveBars[i].style.height = `${h}px`;
      }
    }
  } else {
    for (let i = 0; i < waveBars.length; i++) {
      waveBars[i].style.height = "";
    }
    if (liveVoiceOn) {
      agentStatusText.textContent = t(state.lang, "agentListening");
    } else {
      agentStatusText.textContent = t(state.lang, "agentReady");
    }
  }
}

// Live voice status line under the mic; the key is kept so it re-translates on language change.
function setVoiceStatus(key, cls) {
  voiceStatusKey = key;
  voiceStatusClass = cls;
  renderVoiceStatus();
}

function renderVoiceStatus() {
  voiceStatus.className = voiceStatusClass ? `voice-status ${voiceStatusClass}` : "voice-status";
  voiceStatus.textContent = voiceStatusKey ? t(state.lang, voiceStatusKey) : "";
}

function toggleMic() {
  if (liveVoiceOn) stopLiveVoice();
  else startLiveVoice();
}

// Live transcript in the message box and the spoken user textbox. Each segment id is one utterance:
// interim text replaces the in-progress text for that id; a final result is kept and the next
// utterance is added after it.
// Only masked text reaches this code (the server masks every segment before it is returned).
const voiceSegments = new Map(); // segment id -> text of an utterance still in progress
let voiceBase = null; // textarea text before the in-progress utterances; null when none
let spokenBase = ""; // accumulated final spoken text for the spoken textbox
const spokenSegments = new Map(); // segment id -> in-progress spoken text
let tapToHearShown = false; // the "tap to hear" chat message is shown at most once per session

function joinText(a, b) {
  return a && b ? `${a} ${b}` : a || b;
}

function renderSpokenBox() {
  const interim = [...spokenSegments.values()].join(" ").trim();
  const full = joinText(spokenBase, interim);
  if (!full) {
    spokenContent.textContent = "";
    spokenContent.classList.add("is-empty");
    spokenPlaceholder.hidden = false;
    clearSpokenBtn.hidden = true;
  } else {
    spokenPlaceholder.hidden = true;
    spokenContent.classList.remove("is-empty");
    spokenContent.textContent = full;
    clearSpokenBtn.hidden = false;
    spokenTextFlow.scrollTop = spokenTextFlow.scrollHeight;
  }
}

function showVoiceSegment(segId, text, isFinal) {
  if (voiceBase === null) voiceBase = textarea.value.replace(/\s+$/, "");
  if (isFinal) {
    voiceBase = joinText(voiceBase, text);
    voiceSegments.delete(segId);
    spokenBase = joinText(spokenBase, text);
    spokenSegments.delete(segId);
  } else {
    voiceSegments.set(segId, text);
    spokenSegments.set(segId, text);
  }
  textarea.value = joinText(voiceBase, [...voiceSegments.values()].join(" "));
  if (voiceSegments.size === 0) voiceBase = null;
  renderSpokenBox();
}

// Browser blocked agent audio autoplay: say so in the chat; the next click on the page replays it.
function showTapToHear() {
  if (tapToHearShown) return;
  tapToHearShown = true;
  state.messages.push({
    role: "assistant",
    question: null,
    text: t(state.lang, "voiceTapToHear"),
    matches: [],
    error: false,
    sourceText: "",
  });
  renderConversation();
  document.addEventListener("click", () => resumeVoiceAudio(), { once: true });
}

// Module 9: live voice session. If it fails or drops, the user is told to use text mode.
function startLiveVoice() {
  liveVoiceOn = true;
  voiceSegments.clear();
  spokenSegments.clear();
  voiceBase = null;
  spokenBase = "";
  renderSpokenBox();
  tapToHearShown = false;
  setVoiceStatus("voiceConnecting", "");
  renderMic();
  startVoice({
    onTranscriptChunk: (text, warning, segId, isFinal) => {
      showVoiceSegment(segId, text, isFinal);
      if (warning) {
        state.notice = "privacyHidden";
        renderConversation();
      }
    },
    onAgentSpeaking: (isSpeaking, freqData) => {
      setAgentSpeaking(isSpeaking, freqData);
    },
    onUnavailable: (message) => {
      liveVoiceOn = false;
      setAgentSpeaking(false);
      showTextMode(message);
      renderMic();
    },
    onAudioBlocked: showTapToHear,
    onEnded: () => {
      liveVoiceOn = false;
      setAgentSpeaking(false);
      showTextMode();
      renderMic();
    },
  }).then((connected) => {
    if (!connected || !liveVoiceOn) return;
    state.voiceOk = true;
    renderVoice();
    setVoiceStatus("voiceLive", "voice-active");
  });
}

function stopLiveVoice() {
  liveVoiceOn = false;
  setAgentSpeaking(false);
  stopVoice();
  setVoiceStatus("", "");
  renderMic();
}

// Live voice failed: show the text-mode message under the mic, in the banner, and in the chat.
function showTextMode(detail) {
  state.voiceOk = false;
  setVoiceStatus("voiceTextMode", "voice-failed");
  renderVoice();
  state.messages.push({
    role: "assistant",
    question: null,
    text: detail || t(state.lang, "voiceTextMode"),
    matches: [],
    error: false,
    sourceText: "",
  });
  renderConversation();
}

// ---------- Chat ----------
// Sends the raw text to the server for masking. Only the masked text is ever used after this.
async function checkPrivacy(text) {
  const res = await fetch("/api/privacy/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error("bad status");
  const data = await res.json();
  if (!data || typeof data.masked_text !== "string") throw new Error("bad shape");
  return { maskedText: data.masked_text, warning: data.warning === true };
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const raw = textarea.value.trim();
  if (!raw || state.checking) return;

  state.checking = true;
  let checked = null;
  try {
    checked = await checkPrivacy(raw);
  } catch {
    checked = null; // never fall back to the raw text
  }
  state.checking = false;

  if (!checked) {
    state.notice = "privacyUnavailable";
    renderConversation();
    return;
  }
  state.notice = checked.warning ? "privacyHidden" : null;
  const reply = { role: "assistant", pending: true, reply: null, question: null, matches: [], error: false, sourceText: "" };
  state.messages.push({ role: "user", text: checked.maskedText }, reply);
  if (textarea.value.trim() === raw) {
    textarea.value = "";
    updateSendButton();
  }
  renderConversation();
  askFollowUp(reply, checked.maskedText, false);
});

// Build conversation history from state.messages for the LLM.
function buildHistory() {
  return state.messages
    .filter((m) => m.text || m.question || m.reply)
    .map((m) => ({
      role: m.role,
      content: m.role === "user" ? m.text : (m.reply || m.question || m.text || ""),
    }));
}

// Posts only masked text to the follow-up endpoint (never the raw input).
async function requestFollowUp(text, skipped) {
  const res = await fetch("/api/chat/follow-up", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: text,
      lang: state.lang,
      known_facts: state.knownFacts,
      rounds_asked: state.roundsAsked,
      skipped,
      history: buildHistory(),
      last_question_key: state.lastQuestionKey,
    }),
  });
  if (!res.ok) throw new Error("bad status");
  const data = await res.json();
  if (!data || typeof data !== "object") throw new Error("bad shape");
  // Merge any new facts from the LLM or fallback into accumulated state
  if (data.known_facts && typeof data.known_facts === "object") {
    for (const [key, val] of Object.entries(data.known_facts)) {
      if (val !== null && val !== undefined && String(val).trim() !== "") {
        state.knownFacts[key] = val;
      }
    }
  }
  // Track which question was asked so the next user reply can answer it
  state.lastQuestionKey = data.question_key || null;
  return {
    reply: typeof data.reply === "string" ? data.reply : null,
    questions: Array.isArray(data.questions)
      ? data.questions.filter((q) => typeof q === "string" && q.trim() !== "")
      : [],
    matches: Array.isArray(data.matches)
      ? data.matches.filter((m) => m && typeof m === "object")
      : [],
    done: data.done === true,
  };
}

// Fetches the next step for an assistant reply. Used for the first answer and for Skip.
async function askFollowUp(reply, text, skipped) {
  reply.sourceText = text;
  reply.pending = true;
  state.checking = true;
  try {
    const data = await requestFollowUp(text, skipped);
    reply.pending = false;
    reply.error = false;
    // Use the LLM's natural reply, or fall back to the first question
    reply.reply = data.reply || null;
    reply.question = !skipped && data.questions.length > 0 ? data.questions[0] : null;
    reply.matches = (data.done || (data.matches && data.matches.length > 0)) ? data.matches : [];
    if (data.reply || reply.question) state.roundsAsked += 1;
    if (data.done || skipped || (data.matches && data.matches.length > 0)) state.lastQuestionKey = null;
  } catch {
    reply.pending = false;
    reply.error = true;
    reply.reply = null;
    reply.question = null;
    reply.matches = [];
  }
  state.checking = false;
  renderConversation();
}

function assistantText(m) {
  if (m.error) return t(state.lang, "followUpError");
  if (m.pending) return t(state.lang, "loading");
  if (m.reply) return m.reply;
  if (m.text) return m.text;
  if (m.question) return m.question;
  if (m.matches && m.matches.length > 0) return t(state.lang, "assistantNote");
  return "";
}

function renderMatch(match) {
  const li = el("li", "match");

  const header = el("div", "match-header");
  const info = el("div", "match-info");
  info.append(el("span", "match-name", localized(match, "name") || String(match.slug || "")));
  const url = typeof match.official_url === "string" ? match.official_url : "";
  if (/^https?:\/\//i.test(url)) {
    const link = el("a", "match-link", t(state.lang, "officialWebsite"));
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    info.append(link);
  }
  header.append(info);

  const actions = el("div", "match-actions");
  const isLikely =
    String(match.status || "").trim().toLowerCase().replace(/[\s-]+/g, "_") === "likely_eligible";
  actions.append(
    el(
      "span",
      `badge ${isLikely ? "badge--likely" : "badge--needs"}`,
      t(state.lang, isLikely ? "badgeLikely" : "badgeNeeds")
    )
  );
  const slug = typeof match.slug === "string" ? match.slug.trim() : "";
  if (slug) {
    const checklistBtn = el("button", "btn-checklist", t(state.lang, "viewChecklist"));
    checklistBtn.type = "button";
    checklistBtn.addEventListener("click", () => openChecklist(slug));
    actions.append(checklistBtn);
  }
  header.append(actions);
  li.append(header);

  // Scheme offering / key benefit
  const benefit = localized(match, "benefit") || match.description || "";
  if (benefit) {
    const benefitEl = el("div", "match-benefit");
    const tag = el("span", "match-benefit-tag", t(state.lang, "schemeOffers"));
    const text = el("span", "match-benefit-text", benefit);
    benefitEl.append(tag, text);
    li.append(benefitEl);
  }

  return li;
}

// Skip button for the latest question, and the matches list once the flow is done.
function renderFollowUp(m, isLast) {
  const parts = [];
  const hasQuestion = !m.pending && (m.question || m.reply);
  if (isLast && hasQuestion && m.matches.length === 0) {
    const skip = el("button", "btn-skip", t(state.lang, "skip"));
    skip.type = "button";
    skip.addEventListener("click", () => {
      if (state.checking) return;
      m.pending = true;
      m.question = null;
      m.reply = null;
      renderConversation();
      askFollowUp(m, m.sourceText, true);
    });
    parts.push(skip);
  }
  if (m.matches.length > 0) {
    const list = el("ul", "match-list");
    list.replaceChildren(...m.matches.map(renderMatch));
    parts.push(el("span", "label", t(state.lang, "matchesTitle")), list);
  }
  return parts;
}

function renderConversation() {
  const last = state.messages.length - 1;
  const items = state.messages.map((m, i) => {
    const isUser = m.role === "user";
    const wrap = el("div", `msg ${isUser ? "msg--user" : "msg--assistant"}${m.pending ? " msg--pending" : ""}`);
    const label = el("span", "label", t(state.lang, isUser ? "you" : "assistant"));
    const body = el("p", "body", isUser ? m.text : assistantText(m));
    wrap.append(label, body);
    if (!isUser) wrap.append(...renderFollowUp(m, i === last));
    return wrap;
  });
  if (state.notice) {
    items.push(el("p", "privacy-notice", t(state.lang, state.notice)));
  }
  conversation.replaceChildren(...items);
  requestAnimationFrame(() => {
    conversation.scrollTop = conversation.scrollHeight;
  });
}

// ---------- Module 5: scheme checklist ----------
function asObjects(value) {
  return Array.isArray(value) ? value.filter((x) => x && typeof x === "object") : [];
}

function asStrings(value) {
  return Array.isArray(value) ? value.filter((x) => typeof x === "string" && x.trim() !== "") : [];
}

function isHttpUrl(url) {
  return typeof url === "string" && /^https?:\/\//i.test(url);
}

// Steps in the current language, falling back to English when the Telugu list is empty.
function checklistSteps(where) {
  const te = asStrings(where.steps_te);
  if (state.lang === "te" && te.length > 0) return te;
  return asStrings(where.steps_en);
}

// Fee and processing time come from the API response; nothing is hardcoded here.
function feeText(item) {
  if (item.fee_amount === null || item.fee_amount === undefined) return "";
  const amount = `${item.fee_amount} ${item.currency || ""}`.trim();
  return t(state.lang, "checklistFee", { amount });
}

function processingText(item) {
  if (item.processing_days === null || item.processing_days === undefined) return "";
  return t(state.lang, "checklistProcessing", { days: item.processing_days });
}

function whereToApply(data) {
  return data.where_to_apply && typeof data.where_to_apply === "object" ? data.where_to_apply : {};
}

function buildChecklistItem(title, item, details) {
  const li = el("li", "checklist-item");
  li.append(el("span", "match-name", title));
  if (details) li.append(el("span", "body", details));
  if (item.needs_verification === true) {
    li.append(el("span", "badge badge--needs", t(state.lang, "needsVerification")));
  }
  return li;
}

function buildChecklistBody(data) {
  const where = whereToApply(data);

  // Free papers, with the Udyam warning in bold when the API provides one.
  const free = el("section", "checklist-section");
  free.append(el("h3", "checklist-heading", t(state.lang, "checklistFreeTitle")));
  const warning = localized(data, "udyam_warning");
  if (warning) {
    const warningPara = el("p", "checklist-warning");
    warningPara.append(el("strong", "", warning));
    free.append(warningPara);
  }
  const freeItems = asObjects(data.free_papers);
  if (freeItems.length === 0) {
    free.append(el("p", "body", t(state.lang, "checklistNone")));
  } else {
    const freeList = el("ul", "checklist-list");
    freeList.replaceChildren(
      ...freeItems.map((p) => buildChecklistItem(localized(p, "title"), p, ""))
    );
    free.append(freeList);
  }

  // MeeSeva certificates with fee and processing time.
  const meeseva = el("section", "checklist-section");
  meeseva.append(el("h3", "checklist-heading", t(state.lang, "checklistMeesevaTitle")));
  const certs = asObjects(data.meeseva_certificates);
  if (certs.length === 0) {
    meeseva.append(el("p", "body", t(state.lang, "checklistNone")));
  } else {
    const certList = el("ul", "checklist-list");
    certList.replaceChildren(
      ...certs.map((c) =>
        buildChecklistItem(
          localized(c, "title"),
          c,
          [feeText(c), processingText(c)].filter(Boolean).join("  ·  ")
        )
      )
    );
    meeseva.append(certList);
  }

  // Where to apply for free: official link (new tab) and numbered steps.
  const apply = el("section", "checklist-section");
  apply.append(el("h3", "checklist-heading", t(state.lang, "checklistApplyTitle")));
  if (isHttpUrl(where.official_url)) {
    const row = el("p", "body");
    const link = el("a", "match-link", where.official_url);
    link.href = where.official_url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    row.append(link);
    if (where.needs_verification === true) {
      row.append(el("span", "badge badge--needs", t(state.lang, "needsVerification")));
    }
    apply.append(row);
  }
  const steps = checklistSteps(where);
  if (steps.length > 0) {
    const stepList = el("ol", "checklist-steps");
    stepList.replaceChildren(...steps.map((s) => el("li", "", s)));
    apply.append(stepList);
  }

  return [free, meeseva, apply];
}

// Plain text for WhatsApp, in the current language.
function buildChecklistText(data) {
  const where = whereToApply(data);
  const verify = (item) =>
    item.needs_verification === true ? ` (${t(state.lang, "needsVerification")})` : "";
  const lines = [localized(data, "name"), "", t(state.lang, "checklistFreeTitle")];
  const warning = localized(data, "udyam_warning");
  if (warning) lines.push(warning);
  for (const p of asObjects(data.free_papers)) {
    lines.push(`- ${localized(p, "title")}${verify(p)}`);
  }
  lines.push("", t(state.lang, "checklistMeesevaTitle"));
  for (const c of asObjects(data.meeseva_certificates)) {
    const details = [feeText(c), processingText(c)].filter(Boolean).join(", ");
    lines.push(`- ${localized(c, "title")}${details ? ` (${details})` : ""}${verify(c)}`);
  }
  lines.push("", t(state.lang, "checklistApplyTitle"));
  if (isHttpUrl(where.official_url)) lines.push(where.official_url);
  checklistSteps(where).forEach((step, i) => lines.push(`${i + 1}. ${step}`));
  return lines.join("\n");
}

function shareChecklist(data) {
  const url = `https://wa.me/?text=${encodeURIComponent(buildChecklistText(data))}`;
  window.open(url, "_blank", "noopener,noreferrer");
}

function renderChecklist() {
  const current = state.checklist;
  checklistPanel.replaceChildren();
  checklistPanel.hidden = current === null;
  if (current === null) return;

  const header = el("div", "checklist-header");
  const close = el("button", "btn-skip", t(state.lang, "checklistClose"));
  close.type = "button";
  close.addEventListener("click", () => {
    state.checklist = null;
    renderChecklist();
  });
  header.append(el("h2", "", t(state.lang, "checklistTitle")), close);
  checklistPanel.append(header);

  if (current.status === "loading") {
    checklistPanel.append(el("p", "body", t(state.lang, "loading")));
    return;
  }
  if (current.status === "error") {
    checklistPanel.append(el("p", "body", t(state.lang, "checklistError")));
    return;
  }

  const data = current.data;
  const name = localized(data, "name");
  if (name) checklistPanel.append(el("p", "checklist-name", name));
  checklistPanel.append(...buildChecklistBody(data));
  const share = el("button", "btn-primary", t(state.lang, "shareWhatsapp"));
  share.type = "button";
  share.addEventListener("click", () => shareChecklist(data));
  checklistPanel.append(share);
}

async function fetchChecklist(slug) {
  const res = await fetch(`/api/schemes/${encodeURIComponent(slug)}/checklist`);
  if (!res.ok) throw new Error("bad status");
  const data = await res.json();
  if (!data || typeof data !== "object") throw new Error("bad shape");
  return data;
}

async function openChecklist(slug) {
  const current = { slug, status: "loading", data: null };
  state.checklist = current;
  renderChecklist();
  checklistPanel.scrollIntoView?.({ behavior: "smooth", block: "start" });
  try {
    current.data = await fetchChecklist(slug);
    current.status = "ready";
  } catch {
    current.status = "error";
  }
  // Ignore the response if the panel was closed or another checklist was opened meanwhile.
  if (state.checklist === current) renderChecklist();
}

// ---------- Module 7: admin console ----------
// Failed requests carry the HTTP status, or "network" when fetch itself fails.
class AdminError extends Error {
  constructor(code) {
    super(String(code));
    this.code = code;
  }
}

const ADMIN_ERROR_KEYS = {
  401: "adminErr401",
  404: "adminErr404",
  409: "adminErr409",
  503: "adminErr503",
  network: "adminErrNetwork",
};

async function adminRequest(path, method = "GET", body) {
  const headers = { Authorization: `Bearer ${state.admin.token}` };
  const init = { method, headers };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, init);
  } catch {
    throw new AdminError("network");
  }
  if (!res.ok) throw new AdminError(res.status);
  try {
    return await res.json();
  } catch {
    return null;
  }
}

// Clears the token and everything tied to it (used on log out and on 401).
function forgetAdminToken() {
  state.admin.token = "";
  state.admin.proposals = null;
  state.admin.preview = null;
  writeAdminToken("");
}

function setAdminMessage(key, error) {
  state.admin.message = { key, error };
}

function handleAdminError(err, refresh) {
  const code = err instanceof AdminError ? err.code : "other";
  if (code === 401) forgetAdminToken();
  setAdminMessage(ADMIN_ERROR_KEYS[code] || "adminErrGeneric", true);
  renderAdmin();
  // A stale list after 404/409 is refreshed so the admin sees the current state.
  if (refresh && (code === 404 || code === 409) && state.admin.token) loadProposals();
}

function toggleAdmin() {
  state.admin.open = !state.admin.open;
  if (state.admin.open) {
    if (!state.admin.token) {
      state.admin.token = DEMO_ADMIN_TOKEN;
      writeAdminToken(DEMO_ADMIN_TOKEN);
    }
    loadProposals();
    adminPanel.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }
  renderAdmin();
}

function loginAdmin(event) {
  event.preventDefault();
  const token = adminTokenInput.value.trim();
  if (!token) {
    setAdminMessage("adminNeedLogin", true);
    renderAdmin();
    return;
  }
  state.admin.token = token;
  writeAdminToken(token);
  adminTokenInput.value = "";
  state.admin.message = null;
  loadProposals();
}

function logoutAdmin() {
  forgetAdminToken();
  state.admin.message = null;
  adminForm.reset();
  renderAdmin();
}

async function loadProposals() {
  if (!state.admin.token) return;
  state.admin.proposals = null;
  renderAdmin();
  try {
    const data = await adminRequest("/api/admin/proposals");
    if (!Array.isArray(data)) throw new AdminError("other");
    state.admin.proposals = asObjects(data);
  } catch (err) {
    state.admin.proposals = "error";
    handleAdminError(err, false);
  }
  renderAdmin();
}

// Parses the changes textarea. Returns null (and sets a message) when it is not a valid list.
function parseChanges(text) {
  let changes;
  try {
    changes = JSON.parse(text);
  } catch {
    setAdminMessage("adminInvalidJson", true);
    return null;
  }
  const valid =
    Array.isArray(changes) &&
    changes.length > 0 &&
    changes.every(
      (c) =>
        c &&
        typeof c === "object" &&
        typeof c.rule_key === "string" &&
        c.rule_key.trim() !== "" &&
        "new_value" in c
    );
  if (!valid) {
    setAdminMessage("adminInvalidShape", true);
    return null;
  }
  return changes;
}

async function submitProposal(event) {
  event.preventDefault();
  const slug = adminSlugInput.value.trim();
  const notice = adminNoticeInput.value.trim();
  if (!slug || !notice) {
    setAdminMessage("adminRequired", true);
    renderAdmin();
    return;
  }
  const changes = parseChanges(adminChangesInput.value);
  if (!changes) {
    renderAdmin();
    return;
  }

  adminSubmitBtn.disabled = true;
  try {
    const data = await adminRequest("/api/admin/proposals", "POST", {
      scheme_slug: slug,
      source_text: notice,
      changes,
    });
    if (data && data.changed === true) {
      state.admin.preview = {
        scheme_slug: slug,
        changes: asObjects(data.changes),
      };
      setAdminMessage("adminSubmitted", false);
      renderAdmin();
      loadProposals();
    } else {
      state.admin.preview = null;
      setAdminMessage("adminNoChange", false);
      renderAdmin();
    }
  } catch (err) {
    handleAdminError(err, true);
  } finally {
    adminSubmitBtn.disabled = false;
  }
}

async function actOnProposal(id, action) {
  state.admin.preview = null;
  try {
    const path = `/api/admin/proposals/${encodeURIComponent(String(id))}/${action}`;
    await adminRequest(path, "POST");
    setAdminMessage(action === "approve" ? "adminApproved" : "adminDismissed", false);
    loadProposals();
  } catch (err) {
    handleAdminError(err, true);
  }
}

// Flat table: rule_key, current value, proposed value. Values are shown as JSON text.
function formatAdminValue(value) {
  const json = JSON.stringify(value);
  return json === undefined ? "" : json;
}

function buildChangesTable(changes) {
  const wrap = el("div", "admin-table-wrap");
  const table = el("table", "admin-table");
  const head = el("tr");
  head.append(
    el("th", "", t(state.lang, "adminColRule")),
    el("th", "", t(state.lang, "adminColCurrent")),
    el("th", "", t(state.lang, "adminColProposed"))
  );
  const thead = el("thead");
  thead.append(head);
  const tbody = el("tbody");
  tbody.replaceChildren(
    ...changes.map((c) => {
      const tr = el("tr");
      tr.append(
        el("td", "", String(c.rule_key ?? "")),
        el("td", "", formatAdminValue(c.old_value)),
        el("td", "", formatAdminValue(c.new_value))
      );
      return tr;
    })
  );
  table.append(thead, tbody);
  wrap.append(table);
  return wrap;
}

function renderAdminPreview() {
  const preview = state.admin.preview;
  adminPreview.replaceChildren();
  adminPreview.hidden = !preview;
  if (!preview) return;
  adminPreview.append(
    el("span", "admin-proposal-slug", preview.scheme_slug),
    buildChangesTable(preview.changes)
  );
}

function buildAdminProposal(p) {
  const card = el("div", "admin-proposal");
  card.append(el("span", "admin-proposal-slug", String(p.scheme_slug ?? "")));
  if (p.created_at) card.append(el("span", "caption", String(p.created_at)));
  card.append(buildChangesTable(asObjects(p.changes)));

  const actions = el("div", "admin-actions");
  const approve = el("button", "btn-primary", t(state.lang, "adminApprove"));
  approve.type = "button";
  approve.addEventListener("click", () => actOnProposal(p.id, "approve"));
  const dismiss = el("button", "btn-skip", t(state.lang, "adminDismiss"));
  dismiss.type = "button";
  dismiss.addEventListener("click", () => actOnProposal(p.id, "dismiss"));
  actions.append(approve, dismiss);
  card.append(actions);
  return card;
}

function renderAdminList() {
  const proposals = state.admin.proposals;
  if (proposals === null) {
    adminList.replaceChildren(el("p", "body", t(state.lang, "loading")));
    return;
  }
  if (proposals === "error") {
    adminList.replaceChildren();
    return;
  }
  if (proposals.length === 0) {
    adminList.replaceChildren(el("p", "body", t(state.lang, "adminNoPending")));
    return;
  }
  adminList.replaceChildren(...proposals.map(buildAdminProposal));
}

function renderAdmin() {
  const admin = state.admin;
  adminBtn.setAttribute("aria-expanded", String(admin.open));
  adminPanel.hidden = !admin.open;
  if (!admin.open) return;

  const loggedIn = admin.token !== "";
  adminLogoutBtn.hidden = !loggedIn;
  adminLoginForm.hidden = loggedIn;
  adminConsole.hidden = !loggedIn;
  adminMessage.hidden = admin.message === null;
  adminMessage.textContent = admin.message ? t(state.lang, admin.message.key) : "";
  adminMessage.classList.toggle("admin-message--error", Boolean(admin.message?.error));
  if (!loggedIn) return;

  renderAdminPreview();
  renderAdminList();
}

// ---------- Module 8: bank-loan call requests ----------
const BANK_ERROR_KEYS = { 404: "bankErr404", 422: "bankNeedPhone", network: "adminErrNetwork" };

function bankFormFor(slug) {
  if (!state.banks.forms[slug]) {
    state.banks.forms[slug] = { on: false, phone: "", message: null, error: false, sending: false };
  }
  return state.banks.forms[slug];
}

async function loadBanks() {
  try {
    const schemes = await fetchList("/api/schemes");
    state.banks.schemes = asObjects(schemes).filter((s) =>
      BANK_LOAN_LANE.test(String(s.lane ?? ""))
    );
  } catch {
    state.banks.schemes = "error";
  }
  renderBank();
}

function renderBank() {
  bankTitle.textContent = t(state.lang, "bankTitle");
  bankGrid.replaceChildren();
  bankNote.textContent = "";
  const schemes = state.banks.schemes;
  if (schemes === null) {
    bankNote.textContent = t(state.lang, "loading");
    return;
  }
  if (schemes === "error") {
    bankNote.textContent = t(state.lang, "bankError");
    return;
  }
  if (schemes.length === 0) {
    bankNote.textContent = t(state.lang, "bankNone");
    return;
  }
  schemes.forEach((s, i) => bankGrid.append(buildBankCard(s, VARIANTS[i % VARIANTS.length])));
}

function buildBankCard(scheme, variant) {
  const slug = String(scheme.slug ?? "");
  const f = bankFormFor(slug);
  const card = el("div", `card bank-card ${variant}`);
  card.append(el("h3", "value", localized(scheme, "name") || slug));

  // The switch is unchecked by default. Nothing is sent unless it is ON and the form is submitted.
  const switchLabel = el("label", "switch");
  const toggle = el("input");
  toggle.type = "checkbox";
  toggle.setAttribute("role", "switch");
  toggle.checked = f.on;
  toggle.disabled = f.sending;
  toggle.addEventListener("change", () => {
    f.on = toggle.checked;
    f.phone = ""; // a number typed before switching off is discarded
    f.message = null;
    renderBank();
  });
  switchLabel.append(toggle, el("span", "body", t(state.lang, "bankCallSwitch")));
  card.append(switchLabel);

  if (f.on) {
    const form = el("form", "admin-form");
    const phoneLabel = el("label", "label", t(state.lang, "bankPhoneLabel"));
    const phone = el("input", "admin-input");
    phone.type = "tel";
    phone.autocomplete = "tel";
    phone.placeholder = t(state.lang, "bankPhonePlaceholder");
    phone.value = f.phone;
    phone.addEventListener("input", () => {
      f.phone = phone.value;
    });
    phoneLabel.append(phone);
    const submit = el("button", "btn-primary", t(state.lang, "bankSubmit"));
    submit.type = "submit";
    submit.disabled = f.sending;
    form.append(phoneLabel, el("p", "caption", t(state.lang, "bankConsentNote")), submit);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      submitBankLead(scheme, f);
    });
    card.append(form);
  }

  if (f.message) {
    const msg = el("p", "admin-message", t(state.lang, f.message));
    msg.setAttribute("role", "status");
    msg.classList.toggle("admin-message--error", f.error);
    card.append(msg);
  }
  return card;
}

// Sends the phone number and opt_in=true only when the switch is ON.
async function submitBankLead(scheme, f) {
  if (!f.on || f.sending) return;
  const phone = f.phone.trim();
  if (!phone) {
    f.message = "bankNeedPhone";
    f.error = true;
    renderBank();
    return;
  }
  f.sending = true;
  f.message = null;
  renderBank();
  try {
    const res = await fetch("/api/leads", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scheme_slug: String(scheme.slug), phone, opt_in: true }),
    });
    if (!res.ok) throw new AdminError(res.status);
    f.on = false;
    f.phone = "";
    f.message = "bankSent";
    f.error = false;
  } catch (err) {
    const code = err instanceof AdminError ? err.code : "other";
    f.message = BANK_ERROR_KEYS[code] || "bankErrGeneric";
    f.error = true;
  } finally {
    f.sending = false;
    renderBank();
  }
}

// ---------- Module 8: partner and sponsor login ----------
const PARTNER_ERROR_KEYS = {
  401: "partnerErr401",
  403: "partnerErr403",
  503: "partnerErr503",
  network: "adminErrNetwork",
};

// The session token is passed as a Bearer header and kept in memory only.
async function partnerRequest(path, token, body) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const init = { method: body === undefined ? "GET" : "POST", headers };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, init);
  } catch {
    throw new AdminError("network");
  }
  if (!res.ok) throw new AdminError(res.status);
  return res.json();
}

function setPartnerMessage(key, error) {
  state.partner.message = { key, error };
}

function forgetPartner() {
  state.partner.token = "";
  state.partner.role = "";
  state.partner.org = "";
  state.partner.leads = null;
  state.partner.impact = null;
}

function handlePartnerError(err) {
  const code = err instanceof AdminError ? err.code : "other";
  if (code === 401) forgetPartner();
  setPartnerMessage(PARTNER_ERROR_KEYS[code] || "adminErrGeneric", true);
  renderPartner();
}

function togglePartner() {
  state.partner.open = !state.partner.open;
  if (state.partner.open) {
    if (!state.partner.token) state.partner.token = DEMO_ADMIN_TOKEN;
    if (!state.partner.role) state.partner.role = "partner";
    loadPartnerView();
    partnerPanel.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }
  renderPartner();
}

async function loginPartner(event) {
  event.preventDefault();
  const username = partnerUserInput.value.trim();
  const password = partnerPassInput.value;
  if (!username || !password) {
    setPartnerMessage("partnerNeedCredentials", true);
    renderPartner();
    return;
  }
  partnerLoginBtn.disabled = true;
  try {
    const data = await partnerRequest("/api/partner/login", "", { username, password });
    if (!data || typeof data.access_token !== "string" || typeof data.role !== "string") {
      throw new AdminError("other");
    }
    partnerPassInput.value = "";
    state.partner.message = null;
    if (data.role === "admin") {
      // Admin sessions reuse the existing admin console (token in sessionStorage, as before).
      state.partner.open = false;
      state.admin.open = true;
      state.admin.token = data.access_token;
      writeAdminToken(data.access_token);
      renderPartner();
      toggleAdminOpenedView();
      return;
    }
    state.partner.token = data.access_token;
    state.partner.role = data.role;
    state.partner.org = typeof data.org_name === "string" ? data.org_name : "";
    partnerUserInput.value = "";
    loadPartnerView();
  } catch (err) {
    handlePartnerError(err);
  } finally {
    partnerLoginBtn.disabled = false;
  }
}

function toggleAdminOpenedView() {
  renderAdmin();
  loadProposals();
  adminPanel.scrollIntoView?.({ behavior: "smooth", block: "start" });
}

function logoutPartner() {
  forgetPartner();
  state.partner.message = null;
  partnerLoginForm.reset();
  renderPartner();
}

// Partners get the opt-in lead list; sponsors get aggregate impact numbers.
async function loadPartnerView() {
  const token = state.partner.token || DEMO_ADMIN_TOKEN;
  state.partner.token = token;
  const role = state.partner.role || "partner";
  state.partner.role = role;
  tabPartnerBtn.classList.toggle("active", role === "partner");
  tabSponsorBtn.classList.toggle("active", role === "sponsor");
  try {
    if (role === "partner") {
      state.partner.leads = null;
      renderPartner();
      const data = await partnerRequest("/api/partner/leads", token);
      if (!Array.isArray(data)) throw new AdminError("other");
      if (state.partner.token !== token) return; // logged out while loading
      state.partner.leads = asObjects(data);
    } else if (role === "sponsor") {
      state.partner.impact = null;
      renderPartner();
      const data = await partnerRequest("/api/sponsor/impact", token);
      if (!data || typeof data !== "object") throw new AdminError("other");
      if (state.partner.token !== token) return; // logged out while loading
      state.partner.impact = data;
    }
  } catch (err) {
    if (state.partner.token !== token) return;
    if (role === "partner") state.partner.leads = "error";
    if (role === "sponsor") state.partner.impact = "error";
    handlePartnerError(err);
    return;
  }
  renderPartner();
}

function renderPartner() {
  const p = state.partner;
  partnerLinkBtn.setAttribute("aria-expanded", String(p.open));
  partnerPanel.hidden = !p.open;
  if (!p.open) return;

  const loggedIn = p.token !== "";
  partnerLogoutBtn.hidden = !loggedIn;
  partnerLoginForm.hidden = loggedIn;
  partnerMessage.hidden = p.message === null;
  partnerMessage.textContent = p.message ? t(state.lang, p.message.key) : "";
  partnerMessage.classList.toggle("admin-message--error", Boolean(p.message?.error));
  partnerView.replaceChildren();
  if (!loggedIn) return;
  if (p.role === "partner") partnerView.append(buildLeadsView(p.leads));
  if (p.role === "sponsor") partnerView.append(buildImpactView(p.impact));
}

function formatPhone(phone) {
  if (!phone) return "";
  const cleaned = String(phone).replace(/\D/g, "");
  if (cleaned.length === 10) {
    return `${cleaned.slice(0, 5)} ${cleaned.slice(5)}`;
  }
  return String(phone);
}

function buildLeadsView(leads) {
  const wrap = el("div", "");
  wrap.append(el("h2", "", t(state.lang, "leadsTitle")));
  if (leads === null) {
    wrap.append(el("p", "body", t(state.lang, "loading")));
    return wrap;
  }
  if (leads === "error") return wrap;
  if (leads.length === 0) {
    wrap.append(el("p", "body", t(state.lang, "leadsNone")));
    return wrap;
  }
  const table = el("table", "admin-table");
  const head = el("tr");
  head.append(
    el("th", "", t(state.lang, "leadColPhone")),
    el("th", "", t(state.lang, "leadColScheme")),
    el("th", "", t(state.lang, "leadColConsent")),
    el("th", "", "Action / Status")
  );
  const thead = el("thead");
  thead.append(head);
  const tbody = el("tbody");
  tbody.replaceChildren(
    ...leads.map((row) => {
      const tr = el("tr");
      const actionTd = el("td", "");
      const leadKey = `${row.phone}_${row.scheme_slug}`;
      const isDone = state.partner.contactedLeads.has(leadKey);
      const callBtn = el(
        "button",
        isDone ? "lead-action-btn lead-action-btn--done" : "lead-action-btn",
        isDone ? "✅ Callback Done" : "📞 Simulate Call"
      );
      callBtn.type = "button";
      callBtn.addEventListener("click", () => {
        if (state.partner.contactedLeads.has(leadKey)) {
          state.partner.contactedLeads.delete(leadKey);
        } else {
          state.partner.contactedLeads.add(leadKey);
        }
        renderPartner();
      });
      actionTd.append(callBtn);
      tr.append(
        el("td", "", `+91 ${formatPhone(row.phone)}`),
        el("td", "", String(row.scheme_slug ?? "")),
        el("td", "", String(row.consent_at ?? "")),
        actionTd
      );
      return tr;
    })
  );
  table.append(thead, tbody);
  const tableWrap = el("div", "admin-table-wrap");
  tableWrap.append(table);
  wrap.append(tableWrap);
  return wrap;
}

function impactStat(label, value) {
  const item = el("div", "impact-stat");
  item.append(el("span", "label", label), el("span", "value", value));
  return item;
}

function impactList(title, items, field, recorded) {
  const section = el("div", "impact-list");
  section.append(el("h3", "checklist-heading", title));
  if (items.length === 0 || recorded === false) {
    section.append(el("p", "body", t(state.lang, "impactNone")));
    return section;
  }
  const list = el("ol", "checklist-steps");
  list.replaceChildren(
    ...items.map((item) =>
      el(
        "li",
        "",
        `${String(item[field] ?? "")} — ${t(state.lang, "impactSessions", {
          count: Number(item.sessions) || 0,
        })}`
      )
    )
  );
  section.append(list);
  return section;
}

function buildImpactView(impact) {
  const wrap = el("div", "");
  wrap.append(el("h2", "", t(state.lang, "impactTitle")));
  if (impact === null) {
    wrap.append(el("p", "body", t(state.lang, "loading")));
    return wrap;
  }
  if (impact === "error") return wrap;
  const avg =
    typeof impact.average_cost_per_session === "number"
      ? String(impact.average_cost_per_session)
      : t(state.lang, "impactNotRecorded");
  wrap.append(
    impactStat(t(state.lang, "impactWomen"), String(impact.total_women_helped ?? 0)),
    impactStat(t(state.lang, "impactAvgCost"), avg),
    impactList(
      t(state.lang, "impactTopDistricts"),
      asObjects(impact.top_districts),
      "district",
      impact.districts_recorded
    ),
    impactList(
      t(state.lang, "impactTopSchemes"),
      asObjects(impact.top_schemes),
      "scheme_slug",
      true
    )
  );
  return wrap;
}

// ---------- Boot ----------
renderAll();
if (!state.voiceOk) renderVoice();
loadHealth();
loadQuick();
loadBanks();
