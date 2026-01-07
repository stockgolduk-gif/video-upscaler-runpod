import runpod
import json

def handler(event):
    print("Job received:")
    print(json.dumps(event, indent=2))

    return {
        "status": "ok",
        "message": "Handler ran successfully",
        "input": event
    }

runpod.serverless.start({"handler": handler})
