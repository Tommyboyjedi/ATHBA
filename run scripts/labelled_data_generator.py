import csv
import json
from llama_cpp import Llama

# === Model Setup ===
MODEL_PATH = "C:/source/python/commercial_agentic_ai/llm_service/models/llama-3.2-3b-instruct-q4_k_m.gguf"
llm = Llama(model_path=MODEL_PATH, n_ctx=2048, n_threads=12)

# === Few-shot Prompt Template ===
few_shot = """
You are an intent classifier for a DevOps AI system. You MUST classify user prompts into one of these intents:
- create_project
- edit_spec
- remind_approval
- basic_reply

Respond in the following strict JSON format:
{"intent": "<intent_name>"}

Only respond with the JSON object. Do not explain. Do not add extra text or formatting.

Examples:
User: "Can we start a new project?"
{"intent": "create_project"}

User: "Update the spec for the login page"
{"intent": "edit_spec"}

User: "Did the team approve the last update?"
{"intent": "remind_approval"}

User: "Thanks, that's clear now."
{"intent": "basic_reply"}
"""

# === User Prompts to Classify ===
user_prompts = [
    "Let's create a new project called Alpha",
    "Remind me if we've got approval from NSCM",
    "Hey there!",
    "Change the specification section for payments",
    "Cool, understood",
    "Can we build something from scratch?",
    "Where are we with the spec now?",
    "Just checking in."
]

# === Classification Loop ===
results = []

for prompt in user_prompts:
    response = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": few_shot.strip()},
            {"role": "user", "content": f"{prompt}\nRespond only with JSON."}
        ],
        max_tokens=64,
        temperature=0.0
    )

    text = response["choices"][0]["message"]["content"].strip()

    try:
        parsed = json.loads(text)
        intent = parsed["intent"]
        results.append((prompt, intent))
    except Exception:
        print(f"⚠️ Failed to parse response for prompt:\n  {prompt}\n  → Raw output: {text}")
        results.append((prompt, "INVALID"))

# === Save Results to CSV ===
with open("intent_classification_output.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["prompt", "intent"])
    writer.writerows(results)

print("✅ Done. Results written to intent_classification_output.csv")
