"""Business rules: document types, what each kind of payment needs on file, and the monthly checklist.

Dates are written as (month_offset, day): offset 0 = the payroll month itself, 1 = the following month.
"""

DOC_TYPES = {
    "pv": "Payment Voucher (SQL)",
    "jv": "Journal Voucher (SQL)",
    "or": "Official Receipt (SQL)",
    "invoice": "Invoice / bill",
    "bank": "Bank receipt / transfer slip",
    "einvoice": "e-Invoice (MyInvois)",
    "portal": "Acknowledgement / portal bill",
    "claim": "Claim form & receipts",
    "approval": "Approval (signed / email)",
    "payroll": "Payroll summary / payslips",
    "statement": "Bank statement",
    "recon": "Bank reconciliation",
    "sqlexport": "SQL Account export",
    "other": "Other",
}

# A required document counted, one and several: 1 invoice, 8 invoices.
DOC_COUNTED = {"pv": ("payment voucher", "payment vouchers"), "jv": ("journal voucher", "journal vouchers"),
               "or": ("official receipt", "official receipts"), "invoice": ("invoice", "invoices"),
               "bank": ("bank receipt", "bank receipts"), "einvoice": ("e-Invoice", "e-Invoices"),
               "portal": ("acknowledgement", "acknowledgements"), "claim": ("claim form", "claim forms"),
               "approval": ("approval", "approvals"), "payroll": ("payroll summary", "payroll summaries")}

# Filing order inside an audit pack.
DOC_ORDER = ["pv", "jv", "or", "approval", "invoice", "claim", "payroll", "portal", "bank", "einvoice", "other"]

CATEGORIES = {
    "salary": "Salary",
    "director": "Director allowance",
    "consultant": "Consultant fee",
    "statutory": "Statutory (KWSP / PERKESO / LHDN)",
    "utility": "Utility / telco",
    "rental": "Rental",
    "claim": "Staff claim",
    "claim_overseas": "Staff claim - overseas service (self-billed e-Invoice)",
    "transfer": "Inter-company transfer",
    "receipt": "Money received",
    "other": "Other payment",
}

# Documents a payment must have before it counts as complete. "pv" is only demanded for
# entities that keep their books in SQL Account (see entities.uses_sql).
REQUIRED_DOCS = {
    "salary": ["pv", "bank"],
    "director": ["pv", "bank"],
    "consultant": ["invoice", "pv", "bank"],
    "statutory": ["portal", "pv", "bank"],
    "utility": ["invoice", "pv", "bank"],
    "rental": ["invoice", "pv", "bank"],
    "claim": ["claim", "approval", "pv", "bank"],
    # Overseas providers (Claude, Google) don't issue Malaysian e-Invoices, so a self-billed one is issued in SQL.
    "claim_overseas": ["claim", "approval", "pv", "bank", "einvoice"],
    "transfer": ["approval", "bank"],
    "receipt": ["invoice", "or"],
    "other": ["invoice", "pv", "bank"],
}
SQL_ONLY = {"pv", "jv", "or"}

# The SQL voucher types that stand for a required document once the voucher is linked: it is printed from SQL.
SQL_VOUCHERS = {"PV": "pv", "OR": "or", "JV": "jv", "JE": "jv"}

# Legal deadline per payment type, as (month_offset, day) from the payroll month: KWSP, PERKESO (SOCSO, EIS, SKBBK)
# and LHDN PCB are due by the 15th of the following month.
LEGAL_DUE = {"statutory": (1, 15)}


def required_docs(category, uses_sql):
    docs = REQUIRED_DOCS.get(category, REQUIRED_DOCS["other"])
    return [d for d in docs if uses_sql or d not in SQL_ONLY]


# Monthly checklist per entity code. Each task can also ask for documents (attached to the task itself).
CHECKLIST = {
    "AISB": [
        ("inputs", (0, 18), "Collect payroll changes",
         "Joiners, leavers, unpaid leave, allowance changes. Update the leave record for the month.", []),
        ("budget", (0, 20), "Prepare budget and fund requisition",
         "Payroll, consultant fees, claims, office rental, copier, TNB, Unifi. Send the requisition for approval.", ["approval"]),
        ("payroll-calc", (0, 22), "Calculate payroll, KWSP, SOCSO, EIS, SKBBK and PCB",
         "Net pay per employee and the employer contributions for the month.", ["payroll"]),
        ("payroll-approve", (0, 24), "Payroll approved",
         "Approval of the payroll summary before the bank transfer.", ["approval"]),
        ("fund-received", (0, 24), "Fund received from Agrinexus International: issue OR and e-Invoice",
         "SQL Sales tab: e-Invoice to Agrinexus International for monthly operating expenses. Done once the receipt has "
         "its OR and the e-Invoice is validated.", []),
        ("payroll-jv", (0, 28), "Salary PVs in SQL (one per person)",
         "A Payment Voucher in SQL for each salary and the director allowance, then send the payslips.", []),
        ("claims", (1, 2), "Staff claims compiled and approved",
         "Compiled and approved, then paid. Add each claim as a payment.", []),
        ("kwsp", (1, 3), "KWSP: submit contribution data",
         "i-Akaun: contribution month = next month, wages month = payroll month. File the acknowledgement on the KWSP "
         "payment.", []),
        ("perkeso", (1, 3), "PERKESO: submit SOCSO, EIS and SKBBK",
         "ASSIST portal. SOCSO, EIS and SKBBK (Lindung 24 Jam) are separate lines. File the acknowledgement on each "
         "payment.", []),
        ("epcb", (1, 3), "LHDN: submit PCB (e-PCB Plus)",
         "Get the payment reference before paying. File the acknowledgement on the PCB payment.", []),
        ("einv-rental", (1, 6), "e-Invoice to the office tenant for rental",
         "SQL Sales tab. Tick it by hand: the app can't tell which month's rent an e-Invoice is for.", ["einvoice"]),
        ("einv-selfbilled", (1, 10), "Self-billed e-Invoices for overseas providers",
         "Claude, Google and other overseas services, via the SQL Cash Book tab. Done once each overseas claim of the "
         "month has its e-Invoice.", []),
        ("statement", (1, 5), "Download bank statement and import it here", "", []),
        ("recon", (1, 10), "Bank reconciliation", "Every statement line matched to a payment or receipt.", ["recon"]),
        ("file", (1, 10), "Print and file the audit pack", "Generate the pack from the Audit pack screen.", []),
    ],
    "AI": [
        ("budget", (0, 20), "Prepare Agrinexus International budget", "Consultant fees and the AISB fund requisition.", ["approval"]),
        ("invoices", (0, 26), "Issue invoices to customers", "", ["invoice"]),
        ("statement", (1, 5), "Download MBB statements (CA and FCA) and import them here", "", []),
        ("records", (1, 8), "Update MBB bank records", "Record every payment and receipt for the month.", []),
        ("file", (1, 10), "Print and file the audit pack", "", []),
    ],
}
# The checklist items whose wording or documents changed since the first release; the update gives the items already
# set up the wording and documents above.
CHECKLIST_CHANGED = {"fund-received", "payroll-jv", "kwsp", "perkeso", "epcb", "einv-rental", "einv-selfbilled"}

# Checklist items the month's payments show done (db.task_status), once each payment they cover has the documents
# named (uploaded, or shown by SQL or the bank). Which payments: types, money in or out, and words (whole words) in the
# description or payee. on_item: documents that may be filed on the checklist item itself instead: an upload there
# stands for every payment (the acknowledgement the item used to ask for), and the item's validated e-Invoices for its
# month stand for payments up to what they add up to (the e-Invoice to Agrinexus International is an SQL sales invoice
# filed on the item). paid: a paid one counts too, as statutory data is submitted before it can be paid. none: done
# with no such payment once the month's bank statements are imported, saying this. name: what one and several are
# called.
TASK_PAYMENTS = {
    "payroll-jv": {"categories": ("salary", "director"), "docs": ["pv"],
                   "name": ("salary or director payment", "salary and director payments")},
    "fund-received": {"direction": "in", "words": ("AGRINEXUS INTERNATIONAL",), "docs": ["or", "einvoice"],
                      "on_item": ["einvoice"],
                      "name": ("receipt from Agrinexus International", "receipts from Agrinexus International")},
    "kwsp": {"categories": ("statutory",), "words": ("KWSP", "KUMPULAN WANG"), "docs": ["portal"], "on_item": ["portal"],
             "paid": True, "name": ("KWSP payment", "KWSP payments")},
    "perkeso": {"categories": ("statutory",), "words": ("PERKESO", "SOCSO", "EIS", "SIP", "SKBBK"), "docs": ["portal"],
                "on_item": ["portal"], "paid": True, "name": ("PERKESO payment", "PERKESO payments")},
    "epcb": {"categories": ("statutory",), "words": ("PCB", "POTONGAN CUKAI"), "docs": ["portal"],
             "on_item": ["portal"], "paid": True, "name": ("PCB payment", "PCB payments")},
    "einv-selfbilled": {"categories": ("claim_overseas",), "docs": ["einvoice"], "none": "no overseas claims this month",
                        "name": ("overseas claim", "overseas claims")},
}
# Checklist items the bank statements show done: every account's statement for the month imported, and for True also
# balancing with no line left to explain.
TASK_STATEMENTS = {"statement": False, "recon": True, "records": True}
# The checklist item an audit pack built since the month's documents last changed shows done.
TASK_PACK = "file"

# One-off reminders from a salary's start date (joiner) or last day (leaver), for a company that runs Malaysian
# payroll: (joiner or leaver, key, days from that date, monthly salary it must be over or None, title, detail,
# documents). Each goes in the month being worked on when it falls due (db.sync_reminders). Reminders to check, not
# legal advice.
PEOPLE_TASKS = [
    ("joiner", "ecp22", 30, None, "e-CP22 to LHDN for {name}",
     "Tell LHDN about the new employee (MyTax, e-CP22) within 30 days of the start date, {date}.", ["portal"]),
    ("joiner", "perkeso", 30, None, "PERKESO registration for {name}",
     "Register the employee for SOCSO and EIS on the ASSIST portal within 30 days of the start date, {date}.", ["portal"]),
    ("joiner", "kwsp", 7, None, "KWSP registration for {name}",
     "Register the employee with KWSP within 7 days of the start date, {date}, unless they already have a member "
     "number.", ["portal"]),
    ("joiner", "stamp", 30, 3000, "Stamp {name}'s appointment letter",
     "Stamp duty on the appointment letter (LHDN e-Duti Setem) within 30 days, as the monthly salary is over RM 3,000.",
     ["portal"]),
    ("leaver", "cp22a", -30, None, "CP22A to LHDN for {name}",
     "Tell LHDN at least 30 days before the last day, {date}. Not needed when the pay is below the PCB threshold, or "
     "when PCB is deducted and the employee isn't retiring or leaving Malaysia. For an employee leaving Malaysia, check "
     "whether a CP21 is due instead.", ["portal"]),
]
