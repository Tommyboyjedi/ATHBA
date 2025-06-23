import os
import time
import asyncio

import psutil
from fastapi import FastAPI, HTTPException
from llama_cpp import Llama
from threading import Lock

from llm_service.llm_server_management import LlmServerManagement
from llm_service.py_models.llm_request import LLMRequest
from llm_service.model_registry import ModelRegistry, FLOW_JUDGE_PATH, FLOW_JUDGE_ENABLED
from llm_service.enums.eagent import EAgent
from llm_service.enums.etier import ETier
from llm_service.llm_server_state import (loaded_models, model_locks, model_last_used)

app = FastAPI()
registry = ModelRegistry()
management = LlmServerManagement()
# Config
llm_server_url = os.getenv("LLM_SERVER_URL", "http://127.0.0.1:8011")


# Preload PM-standard model
def preload_default_model():
    path = str(registry.get_model(EAgent.PM, ETier.STANDARD))
    ctx = registry.get_ctx(EAgent.PM, ETier.STANDARD)
    threads = registry.get_threads(EAgent.PM, ETier.STANDARD)
    if path not in loaded_models:
        print(f"[BOOT] Preloading PM standard model: {path}")
        loaded_models[path] = Llama(model_path=path, n_ctx=ctx, n_threads=threads)
        model_locks[path] = Lock()
        model_last_used[path] = time.time()
    else:
        print(f"[BOOT] PM standard model already loaded: {path}")
    if FLOW_JUDGE_ENABLED:
        if str(FLOW_JUDGE_PATH) not in loaded_models:
            try:
                print(f"[BOOT] Preloading Flow Judge model: {str(FLOW_JUDGE_PATH)}")
                loaded_models[str(FLOW_JUDGE_PATH)] = Llama(str(str(FLOW_JUDGE_PATH)), n_ctx=ctx, n_threads=threads)
                model_locks[str(FLOW_JUDGE_PATH)] = Lock()
                model_last_used[str(FLOW_JUDGE_PATH)] = time.time()
            except Exception as e:
                print(f"[BOOT ERROR] Failed to load flow_judge model: {e}")
    else:
        print(f"[BOOT] Flow Judge model not enabled, skipping preload.")


def run_flow_judge(prompt: str, response: str) -> dict:
    if not FLOW_JUDGE_ENABLED:
        return {"response": response}

    model_last_used[str(FLOW_JUDGE_PATH)] = time.time()

    eval_prompt = (
        "You are a model evaluator. Rate the following LLM response on a scale of 1 to 5 "
        "for clarity, completeness, and relevance to the prompt.\n\n"
        f"PROMPT:\n{prompt}\n\nRESPONSE:\n{response}\n\n"
        "Return only the number (1 to 5) and a one-word reason."
    )
    print(eval_prompt)
    with model_locks[str(FLOW_JUDGE_PATH)]:
        result = loaded_models[str(FLOW_JUDGE_PATH)](eval_prompt, max_tokens=64)
        print(result)
        line = result["choices"][0]["text"].strip()

        try:
            parts = line.split(maxsplit=1)
            score = int(parts[0])
            escalate = score <= 2
            reason = parts[1] if len(parts) > 1 else ""
            print(score, reason, escalate)
            return {
                "score": score,
                "reason": reason,
                "escalate": escalate
            }
        except Exception:
            return {
                "score": 0,
                "reason": "Flow Judge response parse failed",
                "escalate": False
            }

def clean_llm_response(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        cleaned = cleaned.strip("`").strip()
    return cleaned


# API Routes
@app.post("/infer")
def infer(req: LLMRequest):
    try:
        path = str(registry.get_model(req.agent, req.tier))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if path not in loaded_models:
        loaded_models[path] = Llama(model_path=path, n_ctx=4096, n_threads=8)
        model_locks[path] = Lock()

    model_last_used[path] = time.time()

    with model_locks[path]:
        result = loaded_models[path].create_chat_completion(
        messages=[
            {"role": "system", "content": f"You are the {req.agent.name} agent."},
            {"role": "user", "content": req.prompt}
        ],
        max_tokens=req.max_tokens,
        temperature=0.2,
    )
        print(result)
        response_text = result["choices"][0]["message"]["content"]
        response_text = clean_llm_response(response_text)

    if not req.evaluate:
        return {"response": response_text}

    # Evaluate with Flow Judge
    eval_result = run_flow_judge(req.prompt, response_text)
    print(eval_result)
    return {
        "response": response_text,
        "evaluation": eval_result
    }


@app.get("/status")
def status():
    now = time.time()
    return [
        {
            "model": path,
            "last_used": ts,
            "idle_time": now - ts
        }
        for path, ts in model_last_used.items()
    ]


@app.post("/unload")
def unload(model_path: str):
    if model_path in loaded_models:
        del loaded_models[model_path]
        del model_locks[model_path]
        del model_last_used[model_path]
        return {"status": f"{model_path} unloaded"}
    raise HTTPException(status_code=404, detail="Model not found")


@app.get("/rd/status")
def rd_status():
    return {
        "mem": psutil.virtual_memory().percent,
        "cpu": psutil.cpu_percent(),
        "loaded_models": list(loaded_models.keys()),
        "protected_models": list(management.protected_paths),
        "failed_unloads": list(management.failed_unloads.keys())
    }


# Launch RD manager

preload_default_model()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("llm_service.llm_server:app", host="127.0.0.1", port=8011, reload=False)
