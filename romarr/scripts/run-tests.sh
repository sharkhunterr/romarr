#!/usr/bin/env bash
# Run the full pytest suite in parallel with progress milestones
# (% complete + elapsed + ETA) printed every 10%.
#
# Usage:
#   scripts/run-tests.sh                    # full suite, parallel, no coverage
#   scripts/run-tests.sh tests/api/         # subset
#   scripts/run-tests.sh -k status          # filter
#
# Any extra arguments are forwarded to pytest verbatim.

set -uo pipefail

START=$(date +%s)

# `-n auto` parallelises across CPU cores. `--no-cov` skips
# coverage (the html report slows xdist worker startup
# noticeably). `-q` keeps output parseable. Override either
# via the wrapper args.
uv run pytest "$@" --no-cov -n auto -q 2>&1 | awk -v start="$START" '
  BEGIN {
    last = -1
  }
  {
    print
    fflush()
  }
  match($0, /\[ *[0-9]+%\]/) {
    pct_str = substr($0, RSTART + 1, RLENGTH - 2)
    gsub(/ /, "", pct_str)
    gsub(/%\]/, "", pct_str)
    pct = pct_str + 0
    if (pct >= last + 10 || pct == 100) {
      now = systime()
      elapsed = now - start
      em = int(elapsed / 60); es = elapsed % 60
      if (pct > 0 && pct < 100) {
        total = elapsed * 100 / pct
        remaining = int(total - elapsed)
        rm = int(remaining / 60); rs = remaining % 60
        printf("\n>>> pytest %3d%% — elapsed %dm%02ds, eta %dm%02ds\n\n",
               pct, em, es, rm, rs)
      } else if (pct == 100) {
        printf("\n>>> pytest 100%% — total %dm%02ds\n\n", em, es)
      }
      fflush()
      last = pct
    }
  }
'

# Preserve pytest's exit code through the awk pipe.
exit "${PIPESTATUS[0]}"
