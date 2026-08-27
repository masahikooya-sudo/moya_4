const entityCheckboxes = document.getElementById("entity-checkboxes");
const errorBox = document.getElementById("error-box");
const maskBtn = document.getElementById("mask-btn");
const maskBtnLabel = maskBtn.textContent;
const fileInput = document.getElementById("file-input");
const fileReviewBox = document.getElementById("file-review");
const fileReviewBody = document.getElementById("file-review-body");

let entityDefinitions = [];
// null、または { kind: "tabular"|"freeform", groups?, candidates?, suggestedByKey? }
let reviewState = null;

function showError(message) {
  errorBox.textContent = message;
  errorBox.classList.remove("hidden");
}

function clearError() {
  errorBox.textContent = "";
  errorBox.classList.add("hidden");
}

function getSelectedEntities() {
  return Array.from(entityCheckboxes.querySelectorAll("input[type=checkbox]:checked")).map(
    (el) => el.value
  );
}

function getSelectedStyle() {
  return document.querySelector('input[name="style"]:checked').value;
}

function setStatus(online) {
  const badge = document.getElementById("status-badge");
  const label = document.getElementById("status-label");
  badge.classList.toggle("offline", !online);
  label.textContent = online ? "Presidio Active" : "Presidio Offline";
}

async function loadUser() {
  try {
    const res = await fetch("/api/me");
    if (!res.ok) return;
    const user = await res.json();
    if (!user) return;
    document.getElementById("user-email").textContent = user.email;
    document.getElementById("user-info").classList.remove("hidden");
  } catch (e) {
    // 未ログイン時は何も表示しない(認証無効時など)
  }
}

async function loadEntities() {
  try {
    const res = await fetch("/api/entities");
    if (!res.ok) throw new Error("failed");
    const data = await res.json();
    entityDefinitions = data.entities;
    entityCheckboxes.innerHTML = "";
    data.entities.forEach((entity) => {
      const label = document.createElement("label");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = entity.code;
      checkbox.checked = true;
      label.appendChild(checkbox);
      label.appendChild(document.createTextNode(`${entity.label} (${entity.code})`));
      entityCheckboxes.appendChild(label);
    });
    setStatus(true);
  } catch (e) {
    setStatus(false);
  }
}

function isFileMode() {
  return document.getElementById("file-tab").classList.contains("active");
}

function updateMaskButtonLabel() {
  maskBtn.textContent = isFileMode() && reviewState ? "確認内容でマスキングを実行" : maskBtnLabel;
}

function resetReview() {
  reviewState = null;
  fileReviewBox.classList.add("hidden");
  fileReviewBody.innerHTML = "";
  updateMaskButtonLabel();
}

fileInput.addEventListener("change", () => {
  resetReview();
  document.getElementById("file-result").classList.add("hidden");
});

entityCheckboxes.addEventListener("change", resetReview);

document.getElementById("select-all").addEventListener("click", () => {
  entityCheckboxes.querySelectorAll("input[type=checkbox]").forEach((el) => (el.checked = true));
  resetReview();
});

document.getElementById("select-none").addEventListener("click", () => {
  entityCheckboxes.querySelectorAll("input[type=checkbox]").forEach((el) => (el.checked = false));
  resetReview();
});

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab).classList.add("active");
    clearError();
    document.getElementById("text-result").classList.add("hidden");
    document.getElementById("file-result").classList.add("hidden");
    updateMaskButtonLabel();
  });
});

async function maskText() {
  const text = document.getElementById("input-text").value;
  if (!text.trim()) {
    showError("テキストを入力してください。");
    return;
  }

  const entities = getSelectedEntities();
  const style = getSelectedStyle();

  const res = await fetch("/api/mask/text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, entities, style }),
  });

  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "マスキングに失敗しました。");
  }

  const data = await res.json();
  document.getElementById("output-text").value = data.masked_text;
  document.getElementById("text-result").classList.remove("hidden");
  document.getElementById("file-result").classList.add("hidden");

  const summary = document.getElementById("detection-summary");
  summary.innerHTML = "";
  const counts = {};
  data.detections.forEach((d) => {
    counts[d.entity_label] = (counts[d.entity_label] || 0) + 1;
  });
  if (Object.keys(counts).length === 0) {
    const badge = document.createElement("span");
    badge.className = "detection-badge";
    badge.textContent = "検出なし";
    summary.appendChild(badge);
  } else {
    Object.entries(counts).forEach(([label, count]) => {
      const badge = document.createElement("span");
      badge.className = "detection-badge";
      badge.textContent = `${label}: ${count}件`;
      summary.appendChild(badge);
    });
  }
}

function renderTabularReview(groups) {
  fileReviewBody.innerHTML = "";
  document.getElementById("file-review-title").textContent = "マスキング対象列の確認";
  document.getElementById("file-review-hint").textContent =
    "列名から推定した種別です。見落としがあれば「対象外」の列を選び直し、確認後にマスキングを実行してください。";

  const selectedEntities = getSelectedEntities();
  const suggestedByKey = {};

  groups.forEach((group) => {
    if (group.columns.length === 0) return;

    const groupWrap = document.createElement("div");
    groupWrap.className = "review-group";
    if (group.group) {
      const title = document.createElement("p");
      title.className = "review-group-title";
      title.textContent = group.group;
      groupWrap.appendChild(title);
    }

    group.columns.forEach((col) => {
      suggestedByKey[col.key] = col.suggested || "";

      const row = document.createElement("div");
      row.className = "review-column-row";

      const headerEl = document.createElement("div");
      headerEl.className = "review-header";
      headerEl.textContent = col.header;

      const select = document.createElement("select");
      select.dataset.key = col.key;

      const noneOpt = document.createElement("option");
      noneOpt.value = "";
      noneOpt.textContent = "対象外";
      select.appendChild(noneOpt);

      entityDefinitions
        .filter((entity) => selectedEntities.includes(entity.code))
        .forEach((entity) => {
          const opt = document.createElement("option");
          opt.value = entity.code;
          opt.textContent = entity.label;
          select.appendChild(opt);
        });

      select.value = selectedEntities.includes(col.suggested) ? col.suggested : "";

      const sampleEl = document.createElement("div");
      sampleEl.className = "review-sample";
      sampleEl.textContent = col.sample ? `例: ${col.sample}` : "";

      row.appendChild(headerEl);
      row.appendChild(select);
      row.appendChild(sampleEl);
      groupWrap.appendChild(row);
    });

    fileReviewBody.appendChild(groupWrap);
  });

  reviewState = { kind: "tabular", suggestedByKey };
  fileReviewBox.classList.remove("hidden");
}

function renderFreeformReview(candidates) {
  fileReviewBody.innerHTML = "";
  document.getElementById("file-review-title").textContent = "マスキング候補の確認";
  document.getElementById("file-review-hint").textContent =
    `${candidates.length}件の候補が見つかりました。マスキングしたくない項目はチェックを外してから実行してください。`;

  candidates.forEach((c) => {
    const row = document.createElement("label");
    row.className = "review-candidate-row";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = true;
    checkbox.dataset.entityType = c.entity_type;
    checkbox.dataset.text = c.text;

    const badge = document.createElement("span");
    badge.className = "review-badge";
    badge.textContent = c.entity_label;

    const textEl = document.createElement("span");
    textEl.className = "review-text";
    textEl.textContent = c.sample;

    const countEl = document.createElement("span");
    countEl.className = "review-count";
    countEl.textContent = c.count > 1 ? `${c.count}箇所` : "";

    row.appendChild(checkbox);
    row.appendChild(badge);
    row.appendChild(textEl);
    row.appendChild(countEl);
    fileReviewBody.appendChild(row);
  });

  reviewState = { kind: "freeform" };
  fileReviewBox.classList.remove("hidden");
}

document.getElementById("review-select-all").addEventListener("click", () => {
  if (!reviewState) return;
  if (reviewState.kind === "tabular") {
    fileReviewBody.querySelectorAll("select").forEach((select) => {
      select.value = reviewState.suggestedByKey[select.dataset.key] || "";
    });
  } else {
    fileReviewBody.querySelectorAll('input[type="checkbox"]').forEach((el) => (el.checked = true));
  }
});

document.getElementById("review-select-none").addEventListener("click", () => {
  if (!reviewState) return;
  if (reviewState.kind === "tabular") {
    fileReviewBody.querySelectorAll("select").forEach((select) => (select.value = ""));
  } else {
    fileReviewBody.querySelectorAll('input[type="checkbox"]').forEach((el) => (el.checked = false));
  }
});

function collectColumnOverrides() {
  const overrides = {};
  fileReviewBody.querySelectorAll("select").forEach((select) => {
    overrides[select.dataset.key] = select.value || null;
  });
  return overrides;
}

function collectConfirmedCandidates() {
  return Array.from(fileReviewBody.querySelectorAll('input[type="checkbox"]:checked')).map((el) => ({
    entity_type: el.dataset.entityType,
    text: el.dataset.text,
  }));
}

async function analyzeFile() {
  const file = fileInput.files[0];
  if (!file) {
    showError("ファイルを選択してください。");
    return;
  }

  const entities = getSelectedEntities();
  const formData = new FormData();
  formData.append("file", file);
  formData.append("entities", entities.join(","));

  const res = await fetch("/api/analyze/file", { method: "POST", body: formData });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "ファイルの解析に失敗しました。");
  }
  const data = await res.json();

  if (data.kind === "tabular") {
    const hasColumns = data.groups.some((g) => g.columns.length > 0);
    if (!hasColumns) {
      await performMask();
      return;
    }
    renderTabularReview(data.groups);
  } else {
    if (data.candidates.length === 0) {
      await performMask();
      return;
    }
    renderFreeformReview(data.candidates);
  }
}

async function performMask() {
  const file = fileInput.files[0];
  if (!file) {
    showError("ファイルを選択してください。");
    return;
  }

  const entities = getSelectedEntities();
  const style = getSelectedStyle();

  const formData = new FormData();
  formData.append("file", file);
  formData.append("entities", entities.join(","));
  formData.append("style", style);

  if (reviewState && reviewState.kind === "tabular") {
    formData.append("column_overrides", JSON.stringify(collectColumnOverrides()));
  } else if (reviewState && reviewState.kind === "freeform") {
    formData.append("confirmed_candidates", JSON.stringify(collectConfirmedCandidates()));
  }

  const res = await fetch("/api/mask/file", { method: "POST", body: formData });

  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "マスキングに失敗しました。");
  }

  const detectionCount = res.headers.get("X-Detection-Count") || "0";
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);

  const link = document.getElementById("download-link");
  link.href = url;
  link.download = `masked_${file.name}`;

  document.getElementById("file-result-message").textContent =
    `${detectionCount} 件の情報を検出し、マスキングしました。`;
  document.getElementById("file-result").classList.remove("hidden");
  document.getElementById("text-result").classList.add("hidden");
}

document.getElementById("copy-result-btn").addEventListener("click", async () => {
  const output = document.getElementById("output-text");
  await navigator.clipboard.writeText(output.value);
});

maskBtn.addEventListener("click", async () => {
  clearError();
  maskBtn.disabled = true;
  maskBtn.textContent = isFileMode() && !reviewState ? "候補を確認中..." : "処理中...";

  try {
    if (isFileMode()) {
      if (reviewState) {
        await performMask();
        resetReview();
      } else {
        await analyzeFile();
      }
    } else {
      await maskText();
    }
  } catch (e) {
    showError(e.message);
  } finally {
    maskBtn.disabled = false;
    updateMaskButtonLabel();
  }
});

loadEntities();
loadUser();
