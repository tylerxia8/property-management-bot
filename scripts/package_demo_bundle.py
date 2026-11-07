"""Copy the fixture demo runtime into a zip. Omits git metadata, secrets, and caches."""

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = [
    "Start-Demo.cmd",
    "docs/DEMO_WALKTHROUGH.md",
    "docs/OPEN_SOURCE_REVIEW.md",
    "docs/licenses",
    "scripts/check_demo.py",
    "compose.demo.yaml",
    "apps/api/Dockerfile",
    "apps/api/.dockerignore",
    "apps/api/requirements.lock",
    "apps/api/pyproject.toml",
    "apps/api/alembic.ini",
    "apps/api/src",
    "apps/api/alembic",
    "apps/api/scripts/bootstrap_demo_sample.sql",
    "apps/api/docker/entrypoint.py",
    "apps/web/Dockerfile",
    "apps/web/.dockerignore",
    "apps/web/package.json",
    "apps/web/package-lock.json",
    "apps/web/next.config.ts",
    "apps/web/tsconfig.json",
    "apps/web/next-env.d.ts",
    "apps/web/app",
    "apps/web/lib",
    "deploy/grok-property-sample/Start-GrokDemo.ps1",
    "deploy/grok-property-sample/Stop-GrokDemo.ps1",
    "deploy/grok-property-sample/Reset-GrokDemo.ps1",
    "deploy/grok-property-sample/start-macos.sh",
    "deploy/grok-property-sample/stop-macos.sh",
    "deploy/grok-property-sample/reset-macos.sh",
    "deploy/grok-property-sample/README.md",
]
SKIP_PARTS = {".git", "node_modules", ".venv", ".next", "__pycache__", ".pytest_cache", ".hypothesis", ".env"}


def members() -> list[tuple[Path, str]]:
    found = []
    for item in INCLUDE:
        path = ROOT / item
        if path.is_dir():
            for file in path.rglob("*"):
                if not file.is_file():
                    continue
                if set(file.parts) & SKIP_PARTS:
                    continue
                archive = file.relative_to(ROOT).as_posix()
                found.append((file, archive))
        else:
            archive = "compose.yaml" if item == "compose.demo.yaml" else item
            if item.startswith("deploy/grok-property-sample/"):
                archive = Path(item).name
            found.append((path, archive))
    return found


def write_zip(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file, name in members():
            if name == ".env" or name.endswith("/.env"):
                raise SystemExit("refusing to package an env file")
            archive.write(file, name)


if __name__ == "__main__":
    write_zip(Path(sys.argv[1]))
