export const BASE_PATH = (window.__PANEL_BASE__ || "").replace(/\/+$/, "");

export function withBase(url) {
  if (!BASE_PATH) return url;
  if (url.startsWith("http")) return url;
  if (!url.startsWith("/")) return `${BASE_PATH}/${url}`;
  return `${BASE_PATH}${url}`;
}

export async function apiGet(url) {
  const response = await fetch(withBase(url), { credentials: "same-origin" });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

export async function apiPost(url, options = {}) {
  const response = await fetch(withBase(url), {
    method: "POST",
    headers: { "X-Requested-With": "fetch" },
    credentials: "same-origin",
    ...options,
  });
  if (!response.ok) {
    let detail = `Request failed: ${response.status}`;
    try {
      const data = await response.json();
      if (data && data.detail) detail = data.detail;
    } catch (err) {
      try {
        const text = await response.text();
        if (text) detail = text;
      } catch (e) {
        // ignore
      }
    }
    throw new Error(detail);
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return null;
}

export function fetchPeers() {
  return apiGet("/api/peers");
}

export function togglePeer(id) {
  return apiPost(`/api/peers/${id}/toggle`);
}

export function deletePeer(id) {
  return apiPost(`/peers/${id}/delete`);
}

export function fetchStats() {
  return apiGet("/api/stats");
}

export function fetchSystem() {
  return apiGet("/api/system");
}

export function restartPanel() {
  return apiPost("/api/restart/panel");
}

export function restartAwg() {
  return apiPost("/api/restart/awg");
}

export function restartServer() {
  return apiPost("/api/restart/server");
}

export function resetTraffic() {
  return apiPost("/api/traffic/reset");
}

export function fetchAwgParams() {
  return apiGet("/api/awg/params");
}

export function fetchApiInfo() {
  return apiGet("/api/api-info");
}

export function resetApiToken() {
  return apiPost("/api/api-token/reset");
}

export async function updateAwgParams(params) {
  const response = await fetch(withBase("/api/awg/params"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "fetch",
    },
    body: JSON.stringify(params || {}),
    credentials: "same-origin",
  });
  if (!response.ok) {
    throw new Error("Update failed");
  }
  return response.json();
}

export function fetchIChain() {
  return apiGet("/api/awg/i-chain");
}

export function fetchAwgSettings() {
  return apiGet("/api/awg/settings");
}

export function fetchAwgRouting() {
  return apiGet("/api/awg/routing");
}

export async function updateAwgRouting(payload) {
  const response = await fetch(withBase("/api/awg/routing"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "fetch",
    },
    body: JSON.stringify(payload || {}),
    credentials: "same-origin",
  });
  if (!response.ok) {
    let detail = "Не удалось сохранить маршрутизацию";
    try {
      const data = await response.json();
      if (data && data.detail) detail = data.detail;
    } catch (err) {
      // ignore
    }
    throw new Error(detail);
  }
  return response.json();
}

export function updateAwgRoutingGeoip(payload) {
  return apiPost("/api/awg/routing/geoip/update", {
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "fetch",
    },
    body: JSON.stringify(payload || {}),
  });
}

export function updateAwgRoutingGeosite(payload) {
  return apiPost("/api/awg/routing/geosite/update", {
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "fetch",
    },
    body: JSON.stringify(payload || {}),
  });
}

export function applyAwgRouting() {
  return apiPost("/api/awg/routing/apply");
}

export function clearAwgRouting() {
  return apiPost("/api/awg/routing/clear");
}

export function resetAwgRouting() {
  return apiPost("/api/awg/routing/reset");
}

export async function updateAwgSettings(payload) {
  const response = await fetch(withBase("/api/awg/settings"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "fetch",
    },
    body: JSON.stringify(payload || {}),
    credentials: "same-origin",
  });
  if (!response.ok) {
    let detail = "Не удалось сохранить настройки";
    try {
      const data = await response.json();
      if (data && data.detail) detail = data.detail;
    } catch (err) {
      // ignore
    }
    throw new Error(detail);
  }
  return response.json();
}

export async function createPeer(name) {
  const form = new FormData();
  if (name && typeof name === "object") {
    Object.entries(name).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        form.append(key, value);
      }
    });
  } else {
    form.append("name", name || "");
  }
  const response = await fetch(withBase("/peers"), {
    method: "POST",
    headers: { "X-Requested-With": "fetch" },
    body: form,
    credentials: "same-origin",
  });
  if (!response.ok) {
    let detail = `Request failed: ${response.status}`;
    try {
      const data = await response.json();
      if (data && data.detail) detail = data.detail;
    } catch (err) {
      try {
        const text = await response.text();
        if (text) detail = text;
      } catch (e) {
        // ignore
      }
    }
    throw new Error(detail);
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return true;
}
