from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = REPO_ROOT / "frontend"


def test_nextjs_standalone_output_is_enabled():
    next_config = FRONTEND_DIR / "next.config.ts"
    assert next_config.exists(), "frontend/next.config.ts is missing"

    contents = next_config.read_text(encoding="utf-8")
    assert 'output: "standalone"' in contents


def test_frontend_api_client_exists():
    api_client = FRONTEND_DIR / "src" / "lib" / "api.ts"
    assert api_client.exists(), "frontend/src/lib/api.ts is missing"

    contents = api_client.read_text(encoding="utf-8")
    assert "fetchHealth" in contents
    assert "fetchVersion" in contents


def test_frontend_dockerfile_exists():
    dockerfile = FRONTEND_DIR / "Dockerfile"
    assert dockerfile.exists(), "frontend/Dockerfile is missing"
