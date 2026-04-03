"""
Phase 1: Anonymize sanitized_for_eval.json into blind_evaluation_set.json.
Strips all condition markers and maps each entry to a UUID.
"""
import json
import random
import uuid
from pathlib import Path

BASE = Path(__file__).parent
INPUT = BASE / "sanitized_for_eval.json"
OUTPUT_BLIND = BASE / "blind_evaluation_set.json"
OUTPUT_MAPPING = BASE / "id_mapping.json"

with open(INPUT) as f:
    entries = json.load(f)

print(f"Loaded {len(entries)} entries from {INPUT.name}")

blind = []
mapping = {}

for entry in entries:
    uid = str(uuid.uuid4())
    mapping[uid] = entry["eval_id"]
    blind.append({
        "id": uid,
        "question": entry["question"],
        "response": entry["response"],
    })

# Shuffle to break b/lt/im triplet positional grouping
random.shuffle(blind)

with open(OUTPUT_BLIND, "w") as f:
    json.dump(blind, f, indent=2)

with open(OUTPUT_MAPPING, "w") as f:
    json.dump(mapping, f, indent=2)

print(f"Written {len(blind)} entries to {OUTPUT_BLIND.name}")
print(f"Written {len(mapping)} mappings to {OUTPUT_MAPPING.name}")

# Verify: no condition clues in blind file
for entry in blind:
    assert set(entry.keys()) == {"id", "question", "response"}, f"Unexpected keys: {entry.keys()}"
    assert entry["id"] in mapping

print("Verification passed: blind file contains only id/question/response keys")
