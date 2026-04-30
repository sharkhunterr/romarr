# Research — Spec 007 Search & Decision Engine

## Pipeline scoring perf (T081 / SC-003)

Budget: 100 results scored post-network in **< 200 ms**.

Method: warm one full pass through `run_pipeline` over a 100-result
corpus, then time 10 successive trials over the same corpus.
Hardware: developer workstation (Linux 6.17, Python 3.12,
opportunistic measurement, no isolation). Corpus: identical
"Sonic the Hedgehog (USA)" results varying only in `guid` and
`size_bytes` so each result exercises the full pipeline (matching
→ DAT lookup → profile gates → score) without short-circuit.

Result:

```
trials (ms): 1.7 1.7 1.7 1.7 1.7 1.7 1.7 1.7 1.7 1.7
min=1.7  median=1.7  max=1.7
```

**Median 1.7 ms — ~118× under the 200 ms budget.** The pipeline is
pure-Python over a preloaded `LibraryState`; no allocations on the
hot path, no I/O, deterministic `RapidFuzz` scoring on cached
title indexes. Comfortable headroom for the larger custom-format
catalogs that spec 008+ will introduce, and for the n×m fan-out
that the missing-search round will trigger once spec 009 lands.

The complementary `tests/search/test_pipeline_perf.py` regression
test asserts the 200 ms ceiling on every CI run; this research
note records the headroom we ship with for future refactors to
respect.
