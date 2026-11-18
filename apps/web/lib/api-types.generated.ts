// Generated from the FastAPI OpenAPI document by apps/api/scripts/generate_api_types.py.
// Do not edit by hand.
//
// Component schemas: 279.
// Success responses with a schema: 152.
// Success responses without a schema, typed as unknown: 0.
// Those unknown responses are omitted from the route declaration, not filled in here.
export const API_VERSION = "0.1.0";

export interface AccessBody {
  evidence: string;
}

export interface AccessOut {
  access_recorded: boolean;
  id: string;
}

export interface AccountBody {
  property_id: string;
}

export interface AccountOut {
  amount_cents: number;
  code: string;
}

export interface AckOut {
  id: string;
  request_id: string;
  state: string;
}

export interface AdvanceOut {
  delivered_at: null;
  recorded_attempts: number;
  request_id: string;
}

export interface AgreementBody {
  cap_cents?: number | null;
  end_date: string;
  fixed_cents?: number;
  minimum_cents?: number | null;
  rate_denominator: number;
  rate_numerator: number;
  reserve_target_total_cents?: number | null;
  responsibility_mode?: string;
  start_date: string;
}

export interface AgreementOut {
  id: string;
  property_id: string;
  request_id: string;
}

export interface AlertAttemptOut {
  delivered_at: null;
  id: string;
  status: string;
}

export interface AlertBody {
  fail?: boolean;
  kind: string;
}

export interface AlertFallbackOut {
  delivered_at: null;
  fallback_id: string;
  id: string;
  status: string;
}

export interface AlertOut {
  delivered: boolean;
  delivered_at: null;
  id: string;
  processed: (AlertFallbackOut | AlertAttemptOut)[];
}

export interface AllocationBody {
  amount_cents?: number | null;
  posting_date: string;
}

export interface AmountDateBody {
  amount_cents: number;
  posting_date?: string | null;
}

export interface AppointmentBody {
  ends_at: string;
  starts_at: string;
  timezone: string;
}

export interface AppointmentOut {
  ends_at: string;
  expires_at: string | null;
  external_event_created: boolean;
  external_event_key: string | null;
  id: string;
  starts_at: string;
  status: string;
  timezone: string;
  version: number;
}

export interface Approve {
  action: string;
  estimate_version: number;
  spending_limit_cents: number;
}

export interface ApproveBody {
  posting_date?: string | null;
  reason: string;
  snapshot_hash: string;
}

export interface ApprovedBatchOut {
  approval_id: string;
  currency: string;
  expires_at: string | null;
  id: string;
  items: BatchItemOut[];
  property_id: string;
  retained_reserves_cents: number;
  snapshot_hash: string | null;
  status: string;
  submitted: boolean;
  total_cents: number;
}

export interface ArrangeRepair {
  action: string;
  ends_at: string;
  estimate_cents?: number | null;
  scope: string;
  starts_at: string;
  timezone: string;
}

export interface Assign {
  action: string;
  contractor_profile_id: string;
  scope: string;
}

export interface AssignmentBody {
  contractor_profile_id: string;
  scope: string;
}

export interface AssignmentOut {
  assignment_id: string;
  status: string;
  work_order_id: string;
}

export interface Availability {
  action: string;
  windows: string[];
}

export interface BackgroundWorkerOut {
  failure_count: number;
  heartbeat_at: string | null;
  last_error_type: string | null;
  last_success_at: string | null;
  status: string;
}

export interface BalanceOut {
  accounts: AccountOut[];
  currency: string;
  owners: OwnerOut[];
  property_id: string;
}

export interface BankAccountBody {
  display_name: string;
  masked_label: string;
}

export interface BankAccountOut {
  currency: string;
  display_name: string;
  id: string;
  masked_label: string;
  request_id: string;
}

export interface BankImportBody {
  csv_text?: string | null;
  format?: string | null;
  transactions?: BankTransactionBody[];
}

export interface BankItemOut {
  amount_cents: number;
  bank_account_id: string;
  currency: string;
  external_id: string;
  id: string;
  matched_cents: number;
  posted_on: string;
}

export interface BankListOut {
  currency: string;
  items: BankItemOut[];
  next_cursor: string | null;
}

export interface BankTransactionBody {
  amount_cents: number;
  bank_account_id: string;
  external_id: string;
  posted_on: string;
}

export interface BatchItemOut {
  amount_cents: number;
  channel?: "ZELLE" | "VENMO" | "STRIPE_ACH" | null;
  destination_label?: string | null;
  destination_version: number | null;
  id: string;
  kind: string;
  liability_id: string | null;
  provider_key: string;
  recipient_id: string;
  status: string;
}

export interface BatchOut {
  currency: string;
  expires_at: string | null;
  id: string;
  items: BatchItemOut[];
  property_id: string;
  retained_reserves_cents: number;
  snapshot_hash: string | null;
  status: string;
  submitted: boolean;
  total_cents: number;
}

export interface BridgeOut {
  expires_at: string;
  mode: "demo" | "workspace";
  organization_id: string;
  properties: PropertyLinkOut[];
  source: string;
}

export interface CheckoutOut {
  checkout_url: string;
  rent_id: string;
}

export interface Complete {
  action: string;
  media_ids: string[];
  notes: string;
}

export interface CompletionBody {
  notes?: string;
}

export interface CompletionOut {
  payable_journal_id: null;
  request_id: string;
  status: string;
  work_order_id: string;
}

export interface ConfirmVisit {
  action: string;
  appointment_id: string;
  entry_permission: "GRANTED" | "DENIED";
}

export interface ConnectionBody {
  source: "guest_recovery" | "cleaner_scheduler";
}

export interface ConnectionOut {
  expires_at: string;
  mode: "demo" | "workspace";
  organization_id: string;
  source: string;
  token: string;
}

export interface CreditNoteOut {
  credit_note_id: string;
  credited_cents: number;
  currency: string;
  id: string;
  journal_id: string;
  original_payable_journal_id: string;
  payable_journal_id: string | null;
  property_id: string;
  settled_cents: number;
  status: string;
  tax_cents: number;
  total_cents: number;
}

export interface DeescalateOut {
  emergency: boolean;
  id: string;
}

export interface DepositBody {
  bank_account_id: string;
  deposited_on: string;
  items: DepositItem[];
  property_id: string;
  slip_reference: string;
}

export interface DepositItem {
  amount_cents: number;
  receipt_id: string;
}

export interface DepositOut {
  currency: string;
  id: string;
  request_id: string;
  total_cents: number;
}

export interface DestinationOut {
  id: string;
  masked_label: string;
  party_id: string;
  version: number;
}

export interface DispositionBody {
  decision_note: string;
  reason: string;
}

export interface DispositionOut {
  automated: boolean;
  decided_by: string;
  id: string;
}

export interface DownloadOut {
  download_url: string;
  expires_in_seconds: number;
  request_id: string;
  scanner_name: string | null;
  video_understanding: boolean;
}

export interface DraftBatchOut {
  currency: string;
  expires_at: string | null;
  id: string;
  items: BatchItemOut[];
  property_id: string;
  request_id: string;
  retained_reserves_cents: number;
  snapshot_hash: string | null;
  status: string;
  submitted: boolean;
  total_cents: number;
}

export interface DraftBody {
  as_of: string;
  liability_ids?: string[] | null;
  management_party_id?: string | null;
  property_id: string;
}

export interface ErrorBody {
  code: string;
  details: ErrorDetails;
  message: string;
  retryable: boolean;
}

export interface ErrorDetails {
  errors?: ErrorIssue[] | null;
}

export interface ErrorEnvelope {
  error: ErrorBody;
  request_id: string;
}

export interface ErrorIssue {
  loc: string[];
  msg: string;
}

export interface EscalationDestinationOut {
  delivered_at: null;
  fail_next: boolean;
  id: string;
  label: string;
  role: string;
}

export interface EscalationOut {
  delivered_at: null;
  escalation_id: string;
  request_id: string;
  ticket_id: string;
}

export interface Estimate {
  action: string;
  estimate_cents: number;
  scope: string;
}

export interface EstimateBody {
  estimate_cents: number;
}

export interface EstimateOut {
  authorization_state: string;
  spending_limit: null;
}

export interface EvaluationOut {
  configuration_code: string | null;
  disclosure: string;
  final_denial: boolean;
  formal_screening_permitted: boolean;
  input_hash: string;
  intake_version: number;
  missing_fields: string[];
  policy_fixture: boolean | null;
  policy_version: number | null;
  prospect_id: string;
  request_id: string;
  result: string;
  rule_results: (RuleReasonOut | RuleHitOut)[];
}

export interface EvidenceBody {
  posting_date?: string | null;
  reference: string;
}

export interface EvidenceOut {
  amount_cents: number;
  bank_contacted: boolean;
  currency: string;
  id: string;
  kind: string;
  reference: string;
  settled: boolean;
  simulator: boolean;
}

export interface ExportArtifactOut {
  batch_id: string;
  items: ExportItemOut[];
  settled: boolean;
  snapshot_hash: string | null;
  submitted: boolean;
}

export interface ExportItemOut {
  amount_cents: number;
  destination_version: number | null;
  id: string;
  kind: string;
  provider_key: string;
}

export interface ExportOut {
  artifact: ExportArtifactOut;
  artifact_hash: string;
  batch_id: string;
  duplicate_download: boolean;
  id: string;
  settled: boolean;
  status: string;
}

export interface FeeSettlementBody {
  amount_cents: number;
  posting_date: string;
  property_id: string;
}

export interface GrantOut {
  resource_id: string | null;
  resource_type: string | null;
  role: string;
}

export interface HealthOut {
  local_auth_enabled: boolean;
  request_id: string;
  status: string;
}

export interface HoldBody {
  dst_resolution?: string | null;
  local_end?: string | null;
  local_start: string;
  property_id: string;
  prospect_id: string;
  resource_id: string;
  timezone: string;
  unit_id?: string | null;
}

export interface ImportBody {
  conversation_id: string;
  description: string;
  external_property_id: string;
  issue_id: string;
  reservation_id: string;
  source_fingerprint: string;
}

export interface ImportOut {
  created: number;
  existing: number;
  request_id: string;
}

export interface InquiryBody {
  address_hint?: string | null;
  external_listing_id?: string | null;
  provider: string;
  provider_message_id: string;
}

export interface InquiryCreatedOut {
  ambiguous: boolean;
  clarification: string;
  disclosure: string;
  duplicate: boolean;
  id: string;
  prospect_id: string | null;
  request_id: string;
}

export interface InquiryDuplicateOut {
  ambiguous: boolean;
  clarification: string;
  duplicate: boolean;
  id: string;
  prospect_id: string | null;
  request_id: string;
}

export interface IntakeFieldOut {
  field_key: string;
  reason: string | null;
  status: string;
  value_text: string | null;
}

export interface IntakeLinkOut {
  request_id: string;
  token: string;
}

export interface IntakeMessageOut {
  assistance_animal_requested: boolean;
  disclosure: string;
  income_monthly_cents: number | null;
  income_original_cents: number | null;
  income_period: string | null;
  income_source: string | null;
  income_treated_as_zero: boolean;
  income_unverified: boolean;
  lease_months: number | null;
  model_adapter: string;
  move_in_date: string | null;
  occupant_count: number | null;
  pets_declared: boolean | null;
  questions: string[];
  rental_history: string | null;
  request_id: string;
  version: number;
}

export interface IntakeOut {
  assistance_animal_requested: boolean;
  income_monthly_cents: number | null;
  income_original_cents: number | null;
  income_period: string | null;
  income_source: string | null;
  income_unverified: boolean;
  lease_months: number | null;
  move_in_date: string | null;
  occupant_count: number | null;
  pets_declared: boolean | null;
  rental_history: string | null;
  version: number;
}

export interface IntakeUpdatedOut {
  assistance_animal_requested: boolean;
  disclosure: string;
  income_monthly_cents: number | null;
  income_original_cents: number | null;
  income_period: string | null;
  income_source: string | null;
  income_treated_as_zero: boolean;
  income_unverified: boolean;
  lease_months: number | null;
  move_in_date: string | null;
  occupant_count: number | null;
  pets_declared: boolean | null;
  questions: string[];
  rental_history: string | null;
  request_id: string;
  version: number;
}

export interface InvitationBody {
  external_reference?: string | null;
}

export interface InvitationOut {
  formal_screening_permitted: boolean;
  id: string;
  report_ordered: boolean;
}

export interface InvoiceBody {
  contractor_party_id: string;
  currency?: string;
  invoice_number: string;
  lines: InvoiceLineBody[];
  property_id: string;
  tax_cents: number;
  total_cents: number;
}

export interface InvoiceCreatedOut {
  credited_cents: number;
  currency: string;
  id: string;
  payable_journal_id: string | null;
  property_id: string;
  request_id: string;
  settled_cents: number;
  status: string;
  tax_cents: number;
  total_cents: number;
}

export interface InvoiceLineBody {
  description: string;
  line_total_cents: number;
  quantity: number;
  unit_price_cents: number;
}

export interface InvoiceOut {
  credited_cents: number;
  currency: string;
  id: string;
  payable_journal_id: string | null;
  property_id: string;
  settled_cents: number;
  status: string;
  tax_cents: number;
  total_cents: number;
}

export interface IssueEventOut {
  actor_id: string | null;
  before_status: string | null;
  created_at: string;
  id: string;
  issue_id: string;
  note: string;
  organization_id: string;
  source: string;
  status: string;
  ticket_id: string;
  version: number;
}

export interface IssueOut {
  confirmed_at: string | null;
  confirmed_by: string | null;
  created_at: string;
  evidence: string;
  id: string;
  key: string;
  organization_id: string;
  status: string;
  ticket_id: string;
  title: string;
  updated_at: string;
  version: number;
}

export interface IssueUpdate {
  note?: string | null;
  status: "OPEN" | "WAITING_PARTS" | "RESOLUTION_REPORTED" | "TENANT_CONFIRMED";
  version: number;
}

export interface IssuesOut {
  events: IssueEventOut[];
  items: IssueOut[];
}

export interface KnowledgeCreate {
  instructions: string;
  model?: string;
  part_details?: string;
  problem_key: string;
  property_id: string;
  reference_media_ids?: string[];
  title: string;
  verified?: boolean;
}

export interface KnowledgeEntry {
  active: boolean;
  created_at: string;
  id: string;
  instructions: string;
  model: string;
  part_details: string;
  problem_key: string;
  property_id: string;
  reference_media_ids: string[];
  title: string;
  updated_at: string;
  verified: boolean;
  verified_at: string | null;
  verified_by: string | null;
  version: number;
}

export interface KnowledgeList {
  approved_instructions: string[];
  entries: KnowledgeEntry[];
  problem_keys: string[];
  properties: KnowledgeProperty[];
  reference_media: KnowledgeReferenceMedia[];
}

export interface KnowledgePatch {
  active?: boolean | null;
  instructions?: string | null;
  model?: string | null;
  part_details?: string | null;
  problem_key?: string | null;
  reference_media_ids?: string[] | null;
  title?: string | null;
  verified?: boolean | null;
  version: number;
}

export interface KnowledgeProperty {
  id: string;
  name: string;
}

export interface KnowledgeReferenceMedia {
  content_type: string;
  created_at: string;
  id: string;
  property_id: string;
}

export interface LeaseBody {
  agreed_rent_cents: number;
  end_date: string;
  start_date: string;
  unit_id: string;
}

export interface LeaseItemOut {
  agreed_rent_cents: number;
  id: string;
}

export interface LeaseOut {
  agreed_rent_cents: number;
  id: string;
  request_id: string;
  unit_id: string;
}

export interface LeasePageOut {
  items: LeaseItemOut[];
}

export interface LeasePartyBody {
  user_id: string;
}

export interface LeasePartyOut {
  id: string;
  lease_id: string;
  user_id: string;
}

export interface LedgerItemOut {
  id: string;
  posting_date: string;
  reversal_of_id: string | null;
  source_id: string;
  source_type: string;
}

export interface LedgerOut {
  accounts: AccountOut[];
  currency: string;
  items: LedgerItemOut[];
  next_cursor: string | null;
  owners: OwnerOut[];
  property_id: string;
}

export interface ListingBody {
  asking_rent_cents: number;
  display_label: string;
  external_listing_id: string;
  external_source: string;
  property_id: string;
  unit_id?: string | null;
}

export interface ListingCreatedOut {
  id: string;
  request_id: string;
}

export interface ListingItemOut {
  asking_rent_cents: number;
  display_label: string;
  id: string;
  property_id: string;
}

export interface ListingPageOut {
  items: ListingItemOut[];
}

export interface LoginBody {
  password: string;
  subject: string;
}

export interface LoginOut {
  auth_method: string;
  display_name: string;
  organization_id: string;
  production_oidc: boolean;
  request_id: string;
  token: string;
  token_type: string;
  user_id: string;
}

export interface MaintenanceAnalysisOut {
  assistant_stage?: "triage" | "handoff" | null;
  audio_analyzed: boolean;
  category: string;
  follow_up: string[];
  historical_examples?: number;
  images_analyzed: number;
  issues?: MaintenanceIssueOut[];
  model: string | null;
  next_action: string;
  plan_version?: number | null;
  priority: string;
  repair_steps?: string[];
  source?: "rules" | "model" | null;
  status: "ready" | "unavailable" | "failed" | "stale";
  summary: string;
  trade?: string | null;
  video_frames_analyzed: number;
}

export interface MaintenanceAppointmentOut {
  entry_permission: string;
  id: string;
  status: string;
}

export interface MaintenanceConfirmOut {
  id: string;
  status: string;
}

export interface MaintenanceContextOut {
  can_manage: boolean;
  homes: MaintenanceHomeOut[];
  photos_enabled: boolean;
  request_id: string;
}

export interface MaintenanceHistoryOut {
  created_at: string;
  reason: string | null;
  status: string;
}

export interface MaintenanceHomeOut {
  lease_id: string;
  property_name: string;
  unit_id: string;
  unit_label: string;
}

export interface MaintenanceIssueOut {
  evidence: string;
  key: string;
  status: "open" | "reported_resolved";
  title: string;
}

export interface MaintenanceIssueRecordOut {
  confirmed_at: string | null;
  confirmed_by: string | null;
  created_at: string;
  evidence: string;
  id: string;
  key: string;
  organization_id: string;
  status: string;
  ticket_id: string;
  title: string;
  updated_at: string;
  version: number;
}

export interface MaintenanceMediaOut {
  content_type: string | null;
  id: string;
  rejection_reason: string | null;
  status: string;
}

export interface MaintenanceMessageOut {
  author_role?: "tenant" | "manager" | "contractor" | "system";
  body: string;
  created_at: string;
  id: string;
}

export interface MaintenancePageOut {
  items: MaintenanceSummaryOut[];
  next_cursor: string | null;
  request_id: string;
}

export interface MaintenanceSummaryOut {
  category: string;
  created_at: string;
  description: string;
  emergency: boolean;
  id: string;
  priority: string;
  property_name: string | null;
  status: string;
  ticket_number: number;
  unit_label: string | null;
}

export interface MatchBody {
  amount_cents: number;
  bank_transaction_id: string;
  deposit_batch_id: string;
}

export interface MatchOut {
  amount_cents: number;
  bank_transaction_id: string;
  currency: string;
  deposit_batch_id: string;
  id: string;
  posted_journal: boolean;
}

export interface MeOut {
  auth_method: string;
  capabilities: string[];
  display_name: string;
  grants: GrantOut[];
  organization_id: string;
  production_oidc: boolean;
  request_id: string;
  roles: string[];
  user_id: string;
}

export interface Message {
  action: string;
  body: string;
  media_ids?: string[];
}

export interface MessageBody {
  body: string;
  classifier_result?: string | null;
  field_key?: string | null;
}

export interface NoteBody {
  note: string;
}

export interface OnboardingOut {
  onboarding_url: string;
  recipient_id: string;
}

export interface OpeningOut {
  amount_cents: number;
  currency: string;
  id: string;
  request_id: string;
}

export interface OpeningReserveBody {
  amount_cents: number;
  bank_account_id: string;
  owner_party_id: string;
  posting_date: string;
  property_id: string;
  reason: string;
}

export interface OperationsOut {
  background_worker: BackgroundWorkerOut;
  properties: grok_bot__api__routes__maintenance_operations__PropertyOut[];
  requests: RequestOut[];
  worker_health: WorkerHealthOut;
  workers: WorkerOut[];
}

export interface OperationsQueueOut {
  alerts_sent: boolean;
  approved_batches: number;
  dead_letters: number;
  delivery_enabled: boolean;
  unassigned_emergency_tickets: number;
  unknown_payments: number;
}

export interface OutcomeBody {
  outcome: "settle" | "timeout" | "fail";
}

export interface OwnerLinkBody {
  party_id: string;
  user_id: string;
}

export interface OwnerLinkOut {
  id: string;
}

export interface OwnerOut {
  owner_party_id: string;
  reserve_cents: number;
  unrestricted_cents: number;
}

export interface OwnershipBody {
  end_date: string;
  shares: ShareBody[];
  start_date: string;
}

export interface OwnershipOut {
  id: string;
  property_id: string;
  request_id: string;
  shares: ShareOut[];
}

export interface PartyBody {
  display_name: string;
  kind: string;
}

export interface PartyCreatedOut {
  display_name: string;
  id: string;
  kind: string;
  request_id: string;
}

export interface PartyOut {
  display_name: string;
  id: string;
  kind: string;
}

export interface PartyPageOut {
  items: PartyOut[];
}

export interface PeriodCloseBody {
  period_end: string;
  period_start: string;
  reason: string;
}

export interface PeriodOut {
  id: string;
  status: string;
}

export interface PhoneEventOut {
  body: string;
  channel: "SMS" | "VOICEMAIL";
  created_at: string;
  direction: "INBOUND" | "OUTBOUND";
  from_number: string;
  id: string;
  recipient_kind: "RESIDENT" | "MAINTENANCE";
  request_id?: string | null;
  status: string;
  ticket_id: string;
  ticket_number: number;
  to_number: string;
}

export interface PhoneInboxOut {
  configured: boolean;
  events: PhoneEventOut[];
  maintenance_number: string | null;
  mode: "simulated" | "twilio";
  phone_number: string | null;
  request_id: string;
  simulation_enabled: boolean;
}

export interface PolicyBody {
  automatic_final_denial?: boolean;
  effective_at: string;
  fixture?: boolean;
  legal_review_reference: string;
  missing_action?: string;
  review_reason: string;
  rules: PolicyRule[];
}

export interface PolicyOut {
  automatic_final_denial: boolean;
  fixture: boolean;
  id: string;
  version: number;
}

export interface PolicyRule {
  failure_action?: string;
  field: string;
  id: string;
  operator: string;
  ratio_denominator?: number | null;
  ratio_numerator?: number | null;
  value?: number | null;
  values?: number[] | null;
}

export interface PostingBody {
  posting_date: string;
}

export interface PostingDateBody {
  posting_date: string;
}

export interface ProfileBody {
  approved?: boolean;
  party_id: string;
  trades?: string;
  user_id?: string | null;
}

export interface ProfileOut {
  approved: boolean;
  id: string;
  trades: string;
}

export interface PropertyBody {
  property_id: string;
}

export interface PropertyLinkBody {
  external_property_id: string;
  unit_id: string;
}

export interface PropertyLinkOut {
  external_property_id: string;
  label: string;
  name: string;
  unit_id: string;
}

export interface PropertyPageOut {
  items: grok_bot__api__success__PropertyOut[];
  next_cursor: string | null;
  request_id: string;
}

export interface PropertyPatch {
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  country_code?: string | null;
  name?: string | null;
  postal_code?: string | null;
  region?: string | null;
  timezone?: string | null;
}

export interface PropertyRepairsOut {
  external_property_id: string;
  has_more: boolean;
  repairs: RepairOut[];
}

export interface PropertyWrite {
  address_line1: string;
  address_line2?: string | null;
  city: string;
  country_code: string;
  name: string;
  postal_code: string;
  region: string;
  timezone: string;
}

export interface ProspectOut {
  disclosure: string;
  final_housing_decision: boolean;
  id: string;
  intake: IntakeOut;
  listing_id: string | null;
  property_id: string | null;
  questions: string[];
  request_id: string;
  state: string;
  unverified: boolean;
}

export interface ProspectStart {
  listing_id?: string | null;
}

export interface QuarantineOut {
  id: string;
  request_id: string;
  status: string;
}

export interface Reason {
  action: "decline" | "reject_estimate" | "reopen" | "resolve_self";
  reason: string;
}

export interface ReasonAmountBody {
  amount_cents: number;
  posting_date: string;
  reason: string;
}

export interface ReasonBody {
  reason?: string;
}

export interface ReceiptBody {
  amount_cents: number;
  currency?: string;
  lease_id: string;
  method: string;
  payer_party_id: string;
  posting_date: string;
  property_id: string;
  received_at: string;
  reference: string;
  service_period?: string | null;
  unit_id: string;
}

export interface ReceiptCreatedOut {
  allocated_cents: number;
  amount_cents: number;
  available_at: string | null;
  available_cents: number;
  currency: string;
  deposited_cents: number;
  id: string;
  method: string;
  property_id: string;
  receipt_number: number;
  request_id: string;
  returned_cents: number;
  status: string;
  verified_cents: number;
}

export interface ReceiptOut {
  allocated_cents: number;
  amount_cents: number;
  available_at: string | null;
  available_cents: number;
  currency: string;
  deposited_cents: number;
  id: string;
  method: string;
  property_id: string;
  receipt_number: number;
  returned_cents: number;
  status: string;
  verified_cents: number;
}

export interface ReceiptReturnOut {
  allocated_cents: number;
  amount_cents: number;
  available_at: string | null;
  available_cents: number;
  currency: string;
  deposited_cents: number;
  id: string;
  method: string;
  property_id: string;
  receipt_number: number;
  return_journal_id: string;
  returned_cents: number;
  status: string;
  verified_cents: number;
}

export interface RecipientBody {
  party_id: string;
}

export interface ReconcileBody {
  posting_date: string;
}

export interface ReconciliationBody {
  bank_account_id: string;
  period_end: string;
  period_start: string;
  statement_closing_cents: number;
  statement_opening_cents: number;
  timing_item_cents?: number;
}

export interface ReconciliationOut {
  currency: string;
  difference_cents: number;
  id: string;
  ledger_cash_cents: number;
  obligation_cents: number;
  statement_closing_cents: number;
  status: string;
}

export interface RefreshBody {
  posting_date: string;
}

export interface ReimbursementBody {
  posting_date: string;
  topup_id: string;
}

export interface RentChargeBody {
  amount_cents: number;
  description: string;
  due_on: string;
  lease_id: string;
}

export interface RentChargeOut {
  amount_cents: number;
  currency: string;
  id: string;
  journal_posted: boolean;
  request_id: string;
}

export interface RepairOut {
  priority: string;
  status: string;
  ticket_id: string;
  ticket_number: number;
  updated_at: string;
}

export interface ReplyBody {
  body: string;
  ticket_id: string;
}

export interface RequestOut {
  description: string;
  id: string;
  last_activity_at: string;
  next_action: string;
  notification_status: string | null;
  owner_name: string | null;
  priority: string;
  reason_codes: string[];
  status: string;
  ticket_number: number;
}

export interface RescheduleOut {
  appointment: AppointmentOut;
  previous_id: string;
  previous_reminders: string;
}

export interface ResourceBody {
  display_name: string;
}

export interface ResourceOut {
  id: string;
  kind: string;
}

export interface RespondBody {
  accept: boolean;
}

export interface RespondOut {
  id: string;
  status: string;
}

export interface ReturnItemOut {
  disbursements_frozen: boolean;
  id: string;
  recovery_account: string;
  simulator: boolean;
  status: string;
}

export interface ReversalOut {
  currency: string;
  id: string;
  posted: boolean;
  reason: string;
  reversal_of_id: string;
}

export interface ReviewBody {
  reason?: string | null;
  resolution: string;
}

export interface ReviewItemOut {
  final_housing_decision: boolean;
  id: string;
  missing_fields: string[];
  opened_at: string;
  property_id: string | null;
  prospect_id: string;
  prospect_state: string;
  reason: string;
  rule_ids: string[];
  state: string;
}

export interface ReviewPageOut {
  items: ReviewItemOut[];
}

export interface ReviewResolvedOut {
  exception_granted: boolean;
  final_housing_decision: boolean;
  id: string;
  resolution: string;
}

export interface RuleHitOut {
  result: string;
  rule_id: string;
}

export interface RuleReasonOut {
  reason: string;
  result: string;
  rule_id: string;
}

export interface ScanOut {
  id: string;
  request_id: string;
  scan_code: string;
  scanner_name: string | null;
  status: string;
  ticket_id: string;
  video_understanding: boolean;
}

export interface ScheduleBody {
  buffer_minutes: number;
  day_end: string;
  day_start: string;
  duration_minutes: number;
  fixture?: boolean;
  hold_minutes: number;
  label?: string;
  min_notice_minutes: number;
  open_weekdays: number[];
  timezone: string;
}

export interface ScheduleOut {
  fixture: boolean;
  id: string;
}

export interface SecretBody {
  code: string;
}

export interface ShareBody {
  owner_party_id: string;
  weight: number;
}

export interface ShareOut {
  owner_party_id: string;
  weight: number;
}

export interface Simple {
  action: "accept" | "start_work" | "confirm_completion";
}

export interface SimulateBody {
  body: string;
  channel: "SMS" | "VOICEMAIL";
  from_number: string;
}

export interface SimulatedAccountOut {
  balance_cents: number;
  id: string;
  next_outcome: "settle" | "timeout" | "fail";
  property_id: string;
  property_name: string;
}

export interface SimulatedBankOut {
  accounts: SimulatedAccountOut[];
  bank_contacted: boolean;
  batches: BatchOut[];
  enabled: boolean;
  simulator: boolean;
  transactions: SimulatedTransactionOut[];
}

export interface SimulatedTransactionOut {
  account_id: string;
  amount_cents: number;
  channel: "ZELLE" | "VENMO";
  created_at: string;
  id: string;
  item_id: string | null;
  kind: "RECEIPT" | "PAYOUT";
  receipt_id: string | null;
  reference: string;
  status: "SETTLED" | "FAILED";
}

export interface SlotOut {
  ends_at: string;
  resource_id: string;
  starts_at: string;
  timezone: string;
}

export interface SlotPageOut {
  configuration: string;
  items: SlotOut[];
  timezone: string;
}

export interface SourceRepairOut {
  issue_id: string;
  priority: string;
  source_fingerprint: string;
  status: string;
  ticket_id: string;
  ticket_number: number;
  updated_at: string;
}

export interface StatementAccountOut {
  amount_cents: number;
  code: string;
}

export interface StatementBody {
  owner_party_id: string;
  period_end: string;
  period_start: string;
  property_id: string;
  reason: string;
}

export interface StatementIssuedOut {
  id: string;
  snapshot: StatementSnapshotOut;
  snapshot_hash: string;
  supersedes: string | null;
  version: number;
}

export interface StatementOut {
  id: string;
  owner_party_id: string;
  period_end: string;
  period_start: string;
  reason: string;
  snapshot: StatementSnapshotOut;
  snapshot_hash: string;
  unrestricted_cents: number | null;
  version: number;
}

export interface StatementPageOut {
  items: StatementOut[];
}

export interface StatementSnapshotOut {
  accounts: StatementAccountOut[];
  fixture: boolean;
  owner_party_id: string;
  period_end: string;
  period_start: string;
  property_id: string;
  reserve_cents: number;
  unrestricted_cents: number;
}

export interface StepUpOut {
  id: string;
  method: "LOCAL_DEV_PASSWORD" | "SIMULATED_APPROVAL";
  production_oidc: boolean;
  request_id: string;
}

export interface StoredOut {
  request_id: string;
  stored: boolean;
}

export interface StripeOut {
  configured: boolean;
  fee_payer: string;
  payouts: StripePayoutOut[];
  properties: StripePropertyOut[];
  recipients: StripeRecipientOut[];
  rents: StripeRentOut[];
  sandbox: boolean;
  webhook_configured: boolean;
  worker_enabled: boolean;
}

export interface StripePayoutOut {
  amount_cents: number;
  batch_id: string;
  id: string;
  item_id: string;
  last_error: string | null;
  payout_id: string | null;
  status: string;
  transfer_id: string | null;
}

export interface StripePropertyOut {
  bank_account_id: string;
  property_id: string;
  property_name: string;
}

export interface StripeRecipientOut {
  account_id: string | null;
  destination_id: string | null;
  display_name: string;
  party_id: string;
  status: string;
}

export interface StripeRentOut {
  amount_cents: number;
  checkout_url: string | null;
  fee_cents: number;
  fee_due_cents: number;
  id: string;
  lease_id: string;
  property_id: string;
  status: string;
}

export interface StripeWebhookOut {
  accepted: boolean;
  sandbox: boolean;
}

export interface SubmitBatchOut {
  bank_contacted: boolean;
  currency: string;
  expires_at: string | null;
  id: string;
  items: BatchItemOut[];
  property_id: string;
  retained_reserves_cents: number;
  simulator: boolean;
  snapshot_hash: string | null;
  status: string;
  submitted: boolean;
  total_cents: number;
}

export interface SubmitBody {
  posting_date: string;
  scripts?: Record<string, string>;
}

export interface SwitchBody {
  calendar_enabled: boolean;
  messaging_enabled: boolean;
  payment_enabled: boolean;
}

export interface SwitchOut {
  calendar_enabled: boolean;
  messaging_enabled: boolean;
  payment_enabled: boolean;
}

export interface TicketBody {
  category?: string | null;
  contact?: string | null;
  contact_id?: string | null;
  description: string;
  entry_permission?: string | null;
  frequency?: string | null;
  lease_id?: string | null;
  location?: string | null;
  media_reason?: string | null;
  media_status?: string | null;
  onset?: string | null;
  preferred_access_windows?: string[] | null;
  safety_concerns?: string | null;
  unit_id?: string | null;
}

export interface TicketContractorOut {
  analysis?: MaintenanceAnalysisOut | null;
  category: string;
  created_at: string;
  description: string;
  emergency: boolean;
  handoff: boolean;
  history: MaintenanceHistoryOut[];
  id: string;
  intake: IntakeFieldOut[];
  media: MaintenanceMediaOut[];
  messages: MaintenanceMessageOut[];
  missing_fields: string[];
  model_adapter: string;
  next_questions: string[];
  notification_status?: string | null;
  priority: string;
  property_name: string | null;
  questions_source: string;
  request_id: string;
  safety_message: string | null;
  status: string;
  ticket_number: number;
  unit_label: string | null;
  urgent_triage: boolean;
  verification: string;
  video_understanding: boolean;
}

export interface TicketPublicOut {
  emergency: boolean;
  id: string;
  intake_token: string;
  missing_fields: string[];
  model_adapter: string;
  next_questions: string[];
  priority: string;
  questions_source: string;
  request_id: string;
  safety_message: string | null;
  status: string;
  ticket_number: number;
  verification: string;
  video_understanding: boolean;
}

export interface TicketStaffOut {
  analysis?: MaintenanceAnalysisOut | null;
  category: string;
  created_at: string;
  description: string;
  emergency: boolean;
  handoff: boolean;
  history: MaintenanceHistoryOut[];
  id: string;
  intake: IntakeFieldOut[];
  intake_token: string;
  media: MaintenanceMediaOut[];
  messages: MaintenanceMessageOut[];
  missing_fields: string[];
  model_adapter: string;
  next_questions: string[];
  notification_status?: string | null;
  priority: string;
  property_name: string | null;
  questions_source: string;
  request_id: string;
  safety_message: string | null;
  status: string;
  ticket_number: number;
  unit_label: string | null;
  urgent_triage: boolean;
  verification: string;
  video_understanding: boolean;
}

export interface TopUpOut {
  currency: string;
  owners: Record<string, number>;
  property_id: string;
  top_up_cents: number;
}

export interface TourCancelOut {
  id: string;
  reminders: string;
  status: string;
}

export interface TourCompleteOut {
  id: string;
  status: string;
}

export interface TransitionBody {
  action: string;
  duplicate_of_id?: string | null;
  reason?: string | null;
  status?: string | null;
}

export interface TransitionDuplicateOut {
  deleted: boolean;
  duplicate_of_id: string;
  id: string;
  status: string;
}

export interface TransitionStatusOut {
  id: string;
  status: string;
}

export interface UnitOut {
  created_at: string;
  id: string;
  label: string;
  organization_id: string;
  property_id: string;
  request_id: string;
  version: number;
}

export interface UnitPageOut {
  items: UnitOut[];
  next_cursor: string | null;
  request_id: string;
}

export interface UnitPatch {
  label: string;
}

export interface UnitWrite {
  label: string;
}

export interface UnlinkBody {
  external_property_id: string;
}

export interface UnlinkOut {
  removed: boolean;
}

export interface UnverifiedBody {
  description: string;
  phone?: string | null;
  unit_id?: string | null;
}

export interface UploadBody {
  content_type: string;
  filename: string;
  sha256: string;
  size_bytes: number;
}

export interface UploadHeadersOut {
  "Content-Type": string;
}

export interface UploadOut {
  expires_in_seconds: number;
  id: string;
  request_id: string;
  required_headers: UploadHeadersOut;
  status: string;
  ticket_id: string;
  upload_url: string;
}

export interface Visit {
  action: string;
  ends_at: string;
  starts_at: string;
  timezone: string;
}

export interface WebhookOut {
  delivered: boolean;
  provider_event_id: string;
  request_id: string;
  status: string;
}

export interface WorkerHealthOut {
  failed_notifications: number;
  history_configured: boolean;
  pending_notifications: number;
  phone_configured: boolean;
  unknown_notifications: number;
}

export interface WorkerOut {
  accepting_work: boolean;
  active: boolean;
  approved: boolean;
  availability_note: string;
  id: string;
  max_open_jobs: number;
  name: string;
  open_jobs: number;
  service_categories: string[];
  service_property_ids: string[];
  user_id: string | null;
  version: number;
}

export interface WorkerUpdate {
  accepting_work?: boolean | null;
  approved?: boolean | null;
  availability_note?: string | null;
  max_open_jobs?: number | null;
  service_categories?: ("leak" | "electrical" | "hvac" | "appliance" | "structural" | "pest_mold" | "lock" | "general")[] | null;
  service_property_ids?: string[] | null;
  version: number;
}

export interface WorkflowAppointment {
  assignment_id: string | null;
  contractor_accepted: boolean;
  ends_at: string;
  entry_granted_by: string | null;
  entry_permission: string;
  id: string;
  starts_at: string;
  status: string;
  timezone: string;
}

export interface WorkflowAssignment {
  contractor_profile_id: string;
  created_at: string;
  id: string;
  scope: string;
  status: "PENDING" | "ACCEPTED" | "DECLINED";
  updated_at: string;
}

export interface WorkflowAvailability {
  windows: string[];
}

export interface WorkflowBoardItem {
  description: string;
  due_flags: string[];
  home: WorkflowHome | null;
  id: string;
  job_status: string;
  next_step: string;
  priority: string;
  status: string;
  ticket_number: number;
  verification: string;
}

export interface WorkflowBoardOut {
  contractors: WorkflowContractor[];
  items: WorkflowBoardItem[];
  next_cursor?: string | null;
  role: "tenant" | "manager" | "contractor";
}

export interface WorkflowContractor {
  id: string;
  name: string;
  trades: string;
}

export interface WorkflowDetailOut {
  appointments: WorkflowAppointment[];
  assignment: WorkflowAssignment | null;
  availability: WorkflowAvailability;
  available_actions: string[];
  completion_media: WorkflowMedia[];
  contractors: WorkflowContractor[];
  escalation?: WorkflowEscalation | null;
  follow_up_flags: string[];
  issue_records?: MaintenanceIssueRecordOut[];
  issues?: MaintenanceIssueOut[];
  media: WorkflowMedia[];
  messages: WorkflowMessage[];
  role: "tenant" | "manager" | "contractor";
  ticket: WorkflowTicket;
  work_order: WorkflowWorkOrder | null;
}

export interface WorkflowEscalation {
  acknowledged_at: string | null;
  created_at: string;
  id: string;
  state: string;
}

export interface WorkflowHome {
  property_name: string;
  unit_label: string;
}

export interface WorkflowMedia {
  content_type: string;
  id: string;
  status: string;
}

export interface WorkflowMessage {
  author_role: "tenant" | "manager" | "contractor" | "system";
  body: string;
  created_at: string;
  id: string;
  media_ids: string[];
  sender_label: string;
}

export interface WorkflowTicket {
  description: string;
  home: WorkflowHome | null;
  id: string;
  priority: string;
  status: string;
  ticket_number: number;
  verification: string;
}

export interface WorkflowWorkOrder {
  approved_at: string | null;
  approved_by: string | null;
  approved_version: number | null;
  assignment_id: string;
  authorization_state: string;
  completed_at: string | null;
  completion_media_ids: string[];
  completion_notes: string | null;
  confirmed_at: string | null;
  created_at: string;
  estimate_cents: number | null;
  estimate_scope: string | null;
  estimate_version: number;
  id: string;
  spending_limit_cents: number | null;
  started_at: string | null;
  updated_at: string;
  workflow_managed: boolean;
}

export interface WorkspaceAppBody {
  project: "guest_recovery" | "cleaner_scheduler";
  url: string;
}

export interface WorkspaceOut {
  apps: WorkspaceAppBody[];
  mode: "demo" | "workspace";
  properties: PropertyLinkOut[];
  units: Record<string, string>[];
}

export interface grok_bot__api__routes__distributions__DestinationBody {
  channel?: "ZELLE" | "VENMO";
  masked_label: string;
  party_id: string;
}

export interface grok_bot__api__routes__maintenance__ConfirmBody {
  contractor_accepted?: boolean;
  entry_permission: string;
  notice_evidence?: string | null;
}

export interface grok_bot__api__routes__maintenance__DestinationBody {
  fail_next?: boolean;
  label: string;
  role: string;
}

export interface grok_bot__api__routes__maintenance__IntakeBody {
  category?: string | null;
  field_key?: string | null;
  reason?: string | null;
  status?: string | null;
  value?: string | null;
}

export interface grok_bot__api__routes__maintenance_operations__PropertyOut {
  id: string;
  name: string;
}

export interface grok_bot__api__routes__prospects__ConfirmBody {
  manager_local?: boolean;
}

export interface grok_bot__api__routes__prospects__IntakeBody {
  accommodation_note?: string | null;
  assistance_animal_requested?: boolean | null;
  consents?: Record<string, boolean> | null;
  income_original_cents?: number | null;
  income_period?: string | null;
  income_source?: string | null;
  lease_months?: number | null;
  move_in_date?: string | null;
  occupant_count?: number | null;
  pets_declared?: boolean | null;
  rental_history?: string | null;
}

export interface grok_bot__api__routes__simulated_bank__RentBody {
  account_id: string;
  amount_cents: number;
  channel: "ZELLE" | "VENMO";
  lease_id: string;
  payer_party_id: string;
  posting_date: string;
  reference: string;
}

export interface grok_bot__api__routes__stripe__RentBody {
  amount_cents: number;
  lease_id: string;
  payer_party_id: string;
  posting_date: string;
  property_id: string;
  reference: string;
}

export interface grok_bot__api__success__PropertyOut {
  address_line1: string;
  address_line2: string | null;
  city: string;
  country_code: string;
  created_at: string;
  id: string;
  name: string;
  organization_id: string;
  postal_code: string;
  region: string;
  request_id: string;
  timezone: string;
  unit_count: number;
  version: number;
}

export interface apiPaths {
  "/v1/alerts": {
    post: {
      requestBody: AlertBody;
      responses: {
        "200": AlertOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/appointments/holds": {
    post: {
      requestBody: HoldBody;
      responses: {
        "201": AppointmentOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/appointments/{appointment_id}/access-evidence": {
    post: {
      parameters: {
        appointment_id: string;
      };
      requestBody: AccessBody;
      responses: {
        "200": AccessOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/appointments/{appointment_id}/cancel": {
    post: {
      parameters: {
        appointment_id: string;
      };
      responses: {
        "200": TourCancelOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/appointments/{appointment_id}/complete": {
    post: {
      parameters: {
        appointment_id: string;
      };
      responses: {
        "200": TourCompleteOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/appointments/{appointment_id}/confirm": {
    post: {
      parameters: {
        appointment_id: string;
      };
      requestBody: grok_bot__api__routes__prospects__ConfirmBody;
      responses: {
        "200": AppointmentOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/appointments/{appointment_id}/reschedule": {
    post: {
      parameters: {
        appointment_id: string;
      };
      requestBody: HoldBody;
      responses: {
        "200": RescheduleOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/assignments/{assignment_id}/respond": {
    post: {
      parameters: {
        assignment_id: string;
      };
      requestBody: RespondBody;
      responses: {
        "200": RespondOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/auth/local/login": {
    post: {
      requestBody: LoginBody;
      responses: {
        "200": LoginOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/auth/local/step-up": {
    post: {
      requestBody: LoginBody;
      responses: {
        "200": StepUpOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/bank-accounts": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: BankAccountBody;
      responses: {
        "201": BankAccountOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/bank-imports": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: BankImportBody;
      responses: {
        "201": ImportOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/bank-matches": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: MatchBody;
      responses: {
        "200": MatchOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/bank-transactions": {
    get: {
      parameters: {
        limit?: number;
        cursor?: string | null;
      };
      responses: {
        "200": BankListOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/contractor-profiles": {
    post: {
      requestBody: ProfileBody;
      responses: {
        "201": ProfileOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/deposit-batches": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: DepositBody;
      responses: {
        "201": DepositOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/distribution-batches": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: DraftBody;
      responses: {
        "201": DraftBatchOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/distribution-batches/{batch_id}": {
    get: {
      parameters: {
        batch_id: string;
      };
      responses: {
        "200": BatchOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/distribution-batches/{batch_id}/approve": {
    post: {
      parameters: {
        batch_id: string;
        "Idempotency-Key"?: string | null;
      };
      requestBody: ApproveBody;
      responses: {
        "200": ApprovedBatchOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/distribution-batches/{batch_id}/cancel": {
    post: {
      parameters: {
        batch_id: string;
      };
      responses: {
        "200": BatchOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/distribution-batches/{batch_id}/export": {
    post: {
      parameters: {
        batch_id: string;
      };
      responses: {
        "200": ExportOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/distribution-batches/{batch_id}/submit": {
    post: {
      parameters: {
        batch_id: string;
      };
      requestBody: SubmitBody;
      responses: {
        "200": SubmitBatchOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/distribution-batches/{batch_id}/validate": {
    post: {
      parameters: {
        batch_id: string;
      };
      responses: {
        "200": BatchOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/distribution-declarations/{declaration_id}/simulated-settlement": {
    post: {
      parameters: {
        declaration_id: string;
      };
      requestBody: PostingDateBody;
      responses: {
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/distribution-items/{item_id}/returns": {
    post: {
      parameters: {
        item_id: string;
      };
      requestBody: PostingBody;
      responses: {
        "200": ReturnItemOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/escalation-destinations": {
    post: {
      requestBody: grok_bot__api__routes__maintenance__DestinationBody;
      responses: {
        "201": EscalationDestinationOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/escalations/{escalation_id}/acknowledge": {
    post: {
      parameters: {
        escalation_id: string;
      };
      responses: {
        "200": AckOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/fee-settlements/simulated": {
    post: {
      requestBody: FeeSettlementBody;
      responses: {
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/health": {
    get: {
      responses: {
        "200": HealthOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/human-reviews": {
    get: {
      responses: {
        "200": ReviewPageOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/human-reviews/{review_id}/resolve": {
    post: {
      parameters: {
        review_id: string;
      };
      requestBody: ReviewBody;
      responses: {
        "200": ReviewResolvedOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/inquiries": {
    post: {
      requestBody: InquiryBody;
      responses: {
        "200": InquiryCreatedOut | InquiryDuplicateOut;
        "201": InquiryCreatedOut | InquiryDuplicateOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/invoices": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: InvoiceBody;
      responses: {
        "201": InvoiceCreatedOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/invoices/{invoice_id}": {
    get: {
      parameters: {
        invoice_id: string;
      };
      responses: {
        "200": InvoiceOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/invoices/{invoice_id}/approve": {
    post: {
      parameters: {
        invoice_id: string;
      };
      requestBody: PostingDateBody;
      responses: {
        "200": InvoiceOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/invoices/{invoice_id}/credit-notes": {
    post: {
      parameters: {
        invoice_id: string;
        "Idempotency-Key"?: string | null;
        "If-Match"?: string | null;
      };
      requestBody: ReasonAmountBody;
      responses: {
        "200": CreditNoteOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/invoices/{invoice_id}/simulated-settlement": {
    post: {
      parameters: {
        invoice_id: string;
      };
      requestBody: PostingDateBody;
      responses: {
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/journals/{journal_id}/reversals": {
    post: {
      parameters: {
        journal_id: string;
        "Idempotency-Key"?: string | null;
      };
      requestBody: ReasonAmountBody;
      responses: {
        "200": ReversalOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/kill-switches": {
    get: {
      responses: {
        "200": SwitchOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
    put: {
      requestBody: SwitchBody;
      responses: {
        "200": SwitchOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/leases": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: LeaseBody;
      responses: {
        "201": LeaseOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/leases/{lease_id}/parties": {
    post: {
      parameters: {
        lease_id: string;
      };
      requestBody: LeasePartyBody;
      responses: {
        "201": LeasePartyOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/listings": {
    get: {
      responses: {
        "200": ListingPageOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
    post: {
      requestBody: ListingBody;
      responses: {
        "201": ListingCreatedOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-appointments/{appointment_id}/confirm": {
    post: {
      parameters: {
        appointment_id: string;
      };
      requestBody: grok_bot__api__routes__maintenance__ConfirmBody;
      responses: {
        "200": MaintenanceConfirmOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-bridge": {
    get: {
      responses: {
        "200": BridgeOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-bridge/properties/{external_property_id}/repairs": {
    get: {
      parameters: {
        external_property_id: string;
      };
      responses: {
        "200": PropertyRepairsOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-bridge/requests": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: ImportBody;
      responses: {
        "200": SourceRepairOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-bridge/requests/{issue_id}": {
    get: {
      parameters: {
        issue_id: string;
      };
      responses: {
        "200": SourceRepairOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-connections": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: ConnectionBody;
      responses: {
        "200": ConnectionOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-context": {
    get: {
      responses: {
        "200": MaintenanceContextOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-escalations/advance": {
    post: {
      responses: {
        "200": AdvanceOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-intake-links": {
    post: {
      responses: {
        "200": IntakeLinkOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-knowledge": {
    get: {
      responses: {
        "200": KnowledgeList;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
    post: {
      parameters: {
        "Idempotency-Key": string;
      };
      requestBody: KnowledgeCreate;
      responses: {
        "200": KnowledgeEntry;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-knowledge/{entry_id}": {
    patch: {
      parameters: {
        entry_id: string;
        "Idempotency-Key": string;
      };
      requestBody: KnowledgePatch;
      responses: {
        "200": KnowledgeEntry;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-operations": {
    get: {
      responses: {
        "200": OperationsOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-phone": {
    get: {
      responses: {
        "200": PhoneInboxOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-phone/replies": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: ReplyBody;
      responses: {
        "201": PhoneEventOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-phone/simulate": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: SimulateBody;
      responses: {
        "201": PhoneEventOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-phone/twilio/{kind}": {
    post: {
      parameters: {
        kind: "messages" | "voice" | "recording" | "transcription" | "status";
      };
      responses: {
        "200": string;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-property-links": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: PropertyLinkBody;
      responses: {
        "200": PropertyLinkOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-property-links/unlink": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: UnlinkBody;
      responses: {
        "200": UnlinkOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-tickets": {
    get: {
      parameters: {
        limit?: number;
        before?: number | null;
        view?: "active" | "past" | null;
      };
      responses: {
        "200": MaintenancePageOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: TicketBody;
      responses: {
        "201": TicketStaffOut | TicketContractorOut | TicketPublicOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-tickets/unverified": {
    post: {
      requestBody: UnverifiedBody;
      responses: {
        "201": TicketStaffOut | TicketContractorOut | TicketPublicOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}": {
    get: {
      parameters: {
        ticket_id: string;
      };
      responses: {
        "200": TicketStaffOut | TicketContractorOut | TicketPublicOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
    patch: {
      parameters: {
        ticket_id: string;
      };
      requestBody: grok_bot__api__routes__maintenance__IntakeBody;
      responses: {
        "200": TicketStaffOut | TicketContractorOut | TicketPublicOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}/accommodations": {
    post: {
      parameters: {
        ticket_id: string;
      };
      requestBody: NoteBody;
      responses: {
        "200": StoredOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}/analyze": {
    post: {
      parameters: {
        ticket_id: string;
        "Idempotency-Key"?: string | null;
      };
      responses: {
        "200": TicketStaffOut | TicketContractorOut | TicketPublicOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}/appointments": {
    post: {
      parameters: {
        ticket_id: string;
      };
      requestBody: AppointmentBody;
      responses: {
        "201": MaintenanceAppointmentOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}/assignments": {
    post: {
      parameters: {
        ticket_id: string;
      };
      requestBody: AssignmentBody;
      responses: {
        "201": AssignmentOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}/deescalations": {
    post: {
      parameters: {
        ticket_id: string;
      };
      requestBody: ReasonBody;
      responses: {
        "200": DeescalateOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}/entry-secrets": {
    post: {
      parameters: {
        ticket_id: string;
      };
      requestBody: SecretBody;
      responses: {
        "200": StoredOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}/escalations": {
    post: {
      parameters: {
        ticket_id: string;
      };
      responses: {
        "200": EscalationOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}/issues": {
    get: {
      parameters: {
        ticket_id: string;
      };
      responses: {
        "200": IssuesOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}/issues/{issue_id}/updates": {
    post: {
      parameters: {
        ticket_id: string;
        issue_id: string;
        "Idempotency-Key": string;
      };
      requestBody: IssueUpdate;
      responses: {
        "200": IssuesOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}/media-uploads": {
    post: {
      parameters: {
        ticket_id: string;
        "Idempotency-Key"?: string | null;
      };
      requestBody: UploadBody;
      responses: {
        "201": UploadOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}/messages": {
    post: {
      parameters: {
        ticket_id: string;
        "Idempotency-Key"?: string | null;
      };
      requestBody: MessageBody;
      responses: {
        "200": TicketStaffOut | TicketContractorOut | TicketPublicOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}/transitions": {
    post: {
      parameters: {
        ticket_id: string;
        "Idempotency-Key"?: string | null;
      };
      requestBody: TransitionBody;
      responses: {
        "200": TransitionDuplicateOut | TransitionStatusOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}/workflow": {
    get: {
      parameters: {
        ticket_id: string;
      };
      responses: {
        "200": WorkflowDetailOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
    post: {
      parameters: {
        ticket_id: string;
        "Idempotency-Key": string;
      };
      requestBody: unknown;
      responses: {
        "200": WorkflowDetailOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-workers/{profile_id}": {
    patch: {
      parameters: {
        profile_id: string;
        "Idempotency-Key": string;
      };
      requestBody: WorkerUpdate;
      responses: {
        "200": WorkerOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-workflow": {
    get: {
      parameters: {
        view?: "active" | "past" | null;
        before?: string | null;
      };
      responses: {
        "200": WorkflowBoardOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-workspace": {
    get: {
      responses: {
        "200": WorkspaceOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/maintenance-workspace/apps": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: WorkspaceAppBody;
      responses: {
        "200": WorkspaceAppBody;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/me": {
    get: {
      responses: {
        "200": MeOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/media/{media_id}/bytes": {
    post: {
      parameters: {
        media_id: string;
        token: string;
      };
      responses: {
        "200": QuarantineOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/media/{media_id}/complete": {
    post: {
      parameters: {
        media_id: string;
      };
      responses: {
        "200": ScanOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/media/{media_id}/content": {
    get: {
      parameters: {
        media_id: string;
        token: string;
      };
      responses: {
        "200": string;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/media/{media_id}/download": {
    get: {
      parameters: {
        media_id: string;
      };
      responses: {
        "200": DownloadOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/opening-entries/reserve-cash": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: OpeningReserveBody;
      responses: {
        "201": OpeningOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/operations/queue": {
    get: {
      responses: {
        "200": OperationsQueueOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/owner-links": {
    post: {
      requestBody: OwnerLinkBody;
      responses: {
        "201": OwnerLinkOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/parties": {
    get: {
      responses: {
        "200": PartyPageOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: PartyBody;
      responses: {
        "201": PartyCreatedOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/payee-destinations": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: grok_bot__api__routes__distributions__DestinationBody;
      responses: {
        "201": DestinationOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/payment-items/{item_id}/settlement-evidence": {
    post: {
      parameters: {
        item_id: string;
        "Idempotency-Key"?: string | null;
      };
      requestBody: EvidenceBody;
      responses: {
        "200": EvidenceOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/payment-items/{item_id}/submission-evidence": {
    post: {
      parameters: {
        item_id: string;
        "Idempotency-Key"?: string | null;
      };
      requestBody: EvidenceBody;
      responses: {
        "200": EvidenceOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/period-closes": {
    post: {
      requestBody: PeriodCloseBody;
      responses: {
        "200": PeriodOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/properties": {
    get: {
      parameters: {
        limit?: number;
        cursor?: string | null;
      };
      responses: {
        "200": PropertyPageOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: PropertyWrite;
      responses: {
        "201": grok_bot__api__success__PropertyOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/properties/{property_id}": {
    get: {
      parameters: {
        property_id: string;
      };
      responses: {
        "200": grok_bot__api__success__PropertyOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
    patch: {
      parameters: {
        property_id: string;
        "If-Match"?: string | null;
      };
      requestBody: PropertyPatch;
      responses: {
        "200": grok_bot__api__success__PropertyOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/properties/{property_id}/agreements": {
    post: {
      parameters: {
        property_id: string;
        "Idempotency-Key"?: string | null;
      };
      requestBody: AgreementBody;
      responses: {
        "201": AgreementOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/properties/{property_id}/balances": {
    get: {
      parameters: {
        property_id: string;
      };
      responses: {
        "200": BalanceOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/properties/{property_id}/distribution-declarations": {
    post: {
      parameters: {
        property_id: string;
      };
      requestBody: PostingDateBody;
      responses: {
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/properties/{property_id}/ledger": {
    get: {
      parameters: {
        property_id: string;
        limit?: number;
        cursor?: string | null;
      };
      responses: {
        "200": LedgerOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/properties/{property_id}/ownership-periods": {
    post: {
      parameters: {
        property_id: string;
        "Idempotency-Key"?: string | null;
      };
      requestBody: OwnershipBody;
      responses: {
        "201": OwnershipOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/properties/{property_id}/reserve-top-ups": {
    post: {
      parameters: {
        property_id: string;
      };
      requestBody: PostingDateBody;
      responses: {
        "200": TopUpOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/properties/{property_id}/scheduling-resources": {
    post: {
      parameters: {
        property_id: string;
      };
      requestBody: ResourceBody;
      responses: {
        "201": ResourceOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/properties/{property_id}/screening-policies": {
    post: {
      parameters: {
        property_id: string;
      };
      requestBody: PolicyBody;
      responses: {
        "201": PolicyOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/properties/{property_id}/tour-schedules": {
    post: {
      parameters: {
        property_id: string;
      };
      requestBody: ScheduleBody;
      responses: {
        "201": ScheduleOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/properties/{property_id}/units": {
    get: {
      parameters: {
        property_id: string;
        limit?: number;
        cursor?: string | null;
      };
      responses: {
        "200": UnitPageOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
    post: {
      parameters: {
        property_id: string;
        "Idempotency-Key"?: string | null;
      };
      requestBody: UnitWrite;
      responses: {
        "201": UnitOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/properties/{property_id}/units/{unit_id}": {
    patch: {
      parameters: {
        property_id: string;
        unit_id: string;
        "If-Match"?: string | null;
      };
      requestBody: UnitPatch;
      responses: {
        "200": UnitOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/prospects": {
    post: {
      requestBody: ProspectStart;
      responses: {
        "201": ProspectOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/prospects/{prospect_id}/application-invitations": {
    post: {
      parameters: {
        prospect_id: string;
      };
      requestBody: InvitationBody;
      responses: {
        "201": InvitationOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/prospects/{prospect_id}/consumer-reports": {
    post: {
      parameters: {
        prospect_id: string;
      };
      responses: {
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/prospects/{prospect_id}/dispositions": {
    post: {
      parameters: {
        prospect_id: string;
      };
      requestBody: DispositionBody;
      responses: {
        "200": DispositionOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/prospects/{prospect_id}/evaluate": {
    post: {
      parameters: {
        prospect_id: string;
      };
      responses: {
        "200": EvaluationOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/prospects/{prospect_id}/intake": {
    patch: {
      parameters: {
        prospect_id: string;
      };
      requestBody: grok_bot__api__routes__prospects__IntakeBody;
      responses: {
        "200": IntakeUpdatedOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/prospects/{prospect_id}/messages": {
    post: {
      parameters: {
        prospect_id: string;
      };
      responses: {
        "200": IntakeMessageOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/receipts": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: ReceiptBody;
      responses: {
        "201": ReceiptCreatedOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/receipts/{receipt_id}": {
    get: {
      parameters: {
        receipt_id: string;
      };
      responses: {
        "200": ReceiptOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/receipts/{receipt_id}/allocations": {
    post: {
      parameters: {
        receipt_id: string;
        "Idempotency-Key"?: string | null;
      };
      requestBody: AllocationBody;
      responses: {
        "201": ReceiptCreatedOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/receipts/{receipt_id}/availability": {
    post: {
      parameters: {
        receipt_id: string;
      };
      requestBody: AmountDateBody;
      responses: {
        "200": ReceiptOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/receipts/{receipt_id}/bank-verification": {
    post: {
      parameters: {
        receipt_id: string;
      };
      requestBody: AmountDateBody;
      responses: {
        "200": ReceiptOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/receipts/{receipt_id}/returns": {
    post: {
      parameters: {
        receipt_id: string;
        "Idempotency-Key"?: string | null;
      };
      requestBody: ReasonAmountBody;
      responses: {
        "200": ReceiptReturnOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/reconciliations": {
    post: {
      requestBody: ReconciliationBody;
      responses: {
        "200": ReconciliationOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/reconciliations/{reconciliation_id}/close": {
    post: {
      parameters: {
        reconciliation_id: string;
      };
      responses: {
        "200": ReconciliationOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/rent-charges": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: RentChargeBody;
      responses: {
        "201": RentChargeOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/simulated-bank": {
    get: {
      responses: {
        "200": SimulatedBankOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/simulated-bank/accounts": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: AccountBody;
      responses: {
        "200": SimulatedBankOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/simulated-bank/accounts/{account_id}/outcome": {
    post: {
      parameters: {
        account_id: string;
        "Idempotency-Key"?: string | null;
      };
      requestBody: OutcomeBody;
      responses: {
        "200": SimulatedBankOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/simulated-bank/batches/{batch_id}/reconcile": {
    post: {
      parameters: {
        batch_id: string;
        "Idempotency-Key"?: string | null;
      };
      requestBody: ReconcileBody;
      responses: {
        "200": SimulatedBankOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/simulated-bank/demo-setup": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      responses: {
        "200": SimulatedBankOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/simulated-bank/receipts": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: grok_bot__api__routes__simulated_bank__RentBody;
      responses: {
        "200": SimulatedBankOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/simulated-bank/step-up": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      responses: {
        "200": StepUpOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/statements": {
    get: {
      responses: {
        "200": StatementPageOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
    post: {
      requestBody: StatementBody;
      responses: {
        "201": StatementIssuedOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/statements/{statement_id}": {
    get: {
      parameters: {
        statement_id: string;
      };
      responses: {
        "200": StatementOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/stripe": {
    get: {
      responses: {
        "200": StripeOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/stripe/properties": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: PropertyBody;
      responses: {
        "200": StripeOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/stripe/recipients": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: RecipientBody;
      responses: {
        "200": OnboardingOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/stripe/recipients/{party_id}/refresh": {
    post: {
      parameters: {
        party_id: string;
        "Idempotency-Key"?: string | null;
      };
      responses: {
        "200": StripeOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/stripe/rents": {
    post: {
      parameters: {
        "Idempotency-Key"?: string | null;
      };
      requestBody: grok_bot__api__routes__stripe__RentBody;
      responses: {
        "200": CheckoutOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/stripe/rents/{rent_id}/refresh": {
    post: {
      parameters: {
        rent_id: string;
        "Idempotency-Key"?: string | null;
      };
      requestBody: RefreshBody;
      responses: {
        "200": StripeOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/stripe/rents/{rent_id}/reimburse-fee": {
    post: {
      parameters: {
        rent_id: string;
        "Idempotency-Key"?: string | null;
      };
      requestBody: ReimbursementBody;
      responses: {
        "200": StripeOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/stripe/webhook": {
    post: {
      responses: {
        "202": StripeWebhookOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/tour-slots": {
    get: {
      parameters: {
        property_id: string;
      };
      responses: {
        "200": SlotPageOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/units/{unit_id}/leases": {
    get: {
      parameters: {
        unit_id: string;
      };
      responses: {
        "200": LeasePageOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/webhooks/{provider}": {
    post: {
      parameters: {
        provider: string;
      };
      responses: {
        "202": WebhookOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/work-orders/{work_order_id}/completion": {
    post: {
      parameters: {
        work_order_id: string;
      };
      requestBody: CompletionBody;
      responses: {
        "200": CompletionOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/work-orders/{work_order_id}/estimates": {
    post: {
      parameters: {
        work_order_id: string;
      };
      requestBody: EstimateBody;
      responses: {
        "200": EstimateOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
  "/v1/work-orders/{work_order_id}/invoices": {
    post: {
      parameters: {
        work_order_id: string;
      };
      requestBody: InvoiceBody;
      responses: {
        "201": InvoiceOut;
        "401": ErrorEnvelope;
        "403": ErrorEnvelope;
        "404": ErrorEnvelope;
        "409": ErrorEnvelope;
        "422": ErrorEnvelope;
      };
    };
  };
}
