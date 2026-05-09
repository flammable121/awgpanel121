(() => {
  const body = document.body;
  body.dataset.theme = "dark";
  body.classList.add("theme-dark");
  localStorage.removeItem("theme");

  const modal = document.getElementById("configModal");
  const modalClose = document.getElementById("modalClose");
  const qrImg = document.getElementById("configQr");
  const downloadLink = document.getElementById("configDownload");
  const copyBtn = document.getElementById("configCopy");

  const closeModal = () => {
    if (!modal) {
      return;
    }
    modal.classList.add("hidden");
    document.body.style.overflow = "";
  };

  const openModal = (configUrl, qrUrl) => {
    if (!modal || !qrImg || !downloadLink) {
      return;
    }
    qrImg.src = `${qrUrl}${qrUrl.includes("?") ? "&" : "?"}t=${Date.now()}`;
    downloadLink.href = configUrl;
    if (copyBtn) {
      copyBtn.dataset.copyUrl = configUrl;
    }
    modal.classList.remove("hidden");
    document.body.style.overflow = "hidden";
  };

  modalClose?.addEventListener("click", closeModal);
  modal?.addEventListener("click", (event) => {
    if (event.target === modal) {
      closeModal();
    }
  });

  document.querySelectorAll(".config-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const configUrl = btn.getAttribute("data-config-url");
      const qrUrl = btn.getAttribute("data-qr-url");
      if (configUrl && qrUrl) {
        openModal(configUrl, qrUrl);
      }
    });
  });

  copyBtn?.addEventListener("click", async () => {
    const url = copyBtn.dataset.copyUrl;
    if (!url) {
      return;
    }
    try {
      await navigator.clipboard.writeText(url);
      copyBtn.textContent = "Скопировано";
      setTimeout(() => {
        copyBtn.textContent = "Копировать URL";
      }, 1200);
    } catch (err) {
      alert("Не удалось скопировать URL");
    }
  });

  const updateSearchDataset = (row, statusLabel) => {
    const name = row.querySelector(".peer-name")?.textContent?.trim() || "";
    const note = row.querySelector(".peer-note")?.textContent?.trim() || "";
    const address = row.children[1]?.textContent?.trim() || "";
    row.dataset.search = `${name} ${address} ${note} ${statusLabel}`.toLowerCase();
  };

  document.querySelectorAll(".toggle input").forEach((input) => {
    input.addEventListener("change", async () => {
      const toggle = input.closest(".toggle");
      const row = input.closest("tr");
      const peerId = toggle?.getAttribute("data-peer-id");
      if (!peerId || !row) {
        return;
      }
      input.disabled = true;
      try {
        const response = await fetch(`/api/peers/${peerId}/toggle`, {
          method: "POST",
          headers: { "X-Requested-With": "fetch" },
          credentials: "same-origin",
        });
        if (!response.ok) {
          throw new Error("Toggle failed");
        }
        const data = await response.json();
        const pill = row.querySelector(".pill");
        if (pill) {
          pill.className = `pill ${data.status}`;
          pill.textContent = data.status_label;
        }
        row.dataset.status = data.status;
        updateSearchDataset(row, data.status_label || "");
        applyFilter();
      } catch (err) {
        input.checked = !input.checked;
        alert("Не удалось изменить статус");
      } finally {
        input.disabled = false;
      }
    });
  });

  const filterInput = document.getElementById("peerFilter");
  const table = document.getElementById("peersTable");
  const tbody = table?.querySelector("tbody");

  function applyFilter() {
    if (!filterInput || !tbody) {
      return;
    }
    const value = filterInput.value.trim().toLowerCase();
    tbody.querySelectorAll("tr").forEach((row) => {
      const hay = row.dataset.search || "";
      row.style.display = hay.includes(value) ? "" : "none";
    });
  }

  filterInput?.addEventListener("input", applyFilter);
  applyFilter();

  const sortButtons = document.querySelectorAll(".th-sort");
  let currentSort = { key: "", dir: 1 };
  const statusOrder = { active: 0, disabled: 1, expired: 2 };

  const sortRows = (key) => {
    if (!tbody) {
      return;
    }
    const dir = currentSort.key === key ? -currentSort.dir : 1;
    currentSort = { key, dir };
    const rows = Array.from(tbody.querySelectorAll("tr"));
    rows.sort((a, b) => {
      let aVal = a.dataset[key] || "";
      let bVal = b.dataset[key] || "";
      if (key === "expires") {
        aVal = Number(aVal) || 0;
        bVal = Number(bVal) || 0;
      }
      if (key === "status") {
        aVal = statusOrder[aVal] ?? 9;
        bVal = statusOrder[bVal] ?? 9;
      }
      if (typeof aVal === "string") {
        aVal = aVal.toLowerCase();
        bVal = bVal.toLowerCase();
      }
      if (aVal < bVal) return -1 * dir;
      if (aVal > bVal) return 1 * dir;
      return 0;
    });
    rows.forEach((row) => tbody.appendChild(row));
  };

  sortButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.getAttribute("data-sort");
      if (key) {
        sortRows(key);
      }
    });
  });

  const pollTraffic = async () => {
    const cells = document.querySelectorAll(".traffic-value");
    if (!cells.length) {
      return;
    }
    try {
      const response = await fetch("/api/stats", { credentials: "same-origin" });
      if (!response.ok) {
        return;
      }
      const payload = await response.json();
      const map = new Map();
      (payload.peers || []).forEach((item) => {
        map.set(item.public_key, item);
      });
      cells.forEach((cell) => {
        const stat = map.get(cell.dataset.peerKey);
        if (stat && stat.total_display) {
          cell.textContent = stat.total_display;
        }
      });
    } catch (err) {
      // ignore polling errors
    }
  };

  if (document.querySelector(".traffic-value")) {
    pollTraffic();
    setInterval(pollTraffic, 1000);
  }
})();
