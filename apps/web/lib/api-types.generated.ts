// Generated from the FastAPI OpenAPI document by apps/api/scripts/generate_api_types.py.
// Do not edit by hand.
//
// Component schemas: 67.
// Success responses with a schema: 6.
// Success responses without a schema, typed as unknown: 97.
// Those unknown responses are omitted from the route declaration, not filled in here.
export const API_VERSION = "0.1.0";

export interface AccessBody {
  evidence: string;
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

export interface ApproveBody {
  reason: string;
  snapshot_hash: string;
}

export interface AssignmentBody {
  contractor_profile_id: string;
  scope: string;
}

export interface BankAccountBody {
  display_name: string;
  masked_label: string;
}

export interface BankImportBody {
  csv_text?: string | null;
  format?: string | null;
  transactions?: BankTransactionBody[];
}

export interface BankTransactionBody {
  amount_cents: number;
  bank_account_id: string;
  external_id: string;
  posted_on: string;
}

export interface CompletionBody {
  notes?: string;
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

export interface DispositionBody {
  decision_note: string;
  reason: string;
}

export interface DraftBody {
  as_of: string;
  liability_ids?: string[] | null;
  management_party_id?: string | null;
  property_id: string;
}

export interface EstimateBody {
  estimate_cents: number;
}

export interface FeeSettlementBody {
  amount_cents: number;
  posting_date: string;
  property_id: string;
}

export interface HTTPValidationError {
  detail?: ValidationError[];
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

export interface InquiryBody {
  address_hint?: string | null;
  external_listing_id?: string | null;
  provider: string;
  provider_message_id: string;
}

export interface InvitationBody {
  external_reference?: string | null;
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

export interface InvoiceLineBody {
  description: string;
  line_total_cents: number;
  quantity: number;
  unit_price_cents: number;
}

export interface LeaseBody {
  agreed_rent_cents: number;
  end_date: string;
  start_date: string;
  unit_id: string;
}

export interface LeasePartyBody {
  user_id: string;
}

export interface ListingBody {
  asking_rent_cents: number;
  display_label: string;
  external_listing_id: string;
  external_source: string;
  property_id: string;
  unit_id?: string | null;
}

export interface LoginBody {
  password: string;
  subject: string;
}

export interface MessageBody {
  body: string;
  classifier_result?: string | null;
}

export interface NoteBody {
  note: string;
}

export interface OpeningReserveBody {
  amount_cents: number;
  bank_account_id: string;
  owner_party_id: string;
  posting_date: string;
  property_id: string;
  reason: string;
}

export interface OwnerLinkBody {
  party_id: string;
  user_id: string;
}

export interface OwnershipBody {
  end_date: string;
  shares: ShareBody[];
  start_date: string;
}

export interface PartyBody {
  display_name: string;
  kind: string;
}

export interface PeriodCloseBody {
  period_end: string;
  period_start: string;
  reason: string;
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

export interface ProspectStart {
  listing_id?: string | null;
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

export interface ReconciliationBody {
  bank_account_id: string;
  period_end: string;
  period_start: string;
  statement_closing_cents: number;
  statement_opening_cents: number;
  timing_item_cents?: number;
}

export interface RentChargeBody {
  amount_cents: number;
  description: string;
  due_on: string;
  lease_id: string;
}

export interface ResourceBody {
  display_name: string;
}

export interface RespondBody {
  accept: boolean;
}

export interface ReviewBody {
  reason?: string | null;
  resolution: string;
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

export interface SecretBody {
  code: string;
}

export interface ShareBody {
  owner_party_id: string;
  weight: number;
}

export interface StatementBody {
  owner_party_id: string;
  period_end: string;
  period_start: string;
  property_id: string;
  reason: string;
}

export interface SubmitBody {
  posting_date: string;
  scripts?: Record<string, string>;
}

export interface TicketBody {
  category?: string | null;
  contact?: string | null;
  contact_id?: string | null;
  description?: string;
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

export interface TransitionBody {
  action: string;
  duplicate_of_id?: string | null;
  reason?: string | null;
  status?: string | null;
}

export interface UnitPatch {
  label: string;
}

export interface UnitWrite {
  label: string;
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

export interface ValidationError {
  ctx?: Record<string, unknown>;
  input?: unknown;
  loc: (string | number)[];
  msg: string;
  type: string;
}

export interface grok_bot__api__routes__distributions__DestinationBody {
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

export interface apiPaths {
  "/v1/appointments/holds": {
    post: {
      requestBody: HoldBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/appointments/{appointment_id}/access-evidence": {
    post: {
      requestBody: AccessBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/appointments/{appointment_id}/cancel": {
    post: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/appointments/{appointment_id}/complete": {
    post: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/appointments/{appointment_id}/confirm": {
    post: {
      requestBody: grok_bot__api__routes__prospects__ConfirmBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/appointments/{appointment_id}/reschedule": {
    post: {
      requestBody: HoldBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/assignments/{assignment_id}/respond": {
    post: {
      requestBody: RespondBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/auth/local/login": {
    post: {
      requestBody: LoginBody;
      responses: {
        "200": Record<string, unknown>;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/auth/local/step-up": {
    post: {
      requestBody: LoginBody;
      responses: {
        "200": Record<string, unknown>;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/bank-accounts": {
    post: {
      requestBody: BankAccountBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/bank-imports": {
    post: {
      requestBody: BankImportBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/contractor-profiles": {
    post: {
      requestBody: ProfileBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/deposit-batches": {
    post: {
      requestBody: DepositBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/distribution-batches": {
    post: {
      requestBody: DraftBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/distribution-batches/{batch_id}": {
    get: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/distribution-batches/{batch_id}/approve": {
    post: {
      requestBody: ApproveBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/distribution-batches/{batch_id}/cancel": {
    post: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/distribution-batches/{batch_id}/export": {
    post: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/distribution-batches/{batch_id}/submit": {
    post: {
      requestBody: SubmitBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/distribution-batches/{batch_id}/validate": {
    post: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/distribution-declarations/{declaration_id}/simulated-settlement": {
    post: {
      requestBody: PostingDateBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/distribution-items/{item_id}/returns": {
    post: {
      requestBody: PostingBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/escalation-destinations": {
    post: {
      requestBody: grok_bot__api__routes__maintenance__DestinationBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/escalations/{escalation_id}/acknowledge": {
    post: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/fee-settlements/simulated": {
    post: {
      requestBody: FeeSettlementBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/health": {
    get: {
      responses: {
        "200": Record<string, unknown>;
      };
    };
  };
  "/v1/human-reviews": {
    get: {
      responses: {
        "200": unknown;
      };
    };
  };
  "/v1/human-reviews/{review_id}/resolve": {
    post: {
      requestBody: ReviewBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/inquiries": {
    post: {
      requestBody: InquiryBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/invoices": {
    post: {
      requestBody: InvoiceBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/invoices/{invoice_id}/approve": {
    post: {
      requestBody: PostingDateBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/invoices/{invoice_id}/simulated-settlement": {
    post: {
      requestBody: PostingDateBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/leases": {
    post: {
      requestBody: LeaseBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/leases/{lease_id}/parties": {
    post: {
      requestBody: LeasePartyBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/listings": {
    get: {
      responses: {
        "200": unknown;
      };
    };
    post: {
      requestBody: ListingBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/maintenance-appointments/{appointment_id}/confirm": {
    post: {
      requestBody: grok_bot__api__routes__maintenance__ConfirmBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/maintenance-escalations/advance": {
    post: {
      responses: {
        "200": unknown;
      };
    };
  };
  "/v1/maintenance-intake-links": {
    post: {
      responses: {
        "200": unknown;
      };
    };
  };
  "/v1/maintenance-tickets": {
    post: {
      requestBody: TicketBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/maintenance-tickets/unverified": {
    post: {
      requestBody: UnverifiedBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}": {
    get: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
    patch: {
      requestBody: grok_bot__api__routes__maintenance__IntakeBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}/accommodations": {
    post: {
      requestBody: NoteBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}/appointments": {
    post: {
      requestBody: AppointmentBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}/assignments": {
    post: {
      requestBody: AssignmentBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}/deescalations": {
    post: {
      requestBody: ReasonBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}/entry-secrets": {
    post: {
      requestBody: SecretBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}/escalations": {
    post: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}/media-uploads": {
    post: {
      requestBody: UploadBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}/messages": {
    post: {
      requestBody: MessageBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/maintenance-tickets/{ticket_id}/transitions": {
    post: {
      requestBody: TransitionBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/me": {
    get: {
      responses: {
        "200": Record<string, unknown>;
      };
    };
  };
  "/v1/media/{media_id}/bytes": {
    post: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/media/{media_id}/complete": {
    post: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/media/{media_id}/content": {
    get: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/media/{media_id}/download": {
    get: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/opening-entries/reserve-cash": {
    post: {
      requestBody: OpeningReserveBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/operations/queue": {
    get: {
      responses: {
        "200": unknown;
      };
    };
  };
  "/v1/owner-links": {
    post: {
      requestBody: OwnerLinkBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/parties": {
    get: {
      responses: {
        "200": unknown;
      };
    };
    post: {
      requestBody: PartyBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/payee-destinations": {
    post: {
      requestBody: grok_bot__api__routes__distributions__DestinationBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/period-closes": {
    post: {
      requestBody: PeriodCloseBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/properties": {
    get: {
      responses: {
        "200": Record<string, unknown>;
        "422": HTTPValidationError;
      };
    };
    post: {
      requestBody: PropertyWrite;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/properties/{property_id}": {
    get: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
    patch: {
      requestBody: PropertyPatch;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/properties/{property_id}/agreements": {
    post: {
      requestBody: AgreementBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/properties/{property_id}/balances": {
    get: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/properties/{property_id}/distribution-declarations": {
    post: {
      requestBody: PostingDateBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/properties/{property_id}/ownership-periods": {
    post: {
      requestBody: OwnershipBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/properties/{property_id}/reserve-top-ups": {
    post: {
      requestBody: PostingDateBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/properties/{property_id}/scheduling-resources": {
    post: {
      requestBody: ResourceBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/properties/{property_id}/screening-policies": {
    post: {
      requestBody: PolicyBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/properties/{property_id}/tour-schedules": {
    post: {
      requestBody: ScheduleBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/properties/{property_id}/units": {
    get: {
      responses: {
        "200": Record<string, unknown>;
        "422": HTTPValidationError;
      };
    };
    post: {
      requestBody: UnitWrite;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/properties/{property_id}/units/{unit_id}": {
    patch: {
      requestBody: UnitPatch;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/prospects": {
    post: {
      requestBody: ProspectStart;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/prospects/{prospect_id}/application-invitations": {
    post: {
      requestBody: InvitationBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/prospects/{prospect_id}/consumer-reports": {
    post: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/prospects/{prospect_id}/dispositions": {
    post: {
      requestBody: DispositionBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/prospects/{prospect_id}/evaluate": {
    post: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/prospects/{prospect_id}/intake": {
    patch: {
      requestBody: grok_bot__api__routes__prospects__IntakeBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/prospects/{prospect_id}/messages": {
    post: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/receipts": {
    post: {
      requestBody: ReceiptBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/receipts/{receipt_id}": {
    get: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/receipts/{receipt_id}/allocations": {
    post: {
      requestBody: AllocationBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/receipts/{receipt_id}/availability": {
    post: {
      requestBody: AmountDateBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/receipts/{receipt_id}/bank-verification": {
    post: {
      requestBody: AmountDateBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/reconciliations": {
    post: {
      requestBody: ReconciliationBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/reconciliations/{reconciliation_id}/close": {
    post: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/rent-charges": {
    post: {
      requestBody: RentChargeBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/statements": {
    get: {
      responses: {
        "200": unknown;
      };
    };
    post: {
      requestBody: StatementBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/statements/{statement_id}": {
    get: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/tour-slots": {
    get: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/units/{unit_id}/leases": {
    get: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/webhooks/{provider}": {
    post: {
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/work-orders/{work_order_id}/completion": {
    post: {
      requestBody: CompletionBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/work-orders/{work_order_id}/estimates": {
    post: {
      requestBody: EstimateBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
  "/v1/work-orders/{work_order_id}/invoices": {
    post: {
      requestBody: InvoiceBody;
      responses: {
        "200": unknown;
        "422": HTTPValidationError;
      };
    };
  };
}
