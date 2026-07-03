# Phase 1 — Manueller Testplan (Casa de Jonas)

Referenz-Setup laut `rooms.md`:

| Raum | Occupancy | Sat | Media Player | Licht |
|---|---|---|---|---|
| Wohnzimmer+Küche | `binary_sensor.presence_sensor_fp2_997d_presence_sensor_1`, `binary_sensor.presence_sensor_fp2_e01b_presence_sensor_1` | `assist_satellite.wohnzimmer_sattelite_assist_satellit` | `media_player.wohnzimmer_sattelite_media_player` | — |
| Badezimmer | `binary_sensor.badezimmer_mmwave_belegung_2` | — | `media_player.sonos_roam` | — |
| Arbeitszimmer | `binary_sensor.everything_presence_lite_9234a8_occupancy` | `assist_satellite.arbeitszimmer_sattelite_assist_satellit` | `media_player.arbeitszimmer_sattelite_media_player` | `light.schreibtisch_ambiente_leuchte` |

Weitere Konfiguration: primäres TTS `tts.elevenlabs_text_zu_sprache`, Fallback `tts.piper`, Internet-Sensor `binary_sensor.martinrouterking_port_1_online_erkennung`, externe DND-Entität `input_boolean.notification_blocker`, Push `notify.mobile_app_iphone_von_jonas`, Person `person.jonas`.

Log-Level für Checks: `custom_components.herold: debug` in `logger:`.

---

## TC1 — P2 zuhause, Wohnzimmer occupied → Voice via Wohnzimmer-Sat

- **Setup:** `person.jonas` = home, einer der Wohnzimmer-FP2s = on, DND aus, Internet on.
- **Aktion:** `herold.send` mit `message: "Testfall 1"`, `priority: 2`.
- **Erwartet:** `assist_satellite.announce` auf dem Wohnzimmer-Sat. Kein Push. `sensor.herold_last_delivery` = `voice`, Attribut `room` = `Wohnzimmer+Küche`. Event `herold_delivered` mit `channel: voice`.

## TC2 — P2 zuhause, Bad occupied → Media-Player-Only-Fallback

- **Setup:** Nur `binary_sensor.badezimmer_mmwave_belegung_2` = on, sonst wie TC1.
- **Aktion:** `herold.send`, `priority: 2`.
- **Erwartet:** `tts.speak` mit `entity_id: tts.elevenlabs_text_zu_sprache` und `media_player_entity_id: media_player.sonos_roam`. Kein `assist_satellite.announce`. Beweist: Media-Player-Only-Räume funktionieren.

## TC3 — P3 nicht zuhause → nur Push

- **Setup:** `person.jonas` = not_home (Occupancy-Zustand egal).
- **Aktion:** `herold.send`, `priority: 3`.
- **Erwartet:** Push auf `notify.mobile_app_iphone_von_jonas` mit Titel „⚠️ Wichtige Mitteilung" und Sound-Volume 0.8. Keine Voice-Delivery. `sensor.herold_last_delivery` = `push`.

## TC4 — P4 im Arbeitszimmer → Warn-Prefix + Licht-Flash + Critical Push

- **Setup:** Zuhause, nur Arbeitszimmer occupied, DND egal (P4 ignoriert DND).
- **Aktion:** `herold.send`, `priority: 4`.
- **Erwartet (Reihenfolge):**
  1. `light.turn_on` auf `light.schreibtisch_ambiente_leuchte` mit `flash: short`, rot, Brightness 255
  2. Announce „ACHTUNG! KRITISCHE MELDUNG!", 3 s Pause, dann die Nachricht
  3. Push mit Titel „🚨 KRITISCHER ALARM" und `critical: 1`, `volume: 1`

## TC5 — DND aktiv, P2 → dropped

- **Setup:** Zuhause, `switch.herold_dnd` = on.
- **Aktion:** `herold.send`, `priority: 2`.
- **Erwartet:** Keine Delivery. Debug-Log: `Dropping notification <id>: priority 2 blocked by DND`. `binary_sensor.herold_dnd_active` = on.

## TC6 — DND aktiv, P3 → durchgestellt

- **Setup:** Wie TC5.
- **Aktion:** `herold.send`, `priority: 3`.
- **Erwartet:** Voice + Push werden zugestellt — P3 ignoriert DND.

## TC7 — Externe DND-Entität, P2 → dropped

- **Setup:** `switch.herold_dnd` = off, aber `input_boolean.notification_blocker` = on.
- **Aktion:** `herold.send`, `priority: 2`.
- **Erwartet:** Wie TC5 gedroppt. Beweist: Backward-Compat mit dem bestehenden Blocker; `binary_sensor.herold_dnd_active` = on obwohl der interne Schalter aus ist.

## TC8 — Offline ohne Fallback, P2 → Voice skip, Push versucht

- **Setup:** Zuhause, Wohnzimmer occupied, `binary_sensor.martinrouterking_port_1_online_erkennung` = off, `enable_offline_fallback: false`.
- **Aktion:** `herold.send`, `priority: 2`.
- **Erwartet:** Debug-Log `Voice skipped … offline and no offline fallback configured`. Push wird als Fallback versucht und scheitert mangels Internet — Fehler erscheint im Log und in den Attributen von `sensor.herold_last_delivery` (`errors`). `binary_sensor.herold_online` = off. (Echte Offline-Queue kommt in Phase 2.)

## TC9 — Offline mit Fallback, P2 → Voice via Piper

- **Setup:** Wie TC8, aber `enable_offline_fallback: true` und `fallback_tts_entity: tts.piper`. Bad occupied (Media-Player-Pfad, da Sat-Announce kein TTS-Entity nutzt).
- **Aktion:** `herold.send`, `priority: 2`.
- **Erwartet:** `tts.speak` mit `entity_id: tts.piper` auf `media_player.sonos_roam`. Die TTS-Kette hat auf das Offline-Fallback gewechselt.

## TC10 — Multi-Occupancy: nur einer von zwei FP2s → Raum aktiv

- **Setup:** Zuhause. Nur `binary_sensor.presence_sensor_fp2_e01b_presence_sensor_1` = on, der andere FP2 = off.
- **Aktion:** `herold.send`, `priority: 2`.
- **Erwartet:** Wohnzimmer+Küche gilt als occupied (ODER-Verknüpfung), Announce über den Wohnzimmer-Sat. Gegenprobe: beide FP2s off → kein aktiver Raum, Voice wird geskippt (Debug-Log).

---

## Zusatz-Checks (nicht nummeriert)

- **Test-Button:** `button.herold_test` drücken → P2-Nachricht „Herold Test-Nachricht — funktioniert" durchläuft die volle Pipeline.
- **target_player-Override:** `herold.send` mit `target_player: media_player.sonos_roam` bei occupied Arbeitszimmer → Ausgabe auf dem Roam, nicht im Arbeitszimmer (Original-Script-Verhalten).
- **Restart-Restore:** DND-Schalter einschalten, HA neu starten → Schalter ist wieder on (RestoreEntity).
- **Options Flow:** Raum hinzufügen/bearbeiten/entfernen über die Integrations-Optionen → Entry lädt neu, keine Neueinrichtung nötig.
