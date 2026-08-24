/**
 * Herold Alarm Card — an alarm clock you can actually operate.
 *
 * Auto-loaded by the Herold integration alongside herold-card.js.
 *
 *   type: custom:herold-alarm-card
 *   title: Wecker
 *   card_style: glass        # default | glass | material | bubble | mirror
 *   columns: 2
 *   entity: sensor.herold_naechster_wecker   # optional, auto-detected
 *
 * The list is deliberately Apple-shaped: big time, label underneath, a
 * toggle on the right, tap to open the settings. The time field is a native
 * <input type="time">, which on iOS renders the system wheel — a hand-built
 * drum would be a lot of code for a worse result.
 *
 * The visual language (card styles, tile tokens, the detail dialog) follows
 * the Weatherglass card so both can sit on one dashboard without looking
 * like they came from different houses.
 */

(() => {
  const CARD_STYLES = ["default", "glass", "material", "bubble", "mirror"];

  const DAYS = [
    ["mon", "Mo"],
    ["tue", "Di"],
    ["wed", "Mi"],
    ["thu", "Do"],
    ["fri", "Fr"],
    ["sat", "Sa"],
    ["sun", "So"],
  ];

  const DAY_PRESETS = [
    ["Werktags", ["mon", "tue", "wed", "thu", "fri"]],
    ["Wochenende", ["sat", "sun"]],
    ["Täglich", ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]],
    ["Einmalig", []],
  ];

  const URGENCY = [
    ["gentle", "Sanft", "mdi:weather-sunset-up"],
    ["normal", "Normal", "mdi:alarm"],
    ["insistent", "Hartnäckig", "mdi:alarm-light"],
  ];

  const URGENCY_HINT = {
    gentle: "Leise, weite Abstände, gibt schnell auf — 5 Snoozes.",
    normal: "Ausgewogen: alle 45 s, 3 Snoozes.",
    insistent: "Laut und dicht, ein einziger kurzer Snooze.",
  };

  const SOUND_MODES = [
    ["builtin", "Weckton"],
    ["media", "Medien-URL"],
    ["music_assistant", "Music Assistant"],
    ["announce", "Nur Ansage"],
  ];

  const SOUNDS = [
    ["chime", "Glocke"],
    ["beep", "Piepen"],
    ["siren", "Sirene"],
    ["sunrise", "Sonnenaufgang"],
  ];

  const MEDIA_TYPES = [
    ["playlist", "Playlist"],
    ["album", "Album"],
    ["artist", "Interpret"],
    ["track", "Titel"],
    ["radio", "Radio"],
  ];

  const MEDIA_LABELS = Object.fromEntries(MEDIA_TYPES);

  const MEDIA_ICONS = {
    playlist: "mdi:playlist-music",
    album: "mdi:album",
    artist: "mdi:account-music",
    track: "mdi:music-note",
    radio: "mdi:radio",
  };

  const ACCENTS = {
    gentle: "var(--info-color, #4fc3f7)",
    normal: "var(--primary-color, #03a9f4)",
    insistent: "var(--warning-color, #ff9800)",
  };

  const SOUND_BASE = "/herold_static/sounds";

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
      return mins ? `in ${hours} h ${mins} min` : `in ${hours} h`;
    }
    return `in ${Math.round(diff / 86400)} Tagen`;
  };

  const fmtDate = (iso) => {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleString("de-DE", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  /** The bit of a media id worth showing: the file name. */
  const mediaLabel = (id) => {
    try {
      return decodeURIComponent(String(id).split("/").pop()) || id;
    } catch {
      return id;
    }
  };

  /** ISO -> the "YYYY-MM-DDTHH:MM" an <input type="datetime-local"> wants. */
  const toLocalInput = (iso) => {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    const pad = (n) => String(n).padStart(2, "0");
    return (
      `${date.getFullYear()}-${pad(date.getMonth() + 1)}-` +
      `${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
    );
  };

  class HeroldAlarmCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._editing = null; // alarm id, or "new"
      this._draft = null;
      this._advanced = false;
      this._popupFresh = false;
      this._fingerprint = null;
      this.shadowRoot.addEventListener("click", (event) => this._onClick(event));
      this.shadowRoot.addEventListener("input", (event) => this._onInput(event));
      this.shadowRoot.addEventListener("change", (event) => this._onInput(event));
    }

    static getStubConfig() {
      return { title: "Wecker" };
    }

    static getConfigElement() {
      return document.createElement("herold-alarm-card-editor");
    }

    setConfig(config) {
      this._config = config || {};
      this._fingerprint = null;
    }

    getCardSize() {
      return 5;
    }

    set hass(hass) {
      this._hass = hass;
      // Never repaint underneath an open dialog: it would throw away the
      // cursor position in whatever field is being typed into.
      if (this._editing) return;
      const entity = this._entity();
      const stamp = entity ? hass.states[entity]?.last_updated : null;
      if (stamp !== this._fingerprint) {
        this._fingerprint = stamp;
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

    _cardStyle() {
      const style = this._config.card_style || "default";
      return CARD_STYLES.includes(style) ? style : "default";
    }

    /** Scripts and scenes the good-morning routine can pick from. */
    _routines() {
      return Object.keys(this._hass.states)
        .filter((id) => id.startsWith("script.") || id.startsWith("scene."))
        .map((id) => [
          id,
          this._hass.states[id].attributes.friendly_name || id,
        ])
        .sort((a, b) => String(a[1]).localeCompare(String(b[1]), "de"));
    }

    // -- Interaction -------------------------------------------------------

    _openEditor(alarm) {
      this._draft = alarm
        ? {
            time: alarm.time,
            days: [...(alarm.days || [])],
            label: alarm.label || "",
            message: alarm.message || "",
            urgency: alarm.urgency || "normal",
            sound_mode: alarm.sound_mode || "builtin",
            sound: alarm.sound || "chime",
            sound_media_type: alarm.sound_media_type || "",
            announce: alarm.announce !== false,
            workday_only: !!alarm.workday_only,
            voice_snooze: !!alarm.voice_snooze,
            routine: alarm.routine || "",
            valid_until: toLocalInput(alarm.valid_until),
            skip_next: !!alarm.skip_next,
            repeating: (alarm.days || []).length > 0,
          }
        : {
            time: "07:00",
            days: [],
            label: "",
            message: "",
            urgency: "normal",
            sound_mode: "builtin",
            sound: "chime",
            sound_media_type: "",
            announce: true,
            workday_only: false,
            voice_snooze: false,
            routine: "",
            valid_until: "",
            skip_next: false,
            repeating: false,
          };
      this._editing = alarm ? alarm.id : "new";
      this._advanced = false;
      this._popupFresh = true;
      this._upload = null;
      this._search = null;
      this._tested = null;
    }

    _closeEditor() {
      this._editing = null;
      this._draft = null;
      this._fingerprint = null;
    }

    _onClick(event) {
      const el = event.target.closest("[data-action]");
      if (!el) return;
      const { action, id, value } = el.dataset;
      const draft = this._draft;

      if (action === "new") {
        this._openEditor(null);
      } else if (action === "edit") {
        const alarm = this._alarms().find((item) => item.id === id);
        if (!alarm) return;
        this._openEditor(alarm);
      } else if (action === "close") {
        // The backdrop itself closes the sheet; a click that merely bubbled
        // up from inside it must not.
        if (el.classList.contains("backdrop") && event.target !== el) return;
        this._closeEditor();
      } else if (action === "day") {
        const index = draft.days.indexOf(value);
        if (index >= 0) draft.days.splice(index, 1);
        else draft.days.push(value);
      } else if (action === "preset") {
        draft.days = [...DAY_PRESETS[Number(value)][1]];
      } else if (action === "urgency") {
        draft.urgency = value;
      } else if (action === "sound-mode") {
        // Each mode means something different by "sound", so a leftover
        // value from the previous one would be nonsense.
        if (value !== draft.sound_mode) draft.sound = "";
        draft.sound_mode = value;
        if (value === "builtin" && !SOUNDS.some(([key]) => key === draft.sound)) {
          draft.sound = "chime";
        }
        if (value === "announce") draft.announce = true;
        this._upload = null;
        this._search = null;
      } else if (action === "media-type") {
        draft.sound_media_type = draft.sound_media_type === value ? "" : value;
      } else if (action === "clear-sound") {
        draft.sound = "";
        this._upload = null;
        this._search = { ...this._search, pickedName: null };
      } else if (action === "pick") {
        const item = (this._search?.results || [])[Number(value)];
        if (!item) return;
        draft.sound = item.uri;
        draft.sound_media_type = item.media_type || draft.sound_media_type;
        this._search = { ...this._search, pickedName: item.name };
      } else if (action === "search") {
        this._search_();
        return;
      } else if (action === "test-sound") {
        this._test("sound");
        return;
      } else if (action === "test-light") {
        this._test("light");
        return;
      } else if (action === "sound") {
        draft.sound = value;
        this._preview(value);
      } else if (action === "preview") {
        this._preview(draft.sound);
        return;
      } else if (action === "advanced") {
        this._advanced = !this._advanced;
      } else if (action === "save") {
        this._save();
        return;
      } else if (action === "delete") {
        this._call("alarm_cancel", { id });
        this._closeEditor();
        this._render();
        return;
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
        this._closeEditor();
        this._render();
        return;
      } else {
        return;
      }

      if (this._editing) this._renderPopup();
      else this._render();
    }

    _onInput(event) {
      if (!this._draft) return;
      const search = event.target.closest("[data-search]");
      if (search) {
        // Kept out of the draft: it is a query, not a setting.
        this._search = { ...this._search, query: search.value };
        return;
      }
      const picker = event.target.closest("[data-file]");
      if (picker) {
        this._uploadFile(picker.files?.[0]);
        return;
      }
      const el = event.target.closest("[data-field]");
      if (!el) return;
      const field = el.dataset.field;
      const before = this._draft[field];
      this._draft[field] = el.type === "checkbox" ? el.checked : el.value;
      // Checkboxes and selects change what the rest of the form should show;
      // free text must never trigger a repaint or the caret jumps.
      if (el.type === "checkbox" && before !== this._draft[field]) {
        this._renderPopup();
      }
    }

    _preview(sound) {
      if (this._draft?.sound_mode !== "builtin") return;
      if (!SOUNDS.some(([key]) => key === sound)) return;
      this._audio?.pause();
      this._audio = new Audio(`${SOUND_BASE}/${sound}.wav`);
      this._audio.volume = 0.5;
      this._audio.play().catch(() => {
        /* autoplay policy, nothing to do about it */
      });
    }

    _save() {
      const draft = this._draft;
      const payload = {
        time: draft.time,
        days: draft.days,
        label: draft.label,
        message: draft.message,
        urgency: draft.urgency,
        sound_mode: draft.sound_mode,
        sound: draft.sound_mode === "announce" ? "" : draft.sound,
        sound_media_type:
          draft.sound_mode === "music_assistant" ? draft.sound_media_type : "",
        announce: !!draft.announce,
        workday_only: !!draft.workday_only,
        voice_snooze: !!draft.voice_snooze,
        routine: draft.routine,
        valid_until: draft.valid_until,
      };
      if (this._editing === "new") {
        this._call("alarm_set", payload);
      } else {
        this._call("alarm_update", { id: this._editing, ...payload });
      }
      this._closeEditor();
      this._render();
    }

    _call(service, data) {
      this._hass.callService("herold", service, data);
    }

    // -- Rendering ---------------------------------------------------------

    _render() {
      if (!this._hass) return;
      const config = this._config;
      const classes = [
        "cardroot",
        `s-${this._cardStyle()}`,
        config.tiles === false ? "flat" : "tiles",
        config.background === false ? "nobg" : "",
        config.flush ? "flush" : "",
      ]
        .filter(Boolean)
        .join(" ");
      const columns = Math.min(3, Math.max(1, Number(config.columns) || 1));

      this.shadowRoot.innerHTML = `
        <style>${STYLES}</style>
        <ha-card class="${classes}" style="--hac-columns:${columns}">
          ${this._renderHeader()}
          ${this._renderBody(config)}
        </ha-card>
        <div class="popup-host"></div>`;
      this._popupHost = this.shadowRoot.querySelector(".popup-host");
      this._renderPopup();
    }

    _renderHeader() {
      const config = this._config;
      const meta = this._meta();
      const target = meta.target
        ? `<div class="targetline">
             <ha-icon icon="mdi:volume-high"></ha-icon>
             <span>Klingelt in <b>${esc(meta.target)}</b>${
               meta.in_bed ? " · im Bett erkannt" : ""
             }</span>
           </div>`
        : "";
      return `
        <div class="header">
          <div class="titlerow">
            <div class="iconchip head-icon"><ha-icon icon="mdi:alarm"></ha-icon></div>
            <div class="titles">
              <div class="title">${esc(config.title ?? "Wecker")}</div>
              ${
                config.subtitle
                  ? `<div class="subtitle">${esc(config.subtitle)}</div>`
                  : ""
              }
            </div>
            <button class="add" data-action="new" title="Wecker hinzufügen">
              <ha-icon icon="mdi:plus"></ha-icon>
            </button>
          </div>
          ${target}
        </div>`;
    }

    _renderBody(config) {
      if (!this._entity()) {
        return `<div class="empty">Kein Herold-Wecker-Sensor gefunden.</div>`;
      }
      const alarms = this._alarms();
      if (!alarms.length) {
        return `<div class="empty">
          <ha-icon icon="mdi:alarm-off"></ha-icon>
          <div>Kein Wecker gestellt.</div>
          <button class="btn primary" data-action="new">Wecker anlegen</button>
        </div>`;
      }
      const carousel = config.layout === "carousel" ? "carousel" : "";
      return `<div class="alarms ${carousel}">
        ${alarms.map((alarm) => this._renderAlarm(alarm)).join("")}
      </div>`;
    }

    _renderAlarm(alarm) {
      const ringing = alarm.status === "ringing" || alarm.status === "verifying";
      const enabled = alarm.enabled !== false;
      const accent = ringing
        ? "var(--error-color, #ef5350)"
        : ACCENTS[alarm.urgency] || ACCENTS.normal;

      const dots = DAYS.map(
        ([key, label]) =>
          `<span class="dot ${
            (alarm.days || []).includes(key) ? "on" : ""
          }">${label}</span>`
      ).join("");

      const badges = [];
      if (alarm.workday_only) badges.push(["mdi:briefcase", "Arbeitstage"]);
      if (alarm.blocked) badges.push(["mdi:sleep-off", "heute blockiert"]);
      if (alarm.skip_next) badges.push(["mdi:debug-step-over", "übersprungen"]);
      if (alarm.routine) badges.push(["mdi:play-circle", "Routine"]);
      if (alarm.valid_until) {
        badges.push(["mdi:timer-sand", `bis ${fmtDate(alarm.valid_until)}`]);
      }
      if (alarm.voice_snooze) badges.push(["mdi:microphone", "Sprach-Snooze"]);

      const rel =
        enabled && !ringing && alarm.next_trigger
          ? fmtRelative(alarm.next_trigger)
          : "";
      const sub = [alarm.schedule, rel].filter(Boolean).join(" · ");

      const controls = ringing
        ? `<div class="ringrow">
             <button class="btn" data-action="snooze" data-id="${esc(alarm.id)}">
               <ha-icon icon="mdi:snooze"></ha-icon> Schlummern
             </button>
             <button class="btn primary" data-action="dismiss"
               data-id="${esc(alarm.id)}">Ich bin wach</button>
           </div>`
        : "";

      return `
        <div class="alarm ${ringing ? "ringing" : enabled ? "" : "off"}"
          style="--hac-accent:${accent}"
          data-action="edit" data-id="${esc(alarm.id)}">
          <div class="ahead">
            <div class="iconchip">
              <ha-icon icon="${ringing ? "mdi:bell-ring" : "mdi:alarm"}"></ha-icon>
            </div>
            <div class="atime">${esc(alarm.time)}</div>
            <div class="alabel">${esc(alarm.label || "")}</div>
          </div>
          ${
            ringing
              ? ""
              : `<button class="switch ${enabled ? "on" : ""}"
                   data-action="toggle" data-id="${esc(alarm.id)}"
                   aria-label="Wecker an/aus"></button>`
          }
          <div class="days">${dots}</div>
          <div class="asub">${esc(sub)}</div>
          ${
            badges.length
              ? `<div class="badges">${badges
                  .map(
                    ([icon, text]) =>
                      `<span class="badge"><ha-icon icon="${icon}"></ha-icon>${esc(
                        text
                      )}</span>`
                  )
                  .join("")}</div>`
              : ""
          }
          ${controls}
        </div>`;
    }

    // -- The settings dialog ----------------------------------------------

    _renderPopup() {
      if (!this._popupHost) return;
      if (!this._editing) {
        this._popupHost.innerHTML = "";
        return;
      }
      const draft = this._draft;
      const isNew = this._editing === "new";
      const alarm = isNew
        ? null
        : this._alarms().find((item) => item.id === this._editing);
      const accent = ACCENTS[draft.urgency] || ACCENTS.normal;

      this._popupHost.innerHTML = `
        <div class="backdrop s-${this._cardStyle()} ${
          this._popupFresh ? "anim" : ""
        }" data-action="close">
          <div class="dialog" role="dialog" aria-modal="true"
            style="--hac-accent:${accent}"
            >
            <div class="dialog-head">
              <div class="iconchip"><ha-icon icon="mdi:alarm"></ha-icon></div>
              <div class="dialog-title">${
                isNew ? "Neuer Wecker" : esc(draft.label || alarm?.time || "Wecker")
              }</div>
              <button class="close" data-action="close" aria-label="Schließen">
                <ha-icon icon="mdi:close"></ha-icon>
              </button>
            </div>
            ${this._renderForm(draft, isNew, alarm)}
          </div>
        </div>`;
      this._popupFresh = false;
      this._wirePopup();
    }

    /** Listeners the delegated click handler cannot express. */
    _wirePopup() {
      const drop = this._popupHost.querySelector("[data-drop]");
      if (drop) {
        const picker = drop.querySelector("[data-file]");
        drop.addEventListener("click", () => picker.click());
        drop.addEventListener("dragover", (event) => {
          event.preventDefault();
          drop.classList.add("over");
        });
        drop.addEventListener("dragleave", () => drop.classList.remove("over"));
        drop.addEventListener("drop", (event) => {
          event.preventDefault();
          drop.classList.remove("over");
          this._uploadFile(event.dataTransfer?.files?.[0]);
        });
      }
      this._popupHost
        .querySelector("[data-search]")
        ?.addEventListener("keydown", (event) => {
          if (event.key !== "Enter") return;
          event.preventDefault();
          this._search_();
        });
    }

    _renderForm(draft, isNew, alarm) {
      const pills = (items, action, active) =>
        items
          .map(
            ([key, label, icon]) => `
              <button class="pill ${active(key) ? "on" : ""}"
                data-action="${action}" data-value="${esc(key)}">
                ${icon ? `<ha-icon icon="${icon}"></ha-icon>` : ""}${esc(label)}
              </button>`
          )
          .join("");

      const dayPills = pills(DAYS, "day", (key) => draft.days.includes(key));
      const presetPills = DAY_PRESETS.map(
        ([label, days], index) => `
          <button class="chip ${
            days.length === draft.days.length &&
            days.every((day) => draft.days.includes(day))
              ? "on"
              : ""
          }" data-action="preset" data-value="${index}">${label}</button>`
      ).join("");
      const urgencyPills = pills(URGENCY, "urgency", (key) => draft.urgency === key);
      const modePills = pills(
        SOUND_MODES,
        "sound-mode",
        (key) => draft.sound_mode === key
      );

      let soundBlock = "";
      if (draft.sound_mode === "builtin") {
        soundBlock = `
          <div class="pills">${pills(
            SOUNDS,
            "sound",
            (key) => draft.sound === key
          )}</div>
          <button class="chip wide" data-action="preview">
            <ha-icon icon="mdi:play"></ha-icon> Anhören
          </button>`;
      } else if (draft.sound_mode === "media") {
        soundBlock = this._renderMediaBlock(draft);
      } else if (draft.sound_mode === "music_assistant") {
        soundBlock = this._renderMusicAssistantBlock(draft);
      } else {
        soundBlock = `<div class="hint">
          Kein Ton, nur die gesprochene Nachricht. Zum Aufwachen selten genug.
        </div>`;
      }

      const routineOptions = [
        `<option value="">— keine —</option>`,
        ...this._routines().map(
          ([id, name]) =>
            `<option value="${esc(id)}" ${
              draft.routine === id ? "selected" : ""
            }>${esc(name)}</option>`
        ),
      ].join("");

      const snoozeInfo =
        alarm && alarm.snoozes
          ? `<div class="hint">Bisher ${alarm.snoozes}× geschlummert.</div>`
          : "";

      return `
        <div class="form">
          <div class="field">
            <label>Uhrzeit</label>
            <input type="time" class="big" data-field="time"
              value="${esc(draft.time)}">
          </div>

          <div class="field">
            <label>Wiederholung</label>
            <div class="chips">${presetPills}</div>
            <div class="pills days-pills">${dayPills}</div>
            <div class="hint">${
              draft.days.length
                ? "Klingelt jede Woche an den gewählten Tagen."
                : "Nichts gewählt = einmalig, danach löscht sich der Wecker."
            }</div>
          </div>

          <div class="field">
            <label>Bezeichnung</label>
            <input type="text" data-field="label" value="${esc(draft.label)}"
              placeholder="z.B. Arbeit">
          </div>

          <div class="field">
            <label>Hartnäckigkeit</label>
            <div class="pills">${urgencyPills}</div>
            <div class="hint">${URGENCY_HINT[draft.urgency] || ""}</div>
            ${snoozeInfo}
          </div>

          <div class="field">
            <label>Klang</label>
            <div class="pills">${modePills}</div>
            ${soundBlock}
          </div>

          <div class="field">
            <label>Ausprobieren</label>
            <div class="chips">
              <button class="chip ${this._tested === "sound" ? "on" : ""}"
                data-action="test-sound">
                <ha-icon icon="${
                  this._tested === "sound" ? "mdi:check" : "mdi:volume-high"
                }"></ha-icon>
                Ton testen
              </button>
              <button class="chip ${this._tested === "light" ? "on" : ""}"
                data-action="test-light">
                <ha-icon icon="${
                  this._tested === "light" ? "mdi:check" : "mdi:lightbulb-on"
                }"></ha-icon>
                Licht testen
              </button>
            </div>
            <div class="hint">
              Klingelt sofort auf dem echten Ziel — ungespeicherte Änderungen
              zählen erst nach dem Speichern. Das Licht geht danach von selbst
              wieder in den vorherigen Zustand.
            </div>
          </div>

          <div class="field">
            <label class="check">
              <input type="checkbox" data-field="announce"
                ${draft.announce ? "checked" : ""}>
              <span>Nachricht ansagen</span>
            </label>
            ${
              draft.announce
                ? `<input type="text" data-field="message"
                     value="${esc(draft.message)}"
                     placeholder="Guten Morgen — Zeit aufzustehen.">
                   <div class="hint">Leer lassen für den Standardtext.</div>`
                : ""
            }
          </div>

          <div class="field">
            <label class="check">
              <input type="checkbox" data-field="workday_only"
                ${draft.workday_only ? "checked" : ""}>
              <span>Nur an Arbeitstagen</span>
            </label>
            <div class="hint">Feiertage und Krankmeldung blockieren ihn dann.</div>
            <label class="check">
              <input type="checkbox" data-field="voice_snooze"
                ${draft.voice_snooze ? "checked" : ""}>
              <span>Per Sprache schlummern</span>
            </label>
            <div class="hint">
              Nutzt den Assist-Satelliten statt des Lautsprechers — leiser,
              aber man kann ihn anreden.
            </div>
          </div>

          <button class="chip wide" data-action="advanced">
            <ha-icon icon="${
              this._advanced ? "mdi:chevron-up" : "mdi:chevron-down"
            }"></ha-icon>
            Mehr Einstellungen
          </button>

          ${this._advanced ? this._renderAdvanced(draft, routineOptions) : ""}

          <div class="actions">
            <button class="btn" data-action="close">Abbrechen</button>
            ${
              isNew
                ? ""
                : `<button class="btn danger" data-action="delete"
                     data-id="${esc(this._editing)}">Löschen</button>`
            }
            <button class="btn primary" data-action="save">Speichern</button>
          </div>
          ${
            !isNew && draft.repeating && !draft.skip_next
              ? `<button class="chip wide" data-action="skip"
                   data-id="${esc(this._editing)}">
                   <ha-icon icon="mdi:debug-step-over"></ha-icon>
                   Nächstes Mal überspringen
                 </button>`
              : ""
          }
        </div>`;
    }

    // -- Own media: drop a file, or paste an id --------------------------

    _renderMediaBlock(draft) {
      const current = draft.sound || "";
      const state = this._upload;
      let status = "";
      if (state?.busy) {
        status = `<div class="drop-state">Lade ${esc(state.name)} hoch …</div>`;
      } else if (state?.error) {
        status = `<div class="drop-state error">${esc(state.error)}</div>`;
      } else if (current) {
        status = `<div class="drop-state ok">
          <ha-icon icon="mdi:music-note"></ha-icon>
          <span>${esc(mediaLabel(current))}</span>
          <button class="chip" data-action="clear-sound">Entfernen</button>
        </div>`;
      }
      return `
        <div class="drop ${state?.busy ? "busy" : ""}" data-drop>
          <ha-icon icon="mdi:tray-arrow-up"></ha-icon>
          <div><b>MP3 hierher ziehen</b> oder klicken zum Auswählen</div>
          <div class="hint">
            Die Datei landet in deiner Home-Assistant-Medienbibliothek und wird
            von dort abgespielt. MP3, M4A, WAV, OGG oder FLAC.
          </div>
          <input type="file" accept="audio/*" hidden data-file>
        </div>
        ${status}
        <input type="text" data-field="sound" value="${esc(current)}"
          placeholder="media-source://media_source/local/wecker.mp3">
        <div class="hint">
          Alternativ direkt eine Medien-ID oder eine öffentlich erreichbare
          URL eintragen.
        </div>`;
    }

    async _uploadFile(file) {
      if (!file) return;
      if (!/^audio\//.test(file.type || "")) {
        this._upload = { error: `${file.name} ist keine Audiodatei.` };
        this._renderPopup();
        return;
      }
      this._upload = { busy: true, name: file.name };
      this._renderPopup();
      try {
        const folder = await this._uploadFolder();
        const body = new FormData();
        body.append("media_content_id", folder);
        body.append("file", file);
        const response = await this._hass.fetchWithAuth(
          "/api/media_source/local_source/upload",
          { method: "POST", body }
        );
        if (!response.ok) {
          throw new Error(`${response.status} ${await response.text()}`);
        }
        const result = await response.json();
        this._draft.sound = result.media_content_id;
        this._draft.sound_mode = "media";
        this._upload = null;
      } catch (err) {
        this._upload = {
          error:
            "Upload fehlgeschlagen: " +
            String(err.message || err) +
            " — braucht das Medienverzeichnis (media_dirs) in Home Assistant.",
        };
      }
      this._renderPopup();
    }

    /** The local media folder uploads go into; browsed, not guessed. */
    async _uploadFolder() {
      if (this._folder) return this._folder;
      try {
        const root = await this._hass.callWS({
          type: "media_source/browse_media",
          media_content_id: "media-source://media_source",
        });
        const child = (root.children || []).find(
          (item) => item.can_expand && item.media_content_id
        );
        if (child) this._folder = child.media_content_id;
      } catch (err) {
        console.warn("herold: could not browse media sources", err);
      }
      return this._folder || "media-source://media_source/local/.";
    }

    // -- Music Assistant: search instead of guessing ----------------------

    _renderMusicAssistantBlock(draft) {
      const search = this._search || {};
      const typePills = MEDIA_TYPES.map(
        ([key, label]) => `
          <button class="pill ${draft.sound_media_type === key ? "on" : ""}"
            data-action="media-type" data-value="${key}">${label}</button>`
      ).join("");

      let results = "";
      if (search.busy) {
        results = `<div class="drop-state">Suche läuft …</div>`;
      } else if (search.error) {
        results = `<div class="drop-state error">${esc(search.error)}</div>`;
      } else if (search.results) {
        results = search.results.length
          ? `<div class="results">${search.results
              .map(
                (item, index) => `
                  <button class="result ${
                    draft.sound === item.uri ? "on" : ""
                  }" data-action="pick" data-value="${index}">
                    <ha-icon icon="${MEDIA_ICONS[item.media_type] ||
                      "mdi:music"}"></ha-icon>
                    <span class="rname">${esc(item.name)}</span>
                    <span class="rmeta">${esc(
                      [MEDIA_LABELS[item.media_type] || item.media_type,
                       item.artist].filter(Boolean).join(" · ")
                    )}</span>
                  </button>`
              )
              .join("")}</div>`
          : `<div class="drop-state">Nichts gefunden.</div>`;
      }

      const chosen = draft.sound
        ? `<div class="drop-state ok">
             <ha-icon icon="mdi:check"></ha-icon>
             <span>${esc(search.pickedName || draft.sound)}</span>
             <button class="chip" data-action="clear-sound">Entfernen</button>
           </div>`
        : "";

      return `
        <div class="pills">${typePills}</div>
        <div class="searchrow">
          <input type="text" data-search value="${esc(search.query || "")}"
            placeholder="z.B. Morning Coffee">
          <button class="btn primary" data-action="search">
            <ha-icon icon="mdi:magnify"></ha-icon>
          </button>
        </div>
        <div class="hint">
          Medientyp wählen, suchen, Treffer antippen — gespeichert wird dann
          die eindeutige Music-Assistant-URI, kein geratener Name.
        </div>
        ${results}
        ${chosen}`;
    }

    async _search_() {
      const query = (this._search?.query || "").trim();
      if (!query) return;
      this._search = { ...this._search, busy: true, error: null };
      this._renderPopup();
      try {
        const response = await this._hass.callService(
          "herold",
          "alarm_search_media",
          {
            query,
            ...(this._draft.sound_media_type
              ? { media_type: this._draft.sound_media_type }
              : {}),
          },
          undefined,
          false,
          true
        );
        this._search = {
          query,
          results: response?.response?.results || [],
        };
      } catch (err) {
        this._search = {
          query,
          error: "Suche fehlgeschlagen: " + String(err.message || err),
        };
      }
      this._renderPopup();
    }

    // -- Trying it out ----------------------------------------------------

    _test(scope) {
      const data = { scope };
      if (this._editing && this._editing !== "new") data.id = this._editing;
      this._call("alarm_test", data);
      this._tested = scope;
      this._renderPopup();
      window.setTimeout(() => {
        if (this._tested === scope) {
          this._tested = null;
          this._renderPopup();
        }
      }, 4000);
    }

    _renderAdvanced(draft, routineOptions) {
      return `
        <div class="field">
          <label>Guten-Morgen-Routine</label>
          <select data-field="routine">${routineOptions}</select>
          <div class="hint">
            Skript oder Szene, das läuft, sobald du wirklich aufgestanden bist —
            nicht beim ersten Schlummern.
          </div>
        </div>
        <div class="field">
          <label>Läuft ab am</label>
          <input type="datetime-local" data-field="valid_until"
            value="${esc(draft.valid_until)}">
          <div class="hint">
            Für befristete Wecker, etwa während einer Projektwoche. Leer =
            unbefristet.
          </div>
        </div>`;
    }
  }

  // -- Styles --------------------------------------------------------------

  const STYLES = `
    :host {
      --hac-card-bg: var(--ha-card-background, var(--card-background-color, #fff));
      --hac-tile-bg: color-mix(in srgb, var(--primary-text-color) 4%, var(--hac-card-bg));
      --hac-accent: var(--primary-color, #03a9f4);
    }
    .cardroot { display: block; padding: 16px; }
    .cardroot.flush { padding: 0; }
    .cardroot.flat { --hac-tile-bg: transparent; }
    .cardroot.nobg { background: none; box-shadow: none; border: none; }

    /* ---- card styles --------------------------------------------------- */
    .s-glass {
      --hac-tile-bg: color-mix(in srgb, var(--hac-card-bg) 42%, transparent);
      --hac-tile-radius: 22px;
    }
    ha-card.cardroot.s-glass {
      background: color-mix(in srgb, var(--hac-card-bg) 55%, transparent);
      -webkit-backdrop-filter: blur(18px) saturate(1.5);
      backdrop-filter: blur(18px) saturate(1.5);
    }
    .s-glass .alarm {
      border: 1px solid color-mix(in srgb, var(--primary-text-color) 12%, transparent);
      box-shadow:
        inset 0 1px 0 color-mix(in srgb, #fff 25%, transparent),
        0 8px 24px color-mix(in srgb, #000 10%, transparent);
      -webkit-backdrop-filter: blur(18px) saturate(1.5);
      backdrop-filter: blur(18px) saturate(1.5);
    }
    .s-glass .iconchip {
      background: color-mix(in srgb, var(--hac-accent) 24%, transparent);
      border: 1px solid color-mix(in srgb, #fff 30%, transparent);
      box-shadow: inset 0 1px 0 color-mix(in srgb, #fff 40%, transparent);
      -webkit-backdrop-filter: blur(10px) saturate(1.4);
      backdrop-filter: blur(10px) saturate(1.4);
    }
    .s-glass .dialog {
      background: color-mix(in srgb, var(--hac-card-bg) 55%, transparent);
      -webkit-backdrop-filter: blur(26px) saturate(1.5);
      backdrop-filter: blur(26px) saturate(1.5);
      border: 1px solid color-mix(in srgb, #fff 25%, transparent);
      box-shadow:
        inset 0 1px 0 color-mix(in srgb, #fff 30%, transparent),
        0 12px 48px rgba(0, 0, 0, 0.35);
    }

    .s-material { --hac-tile-radius: 24px; }
    ha-card.cardroot.s-material { border-radius: 28px; }
    .s-material .alarm {
      position: relative;
      overflow: hidden;
      background: color-mix(in srgb, var(--hac-accent) 12%, var(--hac-card-bg));
    }
    .s-material .alarm::before {
      content: '';
      position: absolute;
      top: -70px;
      left: -70px;
      width: 190px;
      height: 190px;
      border-radius: 50%;
      background: color-mix(in srgb, var(--hac-accent) 22%, transparent);
      pointer-events: none;
    }
    .s-material .alarm > * { position: relative; }
    .s-material .iconchip {
      border-radius: 14px;
      background: var(--hac-accent);
      color: var(--hac-card-bg);
    }
    .s-material .dialog {
      border-radius: 28px;
      background:
        radial-gradient(
          circle at -30px -30px,
          color-mix(in srgb, var(--hac-accent) 24%, transparent) 0 130px,
          transparent 131px
        ),
        color-mix(in srgb, var(--hac-accent) 9%, var(--hac-card-bg));
      --hac-tile-bg: color-mix(in srgb, var(--hac-accent) 14%, var(--hac-card-bg));
    }
    .s-material .dialog .iconchip {
      background: var(--hac-accent);
      color: var(--hac-card-bg);
    }

    .s-bubble { --hac-tile-bg: var(--hac-card-bg); --hac-tile-radius: 32px; }
    ha-card.cardroot.s-bubble {
      background: none;
      box-shadow: none;
      border: none;
    }
    .s-bubble .alarm {
      box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0, 0, 0, 0.08));
      padding: 14px 18px;
    }
    .s-bubble .iconchip { width: 42px; height: 42px; }
    .s-bubble .iconchip ha-icon { --mdc-icon-size: 22px; }
    .s-bubble .alabel { font-weight: 700; }
    .s-bubble .dialog { border-radius: 32px; }

    .s-mirror { --hac-tile-bg: #000; --hac-tile-radius: 14px; color: #fff; }
    ha-card.cardroot.s-mirror {
      background: #000;
      box-shadow: none;
      border: none;
    }
    .s-mirror .alarm { border: 1px solid rgba(255, 255, 255, 0.28); }
    .s-mirror .title,
    .s-mirror .atime,
    .s-mirror .alabel,
    .s-mirror .dialog-title,
    .s-mirror .dot.on,
    .s-mirror label,
    .s-mirror .check span { color: #fff; }
    .s-mirror .subtitle,
    .s-mirror .asub,
    .s-mirror .hint,
    .s-mirror .targetline,
    .s-mirror .dot { color: rgba(255, 255, 255, 0.72); }
    .s-mirror .iconchip { background: rgba(255, 255, 255, 0.14); color: #fff; }
    .s-mirror .dialog { background: #000; border: 1px solid rgba(255, 255, 255, 0.3); }
    .s-mirror .close,
    .s-mirror .chip,
    .s-mirror .pill,
    .s-mirror .btn {
      background: rgba(255, 255, 255, 0.14);
      color: #fff;
    }
    .s-mirror .pill.on,
    .s-mirror .chip.on,
    .s-mirror .btn.primary { background: #fff; color: #000; }
    .s-mirror input, .s-mirror select {
      background: #000;
      color: #fff;
      border-color: rgba(255, 255, 255, 0.3);
    }

    /* ---- header -------------------------------------------------------- */
    .header { padding: 0 2px 14px; }
    .cardroot.flush .header { padding: 0 0 12px; }
    .titlerow { display: flex; align-items: center; gap: 10px; }
    .titles { flex: 1; min-width: 0; }
    .title {
      font-size: 22px;
      font-weight: 700;
      letter-spacing: -0.3px;
      color: var(--primary-text-color);
    }
    .subtitle { font-size: 13px; color: var(--secondary-text-color); margin-top: 2px; }
    .head-icon { --hac-accent: var(--primary-color, #03a9f4); }
    .add {
      width: 36px;
      height: 36px;
      flex: none;
      border: none;
      border-radius: 50%;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--primary-color);
      background: color-mix(in srgb, var(--primary-color) 14%, transparent);
    }
    .targetline {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-top: 10px;
      font-size: 12.5px;
      color: var(--secondary-text-color);
    }
    .targetline ha-icon { --mdc-icon-size: 16px; }

    /* ---- alarm tiles --------------------------------------------------- */
    .alarms {
      display: grid;
      grid-template-columns: repeat(var(--hac-columns, 1), minmax(0, 1fr));
      gap: 12px;
    }
    .cardroot.flat .alarms { gap: 4px; }
    .cardroot.flat .alarm { border: none; box-shadow: none; }
    .alarms.carousel {
      display: flex;
      overflow-x: auto;
      scroll-snap-type: x mandatory;
      scrollbar-width: none;
    }
    .alarms.carousel::-webkit-scrollbar { display: none; }
    .alarms.carousel > .alarm {
      flex: 0 0 min(85%, 320px);
      scroll-snap-align: center;
      min-width: 0;
    }
    .alarm {
      position: relative;
      background: var(--hac-tile-bg);
      border-radius: var(--hac-tile-radius, 16px);
      box-sizing: border-box;
      padding: 14px 16px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      cursor: pointer;
      transition: background 0.15s ease;
    }
    .alarm:hover {
      background: color-mix(in srgb, var(--primary-text-color) 7%, var(--hac-card-bg));
    }
    .alarm.off { opacity: 0.5; }
    .alarm.ringing {
      animation: hac-pulse 1.4s ease-in-out infinite;
      box-shadow: 0 0 0 2px var(--hac-accent);
    }
    @keyframes hac-pulse {
      50% { box-shadow: 0 0 0 6px color-mix(in srgb, var(--hac-accent) 25%, transparent); }
    }
    .ahead {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
      padding-right: 52px;
    }
    .iconchip {
      width: 32px;
      height: 32px;
      border-radius: 50%;
      flex: none;
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--hac-accent);
      background: color-mix(in srgb, var(--hac-accent) 14%, transparent);
    }
    .iconchip ha-icon { --mdc-icon-size: 18px; }
    .atime {
      font-size: 34px;
      font-weight: 300;
      line-height: 1;
      letter-spacing: -1px;
      font-variant-numeric: tabular-nums;
      color: var(--primary-text-color);
    }
    .alabel {
      flex: 1;
      min-width: 0;
      font-size: 14px;
      font-weight: 600;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--primary-text-color);
    }
    .switch {
      position: absolute;
      top: 14px;
      right: 16px;
      width: 46px;
      height: 27px;
      border-radius: 14px;
      border: none;
      cursor: pointer;
      flex-shrink: 0;
      background: var(--disabled-text-color);
      transition: background 0.2s;
    }
    .switch.on { background: var(--success-color, #43a047); }
    .switch::after {
      content: "";
      position: absolute;
      top: 3px;
      left: 3px;
      width: 21px;
      height: 21px;
      border-radius: 50%;
      background: #fff;
      transition: transform 0.2s;
    }
    .switch.on::after { transform: translateX(19px); }
    .days { display: flex; gap: 4px; }
    .dot {
      flex: 1;
      text-align: center;
      font-size: 11px;
      font-weight: 600;
      padding: 3px 0;
      border-radius: 6px;
      color: var(--secondary-text-color);
      opacity: 0.45;
    }
    .dot.on {
      opacity: 1;
      color: var(--hac-accent);
      background: color-mix(in srgb, var(--hac-accent) 14%, transparent);
    }
    .asub { font-size: 12.5px; color: var(--secondary-text-color); }
    .badges { display: flex; flex-wrap: wrap; gap: 5px; }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 3px;
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 999px;
      color: var(--secondary-text-color);
      background: color-mix(in srgb, var(--primary-text-color) 8%, transparent);
    }
    .badge ha-icon { --mdc-icon-size: 13px; }
    .ringrow { display: flex; gap: 8px; margin-top: 2px; }
    .ringrow .btn { flex: 1; }

    /* ---- shared controls ----------------------------------------------- */
    .btn {
      border: none;
      border-radius: 12px;
      padding: 10px 14px;
      cursor: pointer;
      font: inherit;
      font-size: 13px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 5px;
      background: color-mix(in srgb, var(--primary-text-color) 8%, transparent);
      color: var(--primary-text-color);
    }
    .btn ha-icon { --mdc-icon-size: 17px; }
    .btn.primary {
      background: var(--hac-accent);
      color: var(--text-primary-color, #fff);
      font-weight: 600;
    }
    .btn.danger { color: var(--error-color, #ef5350); }
    .pills { display: flex; gap: 6px; flex-wrap: wrap; }
    .days-pills { margin-top: 6px; }
    .pill {
      flex: 1;
      min-width: 42px;
      border: none;
      border-radius: 11px;
      padding: 9px 6px;
      cursor: pointer;
      font: inherit;
      font-size: 12.5px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 4px;
      background: color-mix(in srgb, var(--primary-text-color) 8%, transparent);
      color: var(--secondary-text-color);
    }
    .pill ha-icon { --mdc-icon-size: 16px; }
    .pill.on {
      background: var(--hac-accent);
      color: var(--text-primary-color, #fff);
      font-weight: 600;
    }
    .chips { display: flex; gap: 6px; flex-wrap: wrap; }
    .chip {
      border: none;
      border-radius: 999px;
      padding: 6px 12px;
      cursor: pointer;
      font: inherit;
      font-size: 12px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 4px;
      background: color-mix(in srgb, var(--primary-text-color) 8%, transparent);
      color: var(--secondary-text-color);
    }
    .chip ha-icon { --mdc-icon-size: 15px; }
    .chip.on {
      background: color-mix(in srgb, var(--hac-accent) 20%, transparent);
      color: var(--hac-accent);
      font-weight: 600;
    }
    .chip.wide { width: 100%; margin-bottom: 14px; }
    .empty {
      padding: 26px 8px;
      text-align: center;
      color: var(--secondary-text-color);
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 10px;
    }
    .empty ha-icon { --mdc-icon-size: 34px; opacity: 0.5; }

    /* ---- dialog -------------------------------------------------------- */
    .backdrop {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.5);
      z-index: 999;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 16px;
    }
    .backdrop.anim { animation: hac-fadein 0.15s ease; }
    @keyframes hac-fadein { from { opacity: 0; } }
    .dialog {
      width: min(440px, 100%);
      max-height: 86vh;
      overflow-y: auto;
      box-sizing: border-box;
      background: var(--hac-card-bg);
      color: var(--primary-text-color);
      border-radius: 24px;
      padding: 20px;
      box-shadow: 0 12px 48px rgba(0, 0, 0, 0.3);
      display: flex;
      flex-direction: column;
      gap: 12px;
      --hac-tile-bg: color-mix(in srgb, var(--primary-text-color) 4%, var(--hac-card-bg));
    }
    .dialog-head { display: flex; align-items: center; gap: 10px; }
    .dialog-title {
      flex: 1;
      font-size: 17px;
      font-weight: 700;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .close {
      width: 32px;
      height: 32px;
      flex: none;
      border: none;
      border-radius: 50%;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--secondary-text-color);
      background: color-mix(in srgb, var(--primary-text-color) 7%, transparent);
    }
    .close ha-icon { --mdc-icon-size: 18px; }
    .field { margin-bottom: 16px; }
    .field > label {
      display: block;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-weight: 600;
      color: var(--secondary-text-color);
      margin-bottom: 7px;
    }
    input[type="time"],
    input[type="text"],
    input[type="datetime-local"],
    select {
      width: 100%;
      box-sizing: border-box;
      font: inherit;
      font-size: 14px;
      padding: 11px;
      border-radius: 12px;
      border: 1px solid var(--divider-color);
      background: var(--hac-card-bg);
      color: var(--primary-text-color);
    }
    input.big {
      font-size: 40px;
      text-align: center;
      font-weight: 300;
      letter-spacing: -1px;
      padding: 6px;
    }
    .hint {
      font-size: 11.5px;
      line-height: 1.45;
      color: var(--secondary-text-color);
      margin-top: 6px;
    }
    .check {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 14px;
      margin-bottom: 8px;
      text-transform: none;
      letter-spacing: 0;
      cursor: pointer;
    }
    .check input { accent-color: var(--hac-accent); width: 18px; height: 18px; }

    /* ---- upload, search, results --------------------------------------- */
    .drop {
      border: 2px dashed color-mix(in srgb, var(--primary-text-color) 22%, transparent);
      border-radius: 14px;
      padding: 18px 14px;
      text-align: center;
      cursor: pointer;
      color: var(--secondary-text-color);
      transition: border-color 0.15s ease, background 0.15s ease;
    }
    .drop:hover, .drop.over {
      border-color: var(--hac-accent);
      background: color-mix(in srgb, var(--hac-accent) 8%, transparent);
    }
    .drop.busy { opacity: 0.6; pointer-events: none; }
    .drop ha-icon { --mdc-icon-size: 26px; color: var(--hac-accent); }
    .drop b { color: var(--primary-text-color); }
    .drop .hint { margin-top: 4px; }
    .drop-state {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 8px;
      font-size: 12.5px;
      padding: 8px 10px;
      border-radius: 10px;
      color: var(--secondary-text-color);
      background: color-mix(in srgb, var(--primary-text-color) 6%, transparent);
    }
    .drop-state span { flex: 1; min-width: 0; overflow: hidden;
      text-overflow: ellipsis; white-space: nowrap; }
    .drop-state ha-icon { --mdc-icon-size: 16px; flex: none; }
    .drop-state.ok { color: var(--primary-text-color); }
    .drop-state.ok ha-icon { color: var(--success-color, #43a047); }
    .drop-state.error {
      color: var(--error-color, #ef5350);
      background: color-mix(in srgb, var(--error-color, #ef5350) 12%, transparent);
    }
    .searchrow { display: flex; gap: 8px; margin-top: 8px; }
    .searchrow input { flex: 1; }
    .searchrow .btn { flex: none; padding: 0 14px; }
    .results {
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin-top: 10px;
      max-height: 220px;
      overflow-y: auto;
    }
    .result {
      display: grid;
      grid-template-columns: 24px 1fr auto;
      align-items: center;
      gap: 8px;
      text-align: left;
      border: none;
      border-radius: 10px;
      padding: 9px 10px;
      cursor: pointer;
      font: inherit;
      background: color-mix(in srgb, var(--primary-text-color) 5%, transparent);
      color: var(--primary-text-color);
    }
    .result:hover {
      background: color-mix(in srgb, var(--hac-accent) 14%, transparent);
    }
    .result.on {
      background: color-mix(in srgb, var(--hac-accent) 22%, transparent);
      box-shadow: inset 0 0 0 1px var(--hac-accent);
    }
    .result ha-icon { --mdc-icon-size: 18px; color: var(--hac-accent); }
    .rname { font-size: 13.5px; overflow: hidden; text-overflow: ellipsis;
      white-space: nowrap; }
    .rmeta { font-size: 11px; color: var(--secondary-text-color); }
    .s-mirror .result { background: rgba(255, 255, 255, 0.1); color: #fff; }
    .s-mirror .drop-state { background: rgba(255, 255, 255, 0.1); }
    .actions { display: flex; gap: 8px; margin-top: 4px; }
    .actions .btn { flex: 1; padding: 12px 8px; }
  `;

  // -- Lovelace visual editor ---------------------------------------------

  const EDITOR_SCHEMA = [
    { name: "title", selector: { text: {} } },
    { name: "subtitle", selector: { text: {} } },
    {
      name: "entity",
      selector: { entity: { domain: "sensor", integration: "herold" } },
    },
    {
      name: "card_style",
      selector: {
        select: {
          mode: "dropdown",
          options: [
            { value: "default", label: "Standard" },
            { value: "glass", label: "Liquid Glass" },
            { value: "material", label: "Material You" },
            { value: "bubble", label: "Bubble" },
            { value: "mirror", label: "Magic Mirror" },
          ],
        },
      },
    },
    {
      name: "layout",
      selector: {
        select: {
          mode: "dropdown",
          options: [
            { value: "grid", label: "Raster" },
            { value: "carousel", label: "Karussell" },
          ],
        },
      },
    },
    { name: "columns", selector: { number: { min: 1, max: 3, mode: "box" } } },
    { name: "tiles", selector: { boolean: {} } },
    { name: "background", selector: { boolean: {} } },
    { name: "flush", selector: { boolean: {} } },
  ];

  const EDITOR_LABELS = {
    title: "Überschrift",
    subtitle: "Untertitel",
    entity: "Wecker-Sensor (leer = automatisch)",
    card_style: "Kartenstil",
    layout: "Anordnung",
    columns: "Spalten",
    tiles: "Wecker als Kacheln",
    background: "Kartenhintergrund",
    flush: "Ohne Außenabstand",
  };

  class HeroldAlarmCardEditor extends HTMLElement {
    setConfig(config) {
      this._config = config || {};
      this._render();
    }

    set hass(hass) {
      this._hass = hass;
      if (this._form) this._form.hass = hass;
    }

    _render() {
      if (this._form) {
        this._form.data = this._data();
        return;
      }
      this._form = document.createElement("ha-form");
      this._form.schema = EDITOR_SCHEMA;
      this._form.data = this._data();
      this._form.hass = this._hass;
      this._form.computeLabel = (item) => EDITOR_LABELS[item.name] || item.name;
      this._form.addEventListener("value-changed", (event) => {
        this.dispatchEvent(
          new CustomEvent("config-changed", {
            detail: { config: { ...this._config, ...event.detail.value } },
            bubbles: true,
            composed: true,
          })
        );
      });
      this.appendChild(this._form);
    }

    _data() {
      return {
        card_style: "default",
        layout: "grid",
        columns: 1,
        tiles: true,
        background: true,
        flush: false,
        ...this._config,
      };
    }
  }

  if (!customElements.get("herold-alarm-card")) {
    customElements.define("herold-alarm-card", HeroldAlarmCard);
  }
  if (!customElements.get("herold-alarm-card-editor")) {
    customElements.define("herold-alarm-card-editor", HeroldAlarmCardEditor);
  }
  window.customCards = window.customCards || [];
  if (!window.customCards.some((card) => card.type === "herold-alarm-card")) {
    window.customCards.push({
      type: "herold-alarm-card",
      name: "Herold Alarm Card",
      description:
        "Wecker stellen, bearbeiten, schlummern und ausschalten — im Stil einer Wecker-App.",
      preview: true,
      documentationURL: "https://github.com/BobMcGlobus/herold",
    });
  }
})();
