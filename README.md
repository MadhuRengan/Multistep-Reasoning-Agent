# Multi-Step Reasoning Agent with Self-Checking

A small agent that solves word problems (time differences, counting, scheduling) in three internal phases: **Planner → Executor → Verifier**. The user only sees a short answer and a short explanation. The plan, verification checks and retry count are kept in `metadata` for debugging and evaluation.

- **Language:** Python
- **LLM provider:** Google Gemini API (free tier), through the `google-genai` SDK
- **Interface:** CLI (`python agent.py`) and a function `solve(question) -> dict` (usable from a notebook)

## Files

| File | Purpose |
|---|---|
| `agent.py` | Prompts, planner, executor, verifier, retry loop, LLM wrapper, CLI |
| `tests.py` | 5 easy + 3 tricky questions, logs each result to `run_logs.json` |
| `run_logs.json` | Example run logs: question, final JSON, verifier result, retried or not |
| `README.md` | This file |

## How to run

1. Get a free API key at [Google AI Studio](https://aistudio.google.com) (Get API key → Create API key).
2. Install and set the key:

```bash
pip install google-genai
export GEMINI_API_KEY="your-key"        # Windows: set GEMINI_API_KEY=your-key
```

3. Run:

```bash
python agent.py              # interactive CLI, type a question
python tests.py easy         # runs the 5 easy questions, appends to run_logs.json
python tests.py tricky       # runs the 3 tricky questions, appends to run_logs.json
```

**In Google Colab:** save the key as a Secret named `GEMINI_API_KEY` and turn on "Notebook access". `agent.py` reads it automatically. Then use `%run tests.py easy` or:

```python
from agent import solve
print(solve("A pen costs 12 rupees. How much do 7 pens cost?"))
```

To change the model, edit the `MODEL = "..."` line at the top of `agent.py`. To use another provider, change only the `call_llm` function.

## Output format

```json
{
  "answer": "<final short answer>",
  "status": "success | failed",
  "reasoning_visible_to_user": "<short explanation, no raw chain-of-thought>",
  "metadata": {
    "plan": "<plan steps joined with ' | '>",
    "checks": [{"check_name": "...", "passed": true, "details": "..."}],
    "retries": 0
  }
}
```

The executor's detailed intermediate steps are never returned to the user. Only its one-to-two sentence explanation is.

## How the agent works

1. **Planner** reads the question and returns a short numbered plan as JSON. It does not solve the problem.
2. **Executor** follows the plan and returns JSON with its intermediate steps, a short answer and a short explanation.
3. **Verifier** first solves the question independently, without trusting the proposed answer. It then compares the two answers by meaning and checks constraints (valid times, non-negative counts, consistent totals). Two checks are recorded in `metadata.checks`: `independent_resolve` and `constraint_check`.
4. If either check fails, the agent retries (new plan, with the verifier's reason fed back to the planner), up to `MAX_RETRIES = 1`. After that it returns `status: "failed"` with the reason.

### Where the prompts live

At the top of `agent.py`: `PLANNER_PROMPT`, `EXECUTOR_PROMPT` and `VERIFIER_PROMPT`. Each one fixes the output format (JSON only) and includes worked examples (3 for the planner, 1 for the executor, 2 for the verifier, including one where the verifier catches a wrong answer).

### Error handling

- **Quota or API errors (for example 429):** the agent raises `APIError` and the test runner stops immediately. This avoids wasting more calls on a quota that is already used up.
- **Temporary overload (503):** `call_llm` waits and retries up to 3 attempts.
- **Malformed model output (bad JSON or missing fields):** treated as a failed verification, which triggers the normal retry path.
- **Progress is saved after every question**, and already-logged questions are skipped on a rerun, so a run can resume later without repeating work.

## Assumptions

- Times are in 24-hour format. If the arrival time is earlier than the departure time, the arrival is on the next day.
- A slot exactly as long as the meeting fits (the boundary is inclusive).
- A test counts as "correct" if the answer contains the required substrings (for example "84" or "11:00"). This is a simple check, not a full grader.

## Test results

All questions passed verification on the first attempt (retries = 0). Full JSON for each is in `run_logs.json`.

| Level | Question | Answer | Verifier passed | Retried |
|---|---|---|---|---|
| easy | Train 14:30 → 18:05, how long? | 3 hours and 35 minutes | yes | no |
| easy | Alice: 3 red apples, twice as many green, total? | 9 apples | yes | no |
| easy | 60-minute meeting, slots 09:00-09:30, 09:45-10:30, 11:00-12:00 | 11:00-12:00 | yes | no |
| easy | Pen costs 12 rupees, cost of 7 pens? | 84 rupees | yes | no |
| easy | Ravi is 25, sister 7 years younger, sum of ages? | 43 | yes | no |
| tricky | Train 23:45 → 02:10 next day (crosses midnight) | 2 hours and 25 minutes | yes | no |
| tricky | Alice's apples, then gives away 2 green (multi-step) | 7 apples | yes | no |
| tricky | 45-minute meeting, slot 10:00-10:45 (exact-fit boundary) | 10:00-10:45 | yes | no |

Because of free-tier quota limits, the logs were produced in batches on two models: the first two easy questions on `gemini-3.5-flash`, and the remaining six on `gemini-3.1-flash-lite`.

## Prompt design: why it is built this way

- **Three separate prompts**, one per phase, so each has a single job and can be improved on its own.
- **JSON-only output with examples** makes the replies easy to parse. The API is also asked for a JSON mime type, which reduces malformed output.
- **The verifier solves the question independently first.** If it saw the proposed answer first, it would tend to just agree with it.
- **The verifier compares meaning, not wording**, so "11:00-12:00" and "the 11:00 to 12:00 slot" count as the same answer.
- **Failure feedback is passed to the planner on retry**, so the next plan can avoid the previous mistake.
- **Short user-facing explanation, detailed steps kept internal**, as required by the assignment.

## What didn't work well (problems met while building)

- **Invalid API key.** The first runs used a placeholder string instead of a real key. The agent handled it as designed: it retried, then returned `status: "failed"` with the reason. This was also a useful accidental test of the failure path.
- **Colab secret is not an environment variable.** The key saved in Colab Secrets was not visible to `os.environ`, so `call_llm` now reads the secret directly when running in Colab.
- **Retired model name.** `gemini-2.5-flash` returned 404 for a new user. Model names must be checked against the current model list.
- **Very small free quotas that are counted per model.** The first retry loop also retried on 429 errors, which only burned more quota. It now stops immediately on quota errors and only retries 503s.
- **Overload errors (503).** These needed a short wait-and-retry inside `call_llm`.
- **Stale module in a notebook.** Editing `agent.py` had no effect until the session was restarted, because the old module stayed cached.
- **Verifier too literal (a risk I identified and fixed in the prompt).** A verifier comparing exact text can reject correct answers that are worded differently, so the prompt tells it to compare meaning and ignore wording, formatting and order.
- **Slow responses** on busy free-tier models, which made the full suite take many minutes.

## Limitations

- All 8 test questions passed on the first attempt, so the retry-after-a-wrong-answer path was exercised in practice only by API failures, never by a genuine reasoning mistake.
- The executor does its arithmetic with the LLM, and the verifier is also an LLM, so both could make the same mistake.
- The test suite is small (5 easy + 3 tricky) and uses a simple substring check for correctness.

## What I would improve with more time

- Run arithmetic and time calculations in Python code instead of the LLM, and add that as a third, code-based verifier check.
- Add more tricky tests (ambiguous numbers, multi-day times, unit conversions) and a summary score.
- Inject deliberately wrong executor answers to prove the verifier catches them and the retry loop recovers.
- Use a stronger model for the verifier than for the executor.
- Add exponential backoff and rate-limit awareness so large test runs fit within free-tier quotas.
