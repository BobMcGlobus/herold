# Herold 📯

*[English version](README.md) · Deutsche Übersetzung — die englische README ist die maßgebliche Fassung.*

> **⚠️ Alpha — nicht für den Produktivbetrieb.** Die Integration ist in aktiver Entwicklung; API und Config-Format können sich noch ändern.

**Herold** ist eine Home Assistant Custom Integration für priorisierte Omnichannel-Benachrichtigungen: raumbewusste Sprachausgabe über Assist-Satelliten und Media Player, Push auf die Mobile App, Telegram mit Antwort-Buttons, ein Wecker, dazu ein 5-stufiges Prioritätsmodell mit DND-Logik und Offline-TTS-Fallback.

Herold ist der Nachfolger des Scripts `System: Universal Omnichannel Communicator (Priority Edition)` — als wartbare, testbare Integration mit UI-Konfiguration.

> **Zur Sprache:** Code, Kommentare, Commits, Changelog und alle Prompts, die Herold ans LLM schickt, sind Englisch. Deutsch sind nur die Oberflächen für den Haushalt — Config Flow, Entity-Namen und diese Übersetzung.

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

Der Config Flow führt durch neun Schritte:

1. **Grundlagen** — Empfänger-Person, Name der Instanz
2. **Räume** (wiederholbar) — pro Raum: Präsenzsensoren (mehrere möglich, ODER-verknüpft), Assist-Satellit und/oder Media Player, optional Lichter und Szenen für den P4-Alarm-Flash, optional Lautstärkestufen
3. **Sprache** — primäres TTS (z.B. ElevenLabs), optionales Fallback-TTS (z.B. Piper), Internet-Erkennungssensor
4. **Push** — Mobile-App-Notify-Entitäten
5. **Chat** — optionale Telegram-Chat-ID für Nachrichten und Antwort-Buttons, optionaler Pending-Question-Helper (Legacy-Kompat für offene Fragen)
6. **LLM** — Conversation-Agent für P0-Selbsterinnerungen plus Fallback-Agent, Schalter für sprechbare Bestätigungen und die Selbstkontrolle
7. **Nicht stören** — optionale externe DND-Entität, interner DND-Schalter, Ruhezeiten
8. **Wecker** — Bett-Sensor, Schlafzimmer, Wecker-Lautsprecher, Lautstärkegrenzen, Schlummer- und Aufgeben-Einstellungen, Aufsteh-Prüfung, Vorlaufzeiten für Licht und Rolladen, Guten-Morgen-Routine, Arbeitstag- und Krankheits-Sensor
9. **Offline** — Offline-TTS-Fallback (opt-in), Offline-Warteschlange (geplant)

Alle Sektionen sind später über die Integrations-Optionen editierbar; Räume und Vorlagen können ohne Neueinrichtung hinzugefügt, bearbeitet und entfernt werden.

## Feature-Matrix

| Feature | Status |
|---|---|
| `herold.send` Service (P0–P4) | ✅ 0.1.0 |
| Raumbewusste Voice-Delivery (Occupancy → Satellit) | ✅ 0.1.0 |
| Multi-Occupancy-Sensoren pro Raum (ODER-verknüpft) | ✅ 0.1.0 |
| Media-Player-Only-Räume (`tts.speak` Fallback) | ✅ 0.1.0 |
| TTS-Kette: Primär → Offline-Fallback (z.B. ElevenLabs → Piper) | ✅ 0.1.0 |
| Mobile App Push (critical Sound für P4) | ✅ 0.1.0 |
| DND-Schalter + externe DND-Entität | ✅ 0.1.0 |
| `herold.query` — Fragen mit Antwort (yesno / open / choice) | ✅ 0.2.0 |
| Telegram-Channel mit Inline-Buttons (legacy-kompatibel) | ✅ 0.2.0 |
| Query-Persistenz über Neustarts, Timeout + default_answer | ✅ 0.2.0 |
| Multi-Occupancy-Konfliktauflösung (Gewicht + Aktualität) | ✅ 0.2.0 |
| Last-Known-Room-Fallback (TTL 15 min) | ✅ 0.2.0 |
| P4 Alarm-Blinken: mehrere Lichter und Szenen pro Raum | ✅ 0.2.0 |
| Pending-Sensoren (`pending_count`, `last_query`, `any_pending`) | ✅ 0.2.0 |
| `herold.schedule` + `herold.remind_self` (persistiert über Neustarts) | ✅ 0.3.0 |
| P0 Internal Channel (LLM-Self-Callback via `conversation.process`) | ✅ 0.3.0 |
| Native LLM-Tools (`list_pending`, `acknowledge`, `answer_query`, `remind_self`) | ✅ 0.3.0 |
| Todo-Inbox `todo.herold_eingang` für P1-Benachrichtigungen | ✅ 0.3.0 |
| Escalation-Chains für unbeantwortete Fragen | ✅ 0.4.0 |
| Voice-Timeout: Buttons gehen nach Telegram, wenn niemand antwortet | ✅ 0.4.0 |
| Rate-Limiting + P2-Aggregation (Anti-Spam) | ✅ 0.4.0 |
| DND-Sessions (`until`, `until_home`) | ✅ 0.4.0 |
| Benachrichtigungs-Vorlagen mit Jinja-Platzhaltern | ✅ 0.4.0 |
| pytest-Suite (Dispatcher, Router, Legacy-Kompat, Limiter, …) | ✅ 0.5.0 |
| Dashboard-Karte (Inbox / Geplant / Wecker / Logbuch) + Verlauf | ✅ 0.6.0 |
| Antwort-Auswertung + Selbstkontrolle für LLM-Anweisungen | ✅ 0.7.0 |
| Ereignis-Trigger (`herold.watch`, `herold_remind_when`) | ✅ 0.8.0 |
| Lautstärkestufen pro Raum + Ruhezeiten | ✅ 0.9.0 |
| Wecker mit Ramp-up, Snooze und Automation-Hooks | ✅ 1.0.0 |
| Wecker: Wecktöne, Hartnäckigkeitsstufen, Aufsteh-Prüfung, eigene Karte | ✅ 1.2.0 |
| Offline-Queue, Multi-User | 🔜 Backlog |

Die Release-Historie steht in [CHANGELOG.md](CHANGELOG.md).

## Service: `herold.send`

```yaml
service: herold.send
data:
  message: "Die Waschmaschine ist fertig"
  priority: 2          # 0 intern · 1 todo · 2 normal · 3 wichtig · 4 alarm
  # title: "Optionaler Push-Titel"
  # target_player: assist_satellite.living_room
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

Der Prompt selbst ist **englisch**, wie alles, was an das LLM geht — die zitierten Beispielsätze bleiben deutsch, weil der User sie so sagt. In den Optionen des Conversation-Agents unter „Anweisungen" ergänzen:

```markdown
## Herold — the household notification system

You have access to the Herold tools (the "Herold" LLM API must be enabled):

- Use `herold_list_pending` when the user asks "was ist neu", "gibt es was
  für mich", "hab ich was verpasst" — and proactively at the end of a
  conversation if something might be open.
- Use `herold_remind_self` for ALL time-delayed tasks ("in einer Stunde",
  "um 18 Uhr", "morgen früh"). Never tell the user you cannot perform
  time-delayed actions. Do NOT use the calendar or any other scheduling
  helper for this.
- Use `herold_remind_when` when the reminder is tied to an event instead of
  a time ("wenn ich das nächste Mal die Haustür öffne", "sobald die
  Waschmaschine fertig ist", "wenn es unter 5 Grad wird").
- Use `herold_set_alarm` for alarm clocks ("stell mir einen Wecker für
  halb sieben"). While an alarm is ringing, "aus"/"stopp" and "snooze" are
  handled by Herold itself — do not call a tool for them.
- ALWAYS read the "confirmation" field of a tool result back to the user so
  they know something was really stored. On success=false, say clearly that
  it did NOT work.
- Use `herold_answer_query` when the user answers an open question (map
  fuzzy yes/no: "klar" → "Ja", "bloß nicht" → "Nein").
- Use `herold_acknowledge` when the user reports a todo as done.

Messages starting with [HEROLD_INTERNAL] are internal reminders from
yourself (scheduled earlier via herold_remind_self). Execute the instruction
silently and do not reply to the user, unless the instruction explicitly
asks for a message or an announcement.
```

**Wichtig für die Migration:** Entferne das alte `script.ai_schedule_command` aus der Assist-Exposure (Einstellungen → Sprachassistenten → Entitäten), sonst greift das LLM weiterhin zum alten Kalender-Workflow statt zu `herold_remind_self`. Die Todos landen übrigens **nicht** im Prompt — `herold_list_pending` ist ein Live-Tool-Call, es gibt kein Caching-Problem.

## Wecker

Herold weckt dich in dem Raum, in dem du schläfst — und zwar mit einem echten Ton statt eines gesprochenen Satzes. Eine TTS-Zeile hat keinen Attack und keine Frequenzspitzen; genau deshalb verschläft man sie.

```yaml
service: herold.alarm_set
data:
  time: "06:30"
  days: [mon, tue, wed, thu, fri]   # weglassen = einmalig
  label: Arbeit
  urgency: insistent                # gentle · normal · insistent
  workday_only: true                # Feiertage und Krankheit blockieren
  # key: schichtplan                # damit eine Automation den Wecker besitzt
  # valid_until: "+7d"              # temporärer Wecker
```

**Am bequemsten über die Karte.** `custom:herold-alarm-card` aufs Dashboard: Wecker als Kacheln mit großer Uhrzeit, Wochentagsleiste, Status-Badges und Schalter. ＋ legt einen an, ein Tipp auf die Kachel öffnet die **Einstellungen als Popup** — Uhrzeit, Wiederholung (mit den Vorlagen Werktags / Wochenende / Täglich), Bezeichnung, Hartnäckigkeit, Klangquelle samt Anhören-Knopf, die Ansage, Arbeitstag- und Sprach-Snooze-Schalter, und unter „Mehr Einstellungen“ die Guten-Morgen-Routine und ein Ablaufdatum. Auf dem iPhone öffnet das Zeitfeld das native Rad.

```yaml
type: custom:herold-alarm-card
title: Wecker
card_style: glass    # default · glass · material · bubble · mirror
columns: 2
```

| Option | Typ | Default | Beschreibung |
|---|---|---|---|
| `title` / `subtitle` | string | – | Überschrift |
| `entity` | string | automatisch | Der Wecker-Sensor, wird selbst gefunden |
| `card_style` | string | `default` | `default`, `glass`, `material`, `bubble`, `mirror` |
| `layout` | string | `grid` | `grid` oder `carousel` |
| `columns` | number | `1` | Kachel-Spalten (1–3) |
| `tiles` | boolean | `true` | `false` = flache Zeilen statt Kacheln |
| `background` | boolean | `true` | `false` entfernt Kartenhintergrund und Schatten |
| `flush` | boolean | `false` | `true` entfernt den Außenabstand |

Die Stile und ihre Tokens sind die der [Weatherglass](https://github.com/BobMcGlobus/Weatherglass)-Karte — auf einem gemeinsamen Dashboard passen beide zusammen. Alles ist auch im visuellen Karteneditor einstellbar.

**Weckton** — vier Töne liegen bei (Glocke, Piepen, Sirene, Sonnenaufgang; von `scripts/generate_sounds.py` synthetisiert, daher ohne Lizenzfragen). `sound_mode` wählt die Quelle: `builtin`, `media` (beliebige Mediendatei, z.B. selbst hochgeladen), `music_assistant`, oder `announce` für das alte reine Sprechen. Die Ansage ist optional und folgt dem Ton.

**Hartnäckigkeit** bestimmt, wie zäh er ist:

| Stufe | Intervall | Gibt auf nach | Schlummern |
|---|---|---|---|
| sanft | 90 s | 3 Durchgängen | unbegrenzt |
| normal | 45 s | 6 Durchgängen | 3× |
| hartnäckig | 25 s | 15 Durchgängen | 1×, dann verweigert |

**Die Lautstärke** bleibt zwischen einer einstellbaren Unter- und Obergrenze (Optionen → Wecker). Der erste Durchgang startet an der Untergrenze und klettert Richtung Obergrenze, solange du nicht reagierst — ein abends leise gedrehter Lautsprecher kann den Wecker also nicht mehr schlucken.

**Aufstehen wird geprüft:** Ein Dismiss, während der Bett-Sensor noch Belegung meldet, gilt als Reflex — nach einer Karenzzeit macht der Wecker weiter. In den Optionen abschaltbar, falls dir das zu streng ist.

**Vor dem Ton** fährt das Licht hoch (Standard 20 Minuten vorher) und die Rolladen öffnen (Standard 5 Minuten vorher) — beide Zeiten einstellbar, `0` schaltet die Stufe ab. Die **Guten-Morgen-Routine** (Script oder Szene) läuft, wenn du wirklich aufgestanden bist, nicht beim ersten Schlummern.

**Arbeitswecker** mit `workday_only` werden übersprungen, wenn der Arbeitstag-Sensor aus oder der Krankheits-Schalter an ist. Einmalige und Feiertagswecker klingeln trotzdem — dafür stellt man sie ja.

**Steuerung:** `herold.alarm_snooze`, `herold.alarm_dismiss`, `herold.alarm_update`, `herold.alarm_skip_next`, `herold.alarm_cancel`. Ohne `id` beziehen sich Snooze und Dismiss auf den klingelnden Wecker.

**Für Automationen:** `sensor.herold_naechster_wecker` (Timestamp, dazu `target` und `in_bed`), `binary_sensor.herold_wecker_klingelt`, plus die Events `herold_alarm_set`, `herold_alarm_triggered`, `herold_alarm_snoozed`, `herold_alarm_dismissed`, `herold_alarm_skipped`, `herold_alarm_pre`.

## Lautstärke & Ruhezeiten

Pro Raum lassen sich drei Lautstärkestufen hinterlegen (Optionen → Räume): **leise**, **normal**, **laut**. Herold setzt die passende Stufe vor der Durchsage und stellt danach die vorherige Lautstärke wieder her — erst wenn der Player wirklich fertig gesprochen hat. Stufen, die du leer lässt, ändern nichts: Ohne Konfiguration bleibt alles wie bisher.

Welche Stufe genommen wird: **P4 immer laut**, sonst **normal** — außer innerhalb der **Ruhezeiten** (Optionen → Nicht stören, z.B. 22:00–07:00), dann **leise**. Ein Alarm um drei Uhr nachts bleibt also laut, eine normale Meldung nicht.

## Erinnerungen an Ereignisse knüpfen

Neben zeitbasierten Erinnerungen kann Herold auf **Zustandsänderungen** warten — kleine Einmal-Automationen, die sich der Assistent selbst anlegt:

> „Erinnere mich daran, dem Postboten das Paket mitzugeben, wenn ich das nächste Mal die Haustür öffne."

```yaml
service: herold.watch
data:
  entity_id: binary_sensor.front_door
  to_state: "on"
  message: Denk an das Paket für den Postboten!
  priority: 3
  ttl_hours: 72        # 0 = verfällt nie
```

Auch numerisch (`above` / `below`, feuert nur beim Überschreiten, nicht dauerhaft):

```yaml
service: herold.watch
data:
  entity_id: sensor.outdoor_temperature
  below: 5
  message: Es wird frostig — denk an die Pflanzen auf dem Balkon.
```

Beobachtungen sind einmalig (danach löschen sie sich selbst), überleben Neustarts, verfallen nach der TTL und tauchen in der Karte unter „Geplant → Nach Ereignis" auf. Automationen können auf `herold_watch_triggered` triggern.

Das LLM legt sie über `herold_remind_when` an und muss die exakte Entity-ID **nicht** kennen: Die Angabe wird gegen die exponierten Entities, ihre Klarnamen und ihre Sprach-Aliase gematcht — „Klimaanlage Arbeitszimmer" findet sich also von selbst. Passt nichts, nennt die Fehlermeldung konkrete Entity-IDs, damit sich das Modell korrigieren kann statt erneut zu raten. `to_state: "on"` funktioniert in jeder Domain: Bei Entities, die nie „on" melden (climate, media_player, cover, …), übersetzt Herold das in „hat den Aus-Zustand verlassen" — also genau das, was „geht an" bedeutet.

## Dashboard-Karte

Herold bringt eine eigene Lovelace-Karte mit — sie wird von der Integration automatisch als Ressource geladen, kein manuelles Registrieren nötig. Einfach im Dashboard **Karte hinzufügen → „Herold Card"** wählen oder per YAML:

```yaml
type: custom:herold-card
title: Herold
```

Vier Tabs:

- **📥 Inbox** — offene Fragen mit Antwort-Buttons (Ja/Nein bzw. Choice-Optionen direkt klickbar) und die Todo-Liste mit Abhaken/Löschen
- **🕐 Geplant** — anstehende Zustellungen mit Countdown und Cancel-Button, getrennt nach „Nach Zeit" und „Nach Ereignis"
- **⏰ Wecker** — gestellte Wecker mit Schlummern, Beenden und Löschen
- **📜 Logbuch** — die letzten 50 Ereignisse (zugestellt, verworfen inkl. Grund, beantwortet, eskaliert, Rate-Limit, …) aus `sensor.herold_verlauf` — überlebt Neustarts

Die Entities werden automatisch erkannt; bei Bedarf per `todo_entity`, `pending_entity`, `scheduled_entity`, `history_entity`, `watches_entity` oder `alarms_entity` überschreibbar.

## Eskalation, Rate-Limiting, DND-Sessions, Vorlagen

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

- **`input_boolean.do_not_disturb`** kann im DND-Schritt als *externe DND-Entität* eingetragen werden — bestehende Automationen (Goodnight, Sport-Popup) bleiben unverändert.
- **Callback-Events bleiben bit-exakt kompatibel:** `callback_event: AI_CONFIRM` (Default) erzeugt Telegram-Buttons mit den Callback-Daten `/AI_YES` / `/AI_NO` — **ohne** CONFIRM-Teil, exakt wie das Original-Script. Bestehende `telegram_callback`-Automationen laufen unverändert weiter; Herold feuert bei Antwort zusätzlich das HA-Event `AI_YES`/`AI_NO` (bzw. `<custom>_YES`/`_NO`) und `herold_answered`. Herold ruft bewusst **kein** `answer_callback_query` auf — das macht weiterhin deine bestehende Handler-Automation.
- **Offene Fragen (`mode: open`)** spiegeln die Frage weiterhin in den konfigurierten `input_text`-Helper (z.B. `input_text.pending_question`), damit die bestehende Telegram-Chat-Automation den Kontext behält.
- **Empfohlener Rollout:** Integration parallel zum Script installieren, Verhalten vergleichen, Automationen schrittweise auf `herold.send` migrieren, Script erst nach zwei stabilen Wochen löschen.

## Entwicklung

```bash
./scripts/setup-dev.sh /pfad/zu/ha-config   # symlinkt die Integration
```

Testsuite ausführen:

```bash
pip install -r requirements_test.txt && pytest tests/
```

## Lizenz

[MIT](LICENSE)
