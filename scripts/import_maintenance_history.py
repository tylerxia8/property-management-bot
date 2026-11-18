import argparse
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api" / "src"))

from grok_bot.domain.maintenance_history import import_history


def main():
    parser = argparse.ArgumentParser(description="Import private, sanitized maintenance history")
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--organization-id", required=True)
    arguments = parser.parse_args()
    try:
        counts = import_history(arguments.source, arguments.output, arguments.organization_id)
    except (OSError, ValueError):
        parser.exit(1, "Maintenance history import failed; check input structure and private file permissions.\n")
    print(json.dumps(counts, sort_keys=True))


if __name__ == "__main__":
    main()
