# Director merges the Coalition Supervisor - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the Coalition Supervisor's runaway pressure into the Director, give the Director the
power to confederate kin factions (runaway and last-stand triggers) within what the game allows,
expose it through a new MCT page, and delete the Supervisor.

**Architecture:** Everything lands in `derpy_director.lua`, paid from the Director's existing
budget and logged under `[director]`. The runaway measure runs in the existing turn-start
listener; merges run inside `respond()`. The MCT options live in one Python list in
`tools/build_director.py`, which generates both the MCT page and a defaults table in the
already-generated lore file, so the page and the reader cannot drift. Every rule is tested by
running the shipped Lua under the existing Lua 5.1.5 harness and proved by a mutant.

**Tech Stack:** Lua 5.1.5 (game scripts), Python 3 (`tools/build_director.py` harness, generator,
packer; `tools/mutate_director.py`), RPFM via `tools/rpfm_client.py`, the wh3-mcp bridge for live
checks.

**Spec:** `docs/superpowers/specs/2026-11-14-director-merges-coalitions-design.md` (approved).
Read it alongside this plan; section numbers below (§) refer to it.

## Global Constraints

- The workspace is **not a git repo**. There are no commits. Each task ends by running the full
  selftest instead, and Task 2 backs up every file this plan edits.
- Lua 5.1. Check every new engine call with `py tools/check_lua_api.py --explain <member>` before
  using it; run `py tools/check_lua_api.py "Modding Files/pack/script/campaign/mod/derpy_director.lua"`
  and `py tools/check_lua_literal_left.py` on the file before packing.
- Confederate only through the payload route: `cm:create_payload()`,
  `p:form_confederation(absorber_iface, target_iface, false, false)`,
  `cm:apply_payload(p, absorber_iface)`. Never `cm:force_confederation`.
- `FactionJoinsConfederation` fires **inside** `cm:apply_payload`.
- Every listener body goes through the file's existing `guarded()`.
- Sorted iteration only over factions and keys; never raw `pairs()` order into a decision.
- Multiplayer reads MCT defaults only (`cm:is_multiplayer()`).
- The word "rung" is banned in code, logs, tests and docs. The Supervisor's "rung" becomes "tier".
- No emojis anywhere. Player text (MCT page) in plain spoken English, CA's register.
- Deal key for confederation: `diplomatic_option_confederation`.
- Plan decision on §6.5: the one source of the MCT options is `MCT_OPTIONS` in
  `tools/build_director.py`, not a hand-written Lua table. Both the page and the Lua defaults are
  generated from it, which meets §6.5's requirement that the two cannot drift more strictly than
  a comparison would.
- Defaults (§6.5): `merge_last_stand` on, `merge_runaway` on, `last_stand_regions` 1 (1-5),
  `runaway_merge_tier` 1 (1-3), `merge_price` 60 (0-180), `merges_per_turn` 1 (0-3),
  `merge_from_turn` 10 (1-100), `merge_needs_willing` off, `race_<subculture>` on,
  `runaway_threat` on, `runaway_alliances` on, `runaway_min_regions` 10 (5-40).
- Supervisor values carried over (§6.1): tier ratios 1.75 / 2.5 / 4.0, exit 1.35, threat scores
  200 / 350 / 500, past event `PAST_EVENT_NEGATIVE_MINOR`, 8 polled pairs a turn, at most 2 forced
  alliances per faction, at most 2 formed a turn, each priced `PRICE.force` (15).
- Live tests follow `docs/LIVE_TESTING.md`: minimal mod list launched through the Mod Manager
  (never `wh3_start`), `py tools/wh3_test_prefs.py --apply` before and `--revert` after with the
  game shut, every `wh3_eval` body inside `pcall` (one Lua error wedges the bridge), screenshots
  only with `common.take_screenshot("name.tga")`, and quit the game when the test ends.
- Packs that live in `data/` are deployed only with the game shut: check
  `tasklist | grep -i Warhammer3` in the same command as the copy.

## Review Focus

The inputs most likely to bite a player that no rule test below would otherwise hit. Each has its
test in the task that owns the code.

1. `cm:apply_payload` throws inside the merge: the own-merge flag must be cleared and neither the
   budget nor the turn's merge slot spent (Task 5).
2. A save loaded mid-runaway: the threat score's carrier is restored from the save and the score is
   re-applied exactly once (Task 3).
3. An invader key or crisis bundle that does not exist on this campaign map: no error, and nobody
   counts as an invader (Task 6).
4. `merges_per_turn` 0 and `merge_price` 0: the first means no merges at all, the second means
   merges cost nothing but still respect the per-turn limit (Task 5).
5. CA's own confederation in the same turn as a Director merge: it must still be answered as a
   deed, because the own-merge flag names one pair and is cleared after the call (Task 5).

---

### Task 1: Live gate - does the deal probe honour CA's confederation locks?

Everything in "lore by default" rests on this (§8.1). No code is written until it passes.

**Files:**

- Create: `<scratchpad>/probe_confed.lua` (scratch only, never shipped)
- Modify: `docs/superpowers/specs/2026-11-14-director-merges-coalitions-design.md` (§19-style
  result note under §8.1)

- [ ] **Step 1: Write the probe script**

A `wh3_eval` body that returns a string and does all its work inside `pcall`. For each of
`wh_main_sc_vmp_vampire_counts`, `wh_main_sc_grn_greenskins`, `wh_main_sc_dwf_dwarfs` and
`wh3_dlc23_sc_chd_chaos_dwarfs`: walk `cm:model():world():faction_list()`, keep alive, non-human,
non-rebel factions of that subculture with at least one region, sorted by key, and take the first
pair `(a, b)` where `a:factions_met()` contains `b` and `a:at_war_with(b)` is false. Report
`cm:cai_evaluate_quick_deal_action(a, b, "diplomatic_option_confederation")` and the reverse, as
`subculture a b score_ab ok_ab score_ba ok_ba`. A second body merges the Greenskin pair through the
payload route (absorber = the one with more regions) and then probes the absorber against the
next met Greenskin faction, both directions.

- [ ] **Step 2: Set up the test game**

Apply test prefs with the game shut (`py tools/wh3_test_prefs.py --apply`), launch the minimal
mod list (bridge + the Mod Manager's intro-skip pack) through the Mod Manager, start a new
Immortal Empires campaign as Karl Franz, wait for `wh3_wait_for_mod`.

- [ ] **Step 3: Run the probes**

Run: the Step 1 body through `wh3_eval`.
Expected: Vampire Counts `ok=false` in at least one direction (CA locks them culture-wide in
`wh_campaign_setup.lua:3031`); Greenskins `ok=true` both ways; Dwarfs `ok=true` both ways (no
human Dwarf). Chaos Dwarfs: record whatever it says; there is no expectation.

Run: the merge body.
Expected: the merge lands (the absorbed faction `is_dead()` or gone from the list), and the
post-merge probe shows `ok=false` in at least one direction (CA's 10-turn lock on the absorber).

- [ ] **Step 4: Quit and restore**

Quit the game (`wh3_quit_to_menu`, then `wh3_stop`), then `py tools/wh3_test_prefs.py --revert`.

- [ ] **Step 5: Record and decide**

Write the four results under spec §8.1 with the date. **If Vampire Counts or the post-merge probe
came back `ok=true` in both directions, STOP and report to the author:** the probe does not see
CA's script locks, and the design needs its own reading of them. Otherwise continue.

---

### Task 2: Backups, harness stubs and the MCT page

**Files:**

- Create: `Modding Files/Backup/director_20261114/merge_build/` (copies)
- Create: `Modding Files/pack/script/mct/settings/derpy_director.lua` (generated)
- Modify: `tools/build_director.py` (harness, generator, `check()`, `pack()`, new selftest group)
- Modify: `Modding Files/pack/script/campaign/mod/derpy_director.lua` (settings reader)
- Modify: `Modding Files/pack/script/campaign/mod/derpy_director_lore.lua` (regenerated)

**Interfaces:**

- Produces, Python: `MCT_OPTIONS`, a list of dicts
  `{key, kind ("checkbox"|"slider"), default, lo, hi, section, text, tooltip}` in §6.5's order;
  `merge_races() -> [(subculture, display_name)]`; `mct_page() -> str`; and these new `run_lua`
  keyword arguments, all optional:
  `mct={key: value}` (an installed MCT returning these finalized values),
  `multiplayer=False`, `deny=["a|b"]` (`cai_evaluate_quick_deal_action(a, b, *)` returns
  `ok=false`), `payload_error=False` (`cm:apply_payload` raises), `script_state={key: bool}`.
  New faction-spec fields: `met` (list of keys; absent means met everyone), `allies` (defensive),
  `military` (military allies), `vassal_of` (key), `bundles` (list of effect bundle keys).
  New pseudo-event `{"event": "Eval", "code": "<lua returning a value>"}` that records
  `("eval", tostring(result))`. Module-level test helpers `outs(calls, s)` (log lines containing
  `s`), `evals(calls)` (the recorded eval results, in order) and `run_mct_page() -> {key: (kind,
  default)}` (the generated page run under a recording MCT stub with `lua.exe`).
- Produces, Lua: `derpy_director:setting(key)` returns the MCT value or the default; unknown keys
  log `unknown setting <key>` and return nil. Globals generated into the lore file:
  `derpy_director_mct_defaults` (key -> default for every non-race option) and
  `derpy_director_merge_races` (subculture -> true for the 23 races).

- [ ] **Step 1: Back up**

Copy `derpy_director.lua`, `derpy_director_lore.lua`, `tools/build_director.py`,
`tools/mutate_director.py` into `Modding Files/Backup/director_20261114/merge_build/`.

- [ ] **Step 2: Write the failing MCT tests** as `_selftest_mct()` in `build_director.py`, called
from `_selftest()` after the long-run group:

```python
def _selftest_mct():
    races = [sc for sc, _ in merge_races()]
    assert len(races) == 23, races
    for sc in ("wh3_dlc23_sc_chd_chaos_dwarfs", "wh2_dlc11_sc_cst_vampire_coast",
               "wh_main_sc_vmp_vampire_counts", "wh3_dlc29_sc_nag_undead_legions"):
        assert sc in races, sc
    for sc in ("wh2_dlc09_sc_tmb_tomb_kings", "wh_main_sc_chs_chaos",
               "wh_main_sc_grn_savage_orcs", "wh_main_sc_teb_teb", "wh2_main_rogue",
               "wh3_main_pro_sc_ksl_kislev"):
        assert sc not in races, sc
    page = open(MCT_PAGE, encoding="utf-8").read()
    assert page == mct_page(), "the MCT page is stale - run --check"
    # The page, run under a recording MCT stub, registers exactly MCT_OPTIONS plus one checkbox
    # per race, with these defaults.
    reg = run_mct_page()                 # {key: (kind, default)}
    want = {o["key"]: (o["kind"], o["default"]) for o in MCT_OPTIONS}
    want.update({"race_" + sc: ("checkbox", True) for sc in races})
    assert reg == want, set(reg) ^ set(want)
    w = [{"name": "a", "regions": 1, "subculture": "wh_main_sc_dwf_dwarfs"}]
    ev = lambda k: [{"event": "Eval", "code": "return derpy_director:setting(%r)" % k}]
    get = lambda calls: [c[1] for c in calls if c[0] == "eval"]
    assert get(run_lua(w, events=ev("merge_price"))[0]) == ["60"]
    assert get(run_lua(w, events=ev("merge_price"), mct={"merge_price": 90})[0]) == ["90"]
    # Wrong type falls back; multiplayer ignores MCT; races default on and read MCT.
    assert get(run_lua(w, events=ev("merge_price"), mct={"merge_price": "90"})[0]) == ["60"]
    assert get(run_lua(w, events=ev("merge_price"), mct={"merge_price": 90},
                       multiplayer=True)[0]) == ["60"]
    k = "race_wh_main_sc_grn_greenskins"
    assert get(run_lua(w, events=ev(k))[0]) == ["true"]
    assert get(run_lua(w, events=ev(k), mct={k: False})[0]) == ["false"]
    assert get(run_lua(w, events=ev("no_such_key"))[0]) == ["nil"]
    print("selftest: mct ok")
```

- [ ] **Step 3: Run it to see it fail**

Run: `py tools/build_director.py --selftest`
Expected: FAIL at `merge_races` / `MCT_PAGE` not defined.

- [ ] **Step 4: Implement**

In `build_director.py`: `MCT_PAGE` path constant; `MCT_OPTIONS` with §6.5's keys, kinds, ranges
and defaults, sections `merging` ("Merging"), `races` ("Races that may merge"), `runaway`
("Runaway"); `merge_races()` reads db.pack's `cultures_subcultures_tables` and
`diplomatic_action_subculture_restrictions_tables` with `tools/read_vanilla_db.py`, keeps every
subculture except `filter_all`, keys containing `_pro_`, and keys whose `can_make_confederations`
is False, sorted, with the display name from `read_vanilla_loc` key
`cultures_subcultures_name_<subculture>`; `mct_page()` emits the page in
`derpy_no_early_wars.lua`'s style (`get_mct`, `register_mod("derpy_director")`, sections, options,
`set_default_value`, `set_assigned_section`); `build_lore()` appends the two generated globals;
`check()` writes the page beside the lore file and `luac -p`s it; `pack()` adds it at
`script/mct/settings/derpy_director.lua` and lists it in the verify step; `run_mct_page()` runs the
page under a recording MCT stub with `lua.exe`. Harness: the stubs and `run_lua` arguments named
in Interfaces; `get_mct()` exists only when `mct` is given, and its options answer
`get_finalized_setting()` with the given value or the option's default.

In `derpy_director.lua`: `setting(key)` reads `derpy_director_mct_defaults[key]`, or `true` for a
`race_` key whose subculture is in `derpy_director_merge_races`; returns the default when
`cm:is_multiplayer()` or MCT is absent; otherwise the finalized MCT value only if its Lua type
equals the default's. MCT text follows the player-text rules; tooltip wording is the
implementer's.

- [ ] **Step 5: Regenerate and run**

Run: `py tools/build_director.py --check` then `py tools/build_director.py --selftest`
Expected: `check ok`, then every group prints ok including `selftest: mct ok`.

---

### Task 3: Runaway measure, threat score and tier-rise grudge

**Files:**

- Modify: `Modding Files/pack/script/campaign/mod/derpy_director.lua` (new runaway section after
  `release_shields`; turn-start listener; `first_tick`; `beat_stance` comment; header comment)
- Modify: `tools/build_director.py` (test 9; new group `_selftest_runaway()`)

**Interfaces:**

- Consumes: `setting(key)` (Task 2).
- Produces: `derpy_director:tier_for(ratio, leader_regions, current) -> integer 0..3`;
  `derpy_director:measure() -> leader_iface|nil, best, second, ratio`;
  `derpy_director:runaway() -> table` (the saved `derpy_director_runaway`:
  `{tier, scored_key, cursor, alliances, last_event_tier, formed_turn, formed_count}`, with
  defaults); `derpy_director:runaway_turn()` (called from the turn-start listener after
  `adapt_turn()` and before `opportunity()`); `derpy_director:leader_key() -> key|nil` (the
  measured leader at its current tier, nil at tier 0). Session field
  `self.runaway_reapply` set true in `first_tick()`.

- [ ] **Step 1: Write the failing tests** in `_selftest_runaway()`, ported from
`build_ai_coalitions.py` groups 1-5c, 11e (score half) and 12-12c, with "rung" renamed "tier".
`MIN_REGIONS` is now `setting("runaway_min_regions")`.

```python
W1 = [{"name": "a", "regions": 1, "subculture": "wh_main_sc_dwf_dwarfs"}]
tier = lambda r, n, cur: evals(run_lua(W1, events=[{"event": "Eval",
           "code": "return derpy_director:tier_for(%s, %d, %d)" % (r, n, cur)}])[0])[0]
assert [tier(r, 10, 0) for r in (1.74, 1.75, 2.5, 4.0)] == ["0", "1", "2", "3"]
assert tier(1.5, 10, 2) == "1" and tier(1.5, 10, 3) == "1"      # held at the minimum tier
assert tier(1.5, 10, 0) == "0" and tier(1.34, 10, 2) == "0"     # never starts; exits below 1.35
assert tier(4.0, 9, 0) == "0"                                   # runaway_min_regions 10
```

Turn-driven: a world with `leader` 25 regions and `second` 10 (ratio 2.5) over three turns
records `set_base_strategic_threat_score leader 350` exactly once; dropping `leader` to 13 with
`SetRegions` (ratio 1.3) records `... leader 0` once and `threat score released on leader`;
a leader swap records the old carrier's release before the new score; a world where only one
faction holds regions releases a held score; `runaway_threat` off in MCT records no score call at
all. Past event: on the turn the tier first rises, one `cai_add_diplomatic_event leader <f>
PAST_EVENT_NEGATIVE_MINOR` per polled faction, sorted, never repeated while the tier holds, fired
again after a fall and a fresh rise. Load: preload `derpy_director_runaway` with
`{"tier": 2, "scored_key": "leader", ...}` and run one turn: exactly one score call on `leader`.

Change test 9's last assertion to: no `set_base_strategic_threat_score` in the sack-only world
(no faction leads by 1.75), with message "only the runaway step may set the threat score".

- [ ] **Step 2: Run to see them fail**

Run: `py tools/build_director.py --selftest`
Expected: FAIL in `_selftest_runaway` (`tier_for` is nil).

- [ ] **Step 3: Implement** the section by porting `derpy_ai_coalitions.lua` lines 8-98 and
256-284 (`rung_for`, `measure`, `release_threat`, `apply_threat`, `tick`) into
`derpy_director` methods with the renames above, state in the one saved table, constants
`TIER_RATIOS = {1.75, 2.5, 4.0}`, `TIER_EXIT = 1.35`, `TIER_SCORES = {200, 350, 500}` plus the
Supervisor's index-coupling `assert`. The poll call stays a stub returning the batch's factions
for the past event until Task 4 (`poll_batch(leader) -> list of factions`, sorted, met the leader).
Drop `claim_context` entirely. Update the `beat_stance` comment and the file header to say the
runaway step is the only writer of the threat score. Log each turn as
`runaway turn=%d leader=%s regions=%d runner_up=%d ratio=%.2f tier=%d`, and
`threat score %d on %s` / `threat score released on %s` (§6.7).

- [ ] **Step 4: Run**

Run: `py tools/build_director.py --selftest`
Expected: all groups ok, including `selftest: runaway ok`.

---

### Task 4: The alliance poll, through the pact machinery

**Files:**

- Modify: `derpy_director.lua` (runaway section)
- Modify: `tools/build_director.py` (`_selftest_runaway()` additions)

**Interfaces:**

- Consumes: `beat_ask(a_key, b_key, deal)`, `at_odds(a_key, b_key)`, `beat_force(a_key, b_key)`,
  `afford(price)`, `PRICE.force`, `runaway()`, `setting("runaway_alliances")`.
- Produces: `derpy_director:poll_alliances(leader_iface, st)`; `poll_batch` now returns the
  polled pairs' factions. Constants `POLL_PAIRS = 8`, `MAX_FORCED_ALLIANCES = 2`,
  `FORMS_PER_TURN = 2`.

- [ ] **Step 1: Write the failing tests** (ported groups 6-9c plus the new limits), each in a world
where `leader` leads at tier 1 and the candidates are non-human, have 2+ regions, met the leader:

- both directions are asked, logged with `ok=`;
- a pair forms on score **sum** above zero (`{"a|b": -5, "b|a": 8}` forms; `{-5, 4}` does not);
- a pair that has not met each other is never asked and does not use up the 8-pair batch;
- two identical runs give identical call lists;
- a faction holding 2 forced alliances is never in a third;
- an existing defensive or military alliance is not re-forced;
- a human is never a candidate;
- `at_odds` pairs are logged `no ask` and not asked;
- with five willing pairs, at most 2 form in one turn and each spends 15 from the budget
  (`derpy_director_budget` falls by 30);
- budget below 15 forms nothing;
- `runaway_alliances` off asks nothing.

- [ ] **Step 2: Run to see them fail**

Run: `py tools/build_director.py --selftest`. Expected: FAIL in the poll assertions.

- [ ] **Step 3: Implement** `poll_alliances` from the Supervisor's `candidates()` and `poll()`
(lines 103-216, the met-each-other filter and the cursor included), replacing `consider()` with
`at_odds` -> `beat_ask(.., DEAL)` -> sum rule -> `afford(PRICE.force)` -> `beat_force`, counting
`alliances[key]` and the turn's `formed_count`.

- [ ] **Step 4: Run**

Run: `py tools/build_director.py --selftest`. Expected: all groups ok.

---

### Task 5: Merge core and the last stand

**Files:**

- Modify: `derpy_director.lua` (new merge section after the runaway section; `respond()`;
  `from_confederation()`; `on_secession()`)
- Modify: `tools/build_director.py` (new group `_selftest_merge()`)

**Interfaces:**

- Consumes: `setting(key)`, `beat_ask`, `afford`, `budget()`, `leader_key()`.
- Produces:
  - `derpy_director:is_invader(f_iface) -> boolean`, returning false here; Task 6 fills it in;
  - `derpy_director:runaway_keys() -> sorted list of keys` (Task 6 adds invaders; here the
    leader alone when its tier is at least `runaway_merge_tier`);
  - `derpy_director:merge_blocked(absorber_key, target_key, sit) -> reason string | nil`;
  - `derpy_director:kin_for(victim_key, sit) -> list of keys` (same subculture, met the victim,
    sorted by region count descending then key, at most 3 after exclusions);
  - `derpy_director:try_merge(sit, mode) -> boolean` with `mode` `"last_stand"` or `"runaway"`;
  - `derpy_director:merge(absorber_key, target_key, mode) -> boolean`;
  - `derpy_director:last_stand(sit) -> boolean`;
  - saved `derpy_director_merge_turn` / `derpy_director_merge_count`, saved set
    `derpy_director_risings`, session field `self.merging = "absorber|target"` during the call.

- [ ] **Step 1: Write the failing tests** in `_selftest_merge()`. Base world: `sacker` (Empire,
8 regions, so nobody leads by 1.75) takes a town from `vic` (Greenskins, `regions` 1 after the
change); `kin_big` (Greenskins, 6 regions), `kin_small` (Greenskins, 3). Events: `SetBudget 180`
on turn 12, then `RegionFactionChangeEvent sacker -> vic` on turn 12. "Budget as without" below
means `derpy_director_budget` equals the same run with `merge_last_stand` off, since the
situation's other beats spend too.

```python
merges = lambda calls: [(c[1], c[2]) for c in calls if c[0] == "apply_payload"]
c, st = run_lua(base, events=conq, regions_spec=regions)
assert merges(c) == [("kin_big", "vic")], merges(c)
assert outs(c, "merge kin_big absorbs vic (last_stand)")
assert outs(c, "own merge, not a deed: kin_big + vic")
assert not [x for x in c if x[0] == "stance_promote" and x[2] == "kin_big"]  # not answered
_, off = run_lua(base, events=conq, regions_spec=regions, mct={"merge_last_stand": False})
assert int(off["derpy_director_budget"]) - int(st["derpy_director_budget"]) == 60
```

Then one assertion block per rule, each varying one thing in `base`:

- `vic` at 2 regions: no merge; at 0 regions: merges; `last_stand_regions` 2 and `vic` at 2: merges;
- `deny=["kin_big|vic"]`: `kin_small` absorbs; deny both kin: `no merge for vic: ...`, budget as
  without, and a second dying victim later the same turn still merges (the slot was not taken);
- scores ignored by default (`{"kin_big|vic": -50, "vic|kin_big": -50}` still merges);
  `merge_needs_willing` on with those scores: `kin_small` absorbs;
- each exclusion skips `kin_big` and `kin_small` absorbs: `kin_big` human; `kin_big` a vassal of
  anyone; `kin_big` the instigator (the conquest made by `kin_big` itself); `kin_big` at war
  with `vic`; `kin_big` the runaway (25 regions, against `sacker`'s 8); `kin_big` a defensive
  ally of a runaway `emp_big` (Empire, 25 regions); `kin_big` of another subculture; `kin_big` in `derpy_director_risings`; a human
  Chaos Dwarf in the world while `vic`, `kin_big` and `kin_small` are Chaos Dwarfs: no merge;
  the same world with no human Chaos Dwarf: merges;
- `race_wh_main_sc_grn_greenskins` false: no merge; turn 9 with `merge_from_turn` 10: no merge;
- `merges_per_turn` 1 with two dying victims in one turn: one merge; `merges_per_turn` 0: none;
  `merge_price` 0: merges, budget as without; `SetBudget 59`: no merge, logged
  `no merge for vic` with the price as the reason;
- a province of three towns falls in one turn (three conquests on turn 12, with `SetRegions vic`
  2, then 1, then 0 before each): the merge happens on the second conquest, after the feud guard
  has already answered the first;
- `merge_last_stand` off: no merge;
- **Review Focus 1:** `payload_error=True`: no merge recorded, `merge failed` logged, budget and
  merge count unchanged, and a following `FactionJoinsConfederation kin_big -> vic` event IS
  answered (the flag was cleared);
- **Review Focus 5:** after a Director merge, a `FactionJoinsConfederation other_a -> other_b`
  event in the same turn is answered as a confederation situation;
- an Iron Court secession (`companions={"ic": True}`, a `Secession` event) puts the rebels' key in
  `derpy_director_risings`.

- [ ] **Step 2: Run to see them fail**

Run: `py tools/build_director.py --selftest`. Expected: FAIL in `_selftest_merge` (no
`apply_payload` recorded).

- [ ] **Step 3: Implement**

`merge_blocked` checks, in this order, and returns the first reason: either side missing, dead,
rebel, human; either side `is_invader`; either side `is_vassal()`, or a
human is `is_vassal_of` it; either side in `derpy_director_risings`; subcultures differ; race
switch off; both Chaos Dwarf (`wh3_dlc23_sc_chd_chaos_dwarfs`) while any human faction is Chaos
Dwarf; at war; absorber in `runaway_keys()`, or `is_vassal_of` / master of /
`military_allies_with` / `defensive_allies_with` one of them; absorber is `sit.instigator`.

`try_merge` order: mode switch -> `turn >= merge_from_turn` -> slot free -> `budget() >= price` ->
`kin_for` -> for each candidate (absorber chosen per mode: last stand, the kin absorbs; runaway,
the side with more regions, ties by key) probe both directions with
`beat_ask(.., "diplomatic_option_confederation")`, require both `ok`, and when
`merge_needs_willing` also `score_ab + score_ba > 0` -> first pass: `merge()`; on success
`afford(price)` and take the slot. Log `no merge for <victim>: <reason>` on every exit.

`merge` sets `self.merging`, runs the payload route in `pcall`, clears `self.merging` in every
path, logs `merge %s absorbs %s (%s)` or `merge failed: <err>`. `from_confederation` returns
false with `own merge, not a deed: a + b` when the pair equals `self.merging`.

In `respond()`, call `self:last_stand(sit)` after `note_loss` and before
`first_of_feud_this_turn`; it runs only for `conquest` and `raze` with a computer victim at or
below `last_stand_regions`. `on_secession` adds `rebels` to `derpy_director_risings`.

- [ ] **Step 4: Run**

Run: `py tools/build_director.py --selftest`. Expected: all groups ok.

---

### Task 6: The runaway trigger and CA's endgame invaders

**Files:**

- Modify: `derpy_director.lua` (merge section, `respond()`)
- Modify: `tools/build_director.py` (`_selftest_merge()` additions)

**Interfaces:**

- Consumes: `try_merge(sit, "runaway")`, `leader_key()`, `runaway()`.
- Produces: `derpy_director:is_invader(f_iface) -> boolean`; `derpy_director:is_runaway(key) ->
  boolean`; `runaway_keys()` now includes alive invaders; `derpy_director:runaway_merge(sit) ->
  boolean`. Constants:
  `INVADERS = {"wh3_dlc29_chaos_invasion_confederation_owner", "wh3_dlc29_vermintide_confederation_owner"}`,
  `NAGASH = "wh3_dlc29_nag_host_of_nagash"`, `NAGASH_STATE = "episode_nagash_endgame"`,
  `CRISIS_BUNDLES = {"wh3_main_ie_scripted_endgame_grudge_too_far", "wh3_main_ie_scripted_endgame_vampires_rise", "wh3_main_ie_scripted_endgame_waaagh", "wh3_main_ie_scripted_endgame_wild_hunt", "wh3_dlc23_ie_scripted_endgame_faction_chaos_dwarfs_hashut"}`.
  The Nagash state is read with
  `cm:model():shared_states_manager():get_state_as_bool_value(NAGASH_STATE)`.

- [ ] **Step 1: Write the failing tests.** World, turn 12: `big` (Empire, 25 regions),
`second` (Dwarfs, 10), victim `vic` (Greenskins, 4 regions, above the last-stand line), kin
`kin_a` (Greenskins, 6). `CharacterSackedSettlement big -> vic`, seed 1 so it is answered.

- `big` at tier 2 (ratio 2.5) and `runaway_merge_tier` 1: `kin_a` absorbs `vic` (more regions),
  logged `(runaway)`; with `vic` at 8 regions, `vic` absorbs `kin_a`;
- `runaway_merge_tier` 3: no merge; `merge_runaway` off: no merge;
- the merge is recorded before any `stance_promote` of the same situation;
- the instigator not a runaway (`big` at 12 regions): no merge;
- each invader kind makes a 5-region instigator a runaway: key
  `wh3_dlc29_chaos_invasion_confederation_owner`; bundle `wh3_main_ie_scripted_endgame_waaagh` on
  an ordinary faction; `wh3_dlc29_nag_host_of_nagash` with `script_state={"episode_nagash_endgame":
  True}` merges, without it does not;
- an invader is never part of a merge: invader kin is skipped as absorber and as target;
- no runaway merge for the other kinds: opportunism where the runaway `big` is the faction that
  lost towns last round (two conquests of `big`'s towns by `vic`, then a turn start, seed 1);
  a `FactionJoinsConfederation big -> x`; a `NegativeDiplomaticEvent` treaty broken by `big`; an
  Iron Court `Secession` with `big` as the realm;
- **Review Focus 3:** a world with none of the invader factions and no bundles: no error, no
  invader, `runaway_keys()` holds only the measured leader.

- [ ] **Step 2: Run to see them fail.** `py tools/build_director.py --selftest`. Expected: FAIL.

- [ ] **Step 3: Implement.** `runaway_merge` runs only for `sack`, `raze`, `conquest`, a computer
victim, `is_runaway(sit.instigator)`, and only if the last stand did not already merge this
victim this situation. Call it in `respond()` right after `chosen()` returns true, before the cast.
`runaway_keys()` walks the faction list once, sorted, and invaders get no threat score.

- [ ] **Step 4: Run.** `py tools/build_director.py --selftest`. Expected: all groups ok.

---

### Task 7: Mutants

**Files:**

- Modify: `tools/mutate_director.py` (`MUTANTS`)

- [ ] **Step 1: Add one mutant per new rule**, each `(name, anchor, replacement)` aimed at the
shipped line, written with the Edit tool (heredocs eat backslashes). At least: tier ratio
boundary `>=` to `>`; hold at the minimum tier removed; exit ratio ignored; score never released;
carrier not saved; re-apply after load dropped; past event fires every turn; met-each-other filter
removed; per-faction alliance limit removed; per-turn form limit removed; sum rule changed to
both-positive; human poll candidate allowed; MCT multiplayer guard removed; MCT type check
removed; each `merge_blocked` clause disabled one at a time; probe ok checked in one
direction only; `merge_needs_willing` ignored; slot taken before a legal partner is found; price
charged on failure; own-merge flag not cleared on error; own-merge check matching any pair;
last stand placed after the feud guard; last stand threshold `<=` to `<`; runaway merge on
opportunism; invader bundle check skipped; Nagash counted without its state; larger-absorbs
reversed.

- [ ] **Step 2: Run the mutants**

Run: `py tools/mutate_director.py`
Expected: every mutant killed, no stale anchors. A survivor means a missing assertion: add it to
the owning task's group and re-run.

- [ ] **Step 3: Runner self-test.** Run: `py tools/mutate_director.py --selftest`. Expected: ok.

---

### Task 8: Delete the Supervisor, update the docs, pack and deploy

**Files:**

- Create: `Modding Files/Backup/director_20261114/coalitions/` (copies)
- Delete: `Modding Files/pack/script/campaign/mod/derpy_ai_coalitions.lua`,
  `Modding Files/Modpacks/derpy_ai_coalitions.pack` and its four `.bak_*` siblings,
  `tools/build_ai_coalitions.py`
- Modify: the reference list in spec §6.8 (CLAUDE.md, GEMINI.md, `Modding Files/CLAUDE.md`,
  `docs/MY_MODS.md`, `docs/DIPLOMACY.md`, `docs/CAMPAIGN_AI.md`, `docs/MODDING_TOOLS.md`,
  four `docs/knowledge-base/` files, `.agents/skills/pack-build/SKILL.md`,
  `.agents/skills/test-harness/SKILL.md`, `tools/build_no_early_wars.py` docstring,
  `tools/README.md`), the Supervisor spec's first line, the Director spec (§20 pointer),
  `docs/SESSION_INDEX.md` (one line)

- [ ] **Step 1: Back up and delete.** Copy the six Supervisor files into the backup folder, then
delete them. Confirm with `ls` that the backup holds six files.

- [ ] **Step 2: Update references.** Replace each live mention with the Director; "working
consumer of the quick-deal probe" now points at `derpy_director.lua`'s `beat_ask`. Copy
`CLAUDE.md` over `GEMINI.md`'s body as the file says. Run `py tools/gen_tools_index.py`, then
`py tools/gen_tools_index.py --check`. Expected: exit 0.

Run: `grep -rl -E "derpy_coalitions|build_ai_coalitions|derpy_ai_coalitions" . --include=*.md --include=*.py --include=*.lua | grep -v -E "^\./(repos|tools/external|Modding Files/(reference|Backup)|\.remember|anti-slop|\.superpowers|docs/(sessions|superpowers))/"`
Expected: no output.

- [ ] **Step 3: Static checks.**

Run: `py tools/check_lua_api.py "Modding Files/pack/script/campaign/mod/derpy_director.lua"`,
`py tools/check_lua_literal_left.py`, `py tools/check_lua_undeclared.py` on the file,
`py tools/build_director.py --check`, `py tools/build_director.py --selftest`,
`py tools/mutate_director.py`.
Expected: all exit 0, no survivors.

- [ ] **Step 4: Pack.** Run: `py tools/build_director.py`. Expected: `verified: all N files are in
the saved pack`, N now including `script/mct/settings/derpy_director.lua`.

- [ ] **Step 5: Deploy to data with the game shut.** In one command: exit if `tasklist` lists
`Warhammer3.exe`, otherwise back up the `data/` copy to `Modding Files/Backup/director_20261114/`
and copy `Modding Files/Modpacks/derpy_director.pack` over
`F:/SteamLibrary/steamapps/common/Total War WARHAMMER III/data/derpy_director.pack`. Confirm the two
MD5s match and record the new MD5 in `docs/MY_MODS.md`.

---

### Task 9: Live checks 8.2 to 8.4

**Files:**

- Modify: spec §8 (results), `docs/SESSION_INDEX.md`, `docs/MY_MODS.md`
- Possibly modify: `tools/build_director.py` `MCT_OPTIONS` (Chaos Dwarf default), then repack

- [ ] **Step 1: Forced last stand (8.2).** Test prefs on, minimal mod list plus the Director,
new campaign as Karl Franz, soak to turn 11 with the soak helper. Pick a computer Greenskin
faction `v` that has met a larger computer Greenskin faction and is at war with neither. Through
`wh3_eval` in `pcall`: `cm:transfer_region_to_faction` all but one of `v`'s regions to a
non-Greenskin computer faction `x`, then call
`derpy_director:respond{kind = "conquest", instigator = x, victim = v, region = <v's last region>,
turn = cm:model():turn_number(), x = 0, y = 0}`. A script transfer is not a capture by force, so
the situation is raised directly rather than through the event.
Expected in the script log: `merge <kin> absorbs <v> (last_stand)`, `own merge, not a deed`, no
situation answered for the merge, and the game's own confederation message on screen.

- [ ] **Step 2: Chaos Dwarfs and the Tower (8.3).** Same session or a new one as a non-Chaos
Dwarf faction with the lords pack loaded: raise a last stand between two computer Chaos Dwarf
houses the same way. Expected: the merge lands, the Tower of Zharr panel opens with the absorbed
house's seat shown under its new owner, and `zz_derpy_toz_annex` logs nothing for it. If the
Tower is inconsistent, set `race_wh3_dlc23_sc_chd_chaos_dwarfs` default to False in
`MCT_OPTIONS`, re-run Task 8 Steps 3 to 5, and record why.

- [ ] **Step 3: Long soak (8.4).** The 55-turn set-up from the 2026-11-14 soak (Very Hard, lowest
graphics via `py tools/wh3_test_prefs.py --apply --lowest`, the soak helper with the war block and
forced peace). Extend the scratchpad `long_stats.py` to count `merge ... (last_stand)`,
`merge ... (runaway)`, `no merge for` reasons, budget spent on merges, and the number of
factions holding regions per decade. Expected: merges happen in both triggers; the count of
region-holding factions falls faster than in the 2026-11-14 soak.

- [ ] **Step 4: Quit, revert prefs, record.** Quit the game, `--revert` prefs, write the results
under spec §8 and one line in `docs/SESSION_INDEX.md`.
