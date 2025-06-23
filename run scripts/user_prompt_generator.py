import csv
import json
from llama_cpp import Llama

MODEL_PATH = "C:/source/python/commercial_agentic_ai/llm_service/models/llama-3.2-3b-instruct-q4_k_m.gguf"
llm = Llama(model_path=MODEL_PATH, n_ctx=2048, n_threads=12, mmap=False)

intents = [
    "create_project",
    "edit_spec",
    "remind_approval",
    "approve_spec",
    "deny_spec",
    "user_changed_spec",
    "request_spec_change",
    "request_kanban_change",
    "request_project_design_change",
    "request_architect_build",
    "approve_architect_build",
    "request_dev_stop",
    "request_dev_start",
    "request_project_hold",
    "basic_reply"
]

# === System Prompt for Generation ===
GEN_PROMPT_TEMPLATE = """
You are a DevOps assistant. Generate 1000 varied user prompts for the intent: "{intent}".
Respond with only the prompts, each separated by this delimiter: -*/ (dash, asterisk, slash).
Do not include the intent name in the prompts.
Do not include any explanations, numbers, or extra formatting.
Example output:
Start a new repo for the feature branch-*/We should kick off a new project-*/Let’s begin with a clean slate
"""

# === Generate Examples ===
generated_prompts = []

for intent in intents:
    system_prompt = GEN_PROMPT_TEMPLATE.format(intent=intent).strip()

    response = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Please provide the prompts."}
        ],
        max_tokens=256,
        temperature=0.7
    )

    content = response["choices"][0]["message"]["content"]
    raw_prompts = content.split("-*/")
    cleaned = [p.strip() for p in raw_prompts if p.strip()]

    for prompt in cleaned:
        generated_prompts.append((intent, prompt))

# === Save Results to CSV ===
with open("generated_user_prompts.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["intent", "prompt"])
    writer.writerows(generated_prompts)

print("✅ Done. Prompts saved to generated_user_prompts.csv")