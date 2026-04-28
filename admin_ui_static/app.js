const state = {
  profiles: [],
  selectedProfileId: "",
};

const els = {
  backendLabel: document.getElementById("backendLabel"),
  profileCount: document.getElementById("profileCount"),
  profileList: document.getElementById("profileList"),
  profileEditor: document.getElementById("profileEditor"),
  profileStatus: document.getElementById("profileStatus"),
  selectedProfileTitle: document.getElementById("selectedProfileTitle"),
  selectedProfileMeta: document.getElementById("selectedProfileMeta"),
  auditCount: document.getElementById("auditCount"),
  auditRecipient: document.getElementById("auditRecipient"),
  auditFamily: document.getElementById("auditFamily"),
  auditClassification: document.getElementById("auditClassification"),
  auditRun: document.getElementById("auditRun"),
  auditLimit: document.getElementById("auditLimit"),
  auditSummary: document.getElementById("auditSummary"),
  auditRows: document.getElementById("auditRows"),
};

document.querySelectorAll(".nav-tab").forEach((button) => {
  button.addEventListener("click", () => switchView(button.dataset.view));
});

document.getElementById("newProfileButton").addEventListener("click", newProfile);
document.getElementById("reloadProfilesButton").addEventListener("click", loadProfiles);
document.getElementById("validateProfileButton").addEventListener("click", validateProfile);
document.getElementById("normalizeProfileButton").addEventListener("click", normalizeProfile);
document.getElementById("saveProfileButton").addEventListener("click", saveProfile);
document.getElementById("reloadAuditButton").addEventListener("click", loadAudit);
document.getElementById("auditFilters").addEventListener("change", loadAudit);
els.auditLimit.addEventListener("input", debounce(loadAudit, 250));

init();

async function init() {
  await loadHealth();
  await loadProfiles();
  await loadAuditOptions();
  await loadAudit();
}

function switchView(viewId) {
  document.querySelectorAll(".nav-tab").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.view === viewId);
  });
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("is-active", view.id === viewId);
  });
}

async function loadHealth() {
  const health = await apiGet("/api/health");
  const fallback = health.using_fallback ? " fallback" : "";
  const label = health.database_label ? ` - ${health.database_label}` : "";
  els.backendLabel.textContent = `${health.backend}${fallback}${label}`;
}

async function loadProfiles() {
  const payload = await apiGet("/api/profiles");
  state.profiles = payload.profiles || [];
  els.profileCount.textContent = `${state.profiles.length} profile${state.profiles.length === 1 ? "" : "s"}`;
  renderProfileList();
  if (!state.selectedProfileId && state.profiles.length) {
    await selectProfile(state.profiles[0].id);
  }
}

function renderProfileList() {
  els.profileList.innerHTML = "";
  if (!state.profiles.length) {
    const empty = document.createElement("p");
    empty.textContent = "No profiles.";
    els.profileList.appendChild(empty);
    return;
  }

  state.profiles.forEach((profile) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `profile-item${profile.id === state.selectedProfileId ? " is-active" : ""}`;
    button.innerHTML = `
      <strong>${escapeHtml(profile.id)}</strong>
      <span>${escapeHtml(profile.email || "-")}</span>
      <span>${profile.enabled ? "enabled" : "disabled"} - ${escapeHtml((profile.target_roles || []).join(", ") || "no roles")}</span>
    `;
    button.addEventListener("click", () => selectProfile(profile.id));
    els.profileList.appendChild(button);
  });
}

async function selectProfile(profileId) {
  const payload = await apiGet(`/api/profiles/${encodeURIComponent(profileId)}`);
  state.selectedProfileId = profileId;
  els.profileEditor.value = JSON.stringify(payload.profile, null, 2);
  renderSelectedProfile(payload.summary);
  setProfileStatus("", "");
  renderProfileList();
}

function newProfile() {
  const profile = {
    id: "new-recipient",
    enabled: true,
    delivery: {
      email: "recipient@example.com",
    },
    candidate: {
      summary: "",
      education_status: "",
      target_roles: [
        {
          id: "swe",
        },
      ],
    },
    job_preferences: {
      target_seniority: {
        max_explicit_years: 1,
        boost_multiplier: 1.2,
        boost_title_terms: ["junior", "grad", "graduate", "entry level", "entry-level"],
      },
      salary: {
        preferred_max_gbp: null,
        hard_cap_gbp: null,
        penalty_strength: 0.35,
      },
    },
    eligibility: {
      needs_sponsorship: false,
      work_authorization_summary: "",
      check_hard_eligibility: false,
      use_sponsor_lookup: false,
    },
    matching: {
      semantic_threshold: 0.42,
    },
    llm_review: {
      extra_screening_guidance: [],
      extra_final_ranking_guidance: [],
    },
  };
  state.selectedProfileId = "";
  els.profileEditor.value = JSON.stringify(profile, null, 2);
  renderSelectedProfile({ id: "new-recipient", email: "recipient@example.com", target_roles: ["swe"], enabled: true });
  setProfileStatus("", "");
  renderProfileList();
}

async function validateProfile() {
  const profile = readProfileEditor();
  const payload = await apiPost("/api/profiles/validate", { profile });
  renderSelectedProfile(payload.summary);
  setProfileStatus("Valid profile.", "ok");
}

async function normalizeProfile() {
  const profile = readProfileEditor();
  const payload = await apiPost("/api/profiles/validate", { profile });
  els.profileEditor.value = JSON.stringify(payload.profile, null, 2);
  renderSelectedProfile(payload.summary);
  setProfileStatus("Normalized profile.", "ok");
}

async function saveProfile() {
  const profile = readProfileEditor();
  const payload = await apiPost("/api/profiles/save", { profile });
  els.profileEditor.value = JSON.stringify(payload.profile, null, 2);
  state.selectedProfileId = payload.summary.id;
  renderSelectedProfile(payload.summary);
  setProfileStatus("Saved profile.", "ok");
  await loadProfiles();
  await loadAuditOptions();
}

function readProfileEditor() {
  try {
    return JSON.parse(els.profileEditor.value || "{}");
  } catch (error) {
    setProfileStatus(`Invalid JSON: ${error.message}`, "error");
    throw error;
  }
}

function renderSelectedProfile(summary) {
  const roles = (summary?.target_roles || []).join(", ") || "no roles";
  els.selectedProfileTitle.textContent = summary?.id || "No profile selected";
  els.selectedProfileMeta.textContent = `${summary?.email || "-"} - ${summary?.enabled ? "enabled" : "disabled"} - ${roles}`;
}

function setProfileStatus(message, kind) {
  els.profileStatus.textContent = message;
  els.profileStatus.className = `status-line ${kind || ""}`.trim();
}

async function loadAuditOptions() {
  const options = await apiGet("/api/audit/options");
  fillSelect(els.auditRecipient, options.recipient_ids || [], "All");
  fillSelect(els.auditFamily, options.review_families || [], "All");
  fillSelect(els.auditClassification, options.classifications || [], "All");
  fillSelect(els.auditRun, options.run_ids || [], "All");
}

async function loadAudit() {
  const params = new URLSearchParams();
  for (const [name, element] of [
    ["recipient_id", els.auditRecipient],
    ["review_family", els.auditFamily],
    ["classification", els.auditClassification],
    ["run_id", els.auditRun],
    ["limit", els.auditLimit],
  ]) {
    if (element.value) {
      params.set(name, element.value);
    }
  }

  const payload = await apiGet(`/api/audit?${params.toString()}`);
  const rows = payload.rows || [];
  els.auditCount.textContent = `${rows.length} row${rows.length === 1 ? "" : "s"}`;
  renderAuditSummary(payload.summary || {});
  renderAuditRows(rows);
}

function renderAuditSummary(summary) {
  els.auditSummary.innerHTML = "";
  const classifications = summary.classifications || {};
  Object.entries(classifications).slice(0, 8).forEach(([name, count]) => {
    els.auditSummary.appendChild(pill(`${name}: ${count}`));
  });
}

function renderAuditRows(rows) {
  els.auditRows.innerHTML = "";
  if (!rows.length) {
    const empty = document.createElement("p");
    empty.textContent = "No audit rows.";
    els.auditRows.appendChild(empty);
    return;
  }

  rows.forEach((row) => {
    const item = document.createElement("article");
    item.className = "audit-row";
    const classificationKind = row.classification?.includes("failed")
      ? " failure"
      : row.classification?.includes("rejected") || row.classification?.includes("below")
        ? " warning"
        : "";
    item.innerHTML = `
      <div>
        <span class="classification${classificationKind}">${escapeHtml(row.classification || "-")}</span>
        <h3>${escapeHtml(row.recipient_id || "-")}</h3>
        <p>${escapeHtml(row.review_family || "-")} - ${escapeHtml(row.stage || "-")}</p>
        <p>${escapeHtml(row.created_at || "")}</p>
      </div>
      <div>
        <h3>${escapeHtml(row.company_name || "-")}</h3>
        <p>${escapeHtml(row.title || "-")}</p>
        <p>${escapeHtml(row.location || "-")}</p>
        ${row.job_url ? `<a href="${escapeAttr(row.job_url)}" target="_blank" rel="noreferrer">${escapeHtml(row.job_url)}</a>` : ""}
      </div>
      <div class="audit-meta">
        ${scoreLine(row)}
        ${row.hard_filter_reason ? `<div>Hard filter: ${escapeHtml(row.hard_filter_reason)}</div>` : ""}
        ${row.gemini_reason ? `<div>Gemini: ${escapeHtml(row.gemini_reason)}</div>` : ""}
        ${row.review_error_stage ? `<div>Error stage: ${escapeHtml(row.review_error_stage)}</div>` : ""}
        ${row.review_error ? `<div>Error: ${escapeHtml(row.review_error)}</div>` : ""}
        ${evidenceBlock("Evidence", row.supporting_evidence)}
        ${evidenceBlock("Mismatch", row.mismatch_evidence)}
      </div>
    `;
    els.auditRows.appendChild(item);
  });
}

function scoreLine(row) {
  const parts = [];
  if (row.semantic_score !== null && row.semantic_score !== undefined) {
    parts.push(`semantic ${Number(row.semantic_score).toFixed(3)}`);
  }
  if (row.semantic_threshold !== null && row.semantic_threshold !== undefined) {
    parts.push(`threshold ${Number(row.semantic_threshold).toFixed(3)}`);
  }
  if (row.gemini_pass1_score !== null && row.gemini_pass1_score !== undefined) {
    parts.push(`pass1 ${row.gemini_pass1_score}`);
  }
  if (row.gemini_pass2_score !== null && row.gemini_pass2_score !== undefined) {
    parts.push(`pass2 ${row.gemini_pass2_score}`);
  }
  return parts.length ? `<div>${escapeHtml(parts.join(" - "))}</div>` : "";
}

function evidenceBlock(label, values) {
  if (!Array.isArray(values) || !values.length) {
    return "";
  }
  const text = values.map((value) => String(value)).join(" | ");
  return `<div class="audit-evidence">${label}: ${escapeHtml(text)}</div>`;
}

function fillSelect(select, values, allLabel) {
  const currentValue = select.value;
  select.innerHTML = "";
  const allOption = document.createElement("option");
  allOption.value = "";
  allOption.textContent = allLabel;
  select.appendChild(allOption);
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
  select.value = values.includes(currentValue) ? currentValue : "";
}

function pill(text) {
  const element = document.createElement("span");
  element.className = "pill";
  element.textContent = text;
  return element;
}

async function apiGet(path) {
  return api(path, { method: "GET" });
}

async function apiPost(path, body) {
  return api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function api(path, options) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) {
    const message = payload.error || `Request failed: ${response.status}`;
    if (path.includes("/profiles/")) {
      setProfileStatus(message, "error");
    }
    throw new Error(message);
  }
  return payload;
}

function debounce(callback, delay) {
  let timer = null;
  return () => {
    clearTimeout(timer);
    timer = setTimeout(callback, delay);
  };
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}
