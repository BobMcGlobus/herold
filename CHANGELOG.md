# Changelog

## 1.0.0 — Wecker

- Weckerverwaltung: einmalig oder auf Wochentagen wiederkehrend, mit
  Bezeichnung und eigener Weckdurchsage; persistent über Neustarts
- Sanftes Wecken: Lautstärke rampt über die Durchgänge hoch (35 % → 100 %
  der „laut"-Stufe), Alarm-Lichter dimmen über 30 s hoch statt rot zu
  blinken; Weckrufe ignorieren DND, Ruhezeiten und Rate-Limiting
- Klingelt alle 45 s weiter bis Dismiss, gibt nach 5 Durchgängen auf
- Services `herold.alarm_set` / `_cancel` / `_snooze` (Standard 9 min) /
  `_dismiss`; Snooze und Dismiss ohne ID betreffen den klingelnden Wecker
- Automation-Hooks: `sensor.*_naechster_wecker` (Timestamp),
  `binary_sensor.*_wecker_klingelt`, Events `herold_alarm_set`,
  `herold_alarm_triggered`, `herold_alarm_snoozed`, `herold_alarm_dismissed`
- LLM-Tools `herold_set_alarm`, `herold_list_alarms`, `herold_cancel_alarm`
- Karte: neuer Tab „Wecker" mit Schlummern/Beenden/Löschen

## 0.9.0 — Lautstärke & Ruhezeiten

- Drei optionale Lautstärkestufen pro Raum (leise / normal / laut) in
  Prozent; nicht gesetzte Stufen lassen die Lautstärke unangetastet
- Nach der Durchsage wird die vorherige Lautstärke wiederhergestellt —
  erst wenn der Player wirklich fertig ist (Polling statt fixem Delay),
  und bei überlappenden Durchsagen nur einmal am Ende
- Player ohne `volume_set` werden übersprungen statt Fehler zu werfen
- **Ruhezeiten** (Optionen → Nicht stören): im Zeitfenster sprechen P2/P3
  auf der leisen Stufe, P4 bleibt immer laut

## 0.8.0 — Ereignis-Trigger

- Neuer Service `herold.watch`: Erinnerungen, die auf eine
  Zustandsänderung warten statt auf eine Uhrzeit („wenn ich das nächste Mal
  die Haustür öffne") — inklusive numerischer Schwellen (`above`/`below`),
  die nur beim Überschreiten auslösen
- Einmalig per Default, mit TTL (Standard 72 h) gegen vergessene Trigger,
  persistent über Neustarts
- Neues LLM-Tool `herold_remind_when`; gibt den aufgelösten Klarnamen der
  Entity zurück, damit eine falsche Zuordnung sofort auffällt
- `sensor.*_aktive_beobachtungen`, Events `herold_watch_armed` und
  `herold_watch_triggered` für eigene Automationen
- `herold.cancel` und `herold_cancel` kümmern sich auch um Beobachtungen
- Karte: Tab „Geplant" trennt jetzt „Nach Zeit" und „Nach Ereignis"

## 0.7.0 — Verlässliche LLM-Rückmeldung

- Der Internal-Channel wertet die Antwort von `conversation.process` jetzt
  aus (`return_response`): Agent-Fehler und fehlgeschlagene Geräte-Ziele
  werden erkannt statt verschluckt
- Optionale **Selbstkontrolle**: nach einer P0-Anweisung prüft der Agent in
  genau einem weiteren Zug, ob wirklich passiert ist was sollte, und bessert
  einmalig nach (`ok` / `corrected` / `failed` / `unverified`) — Standard an,
  abschaltbar in den Optionen
- `sensor.*_letzte_interne_anweisung` mit Status, Agent-Antwort und
  Fehlerdetail; Einträge im Karten-Logbuch
- LLM-Tools liefern einen **sprechbaren Bestätigungssatz** (`confirmation`),
  den der Agent laut Tool-Description vorlesen muss — man hört jetzt, ob
  etwas wirklich gespeichert wurde
- Neues LLM-Tool `herold_cancel`: „vergiss die Erinnerung" funktioniert
- `task_context` bei `herold.schedule` / `herold.remind_self` und im
  Remind-Tool: der Grund wird gespeichert und beim Auslösen mitgegeben
- Events `herold_internal_triggered` (jetzt mit Agent-Antwort) und
  `herold_internal_verified`

## 0.6.0 — Dashboard-Karte & Verlauf

- Lovelace-Karte `custom:herold-card` (automatisch geladen, keine
  Ressourcen-Config nötig): Inbox mit Antwort-Buttons und Todo-Abhaken,
  Tab „Geplant" mit Countdown + Cancel, Logbuch-Tab
- `sensor.*_verlauf`: Ringpuffer der letzten 50 Ereignisse (zugestellt,
  verworfen mit Grund, Rate-Limit, Frage/Antwort, Eskalation, geplant),
  persistent über Neustarts
- Pending-Sensor liefert jetzt auch die `choices` je Frage
- `TESTING.md`: konsolidierter Testplan mit Copy-Paste-YAML

## 0.5.0 — Phase 5: Tests & Polish

- pytest-Suite (64 Tests): Dispatcher-Matrix, Room-Router-Konfliktauflösung,
  Legacy-Event-Semantik, Model-Roundtrips, `parse_when`-Grammatik,
  Rate-Limiter, Templates, Antwort-Normalisierung
- Test-Workflow in CI (`test.yml`, Python 3.13)
- Fix: Voice-Channel meldet „kein Raum / kein Output" jetzt als Fehler im
  `errors`-Attribut statt still als Zustellung zu zählen

## 0.4.0 — Phase 4: Escalation, Rate-Limiting, DND-Sessions, Templates

- Escalation-Chains für unbeantwortete Fragen (`escalation`-Feld,
  `herold_escalated`-Event, `binary_sensor.*_eskalation_aktiv`)
- `voice_timeout_seconds`: ohne Voice-Antwort gehen die Buttons nach Telegram
- Rate-Limiter: P3 60 s Dedup pro Tag, P2 max. 3/5 min mit Aggregation,
  `ignore_rate_limit`-Bypass
- DND-Sessions: `herold.dnd_on` (`until`, `until_home`) / `herold.dnd_off`,
  persistent über Neustarts
- Benachrichtigungs-Vorlagen mit Jinja-Platzhaltern (Options-Editor)
- Drop-/Limit-Gründe im `reason`-Attribut der letzten Zustellung
- `sensor.*_naechste_zustellung` (Timestamp)

## 0.3.0 — Phase 3: P0, Scheduler, LLM-Tools, Todo

- Internal Channel: P0-Instruktionen via `conversation.process`
  (`[HEROLD_INTERNAL]`, Fallback-Agent, 20/h Anti-Runaway)
- `herold.schedule` + `herold.remind_self` mit Persistenz und 5-min-Grace
- Native LLM-API „Herold": `list_pending`, `acknowledge`, `answer_query`,
  `remind_self`
- Todo-Inbox für P1-Benachrichtigungen (`todo.*_eingang`)

## 0.2.0 — Phase 2: Query, Telegram, Room-Router

- `herold.query` (yesno/open/choice) mit Timeout, `default_answer` und
  Persistenz; `herold.acknowledge` / `herold.cancel`
- Telegram-Channel mit legacy-kompatiblen Inline-Buttons (`/AI_YES`-Format)
- Legacy-Events `AI_YES`/`AI_NO` bzw. `<custom>_YES`/`_NO` plus
  strukturiertes `herold_answered`
- Multi-Occupancy-Konfliktauflösung + Last-Known-Room-Fallback (15 min)
- `flash_entities` (mehrere Lichter/Szenen) mit Config-Migration v1→v2

## 0.1.0 — Phase 1: MVP

- `herold.send` mit Prioritätsmodell P0–P4 (portiert vom Original-Script)
- Raumbewusste Voice-Delivery, Media-Player-Only-Räume, TTS-Fallback-Kette
- Push-Channel (critical für P4), DND-Schalter + externe DND-Entität
- Config Flow mit Multi-Occupancy-Räumen, Options Flow
