# Migrating From `cradlewise_local`

The pre-release integration used the `cradlewise_local` domain. The HACS
integration uses `cradlewise`. Home Assistant does not support moving a config
entry across custom-integration domains, so the safe migration is a
side-by-side setup followed by an entity-ID handoff.

Do not edit `.storage` files. And do not remove the old entry until the new one
has current state and a working command provider.

## Before migrating

1. Create a Home Assistant backup.
2. Record automations, scripts, dashboards, scenes, and HomeKit bridges that
   reference `cradlewise_local` entities.
3. If any old entity is exposed to Apple Home, record its AID/IID mapping and
   keep the existing HomeKit bridge and pairing. Removing or rebuilding the
   HomeKit bridge can reset room placement, names, favorites, scenes, and
   automations in Apple Home.

## Side-by-side validation

1. Install the new `cradlewise` component and restart Home Assistant.
2. Add Cradlewise in Automatic, Local only, or Cloud only mode.
3. If video is wanted, configure the optional media companion and verify the
   camera before touching the old entry.
4. Confirm that state is current, the expected provider is active, and one
   normal control command is reported back by the crib.

The retained entity unique-ID suffixes are:

- Binary sensors: `bridge_healthy`, `baby_present`, `baby_needs_attention`,
  `baby_needs_help`, `crib_helping`, `light_on`, `loud_sound_detected`,
  `rocking_not_effective`, `obstruction_detected`, and
  `lower_breath_rate_alert`
- Sensors: `sleep_state`, `sleep_phase`, `bounce_time_remaining`, `music_mood`,
  `music_time_remaining`, `ambient_temperature`, and `breath_rate`
- Controls: `bounce_level`, `music_level`, `bounce_amplitude`,
  `bounce_duration`, `music_volume`, `bounce_mode`, `music_mode`,
  `music_duration`, `actuator_on`, `music_playing`, and
  `adaptive_soothing_enabled`
- Optional media: `camera`

State source and update time also remain available as disabled diagnostics.
Analytics, raw shadow fields, calibration state, debug actions, upload flags,
recipe internals, and firmware actions are intentionally not migrated.

## Entity-ID handoff

After the new entry is verified:

1. Remove the old `cradlewise_local` config entry so its entity IDs are freed.
2. Rename each retained new entity to the old entity ID used by your consumers,
   or update those consumers to the new entity ID.
3. Reload automations and dashboards, then verify every recorded reference.
4. Remove `/config/custom_components/cradlewise_local` and restart Home
   Assistant only after no old config entry remains.
5. Confirm that any HomeKit AID/IID mapping still identifies the same physical
   crib before deleting the backup.

There can be a short unavailable window between removing the old entry and
assigning its entity IDs to the new entities. Existing automations recover as
soon as those exact entity IDs exist again.

If the new entities briefly recorded state under their generated IDs before
the handoff, Recorder can log a one-time warning that it could not merge that
temporary history into an old ID which already has history. Keep the old ID's
existing history. The warning does not affect current state or future history
after the handoff.
