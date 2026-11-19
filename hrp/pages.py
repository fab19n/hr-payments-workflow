"""Which pages of the menu a company uses, by how its books are kept. Pure data: page keys are the new menu's places
(area/page); labels, glyphs and groups belong to the front end. A company's kind comes from its Kept in SQL Account
setting (entities.uses_sql). Nothing here names a company."""

# Every page key of the menu, in menu order.
ALL = (
    "overview",
    "hr/staff", "hr/leave", "hr/claims", "hr/payroll",
    "payments/approvals", "payments/to-pay", "payments/register", "payments/checklist", "payments/budget",
    "payments/recurring",
    "accounting/bank", "accounting/sql", "accounting/einvoices", "accounting/books", "accounting/parties",
    "accounting/statutory", "accounting/sales", "accounting/purchases", "accounting/journals", "accounting/period-close",
    "admin/setup", "admin/audit-pack", "admin/audit-trail", "admin/backup",
)

# Pages only one kind uses: the SQL import is for a company kept in SQL Account; the four placeholders of the Kept here
# group (until the books are kept here) are for a company kept here.
SQL_ONLY = ("accounting/sql",)
HERE_ONLY = ("accounting/sales", "accounting/purchases", "accounting/journals", "accounting/period-close")

KINDS = {"sql": "Kept in SQL Account", "here": "Kept here"}


def kind_of(uses_sql):
    """'sql' for a company kept in SQL Account, else 'here'."""
    return "sql" if uses_sql else "here"


def pages_for(kind):
    """The page keys a company of this kind uses, in menu order."""
    skip = HERE_ONLY if kind == "sql" else SQL_ONLY
    return [p for p in ALL if p not in skip]
