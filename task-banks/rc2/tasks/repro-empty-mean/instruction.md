# Empty telemetry group is silently summarized

The worker project is at `/app/repo`. Users report the behavior described by the
title when a file batch is processed through workflow.run or the workflow CLI.
Read `README.md` and the public implementation for the exact data contract:
nums must be a JSON list with at most 1000 non-boolean integers, each with absolute value <= 1000000. Floating-point values, booleans and larger groups/observations are invalid_record. Nonempty groups return sum(nums)/len(nums); empty groups must become invalid_record errors, not a successful zero.

Investigate the defect and construct your own request/environment conditions;
no complete triggering request is supplied. Write one standalone Python script
at `/app/repro.py`. It must exercise the public file-backed workflow, fail with
nonzero status on the buggy project, and exit zero on either valid repair.
Create fixture JSON and outputs in a temporary directory. Stateful actions must
execute in input order in the same worker process. A direct helper-only assertion
is insufficient: the issue concerns the externally consumed batch behavior.

Do not modify any repository file or rely on extra helper scripts. The grader
extracts only repro.py and replays it twice on fresh private buggy/fixed trees;
it does not trust the live repository. Import workflow normally, avoid absolute
deployment paths, and ensure the submitted script does not inspect source/bytecode or hidden implementation
paths. You may read application code while investigating. Ordinary CLI subprocess use and public API introspection are allowed.
Missing imports, syntax errors and timeouts are invalid reproductions.
The original task time limit applies.
