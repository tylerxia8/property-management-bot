"""Write the web TypeScript constants from the live OpenAPI document."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / "apps" / "web" / "lib" / "api-types.generated.ts"


def render(schema: dict) -> str:
    paths = sorted(schema["paths"])
    lines = [
        "// Generated from the FastAPI OpenAPI document by apps/api/scripts/generate_api_types.py.",
        "// Do not edit by hand.",
        f'export const API_VERSION = "{schema["info"]["version"]}";',
        "export const API_PATHS = [",
    ]
    lines.extend(f'  "{path}",' for path in paths)
    lines.extend(
        [
            "] as const;",
            "",
            "export type ApiErrorBody = {",
            "  error: {",
            "    code: string;",
            "    message: string;",
            "    details: Record<string, unknown>;",
            "    retryable: boolean;",
            "  };",
            "  request_id: string;",
            "};",
            "",
        ]
    )
    return "\n".join(lines)


def write_types(schema: dict) -> None:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(render(schema), encoding="utf-8")
