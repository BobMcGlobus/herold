# Herold — Konsolidierter Testplan (Copy-Paste-Edition)

Alle noch offenen bzw. wiederholbaren Tests mit fertigen YAML-Snippets für
**Entwicklerwerkzeuge → Aktionen → YAML-Modus**. Einfach reinpasten und ausführen.

**Vorbereitung einmalig:**

- Log-Level: `custom_components.herold: debug` in der `logger:`-Config
- Zweiter Browser-Tab: **Entwicklerwerkzeuge → Ereignisse** und dort auf
  `herold_delivered`, `herold_answered`, `herold_escalated`, `herold_expired`,
  `herold_scheduled`, `herold_internal_triggered`, `AI_YES`, `AI_NO` lauschen
- Ab v0.6.0: Die **Herold-Karte** (Logbuch-Tab) zeigt alle Ereignisse live —
  ersetzt für die meisten Checks das Log-Graben.
- Entity-Namen unten sind die deutschen Defaults; bei dir ggf. per
  Autocomplete prüfen (`sensor.herold_…`).

Legende: ☐ = offen · Nummern referenzieren die ursprünglichen Phasen-Testpläne.

---

## 1. Basis-Checks (nach jedem Update)

### ☐ B1 — Testnachricht (P2 Voice)

```yaml
action: herold.send
data:
  message: Basischeck — hörst du mich?
  priority: 2
```

**Erwartet:** Ansage im aktiven Raum. `sensor.herold_letzte_zustellung` = `voice`, Attribut `room` gesetzt.

### ☐ B2 — Drop-Reason sichtbar (P4-TC1, Nachtest!)

DND einschalten (`switch.herold_dnd`), dann:

```yaml
action: herold.send
data:
  message: Dieser Text darf NICHT ankommen
  priority: 2
```

**Erwartet:** Keine Zustellung. `sensor.herold_letzte_zustellung` → Attribut `reason: priority 2 blocked by DND`. Im Logbuch-Tab der Karte: Eintrag „Verworfen". *(Braucht ≥ v0.4.0 — wenn `reason` fehlt: HACS-Update + Neustart prüfen!)* DND danach wieder aus.

---

## 2. Scheduler (P3-TC4, P3-TC13)

### ☐ S1 — Schedule überlebt Neustart

```yaml
action: herold.schedule
data:
  scheduled_for: "+30m"
  message: Neustart-Test — ich habe überlebt
  priority: 2
```

Dann HA neu starten. **Erwartet:** `sensor.herold_geplante_benachrichtigungen` zeigt den Eintrag weiterhin (Karte → Tab „Geplant"), Zustellung pünktlich.

### ☐ S2 — Grace-Period für verpasste Zustellungen

```yaml
action: herold.schedule
data:
  scheduled_for: "+2m"
  message: Grace-Test — nachgeholt
  priority: 2
```

HA sofort stoppen, nach ~4 min starten. **Erwartet:** Zustellung direkt nach dem Boot (5-min-Grace). Gegenprobe mit >10 min Downtime: `herold_expired` mit `reason: missed`, keine Zustellung.

### ☐ S3 — Schedule canceln

```yaml
action: herold.schedule
data:
  scheduled_for: "+30m"
  message: Diesen bitte canceln
```

ID aus der Karte (Tab „Geplant" → ✕) oder aus den Sensor-Attributen, dann:

```yaml
action: herold.cancel
data:
  id: DEINE_ID_HIER
```

**Erwartet:** Eintrag verschwindet, feuert nicht. Unbekannte ID → Fehlermeldung.

---

## 3. P0 / Internal (P3-TC6, P3-TC11)

### ☐ I1 — Anti-Runaway (20/h)

Einmalig ein Test-Script anlegen (Einstellungen → Automationen → Skripte → neu → YAML):

```yaml
alias: Herold P0 Runaway Test
sequence:
  - repeat:
      count: 22
      sequence:
        - action: herold.send
          data:
            message: "Sage nichts, antworte nicht. Runaway-Test {{ repeat.index }}."
            priority: 0
```

**Erwartet:** Ab Nr. 21: Debug-Log `P0 rate limit reached`, Fehler im `errors`-Attribut der letzten Zustellung. Logbuch-Tab zeigt die Drops.

### ☐ I2 — Fallback-Agent (sobald lokales LLM da ist)

Optionen → LLM → Fallback-Agent setzen, Internet-Sensor auf off bringen, dann:

```yaml
action: herold.remind_self
data:
  when: "+1m"
  instruction: Schalte die Schreibtischlampe ein.
```

**Erwartet:** Warning-Log `retrying with fallback`, Instruktion läuft über den lokalen Agent.

---

## 4. Todo-Inbox (P3-TC12)

### ☐ T1 — P1 → Inbox + UI-Roundtrip

```yaml
action: herold.send
data:
  message: Post im Briefkasten
  priority: 1
```

**Erwartet:** Item erscheint in der Karte (Tab „Inbox") bzw. `todo.herold_eingang` — ohne Voice/Push. In der Karte per ✓ abhaken, per 🗑 löschen, HA neu starten → Zustand bleibt erhalten.

---

## 5. Queries: Escalation & Voice-Timeout (P4-TC2 bis TC4)

### ☐ Q1 — Voice-Timeout: Buttons nach Telegram

Im aktiven Raum ausführen und am Sat **nicht** antworten:

```yaml
action: herold.query
data:
  question: Voice-Timeout-Test — nicht am Satelliten antworten!
  mode: yesno
  priority: 2
  voice_timeout_seconds: 30
```

**Erwartet:** Nach ~30 s Telegram-Nachricht mit Ja/Nein-Buttons. Button-Antwort → `herold_answered` + `AI_YES`/`AI_NO`.

### ☐ Q2 — Escalation-Chain

```yaml
action: herold.query
data:
  question: Eskalations-Test — bitte 2 Minuten ignorieren
  mode: yesno
  priority: 2
  escalation:
    - after_minutes: 1
      raise_to_priority: 3
    - after_minutes: 2
      raise_to_priority: 4
```

**Erwartet:** Nach 1 min P3-Redelivery (⚠️-Push + Telegram), Event `herold_escalated`, `binary_sensor.herold_eskalation_aktiv` = on. Nach 2 min P4 (Critical Push + Warn-Announce). Antwort beendet alles.

### ☐ Q3 — Escalation überlebt Neustart

Wie Q2, aber `after_minutes: 10` — nach 2 min HA neu starten. **Erwartet:** Escalation feuert trotzdem ~10 min nach Erstellung.

### ☐ Q4 — Timeout mit default_answer (P2-TC7)

```yaml
action: herold.query
data:
  question: Timeout-Test — nicht antworten
  mode: yesno
  timeout_minutes: 1
  default_answer: Nein
```

**Erwartet:** Nach ~1 min `herold_answered` mit `answer: Nein`, `source_channel: timeout`, plus `AI_NO`.

### ☐ Q5 — Choice per Karte beantworten

```yaml
action: herold.query
data:
  question: Was gibt es zum Abendessen?
  mode: choice
  choices:
    - Pizza
    - Pasta
    - Salat
  priority: 2
```

**Erwartet:** Karte (Tab „Inbox") zeigt die Frage mit drei Buttons; Klick resolved die Query (`herold_answered` mit der Option). Parallel Telegram-Buttons, wenn kein Sat den Answer einfangen kann.

---

## 6. Rate-Limiting (P4-TC5, TC6)

### ☐ R1 — P3-Dedup

Dreimal schnell hintereinander ausführen:

```yaml
action: herold.send
data:
  message: Fenster offen!
  priority: 3
  tag: fenster
```

**Erwartet:** Nur die erste kommt durch; #2/#3 mit `reason: P3 cooldown (60s)…` (Karte → Logbuch: „Rate-Limit"). Bypass-Gegenprobe:

```yaml
action: herold.send
data:
  message: Fenster offen — Bypass
  priority: 3
  tag: fenster
  ignore_rate_limit: true
```

### ☐ R2 — P2-Aggregation

Fünfmal schnell hintereinander (Nachricht variieren: Test 1…5):

```yaml
action: herold.send
data:
  message: Aggregations-Test 1
  priority: 2
```

**Erwartet:** #1–#3 einzeln; #4/#5 gepuffert; nach Ablauf des 5-min-Fensters eine Sammel-Durchsage „2 Meldungen: …".

---

## 7. DND-Sessions (P4-TC7 bis TC10)

### ☐ D1 — Auto-Off nach Zeit

```yaml
action: herold.dnd_on
data:
  until: "+2m"
```

**Erwartet:** `switch.herold_dnd` an; P2 wird gedroppt; nach 2 min geht der Schalter von selbst aus.

### ☐ D2 — Bis zuhause

```yaml
action: herold.dnd_on
data:
  until_home: true
```

**Erwartet:** DND endet automatisch, sobald `person.jonas` auf `home` wechselt.

### ☐ D3 — Session überlebt Neustart

`until: "+30m"` setzen, HA neu starten → DND weiter an, Auto-Off läuft. Gegenprobe: `+2m` setzen, HA 5 min gestoppt lassen → nach Boot ist DND **aus**.

### ☐ D4 — Manuell aus killt die Session

`until: "+1h"` setzen, dann `switch.herold_dnd` manuell aus → bleibt aus, reaktiviert sich nicht.

---

## 8. Vorlagen (P4-TC11)

Einmalig: Optionen → Vorlagen → hinzufügen — Name `appliance_done`, Nachricht `{{ appliance }} ist fertig`, Priorität 2. Dann:

```yaml
action: herold.send
data:
  template: appliance_done
  template_vars:
    appliance: Waschmaschine
```

**Erwartet:** Durchsage „Waschmaschine ist fertig". Mit zusätzlichem `priority: 3` im Call gewinnt der Call. Unbekannter Name → Fehler mit Liste der Vorlagen.

---

## 9. LLM-Tools per Voice (P3-TC7 bis TC10 — kein YAML, sprechen!)

Voraussetzung: LLM-API „Herold" beim Agent aktiviert, System-Prompt-Block aus dem README eingefügt, **altes `script.ai_schedule_command` aus der Assist-Exposure entfernt**.

- ☐ V1: T1-Todo anlegen, dann am Sat: *„Was ist neu?"* → Agent nennt das Todo (`herold_list_pending`)
- ☐ V2: *„Die Post hab ich schon geholt."* → Todo wird abgehakt (`herold_acknowledge`)
- ☐ V3: Q-Test offen lassen, dann: *„Klar, mach das."* → `herold_answered` mit „Ja" (`herold_answer_query`)
- ☐ V4: *„Erinnere mich in 10 Minuten, den Ofen auszuschalten."* → Eintrag in Karte/„Geplant" (`herold_remind_self`), **nicht** im alten Kalender!

---

## 10. Karte & History (neu in v0.6.0)

- ☐ K1: Karte hinzufügen (Dashboard → Karte → „Herold Card" oder YAML `type: custom:herold-card`) — alle drei Tabs füllen sich ohne weitere Config
- ☐ K2: Logbuch-Tab zeigt nach B1/B2 „Zugestellt"/„Verworfen" mit Grund; Einträge überleben Neustart (max. 50)
- ☐ K3: Tab „Geplant": ✕ cancelt wirklich (Gegencheck: `sensor.herold_naechste_zustellung` springt um)
