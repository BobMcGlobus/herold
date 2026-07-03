# Herold 📯

> **⚠️ Alpha — Not for production.** Diese Integration ist in aktiver Entwicklung (Phase 1 / MVP). API und Config-Format können sich noch ändern.

**Herold** ist eine Home Assistant Custom Integration für priorisierte Omnichannel-Benachrichtigungen: raumbewusste Sprachausgabe über Assist-Satelliten und Media Player, Push auf die Mobile App, mit DND-Logik, Offline-TTS-Fallback und einem 5-stufigen Prioritätsmodell.

Herold ist der Nachfolger des Scripts `System: Universal Omnichannel Communicator (Priority Edition)` — als wartbare, testbare Integration mit UI-Konfiguration.

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

Der Config Flow führt durch sechs Schritte:

1. **Grundlagen** — Empfänger-Person, Name der Instanz
2. **Räume** (wiederholbar) — pro Raum: Präsenzsensoren (mehrere möglich, ODER-verknüpft), Assist-Satellit und/oder Media Player, optional Licht für den P4-Alarm-Flash
3. **Sprache** — primäres TTS (z.B. ElevenLabs), optionales Fallback-TTS (z.B. Piper), Internet-Erkennungssensor
4. **Push** — Mobile-App-Notify-Entitäten
5. **Nicht stören** — optionale externe DND-Entität, interner DND-Schalter
6. **Offline** — Offline-TTS-Fallback (opt-in), Offline-Warteschlange (Phase 2)

Alle Sektionen sind später über die Integrations-Optionen editierbar; Räume können ohne Neueinrichtung hinzugefügt, bearbeitet und entfernt werden.

## Feature-Matrix Phase 1

| Feature | Status |
|---|---|
| `herold.send` Service (P0–P4) | ✅ |
| Raumbewusste Voice-Delivery (Occupancy → Satellit) | ✅ |
| Multi-Occupancy-Sensoren pro Raum (ODER-verknüpft) | ✅ |
| Media-Player-Only-Räume (`tts.speak` Fallback) | ✅ |
| TTS-Kette: Primär → Offline-Fallback (z.B. ElevenLabs → Piper) | ✅ |
| Mobile App Push (critical Sound für P4) | ✅ |
| P4 Licht-Flash vor der Durchsage | ✅ |
| DND-Schalter + externe DND-Entität | ✅ |
| Debug-Entities (letzte Zustellung, Online, DND aktiv) | ✅ |
| Test-Button | ✅ |
| Query-Modus (Ja/Nein-Fragen), Telegram | 🔜 Phase 2 |
| P0 Self-Callback, Scheduler, LLM-Tools, Todo | 🔜 Phase 3 |
| Templates, Rate-Limiting, DND-Sessions | 🔜 Phase 4 |

Die vollständige Roadmap steht in [HEROLD_PLAN.md](HEROLD_PLAN.md).

## Service: `herold.send`

```yaml
service: herold.send
data:
  message: "Die Waschmaschine ist fertig"
  priority: 2          # 0 intern · 1 todo · 2 normal · 3 wichtig · 4 alarm
  # title: "Optionaler Push-Titel"
  # target_player: assist_satellite.wohnzimmer_sattelite_assist_satellit
  # tag: waschmaschine
  # ttl_minutes: 30
  # callback_event: AI_CONFIRM
```

### Prioritätsmodell

| Prio | Name | Verhalten (Phase 1) |
|---|---|---|
| 0 | Intern | Wird geskippt (LLM-Self-Callback kommt in Phase 3) |
| 1 | Todo | Nur wenn zuhause & kein DND (Todo-Liste kommt in Phase 3) |
| 2 | Normal | Voice wenn zuhause, sonst Push; blockiert bei DND |
| 3 | Wichtig | Voice + Push, ignoriert DND |
| 4 | Alarm | Warn-Durchsage + Licht-Flash + Critical Push, ignoriert DND |

## Migration vom Script

Herold ist als Drop-in-Nachfolger des Omnichannel-Communicator-Scripts konzipiert:

- **`input_boolean.notification_blocker`** kann im DND-Schritt als *externe DND-Entität* eingetragen werden — bestehende Automationen (Goodnight, Sport-Popup) bleiben unverändert.
- **Callback-Events bleiben bit-exakt kompatibel:** `callback_event: AI_CONFIRM` (Default) feuert `AI_YES` / `AI_NO` — **ohne** CONFIRM-Teil, exakt wie das Original-Script. Ein Custom-Callback `XYZ` feuert `XYZ_YES` / `XYZ_NO`. (Das eigentliche Query-Handling mit Telegram-Buttons landet in Phase 2; die Event-Semantik ist bereits in `legacy_compat.py` festgeschrieben.)
- **Empfohlener Rollout:** Integration parallel zum Script installieren, Verhalten vergleichen, Automationen schrittweise auf `herold.send` migrieren, Script erst nach zwei stabilen Wochen löschen.

## Entwicklung

```bash
./scripts/setup-dev.sh /pfad/zu/ha-config   # symlinkt die Integration
```

Manuelle Testfälle: [PHASE_1_TESTPLAN.md](PHASE_1_TESTPLAN.md)

## Lizenz

[MIT](LICENSE)
