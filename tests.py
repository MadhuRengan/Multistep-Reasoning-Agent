import json, os, sys
import agent

EASY = [
    ("If a train leaves at 14:30 and arrives at 18:05, how long is the journey?", ["3", "35"]),
    ("Alice has 3 red apples and twice as many green apples as red. How many apples in total?", ["9"]),
    ("A meeting needs 60 minutes. Free slots: 09:00-09:30, 09:45-10:30, 11:00-12:00. Which slots can fit the meeting?", ["11:00"]),
    ("A pen costs 12 rupees. How much do 7 pens cost?", ["84"]),
    ("Ravi is 25. His sister is 7 years younger. What is the sum of their ages?", ["43"]),
]

TRICKY = [
    ("A train leaves at 23:45 and arrives at 02:10 the next day. How long is the journey?", ["2", "25"]),
    ("Alice has 3 red apples and twice as many green apples as red. She gives away 2 green apples. How many does she have now?", ["7"]),
    ("A meeting needs 45 minutes. Free slots: 10:00-10:45, 11:00-11:40. Which slots can fit it?", ["10:00"]),
]

batch = sys.argv[1] if len(sys.argv) > 1 else "easy"
tests = EASY if batch == "easy" else TRICKY

results = json.load(open("run_logs.json")) if os.path.exists("run_logs.json") else []
done = {r["question"] for r in results}

for q, expected in tests:
    if q in done:
        continue
    try:
        out = agent.solve(q)
    except agent.APIError as e:
        print(f"\nSTOPPED (API/quota error, no more calls made): {e}")
        break
    correct = all(x in (out["answer"] or "") for x in expected)
    results.append({
        "level": batch, "question": q, "output": out,
        "verifier_passed": out["status"] == "success",
        "retried": out["metadata"]["retries"] > 0,
        "matches_expected": correct,
    })
    json.dump(results, open("run_logs.json", "w"), indent=2)  # saved after every question
    print(f"[{batch}] {q}\n  answer={out['answer']} | verifier_passed={out['status'] == 'success'} "
          f"| retries={out['metadata']['retries']} | correct={correct}\n")

print(f"Logged questions: {len(results)} | API calls made this run: {agent.CALLS}")
