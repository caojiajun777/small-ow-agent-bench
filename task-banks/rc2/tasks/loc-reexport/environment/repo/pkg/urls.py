from pkg.net import localhost


def describe(endpoint, tls):
    host, port = endpoint
    scheme = "https" if tls else "http"
    return {"public_url": f"{scheme}://{host}:{port}", "diagnostic_url": f"http://{localhost()}:{port}/status"}
