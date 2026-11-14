# HANDOFF 2026-09-16 — the Coalition Supervisor's first soak, two patches, and the AI write surface re-surveyed for a Director mod

Two halves. The first is done and deployed. The second is research and one approved design section,
with nothing built.

## 1. Deployed: two patches to `derpy_ai_coalitions`

**The detail lives in `HANDOFF_20260913_AI_COALITION_SUPERVISOR_BUILT.md` §6-§9, appended this
session. Do not duplicate it here.** In brief: 44 sessions of logs read, **zero errors across 85
supervised turns**; the threat score and past event both work as designed; **layer 2 has never
fired — about 50 asks, every result at or below zero**; max ratio ever seen is 2.00, so tiers 2 and
3 are untested in game.

Patched: the ask line now logs `ok=%s/%s` as well as the scores, and `poll()` filters pairs to
factions that have **met each other** before the cursor sees them. Rebuilt to 13,866 B, deployed
17:21, byte-verified by reading the Lua back **out of the deployed pack**.

The verification that matters: both new assertions were run against the **pre-patch Lua extracted
from the deployed pack** and both failed first — 6b with "the one askable pair was never reached",
which is the live log's behaviour reproduced in the harness.

## 2. Corrections found the hard way

- **A recommendation of mine was wrong and was withdrawn before it shipped.** I proposed patching
  `claim_context`'s "already held by ..., skipping" branch to adopt the slot. Reading A10 in the
  2026-09-13 handoff killed it: **CA's own "AI extra aggro" campaign option writes
  `cai_global_script_context_special_1` too**, so adopting would mean clearing CA's setting on tier
  exit. The slot cannot tell you who wrote it. Skipping is the safe side of an ambiguity with no
  resolution available. The branch is reachable because **the context slot is process-global, not
  save-scoped** — a fresh campaign inherits the previous campaign's value (seen once,
  `script_log_150926_1314.txt:8792`).
- **`WAR_COORDINATION_SCRIPT_INTERFACE` does not do what `episodic_scripting.html` says.** The doc
  for `cm:war_coordination()` claims it is the interface "by which war co-ordination requests can
  be made". The interface definition in `scripting_doc.html` exposes **three methods and none of
  them make a request**: `is_null_interface`, `get_faction_favour_points_toward_faction`,
  `set_faction_favour_points_toward_faction`. It is described there as a "Favour Points Script
  Interface". Read the interface block, not the getter's prose.
- **`diplomatic_action_subculture_restrictions` is NOT why alliances get refused.** It is 26 rows
  with exactly two boolean columns, `can_make_confederations` and `can_make_vassals`. It says
  nothing about defensive alliances, trade, or anything else. The zero-alliance mystery still
  belongs to the `ok=` logging.
- **`force_diplomacy` and `cai_evaluate_quick_deal_action` use different vocabularies for the same
  concepts.** The evaluate call takes `diplomatic_actions` keys (`diplomatic_option_join_war`).
  `force_diplomacy` takes **space-separated plain names**: CA passes `"all"` (104 times), `"war"`
  (35), `"form confederation"` (23), `"peace"` (11), and once each `"join war"` and
  `"defensive alliance"`. Passing one where the other belongs is an unvalidated string, so it fails
  silently forever.
- **Dwarfs toward Dwarfs is `+0`, not positive** — see §3. Kin are neutral in CA's data. Any design
  premised on "his kinsmen come to help him" has no data behind it; the grudge against the attacker
  does.
- **`read_pack_index.paths()` over `glob("data*.pack")` returned 0 db tables.** The DB is in
  `db.pack`, which that glob does not match. Name `db.pack` explicitly; it holds **1,521 tables**.
- **`.skilltree_cache/cai_personality_deals.json` was poisoned** (`VecRFile` length 0, the
  documented `fetch_vanilla_tables.py` failure mode). Deleted this session. `read_vanilla_cache.load`
  raises `IndexError: list index out of range` on a poisoned file, which is not an obvious symptom —
  check `len(blob["VecRFile"])` before blaming the loader.

## 3. Do not re-derive: the measured AI numbers

All read from `.skilltree_cache` via `read_vanilla_cache`, this session.

**`cai_personality_strategic_components`, 78 rows by 36 columns — the coordination half:**

| Column | Distinct values across all 78 |
|---|---|
| `war_coordination_assist_attack_force_max_distance` | **3.0, one distinct value** |
| `war_coordination_assist_attack_settlement_max_distance` | **3.0, one distinct value** |
| `call_to_arms_chance_defensive_war_with_ai_only` | 1.0 (72) / 0.0 (6) |
| `call_to_arms_chance_defensive_war_with_human_players` | 1.0 (72) / 0.0 (6) |
| `call_to_arms_chance_offensive_war_with_ai_only` | 0.5 (72) / 0.0 (6) |
| `call_to_arms_chance_offensive_war_with_human_players` | **0.1** (72) / 0.0 (6) |
| `sally_out_chance` | 5.0 (46) / 10.0 (28) / 20.0 (4) |
| `dead_zone` | 15.0, one distinct value |

**The six zero rows are all `wh3_strategic_component_prologue*`.** So in any real campaign these are
**global constants** — CA does not vary AI coordination by personality at all. "My allies never join
my offensive wars" is a literal 10% roll, and an ally will only divert to assist within 3 of the
target. No script call reaches any of these columns; they are DB-only, and buying them ends the
mod's zero-DB compatibility story. Hecleas' AI Overhaul rewrites all 78 rows of that table but
leaves these columns alone.

**`campaign_cultural_relations` — 675 rows, and this IS the lore layer.** Columns: `source` and
`target` (both subculture keys), `attitude_base`, `negative_attitude_multiplier`,
`positive_attitude_multiplier`, `campaign` (empty on every dwarf row, so global). 26 targets per
source. The Dwarf row set, which is lore-exact:

| Dwarfs toward | base | neg | pos |
|---|---|---|---|
| **Chaos Dwarfs** | **-100** | **x2.00** | **x0.10** |
| Daemons and the four gods | -100 | x2.00 | x0.10 |
| Skaven, Greenskins, Savage Orcs, Chaos, Beastmen | -100 | x1.50 | x0.50 |
| Vampire Coast, Dark Elves, Wood Elves, Norsca, Vampire Counts | -40 | x1.25 | x0.75 |
| Tomb Kings | -20 | x1.00 | x1.00 |
| High Elves, Lizardmen, Bretonnia | -10 | x1.00 | x1.00 |
| Cathay, Kislev, Ogres, **Dwarfs**, Empire, Tilea/Estalia | **0** | x1.00 | x1.00 |

Read it at load instead of hand-typing a lore table; a typed one is wrong the next time CA adds a
race. A Chaos Dwarf faction attacking a hold is the most provoking thing in the dwarf matrix, and
`pos x0.10` means goodwill bought afterwards is worth a tenth.

**Other counts:** `diplomatic_actions` 34 rows in 4 categories (alliance 9, break_alliance 15,
default 7, trade 3). `cai_personality_diplomatic_events` 104 rows, 79 transitive. `events.lua`
declares **379 scriptable events**. `cai_contexts_for_context_types` 36 rows across 6 context types.
`diplomatic_action_subculture_restrictions` 26 rows, `_faction_restrictions` 4.

## 4. Do not re-derive: the reachable write surface

- **`cm:force_*` is 25 calls.** The ones that execute a diplomatic outcome outright:
  `force_declare_war`, `force_alliance`, `force_make_peace`, `force_make_trade_agreement`,
  `force_grant_military_access`, `force_make_vassal`, `force_confederation`,
  `force_rebellion_in_region`, `force_rebellion_with_faction`, `force_diplomacy_new`.
- **`cm:force_declare_war(a, b, invite_a_allies, invite_b_allies)` — the two booleans ARE the
  call-to-arms path exposed to script.** CA calls it **91 times** and passes `true, true` in about
  14 of them (blood voyage, Wulfhart). Their own lib signature takes an **undocumented fifth
  argument, `suppress_war_messages`**.
- **`war_coordination_target(faction, REGION|MILITARY_FORCE, offensive) -> bool`** is on
  `CAMPAIGN_PAYLOAD_BUILDER_SCRIPT_INTERFACE`, not on `cm:`. It is the only "point this AI's war
  effort there" lever, and reaching it costs a mission or payload and therefore DB rows.
- **Favour points are read and write between any two factions** via `cm:war_coordination()`. Floats,
  **no documented scale, no bounds, no default** — the same trap as the stance manager's `_level`.
- **`WarCoordinationRequestIssued` is a real event** carrying `context:faction()`. CA listens for it
  in `wh3_narrative_shared_chains.lua` and `wh3_narrative_chaos_warriors.lua` as a mission trigger,
  guarded with `cm:get_saved_value(faction_key .. "_war_coordination_request_issued")`. Also
  present: `SharedDiplomacyWarCoordinationRequestIssued`, `FactionLeaderDeclaresWar`,
  `FactionLeaderSignsPeaceTreaty`, `CharacterSackedSettlement`, `CharacterRazedSettlement`,
  `FactionJoinsConfederation`, `PendingBankruptcy`, `LandTradeRouteRaided`,
  `DiplomaticOfferRejected`, `PositiveDiplomaticEvent`, `NegativeDiplomaticEvent`,
  `FactionCapturesWorldCapital`.
- **Faction script contexts are per-faction and have their own 9-value vocabulary**
  (`cai_faction_script_context_{type_default, alpha, beta, gamma, delta, epsilon, zeta, special_1,
  special_2}`). **They are not the contended single global slot.** The Coalition Supervisor fights
  over the one global slot when the same nudge could go onto named factions with no contention at
  all. That is an available improvement to the shipped mod, not only to the Director.

## 5. The Director design, as far as it got

The user wants `derpy_ai_coalitions` evolved into a reactive Director / Game Master: player actions
generate scenarios procedurally, across **all diplomatic and economic happenings, friendly and
destructive** — not war alone. Two decisions taken, both by explicit choice:

1. **Fidelity: "direct the armies too."** Nudge and force the politics, *plus* `war_coordination_target`
   payloads and spawned relief forces. This buys DB rows and ends the zero-DB compatibility story.
2. **Triggers: all four** — aggression against a kin group, runaway dominance (the existing mod,
   demoted to one scenario among many), weakness and opportunism, and treachery.

Shape approved: **a Director core plus a scenario library.** The core owns the event bus, cast
selection, the per-turn budget, state, the off switch, logging, and six **beat primitives** —
`ask` / `force` / `mood` / `target` / `muster` / `tell` — which are the only ways a scenario may
touch the world, so every documented trap is handled and tested once rather than once per scenario.
Scenarios are data rows: trigger, condition, cast, beats.

**Section 1 approved:** triggers register only the listeners scenarios ask for; a fired trigger
produces a *situation* (instigator, victim, region, kind); **cast selection scores on hatred of the
instigator rather than affinity with the victim**, because Dwarfs-toward-Dwarfs is 0 and there is no
kin affinity in the data to lean on. Three scoring terms, all readable: cultural hatred of the
instigator (`campaign_cultural_relations`), proximity (region adjacency, and beyond 3 hops the
engine will not assist regardless of intent), and self-priority, expressed as a scoring term rather
than a special case.

Also requested and not yet designed: **a news event panel** for interesting world events, and
flavour and lore accuracy throughout.

## 5b. Director Phase 1 — BUILT and packed, 2026-09-16

The spec is `docs/superpowers/specs/2026-09-16-ai-director-design.md` (18 sections) and the plan is
`docs/superpowers/plans/2026-09-16-ai-director-phase1.md` (11 tasks). Both complete.

Shipped: `derpy_director.lua` (the core plus one scenario, hand-written),
`derpy_director_lore.lua` (**generated**, 35 KB, CA's 675-row matrix as a Lua literal),
`tools/build_director.py` (harness, 9 assertion groups, lore generator, `--check`, `pack()`) and
`tools/mutate_director.py` (13 mutants). `Modding Files/Modpacks/derpy_director.pack`, 48,921 B,
**zero DB rows**. Not deployed, not played.

**The spec correction that mattered, made before any code: campaign Lua cannot read a DB table.**
No `cm:` accessor exists and a grep of all 5,778 CA scripts for `campaign_cultural_relations`
returns zero hits, so §4's "read once at load" was not implementable. The matrix is baked at build
time instead, and `check()` re-reads the cache — a stale bake or a CA patch that changes the values
is now a failing check rather than silently wrong casting.

**Two data findings that changed fixtures, both read off the table rather than assumed:**

- **Greenskins are NOT neutral toward Chaos Dwarfs** (-100, like nearly everyone — they are the
  mine slaves). The only subcultures neutral toward Chaos Dwarfs are the Chaos-aligned ones:
  Daemons, the four gods, Norsca, Chaos. A fixture that used Greenskins as the "does not care"
  control failed.
- **Ten subcultures have a NEGATIVE self-attitude** — Chaos Dwarfs worst at **-15**, then Skaven,
  Dark Elves, Vampire Counts, Vampire Coast, Ogres, Beastmen, Norsca, Chaos, Savage Orcs all at
  -10. So the "instigator never casts itself" guard is genuinely load-bearing, and a fixture that
  leaves the instigator out of reach cannot test it.

**The defect found at DEPLOY time, after every check was green: `beat_tell` could not legally
draw.** `cm:show_message_event`'s title and detail arguments must be full `[table]_[field]_[key]`
loc keys or a blank string, and its last argument indexes `event_feed_message_events` — **a
4,988-row table whose index 1 is a Tomb Kings agent-action failure**, with a `tmb/generic` icon, an
agent-targets-army layout and a negative sound. The code was passing invented keys
(`director_kin_avenge`) and index 1, so a dwarf grudge would have drawn a Tomb Kings popup with
unresolved text. Nothing caught it because the harness only asserted the index was non-zero.
**Phase 1 ships zero DB rows, so there is no correct key and no correct index to pass** — the beat
is now log-only, and assertion 12 asserts nothing draws. That assertion fails the day Phase 4 buys
the row and the loc, which is the point of it.

**The defect the LIVE GAME found, which no offline check could: the harness stub agreed with the
code instead of with the engine.** Deployed 19:18, played 21:01, and the log read:

```
[director] first tick, watching 1 event(s), budget 100
[director] dropped: situation_from errored: ...derpy_director.lua:265:
           attempt to call method 'instigator' (a nil value)          x9
```

`CharacterSackedSettlement` exposes **exactly two accessors, `character()` and
`garrison_residence()`**. There is no `context:instigator()` — I invented it when writing the stub,
the shipped Lua used the invention, and both halves of the test agreed with each other. Nine
assertion groups, fourteen mutants and three static checkers all passed on a scenario that could
never fire.

CA's own idiom, from `wh_grudges.lua` (**their Dwarf grudge script** — the exact precedent for this
scenario), `wh2_dlc15_grom_cauldron.lua` and three more:

```lua
context:character():faction()             -- who did it
context:garrison_residence():faction()    -- who it was done to   (41 CA uses)
context:garrison_residence():region()     -- where                (81 CA uses)
```

**The fix is in the harness, not only in the Lua.** The stub now models the documented event shape,
so any future scenario must use the real accessors or fail offline. A stub authored from
imagination cannot catch anything, and this is the one bug class the whole selftest approach is
blind to by construction. The `pcall` guard around `situation_from` worked exactly as designed:
caught it, named the line, and the campaign ran on.

**`mutate_director.py` found five assertion gaps that reading the code did not.** Four were missing
fixtures. The fifth is the one worth remembering: **the "past event fires once per situation"
assertion was passing for two wrong reasons at once** — at the shipping budget the past event is
priced out after turn 1, and the 12-turn per-faction cooldown empties the cast from turn 2 to 12,
so either mask alone made the assertion pass whether or not the guard existed. It needed a 20-turn
run with a preloaded budget before it tested anything. Both masks were found by mutation, not by
review.

## 6. Still open

1. **Director Phases 2 onward are unbuilt** — the campaign seed and the remaining three scenarios
   (Phase 2), the news panel (Phase 3), the `target` beat and its DB half (Phase 4), and the
   separate call-to-arms pack (Phase 5). See spec §18. **`muster` was deliberately cut from Phase
   1** although the plan's brief included it: it is the only remaining beat with no inverse and no
   Phase 1 scenario needs it.
2. **The one live question the shipped patch will answer:** with the poll budget now spent on
   askable pairs, does any pair ever come back positive/positive? If `ok=` returns false in bulk,
   `diplomatic_option_defensive_alliance` is the wrong lever and layer 2 should be withdrawn rather
   than tuned. **No turn has been played with either patch in.**
3. `cai_add_diplomatic_event`'s `(from, to)` direction is still unsettled. The mod logs its argument
   rather than assuming, and the log alone cannot settle it — it needs the diplomacy screen.
4. Every Coalition Supervisor threshold is still a guess, now with 2.00 as the highest ratio ever
   measured against a 2.5 second tier.

## 5c. Director Phase 1 — first live measurements, and the four fixes they bought (2026-09-17)

Four sessions of live logs, 26 situations across turns 65-68. `situation_from` is correct: 26
parses, four instigator cultures, zero errors. The casting is lore-plausible on every one.

**The measured failure.** 69 beats attempted, **61 starved**, and `force_alliance` — the beat the
mod exists to produce — **fired zero times**:

| | count |
|---|---|
| situations detected | 26 |
| mood fired | 6 |
| past_event fired | 2 |
| force fired | **0** |
| beats skipped for budget | 61 |
| empty casts | 3 |

**Root cause: the refill lived only in `first_tick`,** which raises once per campaign LOAD and not
once per turn, so the budget was a one-way drain. Session `script_log_170926_0746` is the pure
case — it opened on a carried-over 0, took its +5, spent it on one mood beat and skipped
everything for the rest of the session.

**Four fixes, each traceable to a line in those logs:**

1. **Per-turn refill.** `WorldStartRound` (round-scoped, 40 CA files use it), refill 60, ceiling
   180. Sized from the measured rate: turn 65 alone produced nine sacks.
2. **The coalition runs before the grudge.** `force` (15, reversible) now precedes `past_event`
   (40, no inverse) on the shared budget. The only mutually willing pair the mod has ever found —
   `cr_cth_sanyo_clan<->wh2_dlc13_emp_golden_order +1.25/+6.48` — was refused for 15 budget that
   two past events had already spent.
3. **The once-only guard keys on the feud, not the settlement.** Sayl vs Zhatan billed three
   times over four turns from three regions.
4. **An empty cast spends nothing,** not even the mood it was billed for three times.

**The ask lever is not dead — Phase 0's open question is answered.** 18 legal asks, 11 refused as
illegal, **1 mutually positive** and 3 one-sided. ~6% mutual. The Director found one in two turns
where the Coalition Supervisor found none in 85, because a cast of co-aggrieved factions is a far
better pair generator than a sorted cursor. `wh_main_brt_carcassonne<->wh_main_emp_empire
-3.62/+4.55` is the near-miss the mood beat is designed to close, and it was starved.

**Read `ok=false/false` as "redundant or illegal", NOT as "Chaos cannot ally".** The pairs are
Cathay/Cathay and High Elf/High Elf as often as Chaos ones, so an existing alliance is the more
likely cause. Unconfirmed — the return value does not distinguish the two.

**A second harness defect, same class as the invented `context:instigator()`.** `PRELOAD` was read
ahead of `SAVED` on every `get_saved_value`, so a preloaded key was frozen for the whole run: a
budget preloaded to 0 could never rise and one preloaded high could never be spent. Every
assertion resting on either passed without exercising the budget at all. A preload now seeds the
store once and is written over like any other value. **The harness event pump also never raised
`WorldStartRound`** and advanced a turn per event, so it could model neither the refill nor the
nine-sacks-in-one-turn contention; events now take an optional `turn`.

Selftest is 18 assertion groups, `mutate_director.py` is 18 mutants, 0 survivors. The feud-key
mutant survived its first run — the 12-turn cooldown emptied the later casts and held the count at
2 either way, the same mask that hid itself in assertion 11. The repeats are now spaced past it.

**Tuning measured, not guessed:** 12 situations on one turn fund 4 and starve 8; the same 12 one
per turn fund all 12 with 135 budget to spare.

**NOT deployed.** `Modding Files/Modpacks/derpy_director.pack` is built and verified, but the game
was running and holds the file open. Copy it into
`F:\SteamLibrary\...\Total War WARHAMMER III\data\` with the game shut.

## 5d. The event feed — BUILT and deployed, 2026-09-17

`beat_tell` was a log-only stub because phase 1 shipped zero DB rows. It now draws. **The pack is
no longer zero-DB** — it ships 5 tables and a loc, all under the fragment `derpy_director_feed`.

**Two records, both `scripted_transient_event`** (feed strip, expires, does not steal the screen —
the only sane choice for something that can fire nine times a turn):

| | index | image | icon | fires when |
|---|---|---|---|---|
| grudge | 7301 | `all/carnage_weapons` | `event_gen_news_negative.png` | past events fired AND the player is instigator or victim |
| pact | 7302 | `all/elector_confederation` | `event_gen_news_positive.png` | an alliance was actually forced, always |

Versions were read off **CA's own shipped tables** via the vanilla cache, not off RPFM's default
for the name: `campaign_groups` v0, `campaign_group_members` v1,
`campaign_group_member_criteria_values` v0, `event_feed_message_events` v1, `event_feed_strings`
v0. `event_feed_strings` has a **single `key` field** — the text is loc-only, at
`event_feed_strings_text_<key>`.

**The message can never name anything.** `show_message_event` takes loc KEYS, so every word has to
be true of every situation it can fire for. `show_message_event_located` is what carries the
specifics instead: `situation_from` now reads `region:settlement():logical_position_x/y()` while
the region interface is in hand, and the player clicks through to the sacked region. Those are
LOGICAL coordinates — the display coordinates a mission location takes are different numbers.

**Art was chosen by extracting the candidates and looking at them**, not by reading filenames.
Only `ui/eventpics/all/` (86 files) is culture-neutral; `all/chaos_stirs` and the `elector_*` set
were rejected or accepted on what they actually depict. `event_gen_news_*` is CA's own
general-news badge and one of the few of the 70 message icons carrying no race mark.

**`involves()` tests instigator and victim only, deliberately not cast membership** — `cast()`
filters humans, so the player can never be in one and a membership test would be dead code that
reads like a live guard.

`NEWS_ALL = false` in the Lua is the noise knob: true reports every grudge in the world rather
than only the player's.

Selftest is 18 groups (12 rewritten from "nothing may draw" to four separate silent-failure
checks: unaddressable world, located-not-plain, transient-not-persistent, index matches the row
that ships). `mutate_director.py` is 23 mutants, 0 survivors. `check_feed()` compares the Lua's
indices and loc keys against the rows in both directions, because nothing in the engine does: a
wrong index draws nothing and logs a line that reads like success, and a loc key with no row
behind it draws the raw key on screen.

Deployed and read back: 8 files in `data\derpy_director.pack`, all five tables present.

### 5d.1 Correction, same day: the involvement gate drew nothing

Gating the grudge message on "the player is instigator or victim" was measured over a full live
session (`script_log_170926_0949`, turns 70-71) and **drew zero messages** — three
`feed grudge withheld, player not involved` lines and nothing on screen. The player simply never
sacked anybody, which is the normal case.

A witnessed grudge is now reported too, rationed by `WORLD_NEWS_PER_TURN = 1`: the first one a
turn is told, the rest withheld. Player-involved grudges and all pacts still bypass the quota.
`NEWS_ALL = true` lifts it entirely.

The first version of that assertion **passed for the wrong reason** — the four burst situations
shared one responder, the 12-turn cooldown emptied the casts after the first past event, and only
one situation ever reached `beat_tell`. The fixture now gives each situation its own responder in
its own isolated region pair. This is the third time the cooldown has masked a count; assume it
does until the fixture rules it out.

Two more mutants (quota never refuses, quota is per campaign) bring `mutate_director.py` to 25,
0 survivors.

### 5d.2 The quota worked, and then the records were the wrong TYPE

`script_log_170926_1417` and `_1531`: **six** `feed grudge index=7301 to=wh3_dlc23_chd_conclave`
lines, one `withheld, world quota spent this turn`. The quota does exactly what it should — one
witnessed grudge a turn, refreshing.

**Nothing drew.** The records were `scripted_transient_event` and the call is
`cm:show_message_event_located`. `event_feed_targeted_events` declares **four** scripted types:

| type | located | vanilla rows |
|---|---|---|
| `scripted_persistent_event` | `event_feed_none` | 93 |
| `scripted_persistent_located_event` | `event_feed_location_position` | 40 |
| `scripted_transient_located_event` | `event_feed_location_position` | 21 |
| `scripted_transient_event` | `event_feed_none` | 4 |

The record type has to match the CALL. A plain record raised through the located call resolves,
logs `show_message_event_located() called, showing event for faction [...]`, and puts nothing in
the feed. `context_located` stays `event_feed_none` on all 21 located-transient rows — **the
location capability comes from `event`, not from that column**, which is why picking by
`context_located` finds nothing.

One-word fix; every other column was already right. The plain-call fallback is gone with it: a
located record raised through the plain call fails the same way, so a region with no settlement
now goes unreported rather than being sent to 0,0 (the map origin, not "nowhere").

**The whitelist line is a red herring.** `campaign_manager:show_message_event` calls
`whitelist_event_feed_event_type`; `show_message_event_located` does not, and CA's docs say it
does nothing at all unless `suppress_all_event_feed_messages` is active. The
`scripted_transient_event` whitelists in these logs are the **Zharr Exchange's**, not ours.

`check_feed()` now asserts the record type and the call agree in both directions. It was proven
to fail against the shipped-wrong configuration before being kept. 25 mutants, 0 survivors.

### 5d.3 It draws — and a blank secondary is an empty plate, not an omission

Confirmed on screen 2026-09-17: title, `all/carnage_weapons` art and body text all correct.

**`""` for the secondary detail draws an empty black box under the body.** The panel reserves the
plate whatever the script passes; it does not collapse the slot. All four vanilla scripted types
set `secondary_detail` in the DB and CA's scripts pass a real key, so there is no vanilla example
of the blank case to copy. Both records now ship a third string, and `check_feed()` parses the
actual arguments of the located call and refuses any that is blank — proven against the
shipped-blank version before being kept.

### 5d.4 Naming the culture: 60 records, one per subculture per message

"It seems too generic without involvement of the faction" - correct, and a **faction** name is
impossible. Every markup token vanilla uses in the 877 `event_feed_strings` entries resolves at
AUTHORING time: `{{tr:}}` (279), `[[url:]]` (282), `[[tooltip:]]` (276), `{{tt:}}` (276),
`[[img:]]` (99), `[[col:]]` (36), `[[sl:]]` (2). **There is no runtime substitution token at
all**, so no line can name the faction it is about.

A **culture** can be named, because `{{tr:cultures_subcultures_name_<subculture>}}` resolves the
real localised name and there are only 29 subcultures worth shipping. So the pack now carries one
record per (message kind, subculture): **60 records, 180 loc strings**.

The message speaks in the **lead responder's** voice - `cast[1]`, the faction that hates the
aggressor most - and wears that race's artwork. Art is `<race>/diplomacy` where it exists and
`<race>/faction` otherwise; all 24 race folders ship `faction`, and kho/nur/sla/tze have no
`diplomacy`. The race prefix is DERIVED from the subculture key (`..._sc_<race>_...`), never
typed, because a typed map went stale the moment the prologue subcultures appeared.

Each culture gets a bespoke title and a bespoke reaction line in the secondary slot - Dwarfs get
"A Grudge is Written" and a scribe of the Dammaz Kron, Chaos Dwarfs get "Entered in the Ledgers
of Zharr", Khorne gets "Blood Is Counted", Skaven get "Squeaked of in the Under-Empire".

**The generic pair is kept as the fallback** for a subculture nothing ships a record for - a
modded race or a rogue army. Without it an unknown culture resolves to no index and draws nothing,
which is the same silent failure this subsystem has produced three times already.

`derpy_director_feed_index` is GENERATED into `derpy_director_lore.lua` from the same table as the
DB rows, so the Lua and the DB cannot drift; the Lua builds the loc keys by concatenation and
`check_feed()` reconstructs the buildable key set and asserts it equals the shipped set exactly,
in both directions. 27 mutants, 0 survivors - the "voice is the LAST responder" mutant survived
its first run because both responders in the fixture were Dwarfs, so there is now a mixed-culture
cast with a deterministic lead.

## 6b. B, A and C — BUILT and deployed, 2026-09-17

### B. The stance manager replaces the global threat score

`set_base_strategic_threat_score` is **gone from the Director** (0 live calls; it survives only in
a comment explaining why). It was global and last-writer-wins, and `derpy_ai_coalitions` writes
the same value — neither mod could tell it had been overwritten. That collision is now closed.

`cm:cai_strategic_stance_manager_promote_specified_stance_towards_target_faction(a, b, stance)`
replaces it, one push per responder aimed AT the aggressor. Seven stances exist
(`BEST_FRIENDS` … `BITTER_ENEMIES`); the Director uses `VERY_UNFRIENDLY`. **promote**, not
`block_all_stances_but` — promote "makes it much more likely", block "sets" it, and this mod
leans on inputs rather than seizing the wheel. Per-pair so mods cannot collide, directional so
the holds turn on the aggressor and not on everyone, and reversible via
`clear_all_promotions_between_factions`, which is what the budget prices.

### A. Righteousness

`outrage(sit)` reads how much the AGGRESSOR's culture naturally hates the VICTIM's, out of the
lore matrix already baked into the pack. Measured bases: Chaos Dwarfs to Dwarfs **-100**, to
Cathay **-40**, Empire to Dwarfs **+0**, Greenskins to Dwarfs **-100**.

| verdict | multiplier |
|---|---|
| kinslaying (same subculture) | 1.5 |
| sworn enemies (base <= -75) | 0.25 |
| old enmity (<= -25) | 0.60 |
| (< 0) | 0.85 |
| unprovoked (>= 0) | 1.0 |

It does two things: **gates the permanent grudge** below `OUTRAGE_FLOOR` 0.5, and **sizes the
cast** (`CAST_TAKE * outrage`, clamped 1..3). Sworn enemies raiding each other draws one wary
neighbour and no grudge that cannot be undone; a kinslaying draws three and is remembered. The
reversible stance push always happens — a shrug is a smaller reaction, never no reaction.

**Live attitude is now read directly.** `f:diplomatic_attitude_towards(key)` — a **key string**,
which is what all five CA call sites pass — multiplies the cast score by 1.0..2.0. The matrix says
what a culture is disposed to feel; this says what the faction actually feels now.

### C. Three more scenarios

`WATCHED` is a scenario table of `{event, build, kind}`. Contexts read from CA's doc entries and
scripts, never guessed:

| event | context | kind |
|---|---|---|
| `CharacterSackedSettlement` | `character`, `garrison_residence` | sack |
| `CharacterRazedSettlement` | identical (plus `loot`, unused) | raze |
| `RegionFactionChangeEvent` | `region`, `previous_faction`, `reason` | conquest |
| `FactionJoinsConfederation` | `confederation`, `faction` | confederation |

A conquest reads the winner as `region():owning_faction()` and the loser as `previous_faction()`.
**`reason()` is checked** — a region that changed hands by confederation, gift, diplomacy or
script is dropped rather than dressed up as an atrocity. A confederation anchors reach on the
absorber's `home_region()`, because the absorbed faction owns nothing by the time it fires.

**`FactionLeaderDeclaresWar` is deliberately NOT watched.** Its context exposes `character` and
nothing else — the declarer but not who war was declared ON — and this whole model is
instigator-against-victim. There is no target to build a situation around. Use
`started_war_this_turn()` polling if it is ever wanted.

The harness builds **one context shape per event** and refuses to answer accessors the real event
lacks; a single permissive table is what let an invented `context:instigator()` pass every offline
check. 10 assertion groups, 35 mutants, 0 survivors.

## 6c. Noted, not built: D, E, F

**E and F were built on 2026-09-17 — see 6d.** The survey below is kept as written. **The budget and gate they run on were
corrected on 2026-09-18 - see 6e; three of the beats below had never once fired in play.**

**D. The news panel.** The ONLY way to ever name a faction on screen — a token census over every
text payload the game has (event feed 877, incidents 5,262, dilemmas 2,254, missions 9,558) finds
`{{tr:}}`, `{{tt:}}`, `[[col:]]`, `[[img:]]`, `[[url:]]`, `[[tooltip:]]`, `[[sl:]]`,
`[[fragment:]]` and **nothing that substitutes at runtime**. `set_scripted_mission_text` takes a
loc key like everything else. A custom `.twui.xml` writing real strings through `SetStateText` is
the only route. Half-built already: `news()` has been buffering the last 50 situations into the
save since 2026-09-16 and nothing reads it. See `docs/CUSTOM_UI.md`.

**E. Protection and relief.** `cm:cai_disable_targeting_against_settlement(settlement_key)` makes
the AI stop targeting a named settlement — a coalition that visibly shields somebody rather than
an abstraction. Plus `create_force_with_general` for spawned relief, `teleport_military_force_to`,
`force_attack_of_opportunity`, and `cai_disable_movement_for_faction/character`.

**F. Economic and disaster scenarios.** `treasury_mod`, `set_tax_rate`, `exempt_region_from_tax`,
`faction_add_pooled_resource`, `force_make_trade_agreement`; `spawn_plague_at_region/settlement/
military_force`, `create_storm_for_region`, `spawn_rogue_army`, `force_rebellion_in_region`.
The Zharr Exchange already models commodity supply, so a sacked town moving a price is a story
the Director could tell.

**Also reachable and unused:** `force_change_cai_faction_personality` (a faction's whole AI
temperament, swappable at runtime), `create_incident_builder` +
`launch_custom_incident_from_builder` (message-plus-payload with no player choice, so it avoids
the dilemma-choice-listener crash that bricks saves), and the full `force_*` diplomacy suite
(`declare_war`, `make_peace`, `make_vassal`, `grant_military_access`, `make_trade_agreement`).

## 6d. E and F — BUILT and deployed, 2026-09-17

D stays skipped by request. E and F are in the shipped pack; the constants, prices and call
conventions below are measured or read from CA's doc entries, not inferred.

### E. Protection — a coalition that visibly shields somebody

`cm:cai_disable_targeting_against_settlement` takes a **SETTLEMENT key**, out of
`campaign_map_settlements` — not a region key. `region:settlement():key()` is where one comes
from, and `sit.region` in its place is a key that fails silently forever. The call is **global**:
while it holds, no AI targets that settlement at all. That is a heavy thing to leave standing, so
it is held on a timer and released.

- `beat_shield(sit)` — price 10, fires once per formed pact, and **only if the victim still owns
  the region**. After a conquest the aggressor owns the place, and shielding it would hand the
  attacker a free garrison. Records `held[settlement_key] = turn + SHIELD_TURNS` (8) in the save.
- `release_shields()` — swept on `WorldStartRound` beside the budget refill, calling the
  documented inverse `cai_enable_targeting_against_settlement`. Iterates a **sorted key list**,
  not `pairs` order, so the log is reproducible across runs.

### F. Economy and disaster

| beat | call | convention trap | price | gate |
|---|---|---|---|---|
| `beat_warchest` | `cm:treasury_mod(key, amount)` | **"This value must be positive"** — it can only give. There is no scripted way to impose a cost. | 25 | both members of a formed pact, 2500 each |
| `beat_plague` | `cm:spawn_plague_at_region(region, plague_key)` | takes a region **INTERFACE** and a plague **KEY** — the two halves disagree | 35 | `kind == "raze"` only |
| `beat_unrest` | `cm:force_rebellion_in_region(region_key, units, x, y, suppress)` | takes a region **KEY**, and logical coordinates the situation already carries | 30 | `kind == "conquest"` only |

`PLAGUES` is five `wh3_main_nur_base_*` keys off the 20-row `plagues` table, rolled with
`cm:random_number(#PLAGUES, 1)` — **max first**.

Plague and unrest are irreversible once loose, so both sit behind `OUTRAGE_FLOOR` as well as the
budget: a sworn enemy doing what sworn enemies do gets a stance push and nothing more. The war
chest and the shield are reversible, so they only need the budget and a pact that actually formed.

### What the mutation suite bought here

**42 mutants, 0 survivors, 0 stale anchors.** Seven are new and each is a mistake that would have
shipped silently:

- the shield applied to a settlement the aggressor now owns
- the shield never lifted, and the shield lifted the same turn it is applied
- `sit.region` passed where `settlement:key()` is wanted
- only one member of a new coalition funded
- every sack breeding plague, not only a razing
- the consequences block ignoring the outrage floor

Two anchors went **stale** on their first run and both were real signals, not noise:
`if not (sit.x and sit.y) then` had become ambiguous the moment `beat_unrest` grew the same guard
(the feed mutant now anchors on the following `log("feed "` line), and the shield-expiry anchor
was written against `held[k]` when the assignment is `held[key]`. A stale anchor means the code a
mutant was aimed at has moved and nobody has checked whether the assertion aimed at it moved too.

### Verified in the deployed binary

`F:\...\data\derpy_director.pack`, 187,287 bytes, read back with `tools/read_pack_index.py`: 8
files, all five new functions present in the shipped Lua. 12 selftest groups pass, ending
`selftest: protection, economy and disaster ok`; `luac -p`, `check_lua_api.py` (0 suspect calls)
and `check_lua_undeclared.py` (0 findings) clean.

## 6e. The starvation pass - three fixes measured off live logs, 2026-09-18

Five live sessions after the E/F deploy said the code was correct and almost never ran.
Per session: 20 stance pushes, 4 past events, 1 rebellion, and **zero** shields, war chests
or plagues. About 50 of ~70 beats skipped for budget. The Director went silent at situation
8 of 25 and spent the rest of the turn logging `budget 0 cannot afford 5`.

Read the logs with `grep -o '\[director\].*'`; the raw `grep derpy_director` matches the
savegame's `saved_values` dump and returns 300KB of noise. The prefix is `[director]`.

### What the logs actually proved

| finding | evidence |
|---|---|
| the budget is first-come-first-served, not selective | 25-39 situations a turn against a 60/turn refill; the first 8 take everything |
| one war bills once per REGION | qb2 taking the Conclave produced **13 situations in one turn**, re-pushing the same three factions to a stance they already held |
| the pact gate had never opened | **151** real evaluations, best `min(sa, sb)` = **-1.12**. Never both positive |
| a starved feud was burnt forever | `seen_key` was set whichever way the spend went |

The pact gate is the one worth remembering. `cai_evaluate_quick_deal_action` is
**directional and the two directions disagree hard** - the same pair scored `-14.93` one way
and `+5.72` the other. `sa > 0 and sb > 0` asks for a deal neither side has any reservation
about, which is not a thing that happens. 31 of 151 pairs had one side positive; none had two.

### The three changes

1. **Per-turn feud dedup** (`first_of_feud_this_turn`). One situation per
   `(instigator, victim)` per turn. The situation is still LOGGED - only the beats are
   withheld - so a province falling still reads as a province falling. Keyed on the pair and
   deliberately not on the kind: a faction that sacks a town and then takes it is doing one
   thing, and it read as two.
2. **`sa + sb > 0`** in place of both-halves. One side keen enough to carry the other's doubts
   is a pact.
3. **One grudge in the world per turn** (`GRUDGES_PER_TURN`, `grudge_slot`), on `cast[1]`
   only. `BUDGET_START`'s comment had claimed this rationing since 2026-09-17 while the code
   fired one past event per cast member - three responders cost 120 of a 180 budget on the
   single beat with no inverse. And `seen_key` now moves inside the branch that fired.

**No budget constant changed.** 180/60 was already right; what was wrong was one beat
spending it three at a time.

### Measured, not guessed

The logs were replayed through the budget under each candidate rule before anything was
edited. Replaying the newest log, counting only situations that drew an audience:

| | heard | starved of the 5-cost push | force | warchest | shield | plague | unrest |
|---|---|---|---|---|---|---|---|
| shipped (both>0, per-responder) | 24 | **14** | 0 | 0 | 0 | 0 | 1 |
| +dedup +sum gate | 14 | 6 | 1 | 1 | 1 | 0 | 1 |
| **+one grudge a turn (shipped)** | 14 | **3** | 1 | 1 | 1 | **1** | **2** |
| +two grudges a turn | 14 | 5 | 1 | 1 | 1 | 1 | 1 |

Raising the refill instead does **not** work: at 90, 120 and 150 the extra money goes
straight to the grudge loop and plague still never fires. The quota is not redundant with
`cast[1]`-only either - without it, 6 of 14 starve and plague stays at zero.

Plague was never structurally broken. Razing is just rare: **3 distinct razes above the
outrage floor across all 26 logs**, all three with an audience, all three reaching the beat.
Two lost to a drained budget.

### Dead code the mutants found

With one grudge a turn there is never a second message for a feed quota to withhold, so
`world_news_slot`, `involves()`, `WORLD_NEWS_PER_TURN` and the `NEWS_ALL` toggle became
unreachable. **Three of their mutants survived, which is how the dead code announced
itself** - a surviving mutant is the suite reporting that nothing can reach the branch.
Removed rather than kept: an untestable guard is not a guard. Raising `GRUDGES_PER_TURN`
above one is what would bring the question back.

### Harness

Six selftest assertions had encoded the old rules and were rewritten, not deleted:

- the one-sided pair now **must** form a pact (+4 sum); a new `5/-9` case must not
- the grudge count per feud drops 2 -> 1, and must land on `cast[1]`
- the busy-turn fixture grew **12 -> 30 situations**, because the fix means twelve no longer
  goes broke. A fixture that stops measuring contention has to grow with the thing it measures
- the feed-quota assertion now asserts the line that actually fires
- two new fixtures: two feuds one turn -> one grudge, and the same two plus a third next turn
  -> two grudges. **Both are needed** - the quota and the permanent burn produce the same
  TOTAL, and only the turn it lands on tells them apart

Two traps worth keeping:

- **The harness refills twice before the first event** (`first_tick`, then `WorldStartRound`
  for turn 1), so the budget at the first event is never below 120 and `preload` cannot be
  used to starve a run. Exhaust it with spend inside the turn instead.
- `STATE_KEYS` is only the dump list, not the store. `SAVED` is a plain table, so new saved
  values persist across events with no harness change.

### Result

`py tools/mutate_director.py` -> **45 mutants, 0 survived, 0 stale anchors** (was 42/3/2 at
the moment of the change; the three survivors and both stale anchors were all real signals
from this work). Seven new mutants cover the three rules and both quota shapes.

12 selftest groups pass. `luac -p`, `check_lua_api.py`, `check_lua_undeclared.py` clean.
Deployed to `F:\...\data\derpy_director.pack`, **189,202 bytes, 2026-09-18 09:55**, read back
with `read_pack_index.py` and checked **with comments stripped** - a first pass matched the
word `NEWS_ALL` in the comment recording its own removal and reported a false failure.

Next live session should show `shield`, `warchest` and `plague` lines, far fewer
`cannot afford`, and `already answered this feud this turn` on a grinding war.

## 6f. The duplicate feed index, and a crash that cannot be attributed, 2026-09-18

### The feed index collision - real, fixed, gated

`FEED_BASE` is `{"grudge": 7300, "pact": 7400}` and `culture_records()` numbers from
`base + n` with `n` starting at **1**. The generic pair was hardcoded `7301`/`7302` from
before per-culture rows existed, so when the culture rows arrived on 2026-09-17 they walked
straight over it:

| index | rows sharing it |
|---|---|
| 7301 | `grudge` (generic) and `grudge_wh2_dlc09_sc_tmb_tomb_kings` |
| 7302 | `pact` (generic) and `grudge_wh2_dlc11_sc_cst_vampire_coast` |

The index is the `value` on a `campaign_group_member_criteria_values` row. The engine
resolves it to whichever member carries that value, so **one row of each pair was unreachable
and the other drew for both**. There is **no `bad_mods_report.txt` entry** - the DB loads
cleanly and the feed just shows the wrong card.

Fixed by putting the generic pair on the base of its own range: grudge `7300`, pact `7400`.
The per-culture rows are untouched at 7301-7329 and 7401-7429. Both copies moved - the DB
rows and the `FEED` table baked into the Lua.

**The gate:** `check_feed()` now asserts every index across `all_feed_rows()` is unique, and
it is called **inside `pack()`**, before the first `import_tsv`, so a repeat aborts the build
rather than shipping. `_selftest()` collides the generic grudge with the first culture grudge
and asserts `check_feed()` raises - a gate nobody has watched fail proves nothing, and this
one was written after the fault it catches had already shipped for a day.

Mutants: the pre-existing "the feed index drifts" mutant was re-pointed to `7300` (its anchor
went stale on the fix), and one added for the generic pact colliding with a culture grudge.
**46 mutants, 0 survived, 0 stale anchors.**

### The crash - what is known and what is not

`0xc0000005` reading `0xffffffffffffffff` at `Warhammer3.exe+0x15D3E7F`, 2026-09-18 10:13:36.

- **The fault address is new.** It appears in none of the 80 earlier dumps in
  `crash_report/`. Yesterday's five were all `+0x268CE1F`/`+0x268CE26`.
- **It is a worker thread.** 24 frames ending `KERNEL32` / `ntdll`, a thread entry point;
  yesterday's were 32 frames with no such tail. A different shape, not a recurrence.
- `0xffffffffffffffff` is a poison/uninitialised pointer, not a null deref.
- Timeline from `wh3_mcp_debug.log`: campaign detected 10:08:14, poll loop 10:09:05, last
  heartbeat 10:13:27 `in_campaign=true pending=false`, crash 10:13:36. About 4.5 minutes in.
  The session immediately before (09:32-09:38) ran the **old** pack and did not crash.
- `lua_mod_log.txt` shows `derpy_director.lua` **loaded successfully**. The ten
  `Failed to load mod` lines are the long-standing duplicate-basename issue under
  `cr_combi_expanded`, not new.
- No `bad_mods_report.txt`, so nothing was rejected at load.

**It cannot be attributed.** One crash, a symbol-stripped stack, and no script log.

### Why there is no script log - read this first next time

**`derpy_debug_script_log.pack` is the only pack in the whole 684-pack library that ships
`script/enable_console_logging`, and it is unticked.** It is absent from `used_mods.txt`
while sitting in `data/`. No script log has been written since 2026-09-17 23:11.

A missing `script_log_DDMMYY_HHMM.txt` is therefore **not** evidence that scripts failed -
it means that pack is off. Re-tick it in the mod manager before any diagnostic session.

### The new risk surface, stated plainly

The 6e fix opened the pact gate, which makes **three engine-mutating calls reachable that had
never once executed in a live campaign** across 151 evaluations: `cm:force_alliance`,
`cm:treasury_mod` and `cm:cai_disable_targeting_against_settlement`. That is the honest
candidate for a new crash and it is the reason to look here first - but all three check out:

- `cm:force_alliance(key, key, boolean)` takes **faction key strings**, per its doc entry and
  8 CA call sites (`wh3_campaign_subjugation`, `wh3_dlc25_gelt_dilemmas`, `wh3_boris` and
  more). Our call passes strings. `beat_force` already refuses `a == b`, carried over from
  the `force_confederation(X, X)` crash.
- `cm:treasury_mod` is give-only and we pass a positive 2500.
- `cai_disable_targeting_against_settlement` takes a settlement key, and `beat_shield`
  derives it as `region:settlement():key()` behind null guards.

### Next session

1. Re-tick `derpy_debug_script_log.pack`.
2. Play the same save. If it crashes again, the script log says how far the Director got and
   whether a pact formed first.
3. If it does, the cheapest bisect is `local ENABLED = false` at the top of
   `derpy_director.lua` - one line, and it silences every listener.
