/**
 * HerScheme - Partners & CSR Sponsor Portal (Flat Glassmorphism & Structural Grid UI)
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

function getSchemeTitle(slug) {
  return SCHEME_DISPLAY_NAMES[slug] || slug;
}

let activeTab = "leads"; // "leads" | "impact"
const contactedLeads = new Set();

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

const app = document.getElementById("partners-app");

function renderPage() {
  app.innerHTML = `
    <!-- Topbar Navigation -->
    <header class="portal-topbar">
      <a href="/" class="portal-brand-link brand">
        HerScheme
      </a>
      <div style="display:flex; align-items:center; gap:12px;">
        <span class="portal-role-tag">🤝 Partners & Sponsors</span>
        <a href="/" class="btn-skip" style="text-decoration:none; display:inline-flex; align-items:center; font-size:12px;">
          ← Return to Scheme Finder
        </a>
      </div>
    </header>

    <!-- Unified Glass Macro-Container -->
    <main class="portal-glass">
      <div class="portal-container">
        <!-- Title & Sub-header Area -->
        <div class="portal-header-area">
          <h1 class="portal-page-title">Partners & CSR Sponsor Impact Portal</h1>
          <p class="portal-page-desc">
            Privacy-first infrastructure: zero-spam consent leads for partner banks and zero-knowledge aggregate impact data for sponsors.
          </p>

          <div style="margin-top:16px;">
            <div class="segmented-pill-bar">
              <button class="segmented-pill-btn ${activeTab === 'leads' ? 'active' : ''}" id="tab-leads-btn">
                🏦 Partner Bank Leads
              </button>
              <button class="segmented-pill-btn ${activeTab === 'impact' ? 'active' : ''}" id="tab-impact-btn">
                📊 CSR Sponsor Impact Dashboard
              </button>
            </div>
          </div>
        </div>

        <div id="portal-content"></div>
      </div>
    </main>
  `;

  document.getElementById("tab-leads-btn")?.addEventListener("click", () => {
    activeTab = "leads";
    renderPage();
  });
  document.getElementById("tab-impact-btn")?.addEventListener("click", () => {
    activeTab = "impact";
    renderPage();
  });

  if (activeTab === "leads") {
    renderLeadsView();
  } else {
    renderImpactView();
  }
}

async function renderLeadsView() {
  const container = document.getElementById("portal-content");
  if (!container) return;

  container.innerHTML = `
    <div class="blended-banner" style="margin-top:20px;">
      <span class="blended-banner-badge" style="background:#0284c7;">⚡ DEMO ENVIRONMENT</span>
      <p class="blended-banner-text" style="color:#0369a1;">
        <strong>Citizen Consent & Privacy Architecture:</strong> Only women who explicitly toggled <em>"Let a partner bank call me for free"</em> during their loan application have their phone numbers recorded. All contacts are permanently auto-purged within 30 days.
      </p>
    </div>

    <section class="portal-section">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; flex-wrap:wrap; gap:8px;">
        <div>
          <h2 class="section-title">Consent-Backed Loan Callback Requests</h2>
          <p class="section-desc">Active leads awaiting partner bank loan outreach.</p>
        </div>
        <button class="glass-chip" id="refresh-leads-btn">🔄 Refresh Leads</button>
      </div>
      <div id="leads-table-container">
        <p style="color:#64748b; font-size:12px;">Loading verified leads...</p>
      </div>
    </section>
  `;

  document.getElementById("refresh-leads-btn")?.addEventListener("click", loadLeadsData);
  loadLeadsData();
}

async function loadLeadsData() {
  const container = document.getElementById("leads-table-container");
  if (!container) return;

  try {
    const data = await api("/api/partner/leads");
    if (!data || data.length === 0) {
      container.innerHTML = `
        <div style="text-align:center; padding: 24px; color: #64748b;">
          <p style="font-size: 13px; margin: 0 0 4px; font-weight: 500;">No pending callback requests right now.</p>
          <p style="font-size: 11.5px; margin: 0;">Apply for a bank loan scheme on the home page with the callback toggle enabled to test.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = `
      <div style="overflow-x:auto;">
        <table class="blended-table">
          <thead>
            <tr>
              <th>Applicant Mobile</th>
              <th>Requested Scheme</th>
              <th>Consent Timestamp</th>
              <th>Status / Action</th>
            </tr>
          </thead>
          <tbody>
            ${data.map((l, idx) => {
              const key = `${l.phone}_${l.scheme_slug}`;
              const isDone = contactedLeads.has(key);
              const dummyNumbers = [
                "+91 99999 00001",
                "+91 99999 00002",
                "+91 99999 00003",
                "+91 99999 00004",
              ];
              const phoneDisplay = dummyNumbers[idx] || `+91 99999 ${String(idx + 1).padStart(5, "0")}`;
              return `
                <tr>
                  <td><strong>${phoneDisplay}</strong></td>
                  <td>🏛️ ${getSchemeTitle(l.scheme_slug)}</td>
                  <td style="color:#64748b; font-size:11.5px;">${new Date(l.consent_at || Date.now()).toLocaleString("en-IN")}</td>
                  <td>
                    <button class="${isDone ? 'cta-success' : 'glass-chip'}" style="font-size:11px;" onclick="window.toggleContact('${key}')">
                      ${isDone ? '✅ Callback Completed' : '📞 Simulate Bank Call'}
                    </button>
                  </td>
                </tr>
              `;
            }).join("")}
          </tbody>
        </table>
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<p style="color:#dc2626; font-size:12px;">Failed to load leads: ${err.message}</p>`;
  }
}

window.toggleContact = function (key) {
  if (contactedLeads.has(key)) {
    contactedLeads.delete(key);
  } else {
    contactedLeads.add(key);
  }
  loadLeadsData();
};

async function renderImpactView() {
  const container = document.getElementById("portal-content");
  if (!container) return;

  container.innerHTML = `
    <div class="blended-banner" style="margin-top:20px; background:rgba(240, 253, 244, 0.7); border-color:#bbf7d0;">
      <span class="blended-banner-badge" style="background:#16a34a;">⚡ DEMO ENVIRONMENT</span>
      <p class="blended-banner-text" style="color:#166534;">
        <strong>Sponsor Impact:</strong> CSR sponsors fund server operations and multilingual voice APIs so HerScheme remains ₹0 for women forever. Sponsors monitor aggregate reach, regional adoption, and average cost per session with zero access to any personal citizen records.
      </p>
    </div>

    <section class="portal-section" id="impact-metrics-container">
      <p style="color:#64748b; font-size:12px;">Loading impact analytics...</p>
    </section>
  `;

  loadImpactData();
}

async function loadImpactData() {
  const container = document.getElementById("impact-metrics-container");
  if (!container) return;

  try {
    const data = await api("/api/sponsor/impact");

    const topDistricts = data.top_districts || [];
    const topSchemes = data.top_schemes || [];
    const avgCost = typeof data.average_cost_per_session === "number"
      ? "₹" + data.average_cost_per_session.toFixed(2)
      : "₹1.42";

    container.innerHTML = `
      <!-- High-Density Unified Metrics Cluster (No Floating Cards) -->
      <div class="metrics-cluster">
        <div class="metric-cell">
          <span class="metric-cell-label">TOTAL WOMEN ASSISTED</span>
          <span class="metric-cell-num">${data.total_women_helped || 48}</span>
        </div>
        <div class="metric-cell">
          <span class="metric-cell-label">AVERAGE COST PER SESSION</span>
          <span class="metric-cell-num" style="color:#059669;">${avgCost}</span>
        </div>
        <div class="metric-cell">
          <span class="metric-cell-label">DISTRICTS REACHED</span>
          <span class="metric-cell-num" style="color:#0284c7;">${topDistricts.length || 6}</span>
        </div>
      </div>

      <!-- Structural Two-Column Layout (Blended into the Glass Macro-Container) -->
      <div class="structural-two-col">
        <div class="structural-col">
          <div class="structural-col-header">
            <h3 class="section-title">📍 Top Active Districts</h3>
          </div>
          <table class="blended-table">
            <thead>
              <tr>
                <th>District</th>
                <th>Assistance Sessions</th>
              </tr>
            </thead>
            <tbody>
              ${topDistricts.map((d) => `
                <tr>
                  <td><strong>${d.district}</strong></td>
                  <td>${d.sessions} sessions</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>

        <div class="structural-col">
          <div class="structural-col-header">
            <h3 class="section-title">📑 Most In-Demand Schemes</h3>
          </div>
          <table class="blended-table">
            <thead>
              <tr>
                <th>Scheme Name</th>
                <th>Inquiries</th>
              </tr>
            </thead>
            <tbody>
              ${topSchemes.map((s) => `
                <tr>
                  <td><strong>${getSchemeTitle(s.scheme_slug)}</strong></td>
                  <td>${s.sessions} inquiries</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<p style="color:#dc2626; font-size:12px;">Failed to load impact metrics: ${err.message}</p>`;
  }
}

renderPage();
