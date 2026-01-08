import runpod

def handler(job):
    job_input = job.get("input", {})

    return {
        "status": "ok",
        "message": "Handler ran successfully",
        "received_input": job_input
    }

runpod.serverless.start({
    "handler": handler
})
