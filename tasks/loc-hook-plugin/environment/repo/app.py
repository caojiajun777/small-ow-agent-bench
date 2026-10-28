from worker import run_job


def process(request):
    return {"jobs": [run_job(job) for job in request.get("jobs", [])]}
