# Export page includes a row from the following page

The worker project is at `/app/repo`. Users report the behavior described by the
title when a file batch is processed through workflow.run or the workflow CLI.
Read `README.md` and the public implementation for the exact data contract:
items/start/end use Python half-open slicing; retain start, exclude end.

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
