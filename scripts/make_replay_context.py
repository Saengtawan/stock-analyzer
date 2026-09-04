"""scripts/make_replay_context.py — build a LEAK-FREE context for replaying a past session.

Replay is the only cheap way to test a change to the brain before deploying it, and it was found to
be contaminated from two directions at once:
  1. decide.md carried single-name examples precise enough to identify one row in one pool file;
  2. resonance/memory.md IS the graded forward record — it contains the outcome of every past
     session by design, so replaying any recorded day hands the agent the answer.
(1) is fixed in the file itself. (2) cannot be: the record has to keep its outcomes. So a replay
must read a TRUNCATED memory — everything the brain knew before that morning, and nothing after.

This writes <out_dir>/memory_<DATE>.md containing every line of memory.md except forward-record
entries dated >= DATE, plus a header saying what was cut. Sections that are not dated lines (the
principles, the lessons) are preserved in full: they are the brain's state, not the answer key.
NOTE the residual: a lesson written after DATE may still encode hindsight about DATE. Truncation
removes the outcomes, not every trace, so a replay remains WEAKER evidence than forward tracking.

Usage:  python scripts/make_replay_context.py 2026-08-21 [out_dir]
"""
import os
import re
import sys

date = sys.argv[1]
out_dir = sys.argv[2] if len(sys.argv) > 2 else "."
src = "resonance/memory.md"

# Two kinds of leak, both found by replay agents that disclosed them unprompted:
#   (a) FORWARD-RECORD lines, which start with the session date;
#   (b) DATED ADDENDA INSIDE THE LESSONS and the gate-tally block — "09-02: the exception written on
#       09-01 was EXERCISED FOR..." — which quote later sessions' names and outcomes in prose. The
#       first version of this script removed only (a), and an agent replaying 08-26 read a lesson
#       addendum that listed that morning's winners by ticker and return. Anything carrying a date
#       at or after the replay date now goes, whatever section it sits in.
year = date[:4]
mmdd = date[5:]


# Residual found after the date filter: outcome citations that carry NO date. Lines like
# "FRVO +19.92%" or "SAIC -8.63%" sit inside LESSONS and the gate tallies with nothing to date them,
# and three replay agents reported reading exactly those before they could tell what session they
# belonged to. Since the date cannot be recovered, a replay context drops EVERY ticker-plus-signed-
# percent citation outside the forward record. That over-strips — some of those outcomes predate the
# replay and were legitimately knowable — but for a harness whose only job is to test a change before
# it ships, under-informing is the cheap error and leaking the answer is the fatal one. The lessons
# keep their mechanism text; they lose their worked numbers.
_OUTCOME = re.compile(r"\b[A-Z]{1,5}\b[^.;|]{0,40}?[+\u2212-]\d+(?:\.\d+)?%")


def _leaks(line):
    """True if the line carries a date at or after the replay date, in any of the file's formats."""
    for d in re.findall(r"\b(\d{4})-(\d{2}-\d{2})\b", line):        # 2026-09-02
        if f"{d[0]}-{d[1]}" >= date:
            return True
    for d in re.findall(r"(?<!\d)(\d{2}-\d{2})(?=[\s:,.)\]]|$)", line):   # bare 09-02
        try:
            if int(d[:2]) in range(1, 13) and f"{year}-{d}" >= date:
                return True
        except ValueError:
            continue
    return False


kept, cut, scrubbed = [], 0, 0
in_forward = False
for line in open(src):
    if line.startswith("#"):
        in_forward = "FORWARD RECORD" in line.upper()
    if _leaks(line):
        cut += 1
        continue
    if not in_forward and _OUTCOME.search(line):
        scrubbed += 1
        continue
    kept.append(line)

os.makedirs(out_dir, exist_ok=True)
path = f"{out_dir}/memory_{date}.md"
with open(path, "w") as f:
    f.write(f"<!-- REPLAY CONTEXT for {date}: {cut} forward-record entries dated >= {date} were "
            f"REMOVED. This is what the brain knew before that morning. -->\n")
    f.writelines(kept)
print(f"{path}  (cut {cut} dated >= {date}, scrubbed {scrubbed} undated outcome lines, "
      f"kept {len(kept)})")
