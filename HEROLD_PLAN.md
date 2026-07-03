# Projektplan: `herold` — Herold — HACS Integration

> **User-Facing Name:** Herold (deutscher Bote/Ausrufer — Herold mit Trompete als Icon-Motiv)
> **Domain / Prefix:** `herold`
> **Ausgangsbasis:** Migration von `script.system_universal_omnichannel_communicator_priority_edition` zu einer wartbaren Custom Integration. Inspiriert von [jumping2000/universal_notifier](https://github.com/jumping2000/universal_notifier), aber substanziell erweitert.
>
> **Zielinstanzen:** Primär Casa de Jonas, portabel für Fährenbruch / Hoppetosse / AnNi's Stoffwelt.
>
> **HA Version Target:** 2026.7+ (nutzt aktuelle `assist_satellite`, `todo`, `conversation`, LLM Tool APIs)

---

## 1. Motivation & Ziele

### Warum weg vom Script?
- **Wartbarkeit:** Jinja-Templates in YAML sind unlesbar geworden
- **State-Handling:** Pending Queries, Scheduled Notifications, Escalation Timer, History — kein Ort im Script
- **UI:** Keine Config-UI, keine sichtbaren Entities, kein Debug-Panel
- **LLM-Integration:** P0-Self-Callback und P1-Todo-Workflow brauchen native Tools
- **Testbarkeit:** Python + pytest statt YAML-Ratespiel

### Kernprinzipien
1. **Offline-First** — jeder Channel deklariert `offline_capable`; bei Internet-Loss läuft alles Wichtige weiter (Piper-TTS, Todo, LLM-Tools)
2. **First-Class Objects** — Notification, Query, Schedule sind eigene Entities mit State, nicht nur Runtime-Variablen
3. **Deklarative Konfig** — UI Config Flow, YAML nur für Migration
4. **LLM-nativ** — Self-Callback via P0 ist erklärtes Feature, nicht Hack
5. **Rückwärtskompat** — bestehende `AI_CONFIRM_*` Events und `input_boolean.notification_blocker` bleiben funktional

---

## 2. Architektur-Überblick

### High-Level

```
┌───────────────────────────────────────────────────────────────┐
│ Services API      LLM Tools        Assist Intents             │
│ herold.send      list_pending     "Was ist neu"              │
│ herold.query     ack_notification "Erledige Notif"           │
│ herold.schedule  answer_query                                │
│ herold.remind_self (P0-Convenience)                          │
└────────────────┬──────────────────────────────────────────────┘
                 │
         ┌───────▼────────┐        ┌──────────────────┐
         │   Scheduler    │◄──────►│  Persistent Store│
         └───────┬────────┘        │  (Queries, Sched,│
                 │                 │   Escalations)   │
         ┌───────▼────────┐        └──────────────────┘
         │  Dispatcher    │
         │  Rate-Limiter  │◄─── Blocker/DND/Home/Prio-Regeln
         │  Aggregator    │
         └───────┬────────┘
                 │
    ┌────────────┼────────────┬─────────────┬─────────────┐
    ▼            ▼            ▼             ▼             ▼
┌────────┐  ┌────────┐  ┌───────────┐  ┌──────────┐  ┌──────────┐
│Voice   │  │Push    │  │Chat       │  │Todo      │  │Internal  │
│Channel │  │Channel │  │Channel    │  │Channel   │  │(P0/LLM)  │
└────────┘  └────────┘  └───────────┘  └──────────┘  └──────────┘
    │           │             │              │             │
    ▼           ▼             ▼              ▼             ▼
Room-Router mobile_app   Telegram      todo entity   conversation
(occupancy) (critical)   (buttons)     (LLM-lesbar)  .process
    │
    ▼
Sat/Media Player Fallback-Chain (ElevenLabs → Piper offline)
```

### Datenfluss

**Notification (fire-and-forget):**
1. Ingest → Dispatcher prüft Regeln → Channel Selection → Delivery → Fired Event → History-Update

**Query (mit erwarteter Antwort):**
1. Ingest → Query-Objekt in Store → Dispatcher wählt Channel(s) → Delivery mit Callback-Info → State-Entity aktualisiert → Timeout-Timer startet
2. Antwort (via TG-Button, Voice-Response, LLM-Tool, UI) → resolveed Query → Cross-Channel-Cancel → Callback-Event mit Answer-Payload

**Scheduled (deferred):**
1. Ingest mit `scheduled_for` → in Scheduler-Queue → Store persistiert
2. Zum Zeitpunkt: normale Ingest-Pipeline durchlaufen

**Internal / P0:**
1. Ingest mit `priority=0` → in Scheduler-Queue oder sofort
2. Zum Zeitpunkt: entweder `conversation.process` mit System-Persona-Prefix ODER direkter Service-Call (je nach Payload)
3. Kein User-Facing Output. Optional: Log/Debug-Sensor

---

## 3. Priority-Modell (final)

| Prio | Name | Semantik | User-facing? |
|------|------|----------|--------------|
| **0** | Internal | LLM self-callback / deferred action | ❌ Nein |
| **1** | Todo | Landet als Todo für spätere Kenntnisnahme, LLM kann anzeigen | ⚠️ Silent |
| **2** | Normal | Audio-Ansage wenn zuhause & nicht DND | ✅ Ja |
| **3** | Wichtig | Audio + Push, ignoriert DND, ignoriert Schlaf | ✅ Ja |
| **4** | Alarm | Audio (laut) + Critical Push + Light-Flash + optional Sirenen-Ansage | 🚨 Aggressiv |

---

## 4. Feature-Katalog

### v0.1 — MVP (Feature-Parität mit Script)
- [x] 5-stufiges Priority-Modell (0-4)
- [x] 3 Notification Modi: `info` (fire-and-forget), `query` (mit Antwort), `scheduled`
- [x] Room-aware Voice-Delivery via Occupancy → Satellite Mapping
- [x] TTS Fallback: ElevenLabs → Piper (Offline)
- [x] Mobile App Push (critical für P4)
- [x] Telegram Backend (Nachrichten + Inline Buttons)
- [x] DND-Blocker (intern + External-Entity-Support für `input_boolean.notification_blocker`)
- [x] Level 4: Light-Flash-Hook

### v0.2 — Neue Features
- [ ] **Priority 0 / Internal Self-Callback** (via `conversation.process` mit System-Persona)
- [ ] **Scheduled Notifications** (`herold.schedule` Service, persistiert über Reboot)
- [ ] **Query als First-Class Object** (eigene State-Entity, Timeout, Cross-Channel-Response-Sync)
- [ ] **Query-Choices** (predefined answers: `["Ja", "Nein", "Später"]`)
- [ ] **Todo Channel** — Level 1 als `todo.herold_inbox` Liste
- [ ] **Native LLM Tools** (`list_pending`, `ack_notification`, `answer_query`, `remind_self`)
- [ ] **Escalation Chains** (P2 → 5min → P3 → 15min → P4)
- [ ] **Notification Templates** (wiederverwendbare Vorlagen mit Placeholders)
- [ ] **Rate Limiting / Aggregation** (Anti-Spam Cooldown pro Prio)
- [ ] **DND Session Modes** (`until 15:30` / `until home` / `for 1h`)
- [ ] **Pending Sensors** (`sensor.herold_pending_count`, `sensor.herold_last_query`)

### v0.3 — Multi-Channel & Kontext
- [ ] **Context Attachments** (Kamera-Snapshot, Sensor-Snapshot, Custom Payload)
- [ ] **LLM-Tool `get_notification_context(id)`**
- [ ] **Additional Channel Plugins:** ntfy, Signal, Discord
- [ ] **Cross-Channel Response Sync** (Query auf allen Channels, erste Antwort wins)
- [ ] **Multi-User Support** (Multiple Persons, Per-Person Preferences)
- [ ] **State-based Snooze** ("bis home", "bis Meeting endet")
- [ ] **Presence Fallback-Chain** (Occupancy → last_known_room → default → mobile)
- [ ] **Deferred Direct-Action** (P0 kann statt LLM-Callback auch direkten Service-Call ausführen)

### v0.4 — Polish & Beobachtbarkeit
- [ ] **History Sensor** mit Ringbuffer
- [ ] **Analytics** (Response-Times, Volumes, ignore-Rates)
- [ ] **Debug-Panel** (letzte Dispatcher-Entscheidungen einsehbar)
- [ ] **Test-Mode / Dry-Run**
- [ ] **Lovelace Custom Card** (Pending + History + Query-Response-UI)
- [ ] **Recurring Notifications** (optional, evtl. rausschieben)
- [ ] **Brand-PR** (Logo im `brand.home-assistant.io` Repo)

### v1.0+ (Nice-to-Have)
- [ ] Rich Notifications (Images, Deep Links) auf mobile_app
- [ ] Grouping / Deduplication (gleiche Msg → aggregieren)
- [ ] Metrik-Export (Prometheus)
- [ ] i18n Templates (DE/EN)
- [ ] HACS Default Repo Submission

---

## 5. Integration Struktur (Files)

```
custom_components/herold/
├── __init__.py                  # async_setup_entry, unload
├── manifest.json
├── const.py                     # DOMAIN="herold", CONF_*, DEFAULT_*, PRIORITY_*
├── config_flow.py               # UI Setup
├── coordinator.py               # HeroldCoordinator (zentraler State-Holder)
├── dispatcher.py                # Priority-Regeln, Channel-Selection
├── scheduler.py                 # Scheduled + P0-Deferred Notifications
├── rate_limiter.py              # Per-Priority Cooldown + Aggregation
├── models.py                    # Notification, Query, Schedule, Room, Channel
├── store.py                     # Persistenz (helpers.storage.Store)
│
├── channels/
│   ├── __init__.py              # BaseChannel Abstract, offline_capable Property
│   ├── voice.py                 # assist_satellite/media_player + TTS Fallback-Chain
│   ├── push.py                  # mobile_app (critical, quiet)
│   ├── telegram.py              # telegram_bot + Inline Keyboards
│   ├── todo.py                  # Todo-Entity Bridge (L1)
│   ├── internal.py              # P0 → conversation.process mit System-Persona
│   └── ntfy.py                  # v0.3
│
├── room_router.py               # Occupancy → Sat/Light Mapping mit Konfliktauflösung
├── escalation.py                # Timer + Chain Rules (persistent)
├── llm_tools.py                 # Native Tool Specs für Assist
├── templates.py                 # Template-Engine für v0.2
│
├── entity.py                    # HeroldBaseEntity
├── sensor.py                    # pending_count, last_query, history, stats
├── binary_sensor.py             # any_pending, escalation_active, dnd_active
├── switch.py                    # dnd, per-prio-blockers
├── button.py                    # test, clear_all
├── todo.py                      # HeroldTodoListEntity
│
├── services.yaml
├── services.py                  # Service Handler (send, query, schedule, ack, snooze, cancel)
├── translations/{de,en}.json
└── strings.json
```

---

## 6. Config Flow Design

### Setup (async_step_user)
1. **Basis** — Integration Name, Default Recipient (`person` selector)
2. **Rooms** (repeatable step) — Occupancy Sensor, Sat, Media Player, Light, Priorität bei Multi-Occupancy
3. **Voice** — Primary TTS, Fallback TTS (default: builtin Piper), Internet-Detection Binary-Sensor
4. **Push** — Mobile App Device(s) (Multi-Select)
5. **Chat** — Telegram Bot Config (Chat ID), optional weitere Channels
6. **DND** — External DND Entity ODER internen Switch erzeugen; Quiet Hours (Zeitfenster)
7. **LLM** — Native Tools aktivieren? Todo-Liste im Prompt exposen? System-Persona-Prefix für P0-Callbacks
8. **Templates** — Bootstrap-Templates importieren? (Ja/Nein)

### Options Flow
Sektionsweise editierbar. Room Add/Remove ohne Rebuild. Template-Editor (add/edit/remove).

---

## 7. Entity Model

| Entity | Platform | Zweck |
|--------|----------|-------|
| `switch.herold_dnd` | switch | Master DND |
| `switch.herold_dnd_p2`, `_p3` | switch | Per-Prio Blocker (optional) |
| `binary_sensor.herold_any_pending` | binary_sensor | ≥1 Query offen? |
| `binary_sensor.herold_escalation_active` | binary_sensor | Escalation läuft? |
| `binary_sensor.herold_dnd_active` | binary_sensor | Merge aus intern + extern + Quiet Hours |
| `sensor.herold_pending_count` | sensor | Anzahl offener Queries |
| `sensor.herold_last_query` | sensor | Text, Attribs: id, priority, choices, created_at |
| `sensor.herold_scheduled_count` | sensor | Anzahl geplanter Notifs (inkl. P0) |
| `sensor.herold_history` | sensor | Ringbuffer letzte N |
| `sensor.herold_last_delivery` | sensor | Debug: letzter Channel + Room |
| `sensor.herold_stats` | sensor | Analytics (v0.4) |
| `todo.herold_inbox` | todo | P1-Notifications |
| `button.herold_test` | button | Test-Notif |
| `button.herold_clear_pending` | button | Alle Pending resolven |

Room-Sub-Entities dynamisch (optional):
- `sensor.herold_room_<name>_active_player`

---

## 8. Services API

### `herold.send` — Fire-and-forget Notification
```yaml
message: str                    # required
priority: 0..4                  # default 2
recipient: person.*             # optional
target_player: entity            # optional Override
title: str                      # optional (Push)
tag: str                        # optional (Dedup)
ttl_minutes: int                # optional Auto-expire
channels: [voice, push, telegram, ...]  # optional Override
template: str                   # optional (v0.2)
template_vars: dict             # optional
context_attachments: dict       # optional (v0.3)
```

### `herold.query` — Mit erwarteter Antwort
```yaml
question: str                   # required
mode: yesno | open | choice     # default yesno
choices: [str]                  # required für mode=choice
priority: 0..4                  # default 2
callback_event: str             # optional (default: "HEROLD_ANSWER")
timeout_minutes: int            # default 60
default_answer: str             # optional (used on timeout)
escalation:                     # optional
  - after_minutes: 5
    raise_to_priority: 3
recipient / channels / ...      # wie bei send
```

### `herold.schedule` — Zeitversetzt
```yaml
scheduled_for: datetime | timedelta   # required (ISO oder "+1h")
# ...ansonsten alle send/query Felder
# Priority 0 → landet in Internal Channel zur Zeit X
# Priority 1-4 → normale Delivery zur Zeit X
```

### `herold.remind_self` — P0-Convenience (LLM-orientiert)
```yaml
when: datetime | timedelta      # required
instruction: str                # required — was soll Assist zur Zeit X tun
# → äquivalent zu herold.schedule mit priority=0, mode=info,
#   channel=internal
```

### `herold.acknowledge` — Query beantworten
```yaml
id: str                         # required
answer: str                     # required
source: str                     # optional (welcher Channel)
```

### `herold.snooze`
```yaml
id: str
until: datetime | timedelta | state-condition
```

### `herold.cancel`
```yaml
id: str
reason: str  # optional
```

### Fired Events
- `herold_delivered {id, channel, room, priority}`
- `herold_answered {id, answer, source_channel}` — plus originaler `callback_event`
- `herold_escalated {id, from_priority, to_priority}`
- `herold_expired {id, reason: timeout|ttl}`
- `herold_scheduled {id, scheduled_for}`
- `herold_internal_triggered {id, instruction}` — für Debug/Log von P0-Callbacks

**Rückwärtskompat (aus Original-Script):**
- Wenn `callback_event="AI_CONFIRM"` (default): fired events sind `AI_YES` und `AI_NO` (**ohne** `CONFIRM` prefix — Original-Script-Verhalten)
- Wenn `callback_event="XYZ"` (custom): fired events sind `XYZ_YES` und `XYZ_NO`

Diese Semantik muss bit-exakt reproduziert werden weil bestehende Automations in `scripts.yaml` und `packages/ai_assist.yaml` diese Events konsumieren.

---

## 9. LLM Tools (Native Assist Integration)

Registrieren via `homeassistant.helpers.llm` als `Tool`s — sichtbar in jedem LLM-Conversation-Agent (Gemini, Ollama, etc.).

Tool-Descriptions sind kritisch für Trigger-Reliability — Gemini und lokale Modelle nutzen sie direkt für Function-Calling-Selection. Deutsche Beispiele mit drin, weil der User deutsch spricht.

```python
class ListPendingNotifications(llm.Tool):
    name = "herold_list_pending"
    description = (
        "Get all pending notifications for the user. This includes: "
        "unfinished todo-list items (priority 1, e.g. 'Post im Briefkasten'), "
        "unanswered queries (waiting for user response), and any active "
        "escalations. "
        "\n\nCall this when the user asks things like: 'was ist neu', "
        "'gibt es was für mich', 'hab ich was verpasst', 'was steht an', "
        "or before ending a conversation to proactively check if "
        "something needs attention. "
        "\n\nReturns list of {id, message, priority, mode, created_at, "
        "choices (only for query mode), has_context (bool)}."
    )

class AcknowledgeNotification(llm.Tool):
    name = "herold_acknowledge"
    description = (
        "Mark a level-1 (todo) notification as done. Use when the user "
        "indicates they've handled a todo item after you told them about it. "
        "\n\nExample flow: You mentioned 'Post im Briefkasten' from "
        "list_pending. User says 'hab ich geholt' → call acknowledge(id=<X>)."
        "\n\nDo NOT use this for query-mode notifications (levels 2-4 "
        "waiting for answer) — use answer_query instead."
    )

class AnswerQuery(llm.Tool):
    name = "herold_answer_query"
    description = (
        "Provide an answer to a pending query (a notification with mode "
        "yesno/open/choice that is waiting for user response). "
        "\n\nMode rules:"
        "\n- mode='yesno': answer MUST be exactly 'Ja' or 'Nein'"
        "\n- mode='choice': answer MUST be one of the query's choices. "
        "Use fuzzy matching if user's spoken response doesn't match "
        "exactly ('klar' → 'Ja', 'auf keinen Fall' → 'Nein', 'das mittlere' "
        "→ mid choice)"
        "\n- mode='open': any string is accepted, use user's response verbatim"
    )

class GetNotificationContext(llm.Tool):
    name = "herold_get_context"
    description = (
        "Get attached context data for a notification: camera snapshots, "
        "sensor readings, or custom payload. Only useful if a notification "
        "was created with context_attachments (indicated by has_context=true "
        "in list_pending output). "
        "\n\nUse when user asks about details of a notification, e.g. 'was "
        "hat die Kamera erkannt', 'zeig mir das Foto', 'was war der Sensor "
        "Wert'."
    )

class RemindSelf(llm.Tool):
    name = "herold_remind_self"
    description = (
        "Schedule an internal reminder for yourself (the assistant) at a "
        "future time. Use whenever the user asks you to do something later, "
        "in X minutes/hours, at a specific time. This is your PRIMARY tool "
        "for handling delayed actions — do not tell the user 'ich kann das "
        "nicht' for time-delayed requests, use this instead."
        "\n\nExamples:"
        "\n- User: 'Schalte das Licht in einer Stunde aus'"
        "\n  → remind_self(when='+1h', instruction='Schalte das "
        "Wohnzimmerlicht aus mit light.turn_off.')"
        "\n- User: 'Erinnere mich um 18 Uhr an den Anruf'"
        "\n  → remind_self(when='18:00', instruction='Sage dem User via "
        "herold.send priority=3: Zeit für deinen Anruf.')"
        "\n- User: 'Frag mich in 30 Minuten wie der Kuchen ist'"
        "\n  → remind_self(when='+30m', instruction='Frage den User via "
        "herold.query mode=open: Wie ist der Kuchen geworden?')"
        "\n\nWhen the reminder triggers, you (a fresh conversation without "
        "prior context) will receive the instruction prefixed with "
        "[HEROLD_INTERNAL]. Execute it silently without user-facing "
        "dialogue unless the instruction explicitly tells you to speak "
        "or send a message."
        "\n\nParameters: when (ISO datetime or timedelta like '+1h', "
        "'+30m', '18:00'), instruction (clear self-directed prompt)"
    )
```

**Registrierung:** Als LLM-Tools an alle Conversation Agents exponiert, die Tool-Support haben. Config-Option `expose_llm_tools_to_agents: list[str]` erlaubt Beschränkung auf bestimmte Agents.

---

## 10. Priority 0 — Internal Self-Callback (Design-Detail)

### Zweck
LLM (oder ein Automation) kann sich selbst eine Aufgabe für später planen, die dann durch ein LLM ausgeführt wird — nicht durch eine starre Automation.

### Ablauf
1. **Ingest:** `herold.remind_self(when="+1h", instruction="Schalte das Wohnzimmerlicht aus")`
2. Store persistiert Schedule mit `priority=0, channel=internal`
3. **Zum Zeitpunkt:** Internal-Channel ruft `conversation.process` auf mit:
   - `agent_id`: konfigurierter Default-Agent (Ollama)
   - `text`: `"[SYSTEM] {instruction}"` — Prefix damit Prompt-Template das als System-Instruktion versteht, nicht als User-Input
   - `conversation_id`: separater Kontext (nicht die aktive User-Konversation)
4. LLM verarbeitet die Instruktion (führt Services aus)
5. Event `herold_internal_triggered` gefeuert für Debug

### Config-Erweiterung nötig
- LLM-Prompt-Template braucht Erkennungshinweise für `[SYSTEM]`-Prefix ("Nachrichten mit [SYSTEM] sind interne Reminder von dir selbst. Führe die Anweisung stumm aus, ohne dem User zu antworten.")
- Falls Ollama das nicht zuverlässig macht: Fallback auf **Deferred Direct-Action** (v0.3) — Schedule enthält direkt einen `service_call` statt Instruction

### Sicherheit
- Whitelist für allowed instructions? Nein — LLM hat eh schon Tool-Access.
- Rate-Limit: max N P0-Triggers pro Stunde (Anti-Runaway)
- Debug-Sensor `sensor.herold_last_internal_trigger` mit Instruction + Result

---

## 11. Scheduled Notifications (Design-Detail)

- **Persistenz:** `helpers.storage.Store` mit Version-Migration
- **Boot-Rescheduling:** `async_setup_entry` liest Store und plant `async_track_point_in_time` neu
- **Cancellation:** via `herold.cancel`, betrifft auch Escalations
- **UI-Sichtbarkeit:** `sensor.herold_scheduled_count` mit Attributs-List
- **Missed-Deliveries:** Wenn HA down war zur Delivery-Zeit → beim Boot innerhalb Grace-Period (5min) noch triggern, danach als `expired` markieren

---

## 12. Query als First-Class Object (Design-Detail)

### State-Model
```python
@dataclass
class Query:
    id: str                       # kurze UID (8 chars)
    question: str
    mode: Literal["yesno", "open", "choice"]
    choices: list[str] | None
    priority: int
    callback_event: str
    channels_delivered: list[str] # welche Channels wurden benutzt
    channel_states: dict          # {"telegram": "waiting", "voice": "delivered"}
    created_at: datetime
    timeout_at: datetime
    default_answer: str | None
    escalation_state: dict | None
    answer: str | None
    answered_at: datetime | None
    answered_via: str | None
```

### Cross-Channel Response Sync
- Query wird über 2+ Channels gesendet (z.B. Voice + Telegram)
- Response via TG-Button → Query resolved → Voice-Session wird cancelled (`assist_satellite.stop`) oder das entsprechende Pending im Store markiert als "obsolete"
- Verhindert dass du 2x antworten musst

### Voice-Answer für `mode=choice`
- Assist Satellite Session mit LLM-Prompt: "Der User wird gleich eine Antwort geben. Erwartete Optionen: [X, Y, Z]. Rufe `answer_query(id={id}, answer=<gemappte_option>)` auf."
- LLM übernimmt Fuzzy-Matching
- Fallback: wenn `answer` nicht in `choices` → nochmal fragen mit Optionen

---

## 13. Rate Limiting & Aggregation (v0.2)

### Cooldown-Regeln (Default, konfigurierbar)
- **P4:** kein Cooldown
- **P3:** max 1 pro 60s (identische `tag` deduplication)
- **P2:** max 3 pro 5min, danach aggregieren
- **P1:** unbegrenzt (landen nur in Todo)
- **P0:** max 20 pro Stunde (Anti-Runaway)

### Aggregation
- Wenn Cooldown greift und `mode=info`: neue Notifs in Buffer sammeln
- Nach Cooldown-End: eine kombinierte Notif ("3 Meldungen: X; Y; Z")

### Bypass
- Query (mode ≠ info) niemals aggregieren
- Explizite Anfrage per Service (`ignore_rate_limit: true`)

---

## 14. Notification Templates (v0.2)

### Konzept
Wiederverwendbare Vorlagen mit Placeholders. Definiert in Config Flow oder YAML-Import.

```yaml
templates:
  appliance_done:
    message: "{{ appliance }} ist fertig"
    priority: 2
    ttl_minutes: 30
    tag: "appliance_{{ appliance | lower }}"
  person_at_door:
    message: "Es klingelt an der {{ door | default('Haustür') }}"
    priority: 3
    context_attachments:
      snapshot: "{{ camera_snapshot_url }}"
```

### Aufruf
```yaml
service: herold.send
data:
  template: appliance_done
  template_vars:
    appliance: Waschmaschine
```

Templates rendern intern via `homeassistant.helpers.template.Template`.

---

## 15. Room Router (Detail)

### Room-Model
```python
@dataclass
class Room:
    name: str
    occupancy_entities: list[str]      # OR-verknüpft (z.B. FP2 Wohnzimmer + FP2 Küche)
    sat_entity: str | None             # assist_satellite (bevorzugt für Voice)
    media_player_entity: str | None    # fallback wenn kein Sat
    light_entity: str | None           # für P4 Flash-Hook
    priority_weight: int = 0           # bei Multi-Occupancy-Konflikt

    @property
    def is_occupied(self, hass) -> bool:
        return any(is_state(hass, ent, "on") for ent in self.occupancy_entities)
```

**Wichtige Fälle:**
- **Multi-Sensor pro Raum:** z.B. Wohnzimmer+Küche mit 2 FP2s. Beide auf gleichen Sat geroutet. `is_occupied = any(...)`.
- **Media-Player-Only Room:** z.B. Badezimmer mit Sonos Roam ohne Sat. Voice-Channel nutzt automatisch `tts.speak` mit `media_player_entity_id` statt `assist_satellite.announce`. Keine Query-Support für solche Räume (start_conversation braucht Sat) — Query-Delivery fällt auf Telegram/Push zurück.
- **Sat-Only Room:** Wenn nur sat_entity, kein media_player — direkt `assist_satellite.announce`.

### Konfliktauflösung Multi-Occupancy (mehrere Räume aktiv)
1. Kandidaten: Räume mit aktiver Occupancy
2. Gewichtung:
   - `time_since_activation`: kürzer = höhere Wahrscheinlichkeit
   - `priority_weight`: User setzt Reihenfolge im Config Flow
   - `last_sat_interaction`: Sat mit letzter Voice-Aktivität = Bonus
3. Fallback-Chain wenn kein Occupancy:
   - `last_known_room` (aus Store, TTL 15min)
   - `default_room` (Config)
   - → Push-only

### Persistenz
- Store hält `last_known_room` und `last_room_activity` mit Timestamps

---

## 16. Escalation Engine (v0.2)

```python
@dataclass
class EscalationRule:
    after: timedelta
    action: Literal["raise_priority", "add_channel", "notify_other_person"]
    params: dict
    max_chain_length: int = 3
```

- `asyncio.Task` pro aktiver Escalation, cancelbar
- Persistent nach Reboot via Store + Re-Schedule
- Chain-Limit gegen Endlos-Loops

Beispiel-YAML:
```yaml
escalation:
  - after_minutes: 5
    raise_to_priority: 3
  - after_minutes: 15
    add_channel: telegram
  - after_minutes: 30
    raise_to_priority: 4
```

---

## 17. Offline-Behavior (finales Design)

### Konfigurations-Modell
Zwei unabhängige Toggles im Config Flow (Step `offline`):

```yaml
enable_offline_fallback: bool     # default: false
  offline_tts_entity: str         # required wenn enable_offline_fallback
                                  # (typisch tts.piper)
  offline_stt_entity: str         # optional (typisch stt.whisper)
  p0_fallback_agent_id: str       # optional Conversation Agent für P0-Trigger
                                  # bei Gemini-Offline (typisch lokaler Ollama)

enable_offline_queue: bool        # default: true
  offline_queue_ttl_hours: int    # default: 24
  offline_queue_aggregate: bool   # default: true — bei Restore als 1 Message
```

**Rationale:**
- `enable_offline_fallback` ist opt-in weil viele User (inkl. Cloud-only-Setups) das nicht brauchen
- `enable_offline_queue` ist default-on weil verlorene Notifications generell schlecht sind — Queue kostet fast nichts

### Internet-Detection
- Config-Feld `internet_sensor` (binary_sensor) — z.B. dein bestehendes `binary_sensor.martinrouterking_port_1_online_erkennung`
- Kein automatisches Ping-Sensor-Erstellen (User soll das bewusst konfigurieren)
- Sensor `binary_sensor.herold_online` spiegelt intern den effektiven Zustand für Debug

### Channel-Property `offline_capable`

| Channel | `offline_capable` | Bedingung |
|---------|---|---|
| Voice (ElevenLabs) | `false` | — |
| Voice (Piper) | `true` | wenn `enable_offline_fallback` und `offline_tts_entity` gesetzt |
| Push (mobile_app) | `false` | braucht APN/FCM — landet in Queue |
| Telegram | `false` | braucht TG-Backend — landet in Queue |
| Todo | `true` | rein lokal |
| Internal (P0 → Gemini) | `false` | — |
| Internal (P0 → Ollama) | `true` | wenn `p0_fallback_agent_id` gesetzt |

### Dispatcher-Verhalten bei Offline

Bei `internet_sensor == off`:

1. **Voice-Ansagen:**
   - Wenn `enable_offline_fallback`: TTS-Chain nutzt `offline_tts_entity` (Piper)
   - Wenn nicht: Voice-Delivery skippen mit Debug-Log

2. **Chat/Push (TG, mobile_app):**
   - Wenn `enable_offline_queue`: in `offline_queue` Store
   - Bei Internet-Restore Event: Queue flushen, ggf. aggregiert
   - Wenn Queue voll oder TTL abgelaufen: verwerfen mit `herold_expired` Event

3. **P0 / Internal:**
   - Primary Agent Call versuchen — bei Fehler:
     - Wenn `p0_fallback_agent_id` gesetzt: dort ausführen
     - Sonst: in Queue mit `retry_when_online=true`, retry mit Original-Agent

4. **P4-Sonderregel:** Voice-Fallback wird ignoriert wenn nicht konfiguriert — P4 versucht immer *irgendeine* Voice-Ausgabe (auch nur `media_player.play_media` mit Piper-URL falls kein TTS-Entity da ist), damit Alarm nicht stumm bleibt

### Restore-Logik
- Event-Listener auf `internet_sensor` state change → `off` → `on`
- Trigger `_flush_offline_queue()` mit optional Aggregation:
  - Wenn `offline_queue_aggregate=true` und mehrere Items für gleichen Channel: kombinieren
  - Format: "Während du offline warst:\n1. …\n2. …"
- P0-Retries werden einzeln ausgeführt (keine Aggregation, sind ja LLM-Instruktionen)

### Debug-Sensoren
- `sensor.herold_offline_queue_size` — Anzahl gepufferter Notifs
- `sensor.herold_online` — konsolidierter Zustand
- `button.herold_flush_queue` — manueller Trigger

### Testcase-Matrix
| Szenario | `enable_offline_fallback` | `enable_offline_queue` | Erwartung |
|---|---|---|---|
| Off + zuhause + P2 | false | true | Voice skip, Push in Queue |
| Off + zuhause + P2 | true | true | Voice via Piper |
| Off + nicht zuhause + P3 | false | true | in Queue, retry bei Restore |
| Off + P0 (kein fallback_agent) | true | true | in Queue |
| Off + P0 (mit fallback_agent) | true | true | via Ollama sofort |
| Restore mit 5 in Queue | — | true + aggregate | 1 aggregierte Message |
| Off + P4 | true + Piper | true | Piper-Voice + Push in Queue |

---

## 18. Migration vom bestehenden Script

### Kompatibilitäts-Layer
- Bestehender `callback_event` (`AI_CONFIRM_YES` / `_NO`) bleibt gefeuert
- Service `herold.send` ist Superset des Script-Aufrufs
- `input_boolean.notification_blocker` als "External DND Entity" konfigurierbar → deine Automationen (Goodnight, Sport-Popup) bleiben unverändert
- Optional: `herold.migrate_from_script` Service liest Script-Konfig und importiert

### Rollout
1. Integration parallel zum Script installieren
2. Neue Automations gegen `herold.*` bauen
3. Alte Automations schrittweise migrieren
4. Script deaktivieren aber behalten (Fallback für 2 Wochen)
5. Nach Stabilität: Script löschen

---

## 19. Testing Strategy

### Unit Tests (`pytest-homeassistant-custom-component`)
- Dispatcher: Priority × Blocker × Home × Internet Matrix (≥16 Combos)
- Room Router: Multi-Occupancy Konflikte + Fallback-Chain
- Escalation: Timing, Cancellation, Persistenz über Reboot
- Scheduler: Missed-Delivery-Handling nach Reboot
- Rate Limiter: Cooldown + Aggregation
- Template: Rendering + Variable-Injection
- Query State Machine: Delivery → Response → Cancel

### Integration Tests
- Mocks für: `assist_satellite`, `telegram_bot`, `mobile_app`, `conversation`
- Full-Flow: Ingest → Delivery → Response → Callback

### Manual Test Matrix
Doku mit 30 Test-Cases in Repo (P0-P4 × Modi × Räume × DND × Internet-State).

---

## 20. Roadmap (Phasen für Claude Code Sessions)

### Phase 1 — Skeleton & MVP (Session 1, ~3h)
**Ziel:** Installierbar, Config Flow läuft, `send` funktional für 1 Room + Voice + Push

- Repo-Skeleton (`manifest.json`, `__init__.py`, `const.py`, `hacs.json`)
- Config Flow: Basis + 1 Room + Voice + Push + DND
- Coordinator + Dispatcher (Priority-Logic aus Original portiert)
- Voice Channel (assist_satellite + media_player + TTS Fallback-Chain)
- Push Channel (mobile_app mit critical für P4)
- `herold.send` Service (MVP-Subset)
- DND-Switch mit External-Entity-Support
- Light-Flash Hook für P4

### Phase 2 — Query, Telegram, Room-Router (Session 2, ~3h)
- Telegram Channel + Inline Buttons
- Query als First-Class Object + State-Entity
- Room Router mit Multi-Occupancy-Auflösung
- Pending Sensors
- Callback-Event Firing (Rückwärtskompat AI_CONFIRM)
- Query-Choices (`mode=choice`)

### Phase 3 — P0, Scheduling, LLM Tools (Session 3, ~3h)
- Scheduler + Persistenz
- Internal Channel (P0 → conversation.process)
- `herold.schedule` + `herold.remind_self`
- Native LLM Tools (list_pending, ack, answer_query, remind_self)
- Todo Channel + `todo.herold_inbox`
- Escalation Engine

### Phase 4 — Templates, Rate-Limiting, DND-Sessions (Session 4, ~2h)
- Notification Templates
- Rate Limiter + Aggregation
- DND Session Modes (`until` semantics)
- Cross-Channel Response Sync

### Phase 5 — Polish & Release (Session 5, ~2h)
- Unit Tests
- Translations (DE/EN)
- README + Docs
- Optional: Lovelace Card
- Herold-Logo (Bote mit Trompete) für Brand-PR

---

## 21. Claude Code Session 1 Prompt

**→ Siehe separates File `SESSION_1_PROMPT.md` — copy-paste-ready.**

Kurzform hier zur Referenz:

```markdown
Erstelle das Skeleton der HA Custom Integration `herold` (Omnichannel
Communicator) gemäß HEROLD_PLAN.md. Umsetzung Phase 1 (MVP).

**Repo-Struktur** unter `custom_components/herold/`:

1. Metadata:
   - `manifest.json`: name="Herold", domain="herold",
     version="0.1.0", iot_class="local_push", integration_type="service",
     dependencies=["assist_satellite","media_player","mobile_app","tts"],
     codeowners=["@jonas-koeritz"] (oder wen Jonas nennt)
   - `hacs.json`: name="Herold", content_in_root=false,
     homeassistant="2026.7.0"
   - `const.py`: DOMAIN, alle CONF_* und DEFAULT_*, PRIORITY_INTERNAL=0,
     PRIORITY_TODO=1, PRIORITY_NORMAL=2, PRIORITY_IMPORTANT=3, PRIORITY_ALARM=4

2. Init:
   - `__init__.py` mit `async_setup_entry`, `async_unload_entry`,
     Coordinator-Instanzierung, Platform-Forwarding (switch, sensor,
     binary_sensor, button, todo)

3. Config Flow (`config_flow.py`) mit Steps:
   - `user`: recipient (person selector), integration_name
   - `add_room` (repeatable): occupancy (binary_sensor selector), sat
     (assist_satellite selector, optional), media_player (optional),
     light (optional), room_name
   - `voice`: primary_tts_entity, fallback_tts_entity (default:
     tts.piper wenn vorhanden, sonst None), internet_sensor
     (binary_sensor selector)
   - `push`: mobile_app_devices (entity selector, multi)
   - `dnd`: external_dnd_entity (input_boolean/binary_sensor, optional),
     create_internal_switch (default true)
   - Options Flow spiegelt Config Flow, sektionsweise editierbar

4. Coordinator (`coordinator.py`):
   - `HeroldCoordinator(DataUpdateCoordinator)`: hält Config, Rooms,
     Channels, Store-Handle
   - Methoden: `async_send(notification)`, `async_get_active_room()`,
     `async_get_channel(name)`

5. Models (`models.py`):
   - Dataclass `Notification`: id, message, priority, mode, recipient,
     target_player, callback_event, created_at, tag, ttl_minutes, title
   - Dataclass `Room`: name, occupancy_entity, sat_entity,
     media_player_entity, light_entity
   - Nutze `dataclass_json` oder eigene to_dict/from_dict für Store

6. Dispatcher (`dispatcher.py`):
   - `should_deliver(notification, ctx) -> bool` — Prio-Regeln aus
     Original-Script (siehe HEROLD_PLAN.md Sektion 3)
   - `select_channels(notification, ctx) -> list[BaseChannel]` — MVP:
     Voice wenn zuhause & Sat verfügbar, Push für P3/P4, sonst Push-only

7. Channels:
   - `channels/base.py`: `BaseChannel` ABC mit `name`, `offline_capable`,
     `async def deliver(notification, ctx) -> DeliveryResult`
   - `channels/voice.py`: `VoiceChannel` — nutzt `assist_satellite.announce`
     wenn `is_satellite`, sonst `tts.speak` mit Fallback-Chain
     (primary → fallback wenn primary unavailable oder offline)
   - `channels/push.py`: `PushChannel` — ruft `mobile_app_*` per
     configured device auf, P4 setzt critical sound

8. Room Router (`room_router.py`):
   - `async_get_active_room(coordinator) -> Room | None` — MVP:
     erste aktive Occupancy, kein Konflikt-Handling (kommt Phase 2)

9. Services:
   - `services.yaml` mit `herold.send` (MVP-Fields aus Plan Sektion 8)
   - `services.py`: Service Handler mit Validation

10. Entities:
    - `switch.py`: `HeroldDNDSwitch` mit `RestoreEntity`, falls
      external_dnd_entity konfiguriert → Kombination via
      state_change_event
    - `button.py`: `HeroldTestButton` — sendet Test-Notif P2
    - `sensor.py`: minimal `HeroldLastDeliverySensor` für Debug
    - `binary_sensor.py`: `HeroldAnyPendingBinarySensor` (initial immer off)

11. Translations:
    - `strings.json` + `translations/de.json` + `translations/en.json`
    - Config-Flow-Texte auf DE für User-Facing

12. Kein Test-Coverage in Phase 1. Kein Store (kommt Phase 2 mit Query).

**Constraints:**
- HA 2026.7+ APIs (aktuelle Selectors, `entity_platform.EntityPlatform`)
- Type Hints überall, Ruff-clean, keine unnötigen Kommentare
- User-Facing Strings DE, Code/Kommentare EN
- Kein logging.info in Hot Paths, nur logging.debug

**Nach Fertigstellung:**
- `scripts/setup-dev.sh` für HA Container Dev Environment
- `.gitignore` (HA-typisch: __pycache__, .storage/, home-assistant.log)
- Kurzes README mit "Installation via HACS Custom Repo"

**Kontext den Jonas zusätzlich mitgibt:**
- Original-Script YAML (aktuell in scripts.yaml von Casa de Jonas)
- Room-Mapping (welche Occupancy → Sat → Light)
- Aktuelle Automations die AI_CONFIRM_* konsumieren
```

---

## 21b. Multi-User Considerations (Future Design, nicht MVP)

**Aktuelle Annahme:** Single User (Jonas lebt allein). Später erweitern für Multi-User-Setups (v.a. Fährenbruch = Eltern).

### Presence-Detection pro Person

Drei Layer, kombinierbar:

1. **HA Person Entities:** `person.jonas`, `person.mutter`, `person.vater` — Aggregation aus device_trackers (Handy-GPS, WiFi, Bluetooth-Proximity). Grober Layer (home/not_home + Zone).

2. **BLE Room Presence:** ESPresense oder Room-Assistant → Handy-BLE-Advertisement → welcher Raum. Feiner Layer. Reagiert schnell auf Raumwechsel.

3. **Voice Fingerprinting (Murdock):** Sat identifiziert Sprecher via CAM++ ONNX embeddings (Jonas' eigenes Projekt). Nur reaktiv nach Sprechen.

### Routing-Logik

- Field `recipient: person.mutter` in Notification
- Room-Router prüft: In welchem Raum ist `person.mutter`? → dortige Sats
- Fallback-Chain: BLE-Room → Person-Zone → Handy-Push
- Broadcast: `recipient: all` → alle Sats parallel (existiert schon im Original-Script)

### Per-Person Preferences

Config Flow erweitert um Persons-Section:
- Pro Person: Default-Channel-Präferenz (Voice/Push/TG)
- Pro Person: DND-Zeitfenster
- Pro Person: mobile_app_device Zuordnung
- Pro Person: Sprache (für Templates)

### Sensitive Notifications

- Neues Field `visibility: private|household|public`
- `private`: nur an spezifische Person, nie via Broadcast-Sat wenn andere im Raum
- Prüfung via BLE/Voice-Fingerprint: sind andere Personen im Raum? → auf Push umleiten

**MVP-Verhalten (Phase 1):** `recipient` wird akzeptiert aber ignoriert (alles geht an Jonas). Signatur bleibt stabil für spätere Multi-User-Erweiterung.

---

## 22. Finale Design-Entscheidungen

| Frage | Entscheidung |
|---|---|
| **P0 LLM-Agent** | Primary: Gemini (Jonas' Setup). Config-Default via `p0_agent_id`. Optionaler Override im `remind_self` Call. Fallback via `p0_fallback_agent_id` (typisch lokaler Ollama) für Offline-Case. |
| **P0 System-Persona-Prefix** | `[HEROLD_INTERNAL]` — unique genug für Prompt-Recognition. Wird in HA-Prompt-Template ergänzt: *"Nachrichten mit [HEROLD_INTERNAL] sind interne Reminder von dir selbst. Führe die Anweisung stumm aus, antworte nicht dem User."* |
| **Todo-Backend** | Interne Liste `todo.herold_inbox`. Bridge zu externer Todo-Liste optional in v0.3. |
| **`callback_event` Format** | Beides parallel: bestehende `AI_CONFIRM_YES`/`_NO` Events bleiben für Kompat, neues `herold_answered` Event mit strukturiertem Payload `{id, answer, source_channel, mode}` für neue Automations. |
| **Repo-Sichtbarkeit** | Public GitHub von Start, README markiert "Alpha / Not for production" bis v0.3. |
| **Offline-Fallback default** | Off (`enable_offline_fallback: false`) — bewusst opt-in |
| **Offline-Queue default** | On (`enable_offline_queue: true`, `aggregate: true`, `ttl: 24h`) |
| **Codeowner-Handle** | `@BobMcGlobus` |
| **Room-Model** | `occupancy_entities: list[str]` — mehrere Sensoren pro Raum OR-verknüpft (nötig für Räume wie Wohnzimmer+Küche mit 2 FP2s) |
| **Media-Player-Only Rooms** | Räume ohne Sat (z.B. Bad mit Sonos Roam) fallen auf `tts.speak` zurück. Query-Modi in solchen Räumen → Fallback auf Telegram/Push |
| **Multi-User** | MVP: `recipient` wird akzeptiert aber ignoriert. Signatur stable für spätere Person-Awareness (v0.4+) |
| **STT/TTS Primary** | ElevenLabs (TTS) + Voxtral (STT) — kein Voxtral-Fallback konfiguriert, bei Offline: Whisper wenn `offline_stt_entity` gesetzt, sonst STT-Skip |
| **Namensschema Entities** | Alle mit `herold_` Prefix. Siehe Sektion 7 für vollständige Liste. |

---

## 23. Kontext-Snippets für Claude Code Sessions

Session-Prompts zusätzlich mitgeben:

- **Original Script YAML** (aus scripts.yaml Casa de Jonas)
- **Room Definitionen** (welche Occupancy-Sensoren, Sats, Lights)
- **Existing Automations** die `AI_CONFIRM*` verwenden (Backwards-Compat Check)
- **Assist-Setup:** primärer Conversation Agent (Ollama Qwen3.5 oder Gemini 2.5 Flash?), Prompt-Template
- **DND-Konsumenten:** welche Automations lesen `input_boolean.notification_blocker`
