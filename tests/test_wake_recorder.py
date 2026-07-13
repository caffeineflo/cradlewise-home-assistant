from pathlib import Path

EXAMPLE_DIR = Path("examples/home-assistant/wake-recorder")
AUTOMATIONS_PATH = EXAMPLE_DIR / "automations.yaml"
SHELL_COMMANDS_PATH = EXAMPLE_DIR / "shell_commands.yaml"
CARD_PATH = EXAMPLE_DIR / "cradlewise-wake-card.js"
DOCS_PATH = Path("docs/process/wake-event-recording.md")


def test_wake_recording_uses_native_camera_action():
    automation = AUTOMATIONS_PATH.read_text()

    assert "action: camera.record" in automation


def test_wake_recording_targets_live_camera_entity():
    automation = AUTOMATIONS_PATH.read_text()

    assert "entity_id: camera.cradlewise_local_2" in automation


def test_wake_recording_preserves_two_minute_pre_and_post_windows():
    automation = AUTOMATIONS_PATH.read_text()

    assert "duration: 120\n        lookback: 120" in automation


def test_wake_recording_uses_authenticated_media_path_only():
    automation = AUTOMATIONS_PATH.read_text()

    assert (
        "/media/cradlewise-wake/events/" in automation
        and "/config/www" not in automation
    )


def test_wake_recording_uses_native_baby_present_condition():
    automation = AUTOMATIONS_PATH.read_text()

    expected = '''condition: state
      entity_id: binary_sensor.cradlewise_local_baby_present
      state: "on"'''
    assert expected in automation


def test_wake_recording_preserves_existing_trigger_entities():
    automation = AUTOMATIONS_PATH.read_text()
    trigger_entities = {
        "sensor.cradlewise_local_sleep_phase",
        "sensor.cradlewise_local_sleep_state",
        "binary_sensor.cradlewise_local_baby_needs_attention",
        "binary_sensor.cradlewise_local_baby_needs_help",
    }

    assert all(entity_id in automation for entity_id in trigger_entities)


def test_attention_and_help_trigger_only_when_turned_on():
    automation = AUTOMATIONS_PATH.read_text()
    triggers = {
        '''entity_id: binary_sensor.cradlewise_local_baby_needs_attention
      to: "on"''',
        '''entity_id: binary_sensor.cradlewise_local_baby_needs_help
      to: "on"''',
    }

    assert all(trigger in automation for trigger in triggers)


def test_wake_recording_preserves_transition_matrix():
    automation = AUTOMATIONS_PATH.read_text()
    transitions = {
        'from: "sleep"\n      to: "awake"',
        'from: "sleep"\n      to: "stirring"',
        'from: "Light sleep"\n      to: "Quite Awake"',
        'from: "Light sleep"\n      to: "Active Awake"',
        'from: "Deep sleep"\n      to: "Quite Awake"',
        'from: "Deep sleep"\n      to: "Active Awake"',
    }

    assert all(transition in automation for transition in transitions)


def test_loud_sound_remains_non_triggering():
    automation = AUTOMATIONS_PATH.read_text()

    assert "binary_sensor.cradlewise_local_loud_sound_detected" not in automation


def test_wake_recording_has_no_template_condition():
    automation = AUTOMATIONS_PATH.read_text()

    assert (
        "condition: template" not in automation and "value_template:" not in automation
    )


def test_custom_recorder_process_was_removed():
    assert not (EXAMPLE_DIR / "cradlewise_wake_recorder.py").exists()


def test_shell_command_process_supervision_was_removed():
    shell_commands = SHELL_COMMANDS_PATH.read_text()

    assert "python" not in shell_commands and "&" not in shell_commands


def test_recordings_are_deleted_after_fourteen_days():
    shell_commands = SHELL_COMMANDS_PATH.read_text()

    assert "-mtime +14 -delete" in shell_commands


def test_documentation_requires_preload_and_explains_retention():
    documentation = DOCS_PATH.read_text()

    assert "Preload stream" in documentation and "older than 14 days" in documentation


def test_documentation_preserves_six_state_anchors():
    documentation = DOCS_PATH.read_text()
    state_anchors = {
        "binary_sensor.cradlewise_local_baby_present",
        "binary_sensor.cradlewise_local_baby_needs_attention",
        "binary_sensor.cradlewise_local_baby_needs_help",
        "binary_sensor.cradlewise_local_loud_sound_detected",
        "sensor.cradlewise_local_sleep_phase",
        "sensor.cradlewise_local_sleep_state",
    }

    assert all(entity_id in documentation for entity_id in state_anchors)


def test_documentation_does_not_restore_the_public_gallery():
    documentation = DOCS_PATH.read_text()

    assert "/local/cradlewise-wake/index.html" not in documentation


def test_wake_card_browses_authenticated_media_source():
    card = CARD_PATH.read_text()

    assert 'type: "media_source/browse_media"' in card


def test_wake_card_resolves_signed_playback_urls():
    card = CARD_PATH.read_text()

    assert 'type: "media_source/resolve_media"' in card


def test_documentation_points_card_at_private_media_directory():
    documentation = DOCS_PATH.read_text()

    assert (
        "media-source://media_source/local/cradlewise-wake/events" in documentation
    )
