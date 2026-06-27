const state = {
  businessId: null,
  conversationId: null,
  tools: [],
  businesses: [],
  whatsappAccounts: [],
  editingWhatsAppAccountId: null,
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
  if (!res.ok) {
    const detail = data?.detail;
    const message = typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : res.statusText || "Request failed";
    throw new Error(message);
  }
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

function currentBusiness() {
  return state.businesses.find((business) => business.id === Number(state.businessId)) || null;
}

function renderActiveBusinessPanel() {
  const business = currentBusiness();
  const panel = $("#activeBusinessPanel");
  panel.classList.toggle("hidden", !business);
  $("#businessEditForm").classList.add("hidden");
  if (!business) return;
  $("#activeBusinessName").textContent = `#${business.id} ${business.name}`;
  $("#activeBusinessMeta").textContent = `${business.status} - ${business.industry || "No industry"} - ${business.timezone} - ${business.locale} - ${business.plan_id}`;
  panel.querySelectorAll(".platform-only").forEach((el) => {
    el.classList.toggle("platform-hidden", !state.isPlatformAdmin);
  });
}

function businessPayloadFromEditForm(form) {
  const payload = formData(form);
  Object.keys(payload).forEach((key) => {
    if (payload[key] === "") delete payload[key];
  });
  return payload;
}

function startBusinessEdit() {
  const business = currentBusiness();
  if (!business) return toast("Select a business first");
  const form = $("#businessEditForm");
  form.elements.name.value = business.name || "";
  form.elements.industry.value = business.industry || "";
  form.elements.timezone.value = business.timezone || "";
  form.elements.locale.value = business.locale || "";
  form.elements.status.value = business.status || "profile_complete";
  form.elements.plan_id.value = business.plan_id || "starter";
  form.classList.remove("hidden");
  form.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function cancelBusinessEdit() {
  $("#businessEditForm").classList.add("hidden");
}

function setWebhookPlaceholder(message) {
  $("#webhookCallback").textContent = `${window.location.origin}/webhooks/meta/whatsapp`;
  $("#webhookToken").textContent = message;
  $("#whatsappSendMode").textContent = "mock";
  $("#webhookNotice").textContent = "This is the local webhook URL. Use ngrok or set PUBLIC_BASE_URL before adding it to Meta.";
  $("#whatsappAccounts").innerHTML = "";
}

function renderWebhookSetup(setup) {
  const callbackUrl = callbackUrlForCurrentOrigin(setup.callback_url);
  $("#webhookCallback").textContent = callbackUrl;
  $("#webhookToken").textContent = setup.verify_token;
  $("#whatsappSendMode").textContent = setup.send_mode === "auto" ? "auto - live for connected accounts" : setup.send_mode;
  $("#webhookNotice").textContent = setup.is_public_url
    ? "Use this callback URL and verify token in Meta WhatsApp webhook settings."
    : "This URL is local only. Meta cannot reach it until you set PUBLIC_BASE_URL to an ngrok, Cloudflare Tunnel, or deployed HTTPS URL.";
}

function callbackUrlForCurrentOrigin(callbackUrl) {
  try {
    const url = new URL(callbackUrl, window.location.origin);
    const current = new URL(window.location.origin);
    if (current.protocol === "https:" && !["localhost", "127.0.0.1"].includes(current.hostname)) {
      url.protocol = current.protocol;
      url.host = current.host;
    }
    return url.toString();
  } catch {
    return callbackUrl;
  }
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

async function loadRuntimeVersion() {
  try {
    const version = await api("/api/platform/version");
    const label = `${version.app_version} · ${version.send_error_format} · WhatsApp ${version.whatsapp_send_mode}`;
    $("#runtimeVersion").textContent = `Backend ${label}`;
  } catch {
    $("#runtimeVersion").textContent = "Backend version unavailable";
  }
}

async function loadBusinesses() {
  const businesses = await api("/api/businesses");
  state.businesses = businesses;
  const select = $("#businessSelect");
  if (!businesses.length) {
    state.businessId = null;
    state.conversationId = null;
    select.innerHTML = `<option value="">No active business found</option>`;
    setWebhookPlaceholder("Create a business first");
    renderActiveBusinessPanel();
    return businesses;
  }
  select.innerHTML = businesses.map((b) => `<option value="${b.id}">#${b.id} ${escapeHtml(b.name)} (${escapeHtml(b.status)})</option>`).join("");
  const hasSelectedBusiness = businesses.some((business) => business.id === Number(state.businessId));
  if (businesses.length && (!state.businessId || !hasSelectedBusiness)) {
    state.businessId = businesses[0].id;
  }
  if (state.businessId) select.value = state.businessId;
  renderActiveBusinessPanel();
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

async function refreshInbox() {
  const button = $("#refreshInbox");
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Refreshing...";
  try {
    await loadInbox();
    if (state.conversationId) {
      await openConversation(state.conversationId);
    }
    toast("Inbox refreshed");
  } finally {
    button.disabled = false;
    button.textContent = originalText;
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
            <div class="account-actions platform-only">
              <button type="button" class="small" data-edit-whatsapp="${account.id}">Edit</button>
              <button type="button" class="danger small" data-delete-whatsapp="${account.id}">Delete</button>
            </div>
          </div>`
        )
        .join("")
    : `<div class="mini-item"><span>No WhatsApp account connected for this business yet.</span></div>`;
  document.querySelectorAll("[data-edit-whatsapp]").forEach((button) => {
    button.addEventListener("click", () => startWhatsAppEdit(Number(button.dataset.editWhatsapp)));
  });
  document.querySelectorAll("[data-delete-whatsapp]").forEach((button) => {
    button.addEventListener("click", () => deleteWhatsAppAccount(Number(button.dataset.deleteWhatsapp)));
  });
  document.querySelectorAll("#whatsappAccounts .platform-only").forEach((el) => {
    el.classList.toggle("platform-hidden", !state.isPlatformAdmin);
  });
}

function setWhatsAppFormMode(account = null) {
  const form = $("#whatsappForm");
  const isEditing = Boolean(account);
  state.editingWhatsAppAccountId = account?.id || null;
  form.dataset.mode = isEditing ? "edit" : "create";
  $("#whatsappSubmit").textContent = isEditing ? "Save WhatsApp changes" : "Connect WhatsApp";
  $("#cancelWhatsAppEdit").classList.toggle("hidden", !isEditing);
  form.querySelector("[name=app_secret]").required = !isEditing;
  form.querySelector("[name=access_token]").required = !isEditing;
  form.querySelector("[name=app_secret]").placeholder = isEditing ? "Leave blank to keep current secret" : "Paste app secret";
  form.querySelector("[name=access_token]").placeholder = isEditing ? "Leave blank to keep current token" : "EAAG...";
  if (!isEditing) {
    form.reset();
    return;
  }
  form.elements.app_id.value = account.app_id || "";
  form.elements.app_secret.value = "";
  form.elements.access_token.value = "";
  form.elements.phone_number_id.value = account.phone_number_id || "";
  form.elements.waba_id.value = account.waba_id || "";
  form.elements.display_phone_number.value = account.display_phone_number || "";
}

function startWhatsAppEdit(accountId) {
  const account = state.whatsappAccounts.find((item) => item.id === accountId);
  if (!account) return toast("Could not find that WhatsApp account");
  setWhatsAppFormMode(account);
  $("#whatsappForm").scrollIntoView({ behavior: "smooth", block: "start" });
}

function whatsappPayloadFromForm(form) {
  const payload = formData(form);
  if (state.editingWhatsAppAccountId) {
    Object.keys(payload).forEach((key) => {
      if (["app_secret", "access_token", "webhook_verify_token"].includes(key) && !payload[key]) {
        delete payload[key];
      }
    });
  }
  return payload;
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
        <div class="meta">${messageStatusText(m)}</div>
        <div>${escapeHtml(m.body)}</div>
        ${messageErrorText(m)}
        ${messageDebugDetails(m)}
      </div>`
    )
    .join("");
}

function messageStatusText(message) {
  const parts = [message.direction, message.status];
  if (message.ai_generated) parts.push("AI");
  if (message.status === "mock_saved") parts.push("not sent to WhatsApp");
  if (message.status === "sent_to_provider" || message.status === "accepted_by_meta") parts.push("accepted by Meta, waiting for delivery");
  if (message.status === "sent") parts.push("sent by WhatsApp");
  if (message.status === "delivered") parts.push("delivered to customer");
  if (message.status === "read") parts.push("read by customer");
  if (message.status === "failed") parts.push("send failed");
  return parts.join(" · ");
}

function messageErrorText(message) {
  const error = message.provider_payload_json?.error || message.provider_payload_json?.errors?.[0];
  if (!error) return "";
  const text = typeof error === "string" ? error : JSON.stringify(error, null, 2);
  return `<div class="message-error">${escapeHtml(text)}</div>`;
}

function messageDebugDetails(message) {
  if (message.direction !== "outbound") return "";
  const payload = message.provider_payload_json || {};
  const providerId = message.provider_message_id ? `<div>Provider ID: ${escapeHtml(message.provider_message_id)}</div>` : "";
  const payloadText = Object.keys(payload).length ? JSON.stringify(payload, null, 2) : "{}";
  return `<details class="message-debug">
    <summary>Meta send details</summary>
    ${providerId}
    <pre>${escapeHtml(payloadText)}</pre>
  </details>`;
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
    renderActiveBusinessPanel();
    await loadWhatsAppSetup();
    await loadInbox();
  });
});

$("#editBusiness").addEventListener("click", startBusinessEdit);
$("#cancelBusinessEdit").addEventListener("click", cancelBusinessEdit);

$("#businessEditForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  await runUiAction(async () => {
    if (!state.businessId) return toast("Select a business first");
    const business = await api(`/api/businesses/${state.businessId}`, { method: "PATCH", body: JSON.stringify(businessPayloadFromEditForm(form)) });
    state.businessId = business.id;
    await loadBusinesses();
    $("#businessSelect").value = business.id;
    cancelBusinessEdit();
    await loadWhatsAppSetup();
    await loadInbox();
    await loadBotBehavior();
    toast("Business updated");
  });
});

$("#deleteBusiness").addEventListener("click", async () => {
  await runUiAction(async () => {
    const business = currentBusiness();
    if (!business) return toast("Select a business first");
    const label = `#${business.id} ${business.name}`;
    if (!confirm(`Delete ${label}? This permanently removes its WhatsApp accounts, conversations, messages, knowledge, settings, tools, secrets, onboarding, and audit logs.`)) return;
    await api(`/api/businesses/${business.id}`, { method: "DELETE" });
    state.businessId = null;
    state.conversationId = null;
    state.whatsappAccounts = [];
    await loadBusinesses();
    await loadWhatsAppSetup();
    await loadInbox();
    await loadBotBehavior();
    toast("Business deleted");
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
    const accountId = state.editingWhatsAppAccountId;
    const method = accountId ? "PATCH" : "POST";
    const path = accountId
      ? `/api/businesses/${state.businessId}/whatsapp/accounts/${accountId}`
      : `/api/businesses/${state.businessId}/whatsapp/accounts`;
    await api(path, { method, body: JSON.stringify(whatsappPayloadFromForm(form)) });
    setWhatsAppFormMode();
    await loadWhatsAppSetup();
    toast(accountId ? "WhatsApp account updated" : "WhatsApp connected");
  });
});

$("#cancelWhatsAppEdit").addEventListener("click", () => setWhatsAppFormMode());

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
  $("#aiProviderStatus").textContent = settings.openai_configured
    ? "OpenAI is configured. Replies use OpenAI with this business knowledge as context."
    : "OpenAI key is not configured. Replies fall back to saved knowledge.";
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
$("#refreshInbox").addEventListener("click", () => runUiAction(refreshInbox));
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
  .then(async () => {
    await loadRuntimeVersion();
  })
  .then(loadBusinesses)
  .then(async () => {
    await loadWhatsAppSetup();
    await loadInbox();
    await loadBotBehavior();
  })
  .catch((error) => toast(error.message));
