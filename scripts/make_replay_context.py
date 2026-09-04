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

kept, cut = [], 0
for line in open(src):
    m = re.match(r"^(\d{4}-\d{2}-\d{2})\s*\|", line)
    if m and m.group(1) >= date:
        cut += 1
        continue
    kept.append(line)

os.makedirs(out_dir, exist_ok=True)
path = f"{out_dir}/memory_{date}.md"
with open(path, "w") as f:
    f.write(f"<!-- REPLAY CONTEXT for {date}: {cut} forward-record entries dated >= {date} were "
            f"REMOVED. This is what the brain knew before that morning. -->\n")
    f.writelines(kept)
print(f"{path}  (cut {cut} entries dated >= {date}, kept {len(kept)} lines)")
