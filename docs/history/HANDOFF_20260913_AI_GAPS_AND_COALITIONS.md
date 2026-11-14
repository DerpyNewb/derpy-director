# HANDOFF 2026-09-13 — the campaign AI doc's four open gaps closed, and the Coalition Supervisor design

Two halves. The first is measurement: every gap `docs/CAMPAIGN_AI.md` declared open on the
morning of 2026-09-13 is now closed or proven to be a dead end, and eight blocks of that doc were
rewritten from measured data. The second is a design, approved in chat, **nothing built**.

**Nothing was packed, deployed or played this session.** The only files changed are
`docs/CAMPAIGN_AI.md` and this handoff.

---

## 1. What changed on disk

- `docs/CAMPAIGN_AI.md` — eight blocks rewritten (§4 twice, §5, §6/§7.1, §7.2, §8, the sources
  table). Row counts and vocabularies are measured, not inferred, and every grep claim names the
  corpus so it can be re-run.
- Newly cached in `.skilltree_cache/` via `tools/fetch_vanilla_tables.py` (RPFM was open):
  `cai_personality_diplomatic_events` (104), `campaign_map_settlements` (830), `region_groups`
  (621), `faction_strategic_threat_levels` (5), `diplomatic_actions` (34).
  `region_group_members` returned **0 rows and its cache file was deleted** — see §3.

## 2. What was verified, and how

Two corpora, both usable with the game shut:

1. **CA's own shipped Lua**, 831 `.lua` files, staged decompressed at
   `Modding Files/reference/ca_scripts_wh3/`. A zero-hit grep here is real evidence about what CA
   never does. (Reached independently this session by decompressing `data_script.pack` with
   `tools/read_pack_index.py` + zstd, 833 files, before noticing the staged copy existed. Same
   corpus; use the staged folder.)
2. **The vanilla DB** through `tools/read_vanilla_cache.py`, with the five tables above fetched.

| Claim | How | Result |
|---|---|---|
| `cai_disable_targeting_against_settlement` key shape | `campaign_map_settlements` + 8 CA usages | **`settlement:<region_key>`**, built by concatenation in CA's own code. The doc's "from `campaign_map_settlements`" and the handoff's `"settlement:"..region_key` were always the same string |
| CA's use of the stance manager | grep, both corpora | **0 files.** All seven calls, never used by CA |
| CA's use of `strategic_stance_between_factions` (and the whole read interface) | grep | **0 files.** The numeric stance mapping cannot be recovered from vanilla |
| CA's use of the POI marker API | grep | **0 real hits** (the one match is that folder's own README) |
| `cai_evaluate_quick_deal_action` returns two values | 6 CA call sites | Confirmed: `local score, can_issue = ...`. CA's `Returns: nil` is wrong |
| `cai_add_diplomatic_event` vocabulary | `cai_personality_diplomatic_events` | 104 rows; only 6 script-facing generics; 79 of 104 transitive |
| What `set_base_strategic_threat_score` actually does | `faction_strategic_threat_levels` -> `effect_bundles_to_effects_junctions` | Threat levels 0/100/200/350/500 each carry `wh_main_bundle_faction_imperium_level_N`, whose only effect is `wh_main_effect_faction_imperium_diplomacy_penalty` at **-5/-10/-20/-30** |
| The zero-DB escalation's real payload | diffed each profile's base component against its `special_1` component | **~6%.** See §3 |
| `diplomatic_option_defensive_alliance` exists | `diplomatic_actions` | Present. 34 rows; both defensive and military alliance keys exist |

## 3. Corrections found the hard way

- **The no-DB context flip is worth almost nothing, and this nearly became a shipped design.**
  Vanilla wires global `special_1` to an escalated component for **17 of 21** strategic profiles
  (51 rows in `cai_personality_strategic_profile_context_overrides`, priority 1 = very_hard,
  2 = legendary, 3 = `special_1`). Flipping it from Lua needs **zero DB edits** — and the entire
  delta, measured per profile against that profile's base component, is
  `enemy_threat_strength_modifier` 0.85 -> 0.80, sometimes `enemy_strength_modifier` 0.85 -> 0.80
  and `unknown_faction_multiplier` 0.0 -> -0.1. CA's whole "AI extra aggro" campaign option is a
  ~6% change in how strong the AI thinks its enemies are. A design was chosen on the assumption
  that this route carried the payload; the measurement reversed the decision.
- **`fetch_vanilla_tables.py` writes a cache file even when the table does not exist**, so a
  wrong name poisons the cache with a 0-row file that `read_vanilla_cache.load()` will later serve
  as if it were the truth. `region_group_members` is not a real table; its file was deleted by
  hand. **Check the printed row count and delete any 0-row output.**
- **`cai_personality_strategic_components` is 78 rows x 36 columns**, not 37 as
  `HANDOFF_20260912` §6 says.
- **`cai_context_types` has six rows, not five.** The sixth is `cai_difficulty_context`
  (easy/normal/hard/very_hard/legendary) — campaign difficulty entering the same override
  machinery the script contexts use, which is CA's "difficulty is one multiplier" claim visible
  in the DB.
- **A staged reference folder existed for the work being redone.** `Modding Files/reference/ca_scripts_wh3/`
  already held CA's decompressed Lua; it was re-extracted from `data_script.pack` first. Check
  `Modding Files/reference/` before writing an extractor.

## 4. Do not re-derive

- **The context strings are the full DB keys, and the default is spelled inconsistently.**
  `cai_global_script_context_alpha`, `cai_faction_script_context_beta` — but
  `cai_faction_script_context_type_default`, carrying a `_type` the other eight lack. `ALPHA` or
  `cai_faction_script_context_default` does nothing, forever.
- **`set_base_strategic_threat_score` is not a hidden AI-only number.** It maps onto
  `faction_strategic_threat_levels` (0/100/200/350/500) and each level above 0 applies
  `wh_main_bundle_faction_imperium_level_N`, i.e. **-5/-10/-20/-30 diplomatic attitude with
  everyone**. It is vanilla's Imperium mechanic, it is reversible by setting 0, and its effect is
  visible on the diplomacy screen — which makes it the one AI lever here that is diagnosable
  without a log.
- **`cai_add_diplomatic_event` has no strength argument.** Magnitude lives in the row's
  `diplomatic_factor_group_active`. Of the 104 rows only six are script-facing generics —
  `PAST_EVENT_{POSITIVE,NEGATIVE}_{MINOR,MODERATE,MAJOR}`, all on `diplomatic_factor_past_events`,
  all non-transitive, all with `strategic_threat_multiplier_mod` 0. The other 98 are
  engine-raised, and **79 of 104 are transitive** (they propagate to third parties). CA's three
  uses all pass a generic and all three carry the comment `-- CHANGE THIS TO A NEW EVENT`, which
  is CA saying a mod's own reason should be a new row.
- **Steering AI targeting is a DB feature, not the POI API.** `region_groups` is 621 rows, 61 of
  them `cai_`-prefixed (`cai_region_hint_area_*`, plus a `cai_chaos_region_hint_*` set). They
  bind through the personality's `region_group_profile` — 99 distinct values, the second most
  varied column in `cai_personalities`. Scripts read the same groups with
  `region:is_contained_in_region_group(...)`. The POI marker call is used zero times by CA and its
  two integer parameters are documented nowhere.
- **Hecleas' AI Overhaul rewrites all 78 rows of `cai_personality_strategic_components`** (staged
  at `Modding Files/source/hecleas_ai_overhaul_2905096541/`, table version 17, 36 columns):
  `enemy_strength_modifier` flattened to 1.5 on every row, `sally_out_chance` to 50,
  `last_settlement_modifier` 25 -> 1, `fortified_settlement_assault_strength_modifier` 0.9 -> 1.0
  on 68 rows. It does **not** touch the four `call_to_arms_chance_*` or either
  `war_coordination_assist_attack_*_max_distance`. So those columns are unclaimed by the most
  common overhaul — and any always-on mod edit to that table collides with every AI overhaul,
  last pack loaded winning the whole row.
- **No AI overhaul is enabled in this install** (113 mods in `used_mods.txt`, none of them one).

## 5. The design that was approved (NOTHING BUILT)

**Coalition Supervisor** — `derpy_ai_coalitions.pack`, one Lua file in `script/campaign/mod/`,
**zero DB rows**, so it composes with every other mod except over one global context slot.

Chosen as option **C of three**: ship the script-only layer now; buy the DB layer (the
call-to-arms and war-coordination numbers, which no script call can reach) only if a soak shows
blocs forming while allied armies still fight alone.

- **Measure**, on `WorldStartRound`: region count per living faction, player included; leader and
  runner-up; `ratio = leader / runner_up`. Enter at `ratio >= 1.75` and `leader >= 10` regions,
  leave below `1.35`. The gap is hysteresis against flapping.
- **Response 1, the load-bearing one:** `cm:set_base_strategic_threat_score(leader, N)` with
  N = 200 / 350 / 500 at ratio 1.75 / 2.5 / 4.0, so the runaway takes -10 / -20 / -30 attitude
  with the whole world. 0 on exit.
- **Response 2:** 8 pairs per turn, deterministic rotation over **sorted** faction keys; for pairs
  that have met each other and met the leader, `cai_evaluate_quick_deal_action(a, b,
  "diplomatic_option_defensive_alliance")` **in both directions**, and only if both scores > 0,
  `cm:force_alliance(a:name(), b:name(), false)`. Defensive, because a defensive ally joins when
  its partner is attacked. Cap 2 forced alliances per faction per campaign.
- **Response 3:** flip global `special_1` only when `cai_get_global_script_context()` shows the
  slot unclaimed, and clear only what we set (~6%, five lines, the only collision surface); plus
  one `PAST_EVENT_NEGATIVE_MINOR` per polled faction while the state holds, **logged with its
  argument order** so the first soak settles CA's ambiguous `(from, to)` direction.
- **Persistence:** `cm:save_named_value` for rung, context ownership and per-faction alliance
  counts, re-applied in the loading callback — both threat score and context are engine state.
- **Off switch:** one constant; the off path makes zero calls, not calls-that-clear.
- **Check:** `tools/build_ai_coalitions.py --selftest` runs the shipped Lua under Lua 5.1.5
  against a stubbed `cm` and world (the `gen_victory_routes.py` pattern), asserting the rung
  mapping and hysteresis in both directions, the both-scores gate, deterministic pair order across
  two runs, the alliance cap, zero calls when disabled, and that an occupied context slot is left
  alone. No flag packs it.
- **Deliberately out of v1:** forced wars, personality swaps, stance-manager promotions (its clear
  is not mod-scoped), MCT UI, and the DB layer.

## 6. Still open

1. **Nothing is built.** The next artefacts are the spec at
   `docs/superpowers/specs/2026-09-13-ai-coalition-supervisor-design.md` and its implementation
   plan.
2. **The `(from, to)` argument order of `cai_add_diplomatic_event` is unsettled.** CA's own three
   uses are ambiguous about which faction ends up resenting which. Response 3 logs it rather than
   assuming it.
3. **The numeric stance mapping for the read interface is unobtainable offline** — zero vanilla
   usages. Only an in-game probe at a known scripted stance will give it.
4. **`HANDOFF_20260912` §8.1 is still unanswered** and now only matters if the DB layer is built:
   does a mid-campaign context change re-resolve the strategic component, or is it cached at
   faction creation? Response 3 does not depend on it (a 6% delta either way).
5. **The thresholds are guesses.** 1.75 / 2.5 / 4.0, 10 regions, 8 pairs, cap 2 — none measured.
   `docs/CAMPAIGN_AI.md` §9 is the standing warning: CA ran thousands of overnight AI-vs-AI games
   and still shipped a defend-priority tuned wrong, and this workspace has no autorun harness at
   all. A per-turn logger driven over the `wh3-mcp` bridge is the cheap version and was offered,
   not built.
