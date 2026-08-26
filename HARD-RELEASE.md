# Hard-Release-15

Official Hard set. Hard-Dev-10 stays scratch paper. Current on-disk names before Gate-B patches are archived as **v0-candidate** (`HARD_RELEASE_V0_CANDIDATE` in `scripts/task_sets.py`); task folders are kept, not deleted.

## Adopted (quality method)

1. Hard comes from live path, state, interaction, and decoys. Demand stays clear. Not trivia, not vague tickets.
2. Gate includes **foils**: oracle=1, nop=0, and ≥2 documented wrong solutions the verifier rejects.
3. Items must not share one core bug across atoms (IRT independence).
4. Grep may hint; it must not uniquely name the gold file.
5. Review keeps **at least one real 1**. Verdict stays a single `0`/`1` in `/app/answer.txt` (same atom as Base). No free-text, no JSON schema, no LLM judge.

## Rejected

- Multi-file / “two hops” as a Hard definition. That mixes Loc into Edit/Testgen/Repro.
- Mechanical H1/H2/H3 file-count gates. Check whether two *independent evidences* are required, not how many files.
- Replace-by-name without instruction + repo + verifier + foils.
- Review `{verdict, file, symbol, issue_code}` for this freeze (changes the atom and invites format tax).

Atomic isolation stays the product: Loc finds files; Edit is given the module; Testgen is given the API; Repro is given the component; Review is given the patch.

## Gate-B (freeze gate)

Hard thresholds (all must pass):

| Gate-B | Standard |
|---|---|
| Atom purity | Mainly the named skill; not a mini SWE-bench |
| Clear contract | Correct behavior from the ticket and/or in-repo docs |
| No mechanism leak | Ticket does not name the live file or the bug mechanism |
| Verifier strength | oracle=1, nop=0, ≥2 foils rejected |
| Independence | No shared core bug with another Hard-15 item |
| Determinism | No network, clocks, shuffle, or LLM judge |

Bonus only: decoy, two evidences, naive patch breaks regression, gold/mutant dual run, readable fail trace.

## v0-candidate audit (from files, not titles)

| Task | Atom | Independence | Grep / leak | Contract | Verdict |
|---|---|---|---|---|---|
| `loc-vendor-shadow` | Loc | ok | 25 is the decoy; gold is 5 | clear | **keep** + foils |
| `loc-env-wrapper` | Loc | ok | “debug” + `/tmp/debug.log` unique-hit gold | clear | **patch** clues |
| `loc-hook-plugin` | Loc | ok | ticket `3`/`5` unique-hit `ATTEMPTS = 3` | clear | **patch** clues |
| `edit-config-beside` | Edit | ok | “ships with this module” is soft | named file | **keep**; reject hardcoded `{retry:5}` |
| `edit-retry-discount` | Edit | **clash** with `repro-double-discount` | second-call is contract, ok | named file | **keep** this atom; drop the Repro twin |
| `edit-blank-name` | Edit | **clash** with `repro-blank-name` | empty-string is in the ticket | named file | **keep** (high-risk, not auto-drop); drop the Repro twin |
| `testgen-tie-order` | Testgen | ok | ticket states the tie rule | API named | **patch**: move tie rule into module docs |
| `testgen-booking-touch` | Testgen | ok | ticket states adjacent-not-overlap | API named | **patch**: move into module docs |
| `testgen-zero-qty` | Testgen | mild vs blank-name (missing vs zero) | ticket states qty 0 | API named | **patch**: don’t name 0 in the ticket |
| `repro-double-discount` | Repro | clash | — | — | **replace** (same bug as Edit) |
| `repro-blank-name` | Repro | clash | — | — | **replace** |
| `repro-stale-quote` | Repro | ok | cache not named | public API | **keep** |
| `review-shared-cart` | Review | clash with `review-fresh-cart` | — | — | **replace** (same mutable-default pair) |
| `review-dead-helper` | Review | ok | — | example vs live path | **keep** |
| `review-fresh-cart` | Review | clash | — | — | **replace** 1-patch with a *different* complete issue |

After patches, official 15 is `HARD_RELEASE_15`: Loc three kept (env/hook clues patched); Edit three kept (config foil + retry extra price test); Testgen three kept (edge rules moved into docstrings); Repro is `repro-second-export`, `repro-nested-alias`, `repro-stale-quote`; Review is `review-bare-except` (0), `review-dead-helper` (0), `review-wired-helper` (1).

`review-dead-helper` / `review-wired-helper` are a 0/1 pair on the same issue on purpose (anti always-reject), like Base slug-almost/complete. Frozen 2026-08-26: harbor oracle=1 / nop=0 on all 15 (`jobs/gate-a-hard-release-oracle-nop.json`); local foil tests pass. Do not rewrite from 12-model scores.

## Official Hard k=3 (compressed examinees)

Hard-15 items stay frozen. **Examinees are not all 12.** Base-47 already shows who cannot do Medium; those IDs are not re-tested on Hard and are **not** imputed as Hard \(p=0\).

Rule (EVAL-NOTE §6.2 Atomic 47-mean): administer if \(p \ge 0.40\), plus 27B and 35B.

| Run | Base-47 Atomic | Why |
|---|---:|---|
| Ministral-8B | 0.496 | Medium-competent; target peer |
| Qwen3.5-9B | 0.823 | Hard definition anchor |
| Qwen3-14B | 0.454 | Medium-competent |
| Ministral-14B | 0.546 | Medium-competent |
| Qwen3.8-27B | ruler | Hard ceiling |
| Qwen3.6-35B-A3B | MoE | Core band, not a spectator |

Skip (stay on Base only): Llama-3.2-3B 0.028, Gemma-3-4B 0.035, Qwen3-8B 0.043, Ministral-3B 0.064, Granite-4.1-8B 0.177, Gemma-3-12B 0.333. Skip is **Medium competence**, not parameter count (Qwen3-8B is 8B but a floor; Ministral-8B is kept).

Writes only `jobs/locked-hard-release-k3.json`. Does not overwrite `locked-core.json`, `locked-core-k3.json`, or Hard-Dev.

```text
python scripts/run_locked.py --hard-release
python scripts/run_locked.py --run --hard-release
```

Dry-run must print **270** (6×15×3). Full 12 is `--group all` (540), not the official table. Resume skips completed `(model, task, attempt)`. Infra retries do not consume attempt numbers. One Novita job at a time.

## Results (do not rewrite items)

Ran 2026-08-26: 90 cells, `n_valid=3`, infra=0. Official numbers and failure composition: [`EVAL-NOTE.md`](EVAL-NOTE.md) §12. Atomic means stay as recorded. Do not impute zeros for skipped models (**missing ≠ 0**). Do not change tasks from these scores. Do not write that all 12 Core models ran Hard-15.

