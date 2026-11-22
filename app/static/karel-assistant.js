/* One contextual assistant for the whole application. No inline browser URLs,
   passwords or arbitrary HTML from responses are rendered as trusted markup. */
(() => {
  "use strict";
  const root = document.getElementById("karel-floating-assistant");
  if (!root) return;
  const launcher = document.getElementById("karel-assistant-launcher");
  const drawer = document.getElementById("karel-assistant-drawer");
  const close = document.getElementById("karel-assistant-close");
  const projectSelect = document.getElementById("karel-assistant-project");
  const locationBox = document.getElementById("karel-assistant-location");
  const messagesBox = document.getElementById("karel-assistant-messages");
  const receiptBox = document.getElementById("karel-assistant-receipt");
  const approvalBox = document.getElementById("karel-assistant-approval");
  const form = document.getElementById("karel-assistant-form");
  const input = document.getElementById("karel-assistant-input");
  const working = document.getElementById("karel-assistant-working");
  const sendButton = document.getElementById("karel-assistant-send");
  const fullChat = document.getElementById("karel-assistant-full-chat");
  const pendingBadge = document.getElementById("karel-launcher-pending");

  const allowedScreens = new Set([
    "chat", "docs", "development", "tasks", "github", "website", "manage",
    "settings", "testing", "releases", "outputs", "history", "files",
    "components", "library", "portfolio", "account", "admin"
  ]);
  let activeChatId = null;
  let busy = false;
  let closedFocus = null;
  let revision = 0;
  let selectedEntity = "";
  const url = new URL(window.location.href);
  const path = url.pathname;
  const route = path.match(/^\/projects\/(\d+)(?:\/|$)/);
  const visibleProject = route ? route[1] : "";
  function routeScreen() {
    if (route) {
      if (/\/github\/?$/.test(path)) return "github";
      const view = url.searchParams.get("view") || "chat";
      return allowedScreens.has(view) ? view : "chat";
    }
    if (path.startsWith("/library")) return "library";
    if (path.startsWith("/admin")) return "admin";
    if (path.startsWith("/settings")) return "settings";
    if (path.startsWith("/account")) return "account";
    return "portfolio";
  }
  function selectedProject() {
    const id = projectSelect.value;
    return /^\d{1,12}$/.test(id) ? id : "";
  }
  function activeScreen() {
    if (visibleProject && selectedProject() !== visibleProject) return "portfolio";
    return routeScreen();
  }
  function busyState(value, text) {
    busy = value;
    sendButton.disabled = value || !selectedProject();
    projectSelect.disabled = value;
    working.textContent = text || "";
    input.disabled = value || !selectedProject();
  }
  function cell(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined) item.textContent = String(text);
    return item;
  }
  function clear(element) {
    while (element.firstChild) element.removeChild(element.firstChild);
  }
  function setOpen(open) {
    drawer.hidden = !open;
    launcher.setAttribute("aria-expanded", String(open));
    if (open) {
      closedFocus = document.activeElement;
      loadState();
      window.requestAnimationFrame(() => input.focus({preventScroll: true}));
    } else {
      (closedFocus && closedFocus.isConnected ? closedFocus : launcher).focus({preventScroll: true});
    }
  }
  async function requestJSON(pathname, options) {
    const response = await fetch(pathname, {
      credentials: "same-origin", redirect: "follow",
      ...options,
    });
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        throw new Error("Pro tuto akci nemáš přístup. Obnov přihlášení nebo oprávnění projektu.");
      }
      throw new Error("Server nevrátil platnou odpověď (" + response.status + ").");
    }
    const type = response.headers.get("content-type") || "";
    if (!type.includes("application/json")) {
      throw new Error("Aplikace nevrátila očekávaný stav chatu; akce není potvrzená.");
    }
    return response.json();
  }
  function renderState(data) {
    activeChatId = data.chat_id;
    clear(messagesBox);
    const rows = Array.isArray(data.messages) ? data.messages : [];
    if (!rows.length) messagesBox.appendChild(cell("p", "karel-assistant-empty",
      "Zatím tu není žádná komunikace. Popiš Karlovi úkol."));
    for (const m of rows) {
      const article = cell("article", "karel-assistant-message " +
        (m.role === "user" ? "from-user" : "from-karel"));
      article.appendChild(cell("b", "", m.role === "user" ? "Ty" : "Karel"));
      const body = cell("p", "", m.content || "");
      article.appendChild(body);
      messagesBox.appendChild(article);
    }
    if (data.messages_truncated) {
      const note = cell("p", "karel-assistant-old-messages",
        "Zobrazena jen poslední část konverzace. Celou historii najdeš v chatu.");
      messagesBox.prepend(note);
    }
    // Only the pane scrolls, not the project page; no delayed page jump.
    messagesBox.scrollTop = messagesBox.scrollHeight;
    locationBox.textContent = (data.context_label || "Projekt") +
      " · " + (data.context_summary || "Projektový kontext není dostupný");
    fullChat.href = "/projects/" + data.project_id + "?view=chat" +
      (data.chat_id ? "&chat_id=" + data.chat_id : "");
    clear(receiptBox);
    const receipt = data.receipt || null;
    receiptBox.hidden = !receipt;
    if (receipt) {
      receiptBox.appendChild(cell("b", "", receipt.title));
      receiptBox.appendChild(cell("p", "", receipt.text));
      if (receipt.url && /^\/projects\/\d+\?view=development/.test(receipt.url)) {
        const link = cell("a", "", "Otevřít ověřenou Pipeline");
        link.href = receipt.url;
        receiptBox.appendChild(link);
      }
    }
    const pending = Array.isArray(data.pending) ? data.pending : [];
    pendingBadge.hidden = !pending.length;
    pendingBadge.textContent = pending.length ? String(pending.length) : "";
    clear(approvalBox);
    approvalBox.hidden = !pending.length;
    if (pending.length) {
      approvalBox.appendChild(cell("strong", "", "Čeká na schválení"));
      for (const item of pending) {
        const title = cell("p", "", item.title || "Navržená změna");
        approvalBox.appendChild(title);
        if (item.description) approvalBox.appendChild(cell("small", "", item.description));
      }
      const button = cell("button", "btn primary small", "Schválit uvedené změny (" +
        pending.length + ")");
      button.type = "button";
      button.disabled = !data.can_edit;
      button.addEventListener("click", approvePending);
      approvalBox.appendChild(button);
      const review = cell("a", "", "Zkontrolovat kompletní návrh v chatu");
      review.href = fullChat.href;
      approvalBox.appendChild(review);
    }
    busyState(false, "");
  }
  async function loadState() {
    const id = selectedProject();
    if (!id) {
      busyState(false, "Vyber projekt.");
      activeChatId = null;
      locationBox.textContent = "Bez projektu Karel nemůže číst ani měnit konkrétní data.";
      clear(messagesBox);
      messagesBox.appendChild(cell("p", "", "Vyber projekt, se kterým chceš pracovat."));
      clear(approvalBox); approvalBox.hidden = true;
      clear(receiptBox); receiptBox.hidden = true;
      return;
    }
    const serial = ++revision;
    busyState(true, "Načítám ověřený kontext…");
    try {
      const viewedChat = selectedProject() === visibleProject
        ? (url.searchParams.get("chat_id") || "") : "";
      const chatParam = /^\d{1,12}$/.test(viewedChat)
        ? "&chat_id=" + viewedChat : "";
      const data = await requestJSON("/projects/" + id + "/assistant/state?screen=" +
        encodeURIComponent(activeScreen()) + chatParam);
      if (serial !== revision) return;
      renderState(data);
    } catch (error) {
      if (serial !== revision) return;
      busyState(false, String(error.message || "Nepodařilo se načíst chat."));
    }
  }
  async function submitText(event) {
    event.preventDefault();
    const id = selectedProject();
    const text = input.value.trim();
    if (busy || !id || !text) return;
    busyState(true, "Karel pracuje se skutečnými daty projektu…");
    const body = new FormData();
    body.set("chat_id", String(activeChatId || 0));
    body.set("message", text);
    body.set("screen_context", activeScreen());
    // "Focused record" is a hint only. The backend validates record
    // identity against the selected project before providing its details.
    body.set("focus_target", selectedEntity);
    try {
      const data = await requestJSON("/projects/" + id + "/assistant/send", {
        method: "POST", body,
      });
      input.value = "";
      renderState(data);
    } catch (error) {
      busyState(false, String(error.message || "Odeslání se nepodařilo."));
      // Keep the original draft so the user never has to retype a failed send.
    }
  }
  async function approvePending() {
    const id = selectedProject();
    if (busy || !id || !activeChatId) return;
    busyState(true, "Schvaluji a kontroluji zápis do projektu…");
    try {
      const body = new FormData();
      body.set("chat_id", String(activeChatId));
      const data = await requestJSON("/projects/" + id + "/assistant/approve", {
        method: "POST", body,
      });
      renderState(data);
      working.textContent = data.approval_notice || "";
    } catch (error) {
      busyState(false, String(error.message || "Zápis nebyl potvrzen."));
    }
  }

  launcher.addEventListener("click", () => setOpen(drawer.hidden));
  close.addEventListener("click", () => setOpen(false));
  form.addEventListener("submit", submitText);
  input.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
  projectSelect.addEventListener("change", () => {
    activeChatId = null;
    try { window.sessionStorage.setItem("karel-project-context", selectedProject()); }
    catch (_) { /* Browsers may disable storage; select still works. */ }
    if (!drawer.hidden) loadState();
  });
  document.addEventListener("click", event => {
    const item = event.target.closest && event.target.closest("[data-karel-entity]");
    if (item && !item.closest("#karel-assistant-drawer")) {
      selectedEntity = (item.getAttribute("data-karel-entity") || "").slice(0,40);
    }
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && !drawer.hidden) setOpen(false);
  });
  if (visibleProject) {
    const found = Array.from(projectSelect.options).some(x => x.value === visibleProject);
    if (found) {
      projectSelect.value = visibleProject;
      try { window.sessionStorage.setItem("karel-project-context", visibleProject); }
      catch (_) { /* Browsers may disable storage. */ }
    }
  } else {
    try {
      const stored = window.sessionStorage.getItem("karel-project-context");
      if (Array.from(projectSelect.options).some(x => x.value === stored)) {
        projectSelect.value = stored;
      }
    } catch (_) { /* Storage not required. */ }
  }
  if (selectedProject() && !visibleProject) {
    // On a dashboard this is only a project selection, not proof that a
    // particular project page is being viewed.
    locationBox.textContent = "Přehled projektů · vybraný projekt";
  }
})();
