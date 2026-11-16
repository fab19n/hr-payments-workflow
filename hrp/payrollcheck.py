"""The payroll workbook check: the month's hand-made Excel payroll (one sheet per person, the payslip, and a Summary
sheet) is uploaded before paying, and this reads it and says in plain words what to fix, what to check and what to
note, with the sheet and the cell each time.

Everything is found by its headings, never by fixed cells, as one sheet can be shifted by a row and the columns vary.
The workbook is read twice: once for the formulas, once for the values Excel saved with them.

What it checks:
- the Summary against the payslips: each row's figures equal its person's pay row, every link points at that
  person's own sheet and at the pay row (not a row of the monthly table), figures typed where the rest are linked,
  links to another workbook, and the Summary's own sums and totals;
- each payslip: the pay row adds up, the year-to-date box agrees with the monthly table (and is built so that it
  will still agree next month), the sheet's own check cells, this month's row of the table, and the sheet's month;
- money with more than 2 decimals where a payment amount is formed;
- EPF, SOCSO, EIS and SKBBK (Lindung 24 Jam) against the rates and bands in RATES. PCB amounts are not checked: they
  need each person's tax details, which payroll will hold once it is built into this app.

The workbook is uploaded as the month's payroll document (doc type "payroll") and each check is kept in
payroll_checks, so a corrected file checked again leaves the earlier results listed as earlier versions. A report
never holds an IC number in full: only the last 4 characters are kept (mask).
"""
import calendar
import io
import json
import posixpath
import re
import unicodedata
import warnings
import zipfile
from collections import Counter
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from xml.etree import ElementTree as ET

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from . import audit, db

MAX_BYTES = 20 * 1024 * 1024  # the largest workbook taken (the real one is under 1 MB)
MAX_UNZIPPED = 300 * 1024 * 1024  # what its parts may add up to once unpacked

SEVERITY = {"fix": "Fix before paying", "check": "Check", "note": "Note"}
ORDER = ("fix", "check", "note")

# The statutory rates and wage bands the check uses: as at Nov 2026, check each year (KWSP's Third Schedule, PERKESO's
# contribution tables for SOCSO, EIS and SKBBK). "from": the first payroll month they are used for; an earlier month's
# figures are not checked against them. Rates are percentages; amounts in sen.
RATES = {
    "as_at": "Nov 2026",
    # EPF: the contribution is the rate times the UPPER limit of the wage band, rounded up to the next ringgit. Wages
    # up to RM 5,000 go in RM 20 bands, above it in RM 100 bands, above RM 20,000 the wage itself. Employer 13% on
    # wages up to RM 5,000, 12% above. Aged 60 and over (Malaysian citizens): employee 0%, employer 4%. EPF wages for
    # this company are the basic pay (the transport allowance isn't EPF wages).
    "epf": {"from": "2024-10", "employee": 11, "employer_low": 13, "employer_high": 12, "low_upto": 500000,
            "employee_60": 0, "employer_60": 4, "band_low": 2000, "band_high": 10000, "exact_above": 2000000},
    # SOCSO first category: employer 1.75%, employee 0.5% of the MIDPOINT of the RM 100 wage band, wages above
    # RM 6,000 counted as the RM 5,900.01-6,000 band. Second category (employment injury only): employer 1.25%,
    # employee nothing. The official table rounds to 5 sen and not always the same way, so 5 sen either way passes.
    # Wages up to RM 400 have smaller bands, not held here.
    "socso": {"from": "2024-10", "employer": Decimal("1.75"), "employee": Decimal("0.5"), "second_employer": Decimal("1.25"),
              "band": 10000, "ceiling": 600000, "smallest": 40000, "tolerance": 5},
    # EIS: 0.2% employer and 0.2% employee of the same band midpoint, same ceiling, for workers aged 18 to 60. Not
    # for workers aged 60 and over, and a worker aged 57 or over with no EIS contributions before 57 is exempt
    # (PERKESO, https://www.perkeso.gov.my/en/our-services/employer-employee/contributions.html).
    "eis": {"from": "2024-10", "employer": Decimal("0.2"), "employee": Decimal("0.2"), "age_limit": 60,
            "exempt_from": 57, "min_age": 18},
    # SKBBK (Lindung 24 Jam): employee only, 0.75% of the same band midpoint, rounded as SOCSO; from the June 2026
    # contribution month, no age limit, voluntary for locals (opt-out) and mandatory for foreign workers. Rises to
    # 1.00% from Jun 2028 and 1.25% from Jun 2031 (PERKESO's LINDUNG 24 Jam FAQ, Aug 2026,
    # https://www.perkeso.gov.my/images/lindung/lindung-24-jam/130826-FAQ%20_LINDUNG24Jam_EN_version.pdf).
    "skbbk": {"from": "2026-06", "employee": Decimal("0.75")},
}

FIGURES = ("basic", "epf", "socso", "eis", "skbbk", "pcb", "total_ded", "allowance", "net", "er_epf", "er_socso", "er_eis")
LABEL = {"basic": "Basic salary", "epf": "EPF", "socso": "SOCSO", "eis": "EIS", "skbbk": "SKBBK", "pcb": "PCB",
         "total_ded": "Total deduction", "allowance": "Allowance", "net": "Net pay", "er_epf": "Employer EPF",
         "er_socso": "Employer SOCSO", "er_eis": "Employer EIS", "insurance": "Insurance", "pay_total": "TOTAL to pay",
         "tot_epf": "KWSP total", "tot_socso": "SOCSO total", "tot_skbbk": "SKBBK total", "tot_eis": "EIS total",
         "name": "Name", "nric": "NRIC"}
# What the Summary's own columns are called on it (shown in findings), as its headings name them.
SUMMARY_LABEL = {"basic": "Basic", "epf": "KWSP", "socso": "Socso", "eis": "EIS", "skbbk": "SKBBK", "pcb": "e-PCB",
                 "total_ded": "Total deduction", "net": "Net", "insurance": "Insurance Premium",
                 "allowance": "Transport Allowance", "pay_total": "TOTAL", "er_epf": "Employer KWSP",
                 "er_socso": "Employer Socso", "er_eis": "Employer EIS", "tot_epf": "Total KWSP",
                 "tot_socso": "Total SOCSO", "tot_skbbk": "Total SKBBK", "tot_eis": "Total EIS",
                 "name": "NAME", "nric": "NRIC NO."}
# The Summary columns linked to a payslip's pay row (Summary key -> payslip key).
LINKED = {"basic": "basic", "epf": "epf", "socso": "socso", "eis": "eis", "skbbk": "skbbk", "pcb": "pcb",
          "insurance": "insurance", "allowance": "allowance", "er_epf": "er_epf", "er_socso": "er_socso",
          "er_eis": "er_eis"}
# The Summary columns it works out itself: key -> (what is added, what is taken off).
SUMS = {"total_ded": (("epf", "socso", "eis", "skbbk", "pcb"), ()), "net": (("basic",), ("total_ded",)),
        "pay_total": (("net", "insurance", "allowance"), ()), "tot_epf": (("er_epf", "epf"), ()),
        "tot_socso": (("er_socso", "socso"), ()), "tot_skbbk": (("skbbk",), ()), "tot_eis": (("er_eis", "eis"), ())}
SUMS_WORDS = {"total_ded": "KWSP + Socso + EIS + SKBBK + e-PCB", "net": "Basic - Total deduction",
              "pay_total": "Net + Insurance Premium + Transport Allowance", "tot_epf": "Employer KWSP + KWSP",
              "tot_socso": "Employer Socso + Socso", "tot_skbbk": "SKBBK", "tot_eis": "Employer EIS + EIS"}
# Who each amount of the month is paid to, from the Summary (key, authority).
AUTHORITIES = (("tot_epf", "KWSP"), ("tot_socso", "SOCSO"), ("tot_eis", "EIS"), ("tot_skbbk", "SKBBK"), ("pcb", "PCB"))
YTD_KEYS = (("grosspay", "basic"), ("allowance", "allowance"), ("netpay", "net"), ("employeeepf", "epf"),
            ("employeesocso", "socso"), ("employeeeis", "eis"), ("employeeskbbk", "skbbk"), ("employeepcb", "pcb"))
SUBKEY = {"epf": "epf", "kwsp": "epf", "socso": "socso", "perkeso": "socso", "eis": "eis", "sip": "eis", "pcb": "pcb",
          "e-pcb": "pcb", "mtd": "pcb", "total": "total"}
MONTH_NAMES = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
               "november", "december"]

HALF_SEN = 0.005


class Refused(ValueError):
    """The workbook can't be checked; the message says why in a sentence for the owner."""


# ---------- small helpers ----------

def squash(s):
    """A heading as compared here: full-width colons and brackets made plain (NFKC), lower case, no spaces, no colon
    at the end. 'Month ：' -> 'month', 'D E D U C T I O N' -> 'deduction', 'Basic \\nSalary' -> 'basicsalary'."""
    s = unicodedata.normalize("NFKC", str(s)).lower()
    return re.sub(r"\s+", "", s).rstrip(":").strip()


def sen(v):
    """An amount in ringgit (a float from the workbook) as whole sen, rounded half up."""
    return int((Decimal(repr(float(v))) * 100).quantize(Decimal("1"), ROUND_HALF_UP))


def has_fraction_of_sen(v):
    """True for an amount with more than 2 decimals (3222.5806451612902), not for float noise (1046.3000000000002)."""
    return v is not None and abs(round(v, 2) - v) > 5e-7


def rm(v):
    """RM 1,234.50; an amount with more than 2 decimals shows them (RM 3,222.580645)."""
    if v is None:
        return "nothing"
    if has_fraction_of_sen(v):
        return "RM " + f"{v:,.6f}".rstrip("0")
    return f"RM {v:,.2f}"


def rm_sen(n):
    return f"RM {n / 100:,.2f}"


def mask(nric):
    """An IC or passport number with every letter and digit but the last 4 hidden: ••••••-••-5555."""
    s = str(nric or "").strip()
    if not s:
        return ""
    keep = 0
    out = []
    for ch in reversed(s):
        if ch.isalnum():
            keep += 1
            out.append(ch if keep <= 4 else "•")
        else:
            out.append(ch)
    return "".join(reversed(out))


def birth_date(nric, month):
    """The date of birth in a Malaysian IC number (yymmdd-pb-####), the century taken so that it isn't after the
    payroll month's year; None for anything else (a passport or other number)."""
    m = re.fullmatch(r"(\d{2})(\d{2})(\d{2})-?(\d{2})-?(\d{4})", str(nric or "").strip())
    if not m:
        return None
    yy, mm, dd = (int(x) for x in m.groups()[:3])
    year_now = int(month[:4]) if month else date.today().year
    year = 2000 + yy if 2000 + yy <= year_now else 1900 + yy
    try:
        return date(year, mm, dd)
    except ValueError:
        return None


def born(nric, month):
    """From a Malaysian IC number: (True, age on the last day of the payroll month); (False, None) for anything else
    (a passport or other number), whose rate group isn't checked."""
    birth = birth_date(nric, month)
    if not birth:
        return False, None
    y, mo = (int(month[:4]), int(month[5:7])) if month else (date.today().year, date.today().month)
    end = date(y, mo, calendar.monthrange(y, mo)[1])
    return True, end.year - birth.year - ((end.month, end.day) < (birth.month, birth.day))


def sixty_rates_from(nric, month):
    """The first payroll month (2026-11) paid at the 60-and-over rates: the month after the month of the 60th
    birthday, whatever the day. None for a number that isn't a Malaysian IC. This is common payroll practice, not a
    published rule: KWSP's Third Schedule only says Part A applies "until the employees attain the age of sixty years"
    (https://www.kwsp.gov.my/documents/d/guest/third_schedule_from_-1-october-2025) and PERKESO ties the SOCSO and
    EIS change to reaching 60; neither says which month. To confirm with KWSP and PERKESO (scope doc, sections 6 and 11, rate checks)."""
    birth = birth_date(nric, month)
    if not birth:
        return None
    y, mo = birth.year + 60, birth.month + 1
    if mo > 12:
        y, mo = y + 1, 1
    return f"{y}-{mo:02d}"


def _month_before(month):
    y, mo = int(month[:4]), int(month[5:7]) - 1
    return f"{y - 1}-12" if mo == 0 else f"{y}-{mo:02d}"


def month_of_text(v):
    """A month written on a sheet ('October 2026', 'SALARY FOR THE MONTH OF OCTOBER 2026', or a date) as 2026-10."""
    if isinstance(v, (datetime, date)):
        return f"{v.year}-{v.month:02d}"
    s = str(v or "").lower()
    for m in re.finditer(r"([a-z]{3,9})\.?\s*,?\s*(\d{4})", s):
        word, year = m.groups()
        for i, name in enumerate(MONTH_NAMES):
            if name.startswith(word) and len(word) >= 3:
                return f"{year}-{i + 1:02d}"
    return None


def month_word(text):
    """A month row's label (JAN, SEPT, June) as its number, else None; 'total' is 13."""
    t = squash(text)
    if t == "total":
        return 13
    if not t.isalpha() or len(t) < 3:
        return None
    for i, name in enumerate(MONTH_NAMES):
        if name.startswith(t):
            return i + 1
    return None


def label_month(month):
    return db.month_label(month) if month else "an unknown month"


# ---------- formulas ----------

# A reference to a cell on a named sheet: Sheet!C17, 'Staff A'!C17, [1]OTHERS!K9 or '[1]Other sheet'!K9.
QUAL = re.compile(r"(?:'((?:[^']|'')+)'|((?:\[\d+\])?[A-Za-z_À-￿][\w.À-￿]*|\[\d+\][\w.À-￿]+))!"
                  r"\$?([A-Z]{1,3})\$?(\d+)(?::\$?([A-Z]{1,3})\$?(\d+))?")
# A reference to a cell (or a range) on the same sheet: C17, $C$52, C40:C51.
BARE = re.compile(r"(?<![A-Za-z0-9_.!'\]$])\$?([A-Z]{1,3})\$?(\d+)(?::\$?([A-Z]{1,3})\$?(\d+))?(?![\w(!])")
NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])")


def refs(formula):
    """The references a formula makes: [{sheet (None: the same sheet), book (the [n] of another workbook, or None),
    col, row, col2, row2, text}]."""
    out, rest = [], formula
    for m in QUAL.finditer(formula):
        name = (m.group(1) or "").replace("''", "'") if m.group(1) is not None else m.group(2)
        book = None
        x = re.match(r"\[(\d+)\](.*)", name)
        if x:
            book, name = int(x.group(1)), x.group(2)
        out.append({"sheet": name, "book": book, "col": m.group(3), "row": int(m.group(4)),
                    "col2": m.group(5), "row2": int(m.group(6)) if m.group(6) else None, "text": m.group(0)})
    rest = QUAL.sub(" ", formula)
    rest = re.sub(r'"[^"]*"', " ", rest)
    for m in BARE.finditer(rest):
        out.append({"sheet": None, "book": None, "col": m.group(1), "row": int(m.group(2)), "col2": m.group(3),
                    "row2": int(m.group(4)) if m.group(4) else None, "text": m.group(0)})
    return out


def numbers_in(formula):
    """The numbers typed into a formula (not those in its references): =C17*7 -> ['7']; =207.4+207.4 -> two."""
    rest = QUAL.sub(" ", formula[1:] if formula.startswith("=") else formula)
    rest = BARE.sub(" ", rest)
    rest = re.sub(r'"[^"]*"', " ", rest)
    return NUMBER.findall(rest)


def single_link(formula):
    """The one reference a formula is (=Sheet!C17, =+C17), or None for anything else."""
    body = formula.lstrip("=").strip().lstrip("+").strip()
    found = refs("=" + body)
    if len(found) == 1 and found[0]["text"] == body and not found[0]["col2"]:
        return found[0]
    return None


# ---------- reading the workbook ----------

class Sheet:
    """One sheet, read for its formulas (fs) and the values Excel saved with them (vs). Cells are only read, never
    made (openpyxl would add empty ones)."""

    def __init__(self, fs, vs):
        self.title, self.fs, self.vs = fs.title, fs, vs
        self.hidden = fs.sheet_state != "visible"
        self._texts = None

    def raw(self, r, c):
        cell = self.fs._cells.get((r, c))
        v = cell.value if cell is not None else None
        return getattr(v, "text", v)  # an array formula keeps its text there

    def value(self, r, c):
        cell = self.vs._cells.get((r, c))
        return cell.value if cell is not None else None

    def formula(self, r, c):
        v = self.raw(r, c)
        return v if isinstance(v, str) and v.startswith("=") else None

    def num(self, r, c):
        v = self.value(r, c)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    def typed_num(self, r, c):
        v = self.raw(r, c)
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    def text(self, r, c):
        v = self.raw(r, c)
        if isinstance(v, str) and not v.startswith("="):
            return v
        v = self.value(r, c)
        return v if isinstance(v, str) else None

    def filled(self, r, c):
        return self.raw(r, c) not in (None, "")

    def texts(self):
        """{(row, col): squashed text} of every cell holding text."""
        if self._texts is None:
            self._texts = {}
            for (r, c) in list(self.fs._cells):
                t = self.text(r, c)
                if t and t.strip():
                    self._texts[(r, c)] = squash(t)
        return self._texts

    def right_of(self, r, c, span=4):
        """The first cell to the right of a label that holds something: (col, raw value, value), or None."""
        for cc in range(c + 1, c + 1 + span):
            if self.filled(r, cc):
                return cc, self.raw(r, cc), self.value(r, cc)
        return None


def cell_name(c, r):
    return f"{get_column_letter(c)}{r}"


def _external_books(z):
    """The other workbooks this one links to, as {n: file name} for the [n] in its formulas, read from its
    xl/externalLinks parts (in the order the workbook lists them)."""
    names = set(z.namelist())
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
          "p": "http://schemas.openxmlformats.org/package/2006/relationships"}
    def rels(part):
        rp = posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")
        if rp not in names:
            return {}
        try:
            root = ET.fromstring(z.read(rp))
        except ET.ParseError:
            return {}
        return {x.get("Id"): x.get("Target") for x in root.findall("p:Relationship", ns)}
    parts = []
    try:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        wrels = rels("xl/workbook.xml")
        for x in wb.findall("m:externalReferences/m:externalReference", ns):
            t = wrels.get(x.get(f"{{{ns['r']}}}id"))
            if t:
                parts.append(posixpath.normpath(posixpath.join("xl", t)) if not t.startswith("/") else t.lstrip("/"))
    except (KeyError, ET.ParseError):
        pass
    if not parts:  # listed by part name only
        parts = sorted((n for n in names if re.fullmatch(r"xl/externalLinks/externalLink\d+\.xml", n)),
                       key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))
    out = {}
    for i, part in enumerate(parts, 1):
        targets = list(rels(part).values())
        name = targets[0] if targets else part
        name = re.sub(r"%20", " ", name.replace("\\", "/").rsplit("/", 1)[-1])
        out[i] = name or f"external workbook {i}"
    return out


def open_workbook(data, filename=None):
    """The workbook as (formula book, value book, {n: other workbook's file name}), or Refused with why."""
    if filename and not filename.lower().endswith(".xlsx"):
        raise Refused("Only an Excel workbook (.xlsx) can be checked. Open the payroll in Excel, save it as an Excel "
                      "Workbook (.xlsx) and upload that.")
    if len(data) > MAX_BYTES:
        raise Refused(f"This file is larger than this check takes ({MAX_BYTES // (1024 * 1024)} MB). The payroll workbook "
                      "is usually under 1 MB: check that this is the right file.")
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        names = set(z.namelist())
        if "xl/workbook.xml" not in names:
            raise zipfile.BadZipFile
        if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED:
            raise Refused("This workbook unpacks to more than this check takes, so it wasn't read. Check that this is "
                          "the payroll workbook.")
        books = _external_books(z)
    except (zipfile.BadZipFile, KeyError, ValueError) as ex:
        if isinstance(ex, Refused):
            raise
        raise Refused("This file isn't an Excel workbook (.xlsx), so it can't be checked. Open the payroll in Excel, "
                      "save it as an Excel Workbook (.xlsx) and upload that.")
    try:
        with warnings.catch_warnings():  # openpyxl warns about parts it doesn't keep (data validation, images)
            warnings.simplefilter("ignore")
            wf = load_workbook(io.BytesIO(data), data_only=False)
            wv = load_workbook(io.BytesIO(data), data_only=True)
    except Exception:
        raise Refused("This workbook couldn't be read. Open it in Excel, save it again as an Excel Workbook (.xlsx) and "
                      "upload that.")
    return wf, wv, books


# ---------- one person's sheet (the payslip) ----------

def _columns(texts, r, c_first):
    """The figures' columns under a pay heading row r (and its sub-headings in row r + 1), from the Basic Salary
    column c_first on: {key: col}."""
    heads = {c: t for (rr, c), t in texts.items() if rr == r and c >= c_first}
    subs = {c: t for (rr, c), t in texts.items() if rr == r + 1 and c >= c_first}
    cols = {"basic": c_first}
    er = min((c for c, t in heads.items() if t.startswith("employercontribution")), default=10 ** 6)
    for c, t in heads.items():
        if t.startswith("totaldeduction"):
            cols["total_ded"] = c
        elif "allowance" in t:
            cols["allowance"] = c
        elif t.startswith("netpay"):
            cols["net"] = c
    for c, t in sorted(subs.items()):
        key = "skbbk" if t.startswith("skbbk") else SUBKEY.get(t)
        if key in (None, "total"):
            continue
        if c >= er:
            if key in ("epf", "socso", "eis"):
                cols.setdefault("er_" + key, c)
        else:
            cols.setdefault(key, c)
    return cols


def read_person(sh):
    """A payslip sheet as {sheet, name, nric, month, pay_row, cols, pay, insurance, ytd, table}; None for a sheet
    with no Basic Salary heading."""
    T = sh.texts()
    basics = sorted((rc for rc, t in T.items() if t == "basicsalary"))
    if not basics:
        return None
    month_heads = {r for (r, c), t in T.items() if t == "month"}
    table_head = next(((r, c) for r, c in basics if r in month_heads and any(
        rr == r and cc < c and t == "month" for (rr, cc), t in T.items())), None)
    pay_head = next(((r, c) for r, c in basics if (r, c) != table_head), None)
    if not pay_head:
        return None
    hr, hc = pay_head
    p = {"sheet": sh.title, "head_row": hr}
    # The person block above the pay table: labels with their values to the right.
    for (r, c), t in sorted(T.items()):
        if r >= hr:
            continue
        key = ("month" if t == "month" else "name" if t == "name" else "nric" if t.startswith("nric")
               else "position" if t == "position" else None)
        if key and key not in p:
            got = sh.right_of(r, c)
            if got:
                p[key] = got[2] if got[2] is not None else got[1]
                p[key + "_cell"] = cell_name(got[0], r)
    p["month_value"] = p.get("month")
    p["month"] = month_of_text(p.get("month")) if p.get("month") is not None else None
    if isinstance(p.get("name"), str):
        p["name"] = p["name"].strip()
    if p.get("nric") is not None:
        p["nric"] = str(p["nric"]).strip()
    cols = _columns(T, hr, hc)
    p["cols"] = cols
    pay_row = None
    for r in range(hr + 2, hr + 10):
        if sh.filled(r, hc) and (sh.num(r, hc) is not None or sh.formula(r, hc)):
            pay_row = r
            break
    if pay_row is None:
        return None
    p["pay_row"] = pay_row
    p["pay"] = {k: sh.num(pay_row, c) for k, c in cols.items()}
    # Insurance: only on some sheets, its amount under the heading.
    ins = next(((r, c) for (r, c), t in T.items() if t == "insurance" and (table_head is None or r < table_head[0])), None)
    p["insurance"], p["insurance_cell"] = 0.0, None
    if ins:
        for r in range(ins[0] + 1, ins[0] + 4):
            if sh.num(r, ins[1]) is not None:
                p["insurance"], p["insurance_cell"] = sh.num(r, ins[1]), (r, ins[1])
                break
    p["pay"]["insurance"] = p["insurance"]
    # The monthly table.
    table = None
    if table_head:
        tr, tc = table_head
        mcol = max(c for (r, c), t in T.items() if r == tr and c < tc and t == "month")
        tcols = _columns(T, tr, tc)
        months, total_row = {}, None
        for r in range(tr + 1, tr + 30):
            w = month_word(sh.text(r, mcol) or "")
            if w == 13:
                total_row = r
                break
            if w and w not in months:
                months[w] = r
        table = {"head_row": tr, "month_col": mcol, "cols": tcols, "months": months, "total_row": total_row}
    p["table"] = table
    # The year-to-date box.
    ytd = None
    y = next(((r, c) for (r, c), t in T.items() if t.startswith("ytd")), None)
    if y:
        yr, yc = y
        lines, seen_cols = [], Counter()
        for r in range(yr + 1, yr + 14):
            t = T.get((r, yc))
            key = next((k for prefix, k in YTD_KEYS if t and t.startswith(prefix)), None)
            if not key:
                continue
            got = None
            for c in range(yc + 1, yc + 5):
                if sh.filled(r, c) and (sh.formula(r, c) or sh.typed_num(r, c)):
                    got = c
                    break
            if got:
                seen_cols[got] += 1
            lines.append((key, r, sh.text(r, yc).strip()))
        vcol = seen_cols.most_common(1)[0][0] if seen_cols else yc + 2
        ytd = {"row": yr, "label_col": yc, "value_col": vcol, "lines": [
            {"key": k, "row": r, "label": lab, "cell": (r, vcol)} for k, r, lab in lines]}
    p["ytd"] = ytd
    return p


# ---------- the Summary ----------

def read_summary(sh):
    """The Summary as {month, head_row, cols: {key: col}, rows: [row numbers], total_row}; None when it has no
    NAME and Basic headings."""
    T = sh.texts()
    hr = next((r for (r, c), t in sorted(T.items()) if t == "name" and any(rr == r and tt == "basic" for (rr, _), tt in T.items())), None)
    if hr is None:
        return None
    heads = {c: t for (r, c), t in T.items() if r == hr}
    subs = {c: t for (r, c), t in T.items() if r == hr + 1}
    groups = {"deduction": ("", {"epf", "socso", "eis", "skbbk", "pcb", "total"}),
              "employer": ("er_", {"epf", "socso", "eis"}), "total": ("tot_", {"epf", "socso", "eis", "skbbk"})}
    cols = {}
    hcols = sorted(heads)
    taken = set()
    for i, hc in enumerate(hcols):
        t = heads[hc]
        nxt = hcols[i + 1] if i + 1 < len(hcols) else 10 ** 6
        g = groups.get(t)
        under = []
        if g:
            c = hc
            while c < nxt:
                st = subs.get(c)
                key = "skbbk" if st and st.startswith("skbbk") else SUBKEY.get(st or "")
                if key in g[1]:
                    under.append((c, key))
                elif st:
                    break
                c += 1
        if under:
            for c, key in under:
                k = "total_ded" if (g[0] == "" and key == "total") else g[0] + key
                cols.setdefault(k, c)
                taken.add(c)
            continue
        key = ("no" if t in ("no.", "no") else "name" if t == "name" else "nric" if t.startswith("nric")
               else "basic" if t == "basic" else "net" if t == "net" else "insurance" if t.startswith("insurance")
               else "allowance" if "allowance" in t else "pay_total" if t == "total" else None)
        if key:
            cols.setdefault(key, hc)
    # A single heading written in the second heading row only.
    for c, t in subs.items():
        if c in taken or c in heads:
            continue
        key = ("net" if t == "net" else "insurance" if t.startswith("insurance") else "allowance" if "allowance" in t
               else None)
        if key:
            cols.setdefault(key, c)
    rows, total_row = [], None
    look = [cols[k] for k in ("no", "name") if k in cols]
    for r in range(hr + 2, hr + 200):
        words = [squash(sh.text(r, c) or "") for c in look] + [squash(sh.text(r, c) or "") for c in range(1, min(look or [3]) + 1)]
        if "total" in words:
            total_row = r
            break
        if any(sh.filled(r, c) for c in cols.values()):
            rows.append(r)
    month = None
    for (r, c), t in T.items():
        if r < hr and "monthof" in t:
            month = month_of_text(sh.text(r, c))
            if month:
                break
    return {"month": month, "head_row": hr, "cols": cols, "rows": rows, "total_row": total_row}


# ---------- the check ----------

class Findings(list):
    def add(self, kind, severity, group, sheet, cell, what, should, expected=None, cells=None):
        self.append({"kind": kind, "severity": severity, "severity_label": SEVERITY[severity], "group": group,
                     "sheet": sheet, "cell": cell, "cells": cells or ([cell] if cell else []), "what": what,
                     "should": should, "expected_sen": None if expected is None else sen(expected)})


def _differs(a, b):
    return abs((a or 0) - (b or 0)) >= HALF_SEN


def _ref_name(ref):
    sheet = ref["sheet"]
    q = f"'{sheet}'" if sheet and not re.fullmatch(r"[A-Za-z_][\w.]*", sheet) else sheet
    return f"{q}!{ref['col']}{ref['row']}" if sheet else f"{ref['col']}{ref['row']}"


def check(data, month=None, filename=None):
    """Reads the workbook (bytes) and checks it for the payroll month chosen (2026-10). Returns the report (see
    report_of); Refused with a sentence when it can't be checked."""
    chosen = month
    wf, wv, books = open_workbook(data, filename)
    sheets = [Sheet(wf[n], wv[n]) for n in wf.sheetnames]
    summary_sheet = next((s for s in sheets if squash(s.title) == "summary" and not s.hidden), None)
    if not summary_sheet:
        raise Refused("This workbook has no sheet named Summary, so it can't be checked against the payslips. Check "
                      "that this is the month's payroll workbook.")
    S = read_summary(summary_sheet)
    if not S or "basic" not in S["cols"]:
        raise Refused("The Summary sheet has no NAME and Basic headings, so its rows can't be read. Check that this is "
                      "the month's payroll workbook.")
    F = Findings()
    people, info = {}, {}
    for s in sheets:
        if s is summary_sheet:
            continue
        if s.hidden:
            F.add("hidden_sheet", "note", "", s.title, None, f"The sheet {s.title} is hidden, so it was not checked.",
                  "Nothing to do if it is an old template. Unhide it if it holds a payslip for this month.")
            continue
        p = read_person(s)
        if p:
            people[s.title] = p
            p["sh"] = s
        else:
            F.add("not_payslip", "note", "", s.title, None,
                  f"The sheet {s.title} has no Basic Salary heading, so it isn't read as a payslip and wasn't checked.",
                  "Nothing to do if it isn't a payslip.")
    if not people:
        raise Refused("No sheet in this workbook looks like a payslip (a Basic Salary heading with the month's pay "
                      "under it), so there is nothing to check.")
    wb_month = S["month"]
    if not wb_month:
        common = Counter(p["month"] for p in people.values() if p["month"]).most_common(1)
        wb_month = common[0][0] if common else None
        F.add("workbook_month", "check", "Summary", summary_sheet.title, None,
              "The Summary doesn't say which month it is for (a line like SALARY FOR THE MONTH OF OCTOBER 2026).",
              "Add the month to the Summary so the file can't be mistaken for another month's.")
    if month and wb_month and wb_month != month:
        F.add("workbook_month", "fix", "Summary", summary_sheet.title, None,
              f"The workbook is for {label_month(wb_month)}, but this is the check for {label_month(month)}.",
              f"Upload {label_month(month)}'s workbook, or choose {label_month(wb_month)} at the top of the page.")
    # Each payslip is compared with the workbook's own month (what the Summary says), else the month chosen.
    month = wb_month or month
    for p in people.values():
        info[p["sheet"]] = _person_checks(p, month, F, books)
    rows = _summary_checks(summary_sheet, S, people, books, F)
    _external_unused(wf, books, F)
    F.add("pcb_not_checked", "note", "", None, None,
          "PCB amounts themselves are not checked (they need the details payroll will hold). Only each payslip's "
          "year-to-date PCB is checked against its monthly table.",
          "Check each PCB on LHDN's calculator as before.")
    return report_of(F, people, info, rows, S, chosen or month, wb_month, books)


def _book_name(books, n):
    return books.get(n, f"external workbook {n}")


def _payslip_external(p, month, books, F):
    """Figures on a payslip that come from another workbook: the pay row, the insurance amount, this month's row of
    the monthly table and the year-to-date box. One finding names every such cell and the other file."""
    sh, s = p["sh"], p["sheet"]
    places = [(p["pay_row"], c, LABEL.get(k, k)) for k, c in p["cols"].items()]
    if p["insurance_cell"]:
        places.append((p["insurance_cell"][0], p["insurance_cell"][1], LABEL["insurance"]))
    t = p["table"]
    if t and month and int(month[5:7]) in t["months"]:
        mr = t["months"][int(month[5:7])]
        places += [(mr, c, f"the monthly table's {label_month(month)} {LABEL.get(k, k)}") for k, c in t["cols"].items()]
    if p["ytd"]:
        places += [(ln["cell"][0], ln["cell"][1], f"year-to-date {ln['label']}") for ln in p["ytd"]["lines"]]
    hits, seen = [], set()
    for r, c, what in places:
        if (r, c) in seen:
            continue
        seen.add((r, c))
        f = sh.formula(r, c)
        if not f:
            continue
        other = [rf for rf in refs(f) if rf["book"]]
        if other:
            hits.append((cell_name(c, r), what, sorted({f"{_book_name(books, rf['book'])} ({rf['sheet']}!{rf['col']}{rf['row']})"
                                                         for rf in other})))
    if hits:
        names = sorted({_book_name(books, rf["book"]) for r, c, _ in places if sh.formula(r, c)
                        for rf in refs(sh.formula(r, c)) if rf["book"]})
        F.add("external_link", "fix", s, s, hits[0][0],
              "; ".join(f"{what} ({cell}) comes from {', '.join(src)}" for cell, what, src in hits)
              + f". That other file decides {'these figures' if len(hits) > 1 else 'this figure'}, and everything "
              "worked out from it here (the deductions, net pay, the year to date and the Summary), not this workbook.",
              f"Type the figure here or work it out on this sheet, so nothing comes from {', '.join(names)}.",
              None, [cell for cell, _, _ in hits])


def _person_checks(p, month, F, books=None):
    """The checks on one payslip; returns the lines saying what was assumed (statutory category, rate group)."""
    sh, s, g = p["sh"], p["sheet"], p["sheet"]
    pay, cols, pr = p["pay"], p["cols"], p["pay_row"]
    lines = []
    cell = lambda k: cell_name(cols[k], pr) if k in cols else None
    _payslip_external(p, month, books or {}, F)
    # The month on the sheet.
    if not p["month"]:
        F.add("sheet_month", "check", g, s, p.get("month_cell"), "No month was found on this payslip.",
              f"Put the month ({label_month(month)}) beside Month on the payslip.")
    elif month and p["month"] != month:
        F.add("sheet_month", "fix", g, s, p.get("month_cell"),
              f"The payslip says {label_month(p['month'])}, but the workbook is for {label_month(month)}.",
              f"Change the month to {label_month(month)} and check that the pay row is this month's.")
    missing = [LABEL[k] for k in ("basic", "epf", "socso", "eis", "pcb", "total_ded", "net") if k not in cols]
    if missing:
        F.add("columns_missing", "check", g, s, cell_name(cols["basic"], p["head_row"]),
              f"These pay table headings weren't found: {', '.join(missing)}, so those figures weren't checked.",
              "Keep the payslip's headings as on the other sheets.")
    no_pay = all(not (pay.get(k) or 0) for k in FIGURES if k in cols)
    ytd_total = 0.0
    if p["ytd"]:
        ytd_total = sum(abs(sh.num(*ln["cell"]) or 0) for ln in p["ytd"]["lines"])
    if no_pay:
        if ytd_total:
            F.add("no_pay", "note", g, s, cell("basic"),
                  "No pay this month (left?): the pay row is all zero but the year-to-date box isn't.",
                  "Nothing to do if they have left. Take the row off the Summary, or keep it at zero.")
        lines.append("No pay this month, so the statutory figures weren't checked.")
    # The pay row adds up.
    if not no_pay and all(k in cols for k in ("epf", "socso", "eis", "pcb", "total_ded")):
        parts = [pay.get(k) or 0 for k in ("epf", "socso", "eis", "skbbk", "pcb") if k in cols]
        if _differs(pay["total_ded"], sum(parts)):
            F.add("pay_row_sum", "fix", g, s, cell("total_ded"),
                  f"Total deduction is {rm(pay['total_ded'])} but the deductions beside it add up to {rm(sum(parts))}.",
                  "Total deduction should be the sum of EPF, SOCSO, EIS, SKBBK and PCB.", sum(parts))
    if not no_pay and all(k in cols for k in ("basic", "total_ded", "net")):
        want = (pay["basic"] or 0) - (pay["total_ded"] or 0) + (pay.get("allowance") or 0)
        if _differs(pay["net"], want):
            F.add("pay_row_sum", "fix", g, s, cell("net"),
                  f"Net pay is {rm(pay['net'])} but basic less deductions plus allowance is {rm(want)}.",
                  "Net pay should be basic salary - total deduction + allowance.", want)
    # This month's row of the monthly table and the year-to-date box.
    t = p["table"]
    if t and month and int(month[5:7]) in t["months"]:
        mr = t["months"][int(month[5:7])]
        bad = [(k, sh.num(mr, t["cols"][k]), pay.get(k)) for k in FIGURES if k in t["cols"] and k in cols
               and _differs(sh.num(mr, t["cols"][k]), pay.get(k))]
        if bad:
            k0 = bad[0][0]
            F.add("month_row", "fix", g, s, cell_name(t["cols"][k0], mr),
                  f"The monthly table's {label_month(month)} row differs from the pay row: "
                  + "; ".join(f"{LABEL[k]} {rm(a)} in the table, {rm(b)} on the pay row" for k, a, b in bad) + ".",
                  "Link the month's row to the pay row (=C17 and so on), so the year-to-date figures include this month.",
                  bad[0][2], [cell_name(t["cols"][k], mr) for k, _, _ in bad])
    elif t and month:
        F.add("month_row", "check", g, s, None, f"No {label_month(month)} row was found in the monthly table.",
              "Keep the table's month rows JAN to DEC.")
    if p["ytd"] and t:
        _ytd_checks(p, t, F)
    # The sheet's own check cells (=N25=K52) showing FALSE.
    if p["ytd"]:
        y = p["ytd"]
        for ln in y["lines"]:
            for c in range(y["value_col"] + 1, y["value_col"] + 4):
                if sh.value(ln["row"], c) is False:
                    f = sh.formula(ln["row"], c)
                    F.add("self_check", "check", g, s, cell_name(c, ln["row"]),
                          f"The sheet's own check beside {ln['label']} shows FALSE" + (f" ({f})" if f else "") + ".",
                          "Find why the two figures it compares differ before paying.")
    first_statutory = len(F)
    if not no_pay:
        lines += _statutory(p, month, F)
    _unrounded_pay_row(p, F, F[first_statutory:])
    return lines


STATUTORY = ("epf", "socso", "eis", "skbbk", "er_epf", "er_socso", "er_eis")


def _unrounded_pay_row(p, F, statutory):
    """Money with fractions of a sen in the pay row (and the insurance amount), with the rounded figure for each. A
    statutory figure the statutory check already gives an amount for is left to that finding, and the total deduction
    and net pay suggested are worked out with that amount, so the two findings never give different figures."""
    s, g = p["sheet"], p["sheet"]
    pay, cols, pr = p["pay"], p["cols"], p["pay_row"]
    odd = [(k, pay[k]) for k in FIGURES if k in cols and has_fraction_of_sen(pay.get(k))]
    if p["insurance_cell"] and has_fraction_of_sen(p["insurance"]):
        odd.append(("insurance", p["insurance"]))
    if not odd:
        return
    # The amount the statutory check gives, by pay-row key, where it found the figure wrong.
    by_cell = {f["cell"]: f["expected_sen"] for f in statutory if f["severity"] == "fix" and f["expected_sen"] is not None}
    told = {k: by_cell[cell_name(cols[k], pr)] / 100 for k in STATUTORY if k in cols and cell_name(cols[k], pr) in by_cell}
    left = [k for k, _ in odd if k in told]
    odd = [(k, v) for k, v in odd if k not in told]
    if not odd:
        return
    def fixed(k):
        return told[k] if k in told else round(pay.get(k) or 0, 2)
    target = {}
    for k, v in odd:
        if k == "total_ded" and told:
            target[k] = round(sum(fixed(x) for x in ("epf", "socso", "eis", "skbbk", "pcb") if x in cols), 2)
        elif k == "net" and told:
            ded = sum(fixed(x) for x in ("epf", "socso", "eis", "skbbk", "pcb") if x in cols)
            target[k] = round(fixed("basic") - ded + fixed("allowance"), 2)
        else:
            target[k] = round(v, 2)
    cells = [cell_name(cols[k], pr) if k != "insurance" else cell_name(p["insurance_cell"][1], p["insurance_cell"][0]) for k, _ in odd]
    listed = "; ".join(f"{LABEL[k]} {rm(v)}" for k, v in odd)
    using = "; ".join(f"{LABEL[k]} {rm(told[k])}" for k in told)
    F.add("unrounded", "fix", g, s, cells[0],
          f"Amounts with more than 2 decimals: {listed}."
          + (f" ({', '.join(LABEL[k] for k in left)} also, but {'their own findings give' if len(left) > 1 else 'its own finding gives'} "
             "the amount it should be.)" if left else ""),
          "Round each to the sen (=ROUND(...,2)) so what is paid is what is on the payslip: "
          + "; ".join(f"{LABEL[k]} {rm(target[k])}" for k, _ in odd) + "."
          + (f" These are worked out with the statutory figures the other findings give ({using})."
             if told and any(k in ("total_ded", "net") for k, _ in odd) else ""),
          target[odd[0][0]], cells)


def _ytd_checks(p, t, F):
    """Each year-to-date line against the monthly table's total for its column, and how it is built."""
    sh, s = p["sh"], p["sheet"]
    first = min(t["months"].values()) if t["months"] else t["head_row"] + 2
    last = max(t["months"].values()) if t["months"] else (t["total_row"] - 1 if t["total_row"] else first)
    for ln in p["ytd"]["lines"]:
        k = ln["key"]
        if k not in t["cols"]:
            continue
        col = t["cols"][k]
        r, c = ln["cell"]
        here = cell_name(c, r)
        if t["total_row"]:
            total = sh.num(t["total_row"], col)
            where = f"the monthly table's Total ({cell_name(col, t['total_row'])})"
        else:
            total = sum(sh.num(mr, col) or 0 for mr in t["months"].values())
            where = "the monthly table's months added up"
        value = sh.num(r, c)
        f = sh.formula(r, c)
        why = _ytd_fragile(f, sh.typed_num(r, c), col, first, last, p["pay_row"], t["total_row"])
        if _differs(value, total):
            F.add("ytd", "fix", s, s, here,
                  f"Year-to-date {ln['label']} is {rm(value)} but {where} is {rm(total)}."
                  + ((f" Its formula {why}." if f else f" It {why}.") if why else ""),
                  f"{rm(total)}, from the table: make it ={cell_name(col, t['total_row'])}." if t["total_row"]
                  else f"{rm(total)}, from the table.", total)
        elif why:
            F.add("ytd_formula", "check", s, s, here,
                  f"Year-to-date {ln['label']} agrees today, but its formula {why}, so it will go wrong next month.",
                  f"Make it ={cell_name(col, t['total_row'])} (the table's Total)." if t["total_row"]
                  else "Make it add up the monthly table's column.")


ROUNDED = re.compile(r"=\s*\+?\s*ROUND(?:UP|DOWN)?\((.*),\s*\d+\s*\)\s*", re.I | re.S)


def _ytd_fragile(f, typed, col, first, last, pay_row, total_row=None):
    """Why a year-to-date cell's formula won't keep agreeing with the table, or None when it is sound: the table's
    Total cell for its column (=C52), or a sum of every month row JAN to DEC of that column (=SUM(C40:C51)), either
    of them maybe rounded (=ROUND(C52,2)). first..last: the month rows (last the DEC row)."""
    if not f:
        return "is a typed figure, not added up from the monthly table" if typed else None
    inner = f
    while True:
        x = ROUNDED.fullmatch(inner)
        if not x:
            break
        inner = "=" + x.group(1)
    found = refs(inner)
    nums = numbers_in(inner)
    letter = get_column_letter(col)
    def rows_of(x):
        return range(min(x["row"], x["row2"] or x["row"]), max(x["row"], x["row2"] or x["row"]) + 1)
    def own_column(x):
        return x["sheet"] is None and x["col"] == letter and x["col2"] in (None, letter)
    def in_table(x):
        rows = rows_of(x)
        return own_column(x) and first <= rows[0] and rows[-1] <= (total_row or last)
    if found and all(in_table(x) for x in found) and not nums:
        if total_row and len(found) == 1 and not found[0]["row2"] and found[0]["row"] == total_row:
            return None
        covered = {r for x in found for r in rows_of(x)}
        if total_row not in covered and set(range(first, last + 1)) <= covered:
            return None
        if total_row not in covered:
            return f"({f}) takes only some months of the table"
    if nums and "*" in f:
        return f"({f}) multiplies by a fixed number of months"
    if len(nums) >= 2:
        return f"({f[:60]}{'…' if len(f) > 60 else ''}) adds up a typed list of past amounts"
    if any(x["sheet"] is None and x["row"] == pay_row for x in found):
        return f"({f}) takes this month's figure only"
    return f"({f[:60]}) doesn't add up the monthly table's column"


# ---------- statutory figures ----------

def _ceil_div(a, b):
    return -(-a // b)


def epf_expected(wage_sen, age60=False):
    """The EPF employee and employer shares in sen for a month's EPF wages (sen), by the Third Schedule's band rule;
    age60: aged 60 or over."""
    R = RATES["epf"]
    if wage_sen <= 0:
        return 0, 0
    if wage_sen > R["exact_above"]:
        base = wage_sen
    elif wage_sen <= R["low_upto"]:
        base = _ceil_div(wage_sen, R["band_low"]) * R["band_low"]
    else:
        base = _ceil_div(wage_sen, R["band_high"]) * R["band_high"]
    if age60:
        ee, er = R["employee_60"], R["employer_60"]
    else:
        ee, er = R["employee"], (R["employer_low"] if wage_sen <= R["low_upto"] else R["employer_high"])
    return _ceil_div(base * ee, 10000) * 100, _ceil_div(base * er, 10000) * 100


def band_midpoint(wage_sen):
    """The midpoint (sen) of the RM 100 wage band PERKESO's tables use for SOCSO, EIS and SKBBK, with the RM 6,000
    ceiling; None below the smallest RM 100 band."""
    R = RATES["socso"]
    if wage_sen <= R["smallest"]:
        return None
    upper = min(_ceil_div(wage_sen, R["band"]) * R["band"], R["ceiling"])
    return upper - R["band"] // 2


def socso_expected(wage_sen, second=False):
    """SOCSO's (employer, employee) share in sen as exact Decimals (the table rounds to 5 sen); None when the wage is
    below the RM 100 bands."""
    mid = band_midpoint(wage_sen)
    if mid is None:
        return None
    R = RATES["socso"]
    if second:
        return mid * R["second_employer"] / 100, Decimal(0)
    return mid * R["employer"] / 100, mid * R["employee"] / 100


def eis_expected(wage_sen):
    mid = band_midpoint(wage_sen)
    if mid is None:
        return None
    R = RATES["eis"]
    return mid * R["employer"] / 100, mid * R["employee"] / 100


def skbbk_expected(wage_sen):
    mid = band_midpoint(wage_sen)
    return None if mid is None else mid * RATES["skbbk"]["employee"] / 100


def five_sen(exact):
    """An exact share (Decimal sen) to the nearest 5 sen, as the tables print it."""
    return int((exact / 5).quantize(Decimal("1"), ROUND_HALF_UP)) * 5


def within(actual, exact):
    return actual is not None and abs(Decimal(sen(actual)) - exact) <= RATES["socso"]["tolerance"]


def _statutory(p, month, F):
    """EPF, SOCSO, EIS and SKBBK on the pay row; returns the lines saying what was assumed."""
    s, pay, cols, pr = p["sheet"], p["pay"], p["cols"], p["pay_row"]
    cell = lambda k: cell_name(cols[k], pr) if k in cols else None
    out = []
    basic = pay.get("basic")
    if basic is None:
        return out
    wage = sen(basic)
    malaysian, age = born(p.get("nric"), month)
    m = month or "9999-12"
    # The 60-and-over rates start with the month after the month of the 60th birthday; the birthday month itself is
    # still paid at the under-60 rates. (SOCSO and EIS are taken to change in the same month as EPF.) Payroll
    # practice, not a published KWSP or PERKESO rule: see sixty_rates_from.
    sixty_from = sixty_rates_from(p.get("nric"), month)
    over60 = bool(malaysian and sixty_from and (month or date.today().strftime("%Y-%m")) >= sixty_from)
    if malaysian and not over60 and sixty_from and month and month == _month_before(sixty_from):
        out.append(f"Turns 60 this month: the under-60 rates still apply; the 60-and-over rates start with "
                   f"{label_month(sixty_from)}'s pay.")
    if not malaysian:
        F.add("rate_group", "note", s, s, p.get("nric_cell"),
              "The NRIC isn't a Malaysian IC number, so the EPF rate group (and EIS, which differs for non-citizens) "
              "was not checked.", "Check the EPF and EIS rates for this person by hand.")
        out.append("EPF rate group not checked: not a Malaysian IC number.")
    # EPF
    if malaysian and "epf" in cols and m >= RATES["epf"]["from"]:
        ee, er = epf_expected(wage, over60)
        out.append(f"EPF: {'aged 60 or over' if over60 else 'under 60'}; on EPF wages {rm(basic)}: "
                   f"{rm_sen(ee)} employee, {rm_sen(er)} employer.")
        if sen(pay.get("epf") or 0) != ee:
            F.add("epf", "fix", s, s, cell("epf"),
                  f"Employee EPF is {rm(pay.get('epf'))}; the Third Schedule gives {rm_sen(ee)} on wages of {rm(basic)}.",
                  f"{rm_sen(ee)} (the rate times the top of the wage band, rounded up to the ringgit).", ee / 100)
        if "er_epf" in cols and sen(pay.get("er_epf") or 0) != er:
            rate = (RATES["epf"]["employer_60"] if over60 else RATES["epf"]["employer_low"] if wage <= RATES["epf"]["low_upto"]
                    else RATES["epf"]["employer_high"])
            F.add("epf", "fix", s, s, cell("er_epf"),
                  f"Employer EPF is {rm(pay.get('er_epf'))}; at {rate}% the Third Schedule gives {rm_sen(er)}.",
                  f"{rm_sen(er)}.", er / 100)
    # SOCSO
    mid = band_midpoint(wage)
    if mid is None:
        out.append("SOCSO, EIS and SKBBK not checked: the wage is in the table's smallest bands, not held here.")
        return out
    if "socso" in cols and m >= RATES["socso"]["from"]:
        er_v, ee_v = pay.get("er_socso"), pay.get("socso") or 0
        second_fits = within(er_v, socso_expected(wage, True)[0])
        second = over60 or (sen(ee_v) == 0 and second_fits)
        why = ("aged 60 or over" if over60 else "the employee pays nothing and the employer about 1.25%") if second else None
        exp_er, exp_ee = socso_expected(wage, second)
        out.append(f"SOCSO: {'second category (employment injury only) assumed: ' + why if second else 'first category assumed'}; "
                   f"band midpoint {rm_sen(mid)}.")
        if not within(ee_v, exp_ee):
            F.add("socso", "fix", s, s, cell("socso"),
                  f"Employee SOCSO is {rm(ee_v)}; the {'second' if second else 'first'} category table gives about "
                  f"{rm_sen(five_sen(exp_ee))} on wages of {rm(basic)}.",
                  f"{rm_sen(five_sen(exp_ee))} (5 sen either way is allowed).", five_sen(exp_ee) / 100)
        if "er_socso" in cols and not within(er_v, exp_er):
            F.add("socso", "fix", s, s, cell("er_socso"),
                  f"Employer SOCSO is {rm(er_v)}; the {'second' if second else 'first'} category table gives about "
                  f"{rm_sen(five_sen(exp_er))} on wages of {rm(basic)}.",
                  f"{rm_sen(five_sen(exp_er))} (5 sen either way is allowed).", five_sen(exp_er) / 100)
    # EIS
    if "eis" in cols and m >= RATES["eis"]["from"] and malaysian:
        exp_er, exp_ee = eis_expected(wage)
        R = RATES["eis"]
        none_paid = all(sen(pay.get(k) or 0) == 0 for k in ("eis", "er_eis") if k in cols)
        if over60:
            exp_er = exp_ee = Decimal(0)
            out.append("EIS: none, as EIS isn't for workers aged 60 or over.")
        elif age is not None and none_paid and (age >= R["exempt_from"] or age < R["min_age"]):
            # Zero is right for a worker under 18, and for one aged 57 or over who had no EIS contributions before 57.
            exp_er = exp_ee = Decimal(0)
            F.add("eis_exempt", "note", s, s, cell("eis"),
                  (f"EIS is 0 for a worker aged {age}: right if they had no EIS contributions before age 57 "
                   "(exempt); otherwise EIS is due until 60.") if age >= R["exempt_from"] else
                  f"EIS is 0 for a worker aged {age}: EIS starts at 18.",
                  "Nothing to do if exempt; else deduct it." if age >= R["exempt_from"] else "Nothing to do.")
            out.append(f"EIS: none taken as right at age {age}.")
        for k, exp, who in (("eis", exp_ee, "Employee"), ("er_eis", exp_er, "Employer")):
            if k in cols and not within(pay.get(k) or 0, exp):
                F.add("eis", "fix", s, s, cell(k),
                      f"{who} EIS is {rm(pay.get(k))}; " + ("EIS isn't paid for a worker aged 60 or over." if over60
                      else f"the table gives {rm_sen(five_sen(exp))} on wages of {rm(basic)}."),
                      f"{rm_sen(five_sen(exp))}.", five_sen(exp) / 100)
    # SKBBK
    if "skbbk" in cols and m >= RATES["skbbk"]["from"]:
        v = pay.get("skbbk") or 0
        exp = skbbk_expected(wage)
        if sen(v) == 0:
            F.add("skbbk_zero", "note", s, s, cell("skbbk"),
                  f"SKBBK (Lindung 24 Jam) is 0: opted out or not yet deducted? check. On these wages it would be "
                  f"{rm_sen(five_sen(exp))}.", "Nothing to do if they opted out; else deduct it.", five_sen(exp) / 100)
        elif not within(v, exp):
            F.add("skbbk", "fix", s, s, cell("skbbk"),
                  f"SKBBK is {rm(v)}; 0.75% of the band midpoint gives about {rm_sen(five_sen(exp))}.",
                  f"{rm_sen(five_sen(exp))} (5 sen either way is allowed).", five_sen(exp) / 100)
    return out


# ---------- the Summary against the payslips ----------

def _summary_checks(sh, S, people, books, F):
    """Each Summary row against its person's payslip, how its figures are linked, its own sums and the totals row.
    Returns the rows read: [{row, sheet, name, nric (masked), values {key: value}, sources {key: where from}}]."""
    cols, g = S["cols"], "Summary"
    by_name = {squash(p.get("name") or ""): t for t, p in people.items() if p.get("name")}
    by_nric = {re.sub(r"\W", "", p.get("nric") or ""): t for t, p in people.items() if p.get("nric")}
    used, out = Counter(), []
    names_typed = []
    for r in S["rows"]:
        here = lambda k: cell_name(cols[k], r)
        vals = {k: sh.num(r, c) for k, c in cols.items() if k not in ("no", "name", "nric")}
        links, kinds = {}, {}
        for k, c in cols.items():
            f = sh.formula(r, c)
            if f:
                x = single_link(f)
                kinds[k] = "link" if x else "formula"
                if x:
                    links[k] = x
                if any(rf["book"] for rf in refs(f)):
                    kinds[k] = "external"
            elif sh.typed_num(r, c) or (sh.text(r, c) or "").strip():
                kinds[k] = "typed"
        # Who the row is for: its name and NRIC cells, else the sheet most of its figures link to.
        who = None
        for k in ("name", "nric"):
            x = links.get(k)
            if x and not x["book"] and x["sheet"] in people:
                who = who or x["sheet"]
        if not who and kinds.get("name") == "typed":
            who = by_name.get(squash(sh.text(r, cols["name"]) or ""))
        if not who and kinds.get("nric") == "typed":
            who = by_nric.get(re.sub(r"\W", "", str(sh.text(r, cols["nric"]) or sh.raw(r, cols["nric"]) or "")))
        votes = Counter(x["sheet"] for k, x in links.items() if k in LINKED and not x["book"] and x["sheet"] in people)
        if not who and votes:
            who = votes.most_common(1)[0][0]
        if not who and not any(vals.get(k) for k in LINKED):
            continue  # an empty row
        name = (sh.text(r, cols["name"]) if "name" in cols else None) or (people[who].get("name") if who else None)
        row = {"row": r, "sheet": who, "name": (name or "").strip(), "nric": mask(people[who].get("nric")) if who else "",
               "values": {k: v for k, v in vals.items()}, "sources": {}}
        out.append(row)
        if not who:
            F.add("summary_person", "check", g, sh.title, cell_name(cols.get("name", cols["basic"]), r),
                  f"Summary row {r} couldn't be matched to a payslip (its name, NRIC and links don't point at one).",
                  "Link the row's name and figures to the person's payslip.")
            continue
        used[who] += 1
        p = people[who]
        if kinds.get("name") == "typed":
            names_typed.append(r)
            if squash(sh.text(r, cols["name"]) or "") != squash(p.get("name") or ""):
                F.add("summary_name", "check", g, sh.title, here("name"),
                      f"The name typed on row {r} isn't the name on {who}'s payslip, whose figures the row takes.",
                      "Check that the row is for the right person, and link the name to the payslip.")
        external = []
        for k, pk in LINKED.items():
            if k not in cols:
                continue
            c = cols[k]
            kind = kinds.get(k)
            x = links.get(k)
            row["sources"][k] = _ref_name(x) if x else ("typed" if kind == "typed" else sh.formula(r, c) or "empty")
            if pk == "insurance":
                want_cell = p["insurance_cell"]
            else:
                want_cell = (p["pay_row"], p["cols"][pk]) if pk in p["cols"] else None
            want = cell_name(want_cell[1], want_cell[0]) if want_cell else None
            want_ref = _ref_name({"sheet": who, "col": get_column_letter(want_cell[1]), "row": want_cell[0]}) if want_cell else None
            linked_wrong = None
            if kind == "external":
                external.append(k)
                row["sources"][k] = "another workbook: " + ", ".join(
                    f"{books.get(rf['book'], 'external workbook ' + str(rf['book']))} ({rf['sheet']}!{rf['col']}{rf['row']})"
                    for rf in refs(sh.formula(r, c)) if rf["book"])
            elif x:
                # A wrong link says how its figure differs today, so the cell isn't counted twice below.
                differs = _differs(vals.get(k), p["pay"].get(pk))
                gives = f"{rm(vals.get(k))} where {p.get('name') or who}'s payslip has {rm(p['pay'].get(pk) or 0)}"
                linked_wrong = len(F)
                if x["sheet"] is None or x["book"]:
                    pass
                elif x["sheet"] != who and x["sheet"] in people:
                    F.add("wrong_person", "fix", g, sh.title, here(k),
                          f"{SUMMARY_LABEL[k]} on row {r} ({p.get('name') or who}) links to {x['sheet']}'s payslip "
                          f"({_ref_name(x)}), another person's"
                          + (" (the same figure today, but it won't follow this person's payslip)." if not differs
                             else f", so it gives {gives}."),
                          f"Link it to ={want_ref}." if want_ref else "Link it to this person's own payslip.",
                          p["pay"].get(pk))
                elif x["sheet"] == who and want and f"{x['col']}{x['row']}" != want:
                    t = p["table"]
                    in_table = t and t["head_row"] < x["row"] <= (t["total_row"] or t["head_row"] + 15)
                    mname = next((MONTH_NAMES[mo - 1].title() for mo, mr in (t["months"].items() if t else []) if mr == x["row"]), None)
                    F.add("month_table_link" if in_table else "wrong_cell", "fix", g, sh.title, here(k),
                          f"{SUMMARY_LABEL[k]} on row {r} links to {_ref_name(x)}, "
                          + (f"a row of the monthly table ({mname})" if in_table and mname else "the monthly table" if in_table
                             else "not the pay row's figure")
                          + (", not this month's pay row (the same figure today)." if not differs
                             else f", not this month's pay row, so it gives {gives}."),
                          f"Link it to ={want_ref}.", p["pay"].get(pk))
                elif x["sheet"] not in people:
                    F.add("wrong_cell", "fix", g, sh.title, here(k),
                          f"{SUMMARY_LABEL[k]} on row {r} links to {_ref_name(x)}, which isn't a payslip checked here"
                          + (f", and gives {gives}." if differs else "."),
                          f"Link it to ={want_ref}." if want_ref else "Link it to the person's payslip.", p["pay"].get(pk))
            elif kind == "typed" and (vals.get(k) or 0) != 0:
                F.add("typed", "check", g, sh.title, here(k),
                      f"{SUMMARY_LABEL[k]} on row {r} ({p.get('name') or who}) is typed ({rm(vals.get(k))}) where the "
                      "other figures are linked, so it won't follow the payslip if that changes.",
                      f"Link it to ={want_ref}." if want_ref else "Link it to the payslip.", p["pay"].get(pk))
            # The value against the payslip's (unless a wrong link above already says so).
            if linked_wrong is not None and len(F) > linked_wrong:
                continue
            if _differs(vals.get(k), p["pay"].get(pk)) and (want or pk == "insurance"):
                F.add("summary_differs", "fix", g, sh.title, here(k),
                      f"{SUMMARY_LABEL[k]} on row {r} is {rm(vals.get(k))} but {who}'s payslip has {rm(p['pay'].get(pk) or 0)}"
                      + (f" ({want})." if want else "."),
                      f"{rm(p['pay'].get(pk))}, from the payslip.", p["pay"].get(pk))
        if external:
            names = sorted({books.get(rf["book"], f"external workbook {rf['book']}") for k in external
                            for rf in refs(sh.formula(r, cols[k])) if rf["book"]})
            F.add("external_link", "fix", g, sh.title, here(external[0]),
                  f"{', '.join(SUMMARY_LABEL[k] for k in external)} on row {r} ({p.get('name') or who}) come from "
                  f"another workbook ({', '.join(names)}): that other file decides them, not this workbook's payslips.",
                  f"Link {'them' if len(external) > 1 else 'it'} to {who}'s pay row in this workbook.",
                  p["pay"].get(LINKED[external[0]]), [here(k) for k in external])
        _row_sums(sh, S, r, vals, g, F, p.get("name") or who)
        odd = [k for k in ("basic", "net", "pay_total", "total_ded", "allowance", "insurance") if k in cols and has_fraction_of_sen(vals.get(k))]
        if odd:
            F.add("unrounded", "fix", g, sh.title, here(odd[0]),
                  f"Row {r} ({p.get('name') or who}) has amounts with more than 2 decimals: "
                  + "; ".join(f"{SUMMARY_LABEL[k]} {rm(vals[k])}" for k in odd) + ".",
                  "Round them to the sen: " + "; ".join(f"{SUMMARY_LABEL[k]} {rm(round(vals[k], 2))}" for k in odd)
                  + " (best on the payslip, so both agree).", round(vals[odd[0]], 2), [here(k) for k in odd])
    if names_typed:
        F.add("typed_name", "note", g, sh.title, cell_name(cols["name"], names_typed[0]),
              f"The name is typed, not linked to the payslip, on row{'s' if len(names_typed) > 1 else ''} "
              f"{', '.join(map(str, names_typed))}.", "Link each name to its payslip (=Sheet!D9) so a row can't be "
              "mixed up.", None, [cell_name(cols["name"], r) for r in names_typed])
    for t, p in people.items():
        if not used[t] and any(p["pay"].get(k) for k in FIGURES):
            F.add("not_on_summary", "check", g, sh.title, None,
                  f"{p.get('name') or t}'s payslip ({t}) has pay this month but no row on the Summary, so it isn't in the "
                  "month's totals.", "Add a row for them, or check that the payslip is meant to be in this workbook.")
        elif used[t] > 1:
            F.add("summary_person", "check", g, sh.title, None,
                  f"{used[t]} Summary rows take their figures from {t}'s payslip.", "Check that each row is a different person.")
    _totals(sh, S, out, F)
    return out


def _row_sums(sh, S, r, vals, g, F, who):
    cols = S["cols"]
    for k, (plus, minus) in SUMS.items():
        if k not in cols or not all(x in cols for x in plus + minus if x != "insurance"):
            continue
        want = sum(vals.get(x) or 0 for x in plus) - sum(vals.get(x) or 0 for x in minus)
        if _differs(vals.get(k), want):
            F.add("summary_sum", "fix", g, sh.title, cell_name(cols[k], r),
                  f"{SUMMARY_LABEL[k]} on row {r} ({who}) is {rm(vals.get(k))} but {SUMS_WORDS[k]} is {rm(want)}.",
                  f"{rm(want)} ({SUMS_WORDS[k]}).", want)


def _totals(sh, S, rows, F):
    """The totals row: each column the sum of the rows above it, without fractions of a sen."""
    tr, cols, g = S["total_row"], S["cols"], "Summary"
    if not tr:
        F.add("summary_total", "check", g, sh.title, None, "The Summary has no Total row.",
              "Add a Total row adding up each column.")
        return
    odd = []
    for k, c in cols.items():
        if k in ("no", "name", "nric"):
            continue
        tot = sh.num(tr, c)
        if tot is None:
            continue
        want = sum(sh.num(r, c) or 0 for r in S["rows"])
        if _differs(tot, want):
            F.add("summary_total", "fix", g, sh.title, cell_name(c, tr),
                  f"The Total of {SUMMARY_LABEL.get(k, k)} is {rm(tot)} but the rows above add up to {rm(want)}.",
                  f"{rm(want)}: check that the SUM covers every row.", want)
        if has_fraction_of_sen(tot):
            odd.append(k)
    if odd:
        k_pay = "pay_total" if "pay_total" in cols else odd[0]
        tot = sh.num(tr, cols[k_pay]) or 0
        rounded_rows = sum(round(sh.num(r, cols[k_pay]) or 0, 2) for r in S["rows"])
        effect = round(rounded_rows - tot, 6)
        F.add("unrounded", "fix", g, sh.title, cell_name(cols[odd[0]], tr),
              "The Total row has amounts with more than 2 decimals: "
              + "; ".join(f"{SUMMARY_LABEL.get(k, k)} {rm(sh.num(tr, cols[k]))}" for k in odd) + ".",
              f"Round each person's figures to the sen; the month's {SUMMARY_LABEL[k_pay]} then is {rm(round(rounded_rows, 2))}, "
              f"{rm(abs(effect))} {'more' if effect > 0 else 'less'} than the {rm(tot)} it shows now.",
              round(rounded_rows, 2), [cell_name(cols[k], tr) for k in odd])


def _external_unused(wf, books, F):
    """A link to another workbook is noted once, naming the cells checked here that use it (each also has its own
    finding to fix)."""
    if books:
        used = [f"{f['sheet']}!{c}" for f in F if f["kind"] == "external_link" for c in f["cells"]]
        F.add("external_file", "note", "", None, None,
              f"This workbook keeps {'links' if len(books) > 1 else 'a link'} to {', '.join(sorted(set(books.values())))}. "
              f"Excel may ask to update {'them' if len(books) > 1 else 'it'} when it is opened. "
              + (f"Cells that take figures from it: {', '.join(used)}." if used
                 else "None of the figures checked here takes anything from it."),
              "Remove links that aren't wanted (Data › Edit Links › Break Link) once every figure comes from this workbook.")


# ---------- the report ----------

def headline(counts):
    """'3 things to fix before paying, 4 to check' (and the notes), or that there is nothing to fix or check."""
    fix, chk, notes = counts.get("fix", 0), counts.get("check", 0), counts.get("note", 0)
    parts = []
    if fix:
        parts.append(f"{fix} thing{'s' if fix > 1 else ''} to fix before paying")
    if chk:
        parts.append(f"{chk} {'thing' + ('s' if chk > 1 else '') + ' ' if not fix else ''}to check")
    head = ", ".join(parts) if parts else "Nothing to fix or check"
    return head + (f"; {notes} note{'s' if notes > 1 else ''}" if notes else "")


def report_of(F, people, info, rows, S, month, wb_month, books):
    """The report kept for a check: {headline, counts, month, workbook_month, groups [{key, title, nric (masked),
    lines, findings}], pay {people [...], totals {...}} in sen, rates_as_at}. No IC number in full."""
    order = {k: i for i, k in enumerate(ORDER)}
    counts = Counter(f["severity"] for f in F)
    groups = []
    summary = [f for f in F if f["group"] == "Summary"]
    groups.append({"key": "Summary", "title": "Summary", "nric": "", "lines": [], "findings": sorted(summary, key=lambda f: order[f["severity"]])})
    for t, p in people.items():
        mine = [f for f in F if f["group"] == t]
        groups.append({"key": t, "title": f"{p['name']} ({t})" if p.get("name") and squash(p["name"]) != squash(t) else (p.get("name") or t), "nric": mask(p.get("nric")),
                       "lines": info.get(t, []), "findings": sorted(mine, key=lambda f: order[f["severity"]])})
    rest = [f for f in F if f["group"] == ""]
    groups.append({"key": "", "title": "The whole workbook", "nric": "", "lines": [], "findings": sorted(rest, key=lambda f: order[f["severity"]])})
    pay_people, totals = [], {"to_pay": 0, **{a: 0 for _, a in AUTHORITIES}}
    for r in rows:
        v = r["values"]
        if not any(v.get(k) for k in ("pay_total", "net", "basic") + tuple(k for k, _ in AUTHORITIES)):
            continue
        row = {"name": r["name"] or (r["sheet"] or f"Row {r['row']}"), "sheet": r["sheet"], "nric": r["nric"], "row": r["row"],
               "to_pay": sen(v.get("pay_total") or 0) if "pay_total" in v else sen((v.get("net") or 0) + (v.get("insurance") or 0) + (v.get("allowance") or 0))}
        for k, a in AUTHORITIES:
            row[a] = sen(v.get(k) or 0) if k in v else 0
        for k in totals:
            totals[k] += row[k]
        pay_people.append(row)
    for r in rows:
        r["values"] = {k: (None if v is None else sen(v)) for k, v in r["values"].items()}
    return {"headline": headline(counts), "counts": {k: counts.get(k, 0) for k in ORDER}, "month": month,
            "workbook_month": wb_month, "groups": groups, "summary_rows": rows,
            "pay": {"people": pay_people, "totals": totals, "authorities": [a for _, a in AUTHORITIES]},
            "linked_files": sorted(set(books.values())), "rates_as_at": RATES["as_at"]}


# ---------- storage ----------

TABLE = """
CREATE TABLE IF NOT EXISTS payroll_checks (
  id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL REFERENCES entities(id), month TEXT NOT NULL,
  document_id INTEGER REFERENCES documents(id), filename TEXT NOT NULL, checked_at TEXT NOT NULL,
  workbook_month TEXT, to_fix INTEGER NOT NULL, to_check INTEGER NOT NULL, notes INTEGER NOT NULL,
  to_pay_sen INTEGER, report TEXT NOT NULL
)"""


def install(con):
    """Update 38: the payroll checks kept (payroll_checks), made empty with its audit triggers before anything goes
    in. Nothing else in the records changes."""
    con.execute(TABLE)
    con.execute("CREATE INDEX IF NOT EXISTS payroll_checks_month ON payroll_checks (entity_id, month)")
    audit.refresh(con)


def ready(con):
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'payroll_checks'").fetchone())


def payroll_task(con, entity_id, month):
    """The month's checklist item that asks for the payroll summary (the payroll calculation item first), or None."""
    found = [t for t in con.execute("SELECT * FROM tasks WHERE entity_id = ? AND month = ? ORDER BY due_date, sort",
                                    (entity_id, month)).fetchall() if "payroll" in json.loads(t["required_docs"] or "[]")]
    found.sort(key=lambda t: t["code"] != "payroll-calc")
    return found[0] if found else None


def save(con, e, month, filename, data, report):
    """Files the workbook as the month's payroll document (on the checklist item asking for it, replacing the
    workbook an earlier check filed there) and keeps the report. Returns the check's id."""
    from .docstore import store
    task = payroll_task(con, e["id"], month)
    folder = f"_Checklist - {task['title']}" if task else "_Payroll check"
    did = store(con, entity=e, month=month, folder=folder, doc_type="payroll", filename=filename, data=data,
                task_id=task["id"] if task else None, note="Uploaded on the Payroll check page")
    before = con.execute("""SELECT d.id FROM payroll_checks c JOIN documents d ON d.id = c.document_id
                            WHERE c.entity_id = ? AND c.month = ? AND d.replaced_by IS NULL AND d.removed_at IS NULL
                              AND d.task_id IS ? AND d.id != ? ORDER BY c.id DESC""",
                         (e["id"], month, task["id"] if task else None, did)).fetchall()
    for (old,) in before:
        con.execute("UPDATE documents SET replaced_by = ? WHERE id = ?", (did, old))
    c = report["counts"]
    cur = con.execute("""INSERT INTO payroll_checks (entity_id, month, document_id, filename, checked_at, workbook_month,
                         to_fix, to_check, notes, to_pay_sen, report) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (e["id"], month, did, filename, db.now(), report["workbook_month"], c["fix"], c["check"], c["note"],
                       report["pay"]["totals"]["to_pay"], json.dumps(report)))
    db.log(con, f"Payroll check for {e['code']} {db.month_label(month)}: {report['headline']} ('{filename}')"
                + (f", filed on {task['title']}" if task else ""))
    return cur.lastrowid


def history(con, entity_id, month):
    """The month's checks, newest first, without their reports."""
    return [dict(r) for r in con.execute(
        """SELECT c.id, c.document_id, c.filename, c.checked_at, c.workbook_month, c.to_fix, c.to_check, c.notes,
                  c.to_pay_sen, d.replaced_by IS NULL AND d.removed_at IS NULL AS current_document
           FROM payroll_checks c LEFT JOIN documents d ON d.id = c.document_id
           WHERE c.entity_id = ? AND c.month = ? ORDER BY c.id DESC""", (entity_id, month))]


def latest(con, entity_id, month):
    r = con.execute("SELECT * FROM payroll_checks WHERE entity_id = ? AND month = ? ORDER BY id DESC LIMIT 1",
                    (entity_id, month)).fetchone()
    return dict(r) if r else None


def view(con, e, month, check_id=None):
    """What the Payroll check page shows for a company and month: the checks (newest first, each with its headline)
    and the report of the one chosen (the latest by default)."""
    if not ready(con):
        return {"ready": False}
    checks = history(con, e["id"], month)
    for x in checks:
        x["headline"] = headline({"fix": x["to_fix"], "check": x["to_check"], "note": x["notes"]})
    chosen = None
    if checks:
        want = check_id or checks[0]["id"]
        r = con.execute("SELECT * FROM payroll_checks WHERE id = ? AND entity_id = ? AND month = ?",
                        (want, e["id"], month)).fetchone()
        if r:
            chosen = {"id": r["id"], "checked_at": r["checked_at"], "filename": r["filename"],
                      "latest": r["id"] == checks[0]["id"], "report": json.loads(r["report"])}
    task = payroll_task(con, e["id"], month)
    return {"ready": True, "entity": {"id": e["id"], "code": e["code"], "name": e["name"]}, "month": month,
            "label": db.month_label(month), "checks": checks, "chosen": chosen,
            "task": {"id": task["id"], "title": task["title"]} if task else None, "rates_as_at": RATES["as_at"]}


# ---------- Excel ----------

def _append(ws, values):
    """A row added to the report, any text from the workbook (a name, a sheet title, a finding quoting a formula)
    kept as text: a value starting with = would otherwise become a live formula in the report."""
    ws.append(values)
    for i, v in enumerate(values, 1):
        if isinstance(v, str) and v.startswith("="):
            ws.cell(ws.max_row, i).data_type = "s"


def workbook(e, month, check):
    """The report of a check as an Excel workbook: the findings, then the month's amounts to pay. IC numbers masked."""
    rep = check["report"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Findings"
    bold = Font(bold=True)
    _append(ws, [f"Payroll check · {e['code']} · {db.month_label(month)}"])
    ws["A1"].font = Font(bold=True, size=13)
    _append(ws, [f"Checked {check['checked_at'].replace('T', ' ')} · {check['filename']}"])
    _append(ws, [rep["headline"]])
    _append(ws, [f"Statutory rates as at {rep['rates_as_at']}. PCB amounts themselves are not checked."])
    _append(ws, [])
    _append(ws, ["Severity", "Where", "Sheet", "Cell", "What is wrong", "What it should be", "Expected (RM)"])
    for c in ws[ws.max_row]:
        c.font = bold
    for g in rep["groups"]:
        for f in g["findings"]:
            _append(ws, [f["severity_label"], g["title"], f["sheet"] or "", ", ".join(f["cells"]) or "", f["what"],
                       f["should"], None if f["expected_sen"] is None else f["expected_sen"] / 100])
            ws.cell(ws.max_row, 7).number_format = "#,##0.00"
    for col, w in zip("ABCDEFG", (18, 26, 14, 12, 70, 50, 14)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=7):
        for c in row[4:6]:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws2 = wb.create_sheet("To pay")
    auth = rep["pay"]["authorities"]
    _append(ws2, ["Name", "NRIC", "Sheet", "To pay (RM)"] + [f"{a} (RM)" for a in auth])
    for c in ws2[1]:
        c.font = bold
    for p in rep["pay"]["people"]:
        _append(ws2, [p["name"], p["nric"], p["sheet"] or "", p["to_pay"] / 100] + [p[a] / 100 for a in auth])
    t = rep["pay"]["totals"]
    _append(ws2, ["Total", "", "", t["to_pay"] / 100] + [t[a] / 100 for a in auth])
    for c in ws2[ws2.max_row]:
        c.font = bold
    for row in ws2.iter_rows(min_row=2, min_col=4):
        for c in row:
            c.number_format = "#,##0.00"
    for col, w in zip("ABCDEFGHI", (28, 18, 14, 14, 12, 12, 12, 12, 12)):
        ws2.column_dimensions[col].width = w
    return wb


def export_name(e, month):
    return f"{e['code']} {month} payroll check.xlsx"
