"""An actual ASGI-compatible fake server with SSE, errors and a cancellable stalled stream."""

import asyncio
import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse

app = FastAPI()
requests: list[dict] = []


@app.get("/v1/models")
async def models():
    return {"data": [{"id": "test-model", "object": "model"}]}


@app.post("/v1/chat/completions")
async def chat(request: Request):
    body = await request.json()
    requests.append(body)
    model = body["model"]
    if model == "redirect":
        return RedirectResponse("http://169.254.169.254/secret", status_code=302)
    if model in ("401", "403", "404", "429", "500"):
        return JSONResponse(
            {"error": request.headers.get("authorization")},
            status_code=int(model),
            headers={"Retry-After": "2"} if model == "429" else {},
        )

    async def stream():
        if model == "timeout":
            await asyncio.sleep(30)
        for chunk in [
            {"choices": [{"index": 0, "delta": {"reasoning_content": "thinking"}}]},
            {"choices": [{"index": 0, "delta": {"content": "@@ROUTE: "}}]},
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": "ready"},
                        "finish_reason": "length" if model == "length" else "stop",
                    }
                ]
            },
            {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 3}},
        ]:
            yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
