from dataclasses import dataclass
from uuid import UUID

# Organization-wide capabilities for M0.
# Unit capabilities mirror the property split in ADR 0004. That analogy is not a
# confirmed business policy for units.
ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "organization_administrator": frozenset(
        {"properties.read", "properties.create", "units.read", "units.create"}
    ),
    "property_manager": frozenset(
        {"properties.read", "properties.update", "units.read", "units.update"}
    ),
    "accounting_staff": frozenset({"properties.read", "units.read"}),
    "owner": frozenset(),
    "tenant": frozenset(),
    "prospect": frozenset(),
    "contractor": frozenset(),
    "ai_service": frozenset(),
    "worker": frozenset(),
}


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    organization_id: UUID
    display_name: str
    roles: tuple[str, ...]
    auth_method: str

    def capabilities(self) -> list[str]:
        granted: set[str] = set()
        for role in self.roles:
            granted.update(ROLE_CAPABILITIES.get(role, frozenset()))
        return sorted(granted)

    def allows(self, capability: str) -> bool:
        return capability in self.capabilities()
