/**
 * Herold Alarm Card — an alarm clock you can actually operate.
 *
 * Auto-loaded by the Herold integration alongside herold-card.js.
 *
 *   type: custom:herold-alarm-card
 *   title: Wecker
 *   entity: sensor.herold_naechster_wecker   # optional, auto-detected
 *
 * The list is deliberately Apple-shaped: big time, label underneath, a
 * toggle on the right, tap to edit. The time field is a native
 * <input type="time">, which on iOS renders the system wheel — a hand-built
 * drum would be a lot of code for a worse result.
 */

(() => {
  const DAYS = [
    ["mon", "Mo"],
    ["tue", "Di"],
    ["wed", "Mi"],
    ["thu", "Do"],
    ["fri", "Fr"],
    ["sat", "Sa"],
    ["sun", "So"],
  ];

  const URGENCY = [
    ["gentle", "Sanft"],
    ["normal", "Normal"],
    ["insistent", "Hartnäckig"],
  ];

  const SOUNDS = [
    ["chime", "Glocke"],
    ["beep", "Piepen"],
    ["siren", "Sirene"],
    ["sunrise", "Sonnenaufgang"],
  ];

  const esc = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (ch) =>
        ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
          ch
        ]
    );

  const fmtRelative = (iso) => {
    if (!iso) return "";
    const diff = (new Date(iso).getTime() - Date.now()) / 1000;
    if (diff < 0) return "";
    if (diff < 3600) return `in ${Math.round(diff / 60)} min`;
    if (diff < 86400) {
      const hours = Math.floor(diff / 3600);
      const mins = Math.round((diff % 3600) / 60);
      return `in ${hours} h ${mins} min`;
    }
    return `in ${Math.round(diff / 86400)} Tagen`;
  };

  class HeroldAlarmCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._editing = null; // alarm id, or "new"
      this._draft = null;
      this._fingerprint = null;
      this.shadowRoot.addEventListener("click", (event) => this._onClick(event));
      this.shadowRoot.addEventListener("change", (event) => this._onChange(event));
    }

    static getStubConfig() {
      return { title: "Wecker" };
    }

    setConfig(config) {
      this._config = config || {};
    }

    getCardSize() {
      return 5;
    }

    set hass(hass) {
      this._hass = hass;
      const entity = this._entity();
      const stamp = entity ? hass.states[entity]?.last_updated : null;
      const fingerprint = [stamp, this._editing].join("|");
      if (fingerprint !== this._fingerprint) {
        this._fingerprint = fingerprint;
        this._render();
      }
    }

    _entity() {
      if (this._config.entity) return this._config.entity;
      if (this._cachedEntity && this._hass.states[this._cachedEntity]) {
        return this._cachedEntity;
      }
      this._cachedEntity = Object.keys(this._hass.states).find(
        (id) =>
          id.startsWith("sensor.") &&
          id.includes("herold") &&
          Array.isArray(this._hass.states[id].attributes.alarms)
      );
      return this._cachedEntity;
    }

    _meta() {
      const entity = this._entity();
      if (!entity) return {};
      return this._hass.states[entity]?.attributes || {};
    }

    _alarms() {
      return this._meta().alarms || [];
    }

    // -- Interaction -------------------------------------------------------

    _onClick(event) {
      const el = event.target.closest("[data-action]");
      if (!el) return;
      const { action, id, value } = el.dataset;

      if (action === "new") {
        this._editing = "new";
        this._draft = {
          time: "07:00",
          days: [],
          label: "",
          urgency: "normal",
          sound_mode: "builtin",
          sound: "chime",
          announce: true,
          workday_only: false,
          voice_snooze: false,
        };
      } else if (action === "edit") {
        const alarm = this._alarms().find((item) => item.id === id);
        if (!alarm) return;
        this._editing = id;
        this._draft = {
          time: alarm.time,
          days: [...(alarm.days || [])],
          label: alarm.label || "",
          urgency: alarm.urgency || "normal",
          sound_mode: alarm.sound_mode || "builtin",
          sound: alarm.sound || "chime",
          announce: alarm.announce !== false,
          workday_only: !!alarm.workday_only,
          voice_snooze: !!alarm.voice_snooze,
        };
      } else if (action === "cancel-edit") {
        this._editing = null;
        this._draft = null;
      } else if (action === "day") {
        const days = this._draft.days;
        const index = days.indexOf(value);
        if (index >= 0) days.splice(index, 1);
        else days.push(value);
      } else if (action === "urgency") {
        this._draft.urgency = value;
      } else if (action === "sound") {
        this._draft.sound = value;
        this._draft.sound_mode = "builtin";
      } else if (action === "save") {
        this._save();
        return;
      } else if (action === "delete") {
        this._call("alarm_cancel", { id });
        this._editing = null;
        this._draft = null;
      } else if (action === "toggle") {
        const alarm = this._alarms().find((item) => item.id === id);
        this._call("alarm_update", { id, enabled: alarm?.enabled === false });
        return;
      } else if (action === "snooze") {
        this._call("alarm_snooze", { id });
        return;
      } else if (action === "dismiss") {
        this._call("alarm_dismiss", { id });
        return;
      } else if (action === "skip") {
        this._call("alarm_skip_next", { id });
        return;
      }
      this._fingerprint = null;
      this._render();
    }

    _onChange(event) {
      const el = event.target.closest("[data-field]");
      if (!el || !this._draft) return;
      const field = el.dataset.field;
      this._draft[field] =
        el.type === "checkbox" ? el.checked : el.value;
    }

    _save() {
      const draft = this._draft;
      const payload = {
        time: draft.time,
        days: draft.days,
        label: draft.label,
        urgency: draft.urgency,
        sound_mode: draft.sound_mode,
        sound: draft.sound,
        announce: !!draft.announce,
        workday_only: !!draft.workday_only,
        voice_snooze: !!draft.voice_snooze,
      };
      if (this._editing === "new") {
        this._call("alarm_set", payload);
      } else {
        this._call("alarm_update", { id: this._editing, ...payload });
      }
      this._editing = null;
      this._draft = null;
      this._fingerprint = null;
      this._render();
    }

    _call(service, data) {
      this._hass.callService("herold", service, data);
    }

    // -- Rendering ---------------------------------------------------------

    _render() {
      if (!this._hass) return;
      const title = esc(this._config.title || "Wecker");
      const meta = this._meta();
      const body = this._entity()
        ? this._editing
          ? this._renderEditor()
          : this._renderList(meta)
        : '<div class="empty">Kein Herold-Wecker-Sensor gefunden.</div>';

      this.shadowRoot.innerHTML = `
        <style>
          ha-card { padding: 12px 8px 8px; }
          .head { display: flex; align-items: center; gap: 8px;
            padding: 0 8px 8px; }
          .head .title { flex: 1; font-size: 1.3em; font-weight: 600; }
          .add { border: none; background: none; cursor: pointer;
            font-size: 1.6em; line-height: 1; color: var(--primary-color); }
          .row { display: flex; align-items: center; gap: 12px;
            padding: 10px 8px; border-bottom: 1px solid var(--divider-color); }
          .row:last-child { border-bottom: none; }
          .row.ringing { background: var(--error-color, #ef5350);
            border-radius: 12px; color: #fff; }
          .row .main { flex: 1; min-width: 0; cursor: pointer; }
          .time { font-size: 2.1em; font-weight: 300; line-height: 1.05;
            color: var(--primary-text-color); }
          .row.off .time, .row.off .sub { opacity: 0.42; }
          .row.ringing .time, .row.ringing .sub { color: #fff; }
          .sub { font-size: 0.8em; color: var(--secondary-text-color);
            margin-top: 2px; }
          .switch { width: 46px; height: 27px; border-radius: 14px;
            border: none; cursor: pointer; position: relative; flex-shrink: 0;
            background: var(--disabled-text-color); transition: background .2s; }
          .switch.on { background: var(--success-color, #43a047); }
          .switch::after { content: ""; position: absolute; top: 3px; left: 3px;
            width: 21px; height: 21px; border-radius: 50%; background: #fff;
            transition: transform .2s; }
          .switch.on::after { transform: translateX(19px); }
          .btn { border: none; border-radius: 10px; padding: 7px 12px;
            cursor: pointer; font: inherit; font-size: .85em;
            background: var(--secondary-background-color);
            color: var(--primary-text-color); }
          .btn.primary { background: var(--primary-color);
            color: var(--text-primary-color, #fff); }
          .btn.danger { color: var(--error-color, #ef5350); }
          .empty { padding: 22px 8px; text-align: center;
            color: var(--secondary-text-color); }
          .note { font-size: .78em; color: var(--secondary-text-color);
            padding: 6px 8px 0; }
          .editor { padding: 4px 8px 8px; }
          .field { margin-bottom: 14px; }
          .field > label { display: block; font-size: .75em;
            text-transform: uppercase; letter-spacing: .05em;
            color: var(--secondary-text-color); margin-bottom: 6px; }
          input[type="time"], input[type="text"] {
            width: 100%; box-sizing: border-box; font: inherit;
            padding: 10px; border-radius: 10px;
            border: 1px solid var(--divider-color);
            background: var(--card-background-color);
            color: var(--primary-text-color); }
          input[type="time"] { font-size: 2em; text-align: center;
            font-weight: 300; }
          .pills { display: flex; gap: 6px; flex-wrap: wrap; }
          .pill { flex: 1; min-width: 38px; border: none; border-radius: 10px;
            padding: 9px 0; cursor: pointer; font: inherit; font-size: .85em;
            background: var(--secondary-background-color);
            color: var(--secondary-text-color); }
          .pill.on { background: var(--primary-color);
            color: var(--text-primary-color, #fff); font-weight: 600; }
          .check { display: flex; align-items: center; gap: 10px;
            font-size: .9em; margin-bottom: 10px; }
          .actions { display: flex; gap: 8px; margin-top: 16px; }
          .actions .btn { flex: 1; padding: 11px; }
        </style>
        <ha-card>
          <div class="head">
            <span>⏰</span><span class="title">${title}</span>
            ${
              this._editing
                ? ""
                : '<button class="add" data-action="new" title="Wecker hinzufügen">+</button>'
            }
          </div>
          ${body}
        </ha-card>`;
    }

    _renderList(meta) {
      const alarms = this._alarms();
      const target = meta.target
        ? `<div class="note">🔊 Klingelt in: <b>${esc(meta.target)}</b>${
            meta.in_bed ? " · im Bett erkannt" : ""
          }</div>`
        : "";
      if (!alarms.length) {
        return `${target}<div class="empty">Kein Wecker gestellt.<br>
          Mit ＋ oben rechts anlegen.</div>`;
      }
      const rows = alarms
        .map((alarm) => {
          const ringing =
            alarm.status === "ringing" || alarm.status === "verifying";
          const enabled = alarm.enabled !== false;
          const parts = [alarm.schedule];
          if (alarm.workday_only) parts.push("nur Arbeitstage");
          if (alarm.skip_next) parts.push("nächster übersprungen");
          if (enabled && alarm.next_trigger && !ringing) {
            const rel = fmtRelative(alarm.next_trigger);
            if (rel) parts.push(rel);
          }
          const controls = ringing
            ? `<button class="btn" data-action="snooze" data-id="${esc(
                alarm.id
              )}">😴</button>
               <button class="btn primary" data-action="dismiss" data-id="${esc(
                 alarm.id
               )}">Aus</button>`
            : `<button class="switch ${enabled ? "on" : ""}"
                 data-action="toggle" data-id="${esc(alarm.id)}"></button>`;
          return `
            <div class="row ${ringing ? "ringing" : enabled ? "" : "off"}">
              <div class="main" data-action="edit" data-id="${esc(alarm.id)}">
                <div class="time">${esc(alarm.time)}</div>
                <div class="sub">${esc(
                  [alarm.label, ...parts].filter(Boolean).join(" · ")
                )}</div>
              </div>
              ${controls}
            </div>`;
        })
        .join("");
      return target + rows;
    }

    _renderEditor() {
      const draft = this._draft;
      const isNew = this._editing === "new";
      const dayPills = DAYS.map(
        ([key, label]) => `
          <button class="pill ${draft.days.includes(key) ? "on" : ""}"
            data-action="day" data-value="${key}">${label}</button>`
      ).join("");
      const urgencyPills = URGENCY.map(
        ([key, label]) => `
          <button class="pill ${draft.urgency === key ? "on" : ""}"
            data-action="urgency" data-value="${key}">${label}</button>`
      ).join("");
      const soundPills = SOUNDS.map(
        ([key, label]) => `
          <button class="pill ${
            draft.sound_mode === "builtin" && draft.sound === key ? "on" : ""
          }" data-action="sound" data-value="${key}">${label}</button>`
      ).join("");

      return `
        <div class="editor">
          <div class="field">
            <label>Uhrzeit</label>
            <input type="time" data-field="time" value="${esc(draft.time)}">
          </div>
          <div class="field">
            <label>Wiederholung — nichts gewählt = einmalig</label>
            <div class="pills">${dayPills}</div>
          </div>
          <div class="field">
            <label>Bezeichnung</label>
            <input type="text" data-field="label" value="${esc(draft.label)}"
              placeholder="z.B. Arbeit">
          </div>
          <div class="field">
            <label>Hartnäckigkeit</label>
            <div class="pills">${urgencyPills}</div>
            <div class="note" style="padding-left:0">
              Sanft: leise, gibt schnell auf · Normal: 3 Snoozes ·
              Hartnäckig: laut, 1 kurzer Snooze
            </div>
          </div>
          <div class="field">
            <label>Weckton</label>
            <div class="pills">${soundPills}</div>
          </div>
          <label class="check">
            <input type="checkbox" data-field="announce"
              ${draft.announce ? "checked" : ""}>
            Nachricht nach dem Ton ansagen
          </label>
          <label class="check">
            <input type="checkbox" data-field="workday_only"
              ${draft.workday_only ? "checked" : ""}>
            Nur an Arbeitstagen (Feiertage und Krankheit blockieren)
          </label>
          <label class="check">
            <input type="checkbox" data-field="voice_snooze"
              ${draft.voice_snooze ? "checked" : ""}>
            Per Sprache schlummern (nutzt den Satelliten statt des Lautsprechers)
          </label>
          <div class="actions">
            <button class="btn" data-action="cancel-edit">Abbrechen</button>
            ${
              isNew
                ? ""
                : `<button class="btn danger" data-action="delete"
                     data-id="${esc(this._editing)}">Löschen</button>`
            }
            <button class="btn primary" data-action="save">Speichern</button>
          </div>
        </div>`;
    }
  }

  if (!customElements.get("herold-alarm-card")) {
    customElements.define("herold-alarm-card", HeroldAlarmCard);
  }
  window.customCards = window.customCards || [];
  if (!window.customCards.some((card) => card.type === "herold-alarm-card")) {
    window.customCards.push({
      type: "herold-alarm-card",
      name: "Herold Alarm Card",
      description:
        "Wecker stellen, bearbeiten, schlummern und ausschalten — im Stil einer Wecker-App.",
    });
  }
})();
