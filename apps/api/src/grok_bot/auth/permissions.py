from dataclasses import dataclass
from uuid import UUID

# Organization-wide capabilities for M0.
# Unit capabilities mirror the property split in ADR 0004. That analogy is not a
# confirmed business policy for units.
ACCOUNTING_READ = frozenset({"ledger.read", "receipts.read", "invoices.read"})
ACCOUNTING_OPERATIONS = frozenset(
    {
        "receipts.write",
        "deposits.write",
        "bank_imports.write",
        "bank_matches.write",
        "availability.write",
        "allocations.write",
        "rent_charges.write",
        "leases.write",
        "parties.write",
        "bank_accounts.write",
        "ownership.write",
        "opening_entries.write",
        "reconciliations.write",
        "period_closes.write",
        "journals.reverse",
        "invoices.submit",
        "reserves.apply",
    }
)
ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "organization_administrator": frozenset(
        {"properties.read", "properties.create", "units.read", "units.create"}
    ),
    "property_manager": frozenset(
        {
            "properties.read",
            "properties.update",
            "units.read",
            "units.update",
            "agreements.write",
            "ownership.write",
            "invoices.approve",
            "distributions.declare",
            "settlements.simulate",
            "maintenance.manage",
            "maintenance.assign",
            "maintenance.acknowledge",
            "prospects.review",
            "screening.publish",
            "tours.manage",
            "invitations.write",
            "dispositions.write",
        }
    )
    | ACCOUNTING_READ,
    "accounting_staff": frozenset({"properties.read", "units.read"})
    | ACCOUNTING_READ
    | ACCOUNTING_OPERATIONS,
    "owner": frozenset(),
    "tenant": frozenset({"maintenance.report"}),
    "prospect": frozenset({"prospects.own", "tours.request"}),
    "contractor": frozenset({"maintenance.respond"}),
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
