"""Generate TypeScript from the FastAPI OpenAPI document.

This emits an interface for every component schema and a path map for every
operation. A success response with no schema in the document becomes
`unknown`. The generator does not invent response fields the routes omitted.
"""

import json
import keyword
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / "apps" / "web" / "lib" / "api-types.generated.ts"
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def render(schema: dict) -> str:
    components = schema.get("components", {}).get("schemas", {})
    typed_success, untyped_success = _response_counts(schema)
    lines = [
        "// Generated from the FastAPI OpenAPI document by apps/api/scripts/generate_api_types.py.",
        "// Do not edit by hand.",
        "//",
        f"// Component schemas: {len(components)}.",
        f"// Success responses with a schema: {typed_success}.",
        f"// Success responses without a schema, typed as unknown: {untyped_success}.",
        "// Those unknown responses are omitted from the route declaration, not filled in here.",
        f'export const API_VERSION = "{schema["info"]["version"]}";',
        "",
    ]
    for name in sorted(components):
        lines.append(_interface(name, components[name]))
        lines.append("")
    lines.append("export interface apiPaths {")
    for path in sorted(schema["paths"]):
        methods = schema["paths"][path]
        lines.append(f"  {json.dumps(path)}: {{")
        for method in sorted(m for m in methods if m in {"get", "post", "patch", "put", "delete"}):
            lines.append(f"    {method}: {{")
            lines.extend(_operation(methods[method]))
            lines.append("    };")
        lines.append("  };")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def write_types(schema: dict) -> None:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(render(schema), encoding="utf-8")


def _response_counts(schema: dict) -> tuple[int, int]:
    typed = untyped = 0
    for methods in schema["paths"].values():
        for method, operation in methods.items():
            if method not in {"get", "post", "patch", "put", "delete"}:
                continue
            for code, response in operation.get("responses", {}).items():
                if not str(code).startswith("2"):
                    continue
                body = response.get("content", {}).get("application/json", {}).get("schema")
                if body:
                    typed += 1
                else:
                    untyped += 1
    return typed, untyped


def _interface(name: str, body: dict) -> str:
    properties = body.get("properties", {})
    required = set(body.get("required", []))
    lines = [f"export interface {name} {{"]
    if not properties and body.get("additionalProperties"):
        lines.append(f"  [key: string]: {_type(body['additionalProperties'])};")
    for prop in sorted(properties):
        optional = "" if prop in required else "?"
        lines.append(f"  {_field(prop)}{optional}: {_type(properties[prop])};")
    lines.append("}")
    return "\n".join(lines)


def _operation(operation: dict) -> list[str]:
    lines = []
    request = operation.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
    if request:
        lines.append(f"      requestBody: {_type(request)};")
    responses = operation.get("responses", {})
    lines.append("      responses: {")
    for code in sorted(responses):
        body = responses[code].get("content", {}).get("application/json", {}).get("schema")
        lines.append(f"        {json.dumps(str(code))}: {_type(body) if body else 'unknown'};")
    lines.append("      };")
    return lines


def _type(schema: dict) -> str:
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "enum" in schema:
        return " | ".join(_literal(item) for item in schema["enum"])
    if "anyOf" in schema:
        return " | ".join(_type(item) for item in schema["anyOf"])
    if "allOf" in schema:
        return " & ".join(_type(item) for item in schema["allOf"])
    kind = schema.get("type")
    if isinstance(kind, list):
        return " | ".join(_type({"type": item}) for item in kind)
    if kind == "array":
        item = _type(schema.get("items", {}))
        if " | " in item or " & " in item:
            item = f"({item})"
        return f"{item}[]"
    if kind == "object":
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict):
            return f"Record<string, {_type(extra)}>"
        return "Record<string, unknown>"
    return {
        "string": "string",
        "integer": "number",
        "number": "number",
        "boolean": "boolean",
        "null": "null",
    }.get(kind, "unknown")


def _literal(value) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def _field(name: str) -> str:
    if IDENT.match(name) and not keyword.iskeyword(name):
        return name
    return json.dumps(name)
