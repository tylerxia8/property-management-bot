"""Success and error models for bodies the handlers already return.

Fields match the dicts returned by the route or domain function. Optional
keys that a handler omits are separate models, not default nulls.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorIssue(APIModel):
    loc: list[str]
    msg: str


class ErrorDetails(APIModel):
    errors: list[ErrorIssue] | None = None


class ErrorBody(APIModel):
    code: str
    message: str
    details: ErrorDetails
    retryable: bool


class ErrorEnvelope(APIModel):
    error: ErrorBody
    request_id: str


ERROR_RESPONSES = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    409: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
}


class HealthOut(APIModel):
    status: Literal["ok"]
    local_auth_enabled: bool
    request_id: str


class LoginOut(APIModel):
    token: str
    token_type: Literal["bearer"]
    auth_method: Literal["local_dev"]
    production_oidc: Literal[False]
    user_id: str
    organization_id: str
    display_name: str
    request_id: str


class StepUpOut(APIModel):
    id: str
    method: Literal["LOCAL_DEV_PASSWORD"]
    production_oidc: Literal[False]
    request_id: str


class GrantOut(APIModel):
    role: str
    resource_type: str | None
    resource_id: str | None


class MeOut(APIModel):
    user_id: str
    organization_id: str
    display_name: str
    roles: list[str]
    grants: list[GrantOut]
    capabilities: list[str]
    auth_method: str
    production_oidc: Literal[False]
    request_id: str


class PropertyOut(APIModel):
    id: str
    organization_id: str
    name: str
    address_line1: str
    address_line2: str | None
    city: str
    region: str
    postal_code: str
    country_code: str
    timezone: str
    version: int
    unit_count: int
    created_at: str
    request_id: str


class PropertyPageOut(APIModel):
    items: list[PropertyOut]
    next_cursor: str | None
    request_id: str


class UnitOut(APIModel):
    id: str
    organization_id: str
    property_id: str
    label: str
    version: int
    created_at: str
    request_id: str


class UnitPageOut(APIModel):
    items: list[UnitOut]
    next_cursor: str | None
    request_id: str


class PartyOut(APIModel):
    id: str
    display_name: str
    kind: str


class PartyCreatedOut(PartyOut):
    request_id: str


class PartyPageOut(APIModel):
    items: list[PartyOut]


class BankAccountOut(APIModel):
    id: str
    display_name: str
    masked_label: str
    currency: Literal["USD"]
    request_id: str


class LeaseOut(APIModel):
    id: str
    unit_id: str
    agreed_rent_cents: int
    request_id: str


class LeaseItemOut(APIModel):
    id: str
    agreed_rent_cents: int


class LeasePageOut(APIModel):
    items: list[LeaseItemOut]


class ShareOut(APIModel):
    owner_party_id: str
    weight: int


class OwnershipOut(APIModel):
    id: str
    property_id: str
    shares: list[ShareOut]
    request_id: str


class AgreementOut(APIModel):
    id: str
    property_id: str
    request_id: str


class ReceiptOut(APIModel):
    id: str
    property_id: str
    amount_cents: int
    available_cents: int
    allocated_cents: int
    deposited_cents: int
    verified_cents: int
    returned_cents: int
    status: str
    available_at: str | None
    receipt_number: int
    currency: Literal["USD"]
    method: str


class ReceiptCreatedOut(ReceiptOut):
    request_id: str


class ReceiptReturnOut(ReceiptOut):
    return_journal_id: str


class DepositOut(APIModel):
    id: str
    total_cents: int
    currency: Literal["USD"]
    request_id: str


class TopUpOut(APIModel):
    property_id: str
    top_up_cents: int
    owners: dict[str, int]
    currency: Literal["USD"]


class OpeningOut(APIModel):
    id: str
    amount_cents: int
    currency: Literal["USD"]
    request_id: str


class RentChargeOut(APIModel):
    id: str
    amount_cents: int
    journal_posted: Literal[False]
    currency: Literal["USD"]
    request_id: str


class InvoiceOut(APIModel):
    id: str
    property_id: str
    status: str
    total_cents: int
    tax_cents: int
    settled_cents: int
    credited_cents: int
    payable_journal_id: str | None
    currency: Literal["USD"]


class InvoiceCreatedOut(InvoiceOut):
    request_id: str


class CreditNoteOut(InvoiceOut):
    credit_note_id: str
    journal_id: str
    original_payable_journal_id: str


class AccountOut(APIModel):
    code: str
    amount_cents: int


class OwnerOut(APIModel):
    owner_party_id: str
    unrestricted_cents: int
    reserve_cents: int


class BalanceOut(APIModel):
    property_id: str
    accounts: list[AccountOut]
    owners: list[OwnerOut]
    currency: Literal["USD"]


class LedgerItemOut(APIModel):
    id: str
    posting_date: str
    source_type: str
    source_id: str
    reversal_of_id: str | None


class LedgerOut(APIModel):
    property_id: str
    accounts: list[AccountOut]
    owners: list[OwnerOut]
    items: list[LedgerItemOut]
    next_cursor: str | None
    currency: Literal["USD"]


class ReversalOut(APIModel):
    id: str
    reversal_of_id: str
    reason: str
    currency: Literal["USD"]
    posted: Literal[True]


class BankItemOut(APIModel):
    id: str
    bank_account_id: str
    external_id: str
    amount_cents: int
    matched_cents: int
    posted_on: str
    currency: Literal["USD"]


class BankListOut(APIModel):
    items: list[BankItemOut]
    next_cursor: str | None
    currency: Literal["USD"]


class MatchOut(APIModel):
    id: str
    bank_transaction_id: str
    deposit_batch_id: str
    amount_cents: int
    currency: Literal["USD"]
    posted_journal: Literal[False]


class ImportOut(APIModel):
    created: int
    existing: int
    request_id: str


class ReconciliationOut(APIModel):
    id: str
    status: str
    statement_closing_cents: int
    ledger_cash_cents: int
    obligation_cents: int
    difference_cents: int
    currency: Literal["USD"]


class PeriodOut(APIModel):
    id: str
    status: Literal["CLOSED"]


class DeclarationItemOut(APIModel):
    id: str
    owner_party_id: str
    amount_cents: int


class BatchItemOut(APIModel):
    id: str
    kind: str
    recipient_id: str
    amount_cents: int
    destination_version: int | None
    liability_id: str | None
    status: str
    provider_key: str


class BatchOut(APIModel):
    id: str
    property_id: str
    status: str
    snapshot_hash: str | None
    total_cents: int
    retained_reserves_cents: int
    expires_at: str | None
    items: list[BatchItemOut]
    currency: Literal["USD"]
    submitted: Literal[False]


class DraftBatchOut(BatchOut):
    request_id: str


class ApprovedBatchOut(BatchOut):
    approval_id: str


class SubmitBatchOut(BatchOut):
    simulator: Literal[True]
    bank_contacted: Literal[False]


class ExportItemOut(APIModel):
    id: str
    kind: str
    amount_cents: int
    destination_version: int | None
    provider_key: str


class ExportArtifactOut(APIModel):
    batch_id: str
    snapshot_hash: str | None
    items: list[ExportItemOut]
    submitted: Literal[False]
    settled: Literal[False]


class ExportOut(APIModel):
    id: str
    batch_id: str
    artifact: ExportArtifactOut
    artifact_hash: str
    duplicate_download: bool
    status: str
    settled: Literal[False]


class ReturnItemOut(APIModel):
    id: str
    status: Literal["RETURNED"]
    recovery_account: Literal["1040"]
    disbursements_frozen: Literal[True]
    simulator: Literal[True]


class StatementAccountOut(APIModel):
    code: str
    amount_cents: int


class StatementSnapshotOut(APIModel):
    property_id: str
    owner_party_id: str
    period_start: str
    period_end: str
    unrestricted_cents: int
    reserve_cents: int
    accounts: list[StatementAccountOut]
    fixture: bool


class StatementIssuedOut(APIModel):
    id: str
    version: int
    snapshot_hash: str
    snapshot: StatementSnapshotOut
    supersedes: str | None


class StatementOut(APIModel):
    id: str
    version: int
    snapshot_hash: str
    snapshot: StatementSnapshotOut
    owner_party_id: str
    period_start: str
    period_end: str
    reason: str
    unrestricted_cents: int | None


class StatementPageOut(APIModel):
    items: list[StatementOut]


class OwnerLinkOut(APIModel):
    id: str


class DestinationOut(APIModel):
    id: str
    party_id: str
    version: int
    masked_label: str


class EvidenceOut(APIModel):
    id: str
    kind: str
    simulator: Literal[False]
    settled: bool
    reference: str
    bank_contacted: Literal[False]
    amount_cents: int
    currency: Literal["USD"]


class SwitchOut(APIModel):
    messaging_enabled: bool
    calendar_enabled: bool
    payment_enabled: bool


class AlertAttemptOut(APIModel):
    id: str
    status: str
    delivered_at: None


class AlertFallbackOut(APIModel):
    id: str
    status: str
    fallback_id: str
    delivered_at: None


class AlertOut(APIModel):
    id: str
    delivered_at: None
    delivered: Literal[False]
    processed: list[AlertFallbackOut | AlertAttemptOut]


class OperationsQueueOut(APIModel):
    dead_letters: int
    unknown_payments: int
    approved_batches: int
    unassigned_emergency_tickets: int
    alerts_sent: Literal[False]
    delivery_enabled: Literal[False]


class WebhookOut(APIModel):
    status: str
    provider_event_id: str
    delivered: Literal[False]
    request_id: str


class IntakeOut(APIModel):
    move_in_date: str | None
    lease_months: int | None
    income_original_cents: int | None
    income_period: str | None
    income_monthly_cents: int | None
    income_unverified: bool
    occupant_count: int | None
    pets_declared: bool | None
    assistance_animal_requested: bool
    rental_history: str | None
    income_source: str | None
    version: int


class ProspectOut(APIModel):
    id: str
    state: str
    unverified: bool
    property_id: str | None
    listing_id: str | None
    disclosure: str
    intake: IntakeOut
    questions: list[str]
    final_housing_decision: Literal[False]
    request_id: str


class IntakeUpdatedOut(IntakeOut):
    questions: list[str]
    disclosure: str
    income_treated_as_zero: Literal[False]
    request_id: str


class IntakeMessageOut(IntakeUpdatedOut):
    model_adapter: Literal["disabled"]


class ListingItemOut(APIModel):
    id: str
    property_id: str
    display_label: str
    asking_rent_cents: int


class ListingPageOut(APIModel):
    items: list[ListingItemOut]


class ListingCreatedOut(APIModel):
    id: str
    request_id: str


class InquiryCreatedOut(APIModel):
    id: str
    prospect_id: str | None
    ambiguous: bool
    clarification: str
    duplicate: Literal[False]
    disclosure: str
    request_id: str


class InquiryDuplicateOut(APIModel):
    id: str
    prospect_id: str | None
    ambiguous: bool
    clarification: str
    duplicate: Literal[True]
    request_id: str


InquiryOut = InquiryCreatedOut | InquiryDuplicateOut


class RuleReasonOut(APIModel):
    rule_id: str
    result: str
    reason: str


class RuleHitOut(APIModel):
    rule_id: str
    result: str


class EvaluationOut(APIModel):
    prospect_id: str
    intake_version: int
    policy_version: int | None
    policy_fixture: bool | None
    result: str
    missing_fields: list[str]
    rule_results: list[RuleReasonOut | RuleHitOut]
    formal_screening_permitted: Literal[False]
    configuration_code: str | None
    input_hash: str
    final_denial: Literal[False]
    disclosure: str
    request_id: str


class PolicyOut(APIModel):
    id: str
    version: int
    fixture: bool
    automatic_final_denial: Literal[False]


class ReviewItemOut(APIModel):
    id: str
    prospect_id: str
    property_id: str | None
    reason: str
    rule_ids: list[str]
    missing_fields: list[str]
    state: str
    prospect_state: str
    opened_at: str
    final_housing_decision: Literal[False]


class ReviewPageOut(APIModel):
    items: list[ReviewItemOut]


class ReviewResolvedOut(APIModel):
    id: str
    resolution: str
    exception_granted: bool
    final_housing_decision: Literal[False]


class DispositionOut(APIModel):
    id: str
    decided_by: str
    automated: Literal[False]


class ScheduleOut(APIModel):
    id: str
    fixture: bool


class ResourceOut(APIModel):
    id: str
    kind: Literal["AGENT"]


class SlotOut(APIModel):
    resource_id: str
    starts_at: str
    ends_at: str
    timezone: str


class SlotPageOut(APIModel):
    items: list[SlotOut]
    timezone: str
    configuration: str


class AppointmentOut(APIModel):
    id: str
    status: str
    starts_at: str
    ends_at: str
    timezone: str
    expires_at: str | None
    external_event_key: str | None
    external_event_created: bool
    version: int


class RescheduleOut(APIModel):
    previous_id: str
    appointment: AppointmentOut
    previous_reminders: Literal["SUPPRESSED"]


class TourCancelOut(APIModel):
    id: str
    status: Literal["CANCELED"]
    reminders: Literal["SUPPRESSED"]


class TourCompleteOut(APIModel):
    id: str
    status: Literal["COMPLETED"]


class AccessOut(APIModel):
    id: str
    access_recorded: Literal[True]


class InvitationOut(APIModel):
    id: str
    report_ordered: Literal[False]
    formal_screening_permitted: Literal[False]


class IntakeFieldOut(APIModel):
    field_key: str
    status: str
    reason: str | None
    value_text: str | None


class TicketPublicOut(APIModel):
    id: str
    ticket_number: int
    status: str
    priority: str
    verification: str
    emergency: bool
    missing_fields: list[str]
    next_questions: list[str]
    safety_message: str | None
    model_adapter: Literal["disabled"]
    questions_source: Literal["template"]
    video_understanding: Literal[False]
    intake_token: str
    request_id: str


class TicketContractorOut(APIModel):
    id: str
    ticket_number: int
    status: str
    priority: str
    verification: str
    emergency: bool
    urgent_triage: bool
    handoff: bool
    category: str
    missing_fields: list[str]
    intake: list[IntakeFieldOut]
    next_questions: list[str]
    safety_message: str | None
    model_adapter: Literal["disabled"]
    questions_source: Literal["template"]
    video_understanding: Literal[False]
    request_id: str


class TicketStaffOut(TicketContractorOut):
    intake_token: str


TicketOut = TicketStaffOut | TicketContractorOut | TicketPublicOut


class IntakeLinkOut(APIModel):
    token: str
    request_id: str


class UploadHeadersOut(APIModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    content_type: str = Field(alias="Content-Type")


class UploadOut(APIModel):
    id: str
    status: Literal["QUARANTINED"]
    upload_url: str
    expires_in_seconds: Literal[300]
    required_headers: UploadHeadersOut
    ticket_id: str
    request_id: str


class QuarantineOut(APIModel):
    id: str
    status: Literal["QUARANTINED"]
    request_id: str


class ScanOut(APIModel):
    id: str
    status: str
    scan_code: str
    scanner_name: str | None
    ticket_id: str
    request_id: str
    video_understanding: Literal[False]


class DownloadOut(APIModel):
    download_url: str
    expires_in_seconds: Literal[300]
    scanner_name: str | None
    video_understanding: Literal[False]
    request_id: str


class EscalationOut(APIModel):
    ticket_id: str
    escalation_id: str
    delivered_at: None
    request_id: str


class AckOut(APIModel):
    id: str
    state: Literal["ACKNOWLEDGED"]
    request_id: str


class AdvanceOut(APIModel):
    recorded_attempts: int
    request_id: str
    delivered_at: None


class DeescalateOut(APIModel):
    id: str
    emergency: Literal[False]


class ProfileOut(APIModel):
    id: str
    approved: bool
    trades: str


class AssignmentOut(APIModel):
    assignment_id: str
    work_order_id: str
    status: Literal["ASSIGNED"]


class RespondOut(APIModel):
    id: str
    status: str


class CompletionOut(APIModel):
    work_order_id: str
    status: Literal["COMPLETION_REVIEW"]
    payable_journal_id: None
    request_id: Literal["maintenance"]


class EstimateOut(APIModel):
    authorization_state: Literal["WAITING_APPROVAL"]
    spending_limit: None


class TransitionDuplicateOut(APIModel):
    id: str
    status: str
    duplicate_of_id: str
    deleted: Literal[False]


class TransitionStatusOut(APIModel):
    id: str
    status: str


TransitionOut = TransitionDuplicateOut | TransitionStatusOut


class StoredOut(APIModel):
    stored: Literal[True]
    request_id: str


class MaintenanceAppointmentOut(APIModel):
    id: str
    status: Literal["REQUESTED"]
    entry_permission: Literal["NOT_YET_GRANTED"]


class MaintenanceConfirmOut(APIModel):
    id: str
    status: Literal["CONFIRMED"]


class EscalationDestinationOut(APIModel):
    id: str
    role: str
    label: str
    fail_next: bool
    delivered_at: None


class LeasePartyOut(APIModel):
    id: str
    lease_id: str
    user_id: str
