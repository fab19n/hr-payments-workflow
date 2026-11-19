# Inventory: MyInvois e-Invoices and printed documents (stage 1, b7d7fa0..HEAD)

I only read files. Nothing was run and nothing was changed.

**Commits in this area:**
- `c026739`: MyInvois copies read, kept and linked to the books.
- `3111c43`: each e-Invoice's MyInvois page from its Long ID, and month-first date fix.
- `f34dee5` and `d3a95cc`: printed invoices and self-billed e-Invoices as PDFs, in SQL's fonts and positions.
- `3030d67`: debit and credit note PDFs, the foreign-currency self-billed line, print settings in the Setup file.
- `2cdf9b6`: polish.

**Files:**
- Server: `hrp\myinvois.py`, `hrp\invoicepdf.py`, `hrp\sqlfetch.py` (lines 258-276), `hrp\app.py` (lines 1343-1503, 1677-1837, 1955-2010, 3118-3228), `hrp\masters.py`, `hrp\setupfile.py`, `hrp\partybook.py` (lines 381-388).
- UI: `static\app.js`.
- Canvas: `design/canvas`.

---

## A. Inventory: exact strings, code lines and rules

### A1. SQL page: fetch instructions for MyInvois (app.js 1597-1600)

The **Fetch exported listings (one click)** note now ends with this sentence:

> It also reads a copy of SQL's **MyInvois Transaction** screen: click its grid, press **Ctrl+A** then **Ctrl+C**, paste it into a new Excel workbook with its headings and save it in the same folder under any name.

The h1 note now reads "Fetch (or paste) each SQL listing for the month: …" (outside this area).

### A2. Pasting a MyInvois grid is refused (app.py 1343, 1383-1384; app.js 4519-4520)

- If the pasted text is detected as a MyInvois grid, the server returns 400.
- The page shows an error toast: "This is a copy of SQL's MyInvois Transaction screen: paste it into Excel, save it in the exports folder and use Fetch from SQL exports."

### A3. How a copy is recognised and read (myinvois.py)

**Recognising a copy:**
- By its headings (lines 23-30, 74-84). The recognised headings are: Doc No./Document No, UUID, Type, Version, Currency, Supplier Name, Supplier TIN, Buyer Name, Buyer TIN, Receiver TIN, Submission ID, Submission Channel, Validated Date, Received Date, Issued Date, Reject/Rejected Date, Status, Total Amount, Total Excluding Tax, Total Net Amount, Long ID.
- A copy needs UUID, Status, Supplier TIN and Buyer TIN headings.
- Without headings, it is recognised by its shape (87-104): a 26-character UUID in column 2 and a known status on more than half the rows.
  - The 20-column layout is the newer grid.
  - The 15-column layout is the older grid (no Receiver TIN, Submission ID, Validated Date, Total Excluding Tax or Total Net).

**Statuses (50-55):**

| LHDN status | Word written on the SQL document |
|---|---|
| Valid | Validated |
| Cancelled | Cancelled |
| Invalid | Invalid |
| Submitted | Submitted, not validated |
| Rejected | Rejected |

**Month-first date fix (166-179, 224-227, 255-256):**
- Rule: if the date columns hold both real dates and day-first text whose day is over 12 (for example "13/11/2026 2:19:44 PM"), Excel read the copy month first.
- Every real date in it with a day of 12 or less has its day and month swapped back.
- No UI string. The effect is that Validated, Issued and Received dates show correctly.

**Long ID (31-33, 182-186, 248-250):**
- The page link is `https://myinvois.hasil.gov.my/{uuid}/share/{long_id}`.
- A Long ID must be at least 20 letters and digits.

**Refusal sentences** (line 219-220, 273, 280). The whole copy is refused, so nothing is taken from it. These appear in the fetch review as **Couldn't be read**:
- "This MyInvois copy has no {Doc No. | UUID | Type | Status | Total Amount, joined with ' or '} column, so nothing was taken from it. Copy the whole MyInvois Transaction grid again, with its headings."
- "Row {n} of this MyInvois copy has {problem}, so nothing was taken from it. Copy the whole MyInvois Transaction grid again, with its headings." The ending is just "…grid again." for a copy without headings. The possible problems are:
  - "a UUID that isn't one LHDN gives ({uuid|blank})"
  - "no Doc No."
  - "no Status"
  - "a status this app doesn't know ({s})"
  - "a Long ID that isn't one LHDN gives ({id})"
  - "a date it can't read under {Validated|Received|Issued|Rejected} Date ({text})"
  - "an amount it can't read ({text})"
  - "no Total Amount"
  - "the UUID {uuid} twice, with different details"
- "This MyInvois copy has no e-Invoices in it, so there is nothing to take. {again}"

### A4. Whose copy it is, and the fetch review (sqlfetch.py 258-276; app.js 2112-2133)

**Owner rule:**
- The company is the one whose Setup TIN (spaces and dashes removed, at least 6 characters) appears as supplier or buyer TIN on the most e-Invoices.
- All companies are checked, including AI.

**Statuses when a copy is not used:**
- Another company: "This MyInvois copy is for AI (Agrinexus International), not AISB."
- Company not in Setup: "This MyInvois copy has no e-Invoice whose supplier or buyer TIN is AISB's[ (its TIN isn't in Setup yet)], so it was left out. Enter the company's TIN in Setup › Companies, then fetch again." There is no **Take it for** button for MyInvois copies.
- Couldn't be read: "The records need update 33 to keep MyInvois copies. Restart the app, then fetch again."

**Review summary line (2123):** after the listings sentence, `<b>MyInvois e-Invoices: {sum of rows}</b>.`

**Per-copy row (2128-2129):**
- Left: `{name} · MyInvois e-Invoices, {3 Sep} to {13 Nov}`. The period is the first to last issued day in the copy.
- Right: `{n} e-Invoice(s): {new} new, {changed} status or details changed, {unchanged} unchanged[, {older} left as a later copy says] ({issued} issued, {self_billed} self-billed, {received} received)`.

**Compare and keep rules (363-412):**
- e-Invoices are kept once per company, by UUID.
- A later-saved copy updates status, dates and details.
- A copy saved earlier than the one already read changes nothing; it is counted as "left as a later copy says".
- An e-Invoice missing from a later copy is kept.
- A copy without a Long ID column never clears a Long ID already kept.

**Direction (302-316):**

| Direction | Rule |
|---|---|
| issued | The company is the supplier and the type is not self-billed |
| self_billed | Type contains "self-billed" and the company is the buyer |
| received | The company is the buyer of an ordinary e-Invoice |
| other | Anything else |

### A5. Preview and apply (app.js 1415-1417, 2164-2168, 4271-4273; app.py 1398-1407, 1677-1690, 1810-1837)

**Preview card when the fetch read only MyInvois copies and/or GL reports:**
- Heading: "MyInvois e-Invoices" (or "SQL's general-ledger reports" when GL reports were read).
- Right side: "No new listing entries".
- Then the review, then the **Keep …** and **Cancel** buttons.

**Apply button label (`applyLabel`):**
- No listing entries: "Keep MyInvois e-Invoices", or "Keep account lines and keep MyInvois e-Invoices".
- With entries: "Import {n} entries ({m} linked)[ and keep account lines][ and keep MyInvois e-Invoices]".

**Toast after apply:**
- Reports or MyInvois only: "[Kept the account lines of …]. Kept {N} MyInvois e-Invoice(s) ({new} new, {changed} changed); {k} SQL document(s) filled in."
- With entries, the same `einv` clause is appended after "Imported {n} entries; {m} linked to payments…".

**Import row:**
- Its file name is "SQL reports fetched YYYYMMDD-HHMM: {file names}", with 0 entries.
- In **Imported files** it reads `{filename} · 0 entries, 0 linked`.
- Each copy is stored as a "_SQL exports" document.

### A6. Linking e-Invoices to SQL's books (myinvois.py 490-731)

These rules change what the pills show.

**Issued and self-billed e-Invoices:**
- The SQL document with the same number (capitals and spaces ignored) takes the UUID, the status word, and the page link (when the Long ID is known).
- It does not take them when SQL's own paste is newer than the copy.
- Ignored documents and documents deleted in SQL are skipped.
- If several SQL documents share the number, only the one with the same amount, dated no later than the issue date, is filled. If that still leaves more than one, none is filled.
- A Cancelled, Invalid or Rejected attempt never replaces a different UUID already on the document.

**Received e-Invoices** are tried in this order:
1. The supplier's document number (its own number, or named in the description), checked against the party TIN, amount or name. Recorded as `doc_no`.
2. TIN plus amount, near the date, for one document only. Recorded as `tin_amount`.
3. Amount only. Recorded as `amount`.
4. One non-bank debit line of that amount, for example a claim voucher line. Recorded as `line`.
5. Two or three e-Invoices of one supplier, within 45 days, summing to one voucher. Recorded as `sum`.

**Link notes:**
- They go only to the activity log, prefixed "MyInvois for AISB: ".
- The toast counts those containing "filled in from MyInvois".
- The note sentences are:
  - "{doc}: {issued|self-billed} e-Invoice {UUID first 8}… ({status}) could be more than one SQL document with this number, so none was filled in. Check in SQL which one it is."
  - "{doc}: {kind} e-Invoice {uuid8}… ({status}) has no SQL document with this number yet; it is filled in once the document is imported."
  - "{doc}: kept its e-Invoice {uuid8}… ({status|UUID recorded}); MyInvois holds only {uuid8}… ({status}) for this number."
  - "{doc}: kept its e-Invoice status from SQL ({…}), pasted after this MyInvois copy was saved."
  - "{doc}: {kind} e-Invoice {uuid8}… filled in from MyInvois, {Validated}[ (was {old})]."
- Read log line: "Read MyInvois copy '{name}' for AISB: {rows} e-Invoices, {new} new, {changed} changed, {unchanged} unchanged[, {older} left as a later copy says]".

### A7. SQL page, **Journals and invoices** card (app.js 1617-1627)

- The heading is now "Journals and invoices". The canvas still says "Journals and customer invoices".
- The card now also holds supplier invoices (PI), because the invoice kind includes PI/SD/SC.
- Columns: Doc No | Date | Description | Amount | e-Invoice | Checklist item.
- The e-Invoice cell holds `einvPill` followed by `invoiceBtn`.
- Empty state: "Fetch SQL's Journal Voucher and Customer Invoice listings on this page to see them here."

**Print bar** (`invoicePrintBar`, 2077-2088), shown above the table and only when some month has printable documents:
- `Print [month select]`. Months come from customer IV/DN/CN plus self-billed, newest first. The default is the newest month, not the month being worked.
- Zip links appear only for a kind present in the chosen month:
  - "All invoices, debit and credit notes of October 2026 (zip)"
  - "All self-billed invoices of October 2026 (zip)"
- When settings are missing: "**Print settings:** invoices print without what is missing." then a list of the sentences (A12), then the button **Open Setup › Companies**. It goes to the Setup Companies list, not the AISB drawer (app.js 4344).
- Then the "**Fonts:**" list and the "**Too long to print in full:**" list, when present.

**PDF button** (`invoiceBtn`, 2071-2075):
- It is a ghost small link opening `/api/invoices/{id}.pdf` in a new tab.
- Labels:

| Document | Label |
|---|---|
| IV, or no type | Invoice PDF |
| DN | Debit note PDF |
| CN | Credit note PDF |
| Self-billed | Invoice PDF (not "Self-billed invoice PDF") |

- Tooltip: "The {invoice|debit note|credit note|self-billed invoice}, laid out as SQL Account prints it".
- Shown only when the server's `print_kind` is set (app.py 1972-1974):
  - `customer` for IV/DN/CN, or an untyped invoice with direction in.
  - `self_billed` for a payment voucher (not OR/RV/CS, not money in) that has a self-billed e-Invoice read from MyInvois.
- There is no PDF button in the unlinked, linked or ignored lists, or in the payment drawer.

### A8. SQL page, **e-Invoices** card (app.js 1628-1634)

- Note: "Every SQL document with an e-Invoice, and whether LHDN has validated it. Where a copy of SQL's MyInvois Transaction screen was read, what MyInvois says is shown beside it."
- Columns: Doc No | Date | Description (payee, or else description) | Amount | Status | **MyInvois** (new) | (actions).
- The list holds up to 200 documents of any kind: PV, IV, OR and so on.
- **MyInvois cell:**
  - The full UUID in mono, with a note under it: "{type} · {status}[ · validated {raw 'YYYY-MM-DD HH:MM:SS'}]".
  - "—" when MyInvois has nothing.
- Actions: **Unlink** (when linked to a payment) and the PDF button.
- Empty state: "None imported yet."

**Status pill** (`einvPill`, 2094-2099):
- "—" when the document has no e-Invoice.
- Green (ok) when the status starts with "Validated" and no credit note took it back.
- Otherwise amber (warn) with the status text: "Submitted, not validated", "Cancelled", "Invalid", "Rejected", "Has UUID" (no status), or "Cancelled by {CN no}".
- The link "MyInvois ↗" appears when `einvoice_link` is set. That link is now the real share URL once a copy with Long ID was read.

The unlinked-list pill (1535), "e-Invoice {first 8}…", is unchanged.

### A9. SQL page, **From MyInvois** box (app.js 2038-2065; myinvois.view 734-761)

The box is hidden entirely when the records are below update 33.

**Empty state:**
> **From MyInvois**: "No copy of MyInvois read yet. In SQL, open the MyInvois Transaction screen, click the grid, press **Ctrl+A** then **Ctrl+C**, paste it into a new Excel workbook with its headings and save it in the exports folder under any name, then use Fetch from SQL exports. The company's TIN must be in Setup › Companies."

**Source note:** "Read from **{name}** (saved {YYYY-MM-DD HH:MM:SS}), on {YYYY-MM-DD HH:MM:SS}." It shows the latest source, from up to 5 kept. The times are raw ISO with the "T" replaced by a space.

**Filter:** a segmented group labelled "Which e-Invoices" with **All**, **Issued (n)**, **Self-billed (n)**, **Received (n)**. "Other" rows appear only under All.

**Table** columns:

| Column | Content |
|---|---|
| Doc No | Document number |
| UUID | Linked with ↗ to the share URL when a Long ID is known, titled "Open it on MyInvois" |
| Type | e-Invoice type |
| Status | Green pill for Valid, amber otherwise |
| Validated | Raw ISO |
| Supplier or buyer | Buyer for issued, supplier for the others |
| Total | Currency prefix when not MYR, for example "USD 100.00" |
| In SQL | See below |

**In SQL cell:**
- The linked document number, plus a grey pill when it was matched by amount: "By amount", "By a line's amount" or "Paid together". The pill's tooltip is "A likely match, by amount only: check it". `doc_no` and `tin_amount` matches get no pill.
- "Not found" when there is no link, or "—" for direction other.
- An **Invoice PDF** button on self-billed rows linked to an SQL document.

Empty filtered table: "None."

**Received but not found:**
- Heading: "e-Invoices received but not found in SQL's books ({n})".
- Note: "Valid e-Invoices issued to the company from {October 2025 = first month tracked} that no supplier invoice or payment voucher in SQL has, by the supplier's document number, its TIN and amount, or its amount alone (a whole voucher, or one line of a claim, dated near it). Check each one: it may still have to be entered in SQL."
- Table: Doc No | Supplier | Supplier TIN | Issued (YYYY-MM-DD) | Total.
- Empty: "None: every valid e-Invoice received is in SQL's books."
- Rule: only Valid, received, unlinked e-Invoices issued on or after the first month tracked are listed.

Nothing in the box can be edited.

### A10. Printed documents: routes, outputs and audit (app.py 3118-3175)

**Routes:**
- `GET /api/invoices/{id}.pdf`. Inline by default; `?download=1` saves it, but the UI never uses that.
  - File name: "{doc_no} {party name}.pdf" (made filename-safe, at most 120 characters).
  - PDF metadata: title "{Title} {doc_no}", author the company name, creator "HR Payments".
- `GET /api/invoices/month.zip?kind=customer|self_billed`. Named "AISB Invoices 2026-10.zip" or "AISB Self-billed invoices 2026-10.zip".
  - Each PDF is named by document number; a duplicate name gets " (2)".
  - "Not printed.txt": "These documents were not printed:" then "{doc}: {reason}" lines.
  - "Text cut short.txt": "These invoices were printed with a line too long for its place, its end cut off:" then lines.
- **Refusal page:** the tab opened shows a small HTML page titled "Not printed", holding only the sentence.
- `GET /api/invoices/{id}/check` returns {kind, file, notes, missing, fonts}. **No UI uses it.** The per-document notes (A13) are therefore never shown on screen.

**Audit:** both PDF and zip are `audited_read`. A successful open adds an "Opened file" event of kind "invoice" or "invoices", with the path and file name.

Zip refusal when the month has nothing: "AISB has no {customer invoices, debit notes or credit notes | payment vouchers with a self-billed e-Invoice} in October 2026 in the SQL documents fetched."

### A11. The PDF itself: SQL's layout, US Letter (invoicepdf.py 763-1137)

The layout is fixed to SQL's own and must not be restyled. Positions are in millimetres from the top left. Fonts are SQL's Windows fonts.

**Header (every page):**
- Logo at top left, fitted in a 26.3 × 25.4 mm box. Omitted when there is none.
- Company name centred, Times New Roman Bold 15.86 pt.
- Registration line, Times 7.99 pt: "(201901023456 (1331234-K))  (TIN No: C 2345678901)".
- Address on one line, its lines joined with commas.
- Contact line: "Phone: …   |   email: …   |   www…".
- Title centred, Tahoma Bold 12 pt: "Invoice", "Debit Note", "Credit Note" or "Self-billed Invoice".

**Left block:**
- Label "To  :" for customer documents, or "Supplier  :" for self-billed.
- Party name, then up to 4 address lines.
- Self-billed only: "TIN : {supplier TIN}".
- "Attn : {attention}" when set.
- Self-billed only: "Buyer : AISB Sdn Bhd (TIN No: C 2345678901)".
- The table moves down if this block runs long.

**Right block:** "Doc No.  :" (bold), "Date   :" (dd/mm/yyyy), "Account  :" (customer code), "Terms  :" (the party's Terms).
- A credit note's "Ref  :" exists in code, but no listing carries it today, so it is never printed.

**Table:**
- Headings "G/L CODE", "DESCRIPTION", and "Amount(MYR)" or "Amount(USD)".
- Rows hold the account code, the description wrapped, and the amount in Trebuchet.
- A credit note prints its lines and total as positive figures.

**Footer (last page only):**
- Amount in words, up to 3 lines, shrinking if needed. Examples: "Malaysian Ringgit : ONE THOUSAND EIGHT HUNDRED ONLY"; "US Dollar : ONE HUNDRED ONLY"; "… AND CENTS TWENTY FIVE ONLY".
- "Total :" in bold, then the total.
- **Foreign-currency self-billed only:** the line under the total, 7 pt: "Paid as MYR 470.00 by PV2610-018".
- **Customer invoice and debit note only** (never a credit note or a self-billed invoice):
  - "All payments to be made to :"
  - The company name.
  - "Bank : …", "Bank Address : …", "Account No : …", "Bank Transfer Code : …". Labels are grey, values Segoe UI Bold 6.91 pt.
  - The whole block is omitted when no bank account is chosen.
- Signature image, a rule, then "For AISB Sdn Bhd" (or the **Under the signature** text).

**e-Invoice block at bottom right** (`_einvoice` 403-425, `_footer` 1045-1065):

| State | What prints |
|---|---|
| valid | A 20 mm QR code (clickable, linking to the share URL), then "e-Invoice UUID: {uuid}" and "Validated on 01/10/2026 11:19:44" in 5.5 pt |
| no_link (Valid but no Long ID) | No QR; "e-Invoice UUID: …", "Validated on …", "QR code not printed: MyInvois's Long ID for it wasn't read." |
| cancelled | In red bold, "e-Invoice cancelled"; then "e-Invoice UUID: …", "Cancelled on MyInvois: this e-Invoice is no longer valid." |
| pending (Submitted, Invalid or Rejected) | "e-Invoice UUID: …", "Not validated on MyInvois ({status}): no QR code." |
| none (no MyInvois row) | Nothing; this triggers a note |

**Several pages:**
- Every page repeats the header.
- Above the foot rule, 8 pt: "Continued on page 2 of 3".
- Bottom right, 7 pt: "Page 1 of 3".
- A row too long for a page is split.

**Lines that don't fit:** a line too long for its place shrinks, down to half SQL's size. Past that its end is cut off and the cut is noted (A12). SQL's own size is never exceeded.

**Fonts and the look-alike fallback:**

| SQL font | Prints |
|---|---|
| Times New Roman | Registration, address and phone lines |
| Times New Roman Bold | Company name |
| Tahoma | Most words |
| Tahoma Bold | Title, document number, Total |
| Trebuchet MS | Amounts |
| Segoe UI | Bank details' labels |
| Segoe UI Bold | Bank details |

- Fonts are found in HRP_FONT_DIR, then Windows Fonts.
- If one is missing: a free look-alike (Liberation or DejaVu), else the PDF maker's Times or Helvetica.
- A look-alike is scaled so it is never larger than SQL's font.

### A12. Print settings notes (invoicepdf.py 365-400, 697-721, 807-831, 1140-1164)

These notes appear on the SQL page print bar and in Setup › Companies.

**Missing settings** (each sentence ends with "in Setup › Companies › AISB" or names Bank accounts):
- "No address: add it as Address in Setup › Companies › AISB."
- "No phone, email or website: add them in Setup › Companies › AISB."
- "No registration no.: add it in Setup › Companies › AISB."
- "No tax ID (TIN): add it in Setup › Companies › AISB."
- "No logo: upload it under Printed invoices in Setup › Companies › AISB." The same sentence exists for signature.
- "The logo file changed or is missing since it was uploaded, so it isn't printed: upload it again under Printed invoices in Setup › Companies › AISB."
- "No bank account chosen for All payments to be made to: choose one as Bank account on invoices in Setup › Companies › AISB."
- "The bank account chosen for invoices is gone: choose another as Bank account on invoices in Setup › Companies › AISB."
- "The bank account chosen for invoices (Maybank current) is stopped."
- "The bank account Maybank current has no bank address or bank transfer (SWIFT) code: add it in Setup › Bank accounts." The gaps listed can be bank, account number, bank address, bank transfer (SWIFT) code.
- Below update 35: "The records need updating before invoices can be printed: restart the app."

**Fonts:**
- "SQL's font Tahoma (most of the invoice's words) isn't on this computer (or its file is damaged), so invoices print it in {DejaVu Sans, a free look-alike on this computer | Helvetica, the PDF maker's own look-alike}, never larger than SQL's size."
- "To print exactly as SQL does, install tahoma.ttf, … on this computer from a Windows computer's Fonts folder, or put licensed copies of them in a folder outside the records folder and name that folder in HRP_FONT_DIR."
- "The fonts folder named in HRP_FONT_DIR (or the font_dir setting) is inside the records folder, so it isn't used: font files are never kept in the records folder. Name a folder outside it."
- "A font file ({path}) failed while an invoice was being printed, so that invoice was printed in the PDF maker's own look-alikes. Install a good copy of the font, then print it again."
- On a Windows PC with all fonts present, no note shows. On a hosted Linux server (planned) all 7 notes would show.

**Too long** (Setup fields only):
- '{The company's address in the header} is too long for its place on the invoice, even at half SQL's size, so its end is cut off (it prints up to "...{last 30 chars}"): shorten it in Setup › Companies › AISB.'
- The phrases for each field:
  - The company's name in the header
  - The registration no. and TIN line in the header
  - The company's address in the header
  - The phone, email and website line in the header
  - The company's name in the bank details
  - The bank's name
  - The bank's address
  - The bank account number
  - The bank transfer (SWIFT) code
  - The words under the signature
- Per-document cuts (party, description and so on) go only into the check route and "Text cut short.txt".

### A13. Refusals and per-document notes (invoicepdf.py 249-526)

**Refusals.** These show on the "Not printed" page or in "Not printed.txt":
- "{doc} isn't a customer invoice, debit note or credit note, or a payment voucher with a self-billed e-Invoice, so it has no invoice to print."
- "{doc} was confirmed as deleted in SQL, so it isn't printed."
- "SQL's account lines of {doc} haven't been fetched. Fetch SQL's GL Journal of Transaction covering 01/10/2026 to print this {invoice|debit note|credit note|self-billed invoice}."
- "{doc}: SQL's account lines under this number are dated {d}, not this invoice's date ({d}), so it isn't printed with another document's lines. If its date was changed in SQL, fetch the invoice listing again; if the number was used again, check it in SQL."
- "{doc}: SQL's account lines don't show which line is the customer's (its listing has no customer code). Fetch the listing again, then print it."
- "{doc}: SQL's account lines put {x} on the customer's account {code}, but SQL's listing says {y}. Fetch the listing and the GL Journal of Transaction covering {date} again so they agree, then print it."
- "{doc}: SQL's account lines don't balance (the lines come to {x}, the customer's account to {y}). Fetch SQL's GL Journal…"
- "{doc}: the e-Invoice is in USD (USD 100.00), but the voucher's lines other than the bank come to MYR 0.00, so they can't be printed at the voucher's rate. Check the voucher in SQL, fetch its GL Journal of Transaction again, then print it."
- "This SQL document is no longer in the records." (404)

**Notes.** These are only available from the unused check route:
- "SQL shows e-Invoice {uuid} on {doc}, but no copy of SQL's MyInvois Transaction screen read here has it, so it prints without its QR code. Fetch a copy of MyInvois to add it."
- "e-Invoice {uuid} has no Long ID in the MyInvois copies read, so its QR code can't be printed. Copy SQL's MyInvois Transaction screen with its Long ID column and fetch it, then print again."
- "e-Invoice {uuid} was cancelled on MyInvois: the invoice prints with no QR code and says so."
- "e-Invoice {uuid} is {status} on MyInvois, not validated, so it prints without a QR code."
- "The e-Invoice is in USD: its lines print SQL's ringgit lines at the voucher's rate (USD 100.00 for MYR 470.00)." This appears only with more than one line.
- "The e-Invoice's total on MyInvois (MYR x) isn't what the voucher's lines come to (MYR y): it prints MyInvois's total. Check the voucher in SQL."

**Foreign-currency rule:** each line is converted at the voucher's single rate. Rounding sen go to the lines that lost the most, so the lines sum exactly to MyInvois's total. A withholding-tax credit prints as a negative line.

### A14. Setup › Companies (masters.py 70-86; app.js 2863-2938, 4344-4346)

**New fields, in code order:**
- After "Registration no.", whose hint is now "As printed on invoices, e.g. 202401012345.":
  - "Old registration no.". Hint: "Printed in brackets after the registration no., e.g. 1234567-X. Empty: none."
- After "SQL Account database":
  - "Address" (textarea). Hint: "Printed in the invoice header, as one line. Several lines are joined with commas."
  - "Phone". Hint: "Printed in the invoice header."
  - "Email". Hint: "Printed in the invoice header."
  - "Website". Hint: "Printed in the invoice header, e.g. www.example.com."
  - "Bank account on invoices" (select). Options look like "Maybank current · Maybank · 5141 2300 4417", accounts in use only. Hint: "Printed under All payments to be made to. Its bank, account number, bank address and transfer code come from Setup › Bank accounts."
  - "Under the signature". Hint: "Empty: For and the company's name, as SQL Account prints it."
- Refusals:
  - "Bank account on invoices: choose one of this company's bank accounts."
  - "Bank account on invoices: that account is stopped. Choose one in use, or use it again first."

**Printed invoices section** (`#suPrint`, in the drawer of an existing company only, including AI):
- h3 "Printed invoices".
- Note: "Customer invoices and self-billed e-Invoices are printed from SQL's documents with this header and footer: the name, registration no., TIN, address, phone, email and website above, the bank account on invoices, and the logo and signature here (PNG or JPEG, at most 2 MB)."
- Two fields, **Logo** and **Signature**, each with:
  - A preview image (max 70 px high, 220 px wide, white background), or "None uploaded".
  - A file input accepting .png, .jpg and .jpeg.
  - An **Upload** button, and a **Remove** button only when an image is present.
- Then "**Print settings still missing** (invoices print without them):" with the list, or "Every print setting is filled in."
- Then the Fonts and Too long notes.

**Toasts:**
- "Choose an image first." (error)
- "Logo uploaded" / "Signature uploaded"
- "Logo taken off the invoices" / "Signature taken off the invoices"
- No reason prompt and no confirm.

**Server errors:**
- "Choose an image to upload."
- "Logo: upload a PNG or JPEG image."
- "Logo: the file is empty."
- "Logo: the image is larger than 2 MB. Save it smaller and upload it again."
- "Logo: the file isn't a PNG image."
- "Logo: the image can't be read. Save it again as PNG or JPEG."
- "Logo: the image is too large (W x H pixels). Save it smaller."

**Rules:**
- Images are stored read-only by fingerprint.
- Remove keeps the file in the records folder.
- An image changed on disk stops printing and triggers the missing note.

**Activity log:** "Uploaded the logo printed on AISB's invoices: '{file}'" and "Removed the logo from AISB's invoices".

### A15. Setup › Bank accounts and Customers and suppliers

**Bank accounts** (masters.py 103-104, 597):
- "Bank address" (wide). Hint: "Printed on invoices when this account is the one to pay into."
- "Bank transfer (SWIFT) code" (max 11). Hint: "Printed on invoices, e.g. EXMBMYKL."
- Used-by counts now include "company's invoices" / "companies' invoices". Delete is refused with "Used by 1 company's invoices, so it can't be deleted. Stop using it instead."

**Customers and suppliers** (masters.py 200-206):
- "Address line 1" to "Address line 4" (wide). Line 1 hint: "Printed on its invoices. Filled from SQL's list when pasted with Address1 to Address4."
- "Attention". Hint: "Printed as Attn on its invoices."
- "Phone".
- "Terms" (max 40). Hint: "Its credit term as SQL prints it, e.g. 30 Days."
- The paste-a-list headings now also take Address1-4, Attention/Attn/Contact person, Phone/Tel, Credit term/Terms (partybook.py 381-388).

### A16. Setup file and audit trail

**Setup file** (setupfile.py 22-27, 154-212, 382-399, 510, 602-619):
- An **Everything** export now carries the print fields, the bank account on invoices (by name and number) and the logo and signature images (base64 with their fingerprints).
- It holds "The companies' signature images, as printed on their invoices."
- It leaves out "The logo of AISB: its file changed or is gone since it was uploaded, so it isn't in the file. Upload it again in Setup › Companies after importing."
- Import refusals:
  - "Logo: the image isn't the one exported (its fingerprint doesn't match). Export the setup again."
  - "Bank account on invoices: the file has no bank account Maybank current (5141 2300 4417) for this company."
  - "…its print settings can be imported once the records are updated."

**Audit trail** (auditread.py 31): the new table appears as "MyInvois e-Invoice" / "MyInvois e-Invoices" (rows added and changed by Import), plus the "Opened file" events from A10.

---

## B. What the canvas covers today, and what is missing or wrong

**Sql.dc.html (SQL import)** covers the old e-Invoice pills only.

What is now wrong:
- (a) Line 129 says "e-Invoice details still come from copy and paste below." Now a MyInvois copy is fetched; use the A1 sentence.
- (b) Section heading "Journals and customer invoices" should be "Journals and invoices".
- (c) The MyInvois link goes to the generic `https://myinvois.hasil.gov.my/`. It should be the share URL, labelled "MyInvois ↗".
- (d) The `EINV.submitted` text "Submitted" should be "Submitted, not validated". This is the word used when MyInvois fills it.
- (e) The STATUS legend meanings for Another company and Company not in Setup describe listings only, by name or registration number. A MyInvois copy is told by its TIN.

What is missing:
- The print bar (month select, two zip links, print-settings, fonts and too-long notes, **Open Setup › Companies**).
- The PDF buttons (Invoice, Debit note, Credit note PDF).
- The e-Invoices table's MyInvois column and PDF action.
- The whole From MyInvois box (empty state, source note, filter, table with match pills, received-but-not-found list).
- The MyInvois copy row in "What the fetch found", and the "MyInvois e-Invoices: N" summary.
- The MyInvois-only preview card and its Keep button labels.
- The apply toast clause.
- The paste refusal toast.
- MyInvois reasons among the unused files.
- A "SQL reports fetched" import row.

**SetupCompanies.dc.html** is missing all six new fields and the **Bank account on invoices** select.
- Its reg_no hint differs from code: the board has "Listings exported from SQL Account are recognised…", the code has "As printed on invoices…". Merge them.
- The AISB sample `reg_no: '201901023456 (1331234-K)'` should be split into reg_no '201901023456' and old_reg_no '1331234-K'.
- The Printed invoices section is missing, with its upload, remove and error states and the missing, fonts and too-long notes.

**Setup.dc.html (Bank accounts)** is missing Bank address and SWIFT. The **Used by** column doesn't count "company's invoices", and the delete refusal for it is missing.

**SetupParties.dc.html** is missing Address lines 1-4, Attention, Phone and Terms, and the paste-preview columns for them. It currently maps only code, name, gl, tin and brn.

No board shows the printed PDF, the zip, or the "Not printed" refusal page.

Minor gaps:
- **SetupMove.dc.html**: the "file holds signature images" note and the left-out image note.
- **Backup.dc.html** (activity log): no MyInvois or logo lines.
- **AuditTrail.dc.html**: no "Opened file" events for invoices and no "MyInvois e-Invoice" rows.

**Company.dc.html, Payment.dc.html and their Dark and Mobile twins** use the number style `IV-2610-031`, `CN-2611-002`, `OR 2610-07`. The SQL board uses `IV2610-014`, `OR2610-006`. SQL's own style is unhyphenated, so the samples should be aligned. The code itself needs no change on these boards.

---

## C. Proposal

### Sample data (AISB, kept in SQL; today Wednesday 18 Nov 2026; month being worked October 2026)

This sample data reconciles with the existing boards.

**AISB (existing values plus new ones):**
- Name: AISB Sdn Bhd. Registration no. 201901023456, old registration no. 1331234-K. TIN C 2345678901; in MyInvois it appears as C2345678901.
- Address: a fictional KL address of 2 lines. Phone 03-xxxx xxxx, email accounts@…, website www…
- Bank account on invoices: "Maybank current · Maybank · 5141 2300 4417", with a bank address and SWIFT EXMBMYKL (the code's own example) or MBBEMYKL.
- Under the signature: empty, so the PDF prints "For AISB Sdn Bhd".

**AI (Agrinexus International):**
- Not kept in SQL, so there is no SQL page and no printing.
- Its Setup drawer still shows Printed invoices in today's code. Propose hiding the section when "Kept in SQL Account" is off. That is a small code change; flag it as new work.

**Customer:** Tenant, 300-T001 (chart: "Tenant (Block A)"). Add address lines 1-3, Attention, Terms "30 Days". Optionally give it a full fictional company name.

**MyInvois copy:** "MyInvois Sep-Nov.xlsx", saved 17 Nov 2026 16:05, fetched 18 Nov 2026 10:42 (the board's existing fetch time). Period "3 Sep to 13 Nov". It holds 14 e-Invoices: 7 issued, 1 self-billed, 6 received.

Issued:

| Doc | e-Invoice | SQL pill | PDF |
|---|---|---|---|
| IV2610-014, 1,800.00 | Invoice, Valid, validated 2026-10-01 11:19:44, Long ID present | Validated | QR |
| IV2610-009, Utilities recharge October Unit 3A, 238.40 (new) | Invoice, Cancelled | Cancelled | Cancelled state |
| IV2611-002, 1,800.00 | Valid | Validated | QR |
| IV2611-005, 245.60 | Submitted | Submitted, not validated | Pending state |
| IV2609-028, 1,200.00 | Valid | Was Submitted; fill note "(was Submitted, not validated)" | — |
| IV2609-022, 4,500.00 | Valid, but the copy has no Long ID | Was Has UUID | no_link state |
| CN2609-002, 4,500.00 | Credit Note, Valid | IV2609-015 keeps "Cancelled by CN2609-002" | Credit note PDF, positive figures, no bank block |

The CN2609-002 credit note is to customer 300-A001 Agrinexus International.

Self-billed:
- PV2610-018, 27 Oct (new number), "Cloud software subscription October".
- Supplier "Brightline Software Pte Ltd" (fictional), TIN EI00000000030.
- USD 100.00, Valid, validated 2026-10-29 14:19:44.
- Lines: 900-600 at MYR 300.00 and 170.00, which print as USD 63.83 and 36.17.
- "Paid as MYR 470.00 by PV2610-018".

Received:
- PV2611-004, Internet and phone, 420.00: matched "By amount".
- PV2611-006, Water, 84.30: matched by TIN and amount, no pill.
- PV2609-027, Printer toner, 312.00: matched by number, no pill.
- Two courier e-Invoices of 93.28 and 93.22 paid together by PV2611-009 (186.50): "Paid together" pill.
- Not found in SQL: Green Pest Control "GPC/2611/0457", RM 250.00, issued 2026-11-12.
- Leave electricity (PV2611-003) out of the matches; that voucher carries the Changed-in-SQL story.

Other samples:
- Print months: customer Nov, Oct and Sep 2026; self-billed Oct 2026. Show October selected; November shows only the customer zip.
- Apply toast: "Kept 14 MyInvois e-Invoices (14 new, 0 changed); 5 SQL documents filled in."

### Boards to add

These go in the Monthly work row, right of the n2 note, for example at x 6680 and 8200, y 12900. Widen that row title's maxW.

**1. "SQL import · MyInvois" (MyInvois.dc.html).** Purpose: the e-Invoices card and the From MyInvois box, as now built. States:
- `read`: All, with match pills, the PDF on the self-billed row, and the not-found list.
- `received` and `self-billed`: the filter selected.
- `none-read`: the empty instructions.
- `fetch-only`: the preview card "MyInvois e-Invoices · No new listing entries", the review row, and the Keep MyInvois e-Invoices button.
- `kept`: the toast.
- `second-copy`: "2 new, 1 status or details changed, 11 unchanged, 1 left as a later copy says".
- `refused`: the Row 7 UUID error, the Another company row, and the no-TIN row.
- `pasted`: the paste refusal toast.
- Format Validated, saved and read times as "1 Oct 2026, 11:19". The code shows raw ISO; this is a formatting-only change for the build.

**2. "Printed invoice" (InvoicePdf.dc.html).** Purpose: show the PDF output, marked "layout is SQL's, not restyled". The page is drawn at US Letter proportion. States:
- `customer-valid`: IV2610-014 with QR, UUID and "Validated on 01/10/2026 11:19:44", and the bank block.
- `self-billed-usd`: PV2610-018, with Supplier, TIN and Buyer lines, Amount(USD), and the Paid as line.
- `credit-note`: CN2609-002.
- `cancelled`: IV2610-009.
- `not-validated`: IV2611-005.
- `no-long-id`: IV2609-022.
- `settings-missing`: no logo, no bank block, "For AISB Sdn Bhd" under an empty signature box.
- `two-pages`: "Continued on page 2 of 2" and "Page 1 of 2".
- `look-alike`: a note that fonts were substituted.
- `refused-tab`: the "Not printed" page with the GL-lines sentence.
- `zip`: a file list for "AISB Invoices 2026-10.zip", with "Not printed.txt" contents.

**3. Setup › Companies print states.** Either add these to SetupCompanies.dc.html or add a board "Setup · Companies · printed invoices". States:
- `print-ok`: logo and signature previews, "Every print setting is filled in."
- `print-missing`: two missing sentences.
- `upload-error`: "Logo: the image is larger than 2 MB…".
- `image-changed`.
- `fonts-hosted`: all 7 font notes.
- `too-long`: the address is cut.
- `ai-not-in-sql`: the proposed hidden section.

### Boards to change

- **Sql.dc.html:**
  - Fix the A1 sentence and the "Journals and invoices" heading.
  - Add the print bar to the top of that card, and PDF buttons in its e-Invoice column for IV2610-014, IV2611-002 and the others.
  - Add the MyInvois column and PDF action to the e-Invoices table; the box itself moves to board 1, or is embedded below.
  - Set the real share link and the "MyInvois ↗" label.
  - Change "Submitted" to "Submitted, not validated".
  - Add "MyInvois Sep-Nov.xlsx · MyInvois e-Invoices, 3 Sep to 13 Nov — 14 e-Invoices: 14 new, … (7 issued, 1 self-billed, 6 received)" to READ, and "MyInvois e-Invoices: 14." to the summary.
  - Make the legend meanings cover TIN for MyInvois copies.
  - Add the applyLabel variants and a "SQL reports fetched" import entry.
  - The board height grows; or move the e-Invoices section to board 1 and leave a pointer.
- **SetupCompanies.dc.html:**
  - Add the group "On printed invoices": Old registration no. (it may sit beside Registration no.), Address, Phone, Email, Website, Bank account on invoices, Under the signature. Use the hints quoted in A14.
  - Merge the reg_no hint.
  - Split the AISB sample.
  - Add the Printed invoices section to the edit drawer.
- **Setup.dc.html (Bank accounts):**
  - Add the group "On invoices" with Bank address and Bank transfer (SWIFT) code.
  - Maybank current: Used by includes "1 company's invoices". Add the delete-refused state.
  - Optional: a stopped-account warning that echoes the missing sentence.
- **SetupParties.dc.html:**
  - Add the group "On its invoices" with Address lines 1-4, Attention, Phone and Terms.
  - Tenant 300-T001 gets values for them.
  - The paste-preview mapping gains these columns.
- **SetupMove.dc.html:** in the import preview, "The file holds: The companies' signature images, as printed on their invoices."
- **Backup.dc.html (Activity log):**
  - "Read MyInvois copy 'MyInvois Sep-Nov.xlsx' for AISB: 14 e-Invoices, 14 new, 0 changed, 0 unchanged"
  - "MyInvois for AISB: IV2609-028: issued e-Invoice 7RPN2QXK… filled in from MyInvois, Validated (was Submitted, not validated)."
  - "Uploaded the logo printed on AISB's invoices: 'aisb-logo.png'"
- **AuditTrail.dc.html:** an "Opened file" event (invoice, IV2610-014 Tenant.pdf, 18 Nov 2026), and "MyInvois e-Invoice · Added · Import" rows.
- **Company.dc.html, Payment.dc.html and their Dark and Mobile twins:** renumber `IV-2610-031`, `CN-2611-002` and `OR 2610-07` to SQL style (`IV2610-031`, `CN2611-002`, `OR2610-007`) so they reconcile with the SQL board. No other change is required by this area.

### Gaps the build team should decide on

These are not code changes made, only flagged:
1. The per-document print notes (A13) are never shown in the UI, because `/api/invoices/{id}/check` exists but is unused. Propose a warning marker on the PDF button with the notes on hover or expand. This is new UI work; the backend is ready.
2. **Open Setup › Companies** opens the list, not AISB's drawer.
3. The month select defaults to the newest month, not the month being worked.
4. The PDF button for a self-billed invoice is labelled just "Invoice PDF".
5. The MyInvois link-notes reach the activity log only, never the SQL page.
