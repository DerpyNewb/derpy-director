# The Director Grows Empires Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each campaign the Director grows three AI empires (a great power toward 50 settlements on Immortal Empires, two lesser toward 25) on a schedule, with natural levers by default and an optional cheat preset.

**Architecture:** A new EMPIRES section in the one model file, `derpy_director.lua`, driven from the existing `WorldStartRound` listener and reusing the seed's ambitious list, `within_reach`, `beat_stance`, `beat_ask`, `merge` and `merge_blocked`. Two existing functions gain gates: `measure()` (the runaway step) and `respond()` (the stories). The Chronicle reads new entry kinds. All state is one saved table, `derpy_director_empires`.

**Tech Stack:** Lua 5.1 (the game's), CA's campaign script API, the Python harness `tools/build_director.py` (runs the shipped Lua under `lua.exe` with stubs), `tools/mutate_director.py`, `tools/preview_director.py`, RPFM through `tools/rpfm_client.py` for the pack.

**Spec:** `docs/superpowers/specs/2026-11-15-director-empires-design.md`

## Global Constraints

- The workspace is not a git repo. A "commit" step here is a ledger line in the plan's workspace; the public mirror `repos/derpy-director` is synced, committed and pushed once, in Task 8.
- All model code goes in `Modding Files/pack/script/campaign/mod/derpy_director.lua`, in a new section headed `-- EMPIRES (2026-11-15)` after the runaway step. File-local helpers (`log`, `model_pairs`, `humans`, `PRICE`, `STANCE_HOSTILE`) are reused, not copied.
- Default is no cheats: "Every settlement an empire gains, it takes itself in war, or gains through a confederation the game allows." Cheats exist only under the MCT preset (spec 6b), default `"natural"`.
- Never a human: no war target, stance push, peace, merge or cheat names, owns or involves a human faction. Never another empire as a target or stance target.
- Chronicle entries are keys and numbers only. No loc lookup in a turn handler or the first tick.
- Receivers, from CA's doc entries: `cm:force_make_peace(key, key)`, `cm:create_force(key, csv, region_key, x, y, id, true)`, `cm:transfer_region_to_faction(region_key, faction_key)`, `cm:find_valid_spawn_location_for_character_from_settlement(faction_key, region_key, false, true, dist)` (returns -1, -1 when none); the payload builder's `war_coordination_target(FACTION_IFACE, REGION_IFACE, true)` then `cm:apply_payload(payload, FACTION_IFACE)`. Read each with `py tools/check_lua_api.py --explain <member>` before writing it.
- Iteration over factions or regions is sorted (count, then key), never raw `pairs`, so every multiplayer machine decides the same.
- No `string.find` with a plain flag or an init argument, in shipped code or probes. Run `py tools/check_lua_literal_left.py` on the file before packing.
- Every new listener body runs through `guarded(...)`.
- Player text follows CA's voice; the sentences are the spec's section 9 drafts.
- Live tests follow `docs/LIVE_TESTING.md`: own mod list, test prefs applied then reverted, the player shield loaded, the game quit after.

## Review Focus

1. A save from before Phase 4 (ambitious minors in the seed, no `derpy_director_empires`), loaded at turn 57: no error, roles assigned at the first turn start, the minors replaced at turn 60. Test in Task 3.
2. An empire absorbed by someone else's confederation (dead): never helped afterwards, no error, replaced at the next check. Test in Task 3.
3. A player owns the weakest settlement next to an empire, or is its weakest neighbour or a stronger enemy: no lever ever picks the player. Test in Task 5.
4. Multiplayer with MCT set to Relentless: Natural, no cheat calls. Test in Task 6.
5. The Empires switch turned off mid-campaign: help, shelter and cheats stop at once and the runaway step measures as before; on again, it resumes from the saved state. Tests in Tasks 3 and 4.

---

### Task 1: Live spike - the war target and the map's size

**Files:**
- Create (scratchpad, never shipped): `<scratchpad>/probes/emp_pairs.lua`, `<scratchpad>/probes/emp_target.lua`, `<scratchpad>/probes/emp_watch.lua`

**Interfaces:**
- Produces: two ledger rulings that Tasks 3 and 5 read: `IE_REGIONS = <measured count>` and `TARGET_BEAT = true|false`.

- [ ] **Step 1: Write the three probes.** `emp_pairs` lists AI factions at war with an AI faction that owns a settlement adjacent to their territory, each pair with the attacker's armies' logical distance to that settlement, and returns `region_manager():region_list():num_items()`. `emp_target` builds `cm:create_payload()`, calls `war_coordination_target(attacker, region, true)`, applies it to the attacker, and returns both results. `emp_watch` returns, for both pairs, the nearest army's distance, whether the settlement is under siege (`--explain` the siege call first) and its owner.
- [ ] **Step 2: Check the probes.** Run: `py tools/check_lua_api.py <scratchpad>/probes/emp_*.lua`. Expected: `0 suspect call(s)`, and no `string.find` in any probe.
- [ ] **Step 3: Launch.** Game shut; `py tools/wh3_test_prefs.py --apply` (if it refuses, compare the live prefs with the backup as on 2026-11-15 before doing anything); a mod list of `!!!!out.pack` and `wh3_mcp_server.pack` only (CA's AI, no Director); load `derpy_vfx_min_ie_t1.13813830289.save`; load `tools/wh3_player_shield.lua`.
- [ ] **Step 4: Pick and apply.** Run `emp_pairs`; pick two pairs with similar distances; run `emp_target` on the first only (the second is the control). Expected: the payload calls return without error.
- [ ] **Step 5: Play five turns** with `wh3_soak_turns`, running `emp_watch` after each. Pass: the targeted pair's nearest army closes on, besieges or takes the target, and does so more than the control.
- [ ] **Step 6: Record and close.** Ledger: `Task 1: Ruling: TARGET_BEAT = <true|false> - <distances per turn, both pairs>` and `Task 1: Ruling: IE_REGIONS = <count> (DB says 644)`. Quit the game, `--revert` the prefs, delete the mod list.

### Task 2: Picking the empires

**Files:**
- Modify: `Modding Files/pack/script/campaign/mod/derpy_director.lua` (`roll_ambitious` near line 371, `roll_seed` near 402, new EMPIRES section)
- Modify: `tools/build_director.py` (harness `faction()` stub, `MCT_SECTIONS`, `MCT_OPTIONS`, new `_selftest_empires_pick`, called from `_selftest` after `_selftest_chronicle`)
- Modify: `tools/mutate_director.py`

**Interfaces:**
- Produces: `derpy_director:empire_candidate(f, strict) -> bool`; `derpy_director:spread_ok(key, chosen) -> bool`; `roll_ambitious() -> {key}` ordered most settlements first (ties by key); Chronicle entry `{t, k = "empire", i = key, n = 1|2}` (1 for the first, the great power); constant `EMPIRE_SPREAD_HOPS = 6`; MCT option `empires` (checkbox, default true, section `empires`, titled "Empires").
- Harness: a faction spec's `minor = true` makes `can_be_human()` false (default true) and `horde = true` makes `is_allowed_to_capture_territory()` false (default true).

- [ ] **Step 1: Write the failing test** `_selftest_empires_pick()`. A row of regions `r1..r12`, each adjacent to its neighbours; factions own one or more each. Rolled with `preload={"derpy_director_seed": False}`; picks read by an `Eval` of `table.concat(derpy_director:seed().ambitious, ",")`.

```python
picks = evals(c)[0].split(",")
assert len(picks) == 3
assert not set(picks) & {"tiny_minor", "horde", "player", "rebel", "vassal", "invader"}, picks
assert picks[0] == "biggest_major"            # most settlements first: the great power
# spread: no two picks' home regions within 6 hops (the fixture puts "near_major" 3 hops from
# biggest_major, so it is never picked while another candidate exists)
assert "near_major" not in picks, picks
roles = [(x["k"], x["i"], x["n"]) for x in _chron(c) if x["k"] == "empire"]
assert roles == [("empire", picks[0], "1"), ("empire", picks[1], "2"), ("empire", picks[2], "2")]
# fallback: one major and four minors on the map -> the major plus two minors
assert evals(c_small)[0].split(",")[0] == "only_major" and len(evals(c_small)[0].split(",")) == 3
```

- [ ] **Step 2: Run it to see it fail.** Run: `py -c "import sys; sys.path.insert(0,'tools'); import build_director as B; B._selftest_empires_pick()"`. Expected: AssertionError (today's roll is uniform and writes no Chronicle entry).
- [ ] **Step 3: Implement** the candidate test (alive, AI, not rebel, not `is_invader`, not vassal, at least one region, `is_allowed_to_capture_territory()`, and `can_be_human()` when `strict`), `spread_ok` (the candidate's `home_region()` key is not in `within_reach(home, EMPIRE_SPREAD_HOPS)` of any chosen empire's home, and vice versa), and the draw: strict candidates first, by `cm:random_number` over the sorted pool, then non-strict to fill. `roll_seed` writes one `empire` entry per pick after `set_saved_value`. Add the `empires` option.
- [ ] **Step 4: Run it to see it pass**, then the whole self-test: `py tools/build_director.py --selftest`. Expected: `selftest: empires pick ok` and exit 0.
- [ ] **Step 5: Mutants.** Add to `MUTANTS`, anchored on the implementing lines: the `can_be_human` test dropped; the horde test dropped; the spread check always true; the fallback removed; the great power not put first. Run `py -c "import sys; sys.path.insert(0,'tools'); import mutate_director as M; M.run([m for m in M.MUTANTS if 'empire' in m[0]])"`. Expected: every new mutant killed, 0 stale.
- [ ] **Step 6: Ledger line** `Task 2: complete (...)`.

### Task 3: The schedule, roles, replacement and graduation

**Files:**
- Modify: `derpy_director.lua` (EMPIRES section; `FEED` table near line 151; `WorldStartRound` listener near line 2051)
- Modify: `tools/build_director.py` (harness: `region_manager()` gains `region_list()` answering `MAP_REGIONS` items, a new `run_lua(map_regions=644)` parameter; `STATE_KEYS` gains `derpy_director_empires`; `FEED_ROWS` gains `empire_rise`; three MCT sliders; new `_selftest_empires_schedule`)
- Modify: `tools/mutate_director.py`

**Interfaces:**
- Consumes: Task 2's `roll_ambitious`, `empire_candidate`, `spread_ok`.
- Produces:
  - `derpy_director:empires() -> st`, saved as `derpy_director_empires`: `{great = key|nil, graduated = {[key] = turn}, chosen = {[key] = turn}, help = {[key] = turn}, merged = {[key] = turn}, cheat = {[key] = turn}, snaps = {{t = turn, n = {[key] = count}}, ...}}` (the last three snapshots, of strict candidates only). A missing table is built from `seed().ambitious` (the old-save path).
  - `map_scale() -> number` = map regions / `IE_REGIONS` (Task 1's ruling, 644 until then); `empire_goal(key) -> int`, `math.floor(setting * map_scale() + 0.5)` for the role; `expected(key, turn) -> number`, `goal * clamp((turn - 10) / (setting("empire_goal_turn") - 10), 0, 1)`.
  - `empire_band(key, turn) -> "graduated"|"ahead"|"behind"|"far"|nil`: nil when not an empire or `empires` is off; `"far"` when `n < 0.6 * expected` and `turn >= 25`; `"behind"` when `n <= expected`; else `"ahead"`.
  - `assign_roles(st)`: a graduated great power keeps the title; else the non-graduated empire with most regions (ties by key). Reorders `seed().ambitious`, great first, and saves the seed.
  - `empire_turn()`: called from the `WorldStartRound` listener in its own `guarded("empires", ...)`, after the runaway step. Order: off switch; state; graduation for every empire; on turn 20 and every 10 after, `empire_check(turn)`; then help (Task 5) and cheats (Task 6).
  - `empire_check(turn)`: snapshot, replacement, `assign_roles`. `graduate(key, st, turn)`: the entry, the feed message for the great power, `st.graduated[key] = turn`.
  - Chronicle: `{k = "empire_fade", i}`, `{k = "empire_goal", i, n = count, g = 1|2}`, and a replacement's own `{k = "empire", i, n}`.
  - Feed: `FEED.empire_rise = {index = 8100, key = "empire_rise"}`; FEED_ROWS row `empire_rise`, index 8100, image `all/elector_confederation`, icon `event_gen_news_negative.png`, sound `UI_CAM_POPUP_Message_Event_Negative`, title "A Great Power Rises", primary "One power has grown into an empire the world cannot ignore. Its capital is marked on the map.", secondary "The balance of the world has shifted.". Sent with `show_message_event_located` at the great power's home region to every human, on its graduation only.
  - MCT sliders: `empire_great_goal` 50 (30-100), `empire_lesser_goal` 25 (10-50), `empire_goal_turn` 80 (40-150).

- [ ] **Step 1: Write the failing test** `_selftest_empires_schedule()`.

```python
goal = lambda key, mr=644: evals(run_lua(W, events=[ev("return derpy_director:empire_goal('%s')" % key)],
                                         preload=P, map_regions=mr)[0])[0]
assert (goal("great"), goal("lesser")) == ("50", "25")
assert (goal("great", 279), goal("lesser", 279)) == ("22", "11")
exp = lambda t: float(evals(...("return derpy_director:expected('great', %d)" % t))[0])
assert [exp(t) for t in (10, 45, 80, 100)] == [0.0, 25.0, 50.0, 50.0]
# bands at turn 50 (expected 28.57 for the great power, far below 17.14)
assert [band(n) for n in (30, 28, 18, 17)] == ["ahead", "behind", "behind", "far"]
assert band(5, turn=24) == "behind"               # far only from turn 25
# graduation: the great power reaching 50 -> one entry, one located feed message per human,
# band "graduated" for ever after, even at 30 settlements
assert ("empire_goal", "great", "50", "1") in goals(c) and len(feed(c, "empire_rise")) == 1
assert band_after_shrink == "graduated"
# a lesser empire's graduation: an entry with g=2 and no feed message
# replacement at turn 20: a dead empire and one under half its schedule are replaced by the
# candidate with the biggest gain since the oldest snapshot; fade then empire entries
assert fades(c) == ["dead_one", "stalled_one"] and new_picks(c) == ["grower_a", "grower_b"]
# a graduate is never replaced, even shrunk to 10 or dead (spec 8: "No new empire replaces a
# graduate")
assert fades(c_grad_shrunk) == [] and fades(c_grad_dead) == []
# Review Focus 1: old save, seed ambitious = two minors, no empires table, events start at 57
assert no_errors(c) and roles_set_at(c, 57) and fades_at(c, 60) == ["minor_a", "minor_b"]
# Review Focus 2: an empire confederated into another faction (FactionJoinsConfederation) is
# never helped afterwards and is replaced at the next check
# Review Focus 5 (half): with MCT empires=False, empire_turn writes nothing and no entry appears
```

- [ ] **Step 2: Run it to see it fail.** Expected: AttributeError-style Lua failure (`empire_goal` is nil).
- [ ] **Step 3: Implement** the functions and the feed row above. Replacement in `empire_check`: an empire that is not graduated and is either dead or under `0.5 * expected` is replaced by the strict candidate (non-strict if none) with the largest gain against the oldest kept snapshot (ties: more regions, then key), not already an empire, passing `spread_ok` against the rest. Write the snapshot after replacing.
- [ ] **Step 4: Run** the group, then `py tools/build_director.py --selftest`. Expected: `selftest: empires schedule ok`, exit 0, and `check_feed` clean with 8100 unused by vanilla.
- [ ] **Step 5: Mutants:** far band from turn 0; graduation not sticky; the great power gets the lesser goal; the scale ignored; replacement keeps a dead empire; the feed sent for a lesser graduation; the off switch ignored. Run the subset. Expected: all killed.
- [ ] **Step 6: Ledger line.**

### Task 4: Shelter

**Files:**
- Modify: `derpy_director.lua` (`measure()` near line 800; `respond()` near 1713)
- Modify: `tools/build_director.py` (new `_selftest_empires_shelter`), `tools/mutate_director.py`

**Interfaces:**
- Consumes: Task 3's `empire_band`.
- Produces: `derpy_director:shelters(key) -> bool` (band is `"behind"` or `"far"`); `derpy_director:sheltered(sit) -> bool` (`shelters(sit.instigator)` and the victim is not human).

- [ ] **Step 1: Write the failing test** `_selftest_empires_shelter()`.

```python
# measure(): a behind empire with 30 regions and a non-empire leader with 20, runner-up 8:
# the leader is the non-empire, and the ratio is 20/30, so no tier (the empire is the runner-up)
assert lead(c) == ("leader", "20", "30") and tier(c) == "0"
assert lead(c_ahead)[0] == "empire"            # ahead of schedule: it can be named
assert lead(c_grad)[0] == "empire"             # a graduate can be named
assert lead(c_player)[0] == "player"           # Review Focus: a player leader is unchanged
# respond(): a sheltered empire sacks an AI town -> the cast's stance pushes happen, and no
# force_alliance, treasury_mod, shield_on, cai_add_diplomatic_event, force_rebellion_with_faction
# or spawn_plague_at_region
assert pushes(c) and not held_calls(c)
assert held_calls(c_vs_player)                 # victim is a human: answered in full
assert held_calls(c_ahead_sack)                # ahead of schedule: answered in full
assert held_calls(c_switch_off)                # Review Focus 5: empires off -> answered in full
```

- [ ] **Step 2: Run it to see it fail.** Expected: the leader is the empire, and the held calls are present.
- [ ] **Step 3: Implement.** `measure()`: the leader is the largest faction for which `shelters` is false; the runner-up is the largest of all others, sheltered or not. `respond()`: compute `sheltered` once after the cast; skip the pact loop, the grudge block and the per-kind consequences when it is true. The tell and the court move are raised only by a pact or a grudge, so a sheltered deed raises neither; ledger this as `Task 4: Ruling: the spec's "and the tell" is the tell the remaining beats raise, which is none - a sheltered deed says nothing to the player beyond the Chronicle`.
- [ ] **Step 4: Run** the group and the whole self-test. Expected: `selftest: empires shelter ok`, exit 0, every earlier group still green.
- [ ] **Step 5: Mutants:** measure skips nobody; measure drops the empire from the runner-up too; shelter ignores the human-victim rule; shelter holds when ahead. Expected: all killed.
- [ ] **Step 6: Ledger line.**

### Task 5: The levers

**Files:**
- Modify: `derpy_director.lua` (EMPIRES section; `PRICE` near line 121 gains `target = 5`; `TARGET_BEAT` constant from Task 1's ruling)
- Modify: `tools/build_director.py` (harness: the payload gains `war_coordination_target(f, r, off)`, and `apply_payload` records `apply_war_target` with the faction, region and flag when the payload carries one; a `cm:force_make_peace` stub recording `force_make_peace`; new `_selftest_empires_levers`), `tools/mutate_director.py`

**Interfaces:**
- Consumes: Task 3's `empires()`, `empire_band`, `empire_turn`; existing `beat_stance`, `beat_ask`, `merge`, `merge_blocked`, `runaway_keys(1)`, `afford`, `chronicle`.
- Produces: `help(key, band, st, turn)`, run by `empire_turn` for each `behind`/`far` empire when `turn - (st.help[key] or -99) >= HELP_EVERY` (3); `empire_target(key) -> region_key|nil`; `beat_target(key, region_key) -> bool`; `empire_stance(key) -> faction_key|nil`; `empire_peace(key, skip_key) -> faction_key|nil`; `empire_merge(key, st, turn) -> faction_key|nil`. Chronicle `{k = "empire_peace", i, v}` and `{k = "empire_merge", i, v}`.

Rules ("weakest" = fewest regions, ties by key; every candidate list sorted):
- Target (`behind` and `far`, when `TARGET_BEAT`): the weakest region adjacent to the empire's regions whose owner is at war with it, is not human, and is not an empire. `PRICE.target`.
- Stance (when no target was set): the weakest owner of an adjacent region that is AI, not at war with it, not an ally, military ally, vassal or master, not the same subculture, and not an empire. `PRICE.mood`.
- Peace (`far` only): the weakest AI enemy with more regions than the empire, other than the target's owner; asked with `diplomatic_option_peace`; forced when both answers are legal and the sum is positive. `PRICE.force`.
- Kin (`far` only, at most once per empire per 10 turns): the weakest same-subculture faction that has met it, has fewer regions, is not an empire and passes `merge_blocked(key, kin, nil, runaway_keys(1))`; the willing ask when `merge_needs_willing`; `merge_from_turn`, `merges_per_turn` and `merge_price` as `try_merge` applies them; `merge(key, kin, "empire")`.

- [ ] **Step 1: Write the failing test** `_selftest_empires_levers()`.

```python
assert targets(c) == [("great", "r_weak_enemy", "true")]           # weakest enemy town next door
assert targets(c_player_weakest) == [("great", "r_strong_enemy", "true")]   # Review Focus 3
assert targets(c_other_empire_weakest) == [("great", "r_strong_enemy", "true")]
assert pushes(c_no_war) == [("great", "weak_neighbour", "CAI_STRATEGIC_STANCE_VERY_UNFRIENDLY")]
assert not [p for p in pushes(c_no_war_player_only) if p[1] == "player"]   # Review Focus 3
# an empire behind from turn 21 to 30 with targets always available is helped every 3 turns
assert help_turns(c_long) == [21, 24, 27, 30]
assert peace(c_far) == [("great", "strong_enemy")] and peace(c_far_denied) == []
assert peace(c_far_player_enemy) == []                              # Review Focus 3
assert merges(c_far) == [("great", "weak_kin")]
mt = merge_turns(c_far_long)                                        # far for 20 turns, kin to spare
assert len(mt) == 2 and mt[1] - mt[0] >= 10
assert ("empire_merge", "great", "weak_kin") in entries(c_far)
assert not targets(c_ahead) and not pushes(c_ahead)                 # ahead: no help
assert not targets(c_target_off) and pushes(c_target_off)          # TARGET_BEAT false -> stance
assert not targets(c_budget_4) and not pushes(c_budget_4)           # priced from the budget
```

- [ ] **Step 2: Run it to see it fail.** Expected: no `apply_war_target`, `promote_stance`, `force_make_peace` or empire merge recorded.
- [ ] **Step 3: Implement** the rules above.
- [ ] **Step 4: Run** the group and the whole self-test. Expected: `selftest: empires levers ok`, exit 0.
- [ ] **Step 5: Mutants:** the target admits a human owner; the target admits an empire; the stance push admits a human; peace runs when only behind; peace without the positive sum; the kin merge skips `merge_blocked`; the 10-turn merge cadence dropped; `HELP_EVERY` ignored; the target not priced. Expected: all killed.
- [ ] **Step 6: Ledger line.**

### Task 6: The optional cheats and the MCT dropdown

**Files:**
- Modify: `tools/build_director.py` (`mct_page()`, `MCT_STUB` and `run_mct_page()` learn the `dropdown` kind; option `empire_help`; harness stubs; `_selftest_mct`; new `_selftest_empires_cheats`)
- Modify: `derpy_director.lua` (EMPIRES section), `tools/mutate_director.py`

**Interfaces:**
- Consumes: Task 3's `empire_band`, `empires()`, `empire_turn`.
- Produces: `empire_cheats(key, st, turn)`, run by `empire_turn` for a `far` empire when `turn - (st.cheat[key] or -99) >= CHEAT_EVERY` (10) and `setting("empire_help") ~= "natural"`; constants `CHEAT_EVERY = 10`, `EMPIRE_GOLD = 5000`. Not charged to the budget.
- MCT: `{"key": "empire_help", "kind": "dropdown", "default": "natural", "values": [("natural", "Natural", ...), ("generous", "Generous", ...), ("relentless", "Relentless", ...)]}`, emitted as `add_new_option(key, "dropdown")`, `add_dropdown_value(key, label, tooltip, is_default)` per value, then `set_default_value("natural")`, the Exchange's pattern (`tools/gen_zharr_exchange.py:7593`). Tooltips state what each adds, in the spec's 6b words.
- Harness: a faction spec's `armies = [["lord_unit", "u1", "u2"], ...]` backs `military_force_list()` (each force: `unit_list()`, `has_general()` true, `is_armed_citizenry()` false); a region spec's `abandoned = True` makes `is_abandoned()` true and gives it no owner; stubs recording `create_force` (faction, units, region), `transfer_region_to_faction` (region, faction; ownership moves), and `find_valid_spawn_location_for_character_from_settlement` returning `1, 2`.

- [ ] **Step 1: Write the failing tests.** In `_selftest_mct`: `run_mct_page()["empire_help"] == ("dropdown", "natural")`. Then `_selftest_empires_cheats()`:

```python
assert not cheats(c_natural)
assert gold(c_generous) == [("great", "5000")] and not armies(c_generous)
assert gold(c_generous_behind) == []                    # far only
assert gold_turns(c_generous_long) == [25, 35]          # far from turn 25 to 40: every 10 turns
assert chronicle(c_relentless) == chronicle(c_natural)  # cheats are logged, never chronicled
assert armies(c_relentless) == [("great", "u1,u2", "r_home")]   # item 0, the lord, left out
assert ruins(c_relentless) == [("r_ruin", "great")]     # never the owned r_taken next to it
assert not cheats(c_relentless_mp)                      # Review Focus 4: multiplayer -> natural
assert budget_after(c_generous) == budget_after(c_natural)      # cheats cost no budget
```

- [ ] **Step 2: Run them to see them fail.** Expected: `empire_help` missing from the page; no cheat calls.
- [ ] **Step 3: Implement** the dropdown kind, the option and `empire_cheats`: Generous pays `EMPIRE_GOLD`; Relentless also copies the largest force of `military_force_list(true)` by unit count, units at items 1 to n-1, spawned at `home_region()` through the spawn finder (skipped on -1), with id `"derpy_director_empire_" .. key .. "_" .. turn`, and settles the abandoned region adjacent to its territory with the lowest key. Never a human: the empire is AI by construction, and the ruin has no owner.
- [ ] **Step 4: Run** both groups and the whole self-test. Expected: `selftest: empires cheats ok`, exit 0; `py tools/build_director.py --check` writes the page with the dropdown.
- [ ] **Step 5: Mutants:** cheats run on `natural`; cheats run when only behind; the army keeps the lord; the ruin may be owned; cheats charged to the budget; the 10-turn cadence dropped. Expected: all killed.
- [ ] **Step 6: Ledger line.**

### Task 7: The Chronicle's empire lines

**Files:**
- Modify: `Modding Files/pack/script/campaign/mod/derpy_director_chronicle.lua` (`DC.sentence`)
- Modify: `tools/gen_director_ui.py` (`CHRONICLE_LOC`), `tools/preview_director.py` (`SENTENCES`, `_hard_chronicle` kinds)

**Interfaces:**
- Consumes: Tasks 2, 3 and 5's entry shapes.
- Produces: loc rows `empire_great` "{i} set out to become a great power.", `empire_lesser` "{i} set out to build an empire.", `empire_fade` "{i}'s ambitions came to nothing.", `empire_goal_great` "{i} now rules {n} settlements, a great power the world cannot ignore.", `empire_goal_lesser` "{i} now rules {n} settlements, an empire in its own right.", `empire_merge` "{v} joined {i} in a confederation.", `empire_peace` "{i} made peace with {v} to turn its armies elsewhere.". Each name appears as a literal `add("...")` call, which `check_loc` reads.

- [ ] **Step 1: Write the failing test:** one `SENTENCES` fixture per row with its exact expected text, for example `({"t": 50, "k": "empire_goal", "i": "mors", "n": 50, "g": 1}, "Clan Mors now rules 50 settlements, a great power the world cannot ignore.")`, and the five kinds added to `_hard_chronicle`.
- [ ] **Step 2: Run** `py tools/preview_director.py --selftest`. Expected: FAIL on each new sentence (`nil`).
- [ ] **Step 3: Implement** the branches and the rows.
- [ ] **Step 4: Run** `py tools/preview_director.py --selftest`, `py tools/gen_director_ui.py --check` and the render `py tools/preview_director.py`. Expected: `selftest ok`, exit 0, no line wider than its cell; show the picture to the author.
- [ ] **Step 5: Ledger line.**

### Task 8: Ship, see it live, record it

**Files:**
- Modify: `docs/superpowers/specs/2026-11-15-director-empires-design.md` (an as-built section), `docs/MY_MODS.md`, `docs/SESSION_INDEX.md`, `tools/sync_director_repo.py` (`DESIGN` gains this spec and plan), `repos/derpy-director/README.md` and `CHANGELOG.md`

- [ ] **Step 1: Run every check.** `py tools/build_director.py --selftest`, `py tools/preview_director.py --selftest`, `py tools/gen_director_ui.py --check`, `py tools/check_lua_literal_left.py "Modding Files/pack/script/campaign/mod/derpy_director.lua"`, then the full `py tools/mutate_director.py`. Expected: all green; mutants all killed, 0 stale.
- [ ] **Step 2: Build and deploy.** `py tools/build_director.py`; read the new functions back out of the saved pack with `tools/read_pack_index.py`; copy to `data/` only with the game shut (checked in the same command) and compare MD5s.
- [ ] **Step 3: Live, a fresh campaign.** A new Immortal Empires campaign with the bridge, the intro skip and the Director. Expected: the log's `seed rolled` names three factions with a legendary lord, none within 6 hops of another; the Chronicle opens with three "set out" lines and the header lists them, the great power first; no script error.
- [ ] **Step 4: Live, the soak.** Player shield loaded; `wh3_soak_turns` to turn 50, reading every empire's settlements, band and the largest non-empire AI faction every 5 turns. Pass (spec section 11): at turn 50 each empire holds at least 60% of its expected count and the great power is the largest AI faction, with no Director error. Ledger the table. If the session allows, continue to turn 80 and record whether the great power reached its goal (the spec's goal check; not a gate). Quit the game, revert the prefs, delete the mod list.
- [ ] **Step 5: Record.** The spec's as-built section (what changed from the plan, the spike's and the soak's numbers), the MY_MODS row and MD5, one SESSION_INDEX line, `tools/README.md` regenerated if a tool docstring changed.
- [ ] **Step 6: Publish.** `py tools/sync_director_repo.py --selftest`, then `py tools/sync_director_repo.py`; README test count and a CHANGELOG section; commit with the casual message and the `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` trailer; push.

### Task 9: The great power plays to win (spec section 15, added 2026-11-15 after the first soak)

**Files:**
- Modify: `Modding Files/pack/script/campaign/mod/derpy_director.lua` (`help`, `empires`, `empire_check`, `empire_turn`; new `empire_friend`, `promote`, `temper`, the `TEMPER` table, `STANCE_FRIENDLY`)
- Modify: `tools/build_director.py` (stub `cm:force_change_cai_faction_personality`, recorded as `personality`; the levers group's two changed assertions; new group 39 `_selftest_empires_great`), `tools/mutate_director.py`

**Interfaces:**
- Consumes: Task 3's `empires()`, `is_great`, `assign_roles`, `empire_candidate`, `spread_ok`; Task 5's `borders`, `empire_peace`, `empire_merge`; `runaway_keys(1)`.
- Produces: `derpy_director:promote(st, turn) -> key|nil` (called from `empire_check` after the fade and rise entries), `derpy_director:temper(st, turn)` (called from `empire_turn` after the roles settle), `derpy_director:empire_friend(key, skip_key) -> key|nil`, the saved field `st.temper = {key = turn}`.

- [ ] **Step 1: Write the failing tests.** Levers group: a great power behind (10 of 15 at turn 31, an enemy of 12) gets peace and a kin merge; a lesser behind gets neither; with no war the great power gets the hostile push and a friendly push toward its strongest neighbour it is not at war with, for one price of 5. Group 39: at the turn-30 check a non-empire of 25 against a great power of 20 takes the title, the weakest lesser fades, and the Chronicle has the fade and an `empire` entry with n=1; a tie changes nothing; a newcomer within 6 hops of an empire that stays is passed over; a measured runaway is passed over; a graduated lesser larger than the great power takes the title and loses its graduation; a great power at its goal keeps it. Temper: a Skaven great power gets `wh3_combi_skaven_endgame` once over five turns; a Greenskin great power and a Skaven lesser get none; a promoted Skaven newcomer gets it at the check.
- [ ] **Step 2: Run** `py tools/build_director.py --selftest`. Expected: FAIL on the levers group's behind peace.
- [ ] **Step 3: Implement.** Help from behind for the great power; the friendly push; `promote`; `temper` with the six rows of spec section 15; `temper` added to `empires()`'s defaults.
- [ ] **Step 4: Run** the selftest, `check_lua_api`, `check_lua_literal_left`, `check_lua_undeclared`. Expected: all green.
- [ ] **Step 5: Mutants:** behind help for every empire; no behind help for the great power; the friendly push for a lesser; the friendly push at the hostile target; a tie promotes; a runaway promoted; the newcomer's spread unchecked; the strongest lesser dropped; the graduation kept on promotion; a graduate great power loses the title; the temper every turn; the temper for a lesser. Expected: all killed, then the full run 0 survived, 0 stale.
- [ ] **Step 6: Rebuild, deploy, soak** to turn 80 on a fresh roll as Task 8 Step 4. Pass (spec section 15): a faction at 50 by turn 80, the great power the largest AI faction at 80, no Director error; and the log shows the endgame personality's owner still building and holding its towns. Record in the spec, then Task 8 Steps 5 and 6.
