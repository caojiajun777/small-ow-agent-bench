from loader import attempts


def max_tries():
    return attempts()


def run_job(job):
    outcomes = job.get("outcomes", [])
    for attempt in range(1, max_tries() + 1):
        success = attempt <= len(outcomes) and outcomes[attempt - 1] == "ok"
        if success:
            return {"id": job["id"], "status": "ok", "attempts": attempt}
    return {"id": job["id"], "status": "failed", "attempts": max_tries()}
