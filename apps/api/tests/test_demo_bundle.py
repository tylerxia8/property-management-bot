"""The laptop bundle publishes only loopback port 3000 and only the demo database."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("package_demo_bundle", ROOT / "scripts" / "package_demo_bundle.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
members = module.members
write_zip = module.write_zip


def test_compose_binds_loopback_web_and_hides_postgres():
    text = (ROOT / "compose.demo.yaml").read_text(encoding="utf-8")
    assert "127.0.0.1:3000:3000" in text
    assert "0.0.0.0:3000" not in text
    assert '"3000:3000"' not in text
    assert "5432:5432" not in text
    assert "grok-property-sample-pg" in text
    assert "PAYMENT_SIMULATOR: unset" in text
    assert "DEMO_FIXTURE: sample" in text
    bootstrap = (ROOT / "apps/api/scripts/bootstrap_demo_sample.sql").read_text(encoding="utf-8")
    assert "grok_demo_sample" in bootstrap
    assert "grok_m0_test" not in bootstrap
    assert "grok_m0_e2e" not in bootstrap
    assert "PASSWORD '" not in bootstrap


def test_bundle_zip_omits_secrets_and_caches(tmp_path):
    destination = tmp_path / "grok-property-sample-demo.zip"
    write_zip(destination)
    names = [name for _file, name in members()]
    assert "compose.yaml" in names
    assert "Start-GrokDemo.ps1" in names
    assert "apps/api/Dockerfile" in names
    assert "apps/web/Dockerfile" in names
    assert not any(name == ".env" or name.endswith("/.env") or ".git" in name.split("/") for name in names)
    assert not any("node_modules" in name or ".venv" in name or ".next" in name for name in names)
    assert destination.stat().st_size > 1000
