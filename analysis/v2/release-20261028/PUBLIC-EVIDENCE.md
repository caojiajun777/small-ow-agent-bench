# SmallOWBench 2.0: public evidence summary

Latest result status: seven configurations have complete 62-task evidence after
the two limited negative-observation supplements. Qwen3.5-9B is held after a
second shared-upstream-pool 429: 29 scored, two infra, 31 unvisited. The extra
approved retry remains unused. See the [completed-configuration results](RESULTS-PARTIAL-20261029.md);
global full-roster acceptance remains false.

Closeout update, 2026-10-29: a separate bounded protocol completes the 32 unvisited
slots and permits exactly one user-approved HTTP-429 retry (497 attempts for 496
unique scored slots). Two original zero-grade capture errors receive strictly
negative-only observation audits. Original records stay intact; final ranking
still requires full acceptance. See the [closeout protocol](CLOSEOUT-PROTOCOL-20261029.md).

Execution update, 2026-10-29: the user waived monetary admission limits after
120 scored attempts. The initial evidence and fee records remain intact; the
remaining 376 slots continue under unchanged evaluation conditions. US$40 below
identifies the initial phase. See the [dated amendment](MONETARY-POLICY-AMENDMENT-20261029.md).

Date: 2026-10-28. This is a manually reviewed projection of local engineering
evidence, not a raw trial archive or a replacement input for any validator.
Host paths, credentials, request traces and Docker host inventories are omitted.
File hashes below identify the retained local originals; readers without those
originals cannot independently reconstruct all checks from this summary alone.

## Task bank and components

- Task bank: `task-banks/rc2/tasks`, 62 authored Python tasks.
- Benchmark, task and grader version: `2.0.0-rc.2`.
- Harness version: `2.0.0-rc.1`.
- Candidate manifest file SHA-256:
  `c2e36e21eff887a688149347d47c7af45c0cf0aa072ef3eff95d684ef4c92b87`.
- Candidate manifest internal digest:
  `dafae53f5ee3aa0afd4c02bd952399a7fe2179217c65e48457b2dd4989e2e889`.

The candidate's protected RC1 source files remain included for integrity
validation. Their presence does not make the old task root an RC2 entry point.
Frozen directory digests use legacy platform-dependent Path ordering; the
release notes explain the cross-host limitation. Per-file bytes are preserved.

## Existing RC2 engineering evidence (2026-10-27)

Five fixed tasks, one per skill, were checked with a reference solution and an
empty submission: `loc-bind-host`, `edit-clip`, `testgen-timeout-zero`,
`repro-keep-zero`, and `review-clip-incomplete`.

- 10 of 10 trials had the expected result: five reference passes and five empty
  submission failures.
- The original evidence contains 20 distinct agent/grader `network_mode=none`
  records and 10 native private grader temporary-directory records under `/tmp`.
- 82 transported files were compared in both directions, including preexisting
  files: 18 submission-role files and 64 observation-role files. This is a file
  count, not a task or new-answer count.
- The run's owned trial/probe containers were absent after cleanup. Existing
  unrelated containers were preserved.
- The post-repair offline regression reported 232 passed and one skipped, with
  no failures or errors. The skipped case lacked permission to create a real
  symlink and is not counted as passed.

Retained original preflight report file SHA-256:
`104af1a8e2a6a94a876b44b941bc2683dec7fed98fcec0e2ee89d0ff414575ce`.
Its internal digest is
`61bcf3876510be148d6234c19b15f466a6fb6c1371de2c5935ce5a22f9466203`.
The retained regression XML SHA-256 is
`0c72887235cce341f06d550c6f4db7e3191d930f8e548e071c9ffdf7f07c636b`.

These checks cover the selected five-task pipeline. Full-bank RC2 container
validation remains false. Historical RC1 full124 and mc3/mc4 results do not
transfer to RC2 and are not official 2.0 model scores.

## Release implementation and image initialization (2026-10-28)

- The additive release pipeline, image initializer and execution/analysis glue
  passed 72 offline contract tests. These tests do not call models or rerun task
  reference/empty-submission evaluation.
- Agent and grader images for all 62 tasks were bound with original build and
  dependency-version receipts. The five previously checked task pins were
  retained. Initialization ran zero task evaluations and zero model calls.
- The original eight OpenRouter configurations matched public endpoint metadata
  in a read-only GET audit. This does not prove inference availability or actual
  parameter behavior; see [route audit](ROUTES.md).

## Authorized model run

The independent release run was activated on 2026-10-28 at 21:58:48 (UTC+08:00):
eight original OpenRouter configurations, 62 tasks, one attempt per task,
at most 496 task attempts, four workers, zero whole-trial retries, US$40 cap.
This does not impose a 496-HTTP-request limit: multi-turn trials contain multiple
requests. Budget admission or infrastructure holds can stop the run early.

Frozen run manifest internal digest:
`c9bebded890b7bfc49518efabadf81a8cbca35355d1fd1a1b300914849fb5fe1`.
Frozen execution-lock internal digest:
`8468e1368799141f67fb3b30200499be60dd9763766f18284c0ff799001c07df`.

**The intended full-roster results remain incomplete.** Completed-configuration
scores are published above; the engineering checks themselves do not establish
model scores. Original run authorization, claims, budget ledgers and
absolute-path runtime receipts remain local. Final results must be recomputed
from the matching run's raw artifacts, with missing, infra, grader errors and
termination categories disclosed. The old US$4 run and its holds are unchanged.
