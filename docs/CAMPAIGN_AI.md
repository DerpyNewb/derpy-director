# CAMPAIGN_AI.md — how the campaign AI actually works, and what a mod can reach

What the turn-based campaign AI is, in CA's own description; where that shape is visible in the
database; the complete documented script surface with the read half separated from the write
half; and the things that have no hook at all.

Battle AI is a different system and is barely covered here — see §8.

**Sources, and how much each is worth:**

| Source | Weight | Checked |
|---|---|---|
| "Analysing AI Behaviour in Total War", CA x BAFTA Games livestream — Duygu Cakmak (senior AI programmer), Csaba Toth (senior AI designer) | CA describing their own design, out loud. **Three Kingdoms era** — see the caveat in §1 | 2026-09-13 |
| `Modding Files/reference/ca_script_docs_wh3/` — `campaign/episodic_scripting.html`, `scripting_doc.html` | CA's own WH3 reference. Authoritative on signatures, **incomplete on vocabularies** (§7) | 2026-09-13 |
| Vanilla DB via `tools/read_vanilla_cache.py` (RPFM shut) | Measured, not inferred | 2026-09-13 |
| **CA's own 831 shipped Lua files**, staged decompressed at `Modding Files/reference/ca_scripts_wh3/` (so every grep below is one command and re-runnable) | CA's shipped *usage* of these calls. Settles argument shapes the docs leave ambiguous, and a zero-hit grep is real evidence about what CA never uses. The 831 were the 8.x set; the folder now holds 9.0's 899 `.lua` (extracted 2026-09-25), and the zero-hit greps below and the six quick-deal calls were re-run against it on 2026-10-09 and still hold | 2026-09-13 |
| `docs/sessions/HANDOFF_20260912_CAMPAIGN_AI_SCRIPT_CONTEXTS.md` | The script-context layer in depth — 177 `cai_*` tables enumerated, the seven override subsystems measured row by row | 2026-09-12 |
| `docs/sessions/HANDOFF_20260913_EXCHANGE_AI_STANCE.md` | The first shipped use of the stance manager in this workspace; the Director (`derpy_director.lua`, `beat_stance`) is the second | 2026-09-13 |
| `docs/sessions/HANDOFF_20260829_CONCLAVE_AI.md` | Why Ghorth's AI sits still — a worked diagnosis ending at the personality row | 2026-08-29 |

---

## 1. There is no central brain. This is CA's design, not an accident

The single most useful thing in the CA talk, from Cakmak at 31:23, near-verbatim: **the AI does
not have a central brain that decides a central plan.** They state the reasoning directly. The
state space is impossible — their own toy example is 40 factions with one army, one territory and
one enemy each and two possible actions, giving 2^39 (over 500 billion) states **for a single
round**. The real game has many armies, a dozen interconnected systems and hundreds of turns.

So they split the search space into domains and solve each one separately, in its own terms:

| Domain | Technique CA names |
|---|---|
| Task management (what armies are told to do) | Monte Carlo tree search |
| Army movement (the "coordinator" layer under it) | heavily modified MCTS |
| Diplomacy | utility AI over generated candidate deals |
| Finance | sits **on top**, allocating budget to each other system |

Two things hold the committee together, and only two:

- **The finance system**, which is *indirect* control. It does not tell the diplomacy system what
  to do; it decides how much money diplomacy gets. Cakmak's word for this is "steers".
- **Strategic context** — one measure of how much trouble the faction is in relative to its own
  strength. This one feeds nearly every decision the AI makes.

Everything else is solved locally and does not coordinate.

**Caveat, and it is a real one.** The talk is Three Kingdoms. WH3 is a later game on a descended
codebase, and nothing in the talk is a WH3 guarantee. But the WH3 database independently shows the
same shape — `cai_personalities` has a separate swappable component column *per domain* (§2), and
`cai_context_types` drives seven separately-overridable subsystems (§6). Treat the architecture as
corroborated and the specific algorithms (MCTS, utility) as 3K-era and unverified for WH3.

**Why this matters for modding, and it is the whole point of this document:** you are never
persuading a strategist. There is no mind to convince. You are changing inputs that individual
departments already read, and letting each react in its own terms. A mod that moves a number is
working *with* the architecture. A mod waiting for the AI to "notice" something and form an
intention about it is waiting for a thing that does not exist.

### Other claims from the talk worth keeping

- **Difficulty is essentially one multiplier.** Toth, 38:56: the higher the difficulty, the more
  the AI weights **the player** as a threat. One value, propagating organically through
  everything downstream. Not per-system cheats.
- **The AI plays the same game you do.** Not a simplified model. It solves the same problems.
- **AI memory has a horizon.** It remembers a *subset* of events, decaying over time. Treaty
  breaking is remembered for a configurable number of rounds; resentful personalities remember
  longer. It does not remember the whole campaign.
- **Fog of war applies to the AI.** It only reasons about factions it has actually met.
- **Diplomacy picks by weighted random among good deals**, not argmax. It generates many candidate
  deals from components, scores each, then samples. This is why an AI's diplomatic behaviour is
  not reproducible turn to turn even from an identical state.
- **Campaign AI and battle AI are separate systems** with very little interface between them. The
  campaign AI does try to pick battles that are not foregone conclusions.

---

## 2. Where the committee is visible in the database

`cai_personalities` — **227 rows x 33 columns**, table version 6. One row is one complete AI
roster. A faction is assigned a row and that row names a separately swappable component for each
domain, exactly as §1 predicts.

Measured distinct values across all 227 rows, which is the part worth having:

| Column | Distinct | Read this as |
|---|---:|---|
| `key` | 227 | — |
| `task_management_system_task_generation_profile` | 192 | **what tasks it generates.** By far the most varied column in the table |
| `region_group_profile` | 99 | **where it wants to go** |
| `displayed_trait_set` | 79 | cosmetic — the traits shown to the player |
| `deal_evaluation_profile` | 51 | how it values an offer |
| `deal_generation_component` | 39 | what it offers you |
| `gds_occupation_decision_profile` | 24 | occupy / raze / sack |
| `strategic_component` | 20 | |
| `strategic_profile` | 19 | expansion and aggression; see the handoff for its 78-row component table |
| `construction_system_policy` | 13 | |
| `budget_policy_key` | 12 | |
| `cultural_component`, `personality_variables_profile`, `technology_manager_key` | 8 each | |
| `diplomatic_component`, `negotiation_component`, `income_allocation_policy`, `tms_variables_profile` | 3 each | |
| `agent_embed_profile`, `empire_rivalry_component`, `military_behaviour_policy`, `reliability_policy_key`, `trespassing_component` | 2 each | |
| `agent_distribution_profile_key`, `agent_recruitment_profile_key`, `allowed_for_random_selection`, `character_skill_selection_policy`, `financial_context_control`, `gds_cultural_occupation_decision_profile`, `military_aggressiveness_policy`, `military_generator_config_override`, `occupation_decision_component`, `ritual_policy` | **1** | CA never varies these. Ten dead knobs |

Two conclusions that are easy to get wrong:

- **A "personality" is overwhelmingly about what tasks a faction generates and which regions it
  wants.** 192 and 99 distinct values against 1 distinct value for
  `military_aggressiveness_policy`. Aggression is not a dial CA turns; *targeting* is.
- **Ten of the 33 columns are single-valued across the entire vanilla table.** Before building
  anything on one of them, note that you have no vanilla precedent that the engine reads it at
  all. See [[wh3-vanilla-row-count-is-not-behaviour]] — and the inverse applies here just as
  hard.

**The personality is assigned in the startpos.** No DB edit in a pack reaches that assignment.
Adding a row to `cai_personalities` gives you a row nothing references. The only runtime route is
`cm:force_change_cai_faction_personality` (§4). See
[[wh3-cai-personality-is-the-aggression-knob]] and, for a worked case where this was the actual
diagnosis, `HANDOFF_20260829_CONCLAVE_AI.md` §5 — Ghorth sits still because CA assigned the
Conclave a `sentinel` personality whose deal-generation and negotiation components are both
passive. Three departments each independently deciding to do nothing.

---

## 3. The causal chain, in CA's own words

From `episodic_scripting.html`, the preamble to the AI section — quote it at anyone who conflates
these layers:

> Diplomatic events (e.g. gifts, trespassing) lead to changes in attitude, which leads to changes
> in strategic stance, which leads to changes in behaviour.

So there are three distinct layers, and they are **not** the same number:

```text
diplomatic event  ->  attitude (the diplomacy screen number)  ->  strategic stance  ->  behaviour
   cai_add_diplomatic_event        diplomatic_standing_with()      the stance manager
```

CA adds the caveat that makes stance worth using at all: stance and attitude are *loosely*
correlated, not locked. Set two hostile factions to `BEST_FRIENDS` and they behave better toward
each other **while still appearing hostile on the diplomacy screen**, with attitude drifting up
over time as positive events accumulate.

**The trap this creates.** Attitude is *downstream* of stance. So any script that computes a
stance promotion from a term that includes diplomatic standing has built a feedback loop with
positive gain: promote a stance, standing moves, standing feeds the next promotion, and the
faction walks to an extreme under its own power within a few turns — with nothing in any log to
find. This is not hypothetical; it was caught during design in
`HANDOFF_20260913_EXCHANGE_AI_STANCE.md` §3.2, and the fix was a build-time assertion that greps
the scoring function for `standing_of` / `stance_of` rather than a comment asking nicely.

**If you want to move attitude, move attitude.** `cm:cai_add_diplomatic_event(from, to, action)`
takes a key from `cai_personality_diplomatic_events` and is the granular, in-fiction way to do it
— the AI gets a *reason* it already understands, instead of a stance override with no cause
attached.

---

## 4. The write surface — every documented call

All verified present in `episodic_scripting.html` on 2026-09-13 via
`py tools/check_lua_api.py --explain <member>`.

**Mind the receiver conventions**, which are inconsistent and unmarked in the docs:

### Strategic stance (7 calls) — all take faction KEY STRINGS, both arguments

| Call | Effect |
|---|---|
| `..._promote_specified_stance_towards_target_faction(fkey, target, stance)` | "Makes it much more likely" the stance will be the supplied one. A thumb on the scale, **not** a set |
| `..._block_all_stances_but_that_specified_towards_target_faction(fkey, target, stance)` | Forbids every other stance. CA describes the effect plainly: this one **sets** the stance |
| `..._set_stance_promotion_between_factions_for_a_given_stance(fkey, target, stance, start_round, start_level, end_round, end_level)` | A **ramp**. Promotes the stance over a span of turns, interpolating from `start_level` to `end_level`. The only call here with a time dimension — use it for a relationship that should sour or warm gradually rather than snap |
| `..._set_stance_blocking_between_factions_for_a_given_stance(fkey, target, stance, round)` | Blocks **one** stance until `round` (inclusive) |
| `..._clear_all_promotions_between_factions(fkey, target)` | Clears **any** scripted promotion between the pair |
| `..._clear_all_blocking_between_factions(fkey, target)` | Same, for blocks |
| `..._force_stance_update_between_factions(fkey, target)` | Forces a re-pick now; the AI chooses an appropriate new stance |

All seven are prefixed `cm:cai_strategic_stance_manager`. The `_level` arguments are described
only as "a numerical indicator of how likely this stance is to be chosen" — CA gives **no scale,
no bounds and no default**, so any value you pick is unvalidated. Nothing here fails loudly.

Seven stance values, and there are only seven:
`CAI_STRATEGIC_STANCE_{BEST_FRIENDS, VERY_FRIENDLY, FRIENDLY, NEUTRAL, UNFRIENDLY,
VERY_UNFRIENDLY, BITTER_ENEMIES}`.

**And CA never calls a single one of the seven.** A census of all 831 shipped Lua files on
2026-09-13 found **zero** uses of `cai_strategic_stance_manager_*` — against 44 uses of
`cai_disable_movement_for_faction` and 15 of `force_change_cai_faction_personality` (9.0,
re-counted 2026-10-09: still zero, against 44 and 18). So the
missing scale is not an omission you can work around by reading vanilla: there is no vanilla
precedent for *any* `_level` value, because nothing in the shipped game passes one. Anything
built on the stance manager is unaccompanied — which raises the bar on the logging in §9 rather
than lowering it, and is the strongest argument for the off-switch discipline below.

**`clear_all_promotions_between_factions` is not mod-scoped.** It clears CA narrative scripts' and
other mods' promotions for that pair too. Any per-turn clear-then-promote loop is stomping on
everyone else every turn it runs, which is why a feature built on it needs a user-facing off
switch whose off path makes **zero** calls rather than clearing-but-not-promoting.

### Personality, threat, context

| Call | Receiver | Notes |
|---|---|---|
| `cm:force_change_cai_faction_personality(fkey, personality_key)` | **strings** | key from `cai_personalities` |
| `cm:cai_force_personality_change(...)` | | accepts `"all"` |
| `cm:cai_force_personality_change_with_override_round_number(...)` | | |
| `cm:set_base_strategic_threat_score(faction, score)` | **faction interface** | scores correspond to `faction_strategic_threat_levels`. This is the same layer CA's difficulty multiplier moves (§1) |
| `cm:cai_set_global_script_context(key)` / `cai_set_faction_script_context(fkey, key)` | strings | the mode switch — §6 |
| `cm:cai_get_global_script_context()` / `cai_get_faction_script_context(fkey)` | | |
| `cm:cai_clear_global_script_context()` / `cai_clear_faction_script_context(fkey)` | | |

### Diplomacy and points of interest

| Call | Notes |
|---|---|
| `cm:cai_add_diplomatic_event(from_key, to_key, action_key)` | action from `cai_personality_diplomatic_events`. **The in-fiction way to move attitude** (§3) |
| `cm:cai_insert_caravan_diplomatic_event(...)` | caravan-specific variant |
| `cm:cai_add_point_of_interest_generic_marker(group_id, poi_id, x, y, [fkey])` | **logical** coords, not display. See the vocabulary gap in §7 |
| `cm:cai_remove_point_of_interest_generic_marker(...)` | |

**The diplomatic-event vocabulary, measured.** `cai_personality_diplomatic_events` is **104
rows**, keyed `id`, with columns `diplomatic_factor_group_active`,
`diplomatic_factor_group_inactive`, `strategic_threat_multiplier_mod` and `is_transitive`. Two
things follow that change how the call is used:

- **The magnitude is in the DB, not in your call.** `cai_add_diplomatic_event` has no strength
  argument — you choose the event whose factor group already carries the weight you want.
- **Only six of the 104 are script-facing generics:**
  `PAST_EVENT_{POSITIVE,NEGATIVE}_{MINOR,MODERATE,MAJOR}`, all six on factor group
  `diplomatic_factor_past_events`, all six with `strategic_threat_multiplier_mod = 0` and
  `is_transitive = false`. The other 98 are engine-raised occurrences (`CITY_SACKED`,
  `ALLY_REFUSED_TO_JOIN_WAR`, `CULTURAL_DIFFERENCES`, ...), and **79 of the 104 are transitive** —
  they propagate to third parties. The generic six do not, so a scripted grudge stays between the
  two factions unless you pass a specific engine event instead.

CA's own three uses all pass a generic, and all three carry the comment
`-- CHANGE THIS TO A NEW EVENT` (`wh3_dlc26_contracts.lua`), which is CA saying the intended route
for a mod's own reason is a **new row** in that table rather than a borrowed generic. Note the
receivers there are faction **key strings** (`wc:client_faction():name()`).

### Direct suppression — the crude levers

`cai_disable_movement_for_faction` / `_for_character`, `cai_disable_command_assignment_for_character`,
`cai_disable_targeting_against_settlement`, and their `enable` partners. These do not persuade the
AI of anything; they take the option away. CA uses the movement pair to bracket scripted turn-1
sequences.

**Settled 2026-09-13 — the two forms were never in conflict.** `campaign_map_settlements` is
**830 rows**, and its `settlement_id` keys are literally `settlement:<region_key>`. CA's own
scripts build the argument by concatenation in all eight places they use the pair —
`cm:cai_disable_targeting_against_settlement("settlement:"..region_key)` in
`wh2_dlc17_lzd_chaos_map.lua`, `wh2_dlc16_wef_worldroots.lua`, `wh2_dlc17_bloodgrounds.lua` and
`wh2_campaign_confederation_missions.lua`. So the handoff's form is correct and CA's doc wording
describes the same string. **Use the concatenation**, not a table lookup.

One wart, since it fails silently: exactly one of the 830 rows is double-prefixed —
`settlement:settlement:wh3_main_combi_region_the_copper_landing`. That settlement cannot be
reached by the normal construction, and no other row has the defect.

---

## 5. The read surface — `CAMPAIGN_AI_SCRIPT_INTERFACE`

This exists and is easy to miss. It is reached from the model, not the campaign manager:

```lua
local ai = cm:model():campaign_ai()
```

`campaign_ai()` is documented on `MODEL_SCRIPT_INTERFACE` in `scripting_doc.html`. Fourteen
members:

**Stance readback (12).** `strategic_stance_between_factions(queried, considered)` plus
`_available`, `_promotion_or_blocking_is_set`, `_promotion_is_active`, `_promotion_current_level`,
`_promotion_start_round`, `_promotion_start_level`, `_promotion_end_round`, `_promotion_end_level`,
`_is_being_blocked`, `_is_being_blocked_until`.

**Budget readback (2), and these are the interesting ones.**

```lua
ai:funds_available_for_immediate_payment_for_faction_by_area(fkey, area)
ai:funds_available_for_upkeep_for_faction_by_area(fkey, area)
```

`area` is one of `CONSTRUCTION | ARMIES | NAVIES | DIPLOMACY | AGENTS | TECHNOLOGIES | CHARACTERS`.

That is a direct read of the finance system's allocation — the one layer §1 identifies as *the*
coordinating mechanism. An AI faction with its budget swung toward `ARMIES` is a faction whose
other departments have been told, indirectly, to expect a war. **This is the closest thing to
reading AI intent that the game exposes**, and it is a real number rather than an inference.

**The trap.** The write calls take a stance by **string**; the read calls take a stance by
**number** (`stance_by_number` in every signature). CA documents the string enum and does **not**
document the numeric mapping. Assume ordinal order from the enum listing if you must, but verify
in game before trusting it — this is exactly the class of thing that fails silently.

**Do not bother grepping vanilla for the mapping — that was done on 2026-09-13 and came back
empty.** `strategic_stance_between_factions` appears **zero** times in CA's 831 shipped Lua
files, as does every other member of this interface. The number has to come from an in-game
probe: read one pair back at a known scripted stance and print what comes out.

Also note CA's `Return:` field is **blank** on all fourteen. The descriptions imply the types;
the doc does not state them.

---

## 6. Script contexts — the AI mode switch

Covered in full in `HANDOFF_20260912_CAMPAIGN_AI_SCRIPT_CONTEXTS.md`; the essentials only.

Two context types are driven purely from Lua, `cai_global_script_context` and
`cai_faction_script_context`. **Seven AI subsystems** carry a `*_context_overrides_junctions`
table mapping (context, priority) to a behaviour profile — strategic profile, decision profile,
TMS task generators, TMS variable profiles, personality variables, income allocation, deal
evaluation. Setting a context swaps behaviour profiles wholesale across whichever of those seven
have a row for it.

CA's own reference implementation is `script/campaign/wh3_campaign_ai.lua` (830 lines, extracted
from `data_script.pack`) — scripted turn-1 openings for every AI major faction, the Chaos Bastion
flip, and the "AI extra aggro" campaign option, which is literally three lines setting one global
context.

**Landmine.** `wh3_dlc23_campaign_chd_hellforge.lua` maps Chaos Dwarf **army composition** onto
six of the nine faction-context values, writes it on every upgrade evaluation, never clears it,
and persists it across saves. Writing a CHD faction's script context for any other purpose
silently corrupts which units its Hell-Forge upgrades. Only `epsilon` and `zeta` are unclaimed
faction-side. Global contexts are mostly free — vanilla uses two of nine. But the global slot
cannot tell you who wrote it: CA's "AI extra aggro" option writes `special_1` too, and the slot
is process-global, not save-scoped - a fresh campaign was once seen inheriting the previous
campaign's value (`HANDOFF_20260916_COALITION_SOAK_AND_AI_DIRECTOR_RESEARCH.md` §2).

---

## 7. Where CA's documentation is wrong or absent

Three measured gaps. All three fail silently.

1. **The script-context value list in `episodic_scripting.html` is incomplete.** It lists
   `DEFAULT, ALPHA, BETA, GAMMA, DELTA, EPSILON, ZETA` — seven. The database has **nine**:
   those plus `_special_1` and `_special_2`. CA's own `wh3_campaign_ai.lua` uses `special_1` for
   the extra-aggro option and `special_2` for the Bastion flip. **The DB is authoritative; the
   scripting doc is not.**

   **And the doc's names are not the strings you pass.** The argument is the full DB key out of
   `cai_contexts_for_context_types`:
   `cm:cai_set_global_script_context("cai_global_script_context_alpha")`,
   `cai_faction_script_context_beta`, and so on. The default is spelled inconsistently —
   `cai_faction_script_context_type_default`, carrying a `_type` the other eight lack. Passing
   `ALPHA`, or `cai_faction_script_context_default`, does nothing, forever.

   That same table also names a **sixth** context type the write surface cannot reach:
   `cai_difficulty_context`, with five values (easy / normal / hard / very_hard / legendary). It is
   campaign difficulty entering the same override machinery the script contexts use — which is
   §1's "difficulty is one multiplier" showing up in the DB, and means any of the seven override
   subsystems can carry difficulty-keyed rows alongside your script-context ones.
2. **The POI group/id vocabulary is documented nowhere, and vanilla will not supply it.**
   `cai_add_point_of_interest_generic_marker` has a fully documented signature and two completely
   opaque integer parameters. The 2026-09-13 census found **zero** uses of `point_of_interest` in
   all 831 shipped Lua files, so the "dig it out of vanilla scripts" plan named in earlier passes
   is a dead end. Treat the call as unusable without in-game probing of integers you are guessing.

   **What CA uses instead, and it is a working route.** Region groups. `region_groups` is **621
   rows**, of which **61 are `cai_`-prefixed** — `cai_region_hint_area_*` (athel_loren, badlands,
   bretonnia, cathay, ...) plus a `cai_chaos_region_hint_area_*` / `_sub_area_*` set for the Chaos
   invasion. These bind to the AI through the personality's `region_group_profile` column, which
   §2 measures at **99 distinct values — the second most varied column in the table**, i.e. the
   biggest thing CA varies per personality after task generation. Scripts read the same groups
   directly: `region:is_contained_in_region_group("cai_region_hint_area_cathay")`
   (`wh3_dlc25_gelt_dilemmas.lua`).

   So "make the AI want to go there" is a **DB** feature — a region group plus a
   `region_group_profile` — reached at runtime only by `cm:force_change_cai_faction_personality`
   to a row that already points where you want. Not an undocumented marker call.
3. **`cai_evaluate_quick_deal_action` has a wrong `Returns:` field** — it says `nil`, while the
   description says it "returns both the quick deal score and whether the deal can be proposed."
   Believe the description. This matters because of §8.

General rule, already the standing one in `CLAUDE.md`: read the doc **entry**, not the signature.
A parameter's name is not its contract.

---

## 8. What has no hook, and one thing that nearly does

**No hook exists to make an AI faction initiate a trade, a purchase, or any economic transaction
with a mod's systems.** There is no "AI, consider this" callback, no economic decision event to
listen for, no way to insert a candidate action into the task management system. A mod that wants
AI participation in an economy must simulate the AI side itself and settle the results into real
faction state (gold via `cm:treasury_mod`, effects via `cm:apply_effect_bundle`). That is what
`docs/ZHARR_EXCHANGE.md` does.

**The near miss, and it is genuinely useful:**

```lua
local score, can_issue = cm:cai_evaluate_quick_deal_action(faction, met_faction, "diplomatic_option_trade_agreement")
if can_issue and score > 0 then ... end
```

Faction **interfaces** for the first two; `deal_type` from `diplomatic_actions`. It returns **two**
values — the quick deal score and whether the deal can be proposed — and CA states that **a score
greater than zero means the AI would likely accept it**. Ignore the doc's `Returns: nil`.

**Verified against CA's own use, 2026-09-13.** `script/campaign/_narrative/wh3_narrative_shared_chains.lua`
calls it six times, in exactly the shape above: iterate `faction:factions_met()`, skip pairs that
already have the treaty, evaluate, keep the highest score among those where `can_issue` is true.
Deal types seen there: `diplomatic_option_trade_agreement`, `diplomatic_option_nonaggression_pact`,
`diplomatic_option_military_alliance`, `diplomatic_option_confederation`.

`diplomatic_option_trade_agreement` being live is the interesting one for any economy mod: you can
ask, per turn and per pair, whether an AI faction would sign a trade agreement — before offering
anything and without touching its state.

**Confirmed against CA's own use, 2026-09-13.** It is called six times in
`script/campaign/_narrative/wh3_narrative_shared_chains.lua`, always destructured as two values:

```lua
local score, can_issue = cm:cai_evaluate_quick_deal_action(faction, met_faction,
        "diplomatic_option_nonaggression_pact")   -- also _trade_agreement, _military_alliance, _confederation
```

So the description is right and the `Returns: nil` field is simply wrong (§7.3), and CA uses the
call for exactly the purpose below: gating a scripted overture on whether it would be accepted.
The four `deal_type` keys above are the ones vanilla passes.

**It is directional, and the two directions disagree hard.** Measured 2026-09-18 off the
Director's live logs: one pair scored `-14.93` one way and `+5.72` the other, and of 151 pairs
evaluated both ways, 31 had one side positive and none had both. Requiring both sides above zero
is a gate that never opens (`HANDOFF_20260916_COALITION_SOAK_AND_AI_DIRECTOR_RESEARCH.md` §6e).

You cannot make the AI *want* a deal. You can ask, before committing to anything, whether it
would say yes. For gating an offer, choosing a target, or deciding whether a scripted overture is
worth making at all, that is most of the value of a real negotiation hook. It was missed in
earlier passes over this API and is the most underused call in the set.

**Battle AI**, for completeness: three layers, two of them closed to scripting. Separate system,
minimal interface to the campaign side. `script/battle/mod/` loads in **every** battle type with
no gating — a fact that bites. See the 2026-09-12 handoff §2.

---

## 9. How CA validates AI behaviour, and what you actually have

CA's pipeline, from the talk, because knowing the shape of it tells you what they can and cannot
have caught before shipping:

- **Autoruns** — AI-vs-AI games run in parallel on dev machines overnight. Core data to a central
  database; detailed reasoning logs generated on request only, because one game produces 100,000+
  diplomatic considerations and logs run to a million lines.
- **CAT**, a map-replay visualiser over that database: region ownership over time, army movement,
  battles, filterable and comparable across runs. Catches indecisiveness (an army oscillating
  between two points), mass passivity, expansion imbalance.
- **Per-subsystem CSV logs.** Their worked example: a resource allocator log of ~200MB and 500,000
  rows showed high-priority "defend region" tasks during an invasion; the task generator log gave
  the reason ("defend recently captured territory"), which was correct logic with a value tuned
  too high. Their summary: CAT tells you *where*, the logs tell you *why*.
- **Nightly automated reports** — SQL over the database, emailed: factions alive at turn 50,
  average army sizes, recruitment counts, compared build to build.
- **Manual playtests**, weekly, whole team, for months. Toth's stated reason: autoruns cannot
  simulate a human player, and QA repeatedly hit AI behaviour that never appeared in any autorun.

**You have none of the first four.** No autotest harness, no replay tool, no central database, no
nightly build. What you have is the game's own log, `pcall`-guarded `out()` lines from your own
script, save-game reloads, and playthroughs.

Two things follow, and both are already house practice for other reasons:

- **A mod that changes AI behaviour must log what it did, every turn, in its own log category.**
  You cannot reconstruct it afterwards. The engine keeps no record of why an AI did anything, and
  the one place a scripted promotion is visible is a line you printed yourself.
- **A build-time assertion beats a comment.** CA's whole apparatus exists because AI misbehaviour
  is invisible until it is egregious. You cannot afford invisible. Where a rule matters — "the
  stance score must not read diplomacy" — assert it in the generator so a violation fails the
  build, not the campaign.

And the honest caveat, which belongs in any write-up that touches this subsystem: CA runs
thousands of AI-vs-AI games overnight and *still* shipped a defend-priority value tuned wrong.
Offline verification of an AI feature proves the code does what you wrote. It proves nothing about
whether what you wrote is good, and nothing at all about how it feels across 200 turns.

---

## 10. Corrections to earlier write-ups in this workspace

- **`cai_personalities` is 227 rows x 33 columns**, table version 6, measured today.
  `HANDOFF_20260913_EXCHANGE_AI_STANCE.md` §4 says "227 rows x 28 columns" — the row count is
  right, the column count is wrong.
- **"There is no 'AI, consider a trade' hook and there will not be one"** (same handoff, §4) is
  too strong. There is no hook to make the AI *initiate*, which is the load-bearing half and
  stands. But `cai_evaluate_quick_deal_action` will tell you whether it would *accept* — see §8.
- **"You cannot read AI intent"**, stated in conversation on 2026-09-12, is wrong as an absolute.
  `campaign_ai():funds_available_for_*_by_area` reads the AI's own budget allocation per domain,
  and the twelve stance accessors read the stance layer back. You cannot read a *plan*; you can
  read the standing allocation that shapes one (§5).

---

## Cross-references

- `docs/sessions/HANDOFF_20260912_CAMPAIGN_AI_SCRIPT_CONTEXTS.md` — the context layer in full: 177
  `cai_*` tables, the seven override subsystems measured, the 78-row strategic component table,
  the Hell-Forge landmine
- `docs/sessions/HANDOFF_20260913_EXCHANGE_AI_STANCE.md` — the first shipped stance-manager feature
  here, and the circularity trap caught during its design
- `docs/sessions/HANDOFF_20260913_AI_COALITION_SUPERVISOR_BUILT.md` — the Coalition Supervisor:
  threat score, past event and `force_alliance` gated on §8's call. Merged into the Director and
  deleted on 2026-11-14 (`docs/superpowers/specs/2026-11-14-director-merges-coalitions-design.md`)
- `docs/superpowers/specs/2026-09-16-ai-director-design.md`, then
  `docs/sessions/HANDOFF_20260916_COALITION_SOAK_AND_AI_DIRECTOR_RESEARCH.md` and
  `HANDOFF_20260925_DIRECTOR_9_0_NAGASH.md` — the Director (`tools/build_director.py`), the second
  stance-manager user
- `docs/sessions/HANDOFF_20260829_CONCLAVE_AI.md` — a full diagnosis that ends at a personality row
- `docs/sessions/HANDOFF_20260911_LL_AI_STRENGTH_FLOOR.md` — faction strength is not a DB column
- `docs/ZHARR_EXCHANGE.md` — an economy built on the assumption in §8
- `Modding Files/reference/ca_script_docs_wh3/campaign/episodic_scripting.html` — the AI section
- `tools/check_lua_api.py --explain <member>` — the doc entry for any call named here
