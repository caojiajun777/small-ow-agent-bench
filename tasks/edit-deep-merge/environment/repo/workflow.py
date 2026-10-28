from merge import deep_merge

def process(request):
    config = {}
    for layer in request["layers"]:
        config.update(layer)
    return {"config": config, "layers_applied": len(request["layers"])}

