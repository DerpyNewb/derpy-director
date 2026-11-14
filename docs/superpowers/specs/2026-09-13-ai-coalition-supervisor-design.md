# Coalition Supervisor — design

**Superseded 2026-11-14:** merged into the Director and deleted. The runaway step lives on in
`derpy_director.lua`; see `2026-11-14-director-merges-coalitions-design.md`.

**Date:** 2026-09-13
**Status:** approved in chat, not built
**Pack:** `derpy_ai_coalitions.pack` — one Lua file, **zero DB rows**
**Background:** `docs/CAMPAIGN_AI.md`, `docs/sessions/HANDOFF_20260913_AI_GAPS_AND_COALITIONS.md`

---

## 1. Purpose

Make the campaign AI *behave* smarter against a runaway faction without touching a DB table, so
the mod composes with every other mod including AI overhauls.

The campaign AI has no central brain to persuade (`CAMPAIGN_AI.md` §1), so this does not try to
give it one. It changes two inputs that existing AI departments already read, and it performs one
action the AI would accept but never proposes on its own:

1. A runaway leader's **strategic threat score**, which is the layer CA's own difficulty
   multiplier moves.
2. **Defensive alliances** among the factions that would already say yes — asked with
   `cai_evaluate_quick_deal_action` before anything is forced.

### Non-goals

- No DB rows. The `call_to_arms_chance_*` and `war_coordination_assist_attack_*_max_distance`
  columns are the real cooperation knobs and **no script call reaches them**; they are deferred
  to a possible second phase (§10).
- No forced wars, no personality swaps, no stance-manager calls (its
  `clear_all_promotions_between_factions` is not mod-scoped and stomps CA and other mods).
- No MCT UI in v1.
- Not an AI overhaul. It does nothing at all until a runaway exists.

## 2. Architecture

One file, `Modding Files/pack/script/campaign/mod/derpy_ai_coalitions.lua`, holding four units
with one job each. They are separable because each can be tested without the others.

| Unit | Job | Depends on |
|---|---|---|
| `measure()` | Read the world, return `{leader, leader_regions, runner_up_regions, ratio}` | model read calls only |
| `rung_for(ratio, leader_regions, current)` | Map ratio to a rung 0..3, applying `MIN_REGIONS` and hysteresis | pure function, no game calls |
| `respond(state)` | Apply threat score, poll and force alliances, own the context slot | write calls |
| `persist` | Save and restore rung, context ownership, alliance counts | `cm:save_named_value` / `load_named_value` |

`rung_for` being pure is deliberate: it is the part most likely to be wrong and the part a
stubbed test can pin exactly.

## 3. Data flow, one turn

```
WorldStartRound
  -> ENABLED false? return (zero calls)
  -> measure()            faction_list -> per-faction region_list count, skip dead/rebel/regionless
  -> rung_for(ratio)      hysteresis against the saved rung
  -> rung changed?        set_base_strategic_threat_score(leader, SCORE[rung])   -- 0 when rung 0
  -> rung > 0?            poll POLL_PAIRS pairs this turn, force those that both accept
  -> rung > 0?            claim global special_1 if unclaimed; release it if we own it and rung 0
  -> log one line per decision
```

## 4. Constants

All at the top of the file, named, no magic numbers inline.

| Constant | Value | Meaning |
|---|---|---|
| `ENABLED` | `true` | Master switch. `false` makes **zero** calls — not calls that clear |
| `MIN_REGIONS` | `10` | Below this the leader is not a runaway however lopsided the ratio |
| `RUNG_RATIOS` | `{1.75, 2.5, 4.0}` | rung 1 / 2 / 3 entry ratios. `RUNG_RATIOS[1]` **is** the entry threshold — there is deliberately no second constant for it |
| `EXIT_RATIO` | `1.35` | fall below this to leave the state. The gap to `RUNG_RATIOS[1]` is the hysteresis band |
| `RUNG_SCORES` | `{200, 350, 500}` | threat score per rung = threat level 2 / 3 / 4 = -10 / -20 / -30 attitude |
| `POLL_PAIRS` | `8` | pairs evaluated per turn, deterministic rotation |
| `MAX_FORCED_ALLIANCES` | `2` | per faction, per campaign, so no mega-bloc forms |
| `CLAIM_CONTEXT` | `true` | flip global `special_1` when the slot is free (worth ~6%) |
| `PAST_EVENT` | `"PAST_EVENT_NEGATIVE_MINOR"` | one per polled faction while the state holds |
| `LOG_PREFIX` | `"[coalitions]"` | own log category |

Float note: WH3 Lua is single-precision ([[wh3-lua-is-single-precision-float]]), so a ratio
comparison at exactly 1.75 may fall either way. Every threshold is a strict `>=` and no rung
boundary is ever also an exit boundary, so a one-bit wobble cannot flap a rung.

## 5. Call inventory, with receiver conventions

The conventions are inconsistent and unmarked in CA's docs, so they are pinned here. All verified
present on 2026-09-13 with `py tools/check_lua_api.py --explain <member>`.

| Call | Receiver / args |
|---|---|
| `cm:model():world():faction_list()` | model read |
| `faction:region_list():num_items()` | faction interface |
| `faction:is_dead()`, `faction:name()` | faction interface |
| `faction:factions_met()` | faction interface, returns a FACTION_LIST (iterate `model_pairs`) |
| `faction:defensive_allies_with(other)` | faction interface, **faction interface** argument |
| `cm:cai_evaluate_quick_deal_action(a, b, deal_type)` | **faction interfaces**, returns `score, can_issue` |
| `cm:force_alliance(a_key, b_key, is_military)` | **key strings**; `false` = defensive |
| `cm:set_base_strategic_threat_score(faction, score)` | **faction interface** |
| `cm:cai_add_diplomatic_event(from_key, to_key, action)` | **key strings** |
| `cm:cai_get_global_script_context()` / `_set_` / `_clear_` | **full DB key strings** |
| `cm:save_named_value(name, value, context)` / `load_named_value(name, default, context)` | saving/loading callback context |

Two keys that fail silently if wrong, both confirmed against the DB this session:
`diplomatic_option_defensive_alliance` (in `diplomatic_actions`, 34 rows) and
`cai_global_script_context_special_1` (in `cai_contexts_for_context_types`).

## 6. Measurement details

- Iterate `faction_list` once; skip a faction that `is_dead()`, answers `is_rebel()`, or owns zero
  regions. Count `region_list():num_items()`.
  (`is_rebel` is documented only on the battle army interface, but CA calls it on campaign faction
  interfaces in `wh3_dlc27_nor_generic.lua`, `wh_start.lua` and `campaign_tours.lua` — usage is the
  authority here, and a wrong member throws rather than failing silently, so the `pcall` catches it.)
- The **player is included**. A runaway player draws the same response; that is the feature.
- Leader is the largest count, runner-up the second largest. If there is no runner-up (one faction
  left) the state is rung 0.
- `ratio = leader_regions / runner_up_regions`.

**Why region count and not strength:** faction strength is not a DB column, and
`military_force_list` counts garrisons, so army-based measures overstate
([[wh3-military-force-list-counts-garrisons]]). Region count is cheap, stable across reloads, and
is what the player perceives as a runaway.

## 7. Coalition polling

- Candidate factions: alive, non-rebel, **not human**, at least 2 regions, have met the leader,
  and are not the leader.

  **Ruling A9, 2026-09-13, filling a gap this spec left.** The human player is excluded from
  candidacy. §6's "the player is included" governs who can be measured as the *leader*, not who
  gets force-allied, and the two are not the same question. `cai_evaluate_quick_deal_action` asks
  what the campaign AI would accept, and a human faction has no AI to ask — the score is
  meaningless rather than merely unknown. `cm:force_alliance` is also unrefusable, so conscripting
  the player into a defensive alliance they never agreed to would be a larger intrusion than
  anything else here, and nothing in this spec authorizes it. A runaway human still draws the
  threat score and still has coalitions formed *against* them, which is the feature.
- A **pair** additionally requires that the two have met each other — `b` must appear in
  `a:factions_met()` — and are not already `a:defensive_allies_with(b)`. Asking
  `cai_evaluate_quick_deal_action` about two factions that have never met is meaningless, which is
  why CA's own six call sites all iterate `faction:factions_met()` rather than the full faction
  list.
- Pairs are drawn from a **key-sorted** candidate list with a saved rotation cursor, `POLL_PAIRS`
  per turn. Sorted iteration, never raw `pairs()` — undefined order diverges across reloads and
  multiplayer clients.
- For each pair, evaluate **both directions** and require both scores `> 0` and both `can_issue`.
  A one-sided deal forced on an unwilling faction is dumber than doing nothing.
- On success: `cm:force_alliance(a, b, false)`, increment both factions' counters, log the pair
  and both scores.
- `MAX_FORCED_ALLIANCES` per faction caps the web.

## 8. Error handling

- The whole turn handler body runs inside `pcall`; a failure logs and returns, and the next turn
  retries from saved state. An erroring listener condition drops silently with no log line
  ([[wh3-listener-condition-fails-silently]]), so the condition stays trivial and all logic lives
  in the handler.
- Every faction interface is checked with `is_null_interface()` before use; a null interface has
  no other members ([[wh3-null-script-interface-has-only-is-null-interface]]).
- **No loc calls anywhere in the handler** — a loc lookup from a turn handler CTDs at turn 1 and
  `pcall` does not catch it ([[wh3-no-loc-calls-from-turn-handlers]]). Log faction **keys**, never
  display names.
- `cm:force_alliance` between two factions already allied is a no-op by the `defensive_allies_with`
  guard; the guard is the check, not an assumption about the call.

## 9. Persistence

`add_saving_game_callback` / `add_loading_game_callback` with these named values:

| Name | Type | Why it must survive |
|---|---|---|
| `derpy_coalitions_rung` | number | hysteresis needs the previous rung |
| `derpy_coalitions_owns_context` | boolean | so we clear only a slot we claimed |
| `derpy_coalitions_alliances` | table (key -> count) | the per-faction cap |
| `derpy_coalitions_cursor` | number | rotation position, so polling does not restart each load |
| `derpy_coalitions_scored_key` | string | **which faction carries the score** — a release must target the carrier even when it is no longer the leader (ruling A4/A6) |

On load, **re-apply** the threat score and the context if the rung is above 0: both are engine
state, not script state, and this is what CA's own Hell-Forge script does with its context.

## 10. Off switch semantics

`ENABLED = false` returns before any call **from the turn handler**. The saving and loading
callbacks stay registered regardless, and that is deliberate rather than an oversight (ruling
A14): if `load` were also gated off, a disabled mod would restore nothing, and its `save` would
then write default state over the record of the threat score and the context slot it is still
holding — destroying the very information the reset procedure below needs. The measured cost of
keeping them live is one log line per campaign load and no game call at all. It does **not** clear a previously set threat score or
context — a disabled mod that keeps writing is the trap `CAMPAIGN_AI.md` §4 warns about with
`clear_all_promotions_between_factions`.

**What that costs, stated plainly (ruling A13, 2026-09-13).** Disabling the mod mid-campaign
leaves two things behind in that save: the runaway's threat score, and — more importantly for
other mods — the global script context slot, if this mod held it. One global slot exists
game-wide, so a leaked claim blocks CA's own "AI extra aggro" option and any other mod that wants
it, for the life of that save. This is a deliberate trade: the alternative is a disabled mod that
still calls into the AI every turn to check whether it has cleaning up to do, which is the worse
of the two failures and the one the source doc warns about. To reset a save cleanly, run one turn
with `ENABLED = true`, `RUNG_SCORES` zeroed, `CLAIM_CONTEXT = false` **and `POLL_PAIRS = 0`**
(without the last one the reset turn still polls: it can force fresh alliances and fire past
events on its way out, adding the one effect that has no inverse) — the latter now
releases a held slot rather than leaking it (ruling A12) — and then disable.

`CLAIM_CONTEXT = false` is different from `ENABLED = false`: the mod is still running, so it can
and does release a slot it already holds, once, before going quiet. The flag gates the **claim**,
never the release.

## 11. Testing

`tools/build_ai_coalitions.py`:

- no flag: pack the file into `derpy_ai_coalitions.pack` through the RPFM MCP server.
- `--selftest`: run the **shipped** Lua under local Lua 5.1.5 against a stubbed `cm`, world and
  faction interfaces, recording every call. The `gen_victory_routes.py --selftest` pattern: the
  test runs the artefact, it does not re-implement it.

Assertions:

1. `rung_for` maps 1.0 / 1.8 / 2.6 / 4.5 to rungs 0 / 1 / 2 / 3.
2. Hysteresis both ways: at ratio 1.5 the rung **holds** if already in the state, and **stays 0**
   if not; below 1.35 it releases.
3. `MIN_REGIONS`: a 9-region leader at ratio 9.0 yields rung 0.
4. Both-scores gate: a pair scoring `(5, -1)` is never allied; `(1, 1)` is.
5. Determinism: two identical runs produce the identical ordered call list.
6. `MAX_FORCED_ALLIANCES`: a faction never exceeds 2 forced alliances across many turns.
7. `ENABLED = false` produces **no call from the turn handler**, and exactly one call in
    total: the loading callback's own log line (see §10 — the persistence callbacks stay
    registered on purpose).
8. An occupied context slot (stub returns `..._special_2`) is left alone and never cleared.
9. Threat score returns to 0 exactly once on release, not every turn afterwards.
10. No stubbed call is a loc lookup.

`py tools/check_lua_api.py` and `py tools/check_lua_undeclared.py` must pass, and
`luac -p` must exit 0, before packing.

## 12. Deferred: the DB layer, and what would buy it

Phase 2 exists only if a soak shows **blocs forming while allied armies still fight alone**. That
is the symptom the script layer cannot fix, because the numbers governing it are DB-only:
`call_to_arms_chance_offensive_war_with_human_players` (0.1 across all 72 live rows) and
`war_coordination_assist_attack_{force,settlement}_max_distance` (3.0 across all 72).

Building it means generated `cai_personality_strategic_profile_context_overrides` rows plus cloned
components, and it carries two known costs: it overwrites any AI overhaul's rows on the components
it clones, and it depends on the still-unanswered question of whether a mid-campaign context
change re-resolves the strategic component at all
(`HANDOFF_20260912_CAMPAIGN_AI_SCRIPT_CONTEXTS.md` §8.1).

## 13. Open risks

1. **The thresholds are guesses.** Nothing here is measured against a played campaign, and this
   workspace has no autorun harness (`CAMPAIGN_AI.md` §9). The per-turn log is the only instrument.
2. **`cai_add_diplomatic_event`'s `(from, to)` direction is unsettled** — CA's three uses are
   ambiguous. The log records the argument order used so the first soak settles it; if it is
   reversed the effect is the leader disliking the others, which is visible and harmless.
3. **The global context slot is shared.** If the player enabled CA's "AI extra aggro" campaign
   option, `special_1` is already set and our claim is skipped — correctly, since the escalation is
   then already on.
4. **Forced alliances are unrefusable.** Even gated on both scores, the web changes the world.
   The cap and the poll throttle are the containment; a soak may show 2 is still too many.
