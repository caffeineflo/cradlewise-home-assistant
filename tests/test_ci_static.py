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


def test_dockerfile_and_ci_include_the_standalone_client_package():
    dockerfile = Path("Dockerfile").read_text()
    workflow = Path(".github/workflows/tests.yml").read_text()

    assert "COPY packages/cradlewise-client" in dockerfile
    assert "uv build --package cradlewise-client" in workflow


def test_bridge_image_includes_inactive_observability_extra():
    dockerfile = Path("Dockerfile").read_text()
    project = Path("pyproject.toml").read_text()

    assert (
        "--extra observability" in dockerfile and "sentry-sdk>=2.68.0,<3.0.0" in project
    )


def test_ci_builds_bridge_image_without_publishing():
    workflow = Path(".github/workflows/tests.yml").read_text()

    assert "docker/build-push-action@" in workflow and "push: false" in workflow


def test_ci_actions_are_pinned_to_full_commit_shas():
    workflows = "\n".join(
        path.read_text() for path in Path(".github/workflows").glob("*.yml")
    )
    action_references = re.findall(r"uses: [^\s]+@([^\s]+)", workflows)

    assert all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_references)


def test_release_package_write_permission_is_bridge_publish_only():
    workflow = Path(".github/workflows/release.yml").read_text()
    publish_job = workflow.split("  bridge-image-publish:", 1)[1].split(
        "  github-release:", 1
    )[0]

    assert (
        "packages: write" in publish_job
        and "ghcr.io/caffeineflo/cradlewise-local-bridge" in workflow
        and "push: true" in publish_job
    )


def test_client_publish_uses_trusted_publishing_without_repository_checkout():
    workflow = Path(".github/workflows/release.yml").read_text()
    publish_job = workflow.split("  client-package-publish:", 1)[1].split(
        "  bridge-image-publish:", 1
    )[0]

    assert (
        "environment: pypi" in publish_job
        and "id-token: write" in publish_job
        and "pypa/gh-action-pypi-publish@" in publish_job
        and "actions/checkout@" not in publish_job
    )


def test_client_release_build_requires_all_unprivileged_gates():
    workflow = Path(".github/workflows/release.yml").read_text()
    build_job = workflow.split("  client-package-build:", 1)[1].split(
        "  client-package-publish:", 1
    )[0]
    needs_block = build_job.split("    needs:", 1)[1].split("\n\n", 1)[0]
    required_jobs = set(re.findall(r"^      - (.+)$", needs_block, re.MULTILINE))

    assert (
        required_jobs
        == {
            "dependabot-audit",
            "test",
            "lint",
            "home-assistant-test",
            "home-assistant-validation",
        }
        and "actions/upload-artifact@" in build_job
        and "id-token: write" not in build_job
    )


def test_bridge_release_requires_dependabot_audit():
    workflow = Path(".github/workflows/release.yml").read_text()
    publish_job = workflow.split("  bridge-image-publish:", 1)[1].split(
        "  github-release:", 1
    )[0]
    needs_block = publish_job.split("    needs:", 1)[1].split("\n    permissions:", 1)[
        0
    ]

    assert "      - dependabot-audit" in needs_block


def test_release_dependabot_audit_queries_open_alerts_and_fails_closed():
    workflow = Path(".github/workflows/release.yml").read_text()
    audit_job = workflow.split("  dependabot-audit:", 1)[1].split("  test:", 1)[0]

    assert (
        "permissions: read-all" in audit_job
        and "dependabot/alerts?state=open" in audit_job
        and "exit 1" in audit_job
    )


def test_release_workflow_is_tag_only_and_creates_full_github_release():
    workflow = Path(".github/workflows/release.yml").read_text()

    assert (
        'tags:\n      - "v*"' in workflow
        and "gh release create" in workflow
        and "client-package-publish" in workflow
        and "bridge-image-publish" in workflow
    )


def test_ci_pull_request_build_has_read_only_permissions():
    workflow = Path(".github/workflows/tests.yml").read_text()
    check_job = workflow.split("  bridge-image-check:", 1)[1]

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

    assert (
        "USER 10001:10001" in dockerfile
        and "HEALTHCHECK" in dockerfile
        and "127.0.0.1:8080/live" in dockerfile
    )


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
