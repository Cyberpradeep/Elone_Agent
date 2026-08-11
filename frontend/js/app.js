// ============================================================
// EloneAgent — Front-end dashboard logic
// ============================================================

(function () {
  "use strict";

  /* ---------------- Theme helper ---------------- */
  const THEME_KEY = "eloneagent-theme";
  const root = document.documentElement;
  const themeBtn = document.getElementById("themeToggle");

  function applyTheme(theme) {
    if (theme === "dark" || theme === "light") {
      root.setAttribute("data-theme", theme);
    } else {
      root.removeAttribute("data-theme");
    }
  }
  const savedTheme = localStorage.getItem(THEME_KEY);
  if (savedTheme) applyTheme(savedTheme);

  if (themeBtn) {
    themeBtn.addEventListener("click", () => {
      const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      const current = root.getAttribute("data-theme") || (prefersDark ? "dark" : "light");
      const next = current === "dark" ? "light" : "dark";
      applyTheme(next);
      localStorage.setItem(THEME_KEY, next);
    });
  }

  /* ---------------- Shared helpers ---------------- */
  function toast(message) {
    let el = document.getElementById("toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "toast";
      el.className = "toast";
      document.body.appendChild(el);
    }
    el.textContent = message;
    el.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.remove("show"), 3200);
  }

  function nowTime() {
    return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  // Escapes text for interpolation into markup. The textContent round-trip
  // covers & < >, but NOT quotes -- which matters because some of these values
  // land inside HTML attributes, where an unescaped " breaks out of the
  // attribute. Step text is LLM-generated from ingested SOPs, so it is not
  // trusted input.
  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  async function api(path, options) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    let data = null;
    try { data = await res.json(); } catch (e) { }
    if (!res.ok) {
      const detail = (data && data.detail) || res.statusText || "Request failed";
      throw new Error(detail);
    }
    return data;
  }

  function updateTicketFromResponse(ticket, resp) {
    if (!ticket || !resp) return;

    const steps = (resp.execution_plan && resp.execution_plan.steps) || [];
    if (steps.length) ticket.totalSteps = steps.length;

    // Progress reflects steps that genuinely executed -- never assume a
    // finished workflow ran every step.
    ticket.currentStep = steps.length
      ? completedStepCount(resp, steps)
      : (resp.current_step_index || 0);

    // Real triage output replaces the placeholders the card was created with.
    // Priority / SOP / user used to stay hardcoded at "High" / "SOP-001" /
    // "Generated User" for every ticket regardless of what the agent decided.
    if (resp.priority) ticket.priority = resp.priority;
    if (resp.sop && resp.sop.sop_id) ticket.sop = resp.sop.sop_id;
    if (resp.category) ticket.department = resp.category;
    if (resp.customer_email) ticket.email = resp.customer_email;
    const who = (resp.entities || {}).employee_name;
    if (who) ticket.user = who;

    // Set status. "escalated" is its own state -- collapsing it into "pending"
    // made a failed ticket indistinguishable from one awaiting approval.
    // awaiting_approval alone is NOT enough for "pending": the graph re-pauses
    // before every step and auto-resumes, so mid-execution frames carry
    // awaiting_approval=true. Only an *unapproved* gate is genuinely waiting
    // on the operator -- the badge used to flicker PENDING while steps ran.
    if (resp.done) {
      ticket.status = resp.workflow_status === "escalated" ? "escalated" : "completed";
    } else if (resp.awaiting_approval && !isApproved(resp)) {
      ticket.status = "pending";
    } else if (resp.awaiting_clarification) {
      ticket.status = "pending";
    } else {
      ticket.status = "in_progress";
    }
  }

  /* ================================================================
     TICKET DATA & STATE MANAGEMENT
     ================================================================ */
  let tickets = [];
  const approvedThreads = new Set();
  const rejectedThreads = new Set();

  let activeTicketId = null;
  let activeThreadId = null;
  let activeResp = null;
  let isExecuting = false;
  let currentFilter = "all";
  let searchQuery = "";

  /* ---------------- DOM References ---------------- */
  const ticketList = document.getElementById("ticketList");
  const ticketSearch = document.getElementById("ticketSearch");
  const filterChips = document.querySelector(".filter-chips");
  const consoleBody = document.getElementById("consoleBody");
  const sessionLabel = document.getElementById("sessionLabel");
  const copySessionBtn = document.getElementById("copySessionBtn");

  // Modal
  const modalOverlay = document.getElementById("ticketModalOverlay");
  const modalCloseBtn = document.getElementById("modalCloseBtn");
  const modalCancelBtn = document.getElementById("modalCancelBtn");
  const createTicketBtn = document.getElementById("createTicketBtn");
  const loadSampleBtn = document.getElementById("loadSampleBtn");
  const newTicketBtn = document.getElementById("newTicketBtn");
  const emptyNewTicketBtn = document.getElementById("emptyNewTicketBtn");

  const ticketEmail = document.getElementById("ticketEmail");
  const ticketUserId = document.getElementById("ticketUserId");
  const ticketCategory = document.getElementById("ticketCategory");
  const ticketDescription = document.getElementById("ticketDescription");

  // Right Rail Widgets
  const executionProgressList = document.getElementById("executionProgressList");
  const remoteMachineInfo = document.getElementById("remoteMachineInfo");

  // Center panel: ticket-contextual header + sub-header + bottom prompt bar
  const consoleTicketId = document.getElementById("consoleTicketId");
  const consoleTicketSep = document.getElementById("consoleTicketSep");
  const consoleTicketIssue = document.getElementById("consoleTicketIssue");
  const liveBadge = document.getElementById("liveBadge");
  const durationBadge = document.getElementById("durationBadge");
  const endSessionBtn = document.getElementById("endSessionBtn");
  const consoleSubHeader = document.getElementById("consoleSubHeader");

  /* ================================================================
     TICKET QUEUE RENDERING & FILTERS
     ================================================================ */
  function renderTickets() {
    ticketList.innerHTML = "";
    
    const filtered = tickets.filter(t => {
      const matchesFilter = 
        currentFilter === "all" || 
        t.status === currentFilter;
      const matchesSearch = 
        t.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        t.issue.toLowerCase().includes(searchQuery.toLowerCase()) ||
        t.user.toLowerCase().includes(searchQuery.toLowerCase()) ||
        t.email.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesFilter && matchesSearch;
    });

    if (filtered.length === 0) {
      ticketList.innerHTML = `<div style="text-align:center;color:var(--text-muted);padding:20px;font-size:12px;">No tickets found.</div>`;
      return;
    }

    filtered.forEach(t => {
      const card = document.createElement("div");
      card.className = `ticket-card ${t.id === activeTicketId ? "selected" : ""}`;
      
      const isHigh = t.priority.toLowerCase() === "high";
      const isMed = t.priority.toLowerCase() === "medium";
      const priorityClass = isHigh ? "high" : isMed ? "medium" : "low";

      // Everything else (user/email/category/agent/SOP/step) lives in the
      // REMOTE MACHINE panel now -- this card is just the at-a-glance list.
      card.innerHTML = `
        <div class="ticket-card-header">
          <span class="ticket-id">${t.id}</span>
          <span class="ticket-priority ${priorityClass}">${t.priority}</span>
        </div>
        <div class="ticket-issue">${escapeHtml(t.issue)}</div>
        <div class="ticket-card-footer">
          <span class="ticket-status-badge ${t.status}">${t.status.replace("_", " ")}</span>
        </div>
      `;

      card.addEventListener("click", () => {
        activeTicketId = t.id;
        renderTickets();
        loadTicketConsole(t);
      });

      ticketList.appendChild(card);
    });
  }

  // Filter chips listeners
  if (filterChips) {
    filterChips.addEventListener("click", (e) => {
      if (e.target.classList.contains("chip")) {
        filterChips.querySelectorAll(".chip").forEach(c => c.classList.remove("active"));
        e.target.classList.add("active");
        currentFilter = e.target.dataset.filter;
        renderTickets();
      }
    });
  }

  // Search input listener
  if (ticketSearch) {
    ticketSearch.addEventListener("input", (e) => {
      searchQuery = e.target.value;
      renderTickets();
    });
  }

  /* ================================================================
     CONSOLE & TERMINAL LOG RENDERING
     ================================================================ */
  function buildConsoleLine(tag, text, timeStr) {
    const row = document.createElement("div");
    row.className = "console-row";

    const displayTime = timeStr || nowTime();
    const tagClass = (tag || "system").toLowerCase();

    row.innerHTML = `
      <span class="console-row-time">${displayTime}</span>
      <span class="console-row-tag ${tagClass}">[${tag.toUpperCase()}]</span>
      <span class="console-row-text"></span>
    `;
    row.querySelector(".console-row-text").textContent = text;
    return row;
  }

  function addConsoleLine(tag, text, timeStr) {
    appendToConsole(buildConsoleLine(tag, text, timeStr));
  }

  /* ---------------- Console transcript reconciliation ----------------
     The console is an APPEND-ONLY transcript, not a snapshot. It used to be
     wiped (`consoleBody.innerHTML = ""`) and rebuilt from the latest state on
     every SSE frame, which caused both long-standing complaints:

       * Flicker -- every row was destroyed and recreated several times a
         second, re-firing the `line-appear` animation on the whole console.
       * Wrong order -- the transcript was re-derived from cumulative state,
         so step lines were emitted in plan order while the (single, latest)
         reasoning line was always dumped at the bottom. Step 1's output never
         stayed under step 1.

     Instead each piece of the transcript is emitted with a stable key. A key
     seen for the first time is appended (so paint order == execution order);
     a key whose content changed is replaced in place; everything else is left
     untouched, so nothing flickers. Only switching tickets clears it. */
  const consoleItems = new Map();  // key -> { el, sig }
  let processingRow = null;

  // Auto-follow only when the operator is already at the bottom -- otherwise
  // scrolling up to read step 2's output yanked them back down on every frame.
  function isPinnedToBottom() {
    return consoleBody.scrollHeight - consoleBody.scrollTop - consoleBody.clientHeight < 40;
  }

  function appendToConsole(el) {
    const pinned = isPinnedToBottom();
    consoleBody.appendChild(el);
    if (pinned) consoleBody.scrollTop = consoleBody.scrollHeight;
  }

  function resetConsole() {
    consoleBody.innerHTML = "";
    consoleItems.clear();
    processingRow = null;
    activeReviewStepIndex = 0;
    wizardEdits = {};
  }


  // `build` is only invoked when something actually needs to be created, so
  // unchanged rows keep their existing DOM node (and their animation state).
  function emit(key, sig, build) {
    const prev = consoleItems.get(key);
    if (prev && prev.sig === sig && prev.el && prev.el.parentNode) return;

    const el = build();
    if (!el) return;

    if (prev && prev.el && prev.el.parentNode) {
      prev.el.parentNode.replaceChild(el, prev.el);
    } else {
      appendToConsole(el);
    }
    consoleItems.set(key, { el, sig });
  }

  /* ---------------- Operator transcript ----------------
     The operator's own decisions ("> no", "User rejected...") are recorded
     here as well as emitted, so re-opening a ticket replays them in the same
     position they originally occupied. */
  let consoleJournal = [];

  function journal(tag, text) {
    consoleJournal.push({ tag, text, time: nowTime() });
    emitJournal();
  }

  function emitJournal() {
    consoleJournal.forEach((e, i) => {
      emit(`journal|${i}`, e.text, () => buildConsoleLine(e.tag, e.text, e.time));
    });
  }

  // Loaded when clicking on tickets or generating a new one
  function loadTicketConsole(ticket) {
    resetConsole();
    if (!ticket) {
      consoleBody.innerHTML = `
        <div class="console-empty" id="emptyChatCta">
          <div class="welcome-box">
            <div class="agent-avatar-welcome">EA</div>
            <h3>EloneAgent v1.0.0</h3>
            <p>Autonomous L1 support agent ready for action. Click "New" to create a support ticket and begin execution.</p>
            <button class="btn-create-welcome" id="emptyNewTicketBtn">Create Support Ticket</button>
          </div>
        </div>
      `;
      const wBtn = document.getElementById("emptyNewTicketBtn");
      if (wBtn) wBtn.addEventListener("click", openModal);

      sessionLabel.textContent = "No active session";
      copySessionBtn.dataset.session = "";

      renderWorkflowChecklist(null);
      renderConsoleHeader(null, null);
      renderRemoteMachinePanel(null, null);
      return;
    }

    sessionLabel.textContent = activeThreadId ? activeThreadId : "No active session";
    copySessionBtn.dataset.session = activeThreadId || "";

    // Always render from real workflow state. (This used to fall back to a
    // hardcoded demo transcript + 4 invented "all complete" SOP steps, which
    // overwrote the live view with a finished-looking ticket that had nothing
    // to do with what actually ran.)
    if (ticket.threadId && activeResp && activeResp.thread_id === ticket.threadId) {
      renderLiveConsoleFlow(activeResp);
      return;
    }

    if (ticket.threadId) {
      // Selected a ticket whose state isn't cached (e.g. switching back to an
      // earlier one) -- pull its real state from the server. The journal is
      // per-thread, so it does not carry over to a different ticket.
      consoleJournal = [];
      lastContactAt = null;
      addConsoleLine("SYSTEM", "Loading ticket state...");
      api(`/api/tickets/${ticket.threadId}/state`)
        .then(state => {
          if (activeTicketId !== ticket.id) return;  // user moved on meanwhile
          activeThreadId = ticket.threadId;
          activeResp = state;
          updateTicketFromResponse(ticket, state);
          renderTickets();
          renderLiveConsoleFlow(state);
        })
        .catch(err => {
          resetConsole();
          addConsoleLine("error", `Could not load ticket state: ${err.message}`);
        });
      return;
    }

    // No agent thread behind this ticket (nothing has been run for it yet).
    consoleBody.innerHTML = `
      <div class="console-empty">
        <div class="welcome-box">
          <div class="agent-avatar-welcome">EA</div>
          <h3>EloneAgent ready</h3>
          <p>No agent run is attached to this ticket yet. Create a new ticket to start an execution session.</p>
        </div>
      </div>
    `;
    renderWorkflowChecklist(null);
    renderConsoleHeader(ticket, null);
    renderRemoteMachinePanel(null, ticket);
  }

  // The plan is rendered read-only. It previously used single-line <input>s
  // that clipped ~28-40% of longer descriptions and truncated the command
  // itself -- asking the operator to approve a destructive command they could
  // not fully read. Text now lives in wrapping <pre>/<div> nodes set via
  // textContent, so nothing is ever hidden and nothing is interpolated as
  // markup. Description and command are contenteditable while the plan is
  // unlocked -- /approve now accepts the edited text and applies it to the
  // plan (matched by step_number) before execution resumes. Only steps that
  // already carried a raw command get an editable command field: synthetic
  // labels like "manual step" or "tool.function()" aren't executable, so
  // editing them would silently do nothing.
  function formatStepAction(s) {
    if (!s) return "manual step";
    if (s.command && typeof s.command === "string" && s.command.length > 0) {
      return s.command;
    }
    const provider = s.provider || s.tool_name;
    const fn = s.function_name;
    if (provider || fn) {
      let inputsStr = "";
      if (s.comm_inputs && Object.keys(s.comm_inputs).length > 0) {
        inputsStr = JSON.stringify(s.comm_inputs);
      }
      return `${provider || 'tool'}.${fn || 'call'}(${inputsStr})`;
    }
    if (s.step_type === "communication") {
      return "[COMMUNICATION STEP]";
    }
    if (s.step_type === "manual") {
      return "[MANUAL INTERVENTION]";
    }
    return s.step_type ? `[${s.step_type.toUpperCase()}]` : "manual step";
  }

  /* ---------------- Sequential Step Review Wizard & Custom Modal ---------------- */
  let activeReviewStepIndex = 0;
  let wizardEdits = {};
  let activeRejectStepNum = null;
  let activeRejectStepDesc = "";

  function openStepRejectModal(stepNum, stepDesc) {
    const modal = document.getElementById("stepRejectModalOverlay");
    const numLabel = document.getElementById("rejectStepNumLabel");
    const descLabel = document.getElementById("rejectStepDescLabel");
    const reasonInput = document.getElementById("stepRejectReasonInput");

    if (numLabel) numLabel.textContent = `Step ${stepNum}`;
    if (descLabel) descLabel.textContent = stepDesc || "";
    if (reasonInput) reasonInput.value = "";

    activeRejectStepNum = stepNum;
    activeRejectStepDesc = stepDesc;

    if (modal) {
      modal.style.display = "flex";
      if (reasonInput) setTimeout(() => reasonInput.focus(), 100);
    }
  }

  function closeStepRejectModal() {
    const modal = document.getElementById("stepRejectModalOverlay");
    if (modal) modal.style.display = "none";
  }

  async function confirmStepRejection() {
    const reasonInput = document.getElementById("stepRejectReasonInput");
    const teamSelect = document.getElementById("stepRejectTeamSelect");
    const reason = reasonInput ? reasonInput.value.trim() : "";
    const team = teamSelect ? teamSelect.value : "L2 Systems Infrastructure";

    if (!reason) {
      toast("Please specify a reason for rejecting this step.");
      if (reasonInput) reasonInput.focus();
      return;
    }

    if (activeThreadId) rejectedThreads.add(activeThreadId);

    const card = document.getElementById("activeWizardCard");
    if (card) {
      card.querySelectorAll("button").forEach(btn => { btn.disabled = true; });
    }

    if (activeResp) renderLiveConsoleFlow(activeResp);

    closeStepRejectModal();
    toast("Submitting rejection and escalating ticket...");

    const t = tickets.find(x => x.id === activeTicketId);
    if (t) { t.status = "escalated"; renderTickets(); }

    if (!activeThreadId) {
      toast("Error: No active thread session for this ticket.");
      return;
    }

    await kickAndStream(() => api(`/api/tickets/${activeThreadId}/reject`, {
      method: "POST",
      body: JSON.stringify({
        reason: reason,
        rejected_step: activeRejectStepNum,
        escalation_team: team
      })
    }));
  }

  async function submitWizardApproval() {
    if (activeThreadId) approvedThreads.add(activeThreadId);

    const card = document.getElementById("activeWizardCard");
    if (card) {
      card.querySelectorAll("button").forEach(btn => { btn.disabled = true; });
    }

    if (activeResp) renderLiveConsoleFlow(activeResp);

    toast("Approving execution plan & starting run...");
    const editedList = Object.values(wizardEdits);
    const t = tickets.find(x => x.id === activeTicketId);
    if (t) { t.status = "in_progress"; renderTickets(); }

    if (!activeThreadId) {
      toast("Error: No active thread session for this ticket.");
      return;
    }

    await kickAndStream(() => api(`/api/tickets/${activeThreadId}/approve`, {
      method: "POST",
      body: JSON.stringify({ edited_steps: editedList }),
    }));
  }

  // Register rejection modal listeners once initialized
  document.addEventListener("DOMContentLoaded", () => {
    const stepRejectCloseBtn = document.getElementById("stepRejectModalCloseBtn");
    const stepRejectCancelBtn = document.getElementById("stepRejectModalCancelBtn");
    const stepRejectConfirmBtn = document.getElementById("stepRejectModalConfirmBtn");

    if (stepRejectCloseBtn) stepRejectCloseBtn.addEventListener("click", closeStepRejectModal);
    if (stepRejectCancelBtn) stepRejectCancelBtn.addEventListener("click", closeStepRejectModal);
    if (stepRejectConfirmBtn) stepRejectConfirmBtn.addEventListener("click", confirmStepRejection);
  });

  function buildStepReviewWizardCard(steps, questionText = "") {
    if (activeReviewStepIndex >= steps.length) activeReviewStepIndex = steps.length - 1;
    if (activeReviewStepIndex < 0) activeReviewStepIndex = 0;

    const currentStep = steps[activeReviewStepIndex];
    const stepNum = currentStep.step_number || (activeReviewStepIndex + 1);

    if (!wizardEdits[stepNum]) {
      wizardEdits[stepNum] = {
        step_number: stepNum,
        sop_step_description: currentStep.sop_step_description || "",
        command: currentStep.command || ""
      };
    }
    const currentEdit = wizardEdits[stepNum];

    const card = document.createElement("div");
    card.className = "wizard-card";
    card.id = "activeWizardCard";

    let progressSegmentsHtml = "";
    steps.forEach((s, idx) => {
      let cls = "wizard-progress-bar-segment";
      if (idx < activeReviewStepIndex) cls += " passed";
      else if (idx === activeReviewStepIndex) cls += " active";
      progressSegmentsHtml += `<div class="${cls}"></div>`;
    });

    const isDangerous = !!(currentStep.is_dangerous || currentStep.danger_warning);
    const hasDependency = !!(currentStep.execute_if || (currentStep.command && String(currentStep.command).includes("{")));
    const stepActionText = formatStepAction(currentStep);

    card.innerHTML = `
      <div class="wizard-header">
        <div class="wizard-title-row">
          <div class="wizard-step-title">
            <span>Sequential Step Review</span>
            ${isDangerous ? `<span class="risk-badge high">⚠️ High Risk</span>` : `<span class="risk-badge low">✓ Standard</span>`}
            ${hasDependency ? `<span class="dep-badge">⚡ Dynamic Dependency</span>` : ""}
          </div>
          <span class="wizard-step-counter">Step ${activeReviewStepIndex + 1} of ${steps.length}</span>
        </div>
        <div class="wizard-progress-track">
          ${progressSegmentsHtml}
        </div>
      </div>

      <div class="wizard-body">
        <div class="wizard-field-group">
          <div class="wizard-field-label">Step Description &amp; Rationale</div>
          <div class="wizard-field-value editable-desc" contenteditable="true" spellcheck="false" title="Click to edit description">${escapeHtml(currentEdit.sop_step_description)}</div>
        </div>

        <div class="wizard-field-group">
          <div class="wizard-field-label">Command / Action Tool</div>
          <div class="wizard-cmd-box editable-cmd" contenteditable="true" spellcheck="false" title="Click to edit command syntax">${escapeHtml(currentEdit.command || stepActionText)}</div>
        </div>

        ${currentStep.danger_warning ? `
          <div class="step-plan-warning" style="margin-top:4px;">
            ⚠️ ${escapeHtml(currentStep.danger_warning)}
          </div>
        ` : ""}
      </div>

      <div class="wizard-actions-row">
        <div class="wizard-actions-left">
          <button type="button" class="btn-wizard-prev" id="wPrevBtn" ${activeReviewStepIndex === 0 ? "disabled" : ""}>
            ⇠ Previous
          </button>
          <button type="button" class="btn-wizard-reject" id="wRejectBtn">
            ✕ Reject Step
          </button>
        </div>
        <div class="wizard-actions-right">
          ${activeReviewStepIndex < steps.length - 1 ? `
            <button type="button" class="btn-wizard-next" id="wNextBtn">
              Next Step: Step ${activeReviewStepIndex + 2} ➔
            </button>
          ` : `
            <button type="button" class="btn-wizard-execute" id="wExecuteBtn">
              🚀 Execute All Approved Steps
            </button>
          `}
        </div>
      </div>
    `;

    const descEl = card.querySelector(".editable-desc");
    const cmdEl = card.querySelector(".editable-cmd");

    if (descEl) {
      descEl.addEventListener("blur", () => {
        wizardEdits[stepNum].sop_step_description = descEl.textContent.trim();
      });
    }
    if (cmdEl) {
      cmdEl.addEventListener("blur", () => {
        wizardEdits[stepNum].command = cmdEl.textContent.trim();
      });
    }

    const prevBtn = card.querySelector("#wPrevBtn");
    const nextBtn = card.querySelector("#wNextBtn");
    const executeBtn = card.querySelector("#wExecuteBtn");
    const rejectBtn = card.querySelector("#wRejectBtn");

    if (prevBtn) {
      prevBtn.addEventListener("click", () => {
        if (activeReviewStepIndex > 0) {
          activeReviewStepIndex--;
          const container = document.getElementById("activeWizardCard");
          if (container && container.parentNode) {
            const newCard = buildStepReviewWizardCard(steps, questionText);
            container.parentNode.replaceChild(newCard, container);
            consoleItems.set("plan", { el: newCard, sig: `${steps.length}|open` });
          }
        }
      });
    }

    if (nextBtn) {
      nextBtn.addEventListener("click", () => {
        if (activeReviewStepIndex < steps.length - 1) {
          activeReviewStepIndex++;
          const container = document.getElementById("activeWizardCard");
          if (container && container.parentNode) {
            const newCard = buildStepReviewWizardCard(steps, questionText);
            container.parentNode.replaceChild(newCard, container);
            consoleItems.set("plan", { el: newCard, sig: `${steps.length}|open` });
          }
        }
      });
    }

    if (rejectBtn) {
      rejectBtn.addEventListener("click", () => {
        openStepRejectModal(stepNum, currentEdit.sop_step_description || currentStep.sop_step_description);
      });
    }

    if (executeBtn) {
      executeBtn.addEventListener("click", () => {
        submitWizardApproval();
      });
    }

    return card;
  }


  function buildPlanApprovalCard(steps, locked = false, questionText = "") {
    const card = document.createElement("div");
    card.className = "console-step-card plan-card" + (locked ? " locked" : "");
    if (!locked) card.id = "activeYamlCard";

    const header = document.createElement("div");
    header.className = "console-step-card-header";
    header.innerHTML = `
      <span class="console-step-num">Execution plan (${steps.length} step${steps.length === 1 ? "" : "s"})</span>
      <span class="console-step-status-tag ${locked ? "locked" : "waiting"}">${locked ? "Locked" : "Awaiting approval"}</span>
    `;
    card.appendChild(header);

    const lede = document.createElement("div");
    lede.className = "plan-lede";
    lede.textContent = locked
      ? `${steps.length} step${steps.length === 1 ? "" : "s"} in this plan.`
      : "Review every step below before approving.";
    card.appendChild(lede);

    const list = document.createElement("div");
    list.className = "execution-plan-list";

    steps.forEach(s => {
      const isDangerous = !!(s.is_dangerous || s.danger_warning);
      const hasRawCommand = typeof s.command === "string" && s.command.length > 0;
      const row = document.createElement("div");
      row.className = "step-plan-row" + (isDangerous ? " dangerous" : "");
      row.dataset.stepNumber = String(s.step_number);
      row.dataset.hasCommand = hasRawCommand ? "1" : "0";

      const num = document.createElement("span");
      num.className = "step-plan-num";
      num.textContent = String(s.step_number).padStart(2, "0");
      row.appendChild(num);

      const body = document.createElement("div");
      body.className = "step-plan-body";

      const desc = document.createElement("span");
      desc.className = "step-plan-desc" + (locked ? "" : " editable-field");
      desc.textContent = s.sop_step_description || "";
      if (!locked) {
        desc.contentEditable = "true";
        desc.spellcheck = false;
        desc.title = "Click to edit this step's description";
        desc.addEventListener("keydown", (e) => {
          if (e.key === "Enter") { e.preventDefault(); desc.blur(); }
        });
      }
      body.appendChild(desc);

      if (isDangerous) {
        const badge = document.createElement("span");
        badge.className = "step-danger-badge";
        badge.textContent = "Sensitive";
        body.appendChild(badge);
      }
      row.appendChild(body);

      const cmd = document.createElement("pre");
      cmd.className = "step-plan-cmd" + (!locked && hasRawCommand ? " editable-field" : "");
      cmd.textContent = formatStepAction(s);
      if (!locked && hasRawCommand) {
        cmd.contentEditable = "true";
        cmd.spellcheck = false;
        cmd.title = "Click to edit the command that will run for this step";
      }
      row.appendChild(cmd);

      if (s.danger_warning || isDangerous) {

        const warn = document.createElement("div");
        warn.className = "step-plan-warning";
        warn.textContent = s.danger_warning || "Sensitive execution. Ensure customer validation.";
        row.appendChild(warn);
      }

      list.appendChild(row);
    });
    card.appendChild(list);

    // Only ask the question while the answer can still change anything. A
    // finished ticket used to keep prompting "Do you want to proceed with
    // execution?" forever.
    if (!locked) {
      const prompt = document.createElement("div");
      prompt.className = "confirmation-prompt-section";
      prompt.innerHTML = `
        <div class="confirm-req-label">User confirmation required</div>
        <div class="confirm-question"></div>
        <div class="approval-actions" id="approvalActionsRow">
          <button type="button" class="btn-approve" id="approveBtn">Approve</button>
          <button type="button" class="btn-reject" id="rejectBtn">Reject</button>
          <span class="approval-hint">or type <b>yes</b> / <b>no</b> then Enter</span>
        </div>
        <div class="inline-input-line" id="approvalInputRow">
          <span class="inline-caret">&gt;</span>
          <input type="text" class="inline-input-field" id="inlineConfirmInput" placeholder="yes / no" autocomplete="off" />
        </div>
        <div class="rejection-reason-box" id="rejectionReasonBox" style="display:none; margin-top: 12px; padding: 10px; background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 6px;">
          <div class="confirm-req-label" style="color: #ef4444; margin-bottom: 6px;">Reason for Rejection</div>
          <div class="inline-input-line" style="display: flex; gap: 8px;">
            <span class="inline-caret" style="color: #ef4444;">&gt;</span>
            <input type="text" class="inline-input-field" id="rejectionReasonInput" placeholder="Specify reason for rejection..." autocomplete="off" style="flex:1;" />
            <button type="button" class="btn-reject" id="confirmRejectBtn" style="white-space: nowrap;">Confirm Rejection</button>
          </div>
        </div>
      `;
      prompt.querySelector(".confirm-question").textContent =
        questionText || "Do you want to proceed with execution?";
      card.appendChild(prompt);

      // Bound directly to the elements just created, not looked up by id from
      // a deferred callback. Direct binding cannot race.
      const approveBtn = prompt.querySelector("#approveBtn");
      const rejectBtn = prompt.querySelector("#rejectBtn");
      const inputField = prompt.querySelector("#inlineConfirmInput");
      const rejectionBox = prompt.querySelector("#rejectionReasonBox");
      const rejectionInput = prompt.querySelector("#rejectionReasonInput");
      const confirmRejectBtn = prompt.querySelector("#confirmRejectBtn");

      function triggerRejectionPrompt() {
        if (rejectionBox) {
          rejectionBox.style.display = "block";
          if (rejectionInput) rejectionInput.focus();
        }
      }

      if (approveBtn) approveBtn.addEventListener("click", () => submitApproval(true));
      if (rejectBtn) rejectBtn.addEventListener("click", triggerRejectionPrompt);
      if (confirmRejectBtn) {
        confirmRejectBtn.addEventListener("click", () => {
          const reason = rejectionInput ? rejectionInput.value.trim() : "";
          submitApproval(false, reason || "Plan rejected by operator.");
        });
      }
      if (rejectionInput) {
        rejectionInput.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            const reason = rejectionInput.value.trim();
            submitApproval(false, reason || "Plan rejected by operator.");
          }
        });
      }
      if (inputField) {
        inputField.addEventListener("keydown", (e) => {
          if (e.key !== "Enter") return;
          const val = inputField.value.trim().toLowerCase();
          if (val === "yes" || val === "y") submitApproval(true);
          else if (val === "no" || val === "n") triggerRejectionPrompt();
          else toast("Type 'yes' or 'no', or use the Approve / Reject buttons.");
        });
      }
    }

    return card;
  }

  /* ================================================================
     STEP STATUS HELPERS
     execution_results[step_number] is a raw stdout/stderr STRING (not an
     object with a .status field) -- current_step_index only advances past
     a step once it succeeds, so status is derived from that instead.
     ================================================================ */
  // True once the user has approved the plan. current_step_index stays 0
  // while step 1 is still in flight, so the audit marker is the only
  // reliable signal that execution has actually been authorised.
  function isApproved(resp) {
    if (!resp) return false;
    const tid = (resp && (resp.thread_id || resp.threadId)) || activeThreadId;
    if (tid && rejectedThreads.has(tid)) return false;
    if (tid && approvedThreads.has(tid)) return true;
    if ((resp.current_step_index || 0) > 0) return true;
    if ((resp.last_executed_step || 0) > 0) return true;
    if (Object.keys(resp.execution_results || {}).length > 0) return true;
    return (resp.audit_log || []).some(a =>
      a.includes("[HITL] User approved") ||
      a.includes("User approved the execution plan")
    );
  }

  // True when the operator declined the plan. A rejection halts the workflow
  // before execution_agent ever runs, so no step can be blamed for it.
  function isRejected(resp) {
    if (!resp) return false;
    const tid = (resp && (resp.thread_id || resp.threadId)) || activeThreadId;
    if (tid && rejectedThreads.has(tid)) return true;
    return (resp.audit_log || []).some(a =>
      a.includes("[HITL REJECT]") ||
      a.includes("User rejected") ||
      a.includes("Operator rejected")
    );
  }

  // A step's real status comes from execution_results, which the backend keys
  // by EXECUTION POSITION (current_step_index + 1), not by the plan's own
  // step_number field. The plan is LLM-generated, so its step_number values
  // are not guaranteed to match positions -- matching by them let a generated
  // plan with quirky numbering desync every status in the console and rail.
  // All lookups here are positional (pos = 0-based index into steps).
  function getStepStatusAt(resp, pos) {
    const results = resp.execution_results || {};
    const exitCodes = resp.execution_exit_codes || {};
    const idx = resp.current_step_index || 0;
    const key = pos + 1;
    const hasRun = Object.prototype.hasOwnProperty.call(results, key)
      || Object.prototype.hasOwnProperty.call(results, String(key));

    if (resp.done && resp.workflow_status === "escalated"
        && isApproved(resp) && !isRejected(resp) && pos === idx) return "failed";
    if (hasRun) {
      // Ground truth is the real exit code, not just "did this step produce a
      // result" -- a non-zero exit still landed in execution_results (the LLM
      // verifier may have parsed retryable output as SUCCESS), so without this
      // check a step that actually failed on the wire showed green.
      const exitRaw = Object.prototype.hasOwnProperty.call(exitCodes, key)
        ? exitCodes[key] : exitCodes[String(key)];
      if (exitRaw !== undefined && exitRaw !== null && Number(exitRaw) !== 0) return "failed";
      return "completed";
    }

    // Execution finished without this step running. On a successful workflow
    // that means execution_agent's execute_if precondition was false -- the
    // step was SKIPPED by design (e.g. "tracert only if external connectivity
    // failed"). Reporting it "Pending" forever made a healthy ticket look
    // unfinished; counting it against progress painted Execution red.
    //
    // Every post-execution status counts, not just "completed". The
    // orchestrator sets "completed" when it hands off to summarization, but
    // summarization_agent then OVERWRITES it with "done"/"escalated" -- so
    // testing for "completed" alone made every skipped step flip back to
    // Pending, and the step at current_step_index back to Running, on the
    // summarization frame, right as the resolution block appeared.
    const executionOver = resp.done
      || resp.workflow_status === "completed"
      || resp.workflow_status === "done"
      || !!resp.resolution_type;
    if (executionOver) {
      return resp.workflow_status === "escalated" ? "pending" : "";
    }
    if (isApproved(resp) && pos === idx) return "running";
    return "pending";
  }

  // How many steps genuinely executed -- used for progress counts so the
  // ticket card / header can't claim more progress than actually happened.
  function completedStepCount(resp, steps) {
    return steps.filter((s, i) => getStepStatusAt(resp, i) === "completed").length;
  }

  function getStepOutputAt(resp, pos) {
    const results = resp.execution_results || {};
    const raw = results[pos + 1] != null ? results[pos + 1] : results[String(pos + 1)];
    return typeof raw === "string" ? raw : (raw ? JSON.stringify(raw) : "");
  }

  // Which step numbers the user has manually expanded -- preserved across the
  // full console re-renders that happen on every SSE event, so clicking a
  // step open doesn't get reset the moment another step finishes.
  const expandedSteps = new Set();

  // Collapsible per-step line: click to reveal that step's command + output.
  // status is one of "pending" | "running" | "completed" | "failed" | "skipped".
  // `note` is an optional muted explanation line (e.g. why a step was skipped).
  function buildStepLine(stepNum, title, status, tool, output, total, note) {
    const details = document.createElement("details");
    details.className = `step-line status-${status}`;
    details.open = expandedSteps.has(stepNum);
    details.addEventListener("toggle", () => {
      if (details.open) expandedSteps.add(stepNum);
      else expandedSteps.delete(stepNum);
    });

    // No spinner here on purpose -- the "running" animation lives in the
    // single bottom-of-console indicator instead of inside each step row.
    const iconMap = { completed: "✓", failed: "✕", running: "▶", skipped: "⊘" };
    const labelMap = { completed: "Completed", failed: "Failed", running: "Running", pending: "Pending", skipped: "" };

    const summary = document.createElement("summary");
    summary.innerHTML = `
      <span class="step-line-icon ${status}">${iconMap[status] || String(stepNum)}</span>
      <span class="step-line-num">STEP ${stepNum}/${total}</span>
      <span class="step-line-title"></span>
      <span class="step-line-status ${status}"></span>
    `;
    summary.querySelector(".step-line-title").textContent = title;
    summary.querySelector(".step-line-status").textContent = labelMap[status] || status;
    details.appendChild(summary);

    if (tool && tool !== "manual step") {
      const cmdRow = document.createElement("div");
      cmdRow.className = "step-line-command";
      const actionLabel = (tool.includes("(") || tool.startsWith("[")) ? "Action" : "Command";
      cmdRow.innerHTML = `${actionLabel}: <span class="term-command"></span>`;
      cmdRow.querySelector(".term-command").textContent = tool;
      details.appendChild(cmdRow);
    }

    if (output) {
      const out = document.createElement("div");
      out.className = "term-raw-output";
      out.textContent = output;
      details.appendChild(out);
    }
    if (note) {
      const n = document.createElement("div");
      n.className = "step-skip-note";
      n.textContent = note;
      details.appendChild(n);
    }

    return details;
  }

  // End-of-ticket summary: the summarization agent's own output and nothing
  // else. Step counts, SOP id, host and duration used to be restated here, but
  // those are frontend-derived and already live in the right rail and in each
  // step's own row -- repeating them buried the two things the agent wrote.
  //
  // NOTE: the "Findings" row (resp.variables, secret-filtered) went with them,
  // and extracted variables are now shown nowhere in the UI. Re-add a row here
  // if operators need them back.
  function renderMarkdown(text) {
    if (!text) return "";
    try {
      if (typeof marked !== "undefined") {
        if (typeof marked.parse === "function") {
          return marked.parse(text);
        } else if (typeof marked === "function") {
          return marked(text);
        }
      }
    } catch (e) {
      console.warn("Marked library rendering failed, using fallback:", e);
    }
    let html = escapeHtml(text);
    return html
      .replace(/^### (.*$)/gim, '<h3>$1</h3>')
      .replace(/^## (.*$)/gim, '<h2>$1</h2>')
      .replace(/^# (.*$)/gim, '<h1>$1</h1>')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\n/g, '<br>');
  }

  function buildResolutionBlock(resp, escalated) {
    const block = document.createElement("div");
    block.className = "resolution-block " + (escalated ? "escalated" : "resolved");

    const resType = resp.resolution_type
      ? resp.resolution_type
      : (escalated ? "ESCALATED_L2" : "COMPLETED");

    const head = document.createElement("div");
    head.className = "resolution-head";
    head.innerHTML = `
      <span class="resolution-title">Ticket resolution</span>
      <span class="resolution-badge ${escalated ? "escalated" : "resolved"}"></span>
    `;
    head.querySelector(".resolution-badge").textContent = resType.replace(/_/g, " ");
    block.appendChild(head);

    if (resp.customer_ticket_reply) {
      const r = document.createElement("div");
      r.className = "resolution-reply resolution-customer-email";
      r.innerHTML = `
        <div class="resolution-label" style="display: flex; align-items: center; justify-content: space-between;">
          <span>✉️ Customer Email Reply</span>
          <span style="font-size: 11px; font-weight: normal; background: rgba(59, 130, 246, 0.15); color: #60a5fa; padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(96, 165, 250, 0.3);">Sent via Email</span>
        </div>
        <div class="resolution-reply-text markdown-body"></div>
      `;
      r.querySelector(".resolution-reply-text").innerHTML = renderMarkdown(resp.customer_ticket_reply);
      block.appendChild(r);
    }
    if (resp.internal_ticket_summary) {
      const r = document.createElement("div");
      r.className = "resolution-reply resolution-internal-notes";
      r.innerHTML = `
        <div class="resolution-label" style="display: flex; align-items: center; justify-content: space-between;">
          <span>📋 Internal Engineering Notes</span>
          <span style="font-size: 11px; font-weight: normal; background: rgba(16, 185, 129, 0.15); color: #34d399; padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(52, 211, 153, 0.3);">Technical Report</span>
        </div>
        <div class="resolution-reply-text markdown-body"></div>
      `;
      r.querySelector(".resolution-reply-text").innerHTML = renderMarkdown(resp.internal_ticket_summary);
      block.appendChild(r);
    }

    return block;
  }

  // The single animated "... is processing" line, always kept last so it sits
  // at the bottom of the console. The node is REUSED across frames (only its
  // label changes) and moved to the end with appendChild -- recreating it made
  // the spinner restart and the timestamp jump on every frame, which was a
  // large part of the console's flicker.
  function appendProcessingIndicator(label) {
    if (!processingRow) {
      processingRow = document.createElement("div");
      processingRow.className = "console-row processing-row";
      processingRow.innerHTML = `
        <span class="console-row-time">${nowTime()}</span>
        <span class="mini-spinner"></span>
        <span class="console-row-text"></span>
      `;
    }
    const text = `${label} is processing...`;
    const textEl = processingRow.querySelector(".console-row-text");
    if (textEl.textContent !== text) textEl.textContent = text;

    // appendChild on an already-attached node MOVES it (no re-create), so the
    // spinner keeps spinning while it stays pinned below the newest step.
    if (processingRow.parentNode !== consoleBody || processingRow.nextSibling) {
      const pinned = isPinnedToBottom();
      consoleBody.appendChild(processingRow);
      if (pinned) consoleBody.scrollTop = consoleBody.scrollHeight;
    }
  }

  function removeProcessingIndicator() {
    if (processingRow && processingRow.parentNode) processingRow.remove();
  }

  /* ================================================================
     WORKFLOW CHECKLIST (rendered into the EXECUTION PROGRESS widget)
     ================================================================ */
  // Coarse 5-phase workflow: Intake, SOP Retrieval, Planning, Execution, Summary
  function wfLi(index, label, state) {
    const li = document.createElement("li");
    li.className = `wf-step ${state}`;
    li.innerHTML = `<span class="wf-step-icon">${index}</span><span class="wf-step-label">${escapeHtml(label)}</span>`;
    return li;
  }

  // Renders the coarse 5-phase workflow into any container -- used by both
  // the left panel's WORKFLOW section and the right panel's EXECUTION
  // PROGRESS widget, so they always stay in sync.
  function renderWorkflowInto(container, resp) {
    container.innerHTML = "";
    if (!resp) {
      container.appendChild(wfLi(1, "Intake", "pending"));
      container.appendChild(wfLi(2, "SOP Retrieval", "pending"));
      container.appendChild(wfLi(3, "Planning", "pending"));
      container.appendChild(wfLi(4, "Execution", "pending"));
      container.appendChild(wfLi(5, "Summary", "pending"));
      return;
    }

    const steps = (resp.execution_plan && resp.execution_plan.steps) || [];
    const escalated = resp.workflow_status === "escalated";
    const ran = completedStepCount(resp, steps);

    // Intake is only done once triage has produced an intent -- it used to be
    // painted green the instant any state arrived, while the console still
    // said "Intake is processing...".
    container.appendChild(wfLi(1, "Intake", resp.intent ? "done" : "current"));
    container.appendChild(wfLi(2, "SOP Retrieval", resp.sop ? "done" : (resp.awaiting_clarification ? "current" : (resp.intent ? "current" : "pending"))));
    container.appendChild(wfLi(3, "Planning", steps.length > 0 ? "done" : (resp.sop ? "current" : "pending")));

    // Execution succeeds when the workflow finished without escalating.
    const executionOver = (resp.done || resp.workflow_status === "completed" || resp.workflow_status === "done") && !!resp.resolution_type;
    let executionState = "pending";
    if (steps.length > 0) {
      if (executionOver) {
        executionState = escalated ? "failed" : "done";
      } else if (resp.awaiting_approval || ran > 0 || isApproved(resp) || (resp.current_step_index || 0) > 0) {
        executionState = "current";
      }
    }
    container.appendChild(wfLi(4, "Execution", executionState));

    // Summary is current while summarization agent works, and done once resolution text is populated
    const summaryState = resp.resolution_type || resp.customer_ticket_reply
      ? (escalated ? "failed" : "done")
      : (resp.done || resp.workflow_status === "completed" ? "current" : "pending");
    container.appendChild(wfLi(5, "Summary", summaryState));
  }

  function renderWorkflowChecklist(resp) {
    renderWorkflowInto(executionProgressList, resp);
  }

  /* ================================================================
     CENTER PANEL: TICKET-CONTEXTUAL HEADER
     ================================================================ */
  // Local clock, re-seeded from the server's elapsed_seconds on every frame.
  let durationTimer = null;

  function startDurationTicker(seedSeconds, running) {
    if (durationTimer) { clearInterval(durationTimer); durationTimer = null; }
    const base = Number(seedSeconds) || 0;
    const startedAt = Date.now();
    durationBadge.textContent = formatClock(base);
    if (!running) return;
    durationTimer = setInterval(() => {
      durationBadge.textContent = formatClock(base + (Date.now() - startedAt) / 1000);

      // Heartbeat on the "... is processing" row: after 20 quiet seconds it
      // starts counting, so a backend stall (LLM retries took 7 minutes in
      // testing) is visibly "still waiting" rather than a frozen line the
      // engineer can't tell apart from a hang.
      const p = consoleBody.querySelector(".processing-row");
      if (p) {
        if (!p.dataset.t0) p.dataset.t0 = String(Date.now());
        const quiet = Math.round((Date.now() - Number(p.dataset.t0)) / 1000);
        let e = p.querySelector(".proc-elapsed");
        if (!e) {
          e = document.createElement("span");
          e.className = "proc-elapsed";
          p.appendChild(e);
        }
        e.textContent = quiet >= 20 ? `waiting ${quiet}s` : "";
      }
    }, 1000);
  }

  function stopDurationTicker() {
    if (durationTimer) { clearInterval(durationTimer); durationTimer = null; }
  }

  function formatClock(totalSeconds) {
    const s = Math.max(0, Math.round(totalSeconds || 0));
    const hh = String(Math.floor(s / 3600)).padStart(2, "0");
    const mm = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
    const ss = String(s % 60).padStart(2, "0");
    return `${hh}:${mm}:${ss}`;
  }

  // Renders the ticket-contextual header (ID, issue, live/duration, end
  // session) as soon as a ticket is selected -- kept identical in structure
  // whether the ticket is actively executing or sitting idle, only the
  // resp-dependent details (duration, step count) vary.
  function renderConsoleHeader(ticket, resp) {
    if (!ticket) {
      consoleTicketId.textContent = "AGENT EXECUTION CONSOLE";
      consoleTicketSep.style.display = "none";
      consoleTicketIssue.textContent = "";
      liveBadge.style.display = "none";
      durationBadge.style.display = "none";
      endSessionBtn.style.display = "none";
      consoleSubHeader.style.display = "none";
      stopDurationTicker();
      return;
    }

    consoleTicketId.textContent = ticket.id;
    consoleTicketSep.style.display = "inline";
    consoleTicketIssue.textContent = ticket.issue || ticket.description || "";
    endSessionBtn.style.display = "inline-block";
    endSessionBtn.disabled = false;

    const isDone = resp ? resp.done : ticket.status === "completed";
    liveBadge.style.display = isDone ? "none" : "flex";
    durationBadge.style.display = "inline";
    // elapsed_seconds only refreshes when an SSE frame lands, so the clock used
    // to sit frozen for tens of seconds beside a pulsing "LIVE" dot. Seed from
    // the server value, then tick locally until the next frame corrects it.
    startDurationTicker(resp ? resp.elapsed_seconds : 0, !isDone);

    const steps = (resp && resp.execution_plan && resp.execution_plan.steps) || [];
    consoleSubHeader.style.display = "none";
  }

  endSessionBtn.addEventListener("click", () => {
    closeTicketStream();
    stopDurationTicker();
    activeTicketId = null;
    activeThreadId = null;
    activeResp = null;
    consoleJournal = [];
    lastContactAt = null;
    renderTickets();
    loadTicketConsole(null);
  });

  /* ================================================================
     RIGHT PANEL: REMOTE MACHINE
     ================================================================ */
  // First time a step actually ran, so "Last Contact" reports when the host was
  // reached rather than when the panel happened to repaint.
  let lastContactAt = null;

  // `ticket` carries the fields the ticket-card used to show inline (user,
  // email, category, agent, SOP, step) -- moved here so the card stays a
  // simple id/description/status row.
  function renderRemoteMachinePanel(resp, ticket) {
    let html = "";
    if (ticket) {
      html += `
        <div class="rm-row"><span class="rm-label">User</span><span class="rm-value">${escapeHtml(ticket.user || "—")}</span></div>
        <div class="rm-row"><span class="rm-label">Email</span><span class="rm-value">${escapeHtml(ticket.email || "—")}</span></div>
        <div class="rm-row"><span class="rm-label">Category</span><span class="rm-value">${escapeHtml(ticket.department || "—")}</span></div>
        <div class="rm-row"><span class="rm-label">Agent</span><span class="rm-value">${escapeHtml(ticket.assigned || "—")}</span></div>
        <div class="rm-row"><span class="rm-label">SOP</span><span class="rm-value">${escapeHtml(ticket.sop || "—")}</span></div>
        <div class="rm-row"><span class="rm-label">Step</span><span class="rm-value">${ticket.currentStep || 0} / ${ticket.totalSteps || 0}</span></div>
      `;
    }

    const entities = (resp && resp.entities) || {};
    const hostname = entities.hostname;
    if (!hostname) {
      html += `<div class="empty-widget-note">No remote session yet</div>`;
      remoteMachineInfo.innerHTML = html;
      return;
    }
    // "Connected" now requires a step to have actually executed against the
    // host. Deriving it from resp.done made every finished ticket -- including
    // ones rejected before a single command ran -- claim a live session.
    const steps = (resp.execution_plan && resp.execution_plan.steps) || [];
    const ran = completedStepCount(resp, steps);
    const connected = ran > 0;
    const lastContact = connected ? (lastContactAt || nowTime()) : "—";
    if (connected && !lastContactAt) lastContactAt = lastContact;
    html += `
      <div class="rm-divider"></div>
      <div class="rm-row"><span class="rm-label">Hostname</span><span class="rm-value">${escapeHtml(hostname)}</span></div>
      <div class="rm-row"><span class="rm-label">OS</span><span class="rm-value">${escapeHtml(entities.target_os || entities.os || "Windows")}</span></div>
      <div class="rm-row"><span class="rm-label">Connection</span><span class="rm-conn-badge ${connected ? "connected" : "unknown"}">${connected ? "Connected" : "Not connected"}</span></div>
      <div class="rm-row"><span class="rm-label">IP Address</span><span class="rm-value">${escapeHtml(entities.ip_address || "—")}</span></div>
      <div class="rm-row"><span class="rm-label">Last Contact</span><span class="rm-value">${escapeHtml(lastContact)}</span></div>
    `;
    remoteMachineInfo.innerHTML = html;
  }

  /* ================================================================
     LIVE AGENT WORKFLOW INTERACTION & POLLING
     ================================================================ */
  // The phase currently in flight, derived from ticket state. The server only
  // announces node_start once per kickoff, so relying on those events alone
  // pinned the console to "Intake" while the right rail had already advanced
  // through SOP Retrieval and Planning. State arrives on every frame, so it is
  // the reliable source; node_start is still used for the tail phases, which
  // state cannot distinguish.
  function derivePhaseLabel(resp) {
    const steps = (resp.execution_plan && resp.execution_plan.steps) || [];
    if (resp.workflow_status === "escalated") return "Escalating";
    if (steps.length > 0) return isApproved(resp) ? "Summarizing" : "Planning";
    if (resp.sop) return "Planning";
    if (resp.intent) return "SOP Retrieval";
    return "Intake";
  }

  // NOTE: per-agent reasoning (triage verdicts, SOP match, planner/verifier/
  // orchestrator commentary, extracted variables) is deliberately NOT rendered
  // here. The console shows the workflow, not the agents' internal log: the
  // phase indicator names whatever is running, the plan card is reviewed and
  // approved, the steps report themselves as they run, and the summarization
  // agent has the last word. Everything else is still on every frame in
  // `resp` -- the right rail and each step's own dropdown surface the detail.
  function renderLiveConsoleFlow(resp) {
    // NOTE: no wipe here. Items are emitted with stable keys and reconciled
    // (see `emit`), so the transcript grows downwards in true execution order
    // and already-painted rows are never rebuilt.
    const steps = (resp.execution_plan && resp.execution_plan.steps) || [];

    // The console deliberately shows only three things: the plan (to review
    // and approve), the step lines as they execute, and the final summary.
    // Agent audit-log chatter stays out of it -- each step's own dropdown
    // already carries the command and raw output.
    const approved = steps.length > 0 && isApproved(resp);
    const rejected = steps.length > 0 && isRejected(resp);

    const stepTool = (step) => formatStepAction(step);


    // The plan card is keyed on its locked state, so approving it swaps the
    // editable card for the locked one exactly once instead of every frame.
    const planSig = `${steps.length}|${approved || rejected || !resp.awaiting_approval ? "locked" : "open"}`;

    if (approved || rejected) {
      // Remove any leftover review wizard cards from the DOM
      document.querySelectorAll(".wizard-card, #activeWizardCard").forEach(card => card.remove());

      // Plan stays visible above the run, locked for reference.
      emit("plan", planSig, () => buildPlanApprovalCard(steps, true, resp.approval_question));

      // The operator's own decision lines ("> yes" / "> no") -- kept, because
      // they are the operator's input rather than agent chatter.
      emitJournal();

      if (approved) {
        // Steps appear one at a time: only those that have already run, plus the
        // one currently in flight.
        steps.forEach((step, pos) => {
          const status = getStepStatusAt(resp, pos);
          if (status === "pending") return;
          const note = status === "skipped"
            ? (step.execute_if
                ? `Skipped — run condition not met: ${step.execute_if}`
                : "Skipped by orchestrator")
            : null;
          const output = getStepOutputAt(resp, pos);
          emit(`step|${pos}`, `${status}|${output}|${note || ""}`, () => buildStepLine(
            step.step_number,
            step.sop_step_description,
            status,
            stepTool(step),
            output,
            steps.length,
            note
          ));
        });
      }
    } else if (resp.awaiting_approval && steps.length > 0) {
      // Any steps already run (cross-SOP referral / replan) stay listed.
      steps.forEach((step, pos) => {
        const status = getStepStatusAt(resp, pos);
        if (status !== "completed" && status !== "failed") return;
        const output = getStepOutputAt(resp, pos);
        emit(`step|${pos}`, `${status}|${output}`, () => buildStepLine(
          step.step_number, step.sop_step_description, status,
          stepTool(step), output, steps.length));
      });

      emit("plan", planSig, () => buildStepReviewWizardCard(steps, resp.approval_question));
    } else {

      emitJournal();
    }

    // The resolution block reports what the SUMMARIZATION agent wrote, so it
    // must not be painted until that agent has actually run. `resolution_type`
    // is written by summarization_agent and by nothing else in the graph, which
    // makes it the exact marker for "summarization is finished" -- safer than
    // resp.done alone, which only says the graph stopped.
    //
    // It is also checked ahead of resp.done so the block lands on the frame
    // summarization itself produced, rather than one frame later on the `done`
    // event. Both frames carry identical state, so `emit` builds it once.
    const summarized = !!(resp.resolution_type || resp.customer_ticket_reply || resp.internal_ticket_summary);
    if (summarized) {
      const escalated = resp.workflow_status === "escalated" || resp.resolution_type === "ESCALATED_L2";
      // The block carries the summarization agent's own words and nothing the
      // frontend derived, so the signature is just the outcome badge and the
      // two pieces of agent text.
      const resSig = `${escalated}|${resp.resolution_type || ""}|${resp.customer_ticket_reply || ""}|${resp.internal_ticket_summary || ""}`;
      emit("resolution", resSig, () => buildResolutionBlock(resp, escalated));
    }

    // Bottom-of-console "processing" line. While executing it names the step
    // in flight; before a plan exists it names the phase. Suppressed only
    // while genuinely waiting on the user -- the graph's between-step
    // interrupts also set awaiting_approval, and hiding the indicator on
    // those frames made the console go quiet mid-run.
    // `summarized` ends the run for display purposes: the summarization frame
    // reports workflow_status "done"/"escalated" (no longer "completed"), which
    // would otherwise fall through to the step branch below and flash
    // "Step N is processing..." underneath the finished resolution block.
    const waitingOnUser = (resp.awaiting_approval && !isApproved(resp)) || resp.awaiting_clarification;
    if (summarized || resp.done || waitingOnUser) {
      removeProcessingIndicator();
    } else {
      if (resp.workflow_status === "completed") {
        // Execution is over; the summarization agent is writing the final
        // reply. This phase ran 7 minutes in testing (LLM provider retries)
        // while the console wrongly claimed a skipped step was "processing".
        appendProcessingIndicator("Summarizing");
      } else if (resp.workflow_status === "escalated") {
        // Escalation path: escalation_agent -> summarization_agent. Without
        // this the step branch below claimed "Step N is processing..." while
        // the run was really being wrapped up, right up to the moment the
        // resolution block appeared.
        appendProcessingIndicator("Escalating");
      } else if (approved && steps.length) {
        appendProcessingIndicator(`Step ${Math.min((resp.current_step_index || 0) + 1, steps.length)}`);
      } else if (steps.length && resp.plan_valid == null) {
        // retrieval_agent has just loaded the SOP's raw steps into
        // execution_plan; planner_agent is synthesizing the executable plan
        // from them. These two labels used to be the other way round, so the
        // console announced "Validating plan" while the planner was still
        // writing it and "Planning" once the plan was already validated.
        appendProcessingIndicator("Planning");
      } else if (steps.length) {
        // planner_agent has returned a plan with a plan_valid verdict;
        // orchestration_agent is checking it ahead of the approval gate.
        appendProcessingIndicator("Validating plan");
      } else {
        appendProcessingIndicator(derivePhaseLabel(resp));
      }
    }

    const currentTicket = tickets.find(t => t.id === activeTicketId);
    renderLiveRightRail(resp, currentTicket);
    renderConsoleHeader(currentTicket, resp);
  }

  // Single path for the operator's decision, shared by the Approve/Reject
  // buttons and the typed yes/no line. Decision lines go through journal() so
  // they survive the console repaint that the next SSE frame triggers.
  async function submitApproval(approve, rejectionReason = "") {
    const activeCard = document.getElementById("activeYamlCard");

    // Read edited text out of the DOM before the card is locked below --
    // locking strips the id the edits are queried against.
    let editedSteps = null;
    if (approve && activeCard) {
      editedSteps = Array.from(activeCard.querySelectorAll(".step-plan-row")).map(row => {
        const step = { step_number: Number(row.dataset.stepNumber) };
        const desc = row.querySelector(".step-plan-desc");
        if (desc) step.sop_step_description = desc.textContent.trim();
        if (row.dataset.hasCommand === "1") {
          const cmd = row.querySelector(".step-plan-cmd");
          if (cmd) step.command = cmd.textContent.trim();
        }
        return step;
      });
    }

    if (activeCard) {
      activeCard.classList.add("locked");
      const badge = activeCard.querySelector(".console-step-status-tag");
      if (badge) {
        badge.textContent = "Locked";
        badge.className = "console-step-status-tag locked";
      }
      const prompt = activeCard.querySelector(".confirmation-prompt-section");
      if (prompt) prompt.remove();
      activeCard.removeAttribute("id");
    }

    journal("SYSTEM", `> ${approve ? "yes" : "no"}`);
    if (!approve && rejectionReason) {
      journal("SYSTEM", `> Reason: ${rejectionReason}`);
    }
    journal("SYSTEM", approve
      ? "Plan approved by operator. Starting execution..."
      : "Plan declined by operator. Routing to escalation...");

    if (!activeThreadId) {
      addConsoleLine("error", "No active agent session for this ticket.");
      return;
    }

    if (approve) {
      if (activeThreadId) approvedThreads.add(activeThreadId);
      if (activeResp) renderLiveConsoleFlow(activeResp);
      const t = tickets.find(x => x.id === activeTicketId);
      if (t) { t.status = "in_progress"; renderTickets(); }
      await kickAndStream(() => api(`/api/tickets/${activeThreadId}/approve`, {
        method: "POST",
        body: JSON.stringify({ edited_steps: editedSteps }),
      }));
    } else {
      if (activeThreadId) rejectedThreads.add(activeThreadId);
      if (activeResp) renderLiveConsoleFlow(activeResp);
      const finalReason = rejectionReason || "Plan rejected by operator.";
      await kickAndStream(() => api(`/api/tickets/${activeThreadId}/reject`, {
        method: "POST",
        body: JSON.stringify({ reason: finalReason })
      }));
    }
  }

  // Approve/Reject/Enter handlers are bound inside buildPlanApprovalCard; this
  // only moves the caret into the yes/no field. Guarded so a repaint can't
  // steal focus back while the operator is editing a step above it.
  function focusApprovalInput() {
    const inputField = document.getElementById("inlineConfirmInput");
    if (!inputField) return;
    const active = document.activeElement;
    if (active && active !== document.body && active !== inputField) return;
    inputField.focus();
  }

  /* ================================================================
     LIVE STREAMING (SSE) -- keeps the console/right-rail responsive while
     each agent node runs, instead of waiting for the whole remaining plan
     to finish in one blocking request.
     ================================================================ */
  // Coarse node -> (console tag, workflow-checklist phase) mapping, used to
  // show a "working" indicator the instant an agent starts, ahead of the
  // full state update that lands once it completes.
  const NODE_META = {
    intake_agent: { label: "Intake", phase: 1 },
    retrieval_agent: { label: "SOP Retrieval", phase: 2 },
    planner_agent: { label: "Planning", phase: 3 },
    orchestration_agent: { label: "Orchestrator", phase: 3 },
    execution_agent: { label: "Execution", phase: 4 },
    execution_result_agent: { label: "Execution", phase: 4 },
    summarization_agent: { label: "Summarizing", phase: 5 },
    escalation_agent: { label: "Escalating", phase: 5 },
  };

  function markPhaseCurrent(phaseIndex) {
    const li = executionProgressList.children[phaseIndex - 1];
    if (!li || li.classList.contains("done") || li.classList.contains("failed")) return;
    li.className = "wf-step current";
  }

  // Records which phase is in flight and repaints, so the bottom indicator
  // updates the moment an agent starts rather than only once it finishes.
  // Execution steps label themselves from ticket state, so they're skipped
  // here.
  const STEP_NODES = new Set(["execution_agent", "execution_result_agent"]);

  function handleAgentWorking(nodeName) {
    const meta = NODE_META[nodeName] || { label: nodeName || "Agent", phase: null };
    if (!STEP_NODES.has(nodeName)) {
      // Repaint from state (which derives its own phase label) rather than
      // pinning the console to whatever node was last announced.
      if (activeResp) renderLiveConsoleFlow(activeResp);
      else appendProcessingIndicator(meta.label);
    }
    if (meta.phase) markPhaseCurrent(meta.phase);
  }

  function applyStreamState(state) {
    // Frames must belong to the ticket currently on screen. An in-flight SSE
    // event from a previous (finished) ticket could land after a new ticket
    // was created, briefly painting the old run's Done/Skipped statuses onto
    // the new session before its own frames arrived.
    if (!state || !activeThreadId || state.thread_id !== activeThreadId) return;
    activeResp = state;
    const t = tickets.find(x => x.id === activeTicketId);
    if (t) {
      updateTicketFromResponse(t, state);
      renderTickets();
    }
    renderLiveConsoleFlow(state);
  }

  let activeEventSource = null;

  // SSE frames can arrive faster than the browser paints -- a fast step
  // (local command + quick LLM verification) can produce several "node"
  // events within the same JS tick. Handling them synchronously meant only
  // the LAST one ever got painted, so a 7-step run looked like every step
  // finished at once instead of appearing in the order it actually ran.
  // Every event is queued and drained one at a time with a short pause
  // after each, guaranteeing a real paint before the next step replaces it.
  const STEP_REVEAL_DELAY_MS = 300;
  let sseQueue = [];
  let sseDraining = false;

  function enqueueStreamEvent(handler) {
    sseQueue.push(handler);
    drainStreamQueue();
  }

  async function drainStreamQueue() {
    if (sseDraining) return;
    sseDraining = true;
    while (sseQueue.length) {
      const handler = sseQueue.shift();
      handler();
      await new Promise(r => setTimeout(r, STEP_REVEAL_DELAY_MS));
    }
    sseDraining = false;
  }

  // Set once a stream has ended on purpose (server sent done/paused), so the
  // browser's follow-up "connection closed" error can be told apart from a
  // genuine mid-run disconnect.
  let streamFinished = false;

  function closeTicketStream() {
    if (activeEventSource) {
      activeEventSource.close();
      activeEventSource = null;
    }
    isExecuting = false;
  }

  function openTicketStream(threadId) {
    closeTicketStream();
    isExecuting = true;
    sseQueue = [];
    sseDraining = false;
    streamFinished = false;

    const es = new EventSource(`/api/tickets/${threadId}/stream`);
    activeEventSource = es;

    es.addEventListener("node_start", (e) => {
      let node;
      try { node = JSON.parse(e.data).node; } catch (err) { return; }
      enqueueStreamEvent(() => handleAgentWorking(node));
    });

    es.addEventListener("node", (e) => {
      let state;
      try { state = JSON.parse(e.data).state; } catch (err) { return; }
      enqueueStreamEvent(() => applyStreamState(state));
    });

    // `paused` and `done` are the LAST events of a stream: the server drops a
    // __end__ sentinel straight after, which ends the HTTP response. The
    // browser reports a server-closed EventSource as an `error` and then tries
    // to reconnect, so the socket has to be closed here SYNCHRONOUSLY -- doing
    // it from inside the paced queue (up to STEP_REVEAL_DELAY_MS later) left a
    // window in which the browser raised that spurious "Connection to agent
    // stream lost." error on every normal, successful run.
    function endStream(e, applyFn) {
      let state = null;
      try { state = JSON.parse(e.data).state; } catch (err) { /* ignore */ }
      streamFinished = true;
      es.close();
      enqueueStreamEvent(() => {
        if (state) applyFn(state);
        closeTicketStream();
      });
    }

    es.addEventListener("paused", (e) => endStream(e, applyStreamState));
    es.addEventListener("done", (e) => endStream(e, applyStreamState));

    es.addEventListener("error", (e) => {
      // A real backend failure arrives as `event: error` WITH a JSON payload
      // (see _stream_worker's except branch). A native EventSource error has
      // no payload -- and after the stream has legitimately finished it just
      // means "the server closed the response", which is not a failure.
      if (!e.data) {
        if (streamFinished) return;
        // Genuine drop mid-run: stop the browser's automatic reconnect, which
        // would otherwise silently re-open a stream we are done with.
        es.close();
      }

      let message = "Connection to agent stream lost.";
      if (e.data) {
        try { message = JSON.parse(e.data).message || message; } catch (err) { /* ignore */ }
      }
      enqueueStreamEvent(() => {
        addConsoleLine("error", message);
        toast("Error: " + message);
        closeTicketStream();
      });
    });
  }

  // Fires the given action (approve/reject/clarify POST), then opens the SSE
  // stream so the console/right-rail update live as each agent node runs.
  async function kickAndStream(fn) {
    if (isExecuting) return;
    try {
      await fn();
      if (activeThreadId) openTicketStream(activeThreadId);
    } catch (err) {
      addConsoleLine("error", err.message);
      toast("Error: " + err.message);
    }
  }

  /* ================================================================
     RIGHT PANEL WIDGET RENDERING
     ================================================================ */
  function renderLiveRightRail(resp, ticket) {
    renderRemoteMachinePanel(resp, ticket);
    renderWorkflowInto(executionProgressList, resp);
  }


  /* ================================================================
     NEW TICKET MODAL OVERLAY
     ================================================================ */
  function openModal() {
    modalOverlay.classList.add("open");
    ticketDescription.focus();
  }
  function closeModal() {
    modalOverlay.classList.remove("open");
  }

  newTicketBtn.addEventListener("click", openModal);
  if (emptyNewTicketBtn) emptyNewTicketBtn.addEventListener("click", openModal);
  modalCloseBtn.addEventListener("click", closeModal);
  modalCancelBtn.addEventListener("click", closeModal);
  modalOverlay.addEventListener("click", (e) => {
    if (e.target === modalOverlay) closeModal();
  });

  // Mirrors main.py's SAMPLE_TICKET, so the CLI and UI exercise the same demo ticket.
  const SAMPLE_TICKET = {
    customer_email: "pradeepnaveen930@gmail.com",
    user_id: "",
    category: "network",
    ticket_raw: "Hi IT support team, my email is pradeepnaveen930@gmail.com. i am facing internet connection issue in my windows lap.",
  };

  loadSampleBtn.addEventListener("click", () => {
    ticketEmail.value = SAMPLE_TICKET.customer_email;
    ticketUserId.value = SAMPLE_TICKET.user_id;
    ticketCategory.value = SAMPLE_TICKET.category;
    ticketDescription.value = SAMPLE_TICKET.ticket_raw;
  });

  createTicketBtn.addEventListener("click", async () => {
    const ticket_raw = ticketDescription.value.trim();
    if (!ticket_raw) {
      toast("Please describe the issue before creating the ticket.");
      return;
    }
    const customer_email = ticketEmail.value.trim() || "unknown@acme.com";
    const user_id = ticketUserId.value.trim() || "12";
    const category = ticketCategory.value;
    const entities = {};
    if (user_id) entities.user_id = user_id;
    if (customer_email) entities.email = customer_email;

    closeModal();

    // 1. Generate new ticket card ID
    const newId = `INC-${250716 + tickets.length}-${String(tickets.length + 1).padStart(4, "0")}`;
    const newTicket = {
      id: newId,
      issue: ticket_raw.length > 25 ? ticket_raw.substring(0, 22) + "..." : ticket_raw,
      user: "Generated User",
      email: customer_email,
      priority: "High",
      department: "Support",
      assigned: "EloneAgent",
      sop: "SOP-001",
      currentStep: 0,
      totalSteps: 0,
      status: "in_progress",
      description: ticket_raw,
      threadId: null,      // set once the agent thread is created
    };

    // Add to ticket stack
    tickets.unshift(newTicket);
    activeTicketId = newId;
    renderTickets();

    // 2. Initiate Agent flow
    resetConsole();
    expandedSteps.clear();
    consoleJournal = [];
    lastContactAt = null;

    // Reset the right rail and header too. Only the console used to be
    // wiped, so the PREVIOUS ticket's step list (with its Done/Skipped
    // statuses) stayed on screen through the new ticket's whole intake/
    // planning phase -- the engineer saw "Skipped" steps before the new run
    // had executed anything.
    renderWorkflowChecklist(null);
    renderRemoteMachinePanel(null, newTicket);
    renderConsoleHeader(newTicket, null);

    addConsoleLine("SYSTEM", "Triage initialized. Processing ticket...");
    activeThreadId = null;
    activeResp = null;

    try {
      const resp = await api("/api/tickets", {
        method: "POST",
        body: JSON.stringify({ ticket_raw, customer_email: customer_email || null, category, entities }),
      });
      activeThreadId = resp.thread_id;
      newTicket.threadId = resp.thread_id;
      sessionLabel.textContent = activeThreadId;
      copySessionBtn.dataset.session = activeThreadId;
      openTicketStream(activeThreadId);
    } catch (err) {
      addConsoleLine("error", `Workflow execution failed: ${err.message}`);
      toast("Failed to initiate thread: " + err.message);
    }

    // Reset Form
    ticketEmail.value = "";
    ticketUserId.value = "";
    ticketCategory.value = "logins";
    ticketDescription.value = "";
  });

  copySessionBtn.addEventListener("click", () => {
    const id = copySessionBtn.dataset.session;
    if (!id) { toast("No active session yet."); return; }
    if (navigator.clipboard) navigator.clipboard.writeText(id).catch(() => { });
    toast(`Copied session ID: ${id}`);
  });

  async function fetchTicketsFromApi() {
    try {
      const data = await api("/api/tickets");
      if (data && Array.isArray(data.tickets) && data.tickets.length > 0) {
        tickets = data.tickets.map((t, idx) => ({
          id: t.ticket_id || t.thread_id,
          issue: t.issue || "Support Request",
          user: t.customer_name || t.customer_email || "Employee",
          email: t.customer_email || "",
          priority: (t.priority || "medium").toUpperCase(),
          department: t.category || "software",
          assigned: "EloneAgent",
          sop: "SOP-001",
          currentStep: t.current_step_index || 0,
          totalSteps: t.total_steps || 0,
          status: t.workflow_status === "escalated" ? "escalated" : (t.workflow_status === "completed" || t.workflow_status === "done" ? "completed" : t.workflow_status),
          description: t.ticket_raw || t.issue,
          threadId: t.thread_id,
        }));
        renderTickets();
        if (tickets.length > 0 && !activeTicketId) {
          activeTicketId = tickets[0].id;
          loadTicketConsole(tickets[0]);
        }
      }
    } catch (e) {
      console.warn("Could not fetch historical tickets:", e);
    }
  }

  // Initial Load
  renderTickets();
  loadTicketConsole(tickets[0]);
  fetchTicketsFromApi();
})();
