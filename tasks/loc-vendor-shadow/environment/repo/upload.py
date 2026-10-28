from pathlib import PurePosixPath
from app import MAX_UPLOAD_MB


def allow(size_mb):
    return 0 <= size_mb <= MAX_UPLOAD_MB


def validate_batch(files, policy):
    total = sum(file["size_mb"] for file in files)
    results = []
    for file in files:
        reason = None
        if PurePosixPath(file["name"]).suffix.lower() not in policy["suffixes"]:
            reason = "type"
        elif not allow(file["size_mb"]):
            reason = "size"
        elif total > policy["max_batch_mb"]:
            reason = "batch"
        results.append({"name": file["name"], "accepted": reason is None, "reason": reason})
    return {"files": results, "total_mb": total}
