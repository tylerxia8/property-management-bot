import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


CONTAINER = "grok-property-sample-db-1"
API_CONTAINER = "grok-property-sample-api-1"
ARCHIVE_PATTERN = r"maintenance-demo-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{32}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a private backup of the local maintenance demo database, uploaded media, and available historical index. Existing backups are retained. Restore with pg_restore into a separate database before replacing any live data.")
    parser.add_argument("--output-dir", type=Path, default=Path.home() / ".guest-recovery-archives" / "maintenance-demo")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    directory = args.output_dir.expanduser().absolute()
    temporary_paths = []
    published_paths = []
    complete = False
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory_stat = directory.lstat()
        if not stat.S_ISDIR(directory_stat.st_mode) or directory_stat.st_uid != os.getuid() or stat.S_IMODE(directory_stat.st_mode) & 0o077:
            print("BACKUP_DIRECTORY_MUST_BE_PRIVATE", file=sys.stderr)
            return 2
        if args.list:
            summaries = []
            for manifest_path in sorted(directory.glob("maintenance-demo-*.json")):
                if not re.fullmatch(ARCHIVE_PATTERN + r"\.json", manifest_path.name) or manifest_path.is_symlink():
                    continue
                if manifest_path.stat().st_size > 4096:
                    continue
                manifest = json.loads(manifest_path.read_text())
                if not isinstance(manifest, dict):
                    continue
                expected_name = manifest_path.stem + ".dump"
                if manifest.get("archive") != expected_name or not re.fullmatch(r"[0-9a-f]{64}", str(manifest.get("sha256", ""))):
                    continue
                archive_path = directory / expected_name
                if not archive_path.is_file() or archive_path.is_symlink():
                    continue
                summary = {"archive": expected_name, "bytes": archive_path.stat().st_size, "sha256": manifest["sha256"], "archive_count": 1}
                for kind, suffix in (("media", ".media.tar.gz"), ("history", ".history.json")):
                    if kind + "_archive" not in manifest:
                        continue
                    expected = manifest_path.stem + suffix
                    artifact = directory / expected
                    if manifest[kind + "_archive"] != expected or not re.fullmatch(r"[0-9a-f]{64}", str(manifest.get(kind + "_sha256", ""))) or not artifact.is_file() or artifact.is_symlink():
                        break
                    summary.update({kind + "_archive": expected, kind + "_bytes": artifact.stat().st_size, kind + "_sha256": manifest[kind + "_sha256"]})
                    summary["archive_count"] += 1
                else:
                    if summary["archive_count"] == manifest.get("archive_count", 1):
                        summaries.append(summary)
            print(json.dumps({"backups": summaries, "count": len(summaries), "archive_count": sum(item["archive_count"] for item in summaries)}, sort_keys=True))
            return 0
        for container, service in ((CONTAINER, b"db"), (API_CONTAINER, b"api")):
            for attempt in range(3):
                try:
                    inspected = subprocess.run(["docker", "inspect", "--format", '{{index .Config.Labels "com.docker.compose.project"}}/{{index .Config.Labels "com.docker.compose.service"}}', container], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, check=False)
                    if inspected.returncode == 0:
                        break
                except subprocess.TimeoutExpired:
                    if attempt == 2:
                        raise
                if attempt < 2:
                    time.sleep(1 << attempt)
            if inspected.returncode != 0 or inspected.stdout.strip() != b"grok-property-sample/" + service:
                print("LOCAL_DEMO_CONTAINER_UNAVAILABLE", file=sys.stderr)
                return 3
        created_at = datetime.now(timezone.utc)
        stem = "maintenance-demo-" + created_at.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex
        archive_path = directory / (stem + ".dump")
        manifest_path = directory / (stem + ".json")
        manifest = {"archive": archive_path.name, "format": "postgresql-custom", "database": "grok_demo_sample", "created_at": created_at.isoformat(), "archive_count": 2}
        artifacts = []
        commands = (
            ("", archive_path, ["docker", "exec", CONTAINER, "pg_dump", "-U", "postgres", "-Fc", "grok_demo_sample"], b"PGDMP"),
            ("media_", directory / (stem + ".media.tar.gz"), ["docker", "exec", API_CONTAINER, "tar", "-C", "/data", "-czf", "-", "media"], b"\x1f\x8b"),
        )
        for prefix, destination, command, signature in commands:
            descriptor, temporary_name = tempfile.mkstemp(prefix=".maintenance-backup-", dir=directory)
            temporary_path = Path(temporary_name)
            temporary_paths.append(temporary_path)
            with os.fdopen(descriptor, "w+b") as output:
                os.fchmod(output.fileno(), 0o600)
                for attempt in range(3):
                    output.seek(0)
                    output.truncate()
                    try:
                        dumped = subprocess.run(command, stdout=output, stderr=subprocess.PIPE, timeout=120, check=False)
                        if dumped.returncode == 0:
                            break
                    except subprocess.TimeoutExpired:
                        if attempt == 2:
                            raise
                    if attempt < 2:
                        time.sleep(1 << attempt)
                if dumped.returncode != 0:
                    print("LOCAL_DEMO_BACKUP_FAILED", file=sys.stderr)
                    return 4
                output.flush()
                os.fsync(output.fileno())
                output.seek(0)
                if output.read(len(signature)) != signature:
                    print("LOCAL_DEMO_BACKUP_INVALID", file=sys.stderr)
                    return 4
                output.seek(0)
                checksum = hashlib.sha256()
                for chunk in iter(lambda: output.read(1024 * 1024), b""):
                    checksum.update(chunk)
                manifest.update({prefix + "archive": destination.name, prefix + "bytes": os.fstat(output.fileno()).st_size, prefix + "sha256": checksum.hexdigest()})
            artifacts.append((temporary_path, destination))
        history_path = Path(os.environ.get("MAINTENANCE_HISTORY_DIRECTORY", "/Users/tylerxia/code/.worktrees/property-management-maintenance-history")).expanduser() / "index.json"
        try:
            history_descriptor = os.open(history_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            history_descriptor = None
        if history_descriptor is not None:
            with os.fdopen(history_descriptor, "rb") as source:
                history_stat = os.fstat(source.fileno())
                if not stat.S_ISREG(history_stat.st_mode) or history_stat.st_uid != os.getuid() or stat.S_IMODE(history_stat.st_mode) & 0o077:
                    print("HISTORY_INDEX_MUST_BE_PRIVATE", file=sys.stderr)
                    return 4
                descriptor, temporary_name = tempfile.mkstemp(prefix=".maintenance-history-", dir=directory)
                temporary_history = Path(temporary_name)
                temporary_paths.append(temporary_history)
                with os.fdopen(descriptor, "wb") as output:
                    os.fchmod(output.fileno(), 0o600)
                    checksum = hashlib.sha256()
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        output.write(chunk)
                        checksum.update(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                    history_after = os.fstat(source.fileno())
                    if (history_stat.st_size, history_stat.st_mtime_ns) != (history_after.st_size, history_after.st_mtime_ns):
                        print("HISTORY_INDEX_CHANGED_DURING_BACKUP", file=sys.stderr)
                        return 4
                    history_destination = directory / (stem + ".history.json")
                    manifest.update({"history_archive": history_destination.name, "history_bytes": os.fstat(output.fileno()).st_size, "history_sha256": checksum.hexdigest(), "archive_count": 3})
                artifacts.append((temporary_history, history_destination))
        descriptor, temporary_name = tempfile.mkstemp(prefix=".maintenance-manifest-", dir=directory)
        temporary_manifest = Path(temporary_name)
        temporary_paths.append(temporary_manifest)
        with os.fdopen(descriptor, "w") as output:
            output.write(json.dumps(manifest, sort_keys=True) + "\n")
            output.flush()
            os.fsync(output.fileno())
        for temporary_artifact, destination in artifacts:
            os.link(temporary_artifact, destination)
            published_paths.append(destination)
        os.link(temporary_manifest, manifest_path)
        published_paths.append(manifest_path)
        directory_descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        complete = True
        print(json.dumps({**manifest, "archive": str(archive_path), "manifest": str(manifest_path)}, sort_keys=True))
        return 0
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        print("LOCAL_DEMO_BACKUP_IO_ERROR", file=sys.stderr)
        return 5
    finally:
        for path in temporary_paths + ([] if complete else published_paths):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                print("BACKUP_TEMPORARY_CLEANUP_FAILED", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
