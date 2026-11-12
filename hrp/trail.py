"""The audit trail from the command line, until it has a page of its own.

  .venv\\Scripts\\python -m hrp.trail status          what the trail holds and what needs attention
  .venv\\Scripts\\python -m hrp.trail verify          recompute every entry's fingerprint (can take a while)
  .venv\\Scripts\\python -m hrp.trail accept "why"    seal changes made outside the app, with the reason given

Works on the records folder the app uses (settings.json, or HRP_DATA_DIR). Close the app first for accept.
"""
import sys

from . import audit, db
from .config import DATA_DIR


def main(argv):
    if not argv or argv[0] not in ("status", "verify", "accept"):
        print(__doc__)
        return 2
    con = db.connect()
    if not audit.present(con):
        print(f"The records in {DATA_DIR} have no audit trail yet. Start the app once to add it.")
        return 1
    if argv[0] == "accept":
        reason = " ".join(argv[1:]).strip()
        if not reason:
            print('Say why the changes were made, e.g.: python -m hrp.trail accept "Corrected a payee name in DB Browser"')
            return 2
        con.arm("user", "Accepted changes made outside this app (command line)", reason=reason)
        n = audit.accept_outside(con, reason)  # the command line names the count first: python -m hrp.trail status
        con.commit()
        con.disarm()
        print(f"Accepted {n} change(s) made outside the app." if n else "There were no changes made outside the app to accept.")
        return 0
    v = audit.verify(con, last=None if argv[0] == "verify" else 200)
    st = audit.status(con)
    print(f"Records folder: {DATA_DIR}\nEntries: {st['entries']}   Check code: {st['check_code']}   "
          f"Changes made outside the app, not yet accepted: {st['outside']}")
    print(f"Checked the {'whole trail' if argv[0] == 'verify' else 'last 200 entries'}: "
          + ("all entries check out." if v["ok"] else "problems found:"))
    for p in v["problems"]:
        print("  - " + p)
    return 0 if v["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
