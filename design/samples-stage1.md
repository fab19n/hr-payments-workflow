# Shared sample data after stage 1

This is the one sample data set for every canvas board drawn after stage 1. Every Books, SQL, Bank, Company, Overview, Setup, statutory and audit pack figure comes from here, so all the boards agree.

- **Today:** Wednesday 18 November 2026.
- **Month being worked:** October 2026.
- **Companies:** AISB is kept in SQL Account. AI (Agrinexus International) is not.
- **Where boards conflict with this file:** this file wins. The edits that make an existing board agree are listed in section 22, "Changes to existing boards' samples".
- **Format rules:**
  - Money in tables is written `1,234.56`.
  - Report tables carry no "RM".
  - Balances are written `x Dr` or `x Cr`.
  - Brackets mean the other way round.
  - `—` means unknown. A zero in a movement column is left blank. A nil balance is `0.00`.

---

## 1. Timeline

| When | What |
|---|---|
| 30 Sep 2026 | September PCB (PV2609-024, 4,915.00), September PERKESO (PV2609-026, 1,086.40) and the September TNB bill (PV2609-025, 1,097.40) are paid from Maybank current. They are dated before the journal kept here, so they reach the books only through the 1 Oct openings. |
| 12 Nov 2026 16:04 | Fetch. The listings read: PV, OR, JV, Customer Invoice and Cash Book, 1 Oct to 12 Nov. Also read: **GL Journal Nov.xlsx** (GL Journal of Transaction, 1 Nov to 12 Nov; 13 documents, 28 lines). This fetch holds version 1 of PV2611-003 (1,163.20) and PV2611-008 (250.00). |
| 18 Nov 2026 10:42 | Fetch: the "SQL exports fetched 18 Nov 2026, 10:42" preview on Sql.dc.html. It reads the six listings already on that board, plus the files below. |
| 18 Nov 2026 10:42 | **GL Journal Oct-Nov.xlsx**: GL Journal of Transaction, 1 Oct to 17 Nov. 34 documents (22 new, 1 changed, 11 unchanged, 1 no longer in SQL), 78 lines. |
| 18 Nov 2026 10:42 | **Trial Balance Oct.xlsx**: Trial Balance, From date 1 Oct, as at 31 Oct. 31 accounts. Its opening balances are kept at 1 Oct 2026. |
| 18 Nov 2026 10:42 | **GL Ledger.xlsx**: GL Ledger, 1 Oct to 12 Nov. 12 accounts. Its Balance B/F are kept at 1 Oct. The trial balance's openings are preferred. |
| 18 Nov 2026 10:42 | **Supplier Invoice Listing Oct.xlsx**: Supplier Invoice Listing, 1 Oct to 31 Oct, 3 documents. |
| 18 Nov 2026 10:42 | **MyInvois Sep-Nov.xlsx**: MyInvois e-Invoices, 3 Sep to 13 Nov. Saved 17 Nov 2026 16:05. 18 e-Invoices. |
| 18 Nov 2026 10:44 | "Take it for AISB" is confirmed for the printed name `AISB (M) SDN BHD (1331234-K)`, by Aisha Rahman. |
| 18 Nov 2026 10:50 | Books › Statutory: **Use these accounts** gives the toast "4 statutory accounts added." |
| 18 Nov 2026 11:05 | Books Excel exports are made ("Exported 18/11/2026 11:05."). |

**What SQL was fetched up to.** The listings reach 12 Nov. The GL Journal of Transaction reaches **17 Nov**. SQL's trial balance is as at **31 Oct**.

**The Books default period.** With no dates typed, the period is 1 Jan 2026 to 17 Nov 2026. 17 Nov is the latest `period_to` among the reports kept.

**What the journal kept covers.** It covers only 01/10/2026 to 17/11/2026. Nothing before 1 Oct is in the lines. Everything before then reaches the books through the 1 Oct openings.

---

## 2. Companies

| Field | AISB | AI |
|---|---|---|
| Code | AISB | AI |
| Name (as printed) | AISB Sdn Bhd | Agrinexus International |
| Short name | — | Agrinexus Intl. |
| Kept in SQL Account | Yes | No |
| **First month tracked** | **September 2026** (2026-09) | **September 2026** (2026-09) |
| Financial year starts in | January (set: `1`) | January (set: `1`) |
| Registration no. | 201901023456 | 202001045678 |
| Old registration no. | 1331234-K | 1378901-W |
| Tax ID (TIN) | C 2345678901 (MyInvois prints C2345678901) | C 3456789012 |
| SST no. | W10-1808-32000123 | — |
| KWSP / PERKESO / LHDN employer nos. | 012345678 / E1234567891A / E 9876543210 | 023456789 / E2345678912B / E 8765432109 |
| SQL Account database | AISB 2025 | — |
| Address | Lot 12, Jalan Teknologi 3/1, Kota Damansara, 47810 Petaling Jaya, Selangor | — (not printed: not in SQL) |
| Phone / Email / Website | 03-6150 2200 / accounts@aisb.example / www.aisb.example | — |
| Bank account on invoices | Maybank current · Maybank · 5141 2345 4417 | — |
| Under the signature | empty, so it prints "For AISB Sdn Bhd" | — |
| Logo / signature | Logo uploaded (aisb-logo.png); signature not uploaded | Section hidden (new_work: hide Printed invoices when not kept in SQL) |
| Printed company names | `AISB (M) SDN BHD (1331234-K)`, confirmed 18/11/2026 at 10:44 by Aisha Rahman | None confirmed. |

**AISB's "Print settings still missing" list**
- "No signature: upload it under Printed invoices in Setup › Companies › AISB."
- The bank account has its address and SWIFT, so no bank sentence is listed.

**Setup › Bank accounts, Maybank current (AISB)**
- Bank address: "Maybank Kota Damansara, 47810 Petaling Jaya, Selangor".
- Bank transfer (SWIFT) code: MBBEMYKL.
- Used by includes "1 company's invoices".

**AI**
- No chart of accounts.
- No books lines or openings.
- No statutory accounts.
- Its only bank account is Maybank FCA (USD).

---

## 3. AISB chart of accounts

"New" marks an account that is not on SetupChart.dc.html today (see section 22).

| Code | Name | SQL group | Type | Special | Parent | Status |
|---|---|---|---|---|---|---|
| 200-000 | Office equipment | FA | Asset | | | |
| 200-100 | Motor vehicles | FA | Asset | | | |
| 300-000 | Trade debtors | CA | Asset | Debtor control | | |
| 300-900 | Cash and bank | CA | Asset | | | |
| 310-000 | Maybank current | CA | Asset | Bank account | 300-900 | |
| 310-100 | Maybank savings | CA | Asset | Bank account | 300-900 | |
| 310-200 | USD collections | CA | Asset | Bank account | 300-900 | Stopped |
| 320-000 | Salary advances | CA | Asset | Deposit / prepayment | | |
| 330-000 | Fixed deposit | CA | Asset | | | **New** |
| 350-000 | Deposits paid | — (no SQL group) | Asset | Deposit / prepayment | | |
| 400-000 | Trade creditors | CL | Liability | Creditor control | | |
| 420-000 | Accruals | CL | Liability | | | |
| 430-000 | Statutory payables | CL | Liability | | | |
| 430-100 | KWSP payable | CL | Liability | | 430-000 | |
| 430-200 | PERKESO payable | CL | Liability | | 430-000 | |
| 430-210 | EIS (SIP) payable | CL | Liability | | 430-000 | **New** |
| 430-300 | PCB payable | CL | Liability | | 430-000 | |
| 440-000 | Deposits received | CL | Liability | | | **New** |
| 500-000 | Share capital | CP | Equity | | | |
| 500-F001 | Funds from Agrinexus International | CP | Equity | | 500-000 | **New** |
| 510-000 | Retained earnings | RE | Equity | | | **New** |
| 600-000 | Rental income | SL | Income | | | |
| 610-000 | Management fees | SL | Income | | | **New** |
| 650-000 | Bank profit | OI | Income | | | **New** |
| 900-010 | Bank charges | EP | Expense | | | **New** |
| 900-100 | Salaries and wages | EP | Expense | | | |
| 900-110 | KWSP - employer | EP | Expense | | | **New** |
| 900-120 | PERKESO - employer | EP | Expense | | | **New** |
| 900-130 | EIS - employer | EP | Expense | | | **New** |
| 900-200 | Directors fee | EP | Expense | | | |
| 900-300 | Office rental | EP | Expense | | | |
| 900-400 | Utilities | EP | Expense | | | |
| 900-600 | Telephone and internet | EP | Expense | | | |
| 900-700 | Contract works | EP | Expense | | | **New** |
| 900-800 | Printing, postage and stationery | EP | Expense | | | **New** |
| 900-900 | Professional fees | EP | Expense | | | **New** |
| 999-000 | Suspense | — | — (not typed) | | | |

- 350-000 and 999-000 stay as they are.
- 999-000 has no balance and no lines, so no Books note names it. Use it only in a state-only variant (section 21).

---

## 4. AISB customers and suppliers (Setup › Customers and suppliers)

| Code | Name in Setup | Kind | Control account | Notes |
|---|---|---|---|---|
| 300-T001 | Tenant | customer | 300-000 | SQL prints the name "Tenant (Block A)". Invoice fields: Address line 1 "Block A, Lot 12, Jalan Teknologi 3/1", line 2 "Kota Damansara", line 3 "47810 Petaling Jaya, Selangor"; Attention "Accounts department"; Phone 03-6150 2288; Terms "30 Days"; TIN C 4567890123. |
| 300-U001 | Office tenant (Unit 3A) | customer | 300-000 | **New in Setup.** Address line 1 "Unit 3A, Lot 12, Jalan Teknologi 3/1", line 2 "Kota Damansara", line 3 "47810 Petaling Jaya, Selangor"; Attention "Accounts department"; Terms "30 Days"; TIN C 5678901234. |
| 300-A001 | *(not in Setup)* | — | 300-000 | Kept out of Setup on purpose. Books names it from SQL ("AGRINEXUS INTERNATIONAL") with the **Not in Setup** pill. |
| 400-E012 | Electricity supplier | supplier | 400-000 | Match words: TNB, ELECTRIC. |
| 400-R001 | Office landlord | supplier | 400-000 | Pays Menara Holdings Sdn Bhd. |
| 400-P004 | Payroll advisor | supplier | 400-000 | Short name Robin Advisory. |
| 400-C003 | Old cleaning contractor | supplier | 400-000 | Stopped. It owes nothing in October. Its July invoice of 850.00 sits inside the 400-000 opening. |
| 400-B002 | Bina Jaya Sdn Bhd | supplier | 400-000 | No SQL entries. |
| 400-K001 | KWSP | statutory | 430-100 | Never listed as a supplier. |
| 400-A001 | Agrinexus International | related | — | |

**Statutory accounts** (Setup › Statutory accounts, AISB; added 18 Nov 10:50 with Use these accounts):

| Name | Kind | Payable account | Employer's share account | Due day | Used by | Status |
|---|---|---|---|---|---|---|
| EPF (KWSP) | EPF (KWSP) | 430-100 KWSP payable | 900-110 KWSP - employer | 15 | 0 | In use |
| SOCSO (PERKESO) | SOCSO (PERKESO) | 430-200 PERKESO payable | 900-120 PERKESO - employer | 15 | 0 | In use |
| EIS (SIP) | EIS (SIP) | 430-210 EIS (SIP) payable | 900-130 EIS - employer | 15 | 0 | In use |
| PCB (LHDN) | PCB (LHDN) | 430-300 PCB payable | — | 15 | 0 | In use |

- Before the accounts were confirmed, the "Suggested from the chart of accounts by their names" table holds the same four rows.
- 430-000 Statutory payables has no kind word, so it is not suggested.
- Clicking Use these accounts gives the toast "4 statutory accounts added."

---

## 5. Payroll and statutory figures (AISB)

Staff salaries are paid net. The payroll journal credits what is taken off the salaries to the payables. Each authority's voucher the next month debits the payable, and debits the employer's share to its own expense account.

| Payroll month | Gross (900-100) | Net paid | EPF employee / employer | SOCSO employee / employer | EIS employee / employer | PCB | KWSP total | PERKESO total (SOCSO + EIS) |
|---|---|---|---|---|---|---|---|---|
| September 2026 | 59,121.90 | 48,600.00 (PV2609-012, 24 Sep) | 5,320.00 / 5,860.00 | 205.00 / 717.60 | 81.90 / 81.90 | 4,915.00 | **11,180.00** | 1,086.40 |
| October 2026 | 59,147.90 | 48,600.00 (PV2610-014, 24 Oct) | 5,346.00 / 5,894.00 | 205.00 / 717.60 | 81.90 / 81.90 | 4,915.00 | **11,240.00** | **1,086.40** |

**Which statutory payments are paid**

| What | Voucher | Date | Amount | Tracker payment (Company board) | In the books here? |
|---|---|---|---|---|---|
| KWSP September | PV2610-005 | 15 Oct 2026 | 11,180.00 | KWSP (EPF) · September, 11,180.00, paid 15 Oct, **linked**, Agrees | Yes |
| PCB September | PV2609-024 | 30 Sep 2026 | 4,915.00 | PCB (MTD) · September, linked | No (before 1 Oct) |
| PERKESO September | PV2609-026 | 30 Sep 2026 | 1,086.40 | none on the Company board | No (before 1 Oct) |
| PCB October | PV2611-012 | 14 Nov 2026 | 4,915.00 | PCB (MTD), paid 14 Nov, entered by hand: **Not linked** | Yes |
| PERKESO October | PV2611-015 | 17 Nov 2026 | 1,086.40 (SOCSO 205.00 + 717.60, EIS 81.90 + 81.90) | PERKESO (SOCSO & EIS), paid 17 Nov, entered by hand: **Not linked** | Yes |
| **KWSP October** | none | — | 11,240.00 owed | KWSP (EPF), unpaid, "Past legal deadline (15 Nov)" | — (late) |

PV2611-012 and PV2611-015 are in the journal (to 17 Nov). They have no listing yet, because the listings stop at 12 Nov. So they are not SQL entries and can't be linked. That is why the tracker column says Not linked.

---

## 6. Opening balances kept at 1 Oct 2026

These come from SQL's trial balance, Trial Balance Oct.xlsx, Opening Balance column at its From date 1 Oct.

| Code | Name | Opening |
|---|---|---|
| 200-000 | Office equipment | 18,500.00 Dr |
| 300-000 | Trade debtors | 8,500.00 Dr |
| 310-000 | Maybank current | 89,218.35 Dr |
| 310-100 | Maybank savings | 50,000.00 Dr |
| 320-000 | Salary advances | 1,500.00 Dr |
| 350-000 | Deposits paid | 6,000.00 Dr |
| 400-000 | Trade creditors | 850.00 Cr |
| 430-100 | KWSP payable | 5,320.00 Cr |
| 500-000 | Share capital | 100,000.00 Cr |
| 500-F001 | Funds from Agrinexus International | 1,050,000.00 Cr |
| 510-000 | Retained earnings | 200,488.05 Dr |
| 600-000 | Rental income | 41,400.00 Cr |
| 610-000 | Management fees | 37,200.00 Cr |
| 650-000 | Bank profit | 168.60 Cr |
| 900-010 | Bank charges | 412.00 Dr |
| 900-100 | Salaries and wages | 522,384.60 Dr |
| 900-110 | KWSP - employer | 46,480.00 Dr |
| 900-120 | PERKESO - employer | 6,458.40 Dr |
| 900-130 | EIS - employer | 737.10 Dr |
| 900-200 | Directors fee | 108,000.00 Dr |
| 900-300 | Office rental | 58,500.00 Dr |
| 900-400 | Utilities | 10,215.60 Dr |
| 900-600 | Telephone and internet | 3,780.00 Dr |
| 900-700 | Contract works | 72,000.00 Dr |
| 900-800 | Printing, postage and stationery | 2,964.50 Dr |
| 900-900 | Professional fees | 28,800.00 Dr |
| **Total** | 26 accounts | **1,234,938.60 Dr = 1,234,938.60 Cr** |

**What the openings hold**
- **300-000 (8,500.00):**
  - IV2609-022, 30 Sep, Management fee September, 300-A001: 4,500.00.
  - IV2609-028, 25 Sep, Consultancy recharge September, 300-A001: 1,200.00.
  - IV2609-030, 30 Sep, Rent September, Block A, 300-T001: 2,800.00.
  - IV2609-015 (4,500.00) is cancelled by CN2609-002, so it nets to nothing.
- **400-000 (850.00):** PI2607-019, 31 Jul, Old cleaning contractor 400-C003, still unpaid.
- **430-100 (5,320.00):** the employees' EPF for September.
- **The other payables:** 430-200, 430-210 and 430-300 are nil, because September was paid on 30 Sep.

**How the books treat the openings**
- Profit and loss openings are the year so far (January to September 2026). The rule is "a profit and loss opening kept later in the year is taken as the year's figure so far".
- Customer and supplier codes have no opening of their own. Their September balances sit inside 300-000 and 400-000 ("inside its control account").
- Five accounts have no opening: 420-000, 430-200, 430-210, 430-300 and 440-000. They show "not on SQL's trial balance, so nothing".

**January to September 2026 in these openings**
- Income: 78,768.60.
- Expenses: 860,732.20.
- Loss: **781,963.60**.
- SQL's trial balance moves this loss into retained earnings on its From date. So SQL prints 510-000 closing at 31 Oct as **982,451.65 Dr** (200,488.05 + 781,963.60), and prints the profit and loss accounts' closing as October only.

---

## 7. October 2026 documents (AISB) with their account lines

There are 20 documents and 45 lines. "Book" is the book name the ledger shows. Dr lines are listed first.

| Date | Doc no. | Book | Description | Dr | Cr | Amount |
|---|---|---|---|---|---|---|
| 1 Oct | IV2610-014 | Sales | Office rental October, Unit 3A | 300-U001 | 600-000 | 1,800.00 |
| 2 Oct | OR2610-001 | Bank | Rental received September | 310-000 | 300-T001 | 2,800.00 |
| 6 Oct | PV2610-003 | Bank | Contractor — field works (Field Works Sdn Bhd, FW-0931) | 900-700 | 310-000 | 24,000.00 |
| 15 Oct | OR2610-002 | Bank | Deposit received, Klinik Sehat | 310-100 | 440-000 | 8,000.00 |
| 15 Oct | PV2610-005 | Bank | KWSP September (code 400-K001) | 430-100 5,320.00; 900-110 5,860.00 | 310-000 11,180.00 | 11,180.00 |
| 20 Oct | OR2610-006 | Bank | Fund received (Agrinexus International, code 500-F001) | 310-000 | 500-F001 | **45,000.00** |
| 24 Oct | JV2610-006 | General | Director fee October | 900-200 | 310-000 | 12,000.00 |
| 24 Oct | PV2610-014 | Bank | Salaries October (8 staff, net) | 420-000 | 310-000 | 48,600.00 |
| 30 Oct | PI2610-011 | Purchase | Office rental October (INV-1043) | 900-300 | 400-R001 | 6,500.00 |
| 30 Oct | PI2610-013 | Purchase | Payroll advisory October (PA-1010) | 900-900 | 400-P004 | 3,200.00 |
| 30 Oct | PV2610-021 | Bank | Office rental October (code 400-R001, Chq 104420) | 400-R001 | 310-000 | 6,500.00 |
| 30 Oct | PV2610-022 | Bank | Stationery Mart (cheque 000214) | 900-800 | 310-000 | 1,120.00 |
| 31 Oct | CB2610-041 | Bank | Bank charges | 900-010 | 310-000 | 48.00 |
| 31 Oct | CB2610-044 | Bank | Reversal of CB2610-041 | 310-000 | 900-010 | 48.00 |
| 31 Oct | CB2610-050 | Bank | Profit paid (Maybank savings) | 310-100 | 650-000 | 21.40 |
| 31 Oct | CB2610-051 | Bank | Service charge (Maybank savings) | 900-010 | 310-100 | 10.00 |
| 31 Oct | IV2610-031 | Sales | Rent October, Block A | 300-T001 | 600-000 | 2,800.00 |
| 31 Oct | IV2610-033 | Sales | Management fee October | 300-A001 | 610-000 | 4,500.00 |
| 31 Oct | JV2610-007 | General | Payroll journal October | 900-100 59,147.90 | 420-000 48,600.00; 430-100 5,346.00; 430-200 205.00; 430-210 81.90; 430-300 4,915.00 | 59,147.90 |
| 31 Oct | PI2610-012 | Purchase | Electricity October (TNB) | 900-400 | 400-E012 | 1,136.20 |

**Documents by book:** Bank 12, General 2, Sales 3, Purchase 3. Total debits = total credits = **238,411.50**.

**October's bank book (310-000)**
- **In: 47,848.00.** These are OR2610-001 2,800.00, OR2610-006 45,000.00 and CB2610-044 48.00.
- **Out: 103,448.00.** These are PV2610-003 24,000.00, PV2610-005 11,180.00, JV2610-006 12,000.00, PV2610-014 48,600.00, PV2610-021 6,500.00, PV2610-022 1,120.00 and CB2610-041 48.00.
- They are the Bank board's 47,800.00 / 103,400.00 plus the 48.00 correction pair.

**What the October documents match on other boards**

| Document | Matches |
|---|---|
| PV2610-003 | Company "Contractor — field works" 24,000.00 |
| PV2610-005 | September KWSP payment, bank line "KWSP SEPT CONTRIBUTION" |
| OR2610-006 | BankReview's 20 Oct receipt, renamed "Fund receipt" |
| PV2610-014 | Company and BankReview "Salaries — staff" 48,600.00 |
| JV2610-006 | Company "Director fee" 12,000.00. A journal can't be linked to a payment, so the payment still reads "paid, not recorded in SQL" on Company, AuditPack and Main. |
| PV2610-021 | Company "Office rental" |
| PV2610-022 | BankReview "Stationery Mart" |
| IV2610-031 | Company "Rental received" invoice, whose e-Invoice is cancelled by CN2611-002 |
| IV2610-014 | Sql board, 1,800.00 |

- PV2610-003, OR2610-006, PV2610-014, PV2610-021 and PV2610-022 also match BankReview's vouchers, renumbered (see section 22).
- Not in SQL in October:
  - the telephone bill (paid 5 Nov by PV2611-004);
  - the October consultant fee (invoiced by PI2610-013, unpaid);
  - the October electricity payment (paid 4 Nov by PV2611-003).

---

## 8. November 2026 documents, 1 to 17 Nov (in the journal kept)

These matter for the default Books view, the statutory tab and the SQL page.

| Date | Doc no. | Book | Description | Lines |
|---|---|---|---|---|
| 2 Nov | IV2611-002 | Sales | Office rental November, Unit 3A | Dr 300-U001 / Cr 600-000 1,800.00 |
| 2 Nov | IV2611-005 | Sales | Utilities recharge November, Unit 3A | Dr 300-U001 / Cr 900-400 245.60 |
| 3 Nov | OR2611-001 | Bank | Rental received October (Tenant) | Dr 310-000 / Cr 300-T001 2,800.00 |
| 3 Nov | JV2611-001 | General | Transfer to fixed deposit | Dr 330-000 / Cr 310-000 20,000.00 |
| 4 Nov | PV2611-003 | Bank | Electricity October | **Version 2:** Dr 400-E012 / Cr 310-000 1,136.20. Version 1 was read 12 Nov at 1,163.20. |
| 5 Nov | PV2611-004 | Bank | Internet and phone (code 400-T003) | Dr 900-600 / Cr 310-000 420.00 |
| 5 Nov | PV2611-006 | Bank | Water bill October (code 400-W001) | Dr 900-400 / Cr 310-000 84.30 |
| 5 Nov | OR2611-002 | Bank | Rental received October, Unit 3A (code **300-U001**) | Dr 310-000 / Cr 300-U001 1,800.00 |
| 6 Nov | PV2611-007 | Bank | Cloud software subscription October (self-billed, USD 100.00) | Dr 900-600 300.00, Dr 900-600 170.00 / Cr 310-000 470.00 |
| 6 Nov | PV2611-009 | Bank | Courier charges October (code 400-C007) | Dr 900-800 / Cr 310-000 186.50 |
| 7 Nov | PV2611-008 | Bank | (250.00) | **No longer in SQL.** It was in the 12 Nov read but is not in the 18 Nov read, and it is still on the PV listing. |
| 8 Nov | JV2611-004 | General | Transfer to Maybank savings | Dr 310-100 5,000.00, Dr 900-010 1.00 / Cr 310-000 5,001.00 |
| 10 Nov | CN2611-002 | Other | Credit note: Rent October, Block A (e-Invoice issued in error) | Dr 600-000 / Cr 300-T001 2,800.00 |
| 14 Nov | PV2611-012 | Bank | PCB October | Dr 430-300 / Cr 310-000 4,915.00 |
| 17 Nov | PV2611-015 | Bank | PERKESO October | Dr 430-200 205.00, Dr 900-120 717.60, Dr 430-210 81.90, Dr 900-130 81.90 / Cr 310-000 1,086.40 |

- **310-000 running balance after 31 Oct:** 3 Nov 36,418.35 → 16,418.35; 4 Nov 15,282.15; 5 Nov 17,082.15 → 16,662.15 → 16,577.85; 6 Nov 16,107.85 → 15,921.35; 8 Nov 10,920.35; 14 Nov 6,005.35; **17 Nov 4,918.95 Dr**.
- **Tenant (300-T001) at 17 Nov:** the credit note leaves the Tenant **in credit 2,800.00** (paid in advance or overpaid) until the invoice is issued again.

---

## 9. Trial balance, 1 Oct 2026 to 31 Oct 2026 (AISB, roll-up ticked)

**Heading:** `Trial balance, 1 October 2026 to 31 October 2026`, with pill **Balances**.

**Banner** (green): **Checked against SQL's trial balance: agrees**. "Agrees with SQL's trial balance as at 31/10/2026: all 31 accounts compared."

**Openings line:** "Openings from SQL's trial balance at 1 October 2026 (26 accounts); not on SQL's trial balance, so nothing at 1 October 2026 (5 accounts)."

**Notes:** there are no notes under the table. The journal covers the period and no opening is missing.

| Code | Name | Opening debit | Opening credit | Debit | Credit | Closing debit | Closing credit |
|---|---|---|---|---|---|---|---|
| 200-000 | Office equipment | 18,500.00 | | | | 18,500.00 | |
| 300-000 | Trade debtors · *With 300-A001, 300-T001, 300-U001* | 8,500.00 | | 9,100.00 | 2,800.00 | 14,800.00 | |
| 310-000 | Maybank current | 89,218.35 | | 47,848.00 | 103,448.00 | 33,618.35 | |
| 310-100 | Maybank savings | 50,000.00 | | 8,021.40 | 10.00 | 58,011.40 | |
| 320-000 | Salary advances | 1,500.00 | | | | 1,500.00 | |
| 350-000 | Deposits paid | 6,000.00 | | | | 6,000.00 | |
| 400-000 | Trade creditors · *With 400-E012, 400-P004, 400-R001* | | 850.00 | 6,500.00 | 10,836.20 | | 5,186.20 |
| 420-000 | Accruals | | | 48,600.00 | 48,600.00 | | |
| 430-100 | KWSP payable | | 5,320.00 | 5,320.00 | 5,346.00 | | 5,346.00 |
| 430-200 | PERKESO payable | | | | 205.00 | | 205.00 |
| 430-210 | EIS (SIP) payable | | | | 81.90 | | 81.90 |
| 430-300 | PCB payable | | | | 4,915.00 | | 4,915.00 |
| 440-000 | Deposits received | | | | 8,000.00 | | 8,000.00 |
| 500-000 | Share capital | | 100,000.00 | | | | 100,000.00 |
| 500-F001 | Funds from Agrinexus International | | 1,050,000.00 | | 45,000.00 | | 1,095,000.00 |
| 510-000 | Retained earnings | 200,488.05 | | | | 200,488.05 | |
| 600-000 | Rental income | | 41,400.00 | | 4,600.00 | | 46,000.00 |
| 610-000 | Management fees | | 37,200.00 | | 4,500.00 | | 41,700.00 |
| 650-000 | Bank profit | | 168.60 | | 21.40 | | 190.00 |
| 900-010 | Bank charges | 412.00 | | 58.00 | 48.00 | 422.00 | |
| 900-100 | Salaries and wages | 522,384.60 | | 59,147.90 | | 581,532.50 | |
| 900-110 | KWSP - employer | 46,480.00 | | 5,860.00 | | 52,340.00 | |
| 900-120 | PERKESO - employer | 6,458.40 | | | | 6,458.40 | |
| 900-130 | EIS - employer | 737.10 | | | | 737.10 | |
| 900-200 | Directors fee | 108,000.00 | | 12,000.00 | | 120,000.00 | |
| 900-300 | Office rental | 58,500.00 | | 6,500.00 | | 65,000.00 | |
| 900-400 | Utilities | 10,215.60 | | 1,136.20 | | 11,351.80 | |
| 900-600 | Telephone and internet | 3,780.00 | | | | 3,780.00 | |
| 900-700 | Contract works | 72,000.00 | | 24,000.00 | | 96,000.00 | |
| 900-800 | Printing, postage and stationery | 2,964.50 | | 1,120.00 | | 4,084.50 | |
| 900-900 | Professional fees | 28,800.00 | | 3,200.00 | | 32,000.00 | |
| **Total** | | **1,234,938.60** | **1,234,938.60** | **238,411.50** | **238,411.50** | **1,306,624.10** | **1,306,624.10** |

That is 31 rows. 420-000 has a nil closing, so both of its closing cells are blank.

**Roll-up off.** The rows that change are below. Each code row carries `Sub-ledger of 300-000` or `Sub-ledger of 400-000`. The totals are unchanged.

| Code | Opening | Debit | Credit | Closing |
|---|---|---|---|---|
| 300-000 | 8,500.00 Dr | | | 8,500.00 Dr |
| 300-A001 | (inside its control account) | 4,500.00 | | 4,500.00 Dr |
| 300-T001 | | 2,800.00 | 2,800.00 | |
| 300-U001 | | 1,800.00 | | 1,800.00 Dr |
| 400-000 | 850.00 Cr | | | 850.00 Cr |
| 400-E012 | | | 1,136.20 | 1,136.20 Cr |
| 400-P004 | | | 3,200.00 | 3,200.00 Cr |
| 400-R001 | | 6,500.00 | 6,500.00 | |

**Search "KWSP".** Two rows match: 430-100 and 900-110 ("2 of 31 shown").

**Excel file.** "AISB Trial balance to 31-10-2026.xlsx".
- Row 1: "AISB Sdn Bhd (AISB)".
- Row 2: "Trial balance, 01/10/2026 to 31/10/2026 (customers and suppliers added into their control accounts)".
- Row 3: "Mirrored from SQL Account, read 18/11/2026. Exported 18/11/2026 11:05."

**Default view** (no dates; 1 Jan 2026 to 17 Nov 2026):
- No opening is kept on or before 1 Jan, so every opening and the opening and closing totals read `—`.
- Grey banner: "Not checked against SQL's trial balance". Text: "No trial balance of SQL's as at 17/11/2026 is kept, so this one can't be checked against SQL's. Fetch SQL's Trial Balance for the same dates."
- Notes:
  - The missing-openings sentence.
  - The coverage note: "The GL Journal of Transaction reads kept cover 01/10/2026-17/11/2026, not all of 01/01/2026-17/11/2026: lines dated outside them are missing here. Fetch the journal for the whole period."
- Pill: the code shows the red **Doesn't balance** (quirk 2). Draw **Can't be totalled** instead and list it as new_work.

---

## 10. General ledger: 310-000 Maybank current, 1 Oct to 31 Oct 2026

| Date | Doc No | Book | Description | Debit | Credit | Balance |
|---|---|---|---|---|---|---|
| | | | Opening balance · SQL's trial balance at 1 October 2026 | | | 89,218.35 Dr |
| 2 Oct | OR2610-001 | Bank | Rental received September | 2,800.00 | | 92,018.35 Dr |
| 6 Oct | PV2610-003 | Bank | Contractor — field works | | 24,000.00 | 68,018.35 Dr |
| 15 Oct | PV2610-005 | Bank | KWSP September | | 11,180.00 | 56,838.35 Dr |
| 20 Oct | OR2610-006 | Bank | Fund received | 45,000.00 | | 101,838.35 Dr |
| 24 Oct | JV2610-006 | General | Director fee October | | 12,000.00 | 89,838.35 Dr |
| 24 Oct | PV2610-014 | Bank | Salaries October | | 48,600.00 | 41,238.35 Dr |
| 30 Oct | PV2610-021 | Bank | Office rental October | | 6,500.00 | 34,738.35 Dr |
| 30 Oct | PV2610-022 | Bank | Stationery Mart (cheque 000214) | | 1,120.00 | 33,618.35 Dr |
| 31 Oct | CB2610-041 | Bank | Bank charges | | 48.00 | 33,570.35 Dr |
| 31 Oct | CB2610-044 | Bank | Reversal of CB2610-041 | 48.00 | | 33,618.35 Dr |
| | | | **Total for the period** | **47,848.00** | **103,448.00** | |
| | | | **Closing balance** | | | **33,618.35 Dr** |

Lines are in date order, then by doc no. (JV2610-006 comes before PV2610-014 on 24 Oct).

**A document's lines, opened inline**

- **PV2610-005**
  - Header: "PV2610-005 · the Bank Journal".
  - Source line: "Version 1, 15 October 2026, from SQL's GL Journal of Transaction (GL Journal Oct-Nov.xlsx), read 2026-11-18 10:42".
  - Lines: 430-100 KWSP payable, Dr 5,320.00. 900-110 KWSP - employer, Dr 5,860.00. 310-000 Maybank current `Bank`, Cr 11,180.00.
  - Total 11,180.00 / 11,180.00.
  - "The lines balance and agree with the listing."
- **PV2611-003** (November, Changed in SQL)
  - Source line: "Version 2, 4 November 2026, from SQL's GL Journal of Transaction (GL Journal Oct-Nov.xlsx), read 2026-11-18 10:42".
  - Lines: 400-E012 Dr 1,136.20. 310-000 `Bank` Cr 1,136.20.
  - "Earlier versions (1)": version 1 was read 2026-11-12 16:04 from GL Journal Nov.xlsx, at 1,163.20 / 1,163.20.

**400-000 picked on its own** (roll-up ticked):
- Note: "The trial balance, with customers and suppliers added into their control accounts, shows 400-000 with 400-E012, 400-P004 and 400-R001 added in: its ledger follows below, and together they close at 5,186.20 Cr."
- The 400-000 card shows only the opening, 850.00 Cr, and the closing, 850.00 Cr.
- The supplier cards follow. 400-R001 shows 30 Oct PI2610-011 Cr 6,500.00, then PV2610-021 Dr 6,500.00, closing nil.

**Default view.** Opening balance `—`, with the note "No opening balance of 310-000 is kept: … The running balance starts from 0."

---

## 11. Profit and loss

**1 Oct to 31 Oct 2026**
- Banner, green: **Reconciles to the trial balance**. "The net profit or loss after tax, -103,852.70, is the trial balance's profit and loss accounts' movement for 01/10/2026 to 31/10/2026."
- The rows below are the accounts that move. 900-120, 900-130 and 900-600 do not move in October.

| Account | 01/10/2026 to 31/10/2026 |
|---|---|
| **Sales** | |
| 600-000 Rental income | 4,600.00 |
| 610-000 Management fees | 4,500.00 |
| Total sales | 9,100.00 |
| **Gross profit** | **9,100.00** |
| **Other income** | |
| 650-000 Bank profit | 21.40 |
| Total other income | 21.40 |
| **Expenses** | |
| 900-010 Bank charges | 10.00 |
| 900-100 Salaries and wages | 59,147.90 |
| 900-110 KWSP - employer | 5,860.00 |
| 900-200 Directors fee | 12,000.00 |
| 900-300 Office rental | 6,500.00 |
| 900-400 Utilities | 1,136.20 |
| 900-700 Contract works | 24,000.00 |
| 900-800 Printing, postage and stationery | 1,120.00 |
| 900-900 Professional fees | 3,200.00 |
| Total expenses | 112,974.10 |
| **Net profit or loss before tax** | **(103,852.70)** |
| **Net profit or loss after tax** | **(103,852.70)** |

Under the table: "No comparative column: Nothing is kept for 01/10/2025 to 31/10/2025, the same period a year before, so there is nothing to compare with."

**This financial year to date, 1 Jan to 31 Oct 2026**

| Line | Amount |
|---|---|
| Sales: 600-000 | 46,000.00 |
| Sales: 610-000 | 41,700.00 |
| Total sales | 87,700.00 |
| Other income: 650-000 | 190.00 |
| 900-010 | 422.00 |
| 900-100 | 581,532.50 |
| 900-110 | 52,340.00 |
| 900-120 | 6,458.40 |
| 900-130 | 737.10 |
| 900-200 | 120,000.00 |
| 900-300 | 65,000.00 |
| 900-400 | 11,351.80 |
| 900-600 | 3,780.00 |
| 900-700 | 96,000.00 |
| 900-800 | 4,084.50 |
| 900-900 | 32,000.00 |
| Total expenses | 973,706.30 |
| **Net profit or loss after tax** | **(885,816.30)**: (781,963.60) for January to September plus (103,852.70) for October |

- Banner, grey: **Not checked against the trial balance**. "The trial balance for these dates can't be fully checked: an opening balance at 01/01/2026 is missing (see the Trial balance tab)."
- The coverage note follows.
- With **Months** ticked:
  - January to September show `—`.
  - October shows the October figures.
  - The total shows the year-to-date figures above.

---

## 12. Balance sheet at 31 October 2026

- Banner, green: **Balances and reconciles to the trial balance**.
  - "Balances: net assets and total equity are both 108,695.65."
  - "The profit or loss for the year to date, -885,816.30, is the profit and loss account's net profit or loss after tax for 01/01/2026 to 31/10/2026."
  - "Every account of the trial balance as at 31/10/2026 is in it once."
- Heading: `Balance sheet at 31 October 2026`, with pill **Balances**.

| Line | At 31/10/2026 |
|---|---|
| **Non-current assets** | |
| 200-000 Office equipment | 18,500.00 |
| Total non-current assets | 18,500.00 |
| **Current assets** | |
| 300-000 Trade debtors | 14,800.00 |
| 300-900 Cash and bank | 0.00 |
| 310-000 Maybank current (indented) | 33,618.35 |
| 310-100 Maybank savings (indented) | 58,011.40 |
| Total Cash and bank | 91,629.75 |
| 320-000 Salary advances | 1,500.00 |
| 350-000 Deposits paid | 6,000.00 |
| Total current assets | 113,929.75 |
| **Current liabilities** | |
| 400-000 Trade creditors | 5,186.20 |
| 430-000 Statutory payables | 0.00 |
| 430-100 (indented) | 5,346.00 |
| 430-200 (indented) | 205.00 |
| 430-210 (indented) | 81.90 |
| 430-300 (indented) | 4,915.00 |
| Total Statutory payables | 10,547.90 |
| 440-000 Deposits received | 8,000.00 |
| Total current liabilities | 23,734.10 |
| **Net current assets** | **90,195.65** |
| **Net assets** | **108,695.65** |
| **Capital** | |
| 500-000 Share capital | 100,000.00 |
| 500-F001 Funds from Agrinexus International (indented) | 1,095,000.00 |
| Total Share capital | 1,195,000.00 |
| **Retained earnings brought forward** | |
| 510-000 Retained earnings | (200,488.05) |
| Profit or loss for the year to date | (885,816.30) |
| **Total equity** | **108,695.65** |

- 420-000 Accruals is nil at 31 Oct.
- Notes:
  - "350-000 Deposits paid is an asset account but it has no SQL group, so it is shown under Current assets. Set its SQL group in Setup › Chart of accounts."
  - The comparative at 31/12/2025 is missing. Nothing is kept before 1 Oct 2026; draw the code's "No comparative…" sentence.
- **Excel file:** "AISB Balance sheet at 31-10-2026.xlsx". Heading: "Balance sheet at 31/10/2026 (profit or loss for the year from 01/01/2026)".

---

## 13. Customers and suppliers, 1 Oct to 31 Oct 2026 (ageing at 31 Oct 2026)

**Customers.** Banner, green: **Ties to the control accounts**. "Every control account ties: the customers listed add up to their control accounts in the trial balance."

Card **300-000 Trade debtors**, with pill **Ties to the trial balance**. Ageing column abbreviations: Cur = Current, 31-60 = 31-60 days, 61-90 = 61-90 days, 90+ = Over 90 days, B/F = Brought forward.

| Code | Name | Opening | Invoiced | Received | Other | Closing | Cur | 31-60 | 61-90 | 90+ | B/F |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 300-000 | *Held on the control account itself, not split by customer* | 8,500.00 | | | | **8,500.00** | | | | | 8,500.00 |
| 300-A001 | AGRINEXUS INTERNATIONAL, pill `Not in Setup` | 0.00 | 4,500.00 | | | **4,500.00** | 4,500.00 | | | | |
| 300-T001 | Tenant | 0.00 | 2,800.00 | 2,800.00 | | **0.00** | | | | | |
| 300-U001 | Office tenant (Unit 3A) | 0.00 | 1,800.00 | | | **1,800.00** | 1,800.00 | | | | |
| **Total** | | 8,500.00 | 9,100.00 | 2,800.00 | 0.00 | 14,800.00 | 6,300.00 | 0.00 | 0.00 | 0.00 | 8,500.00 |
| 300-000 in the trial balance | | 8,500.00 | Moved 6,300.00 | | | 14,800.00 | | | | | |

- Card note: "300-000 Trade debtors: the customers add up to the control account in the trial balance, 8,500.00 at the start and 14,800.00 at the end."
- Bottom note: "Not in Setup › Customers and suppliers, so named from the chart or the name SQL printed: 300-A001."
- Why the Tenant reads 0.00 while the October rent is open: the September rent it paid on 2 Oct sits in the control account's own 8,500.00. A customer's code is counted only from the control account's first opening. This is true to the code, and a designer may note it on the board. Ageing totals 6,300.00 + 8,500.00 = 14,800.00.

**Suppliers.** Banner, green: **Ties to the control accounts**.

| Code | Name | Opening | Invoiced | Paid | Other | Closing | Cur | 31-60 | 61-90 | 90+ | B/F |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 400-000 | *Held on the control account itself, not split by supplier* | 850.00 | | | | **850.00** | | | | | 850.00 |
| 400-E012 | Electricity supplier | 0.00 | 1,136.20 | | | **1,136.20** | 1,136.20 | | | | |
| 400-P004 | Payroll advisor | 0.00 | 3,200.00 | | | **3,200.00** | 3,200.00 | | | | |
| 400-R001 | Office landlord | 0.00 | 6,500.00 | 6,500.00 | | **0.00** | | | | | |
| **Total** | | 850.00 | 10,836.20 | 6,500.00 | 0.00 | 5,186.20 | 4,336.20 | 0.00 | 0.00 | 0.00 | 850.00 |
| 400-000 in the trial balance | | 850.00 | Moved 4,336.20 | | | 5,186.20 | | | | | |

- Card note: "400-000 Trade creditors: the suppliers add up to the control account in the trial balance, 850.00 at the start and 5,186.20 at the end."
- KWSP 400-K001 is not listed.

**Statement 300-A001 AGRINEXUS INTERNATIONAL** (Not in Setup)
- Note: "Customer under 300-000 Trade debtors. Owed by them at 31 Oct 2026: 4,500.00."
- Ledger:
  - Opening 0.00.
  - 31 Oct, IV2610-033, Sales, Management fee October, debit 4,500.00, balance 4,500.00 Dr.
  - Closing 4,500.00 Dr.
- Still open at 31 Oct 2026: pill Current 4,500.00. Row: 31 Oct, IV2610-033, Management fee October, 4,500.00, 4,500.00, 0, Current.

**Statement 300-000** (the control account itself)
- One open item: "Brought forward", 8,500.00.

**Excel file.** "AISB Customers and suppliers to 31-10-2026.xlsx", plus "AISB Customers to 31-10-2026.xlsx" when one side is chosen.

---

## 14. Statutory payables (Books › Statutory, AISB)

### 14a. As Next up opens it: From 1 Oct 2026, To 18 Nov 2026

**Heading:** `Statutory payables, October 2026 to November 2026`.

**Banner** (warn): **Statutory payables to look at**. "1 statutory payable to look at: EPF (KWSP) for October 2026 wasn't paid by 15 Nov 2026."

| Card | Owed line | Month | Withheld (doc) | Employer share | Paid | Difference | Balance at due date | Status and text | Payment voucher | Tracker payment |
|---|---|---|---|---|---|---|---|---|---|---|
| **EPF (KWSP)** · 430-100 KWSP payable. Employer's share: 900-110 KWSP - employer · due by the 15th of the next month | "Owed at 1 Oct 2026: 5,320.00 owed; 5,320.00 of it paid since." | October 2026 (Due 15 Nov 2026) | 5,346.00 (JV2610-007) | | 0.00 | −5,346.00 | 5,346.00 owed | **Late**: "EPF (KWSP) for October 2026 wasn't paid by 15 Nov 2026." | — | — |
| | | November 2026 (Due 15 Dec 2026), muted | 0.00 | | 0.00 | | — | Nothing: "Nothing was taken off the salaries for EPF (KWSP) in November 2026." | — | — |
| **SOCSO (PERKESO)** · 430-200 PERKESO payable. Employer's share: 900-120 PERKESO - employer | "Owed at 1 Oct 2026: nil." | October 2026 | 205.00 (JV2610-007) | 717.60 | 205.00 | | 205.00 owed | **Cleared** + **Paid late**: "SOCSO (PERKESO) for October 2026 paid in full, the last of it on 17 Nov 2026, after the due day 15 Nov 2026." | PV2611-015 17 Nov | Not linked |
| **EIS (SIP)** · 430-210 EIS (SIP) payable. Employer's share: 900-130 EIS - employer | "Owed at 1 Oct 2026: nil." | October 2026 | 81.90 (JV2610-007) | 81.90 | 81.90 | | 81.90 owed | **Cleared** + **Paid late**: "EIS (SIP) for October 2026 paid in full, the last of it on 17 Nov 2026, after the due day 15 Nov 2026." | PV2611-015 17 Nov | Not linked |
| **PCB (LHDN)** · 430-300 PCB payable. No employer's share account | "Owed at 1 Oct 2026: nil." | October 2026 | 4,915.00 (JV2610-007) | | 4,915.00 | | nil | **Cleared**: "PCB (LHDN) for October 2026 paid in full." | PV2611-012 14 Nov | Not linked |

- November rows for SOCSO, EIS and PCB match the EPF November row.
- The payment of PV2610-005 (5,320.00, 15 Oct) is the brought-forward month, so it is not a row.

### 14b. This financial year to date (empty inputs: January 2026 to November 2026)

This is the code's output today.
- January to August: grey "Before tracking · Nothing".
- "Owed at 1 Jan 2026: unknown."
- On each card: "No opening balance of 430-100 is kept at 01/01/2026, so what was owed before then is unknown and its balances can't be shown. Fetch SQL's trial balance for that day." The same note names 430-200, 430-210 and 430-300 on their cards.
- **The false alarm in September.** The journal starts 1 Oct, so September's withholding isn't in the lines. PV2610-005 (15 Oct) is therefore taken as an overpayment of September:
  - EPF September: withheld 0.00, employer 5,860.00, paid 5,320.00, +5,320.00, nil, **Over**: "EPF (KWSP) for September 2026: RM 5,320.00 more was paid than was taken off the salaries."
  - Tracker: "RM 11,180.00 paid 15 Oct 2026 · Agrees".
  - Summary: "2 statutory payables to look at: EPF (KWSP) for September 2026: RM 5,320.00 more was paid than was taken off the salaries; EPF (KWSP) for October 2026 wasn't paid by 15 Nov 2026."
- **The right behaviour to draw (new_work):** don't judge months the GL Journal of Transaction kept doesn't cover. Show them muted as "Not covered by the journal kept (from 1 Oct 2026)". The summary is then the one in 14a. October and November rows are as in 14a.

### 14c. Other statutory states (data for state-only variants)

- **Misposting.** PV2610-005 puts the 5,860.00 on 900-120 instead of 900-110. Banner:
  > "PV2610-005 (15 Oct 2026) pays EPF (KWSP), but puts RM 5,860.00 of employer's share on 900-120 PERKESO - employer, the SOCSO (PERKESO) employer account, though it pays no SOCSO (PERKESO). EPF (KWSP)'s employer share account is 900-110 KWSP - employer. The totals are right; each expense account is off by RM 5,860.00."

  It is followed by the "Correct it in SQL Account…" line.
- **All clear.** From and To are October 2026, and KWSP October is paid 18 Nov by PV2611-018 11,240.00 (5,346.00 + 5,894.00). Text: "All statutory payables cleared up to October 2026." Use this for the state only; the main data has KWSP unpaid.
- **Not configured** (before 18 Nov 10:50). The four suggestions in section 4, then the toast "4 statutory accounts added."
- **AI.** Not configured, with no suggestion: "The chart of accounts has no account whose name looks like an EPF, SOCSO, EIS, SKBBK or PCB payable. Add them in Setup."

**Excel file.** "AISB Statutory payables check to 30-11-2026.xlsx" (FY view, January 2026 to November 2026). The pack month file is "AISB Statutory payables check to 31-10-2026.xlsx".

---

## 15. SQL page: checks, lines and the SQL books item

**"Checks against SQL's reports" card (AISB)**

- **GL Journal Oct-Nov.xlsx · 1 Oct to 17 Nov · read 18 Nov 2026 10:42**
  - "34 documents (22 new, 1 changed, 11 unchanged, 1 no longer in SQL), 78 lines."
- **GL Ledger.xlsx · 1 Oct to 12 Nov · read 18 Nov 2026 10:42**
  - Pill: `No differences`. "12 accounts agree with the lines."
  - The 12 accounts: 300-000, 310-000, 310-100, 320-000, 400-000, 420-000, 430-100, 430-200, 430-210, 430-300, 440-000, 500-F001.
- **Trial Balance Oct.xlsx · 1 Oct to 31 Oct · read 18 Nov 2026 10:42**
  - Pill: `No differences`.
  - "31 accounts agree with the lines for the month."
  - "15 profit and loss accounts agree with the lines dated 01/10/2026-31/10/2026."
  - "SQL's trial balance counts profit and loss from its From date (01/10/2026), so it moved a loss of 781,963.60 from earlier into retained earnings. No document carries that move."
- **No listing fetched · 2:** PV2611-012 · 14 Nov · 4,915.00; PV2611-015 · 17 Nov · 1,086.40. The listings read stop at 12 Nov.
- **No listing this app reads yet · 1:** CN2611-002 · 10 Nov · 2,800.00. It is checked by its lines and SQL's trial balance.
- **Missing from the journal · 1:** PV2611-008 · 7 Nov · 250.00 [No longer in SQL] [Deleted in SQL].

**Line pills on the SQL lists.** Every October and November document above is "2 lines", except:
- PV2610-005: 3 lines.
- JV2610-007: 6 lines.
- PV2611-007: 3 lines.
- JV2611-004: 3 lines.
- PV2611-015: 5 lines.
- PV2611-008: "No longer in SQL".
- PV2609-027 (30 Sep): "No lines" (dated before the journal).

**Changed in SQL card**
- "PV2611-003: changed in SQL from 1,163.20 to 1,136.20."
- "Linked to Electricity bill (October 2026), whose amount is RM 1,163.20."
- Checkbox: "Also change the payment's amount from RM 1,163.20 to RM 1,136.20".

**Imported files rows**
- "SQL exports fetched 20261112-1604 · … · 28 lines".
- "SQL exports fetched 20261118-1042 · … · 78 lines". Keep the board's entry counts.

**SQL books item: "SQL books agree with SQL Account"** (AISB only; due the 15th of the next month)

| Month | State | Note |
|---|---|---|
| **October 2026** | **Done** (auto, box ticked and locked) | "Done: SQL's journal covers October 2026, its documents agree with the listings and SQL's trial balance as at 31 Oct 2026 agrees with the books here" |
| **September 2026** | **Not done**, due 15 Oct (overdue) | "Fetch SQL's GL Journal of Transaction for the whole of September 2026 (from 1 Sep to 30 Sep 2026): no journal fetched covers the whole month." |
| July and August 2026 | Not asked | Before tracking (first month tracked September 2026). |
| AI | Not offered | Refusal if forced: "AI's books aren't kept in SQL Account, so SQL's books can't show this item done." |

---

## 16. MyInvois e-Invoices (AISB)

The copy is "MyInvois Sep-Nov.xlsx". It was saved 17 Nov 2026 16:05 and read 18 Nov 2026 10:42. It covers 3 Sep to 13 Nov and holds 18 e-Invoices: 11 issued, 1 self-billed and 6 received.

**Issued**

| SQL doc | Type | Buyer (TIN) | Amount | MyInvois status | Validated | Long ID | SQL pill after the read |
|---|---|---|---|---|---|---|---|
| IV2609-015 | Invoice | Agrinexus International (C3456789012) | 4,500.00 | Valid | 2026-09-03 10:02:11 | yes | Cancelled by CN2609-002 |
| CN2609-002 | Credit Note | Agrinexus International | 4,500.00 | Valid | 2026-09-10 09:40:05 | yes | Validated |
| IV2609-028 | Invoice | Agrinexus International | 1,200.00 | Valid | 2026-09-25 15:12:30 | yes | Validated (fill note "(was Submitted, not validated)") |
| IV2609-022 | Invoice | Agrinexus International | 4,500.00 | Valid | 2026-09-30 16:45:02 | **no** | Has UUID (no share link) |
| IV2609-030 | Invoice | Tenant (C4567890123) | 2,800.00 | Valid | 2026-09-30 16:50:18 | yes | Validated |
| IV2610-014 | Invoice | Office tenant (Unit 3A) (C5678901234) | 1,800.00 | Valid | 2026-10-01 11:19:44 | yes | Validated |
| IV2610-031 | Invoice | Tenant | 2,800.00 | Valid | 2026-10-31 17:02:40 | yes | Cancelled by CN2611-002 |
| IV2610-033 | Invoice | Agrinexus International | 4,500.00 | Valid | 2026-10-31 17:05:20 | yes | Validated |
| IV2611-002 | Invoice | Office tenant (Unit 3A) | 1,800.00 | Valid | 2026-11-02 10:11:09 | yes | Validated |
| IV2611-005 | Invoice | Office tenant (Unit 3A) | 245.60 | Submitted | — | — | Submitted, not validated |
| CN2611-002 | Credit Note | Tenant | 2,800.00 | Valid | 2026-11-10 09:31:27 | yes | Validated |

**Self-billed**
- PV2611-007, 6 Nov, "Cloud software subscription October".
- Supplier: Brightline Software Pte Ltd, TIN EI00000000030.
- **USD 100.00.** Valid, validated 2026-11-06 14:19:44.
- Lines: 900-600 at MYR 300.00 and 170.00. They print as USD 63.83 and USD 36.17.
- "Paid as MYR 470.00 by PV2611-007".

**Received**

| From | Their number | Amount | Issued | Matched SQL doc | How |
|---|---|---|---|---|---|
| Internet provider (400-T003) | — | 420.00 | 2026-11-03 | PV2611-004 | pill "By amount" |
| Water supplier (400-W001) | — | 84.30 | 2026-11-02 | PV2611-006 | by TIN and amount (no pill) |
| Payroll advisor (400-P004) | — | 312.00 | 2026-09-28 | PV2609-027 | by number (no pill) |
| Courier (400-C007) | — | 93.28 | 2026-10-20 | PV2611-009 | pill "Paid together" |
| Courier (400-C007) | — | 93.22 | 2026-10-27 | PV2611-009 | pill "Paid together" (93.28 + 93.22 = 186.50) |
| Green Pest Control | GPC/2611/0457 | 250.00 | 2026-11-12 | — | listed under "received but not found in SQL" |

- **Apply toast:** "Kept 18 MyInvois e-Invoices (18 new, 0 changed); 6 SQL documents filled in." The 6 are IV2609-028, PV2611-004, PV2611-006, PV2609-027, PV2611-009 and PV2611-007.
- **Share link:** IV2610-014's link is `https://myinvois.hasil.gov.my/<uuid>/share/<long id>`, labelled "MyInvois ↗".
- **Electricity:** PV2611-003 has no e-Invoice in this copy, on purpose. It carries the Changed-in-SQL story.

---

## 17. Printed invoices (AISB, US Letter, SQL's layout)

**Header on every page**
- AISB Sdn Bhd, (201901023456 (1331234-K)), TIN C 2345678901.
- Address, phone, email and website as in section 2.
- The logo.

**Footer**
- "All payments to be made to": Maybank current, Maybank, 5141 2345 4417, "Maybank Kota Damansara, 47810 Petaling Jaya, Selangor", SWIFT MBBEMYKL.
- "For AISB Sdn Bhd" under an empty signature box (no signature uploaded).

| Sample | Document | What it shows |
|---|---|---|
| customer-valid | IV2610-014, 1 Oct 2026 | Office tenant (Unit 3A), 3 address lines, Attn Accounts department, Terms 30 Days. One line, "Office rental October, Unit 3A", 1,800.00. Total 1,800.00. QR, UUID, "Validated on 01/10/2026 11:19:44". |
| credit-note | CN2609-002, 10 Sep 2026 | Agrinexus International, 4,500.00 in positive figures, no bank block. |
| not-validated | IV2611-005 | Utilities recharge November, Unit 3A, 245.60. Submitted, not validated: no QR. |
| no-long-id | IV2609-022 | Management fee September, 4,500.00. UUID without share link. |
| self-billed-usd | PV2611-007 | Supplier Brightline Software Pte Ltd, TIN EI00000000030; buyer AISB. Amount (USD) 63.83 + 36.17 = 100.00. "Paid as MYR 470.00 by PV2611-007". |
| settings-missing | any | No signature. Draw also a variant with no logo. |
| refused | a JV | "Not printed" page (a journal has no customer). |

**Print months**
- Customer invoices: Sep 2026, Oct 2026 and Nov 2026.
- Self-billed: Nov 2026.
- October is selected. Its zip is **"AISB Invoices 2026-10.zip"**, holding IV2610-014, IV2610-031 and IV2610-033. October has no self-billed zip.
- Cancelled e-Invoice (state-only): use the einvoice map's IV2610-009 (238.40) only as a drawn state. It is not in the books or the MyInvois copy above.

---

## 18. Next up (today 18 Nov 2026)

**Main.dc.html todo list, after stage 1.** Existing rows are kept unless shown otherwise.

| id | Company | Title | Meta | Due | Verb |
|---|---|---|---|---|---|
| consultant | AISB | Consultant fee not on the October statement | AISB · Payment · RM 3,200.00 | Overdue 31 Oct | Open payment |
| **statepf** (new, rule 14) | AISB | AISB: EPF (KWSP) for October 2026 wasn't paid by 15 Nov 2026. Check it on the Statutory tab. | AISB · Books › Statutory | Overdue 15 Nov | Go (opens Books › Statutory, From 2026-10-01, To 2026-11-18) |
| **kwspaisb** (new) | AISB | Pay KWSP for October | AISB · Statutory · RM 11,240.00 · legal deadline 15 Nov | Overdue 15 Nov | Open payment |
| kwsp | AI | Pay KWSP for October | AI · Statutory · RM 11,240.00 · legal deadline 15 Nov | Overdue 15 Nov | Open payment |
| **sqlbooks** (new, rule 10) | AISB | Sep AISB: SQL books agree with SQL Account | AISB · Checklist | Overdue 15 Oct | Show item |
| explain | AISB | Explain 5 bank lines on Maybank current | AISB · Bank statements | Today 18 Nov | Explain 5 lines |
| balance | both | Enter the bank balance for the November budget | Budget | Due 20 Nov | Enter balance |
| sql (reworded, rule 7) | AISB | Fetch SQL's Oct and Nov Payment Voucher listings on the SQL import page: 4 payments not recorded; 1 SQL entry not linked yet; 1 voucher changed in SQL (move the link on the SQL page) | AISB · SQL import | Due 21 Nov | Fetch from SQL exports |
| pack | AI | Build and file the October audit pack | AI · Audit pack | Due 30 Nov | Open audit pack |
| ecp22 | AISB | e-CP22 for the joiner starting 3 Nov | AISB · Joiner reminder | Due 3 Dec | Open checklist |
| backup | both | Last backup: 11 Nov, 7 days ago | Backup | — | Open backup |

**Rule 7 details**
- The 4 not recorded: Director fee (24 Oct), Telephone & internet (28 Oct), PCB (14 Nov) and PERKESO (17 Nov). None has a linked voucher.
- The entry not linked: PV2611-009.
- The changed voucher: PV2611-003.
- Take the exact noun for "4 payments" from `nextup._kinds`.

**The KWSP double row.** The October KWSP gives two rows for one unpaid KWSP, as the code does: the payment row and the rule 14 row. Flag it as a design question.

**Company.dc.html, AISB Next up.** Existing rows, plus:
- the rule 14 row;
- the September SQL books row;
- the reworded rule 7 row.

The Sidebar badges follow Main's list.

**Overview counts (Main D)**

| Company | Month | tasks | Change |
|---|---|---|---|
| AISB | October | **[18, 25]** (was [17, 24]) | the SQL books item, done |
| AISB | September | **[23, 25]** (was [23, 24]) | the SQL books item, not done |
| AI | | unchanged | |

---

## 19. Audit pack books pages (AISB, October 2026)

**Page "AISB Sdn Bhd - October 2026 - SQL books check"**
- "Done."
- "SQL's journal covers October 2026, its documents agree with the listings and SQL's trial balance as at 31 Oct 2026 agrees with the books here."
- The standing paragraph: "Whether SQL Account's books for the month agree with the mirror kept here: … SQL Account stays the books; nothing here changes them."

**Page "AISB Sdn Bhd - October 2026 - Statutory payables check"** (payroll month October; From = To = October, so the opening at 1 Oct is known)
- "1 statutory payable to look at: EPF (KWSP) for October 2026 wasn't paid by 15 Nov 2026."
- "- EPF (KWSP) (430-100): EPF (KWSP) for October 2026 wasn't paid by 15 Nov 2026."
- "- SOCSO (PERKESO) (430-200): SOCSO (PERKESO) for October 2026 paid in full, the last of it on 17 Nov 2026, after the due day 15 Nov 2026."
- "- EIS (SIP) (430-210): EIS (SIP) for October 2026 paid in full, the last of it on 17 Nov 2026, after the due day 15 Nov 2026."
- "- PCB (LHDN) (430-300): PCB (LHDN) for October 2026 paid in full."

**Page "AISB Sdn Bhd - October 2026 - Trial balance against SQL"**
- "Agrees with SQL's trial balance."
- "Compared with SQL's trial balance Trial Balance Oct.xlsx, 1 Oct 2026 to 31 Oct 2026."
- "Agrees with SQL's trial balance as at 31/10/2026: all 31 accounts compared."

**Before you print (AISB October)**
- No SQL books row, because the item is done.
- The existing rows stay as they are, including "Director fee: Paid 24 Oct, not recorded in SQL yet" (it is a JV in SQL).

**Auditor package Books/ folder**
- "AISB Trial balance to 31-10-2026.xlsx"
- "AISB General ledger to 31-10-2026.xlsx"
- "AISB Profit and loss to 31-10-2026.xlsx"
- "AISB Balance sheet at 31-10-2026.xlsx"
- "AISB Customers and suppliers to 31-10-2026.xlsx"
- "AISB Statutory payables check to 31-10-2026.xlsx"

AISB's `files` count is 118 + 6 = **124**.

**Check this pack** for "Audit pack AISB 2026-10 (20261114-1640).pdf". The 18 Nov reads came after it was built, so its state becomes **changed**. New group "SQL's books and the statutory accounts (its books pages)":
- Added · Ledger read, 3 rows: GL Journal Oct-Nov.xlsx, Trial Balance Oct.xlsx, GL Ledger.xlsx.
- Added · Ledger document, 22 rows. The first ones are PV2610-003, PV2610-005 and OR2610-006.
- Changed · Ledger document: PV2611-003.
- Changed · Ledger document: PV2611-008 (no longer in SQL).
- Added · Opening balance: 43 rows (31 from the trial balance and 12 from the ledger, at 1 Oct).
- Added · Statutory account, 4 rows: EPF (KWSP), SOCSO (PERKESO), EIS (SIP) and PCB (LHDN).
- The summary adds "74 to SQL's books or the statutory accounts".
- The chart accounts were added 13 Nov, before the pack, so they are not listed.
- Add the new "can't tell" line.

**AI pages**
- SQL books: "Not checked here.", then "This company's books aren't kept in SQL Account, so nothing here can show this done: tick it by hand."
- Statutory: "No statutory accounts are confirmed for this company yet, so nothing is checked."
- Trial balance: "Not checked.", then "This company's books are kept here, not in SQL, so there is no SQL trial balance to check against."

---

## 20. AI (Agrinexus International): Books

| What | Shows |
|---|---|
| Heading | `Books · AI` |
| Intro note | The not-in-SQL intro note |
| Period | Default 1 Jan 2026 to 18 Nov 2026 (today: nothing fetched) |
| Trial balance | No banner; "No opening balance or account line is kept for these dates yet." The code shows a green `Balances` pill (quirk 1); draw no pill (new_work). |
| Profit and loss, Balance sheet | Grey "Nothing to check" |
| Customers and suppliers | Grey "Nothing listed": "No customer balance is kept for these dates." Said once; no SQL hint. |
| Statutory | Not configured, no suggestion |
| Excel row 3 | "Books kept in this app: this company's books are not kept in SQL Account." |

**Company board (tracker only, not in books)**
- KWSP 11,240.00 unpaid.
- PERKESO 612.40 paid 14 Nov.

**Kept-in-SQL refusals**
- These belong to AISB, not AI. For example, an opening entered for AISB is refused with "This company's books are kept in SQL Account: its opening balances come only from SQL's reports."

---

## 21. State-only variants (allowed deviations, drawn as states, never the default)

- **Trial balance differences (Books (c), Bank `october-sql-differs`).**
  - Story: the 8 Oct SERVICE CHARGE 48.00 was booked in SQL as JV2610-012 (Dr 900-010 / Cr 310-000) after the journal was fetched. SQL's trial balance read later has:
    - 310-000 at 33,570.35 Dr;
    - 310-000's October movements at −55,648.00 against −55,600.00 here;
    - 900-010's October lines at 58.00 against 10.00 here.
  - Bank: "Differs from SQL's bank account 310-000 by RM 48.00: the book closing here is RM 33,618.35, SQL's balance on 31/10/2026 is RM 33,570.35".
- **Possibly out of date.** The same, with the journal fetched again 18/11/2026 at 11:05 holding JV2610-012.
- **OR2610-006 "Lines ≠ amount".** The lines move 44,950.00 against a listing of 45,000.00.
- **Not in chart.** 500-F001 before it was added to the chart.
- **Not classified.** 999-000 Suspense with 48.00 Dr.
- **Year-start column.** A hypothetical SQL trial balance from 01/12/2025.

---

## 22. Changes to existing boards' samples

Only the values books figures depend on are listed. **Mirror every change in the Dark and Mobile twins** named.

### Bank.dc.html (and DarkBank.dc.html)

| Where | Old | New | Why |
|---|---|---|---|
| `D.FIRST` | `'2026-07'` | `'2026-09'` | One first month tracked (Main, Budget, Company) |
| Comment above `data()` | "first tracked month July 2026" | "first tracked month September 2026" | |
| `MOV.cur['2026-10']` | `[47800, 103400]` | `[47848, 103448]` | CB2610-041 / CB2610-044 (48.00 each way) count by their bank lines. The closing is unchanged at 33,618.35. |
| `ST['cur:2026-10'].leftOut.invoices` | `2` | `3` | IV2610-014, IV2610-031 and IV2610-033 |
| `ST['cur:2026-09'].booksOnly[0].ref` | `'PV-0912'` | `'PV2609-020'` | SQL numbering (Company's September consultant voucher) |
| `ST['cur:2026-10'].booksOnly[0].ref` | `'PV-1033'` | `'PV2610-022'` | |
| `x.differ[0].ref` (october-split) | `'PV-1002'` | `'PV2610-003'` | |
| (stage 1 note) | — | "Not counted: 3 receipts or payments whose lines in SQL don't touch this bank account (paid from another account)." | OR2610-002, CB2610-050 and CB2610-051 are on 310-100 |

### BankReview.dc.html

| Where | Old | New |
|---|---|---|
| `aRobin` voucher | `v('PV-0912', '2026-09-29')` | `v('PV2609-020', '2026-09-29')` |
| `aRent` voucher | `v('OR-1021', '2026-10-02')` | `v('OR2610-001', '2026-10-02')` |
| `aCon` voucher | `v('PV-1002', '2026-10-06')` | `v('PV2610-003', '2026-10-06')` |
| `aKwsp` voucher | `v('PV-1015', '2026-10-15')` | `v('PV2610-005', '2026-10-15')` |
| `aKlinik` desc | `'Klinik Sehat · invoice 1043'` | `'Fund receipt'` |
| `aKlinik` voucher | `v('OR-1030', '2026-10-20')` | `v('OR2610-006', '2026-10-20')` |
| line 7 desc | `'IBG CR KLINIK SEHAT INV 1043'` | `'IBG CR AGRINEXUS INTERNATIONAL'` |
| `aSal` voucher | `v('PV-1024', '2026-10-24')` | `v('PV2610-014', '2026-10-24')` |
| `aDir` vouchers | `v('PV-1025', '2026-10-24')` | `[]` (SQL has journal JV2610-006, which can't be linked) |
| `aOffice` voucher | `v('PV-1031', '2026-10-30')` | `v('PV2610-021', '2026-10-30')` |
| `aStat` voucher | `v('PV-1033', '2026-10-30')` | `v('PV2610-022', '2026-10-30')` |

### Sql.dc.html

| Where | Old | New |
|---|---|---|
| `ROWS` x1 and `BASE` x1 (OR2610-006) amt | `'50,000.00'` | `'45,000.00'` |
| `PAYS` p9 (Fund receipt) a | `'50,000.00'` | `'45,000.00'` |
| `ROWS` x2 and `BASE` x2 no | `'PV2610-019'` | `'PV2610-005'` |
| x2 date and iso | `'28 Oct'`, `'2026-10-28'` | `'15 Oct'`, `'2026-10-15'` |
| x2 desc | `'KWSP October'` | `'KWSP September'` |
| `BASE` x2 month | `'October 2026'` | `'September 2026'` |
| `ROWS` r2 no | `'PV2610-022'` | `'PV2610-014'` |
| r2 date and iso | `'30 Oct'`, `'2026-10-30'` | `'24 Oct'`, `'2026-10-24'` |
| r2 amt | `'48,200.00'` | `'48,600.00'` |
| `PAYS` p2 (Salaries) a | `'48,200.00'` | `'48,600.00'` |
| `ROWS` r7 and `DOCS` JV2610-007 amt and total | `'48,200.00'`, `48200` | `'59,147.90'`, `59147.90` |
| `DOCS` (journals kept) | — | add `{ no: 'JV2610-006', kind: 'journal', iso: '2026-10-24', date: '24 Oct', desc: 'Director fee October', amt: '12,000.00', total: 12000, moved: -12000 }` |
| `ROWS` r6 (OR2611-002) sub | `'Code 500-R001'` | `'Code 300-U001'` |
| `sample(true)` journal paste | `320-000\tMaybank savings` | `310-100\tMaybank savings` |
| READ | 6 files | add `GL Journal Oct-Nov.xlsx · GL Journal of Transaction, 1 Oct to 17 Nov · 34 documents, 78 lines`, `Trial Balance Oct.xlsx · Trial Balance, 1 Oct to 31 Oct · 31 accounts`, `Supplier Invoice Listing Oct.xlsx · Supplier Invoice Listing, 1 Oct to 31 Oct · 3 new` and `MyInvois Sep-Nov.xlsx · MyInvois e-Invoices, 3 Sep to 13 Nov · 18 e-Invoices` |

### Company.dc.html (and DarkCompany.dc.html; MobileCompany.dc.html and MobilePayment.dc.html for the numbers)

| Where | Old | New |
|---|---|---|
| Everywhere | `'PV-1002'` | `'PV2610-003'` |
| Everywhere | `'IV-2610-031'` | `'IV2610-031'` |
| Everywhere | `'CN-2611-002'` | `'CN2611-002'` |
| Everywhere | `'OR 2610-07'` | `'OR2611-001'` (in its file name too: `'OR2611-001 Rental.pdf'`) |
| Sept KWSP `S(...)`: paid | `'2026-10-14'` | `'2026-10-15'` |
| Sept KWSP `S(...)`: amount | `11240` | `11180` |
| Sept KWSP `S(...)`: bank text | `'FPX KWSP \| 1410552'` | `'KWSP SEPT CONTRIBUTION \| 1510552'` |
| Sept KWSP `S(...)`: file time, here and in the `stat` task's kwsp slot | `'14 Oct, 10:12'` | `'15 Oct, 10:12'` |
| Sept PCB `S(...)`: paid | `'2026-10-14'` | `'2026-09-30'` |
| Sept PCB `S(...)`: voucher | `'PV2610-006'` | `'PV2609-024'` |
| Sept PCB `S(...)`: bank text | `'FPX LHDN \| 1410561'` | `'FPX LHDN \| 3009561'` |
| Sept PCB `S(...)`: file time, here and in the cp39 slot | `'14 Oct, 10:20'` | `'30 Sep, 10:20'` |
| Sept Electricity `S(...)`: paid | `'2026-10-04'` | `'2026-09-30'` |
| Sept Electricity `S(...)`: voucher | `'PV2610-002'` | `'PV2609-025'` |
| Sept Electricity `S(...)`: bank text | `'IBG DR ELECTRICITY BILL \| 0410227'` | `'IBG DR ELECTRICITY BILL \| 3009227'` |
| Sept Electricity `S(...)`: file time | `'4 Oct, 11:20'` | `'30 Sep, 11:20'` |
| AISB October `tasks` | — | add after `recon`: `{ k: 'sqlbooks', title: 'SQL books agree with SQL Account', detail: <BOOKS_DETAIL>, due: '2026-11-15', auto: true, done0: true, why: "Done: SQL's journal covers October 2026, its documents agree with the listings and SQL's trial balance as at 31 Oct 2026 agrees with the books here" }` |
| AISB September `tasks` | — | add after `recon`: `{ k: 'sqlbooks', title: 'SQL books agree with SQL Account', detail: <BOOKS_DETAIL>, due: '2026-10-15', auto: true, bad: true, why: "Fetch SQL's GL Journal of Transaction for the whole of September 2026 (from 1 Sep to 30 Sep 2026): no journal fetched covers the whole month.", lacking: <same> }` |
| AISB `next` | `'Record {nosql} paid payments in SQL Account'` | the rule 7 text in section 18 |
| AISB `next` | — | add the rule 14 row and the September SQL books row (section 18) |
| Claims hint | "Paste the latest SQL listing to record it." | "Fetch SQL's latest listings on the SQL import page to record it." |

### Main.dc.html (and DarkOverview.dc.html, MobileOverview.dc.html)

| Where | Old | New |
|---|---|---|
| `D.aisb.oct.tasks` | `[17, 24]` | `[18, 25]` |
| `D.aisb.sep.tasks` | `[23, 24]` | `[23, 25]` |
| `todo` | — | add `statepf`, `kwspaisb` and `sqlbooks` (section 18) |
| `todo` sql title | `'Record 4 paid payments in SQL Account'` | the rule 7 text (section 18) |
| `first` | `'September 2026'` | unchanged (now agrees with Bank and SetupCompanies) |

### SetupCompanies.dc.html

| Where | Old | New |
|---|---|---|
| AISB `first_month` | `'2025-01'` | `'2026-09'` |
| AI `first_month` | `'2025-03'` | `'2026-09'` |
| AISB `reg_no` | `'201901023456 (1331234-K)'` | `'201901023456'`, plus `old_reg_no: '1331234-K'` |
| AI `reg_no` | `'202001045678 (1378901-W)'` | `'202001045678'`, plus `old_reg_no: '1378901-W'` |
| AISB new fields | — | address, phone, email, website, invoice account, sign label, logo and printed names, as in section 2 |
| `fy_start` blank option | `'January (not set)'` | `'—'` |

### SetupChart.dc.html

- Add the 14 accounts marked **New** in section 3, with their groups, types and parents: 330-000, 430-210, 440-000, 500-F001, 510-000, 610-000, 650-000, 900-010, 900-110, 900-120, 900-130, 900-700, 900-800 and 900-900.
- Keep everything else.

### SetupParties.dc.html

- Add 300-U001 "Office tenant (Unit 3A)": customer, AISB, gl 300-000.
- Give 300-T001 and 300-U001 the address, Attention, Phone and Terms values in section 4.
- Keep 300-A001 out of Setup.

### Setup.dc.html (Bank accounts)

- Maybank current: bank address "Maybank Kota Damansara, 47810 Petaling Jaya, Selangor"; SWIFT "MBBEMYKL"; Used by includes "1 company's invoices".

### SetupChecklist.dc.html

- AISB items: add "SQL books agree with SQL Account" (due day 15 of the next month, Done when `books`, no documents).
- AI: none.

### AuditPack.dc.html

| Where | Old | New |
|---|---|---|
| AISB `toPrint` | `'PV-1002, PV2610-014 and PV2610-021'` | `'PV2610-003, PV2610-014 and PV2610-021'` |
| AISB `files` | `118` | `124` |
| `LABEL` | 3 groups | add `books: "SQL's books and the statutory accounts (its books pages)"` |
| pack `e` state | `'unchanged'` | `'changed'`, with the books rows in section 19 |

### CommandPalette.dc.html

| Old | New |
|---|---|
| `'RM 1,097.40 · PV2610-002'` | `'RM 1,097.40 · PV2609-025'` |

### Budget.dc.html

No change. KWSP 11,240.00, PCB 4,915.00, PERKESO 1,086.40 and Electricity 1,163.20 (the tracker amount) already agree.

---

## 23. Conflicts resolved (what was decided and why)

| Conflict | Decision | Why it needs the fewest changes |
|---|---|---|
| OR2610-006 45,000.00 or 50,000.00 | **45,000.00**, Fund received, Cr 500-F001 | Bank, BankReview and Company money-in totals (47,800 / 103,400, closing 33,618.35) are fixed by statement balances. Only the Sql board's three 50,000.00 values change. BankReview's description is renamed so the receipt is the fund the books, SQL and SQL-bank maps already use. |
| First month tracked: 2025-01 / 2025-03 (Setup), 2026-07 (Bank) or September 2026 (Main, Budget) | **September 2026** for AISB and AI | One Bank value changes. Main, Company and Budget already assume September. July 2026 would need Main's before-tracking card logic rewritten. |
| How far SQL was fetched | Listings to 12 Nov; GL Journal of Transaction **1 Oct to 17 Nov**; trial balance as at **31 Oct**; all read 18 Nov 10:42 | The Sql board's existing listings and fetch time stay. The journal must reach 17 Nov for the October PCB (14 Nov) and PERKESO (17 Nov) payments the Company board shows. |
| Which statutory payments are paid | September KWSP 11,180.00 on 15 Oct (bank line); September PCB and PERKESO on 30 Sep; October PCB 14 Nov; October PERKESO 17 Nov; **October KWSP unpaid** | Keeps the Company board's October story and the October bank statement. Company's September KWSP moves to the bank's 11,180.00 on 15 Oct. Its September PCB and electricity move to 30 Sep, because the October statement has no room for them. |
| PV2610-019 "KWSP October 11,180.00 on 28 Oct", linked | It becomes **PV2610-005 KWSP September, 15 Oct**, linked to September | It contradicted October KWSP being unpaid, and the October statement has no 28 Oct line. |
| Salaries: PV2610-014 48,600.00 on 24 Oct (Company, Bank) or PV2610-022 48,200.00 on 30 Oct (Sql) | **PV2610-014, 48,600.00, 24 Oct**, plus payroll journal **JV2610-007, 59,147.90** crediting the payables | Matches the statement and the Company checklist chip. The journal is how the statutory check finds what was withheld. |
| Director fee: in the SQL cash book (Bank) or "not recorded in SQL yet" (Company, AuditPack, Main) | **JV2610-006**, a journal on 310-000 | It counts in the bank book (Bank stays), and a journal can't be linked to a payment, so "not recorded in SQL" stays true. |
| Voucher numbering: PV-1002 style (Bank boards) or PV2610-014 style | **SQL style** `PV2610-003`, `OR2610-001`, `IV2610-031`, `OR2611-001` | One ledger can't show two series; most boards already use SQL style. |
| The books map's invented October documents (rental 9,500, transfer 8,000, directors fee 30,000…) | Replaced by the documents behind BankReview's payments | Bank totals and the closing are unchanged. |
| Parties map's customer figures (10,850 → 15,150) or books map's (2,800) | **8,500 → 14,800** (section 13) | Only 1 Oct openings exist, so customer codes start at 0 and the control account holds the opening. |
| Electricity October: 1,163.20, 1,136.20 or 1,150 | TNB bill **PI2610-012 1,136.20**; PV2611-003 version 1 1,163.20, version 2 1,136.20; tracker 1,163.20 | Keeps the Sql board's Changed-in-SQL story. |
| 900-010 or 900-700 for bank charges | **900-010 Bank charges** (Sql's code). 900-700 becomes Contract works. | |
| 900-120: PERKESO employer (statutory map) or electricity (sql-bank map) | **PERKESO - employer**. Electricity is 400-E012 / 900-400. | |
| Self-billed PV2610-018 on 27 Oct (470.00 from the bank) | **PV2611-007, 6 Nov** | The October statement has no room for it. |
| SKBBK in PERKESO | Not used; PERKESO = SOCSO + EIS = 1,086.40 | Company calls the payment "PERKESO (SOCSO & EIS)". |

---

## 24. Arithmetic checks (all must hold)

**October trial balance**
- 1,234,938.60 Dr = 1,234,938.60 Cr (openings).
- 238,411.50 = 238,411.50 (October movements).
- 1,306,624.10 = 1,306,624.10 (closings).

**310-000**
- 89,218.35 + 47,848.00 − 103,448.00 = **33,618.35** = the Bank board's book closing = SQL's balance on 31/10/2026.
- The Bank board's 47,800.00 / 103,400.00 + 48.00 each way.

**310-100**
- 50,000.00 + 8,021.40 − 10.00 = **58,011.40** = Bank `sav:2026-10`.

**Payroll and statutory**
- Payroll journal: 48,600.00 + 5,346.00 + 205.00 + 81.90 + 4,915.00 = 59,147.90.
- KWSP October: 5,346.00 + 5,894.00 = 11,240.00 (Company, Budget, Main).
- KWSP September: 5,320.00 + 5,860.00 = 11,180.00 (bank line 15 Oct).
- PERKESO: 205.00 + 717.60 + 81.90 + 81.90 = 1,086.40 (Company, Budget).

**Profit and loss and balance sheet**
- P&L October: 9,100.00 + 21.40 − 112,974.10 = −103,852.70.
- P&L year to date: 87,700.00 + 190.00 − 973,706.30 = −885,816.30 = −781,963.60 − 103,852.70.
- Balance sheet assets: 18,500.00 + 113,929.75 = 132,429.75.
- Liabilities: 23,734.10.
- Net assets: 108,695.65.
- Equity: 1,195,000.00 − 200,488.05 − 885,816.30 = 108,695.65.

**SQL's retained earnings**
- 200,488.05 + 781,963.60 = 982,451.65 Dr (printed at 31 Oct).

**Customers**
- 8,500.00 + 9,100.00 − 2,800.00 = 14,800.00 = 300-000 closing.
- Ageing: 6,300.00 + 8,500.00 = 14,800.00.

**Suppliers**
- 850.00 + 10,836.20 − 6,500.00 = 5,186.20 = 400-000 closing.
- Ageing: 4,336.20 + 850.00 = 5,186.20.

**Statutory balances at the due date (end of 15 Nov)**
- 430-100: 5,320.00 − 5,320.00 + 5,346.00 = 5,346.00 owed.
- 430-200: 205.00 owed (paid 17 Nov).
- 430-210: 81.90 owed.
- 430-300: 4,915.00 − 4,915.00 = nil.

**Counts**
- Journal read 18 Nov: 22 new + 1 changed + 11 unchanged = 34 current documents (20 October + 14 November), plus 1 no longer in SQL.
- Lines: 45 (October) + 33 (November) = 78.

**310-000 at 17 Nov**
- 33,618.35 + 4,600.00 − 33,299.40 = 4,918.95 Dr.

---

## 25. Left as they are (conflicts that touch no Books figure)

These are noted so nobody "fixes" them into the books by mistake.

- **Company September and the Bank September statement disagree.** Company pays salaries, director fee and rental in September from Maybank current. The Bank statement's September out is 15,581.65. September is before the journal kept here, so no Books page shows it.
- **The contractor's bank lines.** Company shows 6 Oct −10,000.00 and 20 Oct −8,000.00. BankReview shows 6 Oct −10,000.00 and −14,000.00. AuditPack says part paid 10,000.00. The SQL voucher is 24,000.00 either way.
- **The October telephone bill.** Company: paid 28 Oct from a bank line of 398.60, which is not on the October statement. SQL: PV2611-004, 420.00 on 5 Nov.
- **Payments missing from the Company October list.** It doesn't list BankReview's Fund receipt, Stationery Mart or Insurance renewal.
- **The Sql board's fetch-preview counts** ("6 new, 1 already imported"…) and its "new" PV2610-021 against Company's link history of 12 Nov. These describe that board's own preview.
- **Company electricity (October).** It shows no SQL ref, but the Sql board links PV2611-003.
