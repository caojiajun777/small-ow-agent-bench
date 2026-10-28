# Structured review negative controls

The old one-bit flip foil is retired. This task now contains four independent candidates, with two conforming and two defective implementations. Constant acceptance/rejection, flipped decisions, invented expected values, rejection without a real counterexample, nonexecuted locations and changed workspace source must all fail.

The executable protocol regressions live in `scripts/test_task_upgrade_review.py`; the task-specific oracle is also checked against the private contract and immutable workspace. `foils.json` inventories these strategies, not executable legacy bit submissions.
