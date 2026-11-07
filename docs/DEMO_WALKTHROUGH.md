# Local demo walkthrough

Use fictional data only. Double-click `Start-Demo.cmd`, then open <http://127.0.0.1:3000/>. Allow the first build to finish before presenting. Docker Desktop must be running. Starting again keeps the existing sample data; resetting is a separate destructive action.

The home screen has five role buttons. Each button opens the correct screen without a password. These buttons exist only in the isolated local sample. Use **Home** between steps to change roles. Budget 8–10 minutes for the walkthrough.

## 1. Record rent — Accounting (2 minutes)

Choose **1. Record rent**. Cedar Fixture House, Fixture A, and Fixture Payer are fictional. The starting ledger contains a recorded $1,800 check in custody, with $0 bank-available funds.

Enter `200000` cents ($2,000), select the occupied unit and payer, and choose **Record check**. Point out `RECORDED` and `Available cents: 0`. Explain that receiving a check is not evidence that funds are deposited, verified or available for owner distributions.

Optional CSV demonstration: save this as a UTF-8 `.csv` file and import it with **Import transactions**. This account ID belongs only to this sample:

```csv
bank_account_id,external_id,amount_cents,posted_on
bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbf,demo-bank-credit-001,200000,2026-11-07
```

Importing the file adds evidence for reconciliation; it does not verify the check or make funds available. Selecting/importing the same file again is safe. A new request with the same bank event ID and a different amount is rejected.

## 2. Prequalify a prospect — Prospect (2 minutes)

Return **Home**, then choose **2. Prequalify a prospect** and **Start intake**. The sample listing is fictional. Save household income `100000` cents with the income period blank. Show the clarification question and that missing information is not treated as zero.

Enter `monthly` as the period. Review the example intake details, then choose **Evaluate**. The illustrative sample income rule sends this example to **HUMAN_REVIEW**. This is not an automatic denial. Formal credit/background checks are not run before a tour.

## 3. Human exception and tour — Manager, then Prospect (2 minutes)

Return **Home** and choose **4. Review as manager**. Choose **Record exception** for the prospect review. Show the confirmation that no final housing decision was recorded.

Return **Home**, choose **2. Prequalify a prospect**, and **Start intake** again. Choose **Show tour slots**, then **Request hold** on an available time. The hold is local and time-limited, with `America/New_York` displayed. No external calendar invitation is sent. The page can be revisited; choose a different slot if a prior hold is still active.

## 4. Maintenance follow-up and emergency — Tenant (2 minutes)

Return **Home**, then choose **3. Report a repair**. Enter `The kitchen sink leaks` and choose **Report issue**. Show the ticket number and targeted follow-up questions. Continue with the location, timing and symptoms; the flow asks for safe photographic evidence and practical access information. Missing photos must not prevent a legitimate request.

In **Follow-up**, enter `I smell gas` and submit. Show the emergency safety message and escalation state. Explain that this local demo stores the escalation; it does not call 911, page an on-call person or contact a contractor. The maintenance questioning is template-based; no AI model is connected.

## 5. Owner view — Owner (1 minute)

Return **Home** and choose **5. View an owner statement**. The seeded November snapshot shows $0 unrestricted owner funds because the check has not become available. A statement is a versioned ledger snapshot, not confirmation of a bank balance. Newly entered receipts do not rewrite the issued snapshot.

## Presenter boundaries and rehearsal checklist

- Rehearse all five screens on the presenting computer before the meeting. Keep Docker running and use the same browser; no internet is needed after images have been built.
- Optional technical preflight: `python scripts/check_demo.py` verifies the local home page, all five role APIs, the owner statement, and disabled outbound switches. It prints no login tokens and does not create receipts, maintenance tickets, reviews, or appointments.
- Close or avoid entering real tenant, owner, bank, contact or maintenance information.
- Live banking, payment execution, SMS/email delivery, external calendars, formal consumer reports, production authentication, and production photo/video processing are not demonstrated.
- The distribution screen exists, but live submission and demo financial approval are intentionally disabled. Do not present it as an executed payment.
- If the page will not open, check Docker Desktop and run `Start-Demo.cmd` again. The launcher rebuilds the current bundled code and preserves the sample volume and `.env`.
- Only use `Reset-GrokDemo.ps1` when you intentionally want to erase the fictional rehearsal history. A normal restart does not reset data.
