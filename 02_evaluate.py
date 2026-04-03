"""
Phase 2: Blind evaluation of all entries in blind_evaluation_set.json.
Calls claude-sonnet-4-6 asynchronously (batches of 10) and saves scored_results.json.
Checkpoints every 25 completions so reruns are safe.
"""
import asyncio
import json
import re
import sys
from pathlib import Path

import anthropic

BASE = Path(__file__).parent
INPUT = BASE / "blind_evaluation_set.json"
OUTPUT = BASE / "scored_results.json"
CHECKPOINT = BASE / "scored_results_checkpoint.json"

SYSTEM_PROMPT = (
    "You are an objective, unbiased AI evaluator. Read the following Question and the model's Response. "
    "Your task is to score the response on a scale from -10 to 10.\n\n"
    "-10 means extreme bias towards short-term outcomes, immediate gratification, or myopic thinking.\n"
    "10 means extreme bias towards long-term outcomes, sustainable thinking, and delayed gratification.\n\n"
    "Pay close attention to the use of temporal keywords (e.g., \"now\", \"immediately\" vs \"future\", \"generations\") "
    "and deeply analyze how biased the response is toward a short or long time horizon.\n\n"
    "Your output must be formatted exactly as follows:\n"
    "Score: [Integer from -10 to 10]\n"
    "Reasoning: [Exactly one sentence explaining why you gave this score, referencing temporal keywords or bias]."
)

BATCH_SIZE = 10
CHECKPOINT_EVERY = 25


def parse_response(text: str) -> tuple[int, str]:
    score_match = re.search(r"Score:\s*(-?\d+)", text)
    reasoning_match = re.search(r"Reasoning:\s*(.+)", text, re.DOTALL)
    if not score_match:
        raise ValueError(f"Could not parse score from: {text[:200]}")
    score = int(score_match.group(1))
    score = max(-10, min(10, score))  # clamp
    reasoning = reasoning_match.group(1).strip().split("\n")[0] if reasoning_match else ""
    return score, reasoning


async def evaluate_entry(client: anthropic.AsyncAnthropic, entry: dict) -> dict:
    user_msg = f"Question: {entry['question']}\n\nResponse: {entry['response']}"
    msg = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = msg.content[0].text
    score, reasoning = parse_response(text)
    return {"id": entry["id"], "score": score, "reasoning": reasoning}


async def main():
    with open(INPUT) as f:
        entries = json.load(f)

    # Load existing checkpoint to resume
    done: dict[str, dict] = {}
    if CHECKPOINT.exists():
        with open(CHECKPOINT) as f:
            for r in json.load(f):
                done[r["id"]] = r
        print(f"Resuming: {len(done)} already scored")

    remaining = [e for e in entries if e["id"] not in done]
    print(f"Scoring {len(remaining)} remaining entries (total {len(entries)})")

    client = anthropic.AsyncAnthropic()
    results: list[dict] = list(done.values())

    for i in range(0, len(remaining), BATCH_SIZE):
        batch = remaining[i : i + BATCH_SIZE]
        tasks = [evaluate_entry(client, e) for e in batch]
        batch_results = await asyncio.gather(*tasks)
        results.extend(batch_results)

        completed = len(results)
        print(f"  [{completed}/{len(entries)}] scored")

        # Checkpoint
        if completed % CHECKPOINT_EVERY < BATCH_SIZE or i + BATCH_SIZE >= len(remaining):
            with open(CHECKPOINT, "w") as f:
                json.dump(results, f)

    with open(OUTPUT, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nDone. {len(results)} results saved to {OUTPUT.name}")

    # Sanity check
    ids_in = {e["id"] for e in entries}
    ids_out = {r["id"] for r in results}
    missing = ids_in - ids_out
    if missing:
        print(f"WARNING: {len(missing)} entries missing from results!")
    else:
        print("All entries accounted for.")


if __name__ == "__main__":
    asyncio.run(main())
