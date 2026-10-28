from serve import bind


def plan(options):
    host, port = bind(options)
    return {"command": ["worker", "--listen", f"{host}:{port}", "--workers", str(options["workers"])], "health": f"http://127.0.0.1:{port}/health"}
