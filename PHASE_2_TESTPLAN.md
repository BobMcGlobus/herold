# Phase 2 — Manueller Testplan (Casa de Jonas)

Voraussetzungen: Phase-1-Setup (siehe `PHASE_1_TESTPLAN.md`), zusätzlich in den Optionen:

- **Chat:** Telegram-Chat-ID `8229685543`, Pending-Question-Helper `input_text.ai_pending_question`
- **Räume:** Arbeitszimmer hat `light.schreibtisch_ambiente_leuchte` jetzt unter *Alarm-Blinken* (nach der automatischen Migration prüfen!)

Log-Level: `custom_components.herold: debug`.

---

## TC1 — Config-Migration v1 → v2

- **Aktion:** Update installieren, HA neu starten.
- **Erwartet:** Integration lädt ohne Fehler. Debug-Log `Migrated config entry … to version 2`. In den Optionen → Räume → Arbeitszimmer steht die Schreibtischleuchte im Multi-Select *Alarm-Blinken*. P4-Verhalten unverändert (TC4 aus Phase 1 wiederholen).

## TC2 — Ja/Nein-Frage zuhause mit Sat → start_conversation + Buttons bei P3

- **Setup:** Zuhause, Arbeitszimmer occupied, Internet on.
- **Aktion:** `herold.query` mit `question: "Soll ich das Licht ausschalten?"`, `mode: yesno`, `priority: 3`.
- **Erwartet:** `assist_satellite.start_conversation` im Arbeitszimmer **und** Telegram-Nachricht `🟠 Soll ich das Licht ausschalten?` mit Buttons `✅ Ja bitte` / `❌ Nein danke`. `sensor.herold_pending_count` = 1, `binary_sensor.herold_any_pending` = on.

## TC3 — Legacy-Button-Kompat: AI_YES-Event + bestehende Automation

- **Setup:** TC2 offen.
- **Aktion:** In Telegram „✅ Ja bitte" drücken.
- **Erwartet (parallel, beides!):**
  1. Deine bestehende `telegram_callback_handler`-Automation läuft wie bisher (conversation.process, Bestätigung im Chat).
  2. Herold feuert `herold_answered` (`{id, answer: "Ja", source_channel: telegram, mode: yesno}`) **und** das Legacy-Event `AI_YES`. Query-Status in `sensor.herold_last_query` = `answered`. Pending-Count = 0.

## TC4 — Custom Callback: XYZ_YES/XYZ_NO

- **Aktion:** `herold.query`, `mode: yesno`, `callback_event: HEIZUNG`, dann „Nein" drücken.
- **Erwartet:** Buttons mit Callback-Daten `/HEIZUNG_YES` / `/HEIZUNG_NO`; nach Klick Event `HEIZUNG_NO` + `herold_answered` mit `answer: "Nein"`.

## TC5 — Choice-Mode

- **Aktion:** `herold.query` mit `mode: choice`, `choices: ["Pizza", "Pasta", "Salat"]`, `priority: 3`.
- **Erwartet:** Telegram mit drei Buttons (ein Button pro Option, Callback `/HRLD_<id>_<index>`). Klick auf „Pasta" → `herold_answered` mit `answer: "Pasta"`. Am Sat wird die Frage per start_conversation gestellt (mit extra_system_prompt der Optionen).

## TC6 — Open-Mode + Legacy input_text

- **Aktion:** `herold.query` mit `mode: open`, `question: "Wie war der Film?"`, `priority: 3`.
- **Erwartet:** `input_text.ai_pending_question` = „Wie war der Film?" (Legacy-Kompat), Telegram `❓ Wie war der Film?`. Freitext-Antwort im Chat → Herold resolved die Query (`herold_answered` mit dem Text) **und** deine bestehende Chat-Automation verarbeitet die Antwort via Gemini wie bisher.

## TC7 — Timeout mit default_answer

- **Aktion:** `herold.query`, `mode: yesno`, `timeout_minutes: 1`, `default_answer: "Nein"`. Nicht antworten.
- **Erwartet:** Nach ~1 min `herold_answered` mit `answer: "Nein"`, `source_channel: timeout`, plus `AI_NO`-Event. Ohne `default_answer`: stattdessen `herold_expired` mit `reason: timeout`.

## TC8 — Reboot-Persistenz

- **Aktion:** Query mit `timeout_minutes: 30` stellen, HA neu starten, dann per Button beantworten.
- **Erwartet:** Nach dem Neustart ist die Query weiterhin pending (Sensor-Check), der Timeout läuft weiter, die Antwort funktioniert. War der Timeout während des Neustarts abgelaufen → Query wird beim Boot als expired markiert.

## TC9 — Media-Player-Only-Raum: Frage gesprochen, Antwort via Telegram

- **Setup:** Nur Badezimmer occupied, zuhause, P2.
- **Aktion:** `herold.query`, `mode: yesno`.
- **Erwartet:** Frage wird via `tts.speak` auf dem Sonos Roam gesprochen **und** Telegram-Buttons kommen trotz P2 (weil der Raum die Antwort nicht einfangen kann — Debug-Log prüfen).

## TC10 — Multi-Occupancy-Konfliktauflösung

- **Setup:** Wohnzimmer+Küche **und** Arbeitszimmer gleichzeitig occupied.
- **Aktion:** a) beide `priority_weight: 0`: Zuletzt aktivierter Raum gewinnt (erst Wohnzimmer-FP2 triggern, dann Arbeitszimmer-Sensor → Ansage im Arbeitszimmer). b) Wohnzimmer `priority_weight: 10` setzen → Ansage immer im Wohnzimmer, egal welcher Sensor zuletzt kam.

## TC11 — Last-Known-Room-Fallback

- **Setup:** Arbeitszimmer occupied, dann Sensor auf off (Raum verlassen), keine 15 min warten.
- **Aktion:** `herold.send`, `priority: 2`.
- **Erwartet:** Ansage weiterhin im Arbeitszimmer (Last-Known-Room, TTL 15 min). Nach >15 min ohne Occupancy: kein Voice, Telegram-Fallback (wenn konfiguriert).

## TC12 — Telegram-Catch-All für Info-Nachrichten

- **Setup:** Nicht zuhause.
- **Aktion:** `herold.send`, `priority: 2`.
- **Erwartet:** Telegram-Nachricht (plain, ohne Prefix) + Push — wie im Original-Script („nicht zuhause → Telegram").

## TC13 — acknowledge/cancel Services

- **Aktion:** Query stellen, dann `herold.acknowledge` mit `id` (aus `sensor.herold_pending_count` Attributen) und `answer: "Ja"`. Zweite Query stellen, `herold.cancel` mit `id`.
- **Erwartet:** Acknowledge feuert `herold_answered` + `AI_YES`; Cancel resolved still (kein Event, Log-Eintrag). Ungültige Antwort („vielleicht") auf yesno → Service-Fehler.
