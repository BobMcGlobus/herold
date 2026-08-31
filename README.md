# Herold 📯

*[Deutsche Version](README.de.md)*

> **⚠️ Alpha — not for production.** Under active development; the API and the
> config format can still change.

**Herold** is a Home Assistant custom integration for prioritised omnichannel
notifications: room-aware voice output through Assist satellites and media
players, mobile push, Telegram with answer buttons, an alarm clock, and a
five-level priority model with do-not-disturb logic and an offline TTS
fallback.

Herold is the successor of the script
`System: Universal Omnichannel Communicator (Priority Edition)` — as a
maintainable, testable integration with UI configuration.

> **A note on languages.** Code, comments, commit messages, the changelog and
> every prompt Herold sends to an LLM are English. The user-facing surfaces —
> config flow, entity names and this README's German twin — are German,
> because that is what the household speaks. See `translations/`.

## Requirements

- **Home Assistant 2026.7.0 or newer**
- At least one Assist satellite **or** a media player with TTS
- Optional: mobile app (for push), occupancy sensors (for room detection)

## Installation via HACS (custom repository)

1. Open HACS → menu (⋮ top right) → **Custom repositories**
2. Add the repository URL `https://github.com/BobMcGlobus/herold`,
   type: **Integration**
3. Search for "Herold" in HACS and install it
4. Restart Home Assistant
5. **Settings → Devices & services → Add integration → Herold**

## Setup (config flow)

The config flow walks through nine steps:

1. **Basics** — recipient person, instance name
2. **Rooms** (repeatable) — per room: occupancy sensors (several possible,
   OR-linked), Assist satellite and/or media player, optional alarm lights
   and scenes for the P4 flash, optional volume levels
3. **Voice** — primary TTS (e.g. ElevenLabs), optional fallback TTS
   (e.g. Piper), internet detection sensor
4. **Push** — mobile app notify entities
5. **Chat** — optional Telegram chat id for messages and answer buttons,
   optional pending-question helper (legacy compatibility for open questions)
6. **LLM** — conversation agent for P0 self-reminders plus a fallback agent,
   toggles for speakable confirmations and the self-check
7. **DND** — optional external DND entity, internal DND switch, quiet hours
8. **Alarm clock** — bed sensor, bedroom, alarm speaker, volume bounds,
   snooze and give-up settings, getting-up verification, pre-alarm lead
   times for lights and blinds, good-morning routine, workday and
   sick-day sensors
9. **Offline** — offline TTS fallback (opt-in), offline queue (planned)

Every section stays editable through the integration options; rooms and
templates can be added, edited and removed without re-running setup.

## Feature matrix

| Feature | Status |
|---|---|
| `herold.send` service (P0–P4) | ✅ 0.1.0 |
| Room-aware voice delivery (occupancy → satellite) | ✅ 0.1.0 |
| Multiple occupancy sensors per room (OR-linked) | ✅ 0.1.0 |
| Media-player-only rooms (`tts.speak` fallback) | ✅ 0.1.0 |
| TTS chain: primary → offline fallback (e.g. ElevenLabs → Piper) | ✅ 0.1.0 |
| Mobile app push (critical sound for P4) | ✅ 0.1.0 |
| DND switch plus external DND entity | ✅ 0.1.0 |
| `herold.query` — questions expecting an answer (yesno / open / choice) | ✅ 0.2.0 |
| Telegram channel with inline buttons (legacy compatible) | ✅ 0.2.0 |
| Query persistence across restarts, timeout and `default_answer` | ✅ 0.2.0 |
| Multi-occupancy conflict resolution (weight plus recency) | ✅ 0.2.0 |
| Last-known-room fallback (15 min TTL) | ✅ 0.2.0 |
| P4 alarm flash: several lights and scenes per room | ✅ 0.2.0 |
| `herold.schedule` and `herold.remind_self` (persisted) | ✅ 0.3.0 |
| P0 internal channel (LLM self-callback via `conversation.process`) | ✅ 0.3.0 |
| Native LLM tools | ✅ 0.3.0 |
| Todo inbox for P1 notifications | ✅ 0.3.0 |
| Escalation chains for unanswered queries | ✅ 0.4.0 |
| Voice timeout: buttons move to Telegram when nobody answers | ✅ 0.4.0 |
| Rate limiting plus P2 aggregation (anti-spam) | ✅ 0.4.0 |
| DND sessions (`until`, `until_home`) | ✅ 0.4.0 |
| Notification templates with Jinja placeholders | ✅ 0.4.0 |
| pytest suite (dispatcher, router, legacy compat, limiter, …) | ✅ 0.5.0 |
| Dashboard card (inbox / scheduled / alarms / logbook) plus history | ✅ 0.6.0 |
| Response inspection and self-check for LLM instructions | ✅ 0.7.0 |
| State triggers (`herold.watch`, `herold_remind_when`) | ✅ 0.8.0 |
| Per-room volume levels plus quiet hours | ✅ 0.9.0 |
| Alarm clock with ramp-up, snooze and automation hooks | ✅ 1.0.0 |
| Alarm clock: wake sounds, urgency levels, get-up verification, standalone card | ✅ 1.2.0 |
| Offline queue, multi-user | 🔜 backlog |

The release history lives in [CHANGELOG.md](CHANGELOG.md).

## Service: `herold.send`

```yaml
service: herold.send
data:
  message: "Die Waschmaschine ist fertig"
  priority: 2          # 0 internal · 1 todo · 2 normal · 3 important · 4 alarm
  # title: "Optional push title"
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
  # choices: ["Pizza", "Pasta", "Salat"]   # only for mode: choice
  priority: 2
  timeout_minutes: 60
  # voice_timeout_seconds: 90   # no voice answer → buttons go to Telegram
  # default_answer: "Nein"      # used automatically on timeout
  # callback_event: AI_CONFIRM
```

Answer paths: satellite conversation (`start_conversation`), Telegram inline
buttons, free text in the Telegram chat (open mode), the card, or
`herold.acknowledge` (id plus answer). Open queries survive restarts. On an
answer Herold fires `herold_answered` with a structured payload — for yesno
additionally the legacy event (`AI_YES`/`AI_NO` resp. `<custom>_YES`/`_NO`).

## Services: `herold.schedule` and `herold.remind_self`

```yaml
service: herold.schedule
data:
  scheduled_for: "+1h30m"       # also "18:00" or an ISO datetime
  message: "Ofen vorheizen nicht vergessen"
  priority: 2
```

```yaml
service: herold.remind_self     # P0 convenience for the assistant
data:
  when: "+30m"
  instruction: "Frage den User via herold.query: Wie ist der Kuchen geworden?"
  task_context: "Es backt gerade ein Kuchen."
```

Scheduled notifications survive restarts; deliveries missed while Home
Assistant was down still fire within five minutes, older ones are marked
`herold_expired`. P0 instructions run through the configured conversation
agent (options → LLM) with the `[HEROLD_INTERNAL]` prefix, a fallback agent
and an anti-runaway limit (max 20 per hour).

## LLM tools

Herold registers an LLM API named **Herold** — enable it per conversation
agent under *Voice assistants → agent → LLM APIs*. Tools:

| Tool | Purpose |
|---|---|
| `herold_list_pending` | todos, open queries, schedules and watches |
| `herold_acknowledge` | mark a todo as done |
| `herold_answer_query` | answer an open query (with fuzzy matching) |
| `herold_remind_self` | time-based self-reminder |
| `herold_remind_when` | state-triggered reminder |
| `herold_cancel` | cancel a reminder, watch or query |
| `herold_set_alarm` / `herold_list_alarms` / `herold_cancel_alarm` | alarm clock |

Every tool returns a ready-to-speak `confirmation` sentence that the tool
description requires the agent to read back, so the user always hears whether
something was really stored.

### System prompt block (copy-paste into the agent instructions)

The prompt is English like all LLM-facing text; the quoted example phrases
stay German because they are what the user actually says.

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

**Important when migrating:** remove the old `script.ai_schedule_command`
from the Assist exposure (Settings → Voice assistants → Entities), otherwise
the LLM keeps reaching for the old calendar workflow instead of
`herold_remind_self`. Todos do *not* end up in the prompt —
`herold_list_pending` is a live tool call, so there is no caching problem.

## Alarm clock

Herold wakes you in the room you sleep in, with an actual tone rather than a
spoken sentence — a TTS line has no attack and no frequency peaks, which is
exactly why it is easy to sleep through.

```yaml
service: herold.alarm_set
data:
  time: "06:30"
  days: [mon, tue, wed, thu, fri]   # omit for a one-shot alarm
  label: Work
  urgency: insistent                # gentle · normal · insistent
  workday_only: true                # skip holidays and sick days
  # key: shift_plan                 # an automation can own this alarm
  # valid_until: "+7d"              # temporary alarm
```

**The card is the comfortable way in.** Add `custom:herold-alarm-card` to a
dashboard: alarms as tiles with big times, weekday strip, status badges and a
toggle. ＋ creates one, tapping a tile opens its **settings sheet** — time,
repeat (with Weekdays / Weekend / Daily presets), label, urgency, sound
source with an audition button, the spoken message, workday and voice-snooze
flags, and under "more settings" the good-morning routine and an expiry date.
On iOS the time field opens the native wheel.

```yaml
type: custom:herold-alarm-card
title: Wecker
card_style: glass    # default · glass · material · bubble · mirror
columns: 2
```

| Option | Type | Default | Description |
|---|---|---|---|
| `title` / `subtitle` | string | – | Heading |
| `entity` | string | auto | The alarm sensor; found automatically |
| `card_style` | string | `default` | `default`, `glass`, `material`, `bubble`, `mirror` |
| `layout` | string | `grid` | `grid` or `carousel` |
| `columns` | number | `1` | Tile columns (1–3) |
| `tiles` | boolean | `true` | `false` renders flat rows instead of tiles |
| `background` | boolean | `true` | `false` removes the card background and shadow |
| `flush` | boolean | `false` | `true` removes the outer padding |

The styles and their tokens are the ones the
[Weatherglass](https://github.com/BobMcGlobus/Weatherglass) card uses, so the
two match on a shared dashboard. Everything is editable in the visual card
editor.

**Sound** — four tones ship with the integration (chime, beep, siren,
sunrise; synthesised by `scripts/generate_sounds.py`, so no third-party
audio licensing — 44.1 kHz mono WAV, because AirPlay receivers reject
anything else). `sound_mode` picks the source:

| Mode | What `sound` holds |
|---|---|
| `builtin` | `chime`, `beep`, `siren` or `sunrise` |
| `media` | a media id or URL — `media-source://media_source/local/wake.mp3`, `https://…/wake.mp3` |
| `music_assistant` | a Music Assistant URI (`library://playlist/12`), or a plain name if you also set `sound_media_type` |
| `announce` | nothing; the alarm only speaks |

The spoken message is optional and follows the tone.

**Bring your own MP3.** Drop an audio file onto the card's sound section and
it is uploaded into your Home Assistant media library, stored as the alarm's
`sound` and resolved to a playable URL at ring time. This needs the media
source to be writable — with `default_config` that is the `media_dirs`
folder (`/media` in a standard install). Supported: MP3, M4A, WAV, OGG,
FLAC.

**Music Assistant** wants to know *what* it is looking for. Rather than
typing a name and hoping, the card searches: pick a media type, search, tap
a result, and the exact URI is stored. From YAML or an automation, set
`sound_media_type` (`track`, `album`, `artist`, `playlist`, `radio`)
alongside a plain name, or pass a URI and leave the type out. The queue is
replaced rather than appended to, so last night's playlist does not play
first. `herold.alarm_search_media` exposes the same search and returns a
response.

**Test it before you rely on it** — `herold.alarm_test` rings now:

```yaml
action: herold.alarm_test
data:
  scope: sound      # sound · light · cover · all
  volume: 0.4       # optional, overrides the floor for this test
  # id: a1b2c3d4    # test one alarm's own sound settings
```

The card has *Ton testen* and *Licht testen* chips in the settings sheet,
and there are two buttons (`button.*_test_alarm_sound` /
`button.*_test_alarm_light`) for a dashboard. Lights and blinds are
snapshotted before the test and restored afterwards (default 12 s), so a
test at 22:00 does not leave the bedroom lit.

The test reports rather than raising: the response carries `media_player`,
`satellite`, `sound`, and on failure an `error` plus a `hint` about what to
change. The card renders that inline — *Spielt auf Schlafzimmer Speaker*, or
the reason it did not.

**Urgency** decides how stubborn it is:

| Level | Interval | Gives up after | Snoozes |
|---|---|---|---|
| gentle | 90 s | 3 rings | unlimited |
| normal | 45 s | 6 rings | 3 |
| insistent | 25 s | 15 rings | 1, then refused |

**Volume** stays between a configurable floor and ceiling (options → alarm
clock). Ring one starts at the floor and climbs towards the ceiling as the
alarm is ignored — a speaker left quiet overnight cannot swallow it.

**Where it rings.** Without any hint, Herold resolves a target itself: in
bed → the bedroom, already up → the active room, nothing occupied → the
bedroom. That is a guess, and it can land on the wrong device — the active
room's media player may well be a TV. Two per-alarm fields override it:

| Field | Effect |
|---|---|
| `target` | Pin this alarm to one `media_player` or `assist_satellite`. Wins over everything |
| `follow_me` | Ring wherever you are right now, ignoring the bed sensor, the bedroom and the configured alarm speaker — for a nap on the couch or a timer at the desk |

Both are in the card's settings sheet under *Wo klingelt er*, which also
shows what an automatically-resolved alarm currently points at. For a
house-wide default instead, set the alarm speaker in options → alarm clock.

Media players with `device_class: tv` are listed in a separate group and
flagged when picked. A television is a poor alarm: it sleeps at night, wakes
slowly, and its streaming stack refuses plenty of ordinary audio files — an
Apple TV in particular. If the chosen player refuses the tone at ring time,
the alarm falls back to speaking the message rather than staying silent for
all fifteen rings.

**Getting up is verified**: a dismiss while the bed sensor still reports
occupancy counts as a reflex, and after a grace period the alarm resumes.
Turn it off in the options if that is too strict.

**Ring only when I'm in bed.** `require_bed` skips an alarm — sound *and*
sunrise phase — when the bed sensor reports an empty bed at wake-up time.
Off by default, and deliberately one-sided: only a sensor that positively
says "empty" may block a wake-up. `unknown`, `unavailable`, a missing
entity or no bed sensor at all all ring anyway and log a warning, because a
missed alarm costs far more than one that rings while you are already up.
Ignored for `follow_me` alarms, which are by definition not about the bed.

**Getting up also ends it.** Leaving the bed while an alarm is ringing,
verifying or snoozed dismisses it, once the bed has stayed empty for
`alarm_up_seconds` (default 30 s — long enough that rolling over does not
cancel the alarm). Set it to `0` to switch that off.

**Voice snooze** asks a real question. With `voice_snooze` the satellite
uses `assist_satellite.ask_question` and listens for the answer:
"schlummern" / "snooze" / "noch fünf Minuten" snoozes, "aus" / "ich bin
wach" / "stopp" dismisses. Needs a Home Assistant with
`assist_satellite.ask_question`; without it the alarm logs a warning and
carries on ringing.

**Songs are played, not restarted.** With `sound_mode: media` or
`music_assistant` the alarm starts the track once and later rings only turn
it up — re-issuing playback every 45 seconds would restart the song or skip
to the next one. The volume is held for the whole alarm instead of being
restored between rings, and dismissing or snoozing stops playback.

**Before the sound**, lights fade up (default 20 minutes early) and blinds
open (default 5 minutes early) — both times configurable, `0` disables the
stage. The **good-morning routine** (a script or scene) runs once you really
got up, not on the first snooze.

**Work alarms** flagged `workday_only` are skipped when the configured
workday sensor is off or the sick-day toggle is on. One-off and holiday
alarms ring regardless — that is usually the point of setting them.

**Control:** `herold.alarm_snooze`, `herold.alarm_dismiss`,
`herold.alarm_update`, `herold.alarm_skip_next`, `herold.alarm_cancel`.
Without an `id`, snooze and dismiss act on the ringing alarm.

**For automations:** `sensor.*_next_alarm` (timestamp, plus `target` and
`in_bed`), `binary_sensor.*_alarm_ringing`, and the events
`herold_alarm_set`, `herold_alarm_triggered`, `herold_alarm_snoozed`,
`herold_alarm_dismissed`, `herold_alarm_skipped`, `herold_alarm_pre`.

## Volume and quiet hours

Each room can define three volume levels (options → rooms): **quiet**,
**normal**, **loud**. Herold applies the matching level before an
announcement and restores the previous volume afterwards — only once the
player actually finished speaking. Levels left blank change nothing, so
without configuration everything behaves as before.

Which level applies: **P4 is always loud**, otherwise **normal** — except
inside the **quiet hours** (options → DND, e.g. 22:00–07:00), where it is
**quiet**. An alarm at three in the morning stays loud, a routine message
does not.

## Tying reminders to events

Besides time-based reminders, Herold can wait for **state changes** — small
one-shot automations the assistant creates for itself:

> "Remind me to hand the parcel to the postman the next time I open the
> front door."

```yaml
service: herold.watch
data:
  entity_id: binary_sensor.front_door
  to_state: "on"
  message: Denk an das Paket für den Postboten!
  priority: 3
  ttl_hours: 72        # 0 = never expires
```

Numeric thresholds work too (`above` / `below`, firing only on the crossing,
not continuously):

```yaml
service: herold.watch
data:
  entity_id: sensor.outdoor_temperature
  below: 5
  message: Es wird frostig — denk an die Pflanzen auf dem Balkon.
```

Watches are one-shot (they remove themselves afterwards), survive restarts,
expire after their TTL and appear in the card under *scheduled → by event*.
Automations can trigger on `herold_watch_triggered`.

The LLM creates them via `herold_remind_when` and does **not** need to know
exact entity ids: the reference is matched against the exposed entities,
their friendly names and their voice aliases, so "Klimaanlage Arbeitszimmer"
resolves on its own. If nothing matches, the error lists concrete entity ids
so the model can correct itself instead of guessing again. `to_state: "on"`
works for every domain — for entities that never report "on" (climate,
media_player, cover, …) Herold rewrites it to "left the off state", which is
what "turns on" means.

## Dashboard card

Herold ships its own Lovelace card — the integration registers it as a
resource automatically, no manual setup needed. Pick **Add card → "Herold
Card"** on a dashboard, or use YAML:

```yaml
type: custom:herold-card
title: Herold
```

Four tabs:

- **📥 Inbox** — open queries with answer buttons (yes/no resp. the choice
  options, directly clickable) and the todo list with check-off and delete
- **🕐 Scheduled** — upcoming deliveries with a countdown and a cancel
  button, split into time-based and event-based entries
- **⏰ Alarms** — configured alarm clocks with snooze, dismiss and delete
- **📜 Logbook** — the last 50 events (delivered, dropped including the
  reason, answered, escalated, rate limited, …) from the history sensor;
  survives restarts

Entities are discovered automatically; override them with `todo_entity`,
`pending_entity`, `scheduled_entity`, `history_entity`, `watches_entity` or
`alarms_entity` if needed.

## Escalation, rate limiting, DND sessions, templates

**Escalation** (on `herold.query`): unanswered questions are redelivered at a
higher priority on a schedule:

```yaml
service: herold.query
data:
  question: "Haustür ist offen — soll ich abschließen?"
  priority: 2
  voice_timeout_seconds: 60     # no voice answer → buttons go to Telegram
  escalation:
    - after_minutes: 5
      raise_to_priority: 3
    - after_minutes: 15
      raise_to_priority: 4
```

**Rate limiting** (automatic): P3 has a 60 s cooldown per tag/message
(dedup), P2 allows max 3 per 5 minutes — the overflow is buffered and
delivered as one aggregated message ("3 Meldungen: …"). P4 is never limited.
Bypass with `ignore_rate_limit: true`. Drops are visible in the `reason`
attribute of the last-delivery sensor.

**DND sessions:** `herold.dnd_on` with `until: "+1h"` / `until: "15:30"` or
`until_home: true` — ends automatically and survives restarts.
`herold.dnd_off` or the switch ends the session manually.

**Templates** (options → templates): reusable messages with Jinja
placeholders:

```yaml
service: herold.send
data:
  template: appliance_done      # template: "{{ appliance }} ist fertig"
  template_vars:
    appliance: Waschmaschine
```

### Priority model

| Prio | Name | Behaviour |
|---|---|---|
| 0 | Internal | LLM self-callback via `conversation.process`, never user-facing |
| 1 | Todo | Lands silently in the todo inbox |
| 2 | Normal | Voice when home, otherwise push plus Telegram; blocked by DND |
| 3 | Important | Voice plus push plus Telegram, ignores DND |
| 4 | Alarm | Warning announcement, alarm flash, critical push, Telegram; ignores DND |

## Migrating from the script

Herold is designed as a drop-in successor of the omnichannel communicator
script:

- **`input_boolean.do_not_disturb`** can be configured as the
  *external DND entity* in the DND step — existing automations (goodnight,
  sports popup) keep working unchanged.
- **Callback events stay bit-exact compatible:** `callback_event: AI_CONFIRM`
  (the default) produces Telegram buttons with the callback data `/AI_YES` /
  `/AI_NO` — **without** the CONFIRM part, exactly like the original script.
  Existing `telegram_callback` automations keep running; on an answer Herold
  additionally fires the HA event `AI_YES`/`AI_NO` (resp.
  `<custom>_YES`/`_NO`) and `herold_answered`. Herold deliberately does
  **not** call `answer_callback_query` — your existing handler automation
  still does that.
- **Open questions (`mode: open`)** still mirror the question into the
  configured `input_text` helper (e.g. `input_text.pending_question`), so
  the existing Telegram chat automation keeps its context.
- **Suggested rollout:** install the integration alongside the script,
  compare behaviour, migrate automations to `herold.*` step by step, and
  delete the script only after two stable weeks.

## Development

```bash
./scripts/setup-dev.sh /path/to/ha-config   # symlinks the integration
```

Run the test suite:

```bash
pip install -r requirements_test.txt && pytest tests/
```

## License

[MIT](LICENSE)
