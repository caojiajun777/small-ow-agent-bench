# Trap taxonomy (closed)

This is the full trap list for this bench. It is closed on purpose: small Python repos, Harbor I/O, 3B–9B agents. It is not every bug in software.

Each trap is **one failure mode**. Surfaces (VIP vs VAT vs TTL) do not count as new traps. Out of scope is listed at the bottom so we do not sneak it back in.

Difficulty is **not** a trap attribute. See [`DIFFICULTY.md`](DIFFICULTY.md): Medium / Hard are empirical labels after the 3B / 8B–9B / 27B ladder. A trap that 9B fails is only Hard if 27B can pass.

Status: `v1` = public unique trap, `unscored` = 27B also fails (not a difficulty band), `stock` = isomorph kept on disk.

## Localization (exact file set)

| ID | Trap | Task | Status |
|---|---|---|---|
| L1 | Config already correct; live code hardcodes the wrong value | `loc-member-discount` | v1 |
| L2 | Same as L1, plus an unused file that shares the bad string | `loc-bind-host` | v1 |
| L3 | Gold is two files among similar names | `loc-vip-two-files` | v1 |
| L4 | Similar helper names; gold is one nested path | `loc-similar-filenames` | v1 |
| L5 | Do not list the traceback wrapper; list the parser | `loc-traceback-helper` | v1 |
| L6 | Do not list the failing test; list the implementation | `loc-failing-test-impl` | v1 |
| L7 | Do not list a re-export `__init__.py`; list the defining module | `loc-reexport` | v1 |
| L8 | Unused file already holds the “fix”; it is never imported | `loc-unused-fix` | v1 |
| L9 | Live hardcoded branch; unused `*_RATE` / `FAST_SECONDS` decoy | `loc-hardcoded-fast-timeout` | unscored |
| — | L1 isomorphs | `loc-config-key`, `loc-log-path`, `loc-retry-max`, `loc-cache-ttl` | stock |
| — | L9 isomorphs | `loc-hardcoded-vip-branch`, `loc-hardcoded-digital-vat` | stock |

## Editing (named file, hidden tests)

| ID | Trap | Task | Status |
|---|---|---|---|
| E1 | Text normalize (case, punctuation, hyphens) | `edit-slugify` | v1 |
| E2 | Half-open interval union length | `edit-covered-length` | v1 |
| E3 | Nested merge, list replace, no mutate | `edit-deep-merge` | v1 |
| E4 | Parse comma ints; whitespace and empty items | `edit-int-list` | v1 |
| E5 | Stable top-k by score | `edit-top-k` | v1 |
| E6 | Filter JSONL; skip bad lines | `edit-jsonl-keep` | v1 |
| E7 | Duration format with zero padding | `edit-hhmmss` | v1 |
| E8 | Inclusive prefix sums; no mutate | `edit-prefix-sums` | v1 |
| E9 | Clamp both bounds | `edit-clip` | v1 |
| E10 | Explicit `0` is not “missing” (`or` default) | `edit-timeout-zero` | v1 |
| E11 | Unique while keeping first-seen order | `edit-unique-keep` | v1 |
| E12 | No-op when already long enough (pad) | `edit-pad-left` | v1 (was stock) |
| — | Filter digits / rotate list | `edit-digits-only`, `edit-rotate-left` | stock |

## Unit-test generation (gold pass + all mutants fail)

| ID | Trap | Task | Status |
|---|---|---|---|
| T1 | Missing lo / hi / identity | `testgen-clip` | v1 |
| T2 | `set()` drops order; last-wins | `testgen-unique-order` | v1 |
| T3 | Leap year is not `year % 4` | `testgen-gregorian` | v1 |
| T4 | Sum or first element instead of mean | `testgen-mean` | v1 |
| T5 | No strip / keep empty tokens | `testgen-parse` | v1 |
| T6 | Case and spaces | `testgen-anagram` | v1 |
| T7 | `or` default drops explicit `0` | `testgen-timeout-zero` | v1 |
| T8 | Missing key / `None` vs present name | `testgen-greet-none` | v1 |
| T9 | `float` cents | `testgen-cents` | v1 |
| T10 | Slice `end+1` / `start+1` | `testgen-window` | v1 |
| — | Direction / pad / digits mutants | `testgen-pad`, `testgen-digits`, `testgen-rotate` | stock |

## Issue reproduction (fail on buggy, pass on gold)

| ID | Trap | Task | Status |
|---|---|---|---|
| R1 | Slice `end+1` | `repro-off-by-one` | v1 |
| R2 | Inclusive end; interior point does not fail | `repro-end-exclusive` | v1 |
| R3 | `or 30` drops present `0` | `repro-zero-timeout` | v1 |
| R4 | `if n` drops `0` | `repro-keep-zero` | v1 |
| R5 | Missing / `None` name | `repro-none-name` | v1 |
| R6 | `float` cents | `repro-float-cents` | v1 |
| R7 | Last-wins; needs a repeated needle | `repro-first-index` | v1 |
| R8 | Empty input must error (returning `0` hides it) | `repro-empty-mean` | v1 |
| R9 | Surrounding whitespace; `isdigit()` without strip drops padded tokens | `repro-whitespace` | v1 |
| R10 | Omitted key vs explicit `0` (flag) | `repro-truthy-flag` | v1 (was stock) |
| — | Slice `start+1` | `repro-start-index` | stock |

## Code review (binary 0/1)

| ID | Trap | Task | Status |
|---|---|---|---|
| V1 | Partial clamp (lo only); example fails | `review-clip-incomplete` | v1 |
| V2 | Near-miss slug (collapse/strip) | `review-slug-almost` | v1 |
| V3 | Sum instead of mean; example fails | `review-mean-wrong` | v1 |
| V4 | Complete slug; label 1 | `review-slug-complete` | v1 |
| V5 | `or` default drops `0`; contract is explicit | `review-configured-timeout` | v1 |
| V6 | Rotates the wrong way | `review-rotate-right` | v1 |
| V7 | Complete prefix sums; label 1 (second domain) | `review-prefix-complete` | v1 |
| V8 | Integer division mean; stated example passes | `review-floor-mean` | v1 candidate |
| V9 | `float` cents; stated examples pass | `review-dollar-cents` | v1 (not Hard; 27B k=1 wrote 1) |
| V10 | No strip; stated example has no extra spaces | `review-unstripped-slug` | v1 candidate |
| — | Partial hi / skip lower | `review-hi-only`, `review-no-lower` | stock |
| — | Second complete patch | `review-digits-complete` | stock |

## Out of scope (will not add)

- Multi-file SWE-bench issues, huge repos, multi-language
- Composite issue-resolve (`rec-*`) as an atom
- Adding Hard edit / testgen / repro unless 9B fails and 27B passes
- Relaxing loc from exact set to subset in order to create a Hard passer
- Network, concurrency, security exploits, GUI
