from limits import get_timeout

def process(request):
    output = []
    for job in request["jobs"]:
        config = dict(request.get("defaults", {}))
        config.update(job.get("config", {}))
        timeout = get_timeout(config) or 30
        output.append({"id": job["id"], "timeout": timeout,
                       "deadline": None if timeout == 0 else request["now"] + timeout})
    return output

