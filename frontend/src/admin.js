/**
 * HerScheme - Admin & Verification Console (Flat Glassmorphism & Structural Grid UI)
 */

const TOKEN = "judge-admin-demo";
const AUTH = { Authorization: `Bearer ${TOKEN}` };

const SCHEME_DISPLAY_NAMES = {
  "pmegp": "Prime Minister's Employment Generation Programme (PMEGP)",
  "pm-mudra": "Pradhan Mantri Mudra Yojana (Mudra Loans)",
  "stree-nidhi": "Stree Nidhi Credit Cooperative (SERP Telangana)",
  "indira-mahila-shakti": "Indira Mahila Shakti Scheme",
  "pm-vishwakarma": "PM Vishwakarma Scheme",
  "telangana-msme-policy": "Telangana MSME Development Policy",
};

const RULE_DISPLAY_NAMES = {
  "max_loan": "Maximum Project Cost / Loan Cap",
  "subsidy_rural_women": "Rural Women Entrepreneur Subsidy",
  "interest_rebate_pct": "Interest Rebate on Prompt Repayment",
  "expedited_processing_days": "Expedited Processing Timeline (Days)",
  "min_age": "Minimum Applicant Age",
  "max_age": "Maximum Applicant Age",
  "shg_membership_required": "SHG Membership Prerequisite",
};

function formatRuleKey(key) {
  return RULE_DISPLAY_NAMES[key] || key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatRuleVal(val) {
  if (val === null || val === undefined) return "Not Set";
  if (typeof val === "number" && val >= 1000) {
    return "₹" + val.toLocaleString("en-IN");
  }
  return String(val);
}

function getSchemeTitle(slug) {
  return SCHEME_DISPLAY_NAMES[slug] || slug;
}

let activeMode = "update"; // "update" | "new"

async function api(path, method = "GET", body = null) {
  const opts = {
    method,
    headers: { ...AUTH },
  };
  if (body) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    let errText = res.statusText;
    try {
      const j = await res.json();
      errText = j.detail || errText;
    } catch {}
    throw new Error(errText);
  }
  return res.json();
}

const app = document.getElementById("admin-app");

function renderPage() {
  app.innerHTML = `
    <!-- Topbar Navigation -->
    <header class="portal-topbar">
      <a href="/" class="portal-brand-link brand">
        HerScheme
      </a>
      <div style="display:flex; align-items:center; gap:12px;">
        <span class="portal-role-tag">🏛️ Admin Console</span>
        <a href="/" class="btn-skip" style="text-decoration:none; display:inline-flex; align-items:center; font-size:12px;">
          ← Return to Scheme Finder
        </a>
      </div>
    </header>

    <!-- Unified Glass Macro-Container -->
    <main class="portal-glass">
      <div class="portal-container">
        <!-- Title & Header Area -->
        <div class="portal-header-area">
          <h1 class="portal-page-title">Policy Verification & Scheme Management</h1>
          <p class="portal-page-desc">
            Official Government Order (G.O.) ingestion, parameter diff verification, and scheme database synchronization.
          </p>

          <div class="blended-banner">
            <span class="blended-banner-badge">⚡ SIMULATION MODE</span>
            <p class="blended-banner-text">
              <strong>Official Policy Ingestion:</strong> Scheme eligibility rules, financial assistance limits, and subsidies reside directly in the verified state database. Ingest official gazette notifications, preview parameter differences, and approve updates with an immutable audit trail.
            </p>
          </div>
        </div>

        <div id="alert-container"></div>

        <!-- Section 1: Ingest Government Order -->
        <section class="portal-section">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:12px;">
            <div>
              <h2 class="section-title">Government Order (G.O.) Ingestion</h2>
              <p class="section-desc">Submit official gazette notifications to update rules or create new schemes.</p>
            </div>
            <div class="segmented-pill-bar">
              <button class="segmented-pill-btn ${activeMode === 'update' ? 'active' : ''}" id="mode-update-btn">
                Update Existing Scheme
              </button>
              <button class="segmented-pill-btn ${activeMode === 'new' ? 'active' : ''}" id="mode-new-btn">
                + Ingest New Scheme
              </button>
            </div>
          </div>

          <!-- File Drop Zone -->
          <div class="blended-dropzone" id="drop-zone">
            <input type="file" id="file-upload" accept=".pdf,.txt,.json,.doc,.docx" style="display:none;" />
            <div class="dropzone-icon">📄</div>
            <p class="dropzone-prompt">Upload Government Order (PDF / Doc / Text)</p>
            <p class="dropzone-hint">Extracts loan limits, subsidy percentages, and document checklists automatically</p>
          </div>

          <!-- Sample Quick Chips -->
          <div class="chips-bar">
            <span class="chips-label">Sample Data:</span>
            <button class="glass-chip" id="chip-pmegp">⚡ Load PMEGP Subsidy G.O.</button>
            <button class="glass-chip" id="chip-stree">⚡ Load Stree Nidhi Circular</button>
            <button class="glass-chip" id="chip-drone">⚡ Load New "Drone Didi" Scheme</button>
          </div>

          <!-- Form Area -->
          <form id="ingest-form" class="portal-form-grid">
            ${activeMode === "update" ? renderUpdateFields() : renderNewSchemeFields()}
            <div style="margin-top:8px;">
              <button type="submit" class="cta-purple" id="submit-btn">
                <span>🚀</span>
                <span>${activeMode === "update" ? "Submit Proposal for Verification" : "Ingest into Database"}</span>
              </button>
            </div>
          </form>
        </section>

        <!-- Section 2: Pending Approvals -->
        <section class="portal-section">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
            <div>
              <h2 class="section-title">Pending Approvals & Live Verification Diff</h2>
              <p class="section-desc">Changes take effect across the platform only after explicit verification.</p>
            </div>
            <button class="glass-chip" id="refresh-btn">🔄 Refresh</button>
          </div>
          <div id="proposals-list">
            <p style="color:#64748b; font-size:12px;">Loading pending proposals...</p>
          </div>
        </section>
      </div>
    </main>
  `;

  bindEvents();
  loadProposals();
}

function renderUpdateFields() {
  return `
    <div class="portal-field-group">
      <label class="portal-field-label" for="scheme-select">Target Scheme</label>
      <select class="portal-select" id="scheme-select" required>
        <option value="pmegp">Prime Minister's Employment Generation Programme (PMEGP)</option>
        <option value="pm-mudra">Pradhan Mantri Mudra Yojana (Mudra Loans)</option>
        <option value="stree-nidhi">Stree Nidhi Credit Cooperative (SERP Telangana)</option>
        <option value="indira-mahila-shakti">Indira Mahila Shakti Scheme</option>
        <option value="pm-vishwakarma">PM Vishwakarma Scheme</option>
        <option value="telangana-msme-policy">Telangana MSME Development Policy</option>
      </select>
    </div>

    <div class="portal-field-group">
      <label class="portal-field-label" for="notice-input">Government Order / Gazette Notification Reference</label>
      <textarea class="portal-textarea" id="notice-input" placeholder="Paste notification excerpt, circular number, or government order..." required rows="3"></textarea>
    </div>

    <div class="portal-form-grid portal-form-grid-2">
      <div class="portal-field-group">
        <label class="portal-field-label" for="rule-key-input">Rule / Policy Criterion</label>
        <select class="portal-select" id="rule-key-input">
          <option value="max_loan">Maximum Project Cost / Loan Cap (₹)</option>
          <option value="subsidy_rural_women">Rural Women Entrepreneur Subsidy (%)</option>
          <option value="interest_rebate_pct">Interest Rebate on Prompt Repayment (%)</option>
          <option value="expedited_processing_days">Processing Days</option>
        </select>
      </div>

      <div class="portal-field-group">
        <label class="portal-field-label" for="rule-val-input">Proposed Value</label>
        <input type="text" class="portal-input" id="rule-val-input" placeholder="e.g. 5000000 or 35%" required />
      </div>
    </div>
  `;
}

function renderNewSchemeFields() {
  return `
    <div class="portal-form-grid portal-form-grid-2">
      <div class="portal-field-group">
        <label class="portal-field-label" for="new-name-en">Scheme Name (English)</label>
        <input type="text" class="portal-input" id="new-name-en" placeholder="e.g. Telangana Drone Didi Agri Scheme" required />
      </div>
      <div class="portal-field-group">
        <label class="portal-field-label" for="new-name-te">Scheme Name (Telugu)</label>
        <input type="text" class="portal-input" id="new-name-te" placeholder="e.g. తెలంగాణ డ్రోన్ దీదీ పథకం" />
      </div>
    </div>

    <div class="portal-form-grid portal-form-grid-2">
      <div class="portal-field-group">
        <label class="portal-field-label" for="new-level">Government Level</label>
        <select class="portal-select" id="new-level">
          <option value="state">State (Telangana)</option>
          <option value="central">Central (Government of India)</option>
        </select>
      </div>
      <div class="portal-field-group">
        <label class="portal-field-label" for="new-lane">Category / Sector</label>
        <select class="portal-select" id="new-lane">
          <option value="agriculture">Agriculture & Agri-Tech</option>
          <option value="micro-enterprise">Micro-Enterprise & Business</option>
          <option value="shg">Self Help Groups (SHG)</option>
          <option value="skill">Skill Training & Technology</option>
        </select>
      </div>
    </div>

    <div class="portal-field-group">
      <label class="portal-field-label" for="new-desc">Eligibility & Benefits Summary</label>
      <textarea class="portal-textarea" id="new-desc" placeholder="Summary of eligibility criteria, target age group, and assistance provided..." required rows="3"></textarea>
    </div>

    <div class="portal-form-grid portal-form-grid-2">
      <div class="portal-field-group">
        <label class="portal-field-label" for="new-url">Official Government Website URL</label>
        <input type="url" class="portal-input" id="new-url" placeholder="https://..." value="https://telangana.gov.in" required />
      </div>
      <div class="portal-field-group">
        <label class="portal-field-label" for="new-cap">Initial Project / Loan Cap (₹)</label>
        <input type="number" class="portal-input" id="new-cap" placeholder="e.g. 1500000" value="1500000" />
      </div>
    </div>
  `;
}

function showAlert(message, type = "success") {
  const container = document.getElementById("alert-container");
  if (!container) return;
  container.innerHTML = `
    <div class="blended-alert ${type === 'success' ? 'blended-alert-success' : 'blended-alert-error'}">
      <span>${type === 'success' ? '✅' : '⚠️'} ${message}</span>
      <button style="border:none;background:transparent;cursor:pointer;font-weight:500;" onclick="this.parentElement.remove()">✕</button>
    </div>
  `;
}

function bindEvents() {
  document.getElementById("mode-update-btn")?.addEventListener("click", () => {
    activeMode = "update";
    renderPage();
  });
  document.getElementById("mode-new-btn")?.addEventListener("click", () => {
    activeMode = "new";
    renderPage();
  });

  const dropZone = document.getElementById("drop-zone");
  const fileInput = document.getElementById("file-upload");
  dropZone?.addEventListener("click", () => fileInput?.click());
  fileInput?.addEventListener("change", (e) => {
    if (e.target.files?.length) {
      const f = e.target.files[0];
      showAlert(`Document "${f.name}" analyzed successfully. Parameters pre-filled into verification form.`);
      simulateFileFill(f.name);
    }
  });

  document.getElementById("chip-pmegp")?.addEventListener("click", () => {
    if (activeMode !== "update") {
      activeMode = "update";
      renderPage();
    }
    const select = document.getElementById("scheme-select");
    const notice = document.getElementById("notice-input");
    const key = document.getElementById("rule-key-input");
    const val = document.getElementById("rule-val-input");
    if (select) select.value = "pmegp";
    if (notice) notice.value = "Ministry of MSME Gazette Notification 2026: Enhancing maximum project cost under PMEGP manufacturing sector for women entrepreneurs to Rs. 50,00,000 and subsidy to 35% in rural areas.";
    if (key) key.value = "max_loan";
    if (val) val.value = "5000000";
    showAlert("Sample PMEGP Gazette Notification loaded. Click 'Submit Proposal' to preview verification diff.");
  });

  document.getElementById("chip-stree")?.addEventListener("click", () => {
    if (activeMode !== "update") {
      activeMode = "update";
      renderPage();
    }
    const select = document.getElementById("scheme-select");
    const notice = document.getElementById("notice-input");
    const key = document.getElementById("rule-key-input");
    const val = document.getElementById("rule-val-input");
    if (select) select.value = "stree-nidhi";
    if (notice) notice.value = "SERP Telangana Circular No. 18/2026: Enhancing prompt repayment interest rebate for women SHG micro-enterprises to 4%.";
    if (key) key.value = "interest_rebate_pct";
    if (val) val.value = "4";
    showAlert("Sample Stree Nidhi circular loaded. Click 'Submit Proposal' to test.");
  });

  document.getElementById("chip-drone")?.addEventListener("click", () => {
    if (activeMode !== "new") {
      activeMode = "new";
      renderPage();
    }
    const name = document.getElementById("new-name-en");
    const te = document.getElementById("new-name-te");
    const desc = document.getElementById("new-desc");
    const cap = document.getElementById("new-cap");
    if (name) name.value = "Telangana Drone Didi & Precision Agri Scheme";
    if (te) te.value = "తెలంగాణ డ్రోన్ దీదీ పథకం";
    if (desc) desc.value = "Equipping rural women and SHG members with agricultural drone operation skills, equipment subsidies up to 80%, and commercial pesticide spraying licenses.";
    if (cap) cap.value = "1000000";
    showAlert("Sample Drone Didi scheme loaded. Click 'Ingest into Database' to create.");
  });

  document.getElementById("refresh-btn")?.addEventListener("click", loadProposals);
  document.getElementById("ingest-form")?.addEventListener("submit", handleSubmit);
}

function simulateFileFill(filename) {
  if (activeMode === "update") {
    const notice = document.getElementById("notice-input");
    const key = document.getElementById("rule-key-input");
    const val = document.getElementById("rule-val-input");
    if (notice) notice.value = `Official Order extracted from [${filename}]: G.O. Ms. No. 58 revision of financial assistance limits.`;
    if (key) key.value = "max_loan";
    if (val) val.value = "4000000";
  } else {
    const name = document.getElementById("new-name-en");
    const desc = document.getElementById("new-desc");
    if (name) name.value = filename.replace(/\.[^/.]+$/, "").replace(/[_-]/g, " ");
    if (desc) desc.value = `Scheme details parsed from uploaded government gazette document ${filename}.`;
  }
}

async function handleSubmit(e) {
  e.preventDefault();
  const submitBtn = document.getElementById("submit-btn");
  if (submitBtn) submitBtn.disabled = true;

  try {
    if (activeMode === "update") {
      const schemeSlug = document.getElementById("scheme-select").value;
      const noticeText = document.getElementById("notice-input").value;
      const ruleKey = document.getElementById("rule-key-input").value;
      let rawVal = document.getElementById("rule-val-input").value.trim();
      let newVal = isNaN(Number(rawVal)) ? rawVal : Number(rawVal);

      const res = await api("/api/admin/proposals", "POST", {
        scheme_slug: schemeSlug,
        source_text: noticeText,
        changes: [{ rule_key: ruleKey, new_value: newVal }],
      });

      if (res.changed) {
        showAlert(`Proposal #${res.proposal_id} created for ${getSchemeTitle(schemeSlug)}. Inspect diff below and click 'Approve & Publish' to update live rules.`);
        loadProposals();
      } else {
        showAlert("No change detected: proposed value matches live database rules.", "error");
      }
    } else {
      const nameEn = document.getElementById("new-name-en").value;
      const nameTe = document.getElementById("new-name-te").value;
      const level = document.getElementById("new-level").value;
      const lane = document.getElementById("new-lane").value;
      const desc = document.getElementById("new-desc").value;
      const url = document.getElementById("new-url").value;
      const cap = Number(document.getElementById("new-cap").value) || 1000000;

      const res = await api("/api/admin/schemes", "POST", {
        name_en: nameEn,
        name_te: nameTe,
        level,
        lane,
        description: desc,
        official_url: url,
        rules: [{ rule_key: "max_loan", new_value: cap }],
      });

      showAlert(`🎉 Scheme "${res.name_en}" ingested into database with published status!`, "success");
      activeMode = "update";
      renderPage();
    }
  } catch (err) {
    showAlert("Error: " + err.message, "error");
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
}

async function loadProposals() {
  const container = document.getElementById("proposals-list");
  if (!container) return;

  try {
    const data = await api("/api/admin/proposals");
    if (!data || data.length === 0) {
      container.innerHTML = `
        <div style="text-align:center; padding: 24px; color: #64748b;">
          <p style="font-size: 13px; margin: 0 0 4px; font-weight: 500;">All pending proposals have been reviewed and published.</p>
          <p style="font-size: 11.5px; margin: 0;">Submit a new Government Order above or click a sample chip to test.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = data.map((p) => `
      <div class="blended-proposal-item" id="proposal-${p.id}">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px; flex-wrap:wrap; gap:12px;">
          <div>
            <div style="font-size:15px; font-weight:500; color:#0f172a;">🏛️ ${getSchemeTitle(p.scheme_slug)}</div>
            <div style="font-size:11.5px; color:#64748b; margin-top:2px;">Proposal Ref #${p.id} • Submitted: ${new Date(p.created_at || Date.now()).toLocaleString("en-IN")}</div>
          </div>
          <div style="display:flex; gap:8px;">
            <button class="cta-success" onclick="window.approveProposal(${p.id})">✅ Approve & Publish</button>
            <button class="cta-dismiss" onclick="window.dismissProposal(${p.id})">❌ Dismiss</button>
          </div>
        </div>

        <table class="blended-table">
          <thead>
            <tr>
              <th>Rule / Policy Criterion</th>
              <th>Current Live Database Value</th>
              <th>Proposed Value</th>
            </tr>
          </thead>
          <tbody>
            ${p.changes.map((c) => `
              <tr>
                <td><strong>${formatRuleKey(c.rule_key)}</strong></td>
                <td><span class="diff-old">${formatRuleVal(c.old_value)}</span></td>
                <td><span class="diff-new">${formatRuleVal(c.new_value)}</span></td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `).join("");
  } catch (err) {
    container.innerHTML = `<p style="color:#dc2626; font-size:12px;">Failed to load proposals: ${err.message}</p>`;
  }
}

window.approveProposal = async function (id) {
  try {
    await api(`/api/admin/proposals/${id}/approve`, "POST");
    showAlert(`Proposal #${id} approved! Live database rules updated and verified timestamp recorded.`, "success");
    loadProposals();
  } catch (err) {
    showAlert("Failed to approve: " + err.message, "error");
  }
};

window.dismissProposal = async function (id) {
  try {
    await api(`/api/admin/proposals/${id}/dismiss`, "POST");
    showAlert(`Proposal #${id} dismissed.`, "success");
    loadProposals();
  } catch (err) {
    showAlert("Failed to dismiss: " + err.message, "error");
  }
};

renderPage();
