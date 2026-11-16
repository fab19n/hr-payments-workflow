"""The payroll workbook check (hrp/payrollcheck.py, update 38 and the Payroll check page), on made-up workbooks only.

The workbooks are built here with openpyxl in the layout of the company's monthly payroll workbook: nine payslip
sheets (one shifted down a row, a full-width colon after Month), a Summary sheet and a hidden old template. Excel
saves each formula's value with it, so the values are worked out here and written beside the formulas. One workbook
carries every fault the real October file had; a clean one carries none. Every name, IC number and amount is made up.

Run: .venv\\Scripts\\python -m synthetic_tests.payroll_check_test
"""
import io
import json
import os
import re
import sqlite3
import sys
import tempfile
import zipfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

tmp = Path(tempfile.mkdtemp(prefix="hrp-payroll-check-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from openpyxl import Workbook, load_workbook  # noqa: E402

from hrp import audit, config, db, nextup, payrollcheck as pc  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file


def check(name, ok, detail=""):
    if not ok:
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))
        sys.exit(1)
    print(f"PASS {name}")


# ---------- a made-up workbook in the payroll layout ----------

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEPT", "OCT", "NOV", "DEC"]
L = "CDEFGHIJKLMN"  # the pay table's columns: basic, EPF, SOCSO, EIS, SKBBK, PCB, total ded., allowance, net, employer x3

PEOPLE = [
    # sheet, name, IC, basic, EPF ee/er, SOCSO ee/er, EIS, SKBBK, PCB, allowance, first month, extras
    dict(sheet="Staff A", name="Staff A", nric="900101-14-5555", basic=6000, epf=660, er_epf=720, socso=29.75,
         er_socso=104.15, eis=11.90, skbbk=44.65, pcb=300, allow=200, start=1, insurance=150),
    dict(sheet="SB", name="Staff B", nric="880202-10-6666", basic=7000, epf=770, er_epf=840, socso=29.75, er_socso=104.15,
         eis=11.90, skbbk=0, pcb=450, allow=0, start=4),
    dict(sheet="SC", name="Staff C", nric="850303-08-7777", basic=9500, epf=1045, er_epf=1140, socso=29.75,
         er_socso=104.15, eis=11.90, skbbk=44.65, pcb=1200, allow=0, start=1, skbbk_from=6, shift=1, epf_typed=True),
    dict(sheet="SD", name="Staff D", nric="920404-14-8888", basic=6500, epf=715, er_epf=780, socso=29.75,
         er_socso=104.15, eis=11.90, skbbk=44.65, pcb=380, allow=0, start=1),
    dict(sheet="SE", name="Staff E", nric="950505-10-9999", basic=5500, epf=605, er_epf=660, socso=27.25, er_socso=95.35,
         eis=10.90, skbbk=40.90, pcb=250, allow=0, start=1),
    dict(sheet="SF", name="Staff F", nric="980606-01-1212", basic=3500, epf=385, er_epf=455, socso=17.25, er_socso=60.35,
         eis=6.90, skbbk=25.85, pcb=0, allow=0, start=1, er_typed=True),
    dict(sheet="SG", name="Staff G", nric="680707-07-3434", basic=6000, epf=660, er_epf=720, socso=0, er_socso=74.40,
         eis=11.90, skbbk=44.65, pcb=320, allow=100, start=1),
    dict(sheet="SH", name="Staff H", nric="000808-14-5656", basic=None, monthly=3700, epf=357, er_epf=422, socso=16.25,
         er_socso=56.85, eis=6.50, skbbk=24.35, pcb=0, allow=0, start=10, epf_typed=True, er_typed=True),
    dict(sheet="SI", name="Staff I", nric="870909-10-2323", basic=0, epf=0, er_epf=0, socso=0, er_socso=0, eis=0, skbbk=0,
         pcb=0, allow=0, start=1, leaver=6),
]


def person_sheet(ws, p, faults, month_text="October 2026"):
    """One payslip sheet in the layout: the person block, the pay table (pay row 17), the YTD box, the monthly table
    (rows 40-51, Total 52), all one row lower for a shifted sheet."""
    o = p.get("shift", 0)
    put = lambda ref, v: ws.__setitem__(re.sub(r"\d+", lambda m: str(int(m.group()) + o), ref, count=1), v)
    R = lambda n: n + o
    put("D1", "Example Payroll Sdn Bhd")
    put("D2", "202601000001 (1234567-X)")
    put("C7", "PAYSLIP ")
    put("C8", "Month ：")
    put("D8", month_text)
    put("C9", "Name :")
    put("D9", p["name"])
    put("C10", "Position :")
    put("D10", "Executive")
    put("C11", "Date Joined :")
    put("D11", datetime(2026, p["start"], 1))
    for lab, ref, v in (("NRIC No :", "M8", p["nric"]), ("KWSP No :", "M9", "00000000"), ("TIN No :", "M10", "IG00000000"),
                        ("Bank Detail :", "M11", "Example Bank 000-000")):
        put("L" + ref[1:], lab)
        put(ref, v)
    for hrow in (13, 38):
        put(f"C{hrow}", "Basic \nSalary")
        put(f"D{hrow}", "Employee Deductions")
        put(f"I{hrow}", "Total \nDeduction")
        put(f"J{hrow}", "Transport Allowance")
        put(f"K{hrow}", "Net Pay")
        put(f"L{hrow}", "Employer Contributions")
        for c, t in zip("DEFGHLMN", ("EPF", "SOCSO", "EIS", "SKBBK", "PCB", "EPF", "SOCSO", "EIS")):
            put(f"{c}{hrow + 1}", t)
    put("B38", "Month")
    pr = R(17)
    # The pay row.
    if p.get("monthly"):
        put("A17", p["monthly"])
        put("C17", f"=+A{pr}/31*27" if faults else f"=ROUND(A{pr}/31*27,2)")
        for i, t in enumerate(("Salary as", "per offer", "letter")):
            put(f"A{18 + i}", t)
    else:
        put("C17", p["basic"])
    put("D17", p["epf"] if p.get("epf_typed") or p["basic"] == 0 else f"=C{pr}*0.11")
    put("E17", p["socso"])
    put("F17", p["eis"])
    put("G17", p["skbbk"])
    put("H17", p["pcb"])
    put("I17", f"=SUM(D{pr}:H{pr})")
    put("J17", p["allow"])
    put("K17", f"=C{pr}-I{pr}+J{pr}")
    put("L17", p["er_epf"] if p.get("er_typed") else f"=C{pr}*0.12")
    put("M17", p["er_socso"])
    put("N17", p["eis"])
    if p.get("insurance"):
        put("Q16", "Insurance")
        put("Q17", p["insurance"])
        put("Q19", f"=Q{pr}+K{pr}")
    # The monthly table.
    tot = R(52)
    for i, m in enumerate(MONTHS):
        r = R(40 + i)
        put(f"B{40 + i}", m)
        mo = i + 1
        if mo == 10:
            for c in "CDEFGHJLMN":
                put(f"{c}{40 + i}", f"={c}{pr}")
        elif p["start"] <= mo < 10 and not (p.get("leaver") and mo > p["leaver"]):
            past = dict(p)
            if p.get("leaver"):
                past.update(basic=4000, epf=440, er_epf=520, socso=19.75, er_socso=69.35, eis=7.90, skbbk=0, pcb=0)
            vals = [past["basic"] if past["basic"] is not None else 3700, past["epf"], past["socso"], past["eis"],
                    past["skbbk"] if mo >= p.get("skbbk_from", 1) else 0, past["pcb"], None, past["allow"], None,
                    past["er_epf"], past["er_socso"], past["eis"]]
            for c, v in zip(L, vals):
                if v is not None:
                    put(f"{c}{40 + i}", v)
        if mo != 10:
            put(f"I{40 + i}", f"=SUM(D{r}:H{r})")
            put(f"K{40 + i}", f"=C{r}-I{r}+J{r}")
        else:
            put(f"I{40 + i}", f"=I{pr}")
            put(f"K{40 + i}", f"=K{pr}")
    put("B52", "Total")
    for c in L:
        put(f"{c}52", f"=SUM({c}{R(40)}:{c}{R(51)})")
    # The YTD box.
    put("L22", "YTD Income and Employee Deductions ")
    for c in "EFGH":
        put(f"{c}23", f"=PROPER({c}{R(13)})")
    labels = ["Gross Pay", "Allowance", "Net Pay", "Employee EPF", "Employee SOCSO", "Employee EIS",
              "Employee SKBBK (June 26)" if p.get("skbbk_from") else "Employee SKBBK ", "Employee PCB"]
    good = [f"=C{tot}", f"=J{tot}", f"=K{tot}", f"=D{tot}", f"=E{tot}", f"=F{tot}", f"=G{tot}", f"=H{tot}"]
    for i, (lab, f) in enumerate(zip(labels, good)):
        put(f"L{23 + i}", lab)
        put(f"N{23 + i}", f)
    if p["sheet"] == "Staff A":
        put("P25", f"=N{R(25)}=K{tot}")  # a self-check that holds
    put("K35", "Approved By:")
    if faults and p["sheet"] == "SB":
        put("N23", f"=C{pr}*7")
        put("N26", "=770*7")
    if faults and p["sheet"] == "SC":
        put("N30", "=" + "+".join(["1200"] * 9) + f"+H{pr}")
        put("N27", "=29.75*9")
    if faults and p["sheet"] == "SD":
        put("N25", 50000)
        put("O25", f"=N{R(25)}=K{tot}")
    if faults and p["sheet"] == "SG":
        put("N24", f"=J{pr}")


EXTERNAL = {}  # (sheet, cell) on the other workbook -> value, for [1]OTHERS!D17


def summary_sheet(ws, people, faults, month_line="SALARY FOR THE MONTH OF OCTOBER 2026"):
    ws["B2"] = "Example Payroll Sdn Bhd"
    ws["B4"] = month_line
    for c, t in (("B", "No."), ("C", "NAME"), ("E", "NRIC NO."), ("F", "Basic"), ("G", "D E D U C T I O N"), ("M", "Net"),
                 ("N", "Insurance Premium"), ("O", "Transport Allowance"), ("P", "TOTAL"), ("Q", "E M P L O Y E R"),
                 ("T", "T O T A L")):
        ws[f"{c}6"] = t
    for c, t in zip("GHIJKLQRSTUVW", ("KWSP", "Socso", "EIS", "SKBBK (Lindung 24 Jam）", "e-PCB", "Total", "KWSP", "Socso",
                                      "EIS", "KWSP", "SOCSO", "SKBBK", "EIS")):
        ws[f"{c}7"] = t
    for i, p in enumerate(people):
        r = 8 + i
        s = f"'{p['sheet']}'" if " " in p["sheet"] else p["sheet"]
        pr = 17 + p.get("shift", 0)
        ws[f"B{r}"] = i + 1
        ws[f"C{r}"] = p["name"] if faults and p["sheet"] in ("SH", "SI") else f"={s}!D{9 + p.get('shift', 0)}"
        ws[f"E{r}"] = f"={s}!M{8 + p.get('shift', 0)}"
        ws[f"F{r}"] = f"={s}!C{pr}"
        for c, src in zip("GHIJK", "DEFGH"):
            ws[f"{c}{r}"] = f"={s}!{src}{pr}"
        if p["sheet"] == "SB":
            ws[f"J{r}"] = 0  # SKBBK typed 0, as on the real file
        ws[f"L{r}"] = f"=SUM(G{r}:K{r})"
        ws[f"M{r}"] = f"=F{r}-L{r}"
        ws[f"N{r}"] = f"={s}!Q{pr}" if p.get("insurance") else 0
        ws[f"O{r}"] = f"={s}!J{pr}"
        ws[f"P{r}"] = f"=SUM(M{r}:O{r})"
        for c, src in zip("QRS", "LMN"):
            ws[f"{c}{r}"] = f"={s}!{src}{pr}"
        ws[f"T{r}"] = f"=+Q{r}+G{r}"
        ws[f"U{r}"] = f"=+R{r}+H{r}"
        ws[f"V{r}"] = f"=J{r}"
        ws[f"W{r}"] = f"=+S{r}+I{r}"
        if faults and p["sheet"] == "SD":
            ws[f"I{r}"] = "='Staff A'!F17"  # 1. EIS from another person's sheet
        if faults and p["sheet"] == "SE":
            ws[f"F{r}"] = f"={s}!C47"  # 2. basic from the August row of the monthly table
        if faults and p["sheet"] == "SF":
            for c, src in zip("GHIJ", "DEFG"):
                ws[f"{c}{r}"] = f"=[1]OTHERS!{src}17"  # 3. from another workbook
                EXTERNAL[("OTHERS", f"{src}17")] = {"D": p["epf"], "E": p["socso"], "F": p["eis"], "G": p["skbbk"]}[src]
        if faults and p["sheet"] == "SG":
            ws[f"F{r}"] = p["basic"]  # 4. typed instead of linked
            ws[f"Q{r}"] = p["er_epf"]
    t = 8 + len(people)
    ws[f"B{t}"] = "Total"
    for c in "FGHIJKLMNOPQRSTUVW":
        ws[f"{c}{t}"] = f"=SUM({c}8:{c}{t - 1})"


# A small evaluator for the formulas above, so the values Excel would save can be written beside them.
CELL = re.compile(r"(?:'([^']+)'!|(\[\d+\])?([A-Za-z_][\w]*)!)?\$?([A-Z]{1,3})\$?(\d+)(?::\$?([A-Z]{1,3})\$?(\d+))?")


def evaluate(book, sheet, ref, memo):
    key = (sheet, ref)
    if key in memo:
        return memo[key]
    ws = book[sheet]
    v = ws[ref].value
    if isinstance(v, str) and v.startswith("="):
        f = v[1:]
        if f.startswith("PROPER("):
            memo[key] = None
            return None

        def sub(m):
            qs, ext, us, c1, r1, c2, r2 = m.groups()
            if ext:
                return repr(EXTERNAL[(us, f"{c1}{r1}")])
            sh = qs or us or sheet
            if c2:
                return f"RNG({sh!r}, {c1!r}, {r1}, {c2!r}, {r2})"
            return f"ONE({sh!r}, '{c1}{r1}')"
        expr = CELL.sub(sub, f)
        expr = expr.replace("SUM(", "SUMS(").replace("ROUND(", "round(")
        expr = re.sub(r"(?<![<>=!])=(?!=)", "==", expr)

        def one(sh, r):
            x = evaluate(book, sh, r, memo)
            return 0 if x is None else x

        def rng(sh, c1, r1, c2, r2):
            from openpyxl.utils import column_index_from_string as ci, get_column_letter as gl
            return [evaluate(book, sh, f"{gl(c)}{r}", memo) for c in range(ci(c1), ci(c2) + 1) for r in range(r1, r2 + 1)]

        def sums(*a):
            out = 0
            for x in a:
                for y in (x if isinstance(x, list) else [x]):
                    if isinstance(y, (int, float)) and not isinstance(y, bool):
                        out += y
            return out
        v = eval(expr, {"ONE": one, "RNG": rng, "SUMS": sums, "round": round})
        if isinstance(v, float):
            v = float(f"{v:.15g}")  # Excel keeps 15 significant digits
    memo[key] = v
    return v


def build(faults=True, people=PEOPLE, month_line="SALARY FOR THE MONTH OF OCTOBER 2026", sheet_months=None, summary=True,
          cells=None, other_book=None):
    """The workbook as bytes, with each formula's value saved beside it as Excel saves it. cells: {(sheet, ref): value}
    put in after the layout is built; other_book: {(sheet, ref): value} of the other workbook a [1] link reads."""
    EXTERNAL.clear()
    wb = Workbook()
    wb.remove(wb.active)
    for p in people:
        person_sheet(wb.create_sheet(p["sheet"]), p, faults, (sheet_months or {}).get(p["sheet"], "October 2026"))
    if summary:
        summary_sheet(wb.create_sheet("Summary"), people, faults, month_line)
    for (sheet, ref), v in (cells or {}).items():
        wb[sheet][ref] = v
    EXTERNAL.update(other_book or {})
    old = wb.create_sheet("2024 Template")
    old["C13"] = "Basic \nSalary"
    old["C17"] = 1500
    old["B17"] = "Contractor"
    old.sheet_state = "hidden"
    memo, values = {}, {}
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("="):
                    values[(ws.title, c.coordinate)] = evaluate(wb, ws.title, c.coordinate, memo)
    buf = io.BytesIO()
    wb.save(buf)
    return inject(buf.getvalue(), wb.sheetnames, values,
                  bool(other_book) or (faults and summary and any(p["sheet"] == "SF" for p in people)))


def inject(data, names, values, external):
    """Writes each formula's value into the saved file (and, with external, the link to another workbook)."""
    zin = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    zout = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
    for item in zin.infolist():
        body = zin.read(item.filename)
        m = re.fullmatch(r"xl/worksheets/sheet(\d+)\.xml", item.filename)
        if m:
            title = names[int(m.group(1)) - 1]
            text = body.decode("utf-8")

            def put(mm):
                ref, attrs, f = mm.group(1), mm.group(2), mm.group(3)
                v = values.get((title, ref))
                if v is None:
                    return mm.group(0)
                if isinstance(v, bool):
                    return f'<c r="{ref}"{attrs} t="b"><f>{f}</f><v>{int(v)}</v></c>'
                if isinstance(v, str):
                    return f'<c r="{ref}"{attrs} t="str"><f>{f}</f><v>{escape(v)}</v></c>'
                return f'<c r="{ref}"{attrs}><f>{f}</f><v>{repr(float(v)) if isinstance(v, float) else v}</v></c>'
            text = re.sub(r'<c r="([A-Z]+\d+)"([^>]*)><f>(.*?)</f><v\s*/></c>', put, text)
            body = text.encode("utf-8")
        if external and item.filename == "xl/workbook.xml":
            body = body.replace(b"</sheets>", b'</sheets><externalReferences><externalReference r:id="rIdX1"/></externalReferences>')
        if external and item.filename == "xl/_rels/workbook.xml.rels":
            body = body.replace(b"</Relationships>", b'<Relationship Id="rIdX1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLink" Target="externalLinks/externalLink1.xml"/></Relationships>')
        if external and item.filename == "[Content_Types].xml":
            body = body.replace(b"</Types>", b'<Override PartName="/xl/externalLinks/externalLink1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.externalLink+xml"/></Types>')
        zout.writestr(item, body)
    if external:
        zout.writestr("xl/externalLinks/externalLink1.xml",
                      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><externalLink xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><externalBook r:id="rId1"><sheetNames>'
                      '<sheetName val="OTHERS"/></sheetNames><sheetDataSet><sheetData sheetId="0"/></sheetDataSet></externalBook></externalLink>')
        zout.writestr("xl/externalLinks/_rels/externalLink1.xml.rels",
                      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                      '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLinkPath" '
                      'Target="Old%20payroll%20copy.xlsx" TargetMode="External"/></Relationships>')
    zout.close()
    return out.getvalue()


def found(rep):
    return [f for g in rep["groups"] for f in g["findings"]]


def key(f):
    return (f["kind"], f["sheet"], f["cell"], f["severity"], f["expected_sen"])


# ---------- 1. the statutory figures, on the pairs checked against the real October figures ----------

for wage, ee, er in ((6000, 660, 720), (7000, 770, 840), (9500, 1045, 1140), (6500, 715, 780), (5500, 605, 660),
                     (3500, 385, 455), (3222.58, 357, 422)):
    got = pc.epf_expected(pc.sen(wage))
    check(f"EPF on RM {wage:,}: {ee} / {er}", got == (ee * 100, er * 100), got)
check("EPF aged 60 and over: employee nothing, employer 4% of the band's top", pc.epf_expected(600000, True) == (0, 24000))
check("EPF band edges: RM 3,220.01 counts as RM 3,240, RM 5,900.01 as RM 6,000",
      pc.epf_expected(322001)[0] == 35700 and pc.epf_expected(590001) == (66000, 72000))
check("EPF: 13% up to RM 5,000, 12% above", pc.epf_expected(500000)[1] == 65000 and pc.epf_expected(500001)[1] == 61200)
for mid, er, ee in ((5950, "104.15", "29.75"), (5450, "95.35", "27.25"), (3450, "60.35", "17.25"), (3250, "56.85", "16.25")):
    wage = (mid + 50) * 100
    e_er, e_ee = pc.socso_expected(wage)
    check(f"SOCSO first category on the RM {mid:,} midpoint: {er} / {ee} within 5 sen",
          pc.band_midpoint(wage) == mid * 100 and pc.within(float(er), e_er) and pc.within(float(ee), e_ee), (e_er, e_ee))
check("SOCSO wages above RM 6,000 count as the RM 5,950 midpoint", pc.band_midpoint(950000) == 595000)
s_er, s_ee = pc.socso_expected(600000, second=True)
check("SOCSO second category on RM 5,950: 74.40 / 0", pc.within(74.40, s_er) and s_ee == 0, (s_er, s_ee))
check("SOCSO's 5 sen tolerance: 6 sen off fails", not pc.within(104.19, pc.socso_expected(600000)[0]))
for mid, v in ((5950, "11.90"), (5450, "10.90"), (3450, "6.90"), (3250, "6.50")):
    e_er, e_ee = pc.eis_expected((mid + 50) * 100)
    check(f"EIS on the RM {mid:,} midpoint: {v} each", pc.within(float(v), e_er) and pc.within(float(v), e_ee))
for mid, v in ((5950, "44.65"), (3450, "25.85"), (3250, "24.35")):
    check(f"SKBBK on the RM {mid:,} midpoint: {v}", pc.within(float(v), pc.skbbk_expected((mid + 50) * 100)))
check("the rates are in one dated table, as at Nov 2026", pc.RATES["as_at"] == "Nov 2026" and all("from" in pc.RATES[k] for k in ("epf", "socso", "eis", "skbbk")))
check("age from a Malaysian IC: born 1965 is 61 in October 2026", pc.born("650101-14-1111", "2026-10") == (True, 61))
check("age from a Malaysian IC: born 2000 is 26", pc.born("000808-14-5656", "2026-10") == (True, 26))
check("a passport number isn't a Malaysian IC", pc.born("K1234567", "2026-10") == (False, None))
check("an IC is masked but for its last 4", pc.mask("900101-14-5555") == "••••••-••-5555" and pc.mask("K1234567") == "••••4567")
check("the full-width colon and spaced headings read as plain ones",
      pc.squash("Month ：") == "month" and pc.squash("D E D U C T I O N") == "deduction" and pc.month_word("SEPT") == 9)

# ---------- 2. the workbook with every fault ----------

BAD = build(True)
rep = pc.check(BAD, "2026-10", "Example Payroll - OCT 2026.xlsx")
F = found(rep)
keys = {key(f) for f in F}


def pay_of(p, wage=None):
    """What a person is paid this month as the Summary works it out: basic less deductions, plus insurance and allowance."""
    basic = wage if wage is not None else p["basic"]
    return basic - (p["epf"] + p["socso"] + p["eis"] + p["skbbk"] + p["pcb"]) + p.get("insurance", 0) + p["allow"]


P_ = {p["sheet"]: p for p in PEOPLE}
total_rounded = round(sum(round(pay_of(p, 3700 / 31 * 27 if p.get("monthly") else None), 2) for p in PEOPLE), 2)
expected = {
    ("wrong_person", "Summary", "I11", "fix", 1190),       # 1. EIS from another person's sheet
    ("month_table_link", "Summary", "F12", "fix", 550000),  # 2. basic from the August row
    ("external_link", "Summary", "G13", "fix", 38500),      # 3. from another workbook
    ("typed", "Summary", "F14", "check", 600000),           # 4. typed instead of linked
    ("typed", "Summary", "Q14", "check", 72000),
    ("typed_name", "Summary", "C15", "note", None),         # 5. names typed
    ("no_pay", "SI", "C17", "note", None),                  # 6. a leaver kept as zeros
    ("unrounded", "SH", "C17", "fix", 322258),              # 7. fractions of a sen
    ("unrounded", "Summary", "F15", "fix", 322258),
    ("unrounded", "Summary", "F17", "fix", pc.sen(total_rounded)),
    ("ytd_formula", "SB", "N23", "check", None),            # 8. YTD built to go wrong next month
    ("ytd_formula", "SB", "N26", "check", None),
    ("ytd_formula", "SC", "N31", "check", None),
    ("ytd", "SC", "N28", "fix", 29750),
    ("ytd", "SD", "N25", "fix", pc.sen(10 * pay_of(P_["SD"]))),
    ("self_check", "SD", "O25", "check", None),
    ("ytd", "SG", "N24", "fix", 100000),
    ("skbbk_zero", "SB", "G17", "note", 4465),
    ("hidden_sheet", "2024 Template", None, "note", None),
    ("pcb_not_checked", None, None, "note", None),
    ("external_file", None, None, "note", None),
}
check("every seeded fault is found, with its sheet, cell, severity and expected figure", expected <= keys,
      sorted(map(str, expected - keys)))
check("and nothing else is found", keys == expected, sorted(map(str, keys - expected)))
check("no finding is given twice", len(F) == len(keys), len(F))
by = {key(f): f for f in F}
ext = by[("external_link", "Summary", "G13", "fix", 38500)]
check("the other workbook is named, with every figure it decides", ext["cells"] == ["G13", "H13", "I13", "J13"]
      and "Old payroll copy.xlsx" in ext["what"] and "decides them" in ext["what"], ext)
wp = by[("wrong_person", "Summary", "I11", "fix", 1190)]
check("the wrong-person link names whose sheet it is and where it should point",
      "Staff A" in wp["what"] and "=SD!F17" in wp["should"] and "same figure today" in wp["what"], wp)
mt = by[("month_table_link", "Summary", "F12", "fix", 550000)]
check("the month-table link says which month's row", "August" in mt["what"] and "=SE!C17" in mt["should"], mt)
check("the shifted sheet is read by its headings (pay row 18)", "=SC!" not in json.dumps([f for f in F if f["sheet"] == "Summary"]))
ur = by[("unrounded", "SH", "C17", "fix", 322258)]
check("the unrounded pay row names each cell and the rounded figure", ur["cells"] == ["C17", "K17"] and "RM 3,222.58" in ur["should"], ur)
tot = by[("unrounded", "Summary", "F17", "fix", pc.sen(total_rounded))]
check("the Total row's rounding gives the effect on the month's total", tot["cells"] == ["F17", "M17", "P17"]
      and "TOTAL then is" in tot["should"] and "than the" in tot["should"], tot)
check("the typed names are one note naming both rows", by[("typed_name", "Summary", "C15", "note", None)]["cells"] == ["C15", "C16"])
yf = by[("ytd_formula", "SB", "N23", "check", None)]
check("a YTD multiplier says it will go wrong next month", "next month" in yf["what"] and "*7" in yf["what"], yf)
check("a typed list of past amounts is named as one", "typed list" in by[("ytd_formula", "SC", "N31", "check", None)]["what"])
yd = by[("ytd", "SC", "N28", "fix", 29750)]
check("a YTD that differs names both figures", "RM 267.75" in yd["what"] and "RM 297.50" in yd["what"], yd)
check("the SKBBK 0 note asks whether they opted out", "opted out or not yet deducted? check" in by[("skbbk_zero", "SB", "G17", "note", 4465)]["what"])
check("no statutory figure is called wrong on the real-figure rows",
      not [f for f in F if f["kind"] in ("epf", "socso", "eis", "skbbk", "rate_group")])
check("the clean person and row give nothing", not [f for f in F if f["sheet"] in ("Staff A", "SE", "SF")]
      and not [f for f in F if f["sheet"] == "Summary" and re.fullmatch(r"[A-Z]+(8|9|10)", f["cell"] or "")])
check("the headline counts what to fix and check", rep["headline"] == "9 things to fix before paying, 6 to check; 6 notes"
      and rep["counts"] == {"fix": 9, "check": 6, "note": 6}, rep["headline"])
g = {x["key"]: x for x in rep["groups"]}
check("the report is grouped: Summary first, then each person, then the whole workbook",
      rep["groups"][0]["key"] == "Summary" and rep["groups"][-1]["key"] == "" and "SG" in g)
check("each group lists Fix before paying first", all([f["severity"] for f in x["findings"]] == sorted(
    [f["severity"] for f in x["findings"]], key=pc.ORDER.index) for x in rep["groups"]))
check("the second SOCSO category is inferred and said", any("second category" in ln for ln in g["SG"]["lines"]))
check("the first category is said too", any("first category assumed" in ln for ln in g["Staff A"]["lines"]))
pay = rep["pay"]
check("the amounts to pay come from the Summary, per person and per authority", len(pay["people"]) == 8
      and pay["authorities"] == ["KWSP", "SOCSO", "EIS", "SKBBK", "PCB"]
      and pay["people"][0]["KWSP"] == 138000 and pay["people"][0]["SOCSO"] == 13390 and pay["people"][0]["to_pay"] == 530370,
      pay["people"][0])
check("the totals add up the people", all(pay["totals"][k] == sum(p[k] for p in pay["people"]) for k in pay["totals"]))
dump = json.dumps(rep, ensure_ascii=False)
check("the report never holds an IC number in full", not any(p["nric"] in dump or p["nric"].replace("-", "") in dump for p in PEOPLE)
      and "••••••-••-5555" in dump)

# ---------- 3. the clean workbook ----------

GOOD = build(False)
clean = pc.check(GOOD, "2026-10", "clean.xlsx")
ck = {(f["kind"], f["sheet"], f["cell"]) for f in found(clean)}
check("a clean workbook has nothing to fix or check", clean["counts"]["fix"] == 0 and clean["counts"]["check"] == 0, sorted(map(str, ck)))
check("only the notes that are true of it", ck == {("hidden_sheet", "2024 Template", None), ("pcb_not_checked", None, None),
                                                    ("skbbk_zero", "SB", "G17"), ("no_pay", "SI", "C17")}, sorted(map(str, ck)))

# ---------- 3b. fixes from the review of the check ----------

# The 60-and-over rates start with the month after the 60th birthday's month, whatever the day.
check("60-and-over rates from the month after the 60th birthday",
      pc.sixty_rates_from("661005-14-5555", "2026-10") == "2026-11" and pc.sixty_rates_from("661031-14-5555", "2026-10") == "2026-11"
      and pc.sixty_rates_from("661201-14-5555", "2026-10") == "2027-01" and pc.sixty_rates_from("K1234567", "2026-10") is None)


def with_person(sheet, **change):
    return [dict(p, **change) if p["sheet"] == sheet else p for p in PEOPLE]


r = pc.check(build(False, people=with_person("Staff A", nric="661005-14-5555")), "2026-10", "x.xlsx")
g60 = {x["key"]: x for x in r["groups"]}["Staff A"]
check("turning 60 during the payroll month: the correct under-60 figures give nothing to fix",
      not g60["findings"] and r["counts"]["fix"] == 0 and any("Turns 60 this month" in ln for ln in g60["lines"])
      and any("under 60" in ln for ln in g60["lines"]), (g60["findings"], g60["lines"]))
over = dict(nric="660905-14-5555", epf=0, er_epf=240, socso=0, er_socso=74.40, eis=0, epf_typed=True, er_typed=True)
r = pc.check(build(False, people=with_person("Staff A", **over)), "2026-10", "x.xlsx")
g60 = {x["key"]: x for x in r["groups"]}["Staff A"]
check("turned 60 the month before: the 60-and-over figures give nothing to fix",
      not g60["findings"] and any("aged 60 or over" in ln for ln in g60["lines"]), g60["findings"])
r = pc.check(build(False, people=with_person("Staff A", **dict(over, nric="660930-14-5555"))), "2026-10", "x.xlsx")
check("a birthday on the 30th switches the month after too, like one on the 5th",
      not {x["key"]: x for x in r["groups"]}["Staff A"]["findings"])
r = pc.check(build(False, people=with_person("Staff A", nric="661030-14-5555")), "2026-10", "x.xlsx")
check("and in the month of a 30th birthday the under-60 figures are still right",
      not {x["key"]: x for x in r["groups"]}["Staff A"]["findings"])

# A payslip figure taken from another workbook is to fix, and the workbook's note names the cell.
r = pc.check(build(False, cells={("Staff A", "C17"): "=[1]OTHERS!C17"}, other_book={("OTHERS", "C17"): 6000}), "2026-10", "x.xlsx")
ext = [f for f in found(r) if f["kind"] == "external_link"]
note = [f for f in found(r) if f["kind"] == "external_file"]
check("a payslip's basic pay from another workbook is to fix, naming the cell and the file",
      len(ext) == 1 and ext[0]["sheet"] == "Staff A" and ext[0]["cells"] == ["C17"] and ext[0]["severity"] == "fix"
      and "Old payroll copy.xlsx" in ext[0]["what"] and "Basic salary" in ext[0]["what"] and r["counts"]["fix"] == 1, ext)
check("the workbook's note on the link names the cell that uses it", len(note) == 1 and "Staff A!C17" in note[0]["what"], note)
check("the Summary's link from another workbook is named in that note too",
      "Summary!G13" in [f for f in F if f["kind"] == "external_file"][0]["what"])

# Year-to-date formulas: only the Total or a sum of every month row is sound; ROUND around it is fine.
r = pc.check(build(False, cells={("Staff A", "N23"): "=SUM(C40:C49)", ("SH", "N23"): "=C49", ("SH", "N30"): "=H49",
                                 ("Staff A", "N24"): "=ROUND(J52,2)", ("Staff A", "N26"): "=ROUND(SUM(D40:D51),2)",
                                 ("SD", "N23"): "=" + "+".join(f"C{x}" for x in range(40, 52))}), "2026-10", "x.xlsx")
yk = {(f["kind"], f["sheet"], f["cell"]): f for f in found(r) if f["kind"] in ("ytd", "ytd_formula")}
check("a YTD over part of the table, or one month's row, is to check: it goes wrong next month",
      set(yk) == {("ytd_formula", "Staff A", "N23"), ("ytd_formula", "SH", "N23"), ("ytd_formula", "SH", "N30")}
      and all("takes only some months of the table" in f["what"] and "next month" in f["what"] for f in yk.values()),
      sorted(map(str, yk)))
check("a rounded Total, a rounded full sum and every month added one by one are sound",
      not {k for k in yk if k[2] in ("N24", "N26") or k[1] == "SD"})
check("the review's own cases straight on the rule",
      pc._ytd_fragile("=ROUND(C52,2)", None, 3, 40, 51, 17, 52) is None
      and pc._ytd_fragile("=SUM(C40:C51)", None, 3, 40, 51, 17, 52) is None
      and pc._ytd_fragile("=C52", None, 3, 41, 52, 18, 53) is not None
      and "only some months" in pc._ytd_fragile("=SUM(C41:C50)", None, 3, 41, 52, 18, 53)
      and pc._ytd_fragile("=SUM(C41:C52)", None, 3, 41, 52, 18, 53) is None)

# One wrong link on the Summary is one thing to fix, saying how its figure differs.
r = pc.check(build(True, cells={("Summary", "I11"): "=SE!F17"}), "2026-10", "x.xlsx")
i11 = [f for f in found(r) if f["sheet"] == "Summary" and f["cell"] == "I11"]
check("a link to another person's different figure is one finding, giving both figures",
      len(i11) == 1 and i11[0]["kind"] == "wrong_person" and "RM 10.90" in i11[0]["what"] and "RM 11.90" in i11[0]["what"]
      and r["counts"]["fix"] == rep["counts"]["fix"], [(f["kind"], f["what"]) for f in i11])

# The rounding advice and the EPF finding never give different EPF figures.
r = pc.check(build(True, cells={("SH", "D17"): "=C17*0.11"}), "2026-10", "x.xlsx")
sh_f = {f["kind"]: f for f in found(r) if f["sheet"] == "SH"}
ur = sh_f.get("unrounded")
check("the EPF finding gives the Third Schedule's figure", sh_f.get("epf") and sh_f["epf"]["expected_sen"] == 35700, sh_f.get("epf"))
check("the rounding advice leaves EPF to it and works the deductions and net pay out from RM 357.00",
      ur and ur["cells"] == ["C17", "I17", "K17"] and "354.48" not in ur["should"] and "RM 404.10" in ur["should"]
      and "RM 2,818.48" in ur["should"] and "RM 357.00" in ur["should"] and "EPF also" in ur["what"], ur)

# Text from the workbook in the Excel report stays text, never a live formula.
import copy  # noqa: E402
evil = '=HYPERLINK("http://evil.example","x")'
rep2 = copy.deepcopy(rep)
rep2["pay"]["people"][0].update(name=evil, sheet="=A1")
rep2["groups"][0]["title"] = evil
rep2["groups"][0]["findings"][0].update(what=evil, should="=1+1", sheet="=B2")
buf = io.BytesIO()
pc.workbook({"code": "AISB"}, "2026-10", {"report": rep2, "checked_at": "2026-11-17T10:00", "filename": "=3+3.xlsx"}).save(buf)
xb = load_workbook(io.BytesIO(buf.getvalue()))
formulas = [(ws.title, c.coordinate) for ws in xb.worksheets for row in ws.iter_rows() for c in row if c.data_type == "f"]
check("the Excel report keeps a name or finding starting with = as text", not formulas
      and xb["To pay"]["A2"].value == evil and xb["Findings"]["B7"].value == evil, formulas)

# ---------- 4. months, and files that can't be checked ----------

r = pc.check(GOOD, "2026-11", "clean.xlsx")
check("a workbook for another month than the one chosen is to fix before paying",
      [(f["kind"], f["severity"]) for f in found(r) if f["kind"] == "workbook_month"] == [("workbook_month", "fix")])
check("its payslips are compared with the workbook's own month, not each flagged", not [f for f in found(r) if f["kind"] == "sheet_month"])
r = pc.check(build(False, sheet_months={"SE": "September 2026"}), "2026-10", "x.xlsx")
check("a payslip showing another month than the workbook's is to fix",
      {(f["kind"], f["sheet"], f["cell"], f["severity"]) for f in found(r) if f["kind"] == "sheet_month"} == {("sheet_month", "SE", "D8", "fix")})


def refused(name, fn, words):
    try:
        fn()
    except pc.Refused as ex:
        check(name, words in str(ex), str(ex))
        return
    check(name, False, "not refused")


refused("a file that isn't .xlsx is refused", lambda: pc.check(b"%PDF-1.4", "2026-10", "payroll.pdf"), ".xlsx")
refused("bytes that aren't a workbook are refused", lambda: pc.check(b"not a workbook", "2026-10", "payroll.xlsx"), "isn't an Excel workbook")
refused("a workbook with no Summary is refused", lambda: pc.check(build(False, summary=False), "2026-10", "p.xlsx"), "no sheet named Summary")
lone = Workbook()
lone.active.title = "Summary"
lone.active["C6"], lone.active["F6"] = "NAME", "Basic"
buf = io.BytesIO()
lone.save(buf)
refused("a workbook with no payslip sheets is refused", lambda: pc.check(buf.getvalue(), "2026-10", "p.xlsx"), "No sheet")
was = pc.MAX_BYTES
pc.MAX_BYTES = 1000
refused("a file over the size limit is refused", lambda: pc.check(GOOD, "2026-10", "p.xlsx"), "larger than")
pc.MAX_BYTES = was

# ---------- 5. update 38 ----------

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "AISB", "name": "Example Payroll Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-777"}]},
]}), encoding="utf-8")


def q(sql, args=()):
    with sqlite3.connect(config.DB_PATH) as r:
        r.row_factory = sqlite3.Row
        return [dict(x) for x in r.execute(sql, args)]


full = db.MIGRATIONS[:]
check("update 38 is the payroll checks", len(full) == 38)
db.MIGRATIONS[:] = full[:37]
db.init()
check("below update 38 there is no payroll checks table", not q("SELECT 1 FROM sqlite_master WHERE name = 'payroll_checks'"))
db.MIGRATIONS[:] = full
trail = db.init()
check("update 38 runs", q("PRAGMA user_version")[0]["user_version"] == 38)
check("the payroll checks table is made empty, with its audit triggers",
      q("SELECT COUNT(*) AS n FROM payroll_checks")[0]["n"] == 0
      and q("SELECT COUNT(*) AS n FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'audit_payroll_checks%'")[0]["n"] >= 3)
with db.connect() as r_:
    v = audit.verify(r_)
check("the audit trail checks out after update 38", v["ok"], v)
check("start-up repaired nothing", trail and not trail["triggers_repaired"] and not trail["late_sealed"], trail)
trail = db.init()
check("a second start repairs nothing either", trail and not trail["triggers_repaired"] and not trail["late_sealed"], trail)

# ---------- 6. the page's routes ----------

c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}
EID = q("SELECT id FROM entities WHERE code = 'AISB'")[0]["id"]


def j(method, path, expect=200, **kw):
    resp = getattr(c, method)(BASE + path, headers=H, **kw)
    assert resp.status_code == expect, (method, path, resp.status_code, resp.data[:800])
    return resp.get_json()


def upload(data, name, month="2026-10", expect=200):
    return j("post", "/api/payroll-check", expect, data={"file": (io.BytesIO(data), name), "entity_id": str(EID), "month": month},
             content_type="multipart/form-data")


def footprint():
    return (q("SELECT COUNT(*) AS n FROM audit_row")[0]["n"], q("SELECT COUNT(*) AS n FROM audit_tx")[0]["n"],
            q("SELECT COUNT(*) AS n FROM activity")[0]["n"])


j("post", "/api/months/open", json={"entity_id": EID, "month": "2026-10"})
task = q("SELECT * FROM tasks WHERE entity_id = ? AND month = '2026-10' AND code = 'payroll-calc'", (EID,))[0]
check("the month's payroll item asks for the payroll summary", json.loads(task["required_docs"]) == ["payroll"])
before = footprint()
d = j("get", f"/api/payroll-check?entity_id={EID}&month=2026-10")
check("before any check the page says there is none, and looking writes nothing",
      d["checks"] == [] and d["chosen"] is None and d["task"]["id"] == task["id"] and footprint() == before)
j("get", f"/api/payroll-check?entity_id={EID}&month=2026-13", 400)

docs0 = q("SELECT COUNT(*) AS n FROM documents")[0]["n"]
e = upload(b"%PDF-1.4 not a workbook", "payroll.pdf", expect=400)
check("a PDF is refused with a sentence, and nothing is kept", ".xlsx" in e["error"]
      and q("SELECT COUNT(*) AS n FROM documents")[0]["n"] == docs0 and not q("SELECT 1 FROM payroll_checks"))
e = upload(build(False, summary=False), "nosummary.xlsx", expect=400)
check("a workbook with no Summary is refused and nothing is kept", "Summary" in e["error"]
      and q("SELECT COUNT(*) AS n FROM documents")[0]["n"] == docs0)

d = upload(BAD, "Example Payroll - OCT 2026.xlsx")
first = d["chosen"]
check("the check is kept and shown", first["latest"] and first["report"]["counts"]["fix"] == 9 and len(d["checks"]) == 1)
doc1 = q("SELECT * FROM documents WHERE id = ?", (d["checks"][0]["document_id"],))[0]
check("the workbook is filed as the month's payroll document on the payroll item",
      doc1["doc_type"] == "payroll" and doc1["task_id"] == task["id"] and doc1["month"] == "2026-10")
with db.connect() as r_:
    st = db.task_status(r_, r_.execute("SELECT * FROM entities WHERE id = ?", (EID,)).fetchone(),
                        r_.execute("SELECT * FROM tasks WHERE id = ?", (task["id"],)).fetchone())
check("the checklist's payroll summary need is met by it", "payroll" not in st["missing"], st)
row = q("SELECT * FROM payroll_checks")[0]
check("integer sen and the counts are kept with the report", row["to_fix"] == 9 and row["to_check"] == 6 and row["notes"] == 6
      and isinstance(row["to_pay_sen"], int) and row["to_pay_sen"] == first["report"]["pay"]["totals"]["to_pay"])
tx = q("SELECT * FROM audit_row WHERE tbl = 'payroll_checks'")
check("the check is in the audit trail", len(tx) == 1 and tx[0]["op"] == "insert")
check("no IC number in full is in the records' trail or report",
      not any(p["nric"] in json.dumps(q("SELECT * FROM audit_row")) or p["nric"] in row["report"] for p in PEOPLE))

# Next up: one line, to the page, with no name or amount.
rows15 = [x for x in nextup.items(db.connect(), date(2026, 11, 5)) if x["rule"] == 15]
check("Next up says the payroll check has things to fix, in one line with a link",
      len(rows15) == 1 and rows15[0]["text"] == "Oct AISB: the payroll check found 9 things to fix before paying"
      and rows15[0]["go"]["view"] == "payroll" and rows15[0]["go"]["month"] == "2026-10" and rows15[0]["priority"] == 1, rows15)
ov = c.get(BASE + "/api/overview?month=2026-10", headers=H).get_data(as_text=True)
check("the Overview shows nothing from payroll", "Staff" not in ov and "5555" not in ov and "•" not in ov)

# The page never shows an IC in full.
page = c.get(BASE + f"/api/payroll-check?entity_id={EID}&month=2026-10", headers=H).get_data(as_text=True)
check("the page's data holds masked ICs only", not any(p["nric"] in page for p in PEOPLE) and "5555" in page)

# Excel export, and its read in the trail.
reads = q("SELECT COUNT(*) AS n FROM audit_row WHERE tbl = 'read'")[0]["n"]
resp = c.get(BASE + f"/api/payroll-check/export.xlsx?entity_id={EID}&month=2026-10", headers=H)
check("the report exports as Excel", resp.status_code == 200 and resp.mimetype.endswith("spreadsheetml.sheet"))
xb = load_workbook(io.BytesIO(resp.data))
fx = [r_ for r_ in xb["Findings"].iter_rows(values_only=True)]
check("the Excel report has the headline and every finding with its cell", fx[2][0] == first["report"]["headline"]
      and sum(1 for r_ in fx[6:] if r_[0]) == 21 and any(r_[3] == "I11" and r_[0] == "Fix before paying" for r_ in fx))
tp = [r_ for r_ in xb["To pay"].iter_rows(values_only=True)]
check("and the amounts to pay, ICs masked", tp[0][:4] == ("Name", "NRIC", "Sheet", "To pay (RM)") and tp[1][1] == "••••••-••-5555"
      and tp[-1][0] == "Total" and not any(p["nric"] in str(tp) for p in PEOPLE))
check("opening the export is noted in the trail", q("SELECT COUNT(*) AS n FROM audit_row WHERE tbl = 'read'")[0]["n"] == reads + 1)

# Check again after a corrected file.
d = upload(GOOD, "Example Payroll - OCT 2026 corrected.xlsx")
check("Check again keeps the earlier result as an earlier version", len(d["checks"]) == 2 and d["chosen"]["latest"]
      and d["checks"][0]["to_fix"] == 0 and d["checks"][1]["to_fix"] == 9)
docs = q("SELECT * FROM documents WHERE task_id = ? ORDER BY id", (task["id"],))
check("the corrected workbook replaces the earlier one on the payroll item", len(docs) == 2 and docs[0]["replaced_by"] == docs[1]["id"]
      and docs[1]["replaced_by"] is None)
old = j("get", f"/api/payroll-check?entity_id={EID}&month=2026-10&check={first['id']}")
check("the earlier version can still be shown", old["chosen"]["id"] == first["id"] and not old["chosen"]["latest"]
      and old["chosen"]["report"]["counts"]["fix"] == 9)
j("get", f"/api/payroll-check?entity_id={EID}&month=2026-09&check={first['id']}", 404)
check("Next up's line goes once the latest check has nothing to fix",
      not [x for x in nextup.items(db.connect(), date(2026, 11, 5)) if x["rule"] == 15])
check("the activity log says what each check found",
      len(q("SELECT * FROM activity WHERE what LIKE 'Payroll check for AISB October 2026: %'")) == 2)
with db.connect() as r_:
    v = audit.verify(r_)
check("the audit trail checks out at the end", v["ok"], v)

print(f"All payroll check checks passed. Records folder used: {tmp}")
