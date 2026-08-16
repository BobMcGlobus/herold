# Changelog

Language note: this file, the code, comments and commit messages are
English. User-facing surfaces (config flow, entity names, the German
README) are German — see `translations/`. Entity ids below use the English
names; on a German instance they are the translated ones, e.g.
`sensor.herold_naechster_wecker` for `sensor.*_next_alarm`.

## 1.0.1 — Watches actually reachable from voice

- `herold_remind_when` no longer requires the model to know exact entity
  ids. The reference is resolved against exposed entities, their friendly
  names and their voice aliases, with a domain prefix narrowing the field —
  so a guessed `climate.ac_arbeitszimmer` finds
  `climate.klimaanlage_arbeitszimmer`
- When nothing matches, the error now **lists concrete entity ids** instead
  of "pick one of the exposed entities", which is what lets the model
  correct itself instead of guessing again; an entity that exists but is not
  exposed says exactly that
- `to_state: "on"` works for every domain: for entities that never report
  "on" (climate, media_player, cover, …) it is rewritten to "left the off
  state", which is what "turns on" means. German state words (an, aus,
  offen, zu, zuhause) are mapped too — in the service as well
- The tool parameter is now `entity` (an id or a name); `entity_id` keeps
  working

## 1.0.0 — Alarm clock

- Alarm management: one-shot or repeating on weekdays, with label and a
  custom wake message; persisted across restarts
- Gentle wake: the volume ramps up across rings (35 % → 100 % of the room's
  "loud" level) and alarm lights fade up over 30 s instead of the P4 red
  strobe; alarm rings deliberately bypass DND, quiet hours and rate limiting
- Rings every 45 s until dismissed, gives up after 5 rings
- Services `herold.alarm_set` / `_cancel` / `_snooze` (default 9 min) /
  `_dismiss`; snooze and dismiss without an id act on the ringing alarm
- Automation hooks: `sensor.*_next_alarm` (timestamp),
  `binary_sensor.*_alarm_ringing`, events `herold_alarm_set`,
  `herold_alarm_triggered`, `herold_alarm_snoozed`, `herold_alarm_dismissed`
- LLM tools `herold_set_alarm`, `herold_list_alarms`, `herold_cancel_alarm`
- Card: new "Wecker" tab with snooze / dismiss / delete

## 0.9.0 — Volume levels and quiet hours

- Three optional volume levels per room (quiet / normal / loud) in percent;
  levels left blank leave the volume untouched
- The previous volume is restored after the announcement — but only once the
  player actually finished (polled instead of a fixed delay), and only once
  at the end when announcements overlap
- Players without `volume_set` support are skipped instead of erroring
- **Quiet hours** (options → DND): inside the window P2/P3 speak at the quiet
  level, P4 always stays loud

## 0.8.0 — State-triggered reminders

- New service `herold.watch`: reminders that wait for a state change instead
  of a point in time ("the next time I open the front door"), including
  numeric thresholds (`above`/`below`) that only fire on the crossing
- One-shot by default, with a TTL (default 72 h) against forgotten triggers,
  persisted across restarts
- New LLM tool `herold_remind_when`; returns the resolved friendly name of
  the entity so a wrong match is obvious immediately
- `sensor.*_watch_count`, events `herold_watch_armed` and
  `herold_watch_triggered` for custom automations
- `herold.cancel` and `herold_cancel` now also cancel watches
- Card: the scheduled tab separates "by time" and "by event"

## 0.7.0 — Reliable LLM feedback

- The internal channel now inspects the `conversation.process` response
  (`return_response`): agent errors and failed device targets are detected
  instead of swallowed
- Optional **self-check**: after a P0 instruction the agent verifies in
  exactly one further turn whether it really happened and corrects once
  (`ok` / `corrected` / `failed` / `unverified`) — on by default, can be
  disabled in the options
- `sensor.*_last_internal` with status, agent reply and failure detail;
  entries in the card's logbook
- LLM tools return a **speakable confirmation sentence** (`confirmation`)
  that the tool description requires the agent to read out — you can now
  hear whether something was really stored
- New LLM tool `herold_cancel`: "forget that reminder" works
- `task_context` on `herold.schedule` / `herold.remind_self` and in the
  remind tool: the reason is stored and handed over when it fires
- Events `herold_internal_triggered` (now with the agent reply) and
  `herold_internal_verified`

## 0.6.0 — Dashboard card and history

- Lovelace card `custom:herold-card` (auto-loaded, no resource config
  needed): inbox with answer buttons and todo check-off, scheduled tab with
  countdown and cancel, logbook tab
- `sensor.*_history`: ring buffer of the last 50 events (delivered, dropped
  with reason, rate limited, query/answer, escalation, scheduled), persisted
  across restarts
- The pending sensor now also exposes the `choices` per query

## 0.5.0 — Phase 5: tests and polish

- pytest suite (64 tests): dispatcher matrix, room router conflict
  resolution, legacy event semantics, model roundtrips, `parse_when`
  grammar, rate limiter, templates, answer normalization
- Test workflow in CI (`test.yml`, Python 3.13)
- Fix: the voice channel reports "no room / no output" as an error in the
  `errors` attribute instead of silently counting as a delivery

## 0.4.0 — Phase 4: escalation, rate limiting, DND sessions, templates

- Escalation chains for unanswered queries (`escalation` field,
  `herold_escalated` event, `binary_sensor.*_escalation_active`)
- `voice_timeout_seconds`: without a voice answer the buttons go to Telegram
- Rate limiter: P3 60 s dedup per tag, P2 max 3 per 5 min with aggregation,
  `ignore_rate_limit` bypass
- DND sessions: `herold.dnd_on` (`until`, `until_home`) / `herold.dnd_off`,
  persisted across restarts
- Notification templates with Jinja placeholders (options editor)
- Drop and rate-limit reasons in the `reason` attribute of the last delivery
- `sensor.*_next_schedule` (timestamp)

## 0.3.0 — Phase 3: P0, scheduler, LLM tools, todo

- Internal channel: P0 instructions via `conversation.process`
  (`[HEROLD_INTERNAL]`, fallback agent, 20/h anti-runaway)
- `herold.schedule` + `herold.remind_self` with persistence and a 5 min grace
  period for deliveries missed while Home Assistant was down
- Native LLM API "Herold": `list_pending`, `acknowledge`, `answer_query`,
  `remind_self`
- Todo inbox for P1 notifications (`todo.*_inbox`)

## 0.2.0 — Phase 2: query, Telegram, room router

- `herold.query` (yesno/open/choice) with timeout, `default_answer` and
  persistence; `herold.acknowledge` / `herold.cancel`
- Telegram channel with legacy-compatible inline buttons (`/AI_YES` format)
- Legacy events `AI_YES`/`AI_NO` resp. `<custom>_YES`/`_NO` plus the
  structured `herold_answered`
- Multi-occupancy conflict resolution and last-known-room fallback (15 min)
- `flash_entities` (multiple lights/scenes) with config migration v1 → v2

## 0.1.0 — Phase 1: MVP

- `herold.send` with the P0–P4 priority model (ported from the original
  script)
- Room-aware voice delivery, media-player-only rooms, TTS fallback chain
- Push channel (critical for P4), DND switch plus external DND entity
- Config flow with multi-occupancy rooms, options flow
