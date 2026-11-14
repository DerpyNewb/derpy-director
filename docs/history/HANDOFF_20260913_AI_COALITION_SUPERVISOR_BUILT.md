# HANDOFF 2026-09-13 — the Coalition Supervisor, built

`HANDOFF_20260913_AI_GAPS_AND_COALITIONS.md` §5 described a design and said **nothing built**.
It is now built, checked and packed. Nothing is deployed and nothing has been played.

## 1. What shipped

| File | What |
|---|---|
| `Modding Files/pack/script/campaign/mod/derpy_ai_coalitions.lua` | 314 lines, the whole mod. **Zero DB rows** |
| `tools/build_ai_coalitions.py` | 615 lines. `--selftest` runs the shipped Lua under Lua 5.1.5 against a stubbed `cm`/world and reads back every recorded call; no flag packs `derpy_ai_coalitions.pack` through RPFM |
| `Modding Files/Modpacks/derpy_ai_coalitions.pack` | 13,140 B, in-pack path `script/campaign/mod/derpy_ai_coalitions.lua`, type `Mod`. Two `.bak_` copies beside it are earlier builds |
| `docs/superpowers/specs/2026-09-13-ai-coalition-supervisor-design.md` | the spec, amended four times during execution (see A9, A12/A13, A14) |
| `docs/superpowers/plans/2026-09-13-ai-coalition-supervisor.md` | the plan, all 30 boxes ticked |

Global table `derpy_coalitions`, not `coalitions` — a mod whose whole point is composing with
other mods must not squat a generic global.

Constants, all at the top of the Lua: `ENABLED=true`, `MIN_REGIONS=10`,
`RUNG_RATIOS={1.75, 2.5, 4.0}`, `EXIT_RATIO=1.35`, `RUNG_SCORES={200, 350, 500}`,
`POLL_PAIRS=8`, `MAX_FORCED_ALLIANCES=2`, `CLAIM_CONTEXT=true`,
`PAST_EVENT="PAST_EVENT_NEGATIVE_MINOR"`.

## 2. The check

```powershell
py tools\build_ai_coalitions.py --selftest
```

Six lines, exit 0: rung logic / threat score / coalition polling / context slot and past event /
persistence / off switch, no-loc and static checks. It runs the **shipped artifact**, not a copy —
the `gen_victory_routes.py` pattern. `py tools\build_ai_coalitions.py` with no flag runs the
selftest first and refuses to pack if it fails (reproduced deliberately with a scratch break).

## 3. Rulings made during execution

Eighteen, recorded as they were made with the cost if wrong. The final whole-branch review agreed
with fourteen of the fifteen it could see and **reopened A11**, correctly — see A16.

**Adapting the skill to this workspace**

- **Not a git repo**, so no worktree, no commits, and the skill's `sdd-workspace` / `task-brief` /
  `review-package` scripts all fail. Substituted a scratchpad workspace, briefs split locally out
  of the plan, and review packages built as `diff -u` between per-task file snapshots.
- Implementers and task reviewers on sonnet, the final whole-branch review on opus. The plan
  carried complete code, which argues for the cheapest tier, but this environment's traps (paths
  with spaces, the `py` launcher, PowerShell vs bash) cost a cheap model turns.

**Pre-flight, before Task 1**

- **A1** — the harness registered the save/load callbacks and never invoked them, so every state
  assertion would have read the string `"nil"` and every `preload=` would have been ignored: tests
  passing for the wrong reason. Amended to call the loader before the turn loop and the saver
  after it.
- **A2** — Task 2's release test restored a rung from a save, but the loading callback was not
  written until Task 5. The test could not express what it was testing. Moved `load` and its
  registration into Task 2.
- **A3** — Task 1's Interfaces block promised a 2-tuple from `run_lua` while its own code returned
  three. Corrected the prose.

**During execution**

- **A4 (rejected an implementer's fix)** — the implementer found, by running the test, that
  `apply_threat`'s release branch can never fire after a load because `load` wiped `scored_key`.
  Real defect, wrong fix: it fell back to `leader:name()`, which releases whoever leads *now*, so a
  runaway beaten while the save sat would keep its -30 forever while an innocent faction was
  zeroed. Replaced with restoring `scored_key` from the save plus a one-shot `loaded` flag.
- **A5 (pre-emptive)** — the plan's `pack()` called `get_packed_files_info` with a ContainerPath,
  copying its neighbours. The live schema takes `values`, a list of plain strings — the one call in
  that function that does not use ContainerPath. Checked the other four packing calls at the same
  time; all correct as written.
- **A6** — on a **leader swap**, `apply_threat` scored the new leader and overwrote `scored_key`
  without releasing the previous carrier, leaving a permanent -30 that nothing ever revisited.
  Extracted `release_threat()` and released the old carrier before scoring the new one.
- **A7** — Task 3's brief quoted the pre-A4/A6 `tick` condition in a "replace these lines" step, so
  a verbatim paste would have silently reverted both rulings. Amended to insert one line instead.
- **A8** — the harness's `defensive_allies_with` stub was static, so a pair allied by
  `force_alliance` earlier in the same run still read as unallied. The stub was more permissive
  than the engine, and the assertion "an existing alliance is never re-forced" could not catch a
  real re-force. Made `force_alliance` mutate both stub factions' ally sets.
- **A9** — **the human player is excluded from candidacy.** The spec's "player is included" is
  about who can be the measured *leader*. `cai_evaluate_quick_deal_action` asks what the campaign
  AI would accept and a human faction has no AI to ask; `cm:force_alliance` is unrefusable, so
  conscripting a player into an alliance they never agreed to is the largest intrusion available
  here and nothing authorises it. A runaway human still draws the threat score and still has
  coalitions formed against them.
- **A10** — `claim_context(true)` returned early on a believed-true flag without asking the engine.
  After a load that belief can be stale, and the harmful direction is the release:
  `cai_clear_global_script_context` clears whatever is in the single global slot, not "ours". Now
  verified against `cai_get_global_script_context()` in both directions.
- **A11** — the past event fired once per polled **pair** (up to 8 a turn) where the spec says once
  per polled **faction**. Moved out of `consider` into `poll`. Incomplete — see A16.
- **A12** — the `CLAIM_CONTEXT` flag gated both the claim and the release, so switching it off
  after a claim held the single global slot forever. It now gates only the claim; if it is false
  and we own the slot, the code forces `want=false` and falls through to the live-checked release.
- **A13** — the `ENABLED` leak is **spec-mandated and stands**. Off makes zero calls, deliberately,
  because a disabled mod that still calls into the AI every turn to check for cleanup is the worse
  failure. Parked openly: spec §10 now names the context slot, says a leaked claim blocks other
  mods for the life of that save, and gives the clean reset procedure.
- **A14a** — assertion 15's literal form (`calls == []`) was wrong and the implementer was right to
  rewrite it. `disable=True` leaves exactly one call, the load callback's own log line, because the
  save/load callbacks stay registered unconditionally — and that is load-bearing: if `load` were
  gated off too, a disabled mod would restore nothing and its save would then overwrite the stored
  rung, context ownership and carrier that the reset procedure depends on.
- **A14b** — `new_pack`'s return shape is `["String"]`, verified against the live server and four
  existing `tools/*.py` precedents, not the defensive both-shapes guess in the plan.
- **A15** — the pack verification asserted a substring in a JSON dump rather than a structural
  match on the path field. That is the "a byte-grep is not proof" standard this workspace already
  holds, and verification is the one step in `pack()` that cannot be approximate. Now structural;
  an absent path returns `{"VecRFileInfo": []}`, so the check discriminates on its own rather than
  riding on the error guard.

**From the final whole-branch review**

- **A16 (A11 reopened)** — per-pair to per-faction fixed the within-turn dose and left per-**turn**
  repetition unbounded: up to 16 events a turn, every turn the rung held. Unlike the threat score
  and the context slot, **the past event has no inverse** — when the runaway stops running away the
  accumulated attitude damage stays for the campaign. It now fires only when the rung **enters or
  increases**, bounding it to at most three rounds per faction per campaign. Measured: five steady
  turns at rung 3 went from 10 events to 2. Rejected the alternative (a fire-every-N-turns cadence)
  because it still accumulates without bound over 200 turns.
- **A17** — `rung_for`'s hysteresis held the *previous* rung inside the band, so ratio 1.5 held
  rung 3 (-30) while ratio 1.8 computed rung 1 (-10): a leader punished harder for being less
  dominant. It holds at the minimum active rung now.
- **A18** — the "rebuilds C(n,2) pairs every turn" finding taken **partially**. Caching `f:name()`
  once removes O(n log n) *engine* calls from the sort comparator, which is the real cost. The
  virtual-pair-index refactor is declined: it trades an obvious loop for triangular-number
  arithmetic and an off-by-one risk in the cursor, to save table allocations Lua handles cheaply.
  Revisit only if a soak shows turn-time pain.

## 4. Accepted residuals

- **One extra past event on upgrade.** A save already parked at a steady rung fires one extra
  `PAST_EVENT_NEGATIVE_MINOR` on the first tick after the mod is updated, because
  `last_event_rung` defaults to 0 for a save written before that field existed. 0 is the lowest
  value, so it can only ever over-notify once and can never suppress. The alternative default
  (`self.rung`) would trade that for a migration path that silently swallows a real escalation.
- **The quick-deal stub always returns ok=true**, so `consider`'s nil/ok guard is present but
  unexercised by any assertion.
- **A rejected pair carries no memory**, so the rotating cursor re-asks it whenever it recurs.
  Already-allied pairs are filtered before any AI call, so this is scoped to rejected-not-allied
  pairs.
- **Assertion 16's loc ban list** is three names, two of them substrings of the third, and it
  catches that literal spelling only.
- Two builds inside one wall-clock second reuse one `.bak_` stamp (house convention, pre-existing).

## 5. Still open

1. **Not deployed.** Copy `Modding Files/Modpacks/derpy_ai_coalitions.pack` to
   `F:\SteamLibrary\steamapps\common\Total War WARHAMMER III\data\`. It will be listed but
   **unticked** — see [[wh3-new-pack-in-data-starts-disabled]].
2. **The `(from, to)` argument order of `cai_add_diplomatic_event` is still unsettled.** The mod
   logs its argument rather than assuming, so 10-15 turns with the log open settles it. This is the
   one thing a soak is needed for beyond tuning.
3. **The thresholds are still guesses.** 1.75 / 2.5 / 4.0, 10 regions, 8 pairs, cap 2.
   `CAMPAIGN_AI.md` §9 is the standing warning: CA ran thousands of overnight AI-vs-AI games and
   still shipped a defend-priority tuned wrong. Every number here is one constant at the top of the
   Lua.
4. **The DB layer was deliberately not bought** (option C). The `call_to_arms_chance_*` and
   `war_coordination_assist_attack_*_max_distance` columns that no script call can reach are the
   upgrade path, and `HANDOFF_20260913_AI_GAPS_AND_COALITIONS.md` §4 records that Hecleas' AI
   Overhaul leaves them alone. Buy them only if a soak shows blocs forming while allied armies
   still fight alone.

---

# 2026-09-16 — first soak read, and two patches

Deployed 2026-09-13, played since. 44 sessions of `script_log_*.txt` read, 2026-09-13 to
2026-09-16. **Zero `[coalitions] error:` lines** — the `pcall` in `turn()` never caught anything
across 85 supervised turns. Tick cost is under 0.1s (the turn line and its follow-ups share a
timestamp), so §3 A18's "revisit only if a soak shows turn-time pain" stays closed.

## 6. What the soak measured

| Layer | Reading |
|---|---|
| Threat score | 26 turns at rung 1 (score 200), 59 at rung 0. Releases and re-applies on load as designed |
| Past event | Fired once per campaign, 9 factions, on rung entry. A16 holds — never re-fired on a holding rung |
| Forced alliances | **Zero, ever. ~50 asks, every result at or below zero** |

Max ratio ever measured is **2.00**, so `RUNG_RATIOS` 2.5 and 4.0 have never been reached and
rungs 2 and 3 are untested in game. The leader was the human player (`wh3_dlc23_chd_conclave`)
in every campaign but four; A9 held, the player drew the score and was never conscripted.

Sample refusals, which are not marginal: `cr_chd_skullstack<->cr_hef_the_starguided -97.4/-44.0`,
`cr_cth_sanyo_clan<->wh_main_emp_wissenland -26.9/3.9`. Three pairs scored `0/0`, all of them
Chaos, Norsca or Greenskin — which reads like "the deal is not legal" rather than "the AI is
neutral", and the log could not tell the two apart. Hence patch 1.

## 7. Patched

**1. The ask line logs the can-propose flags** (`ok=%s/%s`). §4's residual "the quick-deal stub
always returns ok=true, so the guard is unexercised" is unchanged — this is about the *live* log,
which is where the open question above gets settled. Cost of not having it: fifty asks that
cannot be diagnosed.

**2. The pair list is filtered to factions that have MET each other, before the cursor.** This is
the finding the soak actually bought. The met test used to live in `consider()`, so the cursor
spent its budget on pairs it then dropped without asking: **a measured turn polled 8 pairs and
asked 2**, and after 61 turns the cursor had reached index 168 of a list running to four figures,
never once leaving the candidates whose keys sort first — every ask in 44 sessions came from
four proposers, all `cr_chd_*` / `cr_chs_*` / `cr_cth_*`. `candidates()` now returns sorted
entries `{faction, name, met}` and `poll()` pairs on the met set, which also takes `:name()` out
of the O(n^2) loop. It is the same shape as A18's cached-name ruling, one level up.

This is *not* A18's declined virtual-pair-index refactor. The cursor arithmetic is untouched; the
list it walks is shorter and every entry in it is askable.

**Deliberately not patched: `claim_context`'s "already held by ..., skipping" branch.** It was
reached once (`script_log_150926_1314.txt:8792`, turn 44, a fresh campaign whose slot still held
`special_1` from the previous campaign in the same process — the slot is **process-global, not
save-scoped**). In that state `owns_context` stays false and `claim_context(false)` can never
release, so our key sits in the slot for that campaign. Adopting it looks like the fix and is not:
A10's whole point is that CA's own "AI extra aggro" option writes `special_1` too, so adopting
would mean clearing CA's setting on rung exit. The slot cannot tell us who wrote it. Skipping is
the safe side of an ambiguity with no resolution available, and A13's spec §10 reset procedure
already covers the leak.

**Deliberately not patched: §4's "a rejected pair carries no memory".** Re-asking is correct —
attitudes move, and a pair that refuses at turn 40 may accept at turn 90.

## 8. The check

`tools/build_ai_coalitions.py` selftest 6 gains one assertion (the ask line carries `ok=`) and a
new **6b**: nine `far*` candidates that met only the leader, plus `near_a`/`near_b` who met each
other. Sorted, the only askable pair lands at index 54 of the unfiltered C(11,2) list, so a
`POLL_PAIRS=8` budget from cursor 0 never reaches it. **Both new assertions were run against the
pre-patch Lua extracted from the deployed pack and both failed** — 6b with "the one askable pair
was never reached", which is the live log's behaviour reproduced in the harness. Six lines, exit 0
after the patch.

## 9. State

Built and **deployed 2026-09-16 17:21**: `Modding Files/Modpacks/derpy_ai_coalitions.pack`
(13,866 B of Lua, `.bak_` beside it) copied to `data/`, and the in-pack Lua byte-compared against
the staged file **read back out of the deployed pack**, not off the staging copy. Still not on the
Workshop. §5.1 is closed; §5.2 (`cai_add_diplomatic_event`'s `(from, to)` direction) and §5.3
(every threshold a guess, now with 2.00 as the highest ratio ever seen) stay open, and §5.4's DB
layer is the upgrade path if the wider sweep still forms no blocs.

**No turn has been played with either patch in.** The next soak answers one question: with the
budget spent on askable pairs, does any pair ever come back positive/positive? If the `ok=` flags
come back false in bulk instead, the deal type itself is the wrong lever and layer 2 should be
withdrawn rather than tuned.
