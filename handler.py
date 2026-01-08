import runpod

def handler(event):
    return {
        "status": "ok",
        "message": "Handler ran successfully",
        "input": event
    }

runpod.serverless.start({
    "handler": handler
})

