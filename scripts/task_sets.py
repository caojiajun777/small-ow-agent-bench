"""Frozen v1 main set: 47 unique-trap Medium tasks. Not L9, not isomorphs."""

MAIN_47 = (
    "loc-member-discount",
    "loc-bind-host",
    "loc-vip-two-files",
    "loc-similar-filenames",
    "loc-traceback-helper",
    "loc-failing-test-impl",
    "loc-reexport",
    "loc-unused-fix",
    "edit-slugify",
    "edit-covered-length",
    "edit-deep-merge",
    "edit-int-list",
    "edit-top-k",
    "edit-jsonl-keep",
    "edit-hhmmss",
    "edit-prefix-sums",
    "edit-clip",
    "edit-timeout-zero",
    "edit-unique-keep",
    "edit-pad-left",
    "testgen-clip",
    "testgen-unique-order",
    "testgen-gregorian",
    "testgen-mean",
    "testgen-parse",
    "testgen-anagram",
    "testgen-timeout-zero",
    "testgen-greet-none",
    "testgen-cents",
    "testgen-window",
    "repro-off-by-one",
    "repro-end-exclusive",
    "repro-zero-timeout",
    "repro-keep-zero",
    "repro-none-name",
    "repro-float-cents",
    "repro-first-index",
    "repro-empty-mean",
    "repro-whitespace",
    "repro-truthy-flag",
    "review-clip-incomplete",
    "review-slug-almost",
    "review-mean-wrong",
    "review-slug-complete",
    "review-configured-timeout",
    "review-rotate-right",
    "review-prefix-complete",
)

# Protocol check only. Not MAIN_47, not five-skill means.
PROTOCOL_SMOKE = (
    "hello-world",
    "collect-todos",
)

# Ruler k=3 fill: Loc boundary only. Drop loc-unused-fix (easy; 6/10 main already pass).
LOC_RULER_K3 = tuple(
    name for name in MAIN_47 if name.startswith("loc-") and name != "loc-unused-fix"
)

# Diagnostic / stock: oracle/nop at Gate A, not in five-skill means.
DIAGNOSTIC = ("loc-hardcoded-digital-vat",)

# Hard-Dev calibration (2 per atom). Not MAIN_47. Not official Base/Hard means.
HARD_DEV_10 = (
    "loc-codegen-source",
    "loc-lazy-getattr",
    "edit-bankers-round",
    "edit-aware-utc",
    "testgen-nan-mean",
    "testgen-casefold",
    "repro-json-first-key",
    "repro-zulu-later",
    "review-mutates-rank",
    "review-nan-identity",
)

# v0-candidate (pre Gate-B). Kept on disk; not the official 15.
HARD_RELEASE_V0_CANDIDATE = (
    "loc-vendor-shadow",
    "loc-env-wrapper",
    "loc-hook-plugin",
    "edit-config-beside",
    "edit-retry-discount",
    "edit-blank-name",
    "testgen-tie-order",
    "testgen-booking-touch",
    "testgen-zero-qty",
    "repro-double-discount",
    "repro-blank-name",
    "repro-stale-quote",
    "review-shared-cart",
    "review-dead-helper",
    "review-fresh-cart",
)

# Hard-Release-15 after Gate-B patches. Freeze after oracle/nop + foils.
HARD_RELEASE_15 = (
    "loc-vendor-shadow",
    "loc-env-wrapper",
    "loc-hook-plugin",
    "edit-config-beside",
    "edit-retry-discount",
    "edit-blank-name",
    "testgen-tie-order",
    "testgen-booking-touch",
    "testgen-zero-qty",
    "repro-second-export",
    "repro-nested-alias",
    "repro-stale-quote",
    "review-bare-except",
    "review-dead-helper",
    "review-wired-helper",
)
