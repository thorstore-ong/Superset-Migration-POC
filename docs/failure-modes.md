# Failure modes: backfill POC

Each entry: what was tested, what happened (with evidence), what the script does about it,
what risk remains, and why it matters for the real QA/Prod runner.

## FM-01 Connection lost mid-chunk

**Test:** Started a fresh backfill, then ran `pg_terminate_backend` on its connection from a
second terminal (simulates a DB restart, failover, or network drop during a deploy).

**What happened:** Script crashed with exit 1. `conn.rollback()` inside the error handler raised
`InterfaceError: connection already closed`. `backfill_runs` showed 46 chunks `succeeded`,
1 `running` (meter 1, 2026-02-16), and nothing claimed after it. The `running` chunk had
0 rows in `readings`.

**What the script does:** Each chunk's data and its `succeeded` status commit in one transaction,
so Postgres discards a chunk interrupted mid-write. The chunk is left `running`; the next run
with `--batch-id` treats any non-`succeeded` chunk as retryable. Resume finished the remaining
1,403 chunks and `reconcile.py` passed all checks.

**Remaining risk:** The failure is not recorded as `failed` (the handler can't reach the database),
so a stale `running` is indistinguishable from a chunk in progress. Retrying stale `running` is
safe only with a single runner; concurrent runners would need `FOR UPDATE SKIP LOCKED` or a lease.

**Relevance to work:** If the real runner commits a migration's data and its "done" marker
separately, a dropped connection between them would leave it half-applied, and a rerun would
either redo or skip work incorrectly. Check whether it does.

## FM-02 Constraint violation mid-chunk

**Test:** Added a temporary `CHECK (kwh_value < 500) NOT VALID` and then injected a 5000 row. This is
to prove that a row that datbase rejects fails ONLY its own chunkand rolls back that chunk's earlier rows.

**What happened:** This resulted in 1 of the rows in the chunk failing, `exit=1`, with `failed=1 skipped=1448` while the
marker value stayed 0 which proves the ability that the script does account for rollback. And staging was
kept at 34,714 (including the header). Deleted the bad staging row and resumed: `succeeded=1 skipped=1448 failed=0`,
`updated=24` and then the marker was restored to 77.606, staging was the cleaned up.

**What the script does:**
A database error fails only its own chunk. The chunk's data rolls back,
the failure is recorded in `backfill_runs` in a separate transaction, the remaining chunks
continue, and the run exits 1. Staging is kept whenever any chunk failed. Recovery is: fix the
data, rerun with `--batch-id`.

**Relevance to work:** Schema differences between Dev, QA and Prod are a plausible cause of
"works in Dev, fails in QA". With chunking, such a failure is contained and recoverable rather
than leaving a partial load.

## FM-03 Same backfill run twice / accidental re-load.

**Test:** After a complete load, ran the backfill again in two ways:

1. Without `--batch-id`, as someone might by accident. This loads the CSV into staging again
   under a new batch.
2. With `--batch-id` for a batch whose chunks were all already `succeeded`.

**What happened:**

1. Exit 0 with `succeeded=0 skipped=1449`. Staging held two full batches (34,713 rows each),
   but no data or rejects were written, and `reconcile.py` still passed.
2. Batch `5bbc0b76`: `succeeded=0 skipped=1449 failed=0 read=0`, then
   `cleanup deleted 34713 staging rows`.

**What the script does:** A chunk's identity is (meter, chunk_start, chunk_end), not the batch,
so any run finds already-`succeeded` chunks and skips them. Rejects are only written when a chunk
is actually processed, so reruns don't duplicate them. After a fully successful run (no failed
chunks, all chunks accounted for), the batch's staging rows are deleted, which cleans up an
accidental re-load too.

**Limitation:** Because the batch isn't part of the chunk identity, corrected source data for days
already loaded is ignored. Reprocessing is a deliberate manual step:
`UPDATE backfill_runs SET status = 'pending' WHERE ...`, then a rerun.

## Detection safeguards

FM-01 to FM-03 are about failing safely. This section is about failing _visibly_: making sure a
failure can never pass as a success. Each safeguard was proven by deliberately breaking the code
or data and confirming the check caught it (mutation testing). A check that has never been seen
to fail is not trusted.

### SG-01 Chunk-accounting check

**What it does:** At the end of `run_backfill`, every chunk must be `succeeded`, `skipped` or
`failed`. If those three don't add up to the total number of chunks, the run logs
`reconciliation failed: N of M chunks accounted for` and exits 1.

**What it catches:** A run that stops early without raising an error.

**Evidence:** During development, the end-of-run block was accidentally indented inside the chunk
loop. The run processed 1 of 1,449 chunks (`read=24`) and exited 0. After adding the check, a
deliberate `break` in the loop produced exit 1 with the reconciliation error. The same check also
caught a success counter that was never incremented.

**Relevance to work:** A runner that reports success after doing partial work is the hardest kind
of intermittent failure to diagnose. Nothing errors; the gap is only found later as missing data.

### SG-02 Manifest reconciliation (`scripts/reconcile.py`)

**What it does:** Compares the database end state with the generator's manifest: unfinished chunks,
rows read, rows upserted, rejects per reason, distinct readings, and the stored value for each
conflicting duplicate ("last one wins"). Prints expected and actual for every check, and exits 1
on any mismatch.

**What it catches:** Results that are internally consistent but wrong. The script's own counters
can agree with each other while the data is still incorrect.

**Evidence:** Early on, a generator bug injected 1 malformed row instead of 8, and the backfill
totals still reconciled. Only comparing against the manifest exposed it. Mutation test: setting one
conflicting duplicate back to its first value (9.134) produced exactly one `MISMATCH` and exit 1.
After the connection-kill test (FM-01), it reported 10 mismatches, correctly refusing to treat a
half-loaded database as finished.

**Limitation:** Checks the whole database, which works because the POC holds one dataset. Against
real data, scope the checks to a batch or date range.

**Relevance to work:** Verify against what the source says should exist, not against what the
runner says it did.

### SG-03 Full traceback on chunk failure

**What it does:** The chunk error handler calls `log.exception(...)` before rolling back. The
database keeps the short `error_message` for querying; the log keeps the full stack trace for
debugging.

**What it catches:** Losing the location of a failure.

**Evidence:** Before this, all 1,449 chunks failed with `not all arguments converted during string
formatting`, and only that message was stored. Finding the faulty statement meant inspecting the
code by hand. In FM-01, the handler's own `rollback()` raised a second error; logging first means
the original cause is recorded before that happens (not yet confirmed in a captured log).

### SG-04 Non-zero exit code on failure

**What it does:** Exits 1 if any chunk failed or chunk accounting doesn't add up. Uncaught
exceptions also exit 1; command-line usage errors exit 2.

**What it catches:** CI treating a failed run as green. The pipeline decides pass or fail purely
from this number.

**Caveats found during testing:**

- A function that reaches its end without `return` returns `None`, and `sys.exit(None)` exits 0.
  During development, a run where every chunk failed exited 0 for this reason. The return value
  must be explicit on every path.
- Piping output (`python backfill.py | tee run.log`) reports the exit code of the last command in
  the pipe, not the script's, unless `pipefail` is set. GitHub Actions' default bash shell sets it;
  check the equivalent for the Azure Pipelines tasks the real runner uses.
- An exit code alone can't distinguish "a check caught a problem" from "the script crashed".
  Always read the log.
- Mixing `print` (stdout, buffered) and `logging` (stderr, unbuffered) into one redirected file
  reorders lines. Send all output through one stream.

### Lesson: a check's expected value can itself be wrong

While writing `reconcile.py`, the expected count of distinct readings first left out the
conflicting duplicates: 34,713 − 8 − 10 = 34,695, against a correct actual of 34,690. It was
caught in review before running, but it would have reported a false mismatch.

The correct derivation is: CSV rows = unique readings + malformed rows + extra copies from exact
duplicates + extra copies from conflicting duplicates (34,690 + 8 + 10 + 5 = 34,713).

When a check reports `MISMATCH`, re-derive the expectation before blaming the data.
