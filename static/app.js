const entityCheckboxes = document.getElementById("entity-checkboxes");
const errorBox = document.getElementById("error-box");
const maskBtn = document.getElementById("mask-btn");
const maskBtnLabel = maskBtn.textContent;

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

document.getElementById("select-all").addEventListener("click", () => {
  entityCheckboxes.querySelectorAll("input[type=checkbox]").forEach((el) => (el.checked = true));
});

document.getElementById("select-none").addEventListener("click", () => {
  entityCheckboxes.querySelectorAll("input[type=checkbox]").forEach((el) => (el.checked = false));
});

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab).classList.add("active");
    clearError();
  });
});

function isFileMode() {
  return document.getElementById("file-tab").classList.contains("active");
}

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

async function maskFile() {
  const fileInput = document.getElementById("file-input");
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

  const res = await fetch("/api/mask/file", {
    method: "POST",
    body: formData,
  });

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
  maskBtn.textContent = "処理中...";

  try {
    if (isFileMode()) {
      await maskFile();
    } else {
      await maskText();
    }
  } catch (e) {
    showError(e.message);
  } finally {
    maskBtn.disabled = false;
    maskBtn.textContent = maskBtnLabel;
  }
});

loadEntities();
loadUser();
