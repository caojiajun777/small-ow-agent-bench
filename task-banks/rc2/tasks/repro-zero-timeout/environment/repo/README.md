# Worker ignores explicitly disabled timer

This is a small synthetic file-backed worker, not a claimed external repository.
The original `limits.py` public functions remain available. The supported
batch entry point is `workflow.run(input_path, output_path, config_path=None)`;
the CLI is `python3 -m workflow INPUT OUTPUT [--config POLICY]`.

## Request and behavior

The input JSON object has string `batch_id` and a list `records`. Every record
has a unique string `id`. Record contract: config is an object; omitted timeout defaults to 30, explicit zero disables timeout, all provided nonnegative timeouts are retained.

The report is `{"batch_id":...,"processed":N,"results":[{"id":...,"value":...}],"errors":[{"id":...,"code":"invalid_record"}]}`.
Successes and errors retain their respective input order. `processed` counts
all records. Domain ValueError/TypeError/KeyError becomes invalid_record under
the default collect policy. A policy file `{"on_error":"stop"}` instead raises
ValueError on an invalid record and does not overwrite an existing output.
Policy keys other than on_error, unsupported policies, malformed headers,
duplicate IDs and invalid JSON reject the whole batch before publication.
The caller's input and policy files are never modified. The output's parents
are created as needed; publication is atomic. Paths are interpreted as given by
the caller (use absolute fixture paths when changing cwd).

CLI success exits 0 and prints JSON `{"batch_id":...,"processed":N,"errors":E}`;
read/JSON/schema/domain-stop failures exit 2 and do not publish partial output.
The API and CLI must agree. Only Python standard library and pytest are needed.
Create fixtures and outputs in temporary directories, not source directories.

## Submission contract

Write one standalone repro.py outside the repository. Use the public file API or CLI, constructing your own input/policy/temp directories. Do not alter repository files or depend on extra helper scripts.
The agent may read public application source while understanding the task.
The submitted tests or reproducer must check observable behavior: they must not
inspect implementation source or bytecode, verifier files, candidate names,
hidden paths or deployment-absolute paths. This restriction applies to the
submitted behavioral code, not the agent's reading of public application source.
Ordinary subprocess CLI testing and inspect.signature are allowed;
inspect.getsource/getfile in submitted code is not behavioral evidence.
Import workflow normally; grading supplies its module search path.
A missing import, test collection error, empty test suite or timeout is invalid,
not evidence of detecting the target defect. Two distinct correct implementations
must be accepted; graders replay submissions in fresh private project trees.
