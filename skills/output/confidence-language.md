# Output Skill: Confidence Language

**Loaded by:** Communication Agent.
**Purpose:** Translate the Validator's A–F confidence grade into recipient-facing language that calibrates the statement to the evidence. A grade-A finding sounds like a grade-A finding; a grade-C finding sounds like a grade-C finding. The recipient learns, over time, what each register means.

The discipline here is the opposite of the LLM's natural tendency. LLMs default to confident-sounding prose because confident prose reads cleanly. This skill reins that tendency in so that uncertainty is *visible*, not laundered into smooth language.

## The grade-to-language map

| Grade | Register | Sample headline language | Sample caveat language |
|---|---|---|---|
| **A** | Direct statement | *"Account 47 instock dropped 19 points over the past 4 weeks."* | *(no hedge required in headline; high-severity caveats from the run still appear in the CAVEATS section)* |
| **B** | Direct statement + caveat | *"Account 47 instock dropped 19 points over the past 4 weeks. (Caveat: 2 of the 4 weeks include a partial-data refresh that may understate the drop magnitude.)"* | *"Magnitude estimate has a wider confidence interval than typical due to data-refresh issues."* |
| **C** | Preliminary / signal framing | *"Initial signal suggests Account 47 instock may have dropped 12–22 points over the past 4 weeks. Further confirmation would benefit from..."* | *"Result is preliminary; would benefit from longer observation window and partial-correlation analysis to rule out seasonality."* |
| **D** | *not rendered* | — | — |
| **F** | *not rendered* | — | — |

## Calibrated phrases — quick reference

These translate statistical language into business-facing confidence levels:

| Statistical situation | Grade-A phrasing | Grade-B phrasing | Grade-C phrasing |
|---|---|---|---|
| Robust effect, large sample | *"X is..." / "X dropped by..."* | *"X is, subject to..."* | *"Initial signal suggests X..."* |
| Statistically significant + practically meaningful + triangulated | *"... is associated with..."* (if causation not established) | *"... appears associated with..."* | *"... may be associated with..."* |
| Direction confirmed, magnitude uncertain | *"X dropped by an estimated <range>"* | *"X likely dropped by <range>; estimate uncertain due to..."* | *"X may have moved, but direction itself is not yet established with confidence"* |
| Null result, adequately powered | *"No evidence of X within the detectable range (≥ <effect> at n=<size>)"* | *"No evidence of X above <threshold>; some sensitivity to..."* | *"No detectable effect; analysis was underpowered to rule out a smaller effect"* |

## Statistical jargon stays in the Methodology footer — NOT in body text

The recipient-facing body of any action card or descriptive summary uses **plain business English**. Statistical notation — `p`, `ρ`, `r`, `t`, `χ²`, `U`, "Spearman", "Pearson", "Mann-Whitney", "Kruskal-Wallis", "modified z-score", "Benjamini-Hochberg", "BH-adjusted", confidence interval bounds like `[−0.0112, −0.0038]`, sample-size annotations like `n=97` — does NOT appear in:

- The ALERT line
- The WHY THIS MATTERS section
- The ROOT CAUSE section
- The RECOMMENDED ACTION section
- The descriptive-summary key observations
- The TL;DR

All statistical methodology — test names, p-values, test statistics, CI bounds, effect sizes with notation, sample sizes — lives in the Methodology footer at the bottom of each card, typically inside a `<details>` block. The body restates the same information in business language:

| Statistical phrasing (Methodology footer) | Business phrasing (body) |
|---|---|
| `Spearman ρ=−0.235, BH-adjusted p=0.067, n=97` | "weakly negatively associated" or "a small inverse relationship" |
| `Mann-Whitney U=0, p=0.000377` | "every observation falls outside the rest of the network's range" or "the gap is total" |
| `modified z = −24.46` | "more extreme than any other entity by a wide margin" |
| `n=4 weeks, no historical baseline` | "based on only 4 weeks of data, with no longer history available" |
| `slope −0.0075/week, p=0.013` | "declining week after week" / "the metric is moving down each week" |
| `Cohen's d = 0.6` | "a moderate difference" (with the absolute business-unit difference cited) |
| `R² = 0.97` | omit, OR rephrase as "the trend is consistent across all 4 weeks" |

The rule: **if the recipient is an executive, every sentence in the body should be readable by someone who has never taken a statistics course.** If they want methodology depth, they expand the `<details>` block at the bottom. The skill's job is to translate, not to make the recipient learn the system's analytical methods.

## Hedge words that mean something — and hedge words that don't

**Use these — they encode specific uncertainty:**
- *"95% CI: <lower> to <upper>"* — exact uncertainty quantification.
- *"Effect size <value> (medium)"* — calibrated magnitude statement.
- *"Initial signal" / "preliminary" / "candidate finding"* — grade-C marker, paired with what would raise it to B/A.
- *"Conditional on X, the relationship is Y"* — explicit conditioning.

**Avoid these — they imply uncertainty without specifying it:**
- *"It seems that..."* — what does "seems" mean? Use the grade-appropriate phrase.
- *"Suggests that perhaps..."* — double hedge; one is enough if calibrated.
- *"Could potentially..."* — generic hedge; offers nothing.
- *"To some extent..."* — non-specific; either quantify the extent or drop the hedge.

## Causation vs. correlation language — calibrated by the Root Cause Investigator's flag

The Root Cause Investigator's `primary_root_cause.causation_vs_correlation` field carries three values that map directly to language:

| Investigator flag | Language for the action card |
|---|---|
| `established_causal` (experimental or quasi-experimental design backing it) | *"caused by," "drove," "produced"* |
| `strong_correlation` (large effect, triangulated, plausible mechanism, ruled-out alternatives) | *"strongly associated with," "coincided with," "is consistent with"* |
| `associational` (relationship present but mechanism / alternatives not fully ruled out) | *"is associated with," "co-occurs with"* |

The Communication Agent reads this flag and selects language accordingly. **Promoting `associational` to causal language is a render bug.**

## Confidence about the *absence* of findings

For descriptive summaries (see [descriptive-summary-format.md](descriptive-summary-format.md)), the conclusion sentence carries its own calibration:

- **Strong all-clear (Validator passed forward zero candidates with reasonable analytical depth):** *"No findings rose to action level this period."*
- **Soft all-clear (Validator passed forward zero, but the run had reduced depth — e.g., a stage skipped due to failure):** *"No findings rose to action level on the areas examined this period. <Affected stage> was skipped — see Caveats."*
- **Conditional all-clear (some areas had findings, others were stable):** *"Outside the action cards above, no other items required attention."*

Never assert *"nothing is wrong"* — the system did not check everything in the universe of possible problems. The phrase is *"nothing rose to action level,"* which is what the system actually established.

## Required practices

1. **Read the Validator's grade before drafting language.** The grade determines the register; the language follows.
2. **Match causation flags literally.** Do not soften or strengthen the causal language relative to what the investigator's flag supports.
3. **Carry forward Validator-required caveats verbatim.** If the Validator's `required_caveats` field has a specific caveat, use that wording — do not paraphrase into smoother prose.
4. **When in doubt, weaken.** A finding stated with too much confidence and later refuted costs more recipient trust than a finding stated with too little confidence and later confirmed.

## Anti-patterns

- **Smoothing uncertainty out of grade-B and grade-C findings.** A grade-C finding rendered as if it were grade-A is the single most damaging render error this system can commit. It teaches the recipient that the system overstates, which means they discount even the grade-A findings.
- **Adding manufactured hedges to grade-A findings to "sound modest."** A grade-A finding is direct. Adding *"it seems that"* doesn't make the system humble; it makes it imprecise.
- **Mixing registers within a card.** If the headline is grade-A direct but the Why-This-Matters is grade-C preliminary, the recipient is confused. The whole card uses one register.
- **Stating absence of evidence as evidence of absence.** *"No evidence of X"* is correct; *"X is not happening"* is overclaim unless the test was adequately powered to rule it out.

## Tie to framing

Confidence-language discipline is one of the most concrete ways the system either earns or erodes recipient trust. The recipient develops, over many runs, an intuition for what *"strongly associated with"* means vs. what *"may be associated with"* means in this system's vocabulary. That intuition is the durable trust the product is building. Every output that abuses the vocabulary — that uses confident language for an uncertain finding, or that softens a robust finding into mush — sets the trust back.

## Output discipline

This skill is loaded with every Communication Agent call. The agent consults the Validator's `findings_review[].grade` and `required_caveats`, and the investigator's `causation_vs_correlation` flag, and applies the appropriate register to every headline, why-this-matters, and root-cause statement. The skill governs language; it does not govern what content is rendered or in what order — those are [insight-first-formatting.md](insight-first-formatting.md), [proactive-action-card.md](proactive-action-card.md), and [descriptive-summary-format.md](descriptive-summary-format.md).
