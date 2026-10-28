# Harbor runtime used by SmallOWBench 2.0

Upstream: https://github.com/harbor-framework/harbor

Base commit: `f03db62fd2ed2ed1f79aefe024cfcbc68a0d759e` (Harbor 0.21.0).

`0001-smallowbench-runtime.patch` records the local source changes relative
to that base: hidden Windows metric subprocesses and the Docker separate
verifier / static network-none transport used by this benchmark. This is a
dependency patch, not an additional benchmark or a change to model scores.
The upstream Apache-2.0 license is retained in `HARBOR-LICENSE`.

Use adjacent checkouts (the relative layout is part of the current CLI):

```text
parent/
  harbor/
  small-ow-agent-bench/
```

From the parent directory:

```bash
git clone https://github.com/harbor-framework/harbor.git harbor
git -C harbor checkout f03db62fd2ed2ed1f79aefe024cfcbc68a0d759e
git -C harbor apply ../small-ow-agent-bench/vendor/harbor-patches/0001-smallowbench-runtime.patch
cd harbor
uv sync --locked
```

Use Python >=3.12 and the resulting Harbor virtual environment for the
SmallOWBench commands. Windows uses `harbor/.venv/Scripts/python.exe`;
Linux uses `harbor/.venv/bin/python`. Docker Desktop / Docker Engine must
provide Linux containers and a working Compose plugin.

The release records actual Harbor source, dependency, Docker image and
Python/pytest identities for each execution. A new installation generates
its own environment receipts; it must not claim that a different host is
byte-identical to the published run just because this setup completes.

Do not copy an old local virtual environment or private run directory into
a public package. Refer to the main README for executing the benchmark.
