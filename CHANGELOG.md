# Changelog

Language note: this file, the code, comments and commit messages are
English. User-facing surfaces (config flow, entity names, the German
README) are German — see `translations/`. Entity ids below use the English
names; on a German instance they are the translated ones, e.g.
`sensor.herold_naechster_wecker` for `sensor.*_next_alarm`.

## 1.6.0 — The ring loop, fixed

Seven reports from a week of real mornings. Most of them share a cause: the
alarm was built around a five-second tone, and a song is not a tone.

- **A song is started once, not on every ring.** `media` and
  `music_assistant` alarms used to re-issue `play_media` every 45 seconds,
  which restarts the track or skips to the next one. Later rings now only
  raise the volume, and only if the player actually stopped is playback
  started again
- **A song keeps its volume.** The announcement volume was restored as soon
  as the player fell idle — or after 60 s regardless, which for a four
  minute track meant it faded back mid-song. Alarm volume is now *held* for
  the whole alarm and given back when the alarm ends
- **Dismissing and snoozing stop the music.** Neither used to; the song
  simply played on after the alarm was over
- **Getting out of bed ends the alarm.** The bed sensor was only ever read
  on demand, so leaving it did nothing while the alarm rang. It is now
  watched: an empty bed for `alarm_up_seconds` (default 30 s, new option)
  dismisses a ringing, verifying or snoozed alarm. The debounce matters —
  rolling over drops an occupancy sensor for a moment
- **Voice snooze works.** It used to route the alarm to a satellite that
  announced the message and then listened for nothing. It now asks via
  `assist_satellite.ask_question` and acts on the answer — "schlummern",
  "noch fünf Minuten", "aus", "ich bin wach"
- **The card updates the moment the alarm goes off.** The state was only
  published after playback had started, which on a slow player is seconds
  late, and a dismiss during playback published nothing at all
- **A running snooze is shown as a countdown** with a draining bar and
  mm:ss left, ticking once a second. The tile turns blue while snoozed and
  offers "Ich bin wach"; a ringing tile says which ring it is on

## 1.5.1 — When a speaker says no

An Apple TV refusing to stream the wake-up file exposed three things that
were worse than the refusal itself.

- **A refused tone no longer means a silent alarm.** If the player rejects
  the sound, the ring falls back to speaking the message instead of failing
  and repeating the same failure on all fifteen rings
- **The test reports instead of raising.** `herold.alarm_test` returns
  `media_player`, `satellite`, `sound`, and on failure an `error` plus a
  `hint` naming what to change. The card renders it inline under the test
  chips — *Spielt auf Schlafzimmer Speaker*, or the reason it did not
- **Televisions are called out in the target picker.** Media players with
  `device_class: tv` sit in their own group and are flagged when selected.
  A TV sleeps at night, wakes slowly, and its streaming stack refuses
  plenty of ordinary audio files, but the room router cannot tell
- The card's *Ton testen* chip now sends the target currently selected in
  the sheet, so you can try a speaker before committing the alarm to it

## 1.5.0 — Alarms ring where you tell them to

Three field reports, one theme: the alarm decided for itself where to ring,
and it decided badly.

- **Fixes "failed to init decoder".** The built-in tones were 16 kHz WAV.
  AirPlay receivers — an Apple TV, a HomePod — reject any sample rate but
  44.1 kHz outright, so the tone never played. All four tones are now
  44.1 kHz mono WAV. They are about three times the size; an alarm that
  only works on some of the speakers in the house is worse
- **Fixes alarms landing on the television.** With no alarm speaker
  configured, the room router hands the alarm to whatever media player the
  active room owns, and that is as likely to be a TV as a bedside speaker.
  Two new per-alarm fields override the guess:
  - `target` — pin the alarm to one `media_player` or `assist_satellite`
  - `follow_me` — ring wherever you currently are, ignoring the bed sensor,
    the bedroom and the configured alarm speaker. For alarms that have
    nothing to do with sleeping: a nap on the couch, a timer at the desk
- **Both are in the card**, under *Wo klingelt er* — a speaker dropdown and
  a follow-me switch, with a line showing what an automatically-resolved
  alarm points at right now. The alarm tiles show a pinned target or
  "folgt mir" as a badge
- `herold.alarm_test` takes a `target` too, so you can try a speaker without
  first committing an alarm to it, and its response now names the entity it
  actually played on
- A player refusing the sound now says which player and which media instead
  of only passing the driver's error through
- `sensor.*_next_alarm` exposes `target`, `target_name` and `follow_me` per
  alarm; the card's header line is labelled "Ohne festes Ziel" because that
  is what it always was

## 1.4.0 — Your own wake-up sound, and a way to try it

- **Drag an MP3 onto the card.** The sound section of the settings sheet is
  a drop zone: the file is uploaded into the Home Assistant media library,
  stored as that alarm's sound and resolved to a playable URL at ring time,
  so players that do not understand `media-source://` ids work too. MP3,
  M4A, WAV, OGG and FLAC; needs a writable media source (`media_dirs`)
- **Music Assistant stops guessing.** The card now searches it — pick a
  media type, search, tap a result, and the exact URI is stored instead of a
  name that might match anything. New `sound_media_type` field (`track`,
  `album`, `artist`, `playlist`, `radio`) for the YAML and automation route,
  passed on to Music Assistant. New service `herold.alarm_search_media`
  returns the same results as a service response
- Music Assistant playback now **replaces** the queue instead of appending
  to it, so last night's playlist no longer plays before the alarm
- **Test the alarm without waiting for morning.** `herold.alarm_test` rings
  now — `scope: sound | light | cover | all`, with an optional volume
  override and an optional alarm id to test one alarm's own sound. Lights
  and blinds are snapshotted into a scene beforehand and restored after a
  few seconds, so a test at 22:00 does not leave the bedroom lit
- The settings sheet gained *Ton testen* and *Licht testen* chips, and two
  new buttons (`button.*_test_alarm_sound`, `button.*_test_alarm_light`)
  make the same thing available on a dashboard
- Switching sound mode clears the previous mode's value — a built-in tone
  name left over in a Music Assistant field was never going to play

## 1.3.0 — The alarm card grows up

- **Settings live in a popup now.** Tapping an alarm opens a sheet instead of
  swapping the whole card for a form — the list stays where it was, and the
  card no longer repaints out from under a field you are typing in
- **More per-alarm settings**, all of which the services already supported
  but the card could not reach: the spoken wake message, the sound source
  (built-in tone, any media id, a Music Assistant search, or speech only),
  the good-morning routine picked from your scripts and scenes, and an
  expiry date for a temporary alarm. Built-in tones have an audition button
- Repeat presets (Weekdays / Weekend / Daily / One-off), "skip the next one"
  from inside the sheet, and a live hint explaining what the chosen urgency
  actually does
- **Five card styles** — `default`, `glass`, `material`, `bubble`, `mirror` —
  plus `columns`, `layout`, `tiles`, `background` and `flush`, matching the
  Weatherglass card so both can share a dashboard. All of it is editable in
  the visual card editor
- Alarms render as tiles with a weekday strip and status badges (work alarm,
  blocked today, skipped, routine, expires, voice snooze); the accent colour
  follows the urgency and a ringing alarm pulses
- **The announcement target is named, not spelled.** `sensor.*_next_alarm`
  and both cards showed the raw entity id of an explicitly configured
  speaker; they now show its friendly name. The description also prefers the
  media player over the satellite, which is the order the alarm really uses
- Optional alarm fields can be **cleared** again: emptying the routine, the
  expiry, the label or the tone removes it instead of being ignored, and an
  emptied wake message falls back to the default text

## 1.2.0 — An alarm clock that actually wakes you

The alarm used to speak a TTS sentence every 45 seconds. A spoken sentence
has no attack and no frequency peaks, so it is easy to sleep through — this
release makes it a real alarm.

- **Wake-up sounds.** Alarms play audio through the speaker instead of only
  speaking. Four synthesised tones ship with the integration (chime, beep,
  siren, sunrise — generated by `scripts/generate_sounds.py`, so no
  third-party audio licensing), or pick any media, or hand playback to
  Music Assistant. The spoken message is optional and follows the tone
- **Speaker before satellite.** A satellite can only announce text, so the
  media player now wins. The satellite is chosen only when the alarm wants
  a spoken snooze
- **Volume floor and ceiling.** Absolute bounds instead of a fraction of the
  room level — a speaker left at 5 % overnight can no longer swallow the
  alarm. Ring one starts at the floor and climbs towards the ceiling
- **Urgency levels** (gentle / normal / insistent) drive ring spacing, how
  long it keeps trying, how fast the volume climbs and the **snooze
  budget**: insistent grants one short snooze and then refuses
- **Getting-up verification.** A dismiss while the bed sensor still reports
  occupancy is treated as a reflex — after a grace period the alarm resumes
- **Pre-alarm phase.** Lights fade up well before the sound (default 20 min)
  and blinds open shortly before it (default 5 min), both configurable and
  separately disableable
- **Good-morning routine** — a script or scene run after you really got up,
  not on the first snooze
- **Workday and sick-day blocking** for alarms flagged as work alarms;
  one-off and holiday alarms ring regardless
- **Temporary alarms** via `valid_until`, and a `key` so an automation can
  own an alarm instead of creating duplicates. One-shot alarms clean
  themselves up after dismissal instead of lingering as dead rows
- New services `herold.alarm_update` and `herold.alarm_skip_next`; alarms
  can be enabled and disabled without deleting them
- **New standalone card** `custom:herold-alarm-card` — create, edit, toggle,
  snooze, dismiss and delete alarms from the dashboard

## 1.1.0 — Alarms reach the bedroom

- **Fixes alarms staying silent.** Occupancy sensors do not fire while
  somebody lies still, so at wake-up time the room router found no active
  room and the alarm degraded to a push notification. Alarms now resolve
  their own target
- New **alarm section** in the options: a bed sensor, the bedroom (picked
  from the configured rooms), optional satellite/speaker overrides, snooze
  duration and the give-up threshold
- Target resolution: in bed → the bedroom; already up → the active room;
  nothing occupied → the bedroom as fallback. Explicit satellite or speaker
  overrides everything, and no configured output at all logs a warning
  instead of failing quietly
- A failed ring no longer ends the alarm — the next ring is armed anyway
- `sensor.*_next_alarm` exposes `target` and `in_bed`, and the card's alarm
  tab shows where a ring would go right now
- German weekday names work when setting alarms by voice ("Dienstag" used
  to be truncated to "die" and rejected)

## 1.0.2 — Tool errors no longer abort the conversation

- A tool raising an unexpected exception used to kill the whole voice
  pipeline with "intent-failed", leaving the user without any answer. Tools
  now catch anything, log it with a traceback and return a normal failure
  result the agent can talk about
- Fixes the crash behind that: `friendly_name` is not always a string in
  HA 2026 (computed names use a sentinel object), and the resolver called
  `.lower()` on it. Non-text names and aliases are ignored now and the
  entity id is used as the label instead

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
