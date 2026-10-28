# Worker timeout configuration import: write regression tests

The file-backed worker is at `/app/repo`. Read `README.md` for the complete public
batch/API/CLI contract. The existing limits.py functionality is now consumed
by service.py and workflow.py; tests must exercise that real entry point and its
published report, not only an isolated helper.

Write tests under `/app/repo/tests/test_*.py`, with any small fixtures under tests/.
Do not modify application files or add conftest.py. Cover the domain rules,
file publication and collect/stop error policies. Correct alternative implementations
must pass; behaviorally wrong implementations must be detected reproducibly.
Imports, collection failures, empty suites and timeouts do not count as detection.
Normal subprocess CLI tests are allowed. Source/bytecode/hidden-path introspection
is not. Use temporary fixture/output directories and normal imports.

You may run `python3 -m pytest /app/repo/tests -q`. The original task time limit applies.
