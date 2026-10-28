#!/bin/bash
set -u
exec python3 "${BENCH_TESTS_ROOT:-/tests}/verdict_v2.py"
