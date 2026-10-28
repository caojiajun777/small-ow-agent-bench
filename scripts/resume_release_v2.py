"""Continue a frozen release under a separate explicit monetary-cap waiver.

Default is a read-only plan. This command never creates authorization, removes
STOP or changes frozen evaluation/attempt limits. Explicit execution updates
claims through the normal transactional executor.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from release_v2_fee_waiver_executor import execute_experiment


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--worker", type=int, default=0)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        return execute_experiment(args.directory, worker=args.worker, workers=args.workers,
                                  execute=args.execute)
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
        print(json.dumps({"blocked":True,"reason":str(error),
                          "model_execution_authorized_by_command":False}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
