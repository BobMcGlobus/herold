# Phase 3 — Manueller Testplan (Casa de Jonas)

Voraussetzungen: Phase-1/2-Setup, zusätzlich in den Optionen:

- **LLM:** P0-Agent = Gemini 2.5 Flash (`conversation.google_ai_conversation`), Fallback = lokaler Ollama (optional)
- **Prompt-Template des Agents** ergänzt um: „Nachrichten mit [HEROLD_INTERNAL] sind interne Reminder von dir selbst. Führe die Anweisung stumm aus, antworte nicht dem User."
- **LLM-API „Herold"** beim Agent aktiviert (Sprachassistenten → Agent → LLM-APIs)

---

## TC1 — P1 landet in der Todo-Inbox

- **Aktion:** `herold.send` mit `priority: 1`, `message: "Post im Briefkasten"`. DND-Zustand egal.
- **Erwartet:** Kein Voice/Push/Telegram. Item „Post im Briefkasten" erscheint in `todo.herold_eingang` (status: offen). `herold_delivered` mit `channel: todo`. Item überlebt HA-Neustart.

## TC2 — P0 Internal: sofortige Ausführung

- **Aktion:** `herold.send` mit `priority: 0`, `message: "Sage per herold.send priority=2: Internal-Test erfolgreich"`.
- **Erwartet:** `conversation.process` an Gemini mit Text `[HEROLD_INTERNAL] Sage per…`. Event `herold_internal_triggered` mit instruction + agent_id. Kurz darauf die P2-Durchsage — der Agent hat die Instruktion ausgeführt.

## TC3 — herold.schedule: relative Zeit

- **Aktion:** `herold.schedule` mit `scheduled_for: "+2m"`, `message: "Scheduler-Test"`, `priority: 2`.
- **Erwartet:** `herold_scheduled` Event sofort; `sensor.herold_scheduled_count` = 1 mit Details in den Attributen. Nach ~2 min normale P2-Zustellung, Zähler zurück auf 0.

## TC4 — Schedule überlebt Neustart + Grace

- **Aktion:** a) `herold.schedule` mit `+30m`, HA neu starten → Schedule weiterhin im Sensor, feuert pünktlich. b) `+2m` planen, HA sofort stoppen, nach ~4 min starten → Zustellung „nachgeholt" (innerhalb 5-min-Grace). c) HA >10 min gestoppt lassen → `herold_expired` mit `reason: missed`.

## TC5 — herold.remind_self End-to-End

- **Aktion:** `herold.remind_self` mit `when: "+2m"`, `instruction: "Schalte die Schreibtischlampe ein."`.
- **Erwartet:** Nach 2 min geht die Lampe an — ohne Durchsage, ohne Push. `herold_internal_triggered` im Event-Log.

## TC6 — P0 Anti-Runaway

- **Aktion:** >20× `herold.send` mit `priority: 0` innerhalb einer Stunde (Script-Schleife).
- **Erwartet:** Ab dem 21. Call: kein conversation.process mehr, Debug-Log „P0 rate limit reached", Fehler in den `last_delivery`-Attributen.

## TC7 — LLM-Tool list_pending via Voice

- **Setup:** Ein P1-Todo (TC1) und eine offene Query anlegen.
- **Aktion:** Am Sat: „Was ist neu?" / „Gibt es was für mich?"
- **Erwartet:** Der Agent ruft `herold_list_pending` und nennt Todo + offene Frage (im Agent-Debug-Log prüfen).

## TC8 — LLM-Tool acknowledge

- **Aktion:** Nach TC7: „Die Post hab ich schon geholt."
- **Erwartet:** Agent ruft `herold_acknowledge(id=…)`; das Item in `todo.herold_eingang` wird als erledigt markiert.

## TC9 — LLM-Tool answer_query mit Fuzzy-Matching

- **Setup:** `herold.query` mit `mode: yesno` offen.
- **Aktion:** Am Sat: „Klar, mach das."
- **Erwartet:** Agent ruft `herold_answer_query(id, answer="Ja")` → `herold_answered` + `AI_YES`, Query resolved.

## TC10 — LLM-Tool remind_self via Voice

- **Aktion:** Am Sat: „Erinnere mich in 10 Minuten daran, den Ofen auszuschalten."
- **Erwartet:** Agent ruft `herold_remind_self(when='+10m', instruction=…)`; `sensor.herold_scheduled_count` steigt. Nach 10 min führt ein frischer Agent-Kontext die Instruktion aus (typisch: P2/P3-Durchsage via herold.send).

## TC11 — P0-Fallback-Agent bei Offline

- **Setup:** Fallback-Agent (Ollama) konfiguriert, Internet-Sensor off (Gemini nicht erreichbar).
- **Aktion:** `herold.remind_self` mit `when: "+1m"`.
- **Erwartet:** Primary schlägt fehl, Warning-Log „retrying with fallback", Instruktion läuft über Ollama. Ohne Fallback-Agent: Fehler in den Delivery-Errors.

## TC12 — Todo-Inbox UI-Roundtrip

- **Aktion:** In der HA-Todo-Ansicht manuell ein Item anlegen, eines abhaken, eines löschen; HA neu starten.
- **Erwartet:** Alle Änderungen persistent (Store), `binary_sensor`/Sensoren unbeeinflusst.

## TC13 — cancel für Schedules

- **Aktion:** `herold.schedule` mit `+30m`, dann `herold.cancel` mit der Schedule-ID (aus den Sensor-Attributen).
- **Erwartet:** Schedule verschwindet aus dem Sensor, feuert nicht. Unbekannte ID → Service-Fehler.
