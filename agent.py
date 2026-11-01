import json
import os
import time
from google import genai
from google.genai import types

MODEL = "gemini-3.1-flash-lite"
MAX_RETRIES = 1
CALLS = 0


class APIError(Exception):
    """API/quota problem: stop immediately instead of wasting more calls."""


# ---------------- LLM wrapper (swap this one function for another provider) ----------------
def get_key() -> str:
    try:
        from google.colab import userdata
        return userdata.get("GEMINI_API_KEY").strip()
    except Exception:
        return os.environ["GEMINI_API_KEY"].strip()


def call_llm(prompt: str) -> str:
    global CALLS
    client = genai.Client(api_key=get_key())
    for attempt in range(3):
        time.sleep(2)
        CALLS += 1
        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            return resp.text
        except Exception as e:
            if "503" in str(e) and attempt < 2:  # temporary overload only
                time.sleep(15)
                continue
            raise APIError(str(e)[:300])


def parse_json(text: str) -> dict:
    text = text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(text)


# ---------------- Prompts (all in one place) ----------------
PLANNER_PROMPT = """You are a planner. Given a word problem, output a short numbered plan (3-6 steps).
Do NOT solve the problem. Output ONLY JSON: {{"plan": ["step 1", "step 2", ...]}}

Example 1:
Question: Alice has 3 red apples and twice as many green apples as red. How many apples in total?
{{"plan": ["Red = 3", "Green = 2 x red", "Total = red + green", "Format answer"]}}

Example 2:
Question: A train leaves at 14:30 and arrives at 18:05. How long is the journey?
{{"plan": ["Convert both times to minutes", "Subtract (add 24h if arrival is next day)", "Convert back to hours and minutes", "Format answer"]}}

Example 3:
Question: A meeting needs 60 minutes. Free slots: 09:00-09:30, 09:45-10:30. Which fit?
{{"plan": ["Compute length of each slot", "Keep slots with length >= 60", "List them"]}}

{feedback}
Question: {question}
"""

EXECUTOR_PROMPT = """You are an executor. Follow the plan exactly and show intermediate calculations.
Output ONLY JSON: {{"steps": "<intermediate calculations>", "answer": "<short final answer>", "explanation": "<1-2 sentence user-friendly explanation>"}}

Example:
Question: Alice has 3 red apples and twice as many green apples as red. Total?
Plan: ["Red = 3", "Green = 2 x red", "Total = red + green"]
{{"steps": "red=3; green=2*3=6; total=3+6=9", "answer": "9 apples", "explanation": "Alice has 3 red and 6 green apples, so 9 in total."}}

Question: {question}
Plan: {plan}
"""

VERIFIER_PROMPT = """You are a verifier. First solve the question yourself, independently, WITHOUT looking at the proposed answer.
Then compare with the proposed solution. Decide same_answer by MEANING only: ignore wording, formatting, spelling of units and order of items.
Also check constraints (times valid, counts non-negative, totals consistent).
Output ONLY JSON:
{{"independent_answer": "<your answer>", "same_answer": true/false, "constraints_ok": true/false, "details": "<short reason>"}}

Example:
Question: Alice has 3 red apples and twice as many green. Total?
Proposed answer: 9 apples
{{"independent_answer": "9 apples", "same_answer": true, "constraints_ok": true, "details": "3 + 6 = 9, matches."}}

Example:
Question: Train leaves 14:30, arrives 18:05. Duration?
Proposed answer: 4 hours 35 minutes
{{"independent_answer": "3 hours 35 minutes", "same_answer": false, "constraints_ok": true, "details": "18:05 - 14:30 is 3h35m, not 4h35m."}}

Question: {question}
Proposed answer: {answer}
Proposed steps: {steps}
"""


# ---------------- The three phases ----------------
def planner(question: str, feedback: str = "") -> list:
    fb = f"A previous attempt failed verification because: {feedback}\nMake a better plan.\n" if feedback else ""
    return parse_json(call_llm(PLANNER_PROMPT.format(question=question, feedback=fb)))["plan"]


def executor(question: str, plan: list) -> dict:
    return parse_json(call_llm(EXECUTOR_PROMPT.format(question=question, plan=json.dumps(plan))))


def verifier(question: str, solution: dict) -> dict:
    return parse_json(call_llm(VERIFIER_PROMPT.format(
        question=question, answer=solution["answer"], steps=solution["steps"])))


# ---------------- Agent loop ----------------
def solve(question: str) -> dict:
    retries = 0
    feedback = ""
    while True:
        plan, solution = [], {}
        try:
            plan = planner(question, feedback)
            solution = executor(question, plan)
            v = verifier(question, solution)
        except (json.JSONDecodeError, KeyError, TypeError) as e:  # bad model output (APIError is NOT caught)
            v = {"same_answer": False, "constraints_ok": False,
                 "details": f"Malformed model output: {e}", "independent_answer": ""}

        same = str(v.get("same_answer")).lower() == "true"
        ok = str(v.get("constraints_ok")).lower() == "true"
        details = str(v.get("details"))
        checks = [
            {"check_name": "independent_resolve", "passed": same,
             "details": f"Verifier answer: {v.get('independent_answer')}. {details}"},
            {"check_name": "constraint_check", "passed": ok, "details": details},
        ]
        meta = {"plan": " | ".join(plan), "checks": checks, "retries": retries}

        if same and ok:
            return {"answer": solution.get("answer"), "status": "success",
                    "reasoning_visible_to_user": solution.get("explanation"), "metadata": meta}
        if retries >= MAX_RETRIES:
            return {"answer": "Could not produce a verified answer.", "status": "failed",
                    "reasoning_visible_to_user": f"Verification failed after {retries} retries: {details}",
                    "metadata": meta}
        retries += 1
        feedback = details


# ---------------- CLI (python agent.py) ----------------
if __name__ == "__main__":
    print("Reasoning agent. Type a question (or 'quit').")
    while True:
        q = input("\n> ").strip()
        if q.lower() in ("quit", "exit", ""):
            break
        print(json.dumps(solve(q), indent=2))
