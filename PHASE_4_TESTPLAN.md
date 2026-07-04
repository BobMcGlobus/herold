# Phase 4 — Manueller Testplan (Casa de Jonas)

Voraussetzungen: Phase-1/2/3-Setup. Log-Level: `custom_components.herold: debug`.

---

## TC1 — Drop-Reason sichtbar (Nachtest zu Phase-3-TC2)

- **Aktion:** DND aktivieren, `herold.send` mit `priority: 2`.
- **Erwartet:** `sensor.herold_letzte_zustellung` zeigt Attribut `reason: "priority 2 blocked by DND"` — kein Log-Graben mehr nötig. Gleiches bei Rate-Limit-Drops.

## TC2 — Voice-Timeout: Buttons nach Telegram

- **Setup:** Zuhause, Arbeitszimmer occupied.
- **Aktion:** `herold.query` mit `mode: yesno`, `priority: 2`, `voice_timeout_seconds: 30`. Am Sat NICHT antworten.
- **Erwartet:** Frage wird per start_conversation gestellt; nach ~30 s kommt die Telegram-Nachricht mit den Ja/Nein-Buttons nach (Debug-Log „no voice answer within 30 s"). Antwort per Button funktioniert normal. Wer am Sat antwortet, bevor das Fenster abläuft: kein Telegram.

## TC3 — Escalation-Chain

- **Aktion:** `herold.query`, `priority: 2`, `escalation: [{"after_minutes": 1, "raise_to_priority": 3}, {"after_minutes": 2, "raise_to_priority": 4}]`. Nicht antworten.
- **Erwartet:** Nach 1 min: erneute Zustellung als P3 (Push „⚠️" + Telegram), Event `herold_escalated {from_priority: 2, to_priority: 3}`, `binary_sensor.herold_eskalation_aktiv` = on. Nach 2 min: P4 (Critical Push, Warn-Announce). Antwort beendet alles; Sensor geht auf off.

## TC4 — Escalation überlebt Neustart

- **Aktion:** Query mit `escalation: [{"after_minutes": 10, "raise_to_priority": 3}]`, nach 2 min HA neu starten.
- **Erwartet:** Escalation feuert trotzdem ~10 min nach Erstellung (Re-Arm beim Boot; bereits verstrichene Regeln werden übersprungen).

## TC5 — P3-Dedup (Rate-Limit)

- **Aktion:** 3× schnell hintereinander `herold.send`, `priority: 3`, `tag: fenster_offen`.
- **Erwartet:** Nur die erste wird zugestellt; #2/#3 gedroppt mit `reason: P3 cooldown (60s)…`. Nach 60 s geht es wieder. Mit `ignore_rate_limit: true` kommen alle durch.

## TC6 — P2-Aggregation

- **Aktion:** 5× schnell `herold.send`, `priority: 2` (verschiedene Nachrichten), zuhause, Raum occupied.
- **Erwartet:** #1–#3 einzeln zugestellt; #4/#5 gepuffert (`reason: P2 rate limit…`). Nach Ablauf des 5-min-Fensters eine Sammel-Durchsage „2 Meldungen: …".

## TC7 — DND-Session `until`

- **Aktion:** `herold.dnd_on` mit `until: "+2m"`. P2 senden (→ dropped). 2 min warten.
- **Erwartet:** `switch.herold_dnd` geht automatisch aus (Debug-Log „DND session ended"); P2 kommt danach wieder durch.

## TC8 — DND-Session `until_home`

- **Aktion:** `person.jonas` auf not_home, `herold.dnd_on` mit `until_home: true`, dann nach Hause kommen (oder Zone simulieren).
- **Erwartet:** Beim Wechsel auf `home` endet die Session automatisch.

## TC9 — DND-Session überlebt Neustart

- **Aktion:** `herold.dnd_on` mit `until: "+30m"`, HA neu starten.
- **Erwartet:** DND weiterhin an, Auto-Off-Timer läuft weiter. Gegenprobe: Session mit `+2m`, HA 5 min gestoppt lassen → nach dem Boot ist DND aus (abgelaufene Session wird nicht restauriert, auch nicht vom Switch-Restore).

## TC10 — Manuelles Aus beendet Session

- **Aktion:** `herold.dnd_on` mit `until: "+1h"`, dann den Schalter manuell ausschalten.
- **Erwartet:** DND aus UND Session gelöscht — sie reaktiviert sich nicht.

## TC11 — Vorlagen

- **Setup:** Optionen → Vorlagen → hinzufügen: Name `appliance_done`, Nachricht `{{ appliance }} ist fertig`, Priorität 2.
- **Aktion:** `herold.send` mit `template: appliance_done`, `template_vars: {"appliance": "Waschmaschine"}`.
- **Erwartet:** Durchsage „Waschmaschine ist fertig". Explizites `priority: 3` im Call überschreibt die Vorlagen-Priorität. Unbekannter Vorlagenname → Service-Fehler mit Liste der verfügbaren Vorlagen.

## TC12 — Next-Schedule-Sensor

- **Aktion:** Zwei Schedules anlegen (`+10m`, `+5m`).
- **Erwartet:** `sensor.herold_naechste_zustellung` zeigt den +5m-Zeitpunkt (Timestamp, HA rendert „in 5 Minuten") mit message/id in den Attributen; `scheduled_count` = 2 mit voller Liste. Nach dem Feuern springt der Sensor auf den nächsten Eintrag.
