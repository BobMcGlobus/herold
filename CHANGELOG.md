# Changelog

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
