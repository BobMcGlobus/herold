/**
 * Herold Card — Inbox, geplante Nachrichten und Verlauf.
 *
 * Auto-loaded by the Herold integration (no manual resource needed).
 * Entities are auto-discovered; override via card config:
 *
 *   type: custom:herold-card
 *   title: Herold
 *   todo_entity: todo.herold_eingang
 *   pending_entity: sensor.herold_offene_fragen
 *   scheduled_entity: sensor.herold_geplante_benachrichtigungen
 *   history_entity: sensor.herold_verlauf
 */

(() => {
  const PRIO = {
    0: { label: "P0", color: "#78909c" },
    1: { label: "P1", color: "#42a5f5" },
    2: { label: "P2", color: "#66bb6a" },
    3: { label: "P3", color: "#ffa726" },
    4: { label: "P4", color: "#ef5350" },
  };

  const KIND = {
    delivered: { icon: "📣", label: "Zugestellt" },
    dropped: { icon: "🚫", label: "Verworfen" },
    rate_limited: { icon: "⏳", label: "Rate-Limit" },
    query: { icon: "❓", label: "Frage gestellt" },
    answered: { icon: "✅", label: "Beantwortet" },
    expired: { icon: "⌛", label: "Abgelaufen" },
    cancelled: { icon: "✖️", label: "Abgebrochen" },
    escalated: { icon: "⚠️", label: "Eskaliert" },
    scheduled: { icon: "🕐", label: "Geplant" },
  };

  const esc = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (ch) =>
        ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]
    );

  const fmtTime = (iso) => {
    if (!iso) return "";
    const date = new Date(iso);
    const now = new Date();
    const sameDay = date.toDateString() === now.toDateString();
    const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    if (sameDay) return time;
    return `${date.toLocaleDateString([], { day: "2-digit", month: "2-digit" })} ${time}`;
  };

  const fmtRelative = (iso) => {
    const diff = (new Date(iso).getTime() - Date.now()) / 1000;
    const abs = Math.abs(diff);
    let text;
    if (abs < 90) text = `${Math.round(abs)} s`;
    else if (abs < 5400) text = `${Math.round(abs / 60)} min`;
    else if (abs < 129600) text = `${Math.round(abs / 3600)} h`;
    else text = `${Math.round(abs / 86400)} d`;
    return diff >= 0 ? `in ${text}` : `vor ${text}`;
  };

  const prioBadge = (priority) => {
    const prio = PRIO[priority] ?? PRIO[2];
    return `<span class="prio" style="background:${prio.color}">${prio.label}</span>`;
  };

  class HeroldCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._tab = "inbox";
      this._todoItems = [];
      this._todoFingerprint = null;
      this._fingerprint = null;
      this.shadowRoot.addEventListener("click", (event) => this._onClick(event));
    }

    static getStubConfig() {
      return { title: "Herold" };
    }

    setConfig(config) {
      this._config = config || {};
    }

    getCardSize() {
      return 6;
    }

    set hass(hass) {
      this._hass = hass;
      const ids = this._entities();
      this._maybeFetchTodos(ids.todo);
      const fingerprint = [
        this._tab,
        ids.pending && hass.states[ids.pending]?.last_updated,
        ids.scheduled && hass.states[ids.scheduled]?.last_updated,
        ids.history && hass.states[ids.history]?.last_updated,
        this._todoFingerprint,
        this._todoItems.length,
      ].join("|");
      if (fingerprint !== this._fingerprint) {
        this._fingerprint = fingerprint;
        this._render();
      }
    }

    _entities() {
      if (this._ids && !this._idsIncomplete) return this._ids;
      const states = this._hass.states;
      const find = (prefix, attribute) =>
        Object.keys(states).find(
          (id) =>
            id.startsWith(prefix) &&
            id.includes("herold") &&
            (!attribute || Array.isArray(states[id].attributes[attribute]))
        );
      const cfg = this._config;
      this._ids = {
        todo: cfg.todo_entity || find("todo."),
        pending: cfg.pending_entity || find("sensor.", "queries"),
        scheduled: cfg.scheduled_entity || find("sensor.", "schedules"),
        history: cfg.history_entity || find("sensor.", "entries"),
      };
      this._idsIncomplete = Object.values(this._ids).some((id) => !id);
      return this._ids;
    }

    async _maybeFetchTodos(todoEntity) {
      if (!todoEntity) return;
      const stateObj = this._hass.states[todoEntity];
      const fingerprint = stateObj ? stateObj.last_updated : null;
      if (fingerprint === this._todoFingerprint) return;
      this._todoFingerprint = fingerprint;
      try {
        const result = await this._hass.callWS({
          type: "todo/item/list",
          entity_id: todoEntity,
        });
        this._todoItems = result.items || [];
      } catch (err) {
        this._todoItems = [];
      }
      this._fingerprint = null;
      if (this._hass) this.hass = this._hass;
    }

    _onClick(event) {
      const el = event.target.closest("[data-action]");
      if (el) {
        const { action, id, answer, entity } = el.dataset;
        if (action === "tab") {
          this._tab = id;
          this._fingerprint = null;
          this._render();
        } else if (action === "todo-done") {
          this._hass.callService("todo", "update_item", {
            entity_id: entity,
            item: id,
            status: "completed",
          });
        } else if (action === "todo-remove") {
          this._hass.callService("todo", "remove_item", {
            entity_id: entity,
            item: id,
          });
        } else if (action === "answer") {
          this._hass.callService("herold", "acknowledge", {
            id,
            answer,
            source: "card",
          });
        } else if (action === "cancel") {
          this._hass.callService("herold", "cancel", { id });
        }
      }
    }

    _render() {
      const ids = this._entities();
      const title = esc(this._config.title || "Herold");
      const tabs = [
        ["inbox", `📥 Inbox${this._badge(this._inboxCount(ids))}`],
        ["scheduled", `🕐 Geplant${this._badge(this._scheduledItems(ids).length)}`],
        ["history", "📜 Logbuch"],
      ]
        .map(
          ([id, label]) =>
            `<button class="tab ${this._tab === id ? "active" : ""}"
              data-action="tab" data-id="${id}">${label}</button>`
        )
        .join("");

      let body;
      if (this._tab === "inbox") body = this._renderInbox(ids);
      else if (this._tab === "scheduled") body = this._renderScheduled(ids);
      else body = this._renderHistory(ids);

      this.shadowRoot.innerHTML = `
        <style>
          ha-card { padding: 12px 16px 16px; }
          .header { display: flex; align-items: center; gap: 8px;
            font-size: 1.2em; font-weight: 500; margin-bottom: 8px; }
          .tabs { display: flex; gap: 6px; margin-bottom: 10px; }
          .tab { flex: 1; border: none; border-radius: 12px; padding: 8px 4px;
            cursor: pointer; font: inherit; font-size: 0.85em;
            background: var(--secondary-background-color);
            color: var(--secondary-text-color); }
          .tab.active { background: var(--primary-color);
            color: var(--text-primary-color, #fff); font-weight: 600; }
          .row { display: flex; align-items: center; gap: 10px;
            padding: 8px 4px; border-bottom: 1px solid var(--divider-color); }
          .row:last-child { border-bottom: none; }
          .row .main { flex: 1; min-width: 0; }
          .row .text { color: var(--primary-text-color);
            overflow-wrap: anywhere; }
          .row .text.done { text-decoration: line-through;
            color: var(--disabled-text-color); }
          .row .sub { font-size: 0.8em; color: var(--secondary-text-color); }
          .prio { color: #fff; font-size: 0.7em; font-weight: 700;
            border-radius: 8px; padding: 2px 7px; flex-shrink: 0; }
          .icon { flex-shrink: 0; width: 1.4em; text-align: center; }
          .btn { border: none; border-radius: 10px; padding: 6px 10px;
            cursor: pointer; font: inherit; font-size: 0.8em;
            background: var(--secondary-background-color);
            color: var(--primary-text-color); flex-shrink: 0; }
          .btn.primary { background: var(--primary-color);
            color: var(--text-primary-color, #fff); }
          .btn.danger { color: var(--error-color, #ef5350); }
          .empty { padding: 18px 4px; text-align: center;
            color: var(--secondary-text-color); }
          .section { font-size: 0.75em; font-weight: 600;
            letter-spacing: 0.05em; text-transform: uppercase;
            color: var(--secondary-text-color); margin: 10px 4px 2px; }
          .answers { display: flex; gap: 6px; flex-wrap: wrap;
            margin-top: 6px; }
          .warn { font-size: 0.8em; color: var(--warning-color, #ffa726);
            padding: 6px 4px; }
        </style>
        <ha-card>
          <div class="header"><span>📯</span><span>${title}</span></div>
          <div class="tabs">${tabs}</div>
          ${body}
        </ha-card>`;
    }

    _badge(count) {
      return count ? ` (${count})` : "";
    }

    _inboxCount(ids) {
      const open = this._todoItems.filter(
        (item) => item.status === "needs_action"
      ).length;
      return open + this._pendingQueries(ids).length;
    }

    _pendingQueries(ids) {
      if (!ids.pending) return [];
      const stateObj = this._hass.states[ids.pending];
      return (stateObj && stateObj.attributes.queries) || [];
    }

    _scheduledItems(ids) {
      if (!ids.scheduled) return [];
      const stateObj = this._hass.states[ids.scheduled];
      return (stateObj && stateObj.attributes.schedules) || [];
    }

    _renderInbox(ids) {
      const queries = this._pendingQueries(ids);
      const open = this._todoItems.filter((i) => i.status === "needs_action");
      const done = this._todoItems.filter((i) => i.status !== "needs_action");
      const parts = [];

      if (queries.length) {
        parts.push('<div class="section">Offene Fragen</div>');
        for (const query of queries) {
          const answers =
            query.mode === "yesno"
              ? ["Ja", "Nein"]
              : query.mode === "choice" && Array.isArray(query.choices)
                ? query.choices
                : [];
          const buttons = answers
            .map(
              (answer) =>
                `<button class="btn primary" data-action="answer"
                  data-id="${esc(query.id)}" data-answer="${esc(answer)}">
                  ${esc(answer)}</button>`
            )
            .join("");
          parts.push(`
            <div class="row">
              <span class="icon">❓</span>
              <div class="main">
                <div class="text">${esc(query.question)}</div>
                <div class="sub">${fmtTime(query.created_at)} · ${esc(query.mode)}</div>
                ${buttons ? `<div class="answers">${buttons}</div>` : ""}
              </div>
              ${prioBadge(query.priority)}
              <button class="btn danger" data-action="cancel"
                data-id="${esc(query.id)}">✕</button>
            </div>`);
        }
      }

      if (open.length || !queries.length) {
        parts.push('<div class="section">Todos</div>');
      }
      if (!open.length && !queries.length) {
        parts.push('<div class="empty">Nichts offen — alles erledigt 🎉</div>');
      }
      for (const item of open) {
        parts.push(`
          <div class="row">
            <span class="icon">📌</span>
            <div class="main">
              <div class="text">${esc(item.summary)}</div>
              ${item.description ? `<div class="sub">${esc(item.description)}</div>` : ""}
            </div>
            <button class="btn primary" data-action="todo-done"
              data-id="${esc(item.uid)}" data-entity="${esc(ids.todo)}">✓</button>
          </div>`);
      }
      for (const item of done.slice(0, 5)) {
        parts.push(`
          <div class="row">
            <span class="icon">✅</span>
            <div class="main"><div class="text done">${esc(item.summary)}</div></div>
            <button class="btn danger" data-action="todo-remove"
              data-id="${esc(item.uid)}" data-entity="${esc(ids.todo)}">🗑</button>
          </div>`);
      }
      if (!ids.todo) {
        parts.push('<div class="warn">Keine Herold-Todo-Liste gefunden.</div>');
      }
      return parts.join("");
    }

    _renderScheduled(ids) {
      const schedules = this._scheduledItems(ids);
      if (!schedules.length) {
        return '<div class="empty">Keine geplanten Nachrichten.</div>';
      }
      return schedules
        .map(
          (schedule) => `
          <div class="row">
            <span class="icon">🕐</span>
            <div class="main">
              <div class="text">${esc(schedule.message)}</div>
              <div class="sub">${fmtTime(schedule.scheduled_for)} ·
                ${fmtRelative(schedule.scheduled_for)}</div>
            </div>
            ${prioBadge(schedule.priority)}
            <button class="btn danger" data-action="cancel"
              data-id="${esc(schedule.id)}">✕</button>
          </div>`
        )
        .join("");
    }

    _renderHistory(ids) {
      if (!ids.history) {
        return '<div class="warn">Kein Verlauf-Sensor gefunden (ab v0.6.0).</div>';
      }
      const stateObj = this._hass.states[ids.history];
      const entries = (stateObj && stateObj.attributes.entries) || [];
      if (!entries.length) {
        return '<div class="empty">Noch keine Ereignisse.</div>';
      }
      return entries
        .map((entry) => {
          const kind = KIND[entry.kind] || { icon: "•", label: entry.kind };
          const details = [];
          if (entry.channels) details.push(entry.channels.join(", "));
          if (entry.room) details.push(entry.room);
          if (entry.answer) details.push(`Antwort: ${entry.answer}`);
          if (entry.source) details.push(`via ${entry.source}`);
          if (entry.reason) details.push(entry.reason);
          if (entry.at) details.push(`für ${fmtTime(entry.at)}`);
          if (entry.to_priority !== undefined) {
            details.push(`P${entry.from_priority} → P${entry.to_priority}`);
          }
          return `
            <div class="row">
              <span class="icon" title="${esc(kind.label)}">${kind.icon}</span>
              <div class="main">
                <div class="text">${esc(entry.summary)}</div>
                <div class="sub">${fmtTime(entry.when)} · ${esc(kind.label)}
                  ${details.length ? "· " + esc(details.join(" · ")) : ""}</div>
              </div>
              ${entry.priority !== undefined ? prioBadge(entry.priority) : ""}
            </div>`;
        })
        .join("");
    }
  }

  if (!customElements.get("herold-card")) {
    customElements.define("herold-card", HeroldCard);
  }
  window.customCards = window.customCards || [];
  if (!window.customCards.some((card) => card.type === "herold-card")) {
    window.customCards.push({
      type: "herold-card",
      name: "Herold Card",
      description:
        "Inbox, offene Fragen, geplante Nachrichten und Verlauf des Herold-Notification-Hubs.",
    });
  }
})();
