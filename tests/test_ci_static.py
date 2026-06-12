from pathlib import Path


def test_dockerfile_installs_from_uv_lock():
    dockerfile = Path("Dockerfile").read_text()

    assert "uv.lock" in dockerfile
    assert "uv sync --frozen" in dockerfile
    assert "pip install --no-cache-dir -e ." not in dockerfile


def test_ci_builds_and_publishes_bridge_image():
    workflow = Path(".github/workflows/tests.yml").read_text()

    assert "ghcr.io/caffeineflo/cradlewise-local-bridge" in workflow
    assert "docker/metadata-action@v6" in workflow
    assert "docker/build-push-action@v7" in workflow
    assert "packages: write" in workflow
    assert "push: ${{ github.event_name != 'pull_request' }}" in workflow
    assert "type=raw,value=latest,enable={{is_default_branch}}" in workflow
