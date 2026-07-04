# Herold 📯

> **⚠️ Alpha — Not for production.** Diese Integration ist in aktiver Entwicklung (Phase 1 / MVP). API und Config-Format können sich noch ändern.

**Herold** ist eine Home Assistant Custom Integration für priorisierte Omnichannel-Benachrichtigungen: raumbewusste Sprachausgabe über Assist-Satelliten und Media Player, Push auf die Mobile App, mit DND-Logik, Offline-TTS-Fallback und einem 5-stufigen Prioritätsmodell.

Herold ist der Nachfolger des Scripts `System: Universal Omnichannel Communicator (Priority Edition)` — als wartbare, testbare Integration mit UI-Konfiguration.

## Voraussetzungen

- **Home Assistant 2026.7.0 oder neuer**
- Mindestens ein Assist-Satellit **oder** Media Player mit TTS
- Optional: Mobile App (für Push), Präsenzsensoren (für Raumerkennung)

## Installation via HACS (Custom Repository)

1. HACS öffnen → Menü (⋮ oben rechts) → **Benutzerdefinierte Repositories**
   *(Screenshot-Platzhalter)*
2. Repository-URL eintragen: `https://github.com/BobMcGlobus/herold`, Typ: **Integration**
   *(Screenshot-Platzhalter)*
3. „Herold" in HACS suchen und installieren
4. Home Assistant neu starten
5. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Herold**
   *(Screenshot-Platzhalter)*

## Einrichtung (Config Flow)

Der Config Flow führt durch sechs Schritte:

1. **Grundlagen** — Empfänger-Person, Name der Instanz
2. **Räume** (wiederholbar) — pro Raum: Präsenzsensoren (mehrere möglich, ODER-verknüpft), Assist-Satellit und/oder Media Player, optional Licht für den P4-Alarm-Flash
3. **Sprache** — primäres TTS (z.B. ElevenLabs), optionales Fallback-TTS (z.B. Piper), Internet-Erkennungssensor
4. **Push** — Mobile-App-Notify-Entitäten
5. **Chat** — optionale Telegram-Chat-ID für Nachrichten und Antwort-Buttons, optionaler Pending-Question-Helper (Legacy-Kompat für offene Fragen)
6. **Nicht stören** — optionale externe DND-Entität, interner DND-Schalter
7. **Offline** — Offline-TTS-Fallback (opt-in), Offline-Warteschlange (spätere Phase)

Alle Sektionen sind später über die Integrations-Optionen editierbar; Räume können ohne Neueinrichtung hinzugefügt, bearbeitet und entfernt werden.

## Feature-Matrix

| Feature | Status |
|---|---|
| `herold.send` Service (P0–P4) | ✅ Phase 1 |
| Raumbewusste Voice-Delivery (Occupancy → Satellit) | ✅ Phase 1 |
| Multi-Occupancy-Sensoren pro Raum (ODER-verknüpft) | ✅ Phase 1 |
| Media-Player-Only-Räume (`tts.speak` Fallback) | ✅ Phase 1 |
| TTS-Kette: Primär → Offline-Fallback (z.B. ElevenLabs → Piper) | ✅ Phase 1 |
| Mobile App Push (critical Sound für P4) | ✅ Phase 1 |
| DND-Schalter + externe DND-Entität | ✅ Phase 1 |
| `herold.query` — Fragen mit Antwort (yesno / open / choice) | ✅ Phase 2 |
| Telegram-Channel mit Inline-Buttons (legacy-kompatibel) | ✅ Phase 2 |
| Query-Persistenz über Neustarts, Timeout + default_answer | ✅ Phase 2 |
| Multi-Occupancy-Konfliktauflösung (Gewicht + Aktualität) | ✅ Phase 2 |
| Last-Known-Room-Fallback (TTL 15 min) | ✅ Phase 2 |
| P4 Alarm-Blinken: mehrere Lichter und Szenen pro Raum | ✅ Phase 2 |
| Pending-Sensoren (`pending_count`, `last_query`, `any_pending`) | ✅ Phase 2 |
| `herold.schedule` + `herold.remind_self` (persistiert über Neustarts) | ✅ Phase 3 |
| P0 Internal Channel (LLM-Self-Callback via `conversation.process`) | ✅ Phase 3 |
| Native LLM-Tools (`list_pending`, `acknowledge`, `answer_query`, `remind_self`) | ✅ Phase 3 |
| Todo-Inbox `todo.herold_eingang` für P1-Benachrichtigungen | ✅ Phase 3 |
| Escalation-Chains für unbeantwortete Fragen | ✅ Phase 4 |
| Voice-Timeout: Buttons gehen nach Telegram, wenn niemand antwortet | ✅ Phase 4 |
| Rate-Limiting + P2-Aggregation (Anti-Spam) | ✅ Phase 4 |
| DND-Sessions (`until`, `until_home`) | ✅ Phase 4 |
| Benachrichtigungs-Vorlagen mit Jinja-Platzhaltern | ✅ Phase 4 |
| pytest-Suite (Dispatcher, Router, Legacy-Kompat, Limiter, …) | ✅ Phase 5 |
| Dashboard-Karte (Inbox / Geplant / Logbuch) + Verlauf-Sensor | ✅ v0.6.0 |
| Offline-Queue, Multi-User | 🔜 Backlog |

Die vollständige Roadmap steht in [HEROLD_PLAN.md](HEROLD_PLAN.md).

## Service: `herold.send`

```yaml
service: herold.send
data:
  message: "Die Waschmaschine ist fertig"
  priority: 2          # 0 intern · 1 todo · 2 normal · 3 wichtig · 4 alarm
  # title: "Optionaler Push-Titel"
  # target_player: assist_satellite.wohnzimmer_sattelite_assist_satellit
  # tag: waschmaschine
  # ttl_minutes: 30
  # callback_event: AI_CONFIRM
```

## Service: `herold.query`

```yaml
service: herold.query
data:
  question: "Soll ich das Licht ausschalten?"
  mode: yesno          # yesno · open · choice
  # choices: ["Pizza", "Pasta", "Salat"]   # nur für mode: choice
  priority: 2
  timeout_minutes: 60
  # default_answer: "Nein"   # wird beim Timeout automatisch verwendet
  # callback_event: AI_CONFIRM
```

Antwortwege: Satelliten-Konversation (`start_conversation`), Telegram-Inline-Buttons, Freitext im Telegram-Chat (open), oder `herold.acknowledge` (id + answer). Offene Fragen überleben HA-Neustarts. Bei Antwort feuert `herold_answered` mit strukturiertem Payload — bei yesno zusätzlich das Legacy-Event (`AI_YES`/`AI_NO` bzw. `<custom>_YES`/`_NO`).

## Services: `herold.schedule` & `herold.remind_self`

```yaml
service: herold.schedule
data:
  scheduled_for: "+1h30m"       # auch "18:00" oder ISO-Datum
  message: "Ofen vorheizen nicht vergessen"
  priority: 2
```

```yaml
service: herold.remind_self     # P0-Convenience für den Assistenten
data:
  when: "+30m"
  instruction: "Frage den User via herold.query: Wie ist der Kuchen geworden?"
```

Geplante Benachrichtigungen überleben Neustarts; während einer Downtime verpasste Zustellungen werden innerhalb von 5 Minuten nachgeholt, ältere als `herold_expired` markiert. P0-Instruktionen laufen mit `[HEROLD_INTERNAL]`-Prefix durch den konfigurierten Conversation-Agent (Optionen → LLM), mit Fallback-Agent und Anti-Runaway-Limit (max. 20/Stunde).

## LLM-Tools

Herold registriert eine LLM-API namens **Herold** — aktivierbar pro Conversation-Agent unter *Sprachassistenten → Agent → LLM-APIs*. Tools: `herold_list_pending` („was ist neu?"), `herold_acknowledge` (Todo erledigt), `herold_answer_query` (Antwort auf offene Frage, inkl. Fuzzy-Matching), `herold_remind_self` (zeitversetzte Aufgaben).

### System-Prompt-Vorlage (copy-paste in die Agent-Anweisungen)

```yaml
# In den Optionen des Conversation-Agents unter "Anweisungen" ergänzen:

## Herold — Benachrichtigungssystem des Hauses

Du hast Zugriff auf die Herold-Tools (LLM-API "Herold" muss aktiviert sein):

- Nutze `herold_list_pending`, wenn der User fragt "was ist neu", "gibt es
  was für mich", "hab ich was verpasst" — und proaktiv am Gesprächsende,
  wenn etwas offen sein könnte.
- Nutze `herold_remind_self` für ALLE zeitversetzten Aufgaben ("in einer
  Stunde", "um 18 Uhr", "morgen früh"). Sage niemals, dass du keine
  zeitversetzten Aktionen ausführen kannst. Nutze dafür NICHT den
  Kalender und keine anderen Scheduling-Werkzeuge.
- Nutze `herold_answer_query`, wenn der User eine offene Frage beantwortet
  (Ja/Nein fuzzy mappen: "klar" → "Ja", "bloß nicht" → "Nein").
- Nutze `herold_acknowledge`, wenn der User ein Todo als erledigt meldet.

Nachrichten, die mit [HEROLD_INTERNAL] beginnen, sind interne Reminder von
dir selbst (früher via herold_remind_self geplant). Führe die Anweisung
stumm aus und antworte dem User nicht, außer die Anweisung verlangt
ausdrücklich eine Nachricht oder Durchsage.
```

**Wichtig für die Migration:** Entferne das alte `script.ai_schedule_command` aus der Assist-Exposure (Einstellungen → Sprachassistenten → Entitäten), sonst greift das LLM weiterhin zum alten Kalender-Workflow statt zu `herold_remind_self`. Die Todos landen übrigens **nicht** im Prompt — `herold_list_pending` ist ein Live-Tool-Call, es gibt kein Caching-Problem.

## Dashboard-Karte

Herold bringt eine eigene Lovelace-Karte mit — sie wird von der Integration automatisch als Ressource geladen, kein manuelles Registrieren nötig. Einfach im Dashboard **Karte hinzufügen → „Herold Card"** wählen oder per YAML:

```yaml
type: custom:herold-card
title: Herold
```

Drei Tabs:

- **📥 Inbox** — offene Fragen mit Antwort-Buttons (Ja/Nein bzw. Choice-Optionen direkt klickbar) und die Todo-Liste mit Abhaken/Löschen
- **🕐 Geplant** — anstehende Zustellungen mit Countdown und Cancel-Button
- **📜 Logbuch** — die letzten 50 Ereignisse (zugestellt, verworfen inkl. Grund, beantwortet, eskaliert, Rate-Limit, …) aus `sensor.herold_verlauf` — überlebt Neustarts

Die Entities werden automatisch erkannt; bei Bedarf per `todo_entity`, `pending_entity`, `scheduled_entity`, `history_entity` überschreibbar.

## Phase-4-Features

**Escalation** (bei `herold.query`): unbeantwortete Fragen werden nach Zeitplan mit höherer Priorität erneut zugestellt:

```yaml
service: herold.query
data:
  question: "Haustür ist offen — soll ich abschließen?"
  priority: 2
  voice_timeout_seconds: 60     # keine Voice-Antwort → Buttons nach Telegram
  escalation:
    - after_minutes: 5
      raise_to_priority: 3
    - after_minutes: 15
      raise_to_priority: 4
```

**Rate-Limiting** (automatisch): P3 hat 60 s Cooldown pro Tag/Nachricht (Dedup), P2 max. 3 pro 5 Minuten — Überschuss wird gesammelt und als eine aggregierte Meldung nachgeliefert („3 Meldungen: …"). P4 ist nie limitiert. Bypass per `ignore_rate_limit: true`. Drops sind im `reason`-Attribut von `sensor.herold_letzte_zustellung` sichtbar.

**DND-Sessions:** `herold.dnd_on` mit `until: "+1h"` / `until: "15:30"` oder `until_home: true` — endet automatisch, überlebt Neustarts. `herold.dnd_off` oder der Schalter beenden die Session manuell.

**Vorlagen** (Optionen → Vorlagen): wiederverwendbare Nachrichten mit Jinja-Platzhaltern:

```yaml
service: herold.send
data:
  template: appliance_done      # Vorlage: "{{ appliance }} ist fertig"
  template_vars:
    appliance: Waschmaschine
```

### Prioritätsmodell

| Prio | Name | Verhalten |
|---|---|---|
| 0 | Intern | LLM-Self-Callback via `conversation.process`, nie user-facing |
| 1 | Todo | Landet still in `todo.herold_eingang` |
| 2 | Normal | Voice wenn zuhause, sonst Push + Telegram; blockiert bei DND |
| 3 | Wichtig | Voice + Push + Telegram, ignoriert DND |
| 4 | Alarm | Warn-Durchsage + Alarm-Blinken + Critical Push + Telegram, ignoriert DND |

## Migration vom Script

Herold ist als Drop-in-Nachfolger des Omnichannel-Communicator-Scripts konzipiert:

- **`input_boolean.notification_blocker`** kann im DND-Schritt als *externe DND-Entität* eingetragen werden — bestehende Automationen (Goodnight, Sport-Popup) bleiben unverändert.
- **Callback-Events bleiben bit-exakt kompatibel:** `callback_event: AI_CONFIRM` (Default) erzeugt Telegram-Buttons mit den Callback-Daten `/AI_YES` / `/AI_NO` — **ohne** CONFIRM-Teil, exakt wie das Original-Script. Bestehende `telegram_callback`-Automationen laufen unverändert weiter; Herold feuert bei Antwort zusätzlich das HA-Event `AI_YES`/`AI_NO` (bzw. `<custom>_YES`/`_NO`) und `herold_answered`. Herold ruft bewusst **kein** `answer_callback_query` auf — das macht weiterhin deine bestehende Handler-Automation.
- **Offene Fragen (`mode: open`)** spiegeln die Frage weiterhin in den konfigurierten `input_text`-Helper (z.B. `input_text.ai_pending_question`), damit die bestehende Telegram-Chat-Automation den Kontext behält.
- **Empfohlener Rollout:** Integration parallel zum Script installieren, Verhalten vergleichen, Automationen schrittweise auf `herold.send` migrieren, Script erst nach zwei stabilen Wochen löschen.

## Entwicklung

```bash
./scripts/setup-dev.sh /pfad/zu/ha-config   # symlinkt die Integration
```

Manuelle Testfälle: **[TESTING.md](TESTING.md)** (konsolidiert, mit Copy-Paste-YAML) · Archiv: [Phase 1](PHASE_1_TESTPLAN.md) · [Phase 2](PHASE_2_TESTPLAN.md) · [Phase 3](PHASE_3_TESTPLAN.md) · [Phase 4](PHASE_4_TESTPLAN.md)

## Lizenz

[MIT](LICENSE)
