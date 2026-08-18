import re
from pathlib import Path


def test_dockerfile_installs_from_uv_lock():
    dockerfile = Path("Dockerfile").read_text()

    assert "uv.lock" in dockerfile
    assert "uv sync --frozen" in dockerfile
    assert "pip install --no-cache-dir -e ." not in dockerfile


def test_dockerfile_runs_the_copied_source_instead_of_a_cached_project_wheel():
    dockerfile = Path("Dockerfile").read_text()

    assert 'ENTRYPOINT ["python", "-m", "cradlewise_local"]' in dockerfile


def test_dockerfile_installs_mqtt_ca_pin_console_script():
    dockerfile = Path("Dockerfile").read_text()
    source_stage = dockerfile.split("COPY cradlewise_local ./cradlewise_local", 1)[1]

    assert "uv sync --frozen --no-dev" in source_stage
    assert "test -x /app/.venv/bin/cradlewise-pin-mqtt-ca" in source_stage


def test_ci_builds_and_publishes_bridge_image():
    workflow = Path(".github/workflows/tests.yml").read_text()

    assert "ghcr.io/caffeineflo/cradlewise-local-bridge" in workflow


def test_ci_actions_are_pinned_to_full_commit_shas():
    workflow = Path(".github/workflows/tests.yml").read_text()
    action_references = re.findall(r"uses: [^\s]+@([^\s]+)", workflow)

    assert all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_references)


def test_ci_package_write_permission_is_publish_only():
    workflow = Path(".github/workflows/tests.yml").read_text()
    publish_job = workflow.split("  bridge-image-publish:", 1)[1]

    assert "packages: write" in publish_job


def test_ci_pull_request_build_has_read_only_permissions():
    workflow = Path(".github/workflows/tests.yml").read_text()
    check_job = workflow.split("  bridge-image-check:", 1)[1].split(
        "  bridge-image-publish:", 1
    )[0]

    assert "packages: write" not in check_job


def test_ci_runs_lint_and_home_assistant_validation():
    workflow = Path(".github/workflows/tests.yml").read_text()

    assert (
        "ruff check" in workflow
        and "hassfest" in workflow
        and "hacs/action" in workflow
    )


def test_hacs_validation_activates_when_repository_is_public():
    workflow = Path(".github/workflows/tests.yml").read_text()
    hacs_step = workflow.split("      - name: Run HACS validation", 1)[1].split(
        "\n\n", 1
    )[0]

    assert "if: github.event.repository.private == false" in hacs_step
    assert "ignore:" not in hacs_step


def test_dockerfile_runs_as_non_root_with_healthcheck():
    dockerfile = Path("Dockerfile").read_text()

    assert "USER 10001:10001" in dockerfile and "HEALTHCHECK" in dockerfile


def test_compose_pins_and_authenticates_media_server():
    compose = Path("examples/docker-compose.yaml").read_text()

    assert (
        "bluenviron/mediamtx:1.19.2@sha256:" in compose
        and "AUTHINTERNALUSERS" in compose
    )


def test_compose_uses_versioned_published_bridge_image():
    compose = Path("examples/docker-compose.yaml").read_text()

    assert (
        "ghcr.io/caffeineflo/cradlewise-local-bridge:" in compose
        and "build:" not in compose
    )
