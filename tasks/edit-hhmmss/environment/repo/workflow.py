from timefmt import format_hms

def process(request):
    jobs = []
    total = 0
    for job in request["jobs"]:
        seconds = max(0, job["end"] - job["start"])
        total += seconds
        jobs.append({"id": job["id"], "duration": format_hms(seconds)})
    return {"jobs": jobs, "total": format_hms(total)}

