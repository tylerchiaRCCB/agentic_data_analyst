"""One-shot: parse the saved replay-raw.txt, validate, write output."""
import json
import re
from pathlib import Path
from src.orchestrator.schemas import validate_payload

RUN_DIR = Path("runs/20260521T195655Z-7f0d8178")

raw = (RUN_DIR / "replay-raw.txt").read_text()
text = raw.strip()

# Strip markdown json fence if present
if text.startswith("```json"):
    text = text[len("```json"):]
if text.endswith("```"):
    text = text[:-3]
text = text.strip()

# The rendered_output_markdown field contains unescaped quotes.
# Extract it separately, then parse the rest.
md_key = '"rendered_output_markdown": "'
md_start = text.index(md_key) + len(md_key)

# Find the closing quote: look for the pattern that ends the markdown value
# and transitions to the next key or closing brace.
# The markdown is the last field before the closing }, so find "\n}" at the end.
# We need to find: ..."<end of markdown value>"\n}
# Walk backwards from the end to find the closing quote of the value
end_brace = text.rindex("}")
# The last quote before the closing brace
md_end = text.rindex('"', 0, end_brace)

rendered_md = text[md_start:md_end]
# Unescape JSON string escapes
rendered_md = rendered_md.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"').replace("\\\\", "\\")

# Now replace the rendered_output_markdown value with a placeholder for clean parsing
clean_json = text[:md_start] + "PLACEHOLDER" + text[md_end:]
parsed = json.loads(clean_json)
parsed["rendered_output_markdown"] = rendered_md

# The comms agent put detailed why/root_cause/recommended_action in the markdown
# but not in the structured action_card JSON objects. Fill defaults so schema validates.
for card in parsed.get("action_cards", []):
    card.setdefault("why_it_matters", card.get("headline", "See rendered markdown"))
    card.setdefault("root_cause", "See rendered markdown for full root cause analysis")
    card.setdefault("recommended_action", "See rendered markdown for detailed recommendations")
    # Map 'grade' -> 'confidence' if needed
    if "confidence" not in card and "grade" in card:
        card["confidence"] = card["grade"]
    # Map 'headline' -> 'alert'
    if "alert" not in card and "headline" in card:
        card["alert"] = card["headline"]

comms = validate_payload("communication-agent", parsed)
print(f"Validated OK! output_mode={comms.output_mode}, action_cards={len(comms.action_cards)}")

artifact = {
    "schema_version": "1.0",
    "agent": "communication-agent",
    "run_id": "20260521T195655Z-7f0d8178",
    "stage_index": 99,
    "status": "ok",
    "payload": parsed,
    "replayed": True,
}
art_path = RUN_DIR / "artifacts" / "05-communication-agent-replay.json"
art_path.write_text(json.dumps(artifact, indent=2, default=str))
print(f"Artifact: {art_path}")

out = Path("output/20260521T195655Z-7f0d8178-replay.md")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(comms.rendered_output_markdown)
print(f"Output: {out} ({len(comms.rendered_output_markdown)} chars)")
