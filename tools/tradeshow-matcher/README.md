# Tradeshow vs CRM Matcher

A single web tool that replaces the four separate `tradeshow_*` notebook
pipelines (`..._full_name_email`, `..._full_name_company_name_phone`,
`..._full_name_company_name_email`, `..._full_name_company_name_phone_email`)
that used to live as near-duplicate Jupyter notebooks, each hard-coded for
one combination of columns.

Upload one tradeshow attendee list and the tool inspects its columns to see
which of **Company Name**, **Phone**, **Email** are present alongside the
required **Full Name**, then runs the matching logic for exactly that
combination automatically. There is no business-card (BC) input or matching
path anywhere in this tool — that source (`tradeshow_bc_matching.ipynb`,
plus the BC merge cells inside the other notebooks) has been dropped
entirely.

## What it does

1. Cleans and standardizes the tradeshow list and the CRM Contacts / CRM
   Leads exports (name splitting, phone/email normalization).
2. Fuzzy-matches the tradeshow list against CRM Contacts and CRM Leads with
   `recordlinkage` (Jaro-Winkler on name/company, exact-or-fuzzy on email,
   last-10-digit set intersection on phone), weighting each detected field
   equally.
3. Flags each attendee's **Status** as **Existing Contact**, **Existing
   Lead**, **New Contact**, or **New Lead** (see "Status, Match Confidence
   and Matched By" below), plus tags for Duplicate/Bank-CU/Existing
   Domain/personal_email, and buckets job titles (Owner/CEO, Loan Officer,
   Account Executive, ...).
4. Optionally looks up each matched attendee's MLO NMLS id in the NMLS
   database and adds their currently Authorized-to-Represent company or
   branch name (see "NMLS enrichment" below).
5. Produces a color-coded Excel export with clickable links back to the CRM
   record, plus an in-browser preview.

## Running it

```bash
cd tools/tradeshow-matcher
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:5050`.

## CRM data source

For each of Contacts and Leads you can either:

- **Upload a CSV export** — semicolon (`;`) separated, same shape as
  `crm_contacts.csv` / `crm_leads.csv` in the original pipeline, or
- **Pull live from the CRM database** — runs the same SQL against the
  Bitrix CRM database on `bi-02.prod.admortgage.com` that used to be a
  manual export step, so you always match against current data.
  - Both Contacts and Leads authenticate via Windows Integrated Auth
    (`Trusted_Connection`) — no username/password is asked for or sent
    anywhere. This only works when the tool runs on a domain-joined
    Windows machine (or a Linux host configured for Kerberos against that
    domain) as an account with access to the CRM database. (The original
    contacts script also carried a UID/PWD pair, but when
    `Trusted_Connection=yes` is present the ODBC driver ignores UID/PWD
    entirely — that pair was never actually authenticating anything.)
  - This path needs `pyodbc` plus the system-level "ODBC Driver 17 for SQL
    Server" installed, and network access to that server — see
    `matcher/db.py` for the exact queries. It has not been exercised
    against a live database in this repo's own dev/test environment, only
    against a mocked DataFrame shaped like the query output
    (`sample_data/smoke_test_db.py`) — verify it against a real connection
    before relying on it.

The tradeshow file can be `.csv` or `.xlsx` and just needs a name column —
common header spellings (Name, Full Name, Company/Organization,
Phone/Phone Number, Email/E-mail) are recognized automatically.

## Status, Tags, Match Confidence and Matched By

`Status` is exactly one of these 4 values, nothing else mixed in - clean
to filter or pivot on:

- **`Existing Contact`** — matched a CRM Contact. Wins even if the same
  attendee also matched a Lead - that overlap isn't dropped, it's flagged
  with an `Also a Lead` tag in the separate `Tags` column below
  (`Found in Contacts` / `Found in Leads` also show it independently).
- **`Existing Lead`** — matched a CRM Lead, no Contact match.
- **`New Contact`** — no personal match at all, but their Company Name
  already exists somewhere in CRM (blocked + fuzzy-matched against every
  unique company across Contacts + Leads combined, `matcher.matching.
  find_known_companies`) - a known account, just a new person there.
- **`New Lead`** — no personal match, and the company isn't in CRM either
  (or there was no Company Name to check at all).

`Tags` is a separate, semicolon-joined column carrying everything that
used to stack onto the old combined Status string: `Also a Lead`,
Job_Category-driven `Position`, `Bank/CU`, `Existing Domain`,
`personal_email`, `Duplicate` - e.g. `Position; Duplicate`, or blank if
none apply.

`Existing Account Company` / `Existing Lead Company` check whether the
attendee's company checks out against CRM Contacts / CRM Leads
respectively, and say something useful either way:

- Matched to a specific Contact/Lead: does the company they wrote on the
  tradeshow list agree (fuzzy, Jaro-Winkler `COMPANY_THRESHOLD` = 0.85,
  never an exact string check - real company names vary in spelling and
  suffixes, e.g. "Acme Lending" vs "Acme Lending LLC") with what's on
  file for *that specific* record?
- Not matched at all (`New Contact`/`New Lead`): falls back to the
  broader "does this company exist anywhere in that pool" check (same
  one that decides `New Contact` vs `New Lead`, run separately per pool
  - `NEW_CONTACT_COMPANY_THRESHOLD` = 0.92), so a `New Contact` row can
  still say `Yes` on `Existing Account Company` even with no person-level
  match, and a `New Lead` row correctly says `No` on both.

Blank only when there's no Company Name at all to check against either
side.

`Match Confidence` grades *what kind* of evidence backs that Status
conclusion, using the same rule for every category - not different logic
per category:

- **High** — an exact/near-exact identifier (Phone or Email) confirmed or
  ruled it out.
- **Medium** — only fuzzy text (Name and/or Company Name) did.
- **Low** — there was no usable data to compare at all (e.g. `New Lead`
  with a blank Company Name - "new" here just means "unverifiable," not
  "confirmed new").

`Matched By` lists which fields actually contributed (e.g. `Name, Phone`),
or `Company (fuzzy)` for a `New Contact` company-existence match, or blank
for `New Lead`.

The `New Contact`/`New Lead` company-existence check deliberately uses a
*stricter* similarity threshold (0.92) than the person-level company
corroboration used elsewhere (0.85, see below) - at the scale of a full
CRM export with potentially thousands of unique company names, a looser
threshold risks false positives between genuinely different
similarly-named companies, which would wrongly claim an existing
relationship. It also uses `recordlinkage`'s blocking (same technique as
the name-matching above) rather than comparing every unmatched attendee
against every company individually, since that full cross-product would
be far slower at real CRM data volumes.

**Known limitation:** treating a Phone match as High confidence assumes
the phone number is personal, not a shared office/switchboard line where
multiple different employees could all "match" on the same number - worth
keeping in mind if your CRM phone data tends to be a shared main line
rather than a direct/mobile number.

**Breaking change:** this replaced the old `Status` values (`Contact`,
`Contact - Unchecked`, `Lead - Existing`, the old email-domain-based
`New Contact` tag) and moved the old stacked tags out into their own
`Tags` column - any existing Excel filter, pivot table, or saved view
keyed on the old combined `Status` strings will need updating.

## NMLS enrichment

The "NMLS enrichment" checkbox looks up each matched attendee in a
*different* database - the NMLS database on `p-nmls-db01.admortgage.com` -
and adds `NMLS FullName` (that individual's own First/Last Name from
`dbo.Individual`, so you can visually compare it against the attendee's
own Full Name), `NMLS RegulationType` (State-Licensed / Federally
Registered / Dual / None), `NMLS LicensingStatus` (Active/Inactive), `NMLS
LocationNMLSID`, and `NMLS LocationName` (the company or branch that
person is currently authorized to represent, from `dbo.Company.Name` or
`dbo.Branch.Name`), plus `NMLS Match Method` saying how each row was
looked up:

1. **`CRM`** - if the attendee matched a CRM Contact/Lead that has an MLO
   NMLS id on file, that id is used directly. This is the priority path -
   it's an exact, unambiguous id, so it always wins when available.
2. **`Name+Company`** - only for attendees with *no* CRM match at all.
   Falls back to fuzzy-matching their Full Name against `dbo.Individual`
   (blocked on exact `LastName`, Jaro-Winkler on First/Last), then always
   also compares Company Name against each name-candidate's resolved
   company/branch name - a name match alone is never enough to accept a
   result, even when it's the only name candidate. If there's no Company
   Name to compare (blank), a single unambiguous name candidate is still
   accepted; multiple name candidates with no Company Name, or none of the
   candidates' companies matching well enough, leaves the attendee
   unmatched rather than guessing.
3. Blank `NMLS Match Method` - neither path found anything (no CRM match
   and no confident NMLS name match).

Like the CRM pull, this authenticates via Windows Integrated Auth, no
credentials needed. Unlike a typical bulk NMLS export (which processes the
*entire* `dbo.Individual` table - hundreds of thousands of rows, meant to
run offline), this is scoped: it only queries the specific ids/names that
are actually relevant to this run, via SQL `IN (...)` filters, batched at
500 at a time to stay under SQL Server's parameter limit. See
`matcher/nmls.py` for the full "Authorized to Represent" derivation logic
(ported from a reporting script, one simplification: it keeps only the
single most recent authorized location per person, not every one they've
ever held). Like the CRM query, this has only been exercised against a
mocked schema (`sample_data/smoke_test_nmls.py`,
`sample_data/smoke_test_nmls_fallback.py`), not a live database - verify
the `Name` column really exists on both `dbo.Company` and `dbo.Branch` in
your instance before relying on it.

## Also used as a backend by the browser extension

`tools/tradeshow-matcher-extension/` is a Chrome/Edge extension version of
this same tool. It runs entirely client-side, but a browser can't open a
direct SQL Server connection, so its "Pull live via local backend" and
"NMLS enrichment" options call this Flask app's `/api/contacts`,
`/api/leads`, and `/api/nmls` JSON endpoints instead, which do the real
`pyodbc` calls and return standardized rows. Keep `python app.py` running
here if you want to use those options from the extension. CORS on those
routes is restricted to `chrome-extension://` origins only (see `app.py`)
— never widen that to `*`.

## Sample data

`sample_data/make_samples.py` generates small synthetic fixtures covering
all four field combinations; `sample_data/smoke_test.py` runs the pipeline
against them without the web server, for quick regression checks after
changing matching logic.
