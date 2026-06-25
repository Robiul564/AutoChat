const state = {
  businessId: null,
  conversationId: null,
  tools: [],
  whatsappAccounts: [],
  isPlatformAdmin: false,
};

const $ = (selector) => document.querySelector(selector);
const headers = () => ({
  "Content-Type": "application/json",
  "X-User-Email": $("#actorEmail").value || "owner@example.com",
  ...($("#adminKey")?.value ? { "X-Admin-Key": $("#adminKey").value } : {}),
});

async function api(path, options = {}) {
  const res = await fetch(path, { ...options, headers: { ...headers(), ...(options.headers || {}) } });
  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
  }
  if (!res.ok) throw new Error(data?.detail || res.statusText || "Request failed");
  return data;
}

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("visible");
  setTimeout(() => el.classList.remove("visible"), 2600);
}

function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function selectedBusinessId() {
  const value = $("#businessSelect")?.value;
  return value ? Number(value) : null;
}

function setWebhookPlaceholder(message) {
  $("#webhookCallback").textContent = `${window.location.origin}/webhooks/meta/whatsapp`;
  $("#webhookToken").textContent = message;
  $("#whatsappSendMode").textContent = "mock";
  $("#webhookNotice").textContent = "This is the local webhook URL. Use ngrok or set PUBLIC_BASE_URL before adding it to Meta.";
  $("#whatsappAccounts").innerHTML = "";
}

function renderWebhookSetup(setup) {
  $("#webhookCallback").textContent = setup.callback_url;
  $("#webhookToken").textContent = setup.verify_token;
  $("#whatsappSendMode").textContent = setup.send_mode;
  $("#webhookNotice").textContent = setup.is_public_url
    ? "Use this callback URL and verify token in Meta WhatsApp webhook settings."
    : "This URL is local only. Meta cannot reach it until you set PUBLIC_BASE_URL to an ngrok, Cloudflare Tunnel, or deployed HTTPS URL.";
}

async function runUiAction(fn) {
  try {
    await fn();
  } catch (error) {
    toast(error?.message || "Something went wrong");
  }
}

async function loadSession() {
  const session = await api("/api/platform/session");
  state.isPlatformAdmin = session.is_platform_admin;
  document.querySelectorAll(".platform-only").forEach((el) => {
    el.classList.toggle("platform-hidden", !state.isPlatformAdmin);
  });
  if (!state.isPlatformAdmin && $("#tools").classList.contains("active")) {
    document.querySelector('[data-view="inbox"]').click();
  }
}

async function loadBusinesses() {
  const businesses = await api("/api/businesses");
  const select = $("#businessSelect");
  select.innerHTML = businesses.map((b) => `<option value="${b.id}">#${b.id} ${b.name} (${b.status})</option>`).join("");
  const hasSelectedBusiness = businesses.some((business) => business.id === Number(state.businessId));
  if (businesses.length && (!state.businessId || !hasSelectedBusiness)) {
    state.businessId = businesses[0].id;
  }
  if (state.businessId) select.value = state.businessId;
  if (!businesses.length) setWebhookPlaceholder("Create a business first");
  return businesses;
}

async function loadInbox() {
  if (!state.businessId) return;
  const conversations = await api(`/api/businesses/${state.businessId}/conversations`);
  if (!conversations.length) {
    state.conversationId = null;
    $("#conversationList").innerHTML = `<div class="item"><span class="meta">No WhatsApp conversations for this business yet.</span></div>`;
    $("#messageList").innerHTML = "";
    return;
  }
  $("#conversationList").innerHTML = conversations
    .map(
      (c) => {
        const customer = c.customer_name || c.customer_phone || `customer ${c.customer_id}`;
        const preview = c.last_message_body ? `<br /><span class="preview">${escapeHtml(c.last_message_body)}</span>` : "";
        return `<div class="item">
        <strong>${escapeHtml(customer)}</strong><br />
        <span class="meta">conversation #${c.id} · ${c.status} · AI ${c.ai_enabled ? "on" : "off"}</span>${preview}<br />
        <button data-open="${c.id}">Open</button>
      </div>`;
      }
    )
    .join("");
  document.querySelectorAll("[data-open]").forEach((button) => {
    button.addEventListener("click", () => openConversation(button.dataset.open));
  });
  if (conversations.length && !state.conversationId) {
    await openConversation(conversations[0].id);
  }
}

async function loadWhatsAppSetup() {
  state.businessId = selectedBusinessId() || state.businessId;
  if (!state.businessId) {
    const setup = await api("/api/platform/webhook-setup");
    renderWebhookSetup(setup);
    $("#whatsappAccounts").innerHTML = `<div class="mini-item"><span>Select a business to show connected WhatsApp accounts.</span></div>`;
    return;
  }
  $("#businessSelect").value = state.businessId;
  const setup = await api(`/api/businesses/${state.businessId}/whatsapp/accounts/webhook-setup`);
  renderWebhookSetup(setup);
  let accounts;
  try {
    accounts = await api(`/api/businesses/${state.businessId}/whatsapp/accounts`);
  } catch (error) {
    $("#whatsappAccounts").innerHTML = `<div class="mini-item"><span>Could not load accounts for this business.</span></div>`;
    throw error;
  }
  state.whatsappAccounts = accounts;
  $("#whatsappAccounts").innerHTML = accounts.length
    ? accounts
        .map(
          (account) => `<div class="mini-item account-row">
            <div class="mini-item-main">
              <strong>${escapeHtml(account.display_phone_number || account.phone_number_id)}</strong>
              <span>${account.status} · Phone ID ${escapeHtml(account.phone_number_id)}</span>
            </div>
            <button type="button" class="danger small platform-only" data-delete-whatsapp="${account.id}">Delete</button>
          </div>`
        )
        .join("")
    : `<div class="mini-item"><span>No WhatsApp account connected for this business yet.</span></div>`;
  document.querySelectorAll("[data-delete-whatsapp]").forEach((button) => {
    button.addEventListener("click", () => deleteWhatsAppAccount(Number(button.dataset.deleteWhatsapp)));
  });
  document.querySelectorAll("#whatsappAccounts .platform-only").forEach((el) => {
    el.classList.toggle("platform-hidden", !state.isPlatformAdmin);
  });
}

async function refreshWebhookSetup() {
  const button = $("#refreshWebhookSetup");
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Loading...";
  try {
    await loadSession();
    if (!selectedBusinessId()) {
      await loadBusinesses();
    }
    await loadWhatsAppSetup();
    toast("Webhook loaded");
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

async function openConversation(id) {
  state.conversationId = id;
  const detail = await api(`/api/businesses/${state.businessId}/conversations/${id}`);
  $("#messageList").innerHTML = detail.messages
    .map(
      (m) => `<div class="message ${m.direction}">
        <div class="meta">${m.direction} · ${m.status}${m.ai_generated ? " · AI" : ""}</div>
        <div>${escapeHtml(m.body)}</div>
      </div>`
    )
    .join("");
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[char]));
}

async function simulateWebhook() {
  if (!state.businessId) return toast("Create and connect a tenant first");
  if (!state.whatsappAccounts.length) await loadWhatsAppSetup();
  const account = state.whatsappAccounts[0];
  if (!account) return toast("Connect a WhatsApp account for this business first");
  const phone = account?.phone_number_id || document.querySelector("#whatsappForm [name=phone_number_id]").value || "YOUR_PHONE_NUMBER_ID";
  const waba = account?.waba_id || document.querySelector("#whatsappForm [name=waba_id]").value || "YOUR_WABA_ID";
  const body = prompt("Inbound WhatsApp message", "What are your hours?");
  if (!body) return;
  const payload = {
    entry: [
      {
        id: waba,
        changes: [
          {
            value: {
              metadata: { phone_number_id: phone, display_phone_number: "+8801000000000" },
              contacts: [{ wa_id: "8801711111111", profile: { name: "Demo Customer" } }],
              messages: [
                {
                  id: `wamid.${Date.now()}`,
                  from: "8801711111111",
                  timestamp: String(Math.floor(Date.now() / 1000)),
                  type: "text",
                  text: { body },
                },
              ],
            },
          },
        ],
      },
    ],
  };
  await api("/webhooks/meta/whatsapp", { method: "POST", body: JSON.stringify(payload) });
  toast("Webhook accepted");
  setTimeout(loadInbox, 400);
}

async function deleteWhatsAppAccount(accountId) {
  if (!state.businessId || !accountId) return;
  const account = state.whatsappAccounts.find((item) => item.id === accountId);
  const label = account?.display_phone_number || account?.phone_number_id || "this WhatsApp account";
  if (!confirm(`Delete ${label}? Incoming messages for this phone number will no longer route to this business.`)) return;
  await runUiAction(async () => {
    await api(`/api/businesses/${state.businessId}/whatsapp/accounts/${accountId}`, { method: "DELETE" });
    await loadWhatsAppSetup();
    toast("WhatsApp account deleted");
  });
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab,.view").forEach((el) => el.classList.remove("active"));
    tab.classList.add("active");
    $(`#${tab.dataset.view}`).classList.add("active");
    if (tab.dataset.view === "settings") {
      runUiAction(loadBotBehavior);
    }
  });
});

$("#businessForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  await runUiAction(async () => {
    const payload = formData(form);
    const business = await api("/api/businesses", { method: "POST", body: JSON.stringify(payload) });
    state.businessId = business.id;
    await loadBusinesses();
    $("#businessSelect").value = business.id;
    await loadWhatsAppSetup();
    toast("Tenant created");
  });
});

$("#businessSelect").addEventListener("change", async (event) => {
  await runUiAction(async () => {
    state.businessId = Number(event.target.value);
    state.conversationId = null;
    await loadWhatsAppSetup();
    await loadInbox();
  });
});

$("#actorEmail").addEventListener("change", async () => {
  await runUiAction(async () => {
    await loadSession();
    await loadBusinesses();
    await loadWhatsAppSetup();
    await loadInbox();
  });
});

$("#adminKey").value = localStorage.getItem("adminKey") || "";
$("#adminKey").addEventListener("change", () => {
  localStorage.setItem("adminKey", $("#adminKey").value);
  runUiAction(async () => {
    await loadSession();
    await loadBusinesses();
    await loadWhatsAppSetup();
    await loadInbox();
  });
});

$("#whatsappForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  await runUiAction(async () => {
    if (!state.businessId) return toast("Create a tenant first");
    await api(`/api/businesses/${state.businessId}/whatsapp/accounts`, { method: "POST", body: JSON.stringify(formData(form)) });
    await loadWhatsAppSetup();
    toast("WhatsApp connected");
  });
});

$("#knowledgeForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  await runUiAction(async () => {
    if (!state.businessId) return toast("Create a tenant first");
    const payload = { ...formData(form), type: "faq" };
    await api(`/api/businesses/${state.businessId}/knowledge/sources`, { method: "POST", body: JSON.stringify(payload) });
    form.reset();
    toast("Knowledge added");
  });
});

$("#searchForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  await runUiAction(async () => {
    if (!state.businessId) return toast("Create a tenant first");
    const result = await api(`/api/businesses/${state.businessId}/knowledge/search`, {
      method: "POST",
      body: JSON.stringify({ query: formData(form).query, top_k: 5 }),
    });
    $("#knowledgeResults").innerHTML = result.map((r) => `<div class="item"><strong>${r.score}</strong><br />${escapeHtml(r.content)}</div>`).join("");
  });
});

$("#loadTools").addEventListener("click", async () => {
  await runUiAction(async () => {
    state.tools = await api("/api/tools/catalog");
    $("#toolList").innerHTML = state.tools.map((t) => `<div class="item"><strong>${t.name}</strong><br />${t.description}</div>`).join("");
  });
});

$("#enableCalendar").addEventListener("click", async () => {
  await runUiAction(async () => {
    if (!state.businessId) return toast("Create a tenant first");
    const catalog = state.tools.length ? state.tools : await api("/api/tools/catalog");
    const calendar = catalog[0];
    await api(`/api/businesses/${state.businessId}/tools`, {
      method: "POST",
      body: JSON.stringify({ tool_id: calendar.id, credential: "dev-key", config: {}, policy: {} }),
    });
    toast("Calendar tool enabled");
  });
});

$("#settingsForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  await runUiAction(async () => {
    if (!state.businessId) return toast("Create a tenant first");
    const payload = Object.fromEntries(Object.entries(formData(form)).filter(([, value]) => value));
    await api(`/api/businesses/${state.businessId}/settings/ai`, { method: "PATCH", body: JSON.stringify(payload) });
    toast("Bot behavior saved");
  });
});

async function loadBotBehavior() {
  if (!state.businessId) return;
  const settings = await api(`/api/businesses/${state.businessId}/settings/ai`);
  $("#settingsForm [name=tone]").value = settings.tone || "";
  $("#settingsForm [name=system_prompt]").value = settings.system_prompt || "";
  $("#settingsForm [name=fallback_message]").value = settings.fallback_message || "";
  const session = await api(`/api/businesses/${state.businessId}/onboarding/latest`);
  if (!session) {
    $("#onboardingStatus").textContent = "No WhatsApp setup session yet.";
    $("#workflowConfig").textContent = JSON.stringify(settings.workflow_config_json || {}, null, 2);
    return;
  }
  $("#onboardingStatus").textContent =
    session.status === "completed"
      ? `Setup completed from conversation #${session.conversation_id}.`
      : `Setup ${session.status}. Question ${Math.min(session.current_step + 1, 9)} of 9.`;
  $("#workflowConfig").textContent = JSON.stringify(session.generated_config_json || settings.workflow_config_json || {}, null, 2);
}

$("#replyForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  await runUiAction(async () => {
    if (!state.conversationId) return toast("Open a conversation first");
    await api(`/api/businesses/${state.businessId}/conversations/${state.conversationId}/messages`, {
      method: "POST",
      body: JSON.stringify(formData(form)),
    });
    form.reset();
    await openConversation(state.conversationId);
  });
});

$("#simulateWebhook").addEventListener("click", simulateWebhook);
$("#refreshInbox").addEventListener("click", loadInbox);
$("#refreshWebhookSetup").addEventListener("click", () => runUiAction(refreshWebhookSetup));
$("#refreshOnboarding").addEventListener("click", () => runUiAction(loadBotBehavior));
$("#loadAnalytics").addEventListener("click", async () => {
  await runUiAction(async () => {
    if (!state.businessId) return toast("Create a tenant first");
    $("#analyticsOutput").textContent = JSON.stringify(await api(`/api/businesses/${state.businessId}/analytics/overview`), null, 2);
  });
});

setWebhookPlaceholder("Select a business");

loadSession()
  .then(loadBusinesses)
  .then(async () => {
    await loadWhatsAppSetup();
    await loadInbox();
    await loadBotBehavior();
  })
  .catch((error) => toast(error.message));
