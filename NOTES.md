# Build Notes (per Technical Addendum Section 6)

## 1. Email uniqueness — deviation from addendum schema
Addendum 3.1 specifies UNIQUE(org_id, email) on users. Implemented as globally
UNIQUE(email) instead: login is by email alone, and the same email in two orgs
would make login ambiguous without an org selector. Smallest reasonable change;
revisit if org-slug login is added. Related: RLS is NOT enabled on users and
organizations tables because signup/login must run before any org context
exists — those two tables are org-scoped in application code; RLS covers
payees, bank_templates, cheques, audit_log.

## 2. Addendum Section 3.3 test table has arithmetic errors — corrected
Rows 3–5 of the amount-to-words table confuse paise with rupees:
- 10000150 paise = Rs 1,00,001.50 → "One Lakh One Rupees and Fifty Paise Only"
  (table omitted the second "One")
- 100000000 paise = Rs 10,00,000 → "Ten Lakh Rupees Only" (table said One Crore;
  one crore rupees is 1,000,000,000 paise)
- 123456789 paise = Rs 12,34,567.89 → "Twelve Lakh ... Eighty Nine Paise Only"
  (table treated the paise value as rupees)
Tests encode the corrected values; added 1000000000 → "One Crore Rupees Only"
and a 12-crore case to keep crore coverage. The addendum document should be
updated to match.

## 3. Print rule when maker-checker is disabled
Addendum doesn't state which statuses may print when maker_checker_enabled is
false. Implemented: draft or approved may print when disabled; only approved
when enabled. Rejected/printed cheques never re-print via /print (use /reprint).

## 4. PDF output transport
Addendum 4 says print returns { pdf_url }. In this scaffold there is no object
storage yet, so print/reprint return { pdf_base64 } instead. Swap to an S3
presigned URL when the storage task lands.

## 5. Transaction rollback bug caught in billing (Task 5.8)
check_writable() updated status to 'lapsed' then the dependency raised
SUBSCRIPTION_LAPSED — psycopg rolled the transaction back on the exception,
so the lapse never persisted (requests still 402'd, but status stayed
'grace' in the DB). Fixed by committing the transition before raising.
Lesson: any state change that must survive an intentionally-raised error
needs an explicit commit before the raise.

## 6. ESC/P grid pitch assumptions (Task 5.7)
Dot matrix path assumes 10 CPI / 6 LPI draft pitch. Real calibration against
the client's actual printer model is still required before production —
this cannot be verified in software alone (task card 5.7 Done-when).
