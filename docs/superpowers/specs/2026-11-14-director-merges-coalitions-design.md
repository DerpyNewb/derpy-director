# The Director absorbs the Coalition Supervisor and decides confederations

Date: 2026-11-14. Status: design, approved by the author 2026-11-14. Builds on
`2026-09-16-ai-director-design.md` (the Director, §19 as built) and supersedes
`2026-09-13-ai-coalition-supervisor-design.md`.

## 1. Intent

The author wants one brain for the campaign world instead of two mods that don't know about each
other. The Coalition Supervisor (`derpy_ai_coalitions`) pushes against a runaway faction; the
Director (`derpy_director`) answers deeds. The Supervisor's job moves into the Director, the
Supervisor is deleted, and the Director gains a new power: it decides when factions confederate.

The why, in the author's words from the same session: when the player gets stronger, the factions
around them, and the world at large, should get smarter and actually build empires. Merging kin
factions is how a fragmented AI world becomes a few real powers that can stand up to a runaway,
whether that runaway is the player, an AI faction or an endgame invasion.

## 2. Goals, non-goals, anti-goals

Goals:

- One script, one budget, one log prefix (`[director]`), one save layout, one test harness.
- Two merge triggers, each behind its own MCT switch: **runaway** (kin of the runaway's victims
  unite) and **last stand** (a dying faction folds into stronger kin).
- By default the brain only merges pairs the game itself allows at that moment. The MCT can turn
  merging off for a race. It can never add a race the game forbids.
- Everything the Supervisor did that still earns its place carries over: the runaway measure, the
  threat score on the leader, the tier-rise grudge and the alliance poll.

Non-goals:

- No override of CA's confederation rules for any race (the author chose "only what the game
  allows" over a per-race override).
- No new event-feed records, no new DB rows. The game's own confederation message already tells
  the player.
- No MCT for the Director's existing knobs (temperament, budget, outrage). Those can come later.
- No special handling of race mechanics beyond what §6.3 lists for the endgame.

Anti-goals, which would make this a failure even if it ran:

- A human faction absorbed, or handed a faction it did not ask for.
- The runaway fed: a merge that makes the faction everyone is uniting against bigger.
- A race's own confederation feature trampled (Vampire Counts, Beastmen's tech, Wood Elves'
  worldroots, the Tower of Zharr).
- The Director answering its own merge as if it were somebody's deed.
- A desync in multiplayer.

## 3. Constraints

- Lua 5.1, CA's 9.0 API. Check every call with `py tools/check_lua_api.py --explain <member>`.
- `cm:force_confederation` is dead for Chaos Dwarfs since the 2026-10-09 patch and crashes when
  both arguments are one faction. Use the payload route, which works for every race and is already
  in production in `zz_derpy_toz_annex.lua` (`confederate()`):
  `p = cm:create_payload()`, `p:form_confederation(absorber, target, false, false)`,
  `cm:apply_payload(p, absorber)`. Faction **interfaces**, not keys. `FactionJoinsConfederation`
  fires **inside** `apply_payload`.
- Every listener callback goes through `guarded()`: since 9.0 one error stops every later callback
  on that event, CA's included.
- Multiplayer reads MCT defaults only. Everything here steers `cm:` writes and
  `cm:random_number`, which must match on every machine.
- Sorted iteration only, never raw `pairs()` over factions, for the same reason.
- The Supervisor was never installed anywhere (built in `Modding Files/Modpacks/` only; not in
  `data/`, any Workshop folder or `used_mods.txt`), so no save carries its state and nothing needs
  migrating.
- Player-facing text (the MCT page) follows the workspace rules: plain spoken English, CA's
  register, no jargon such as "AI", "cap" or "rep".

## 4. Approaches

1. **One brain, one budget. Picked.** The Supervisor's code moves into `derpy_director.lua`. The
   runaway measure and threat score run each turn at no cost, because they are a standing state.
   Confederation is a new Director action with a price, paid from the same budget as everything
   else. The Supervisor's forced alliances run through the Director's pact machinery. Every merge
   has a cause in the log, and the temperaments pace it like everything else. The risk is a busy
   turn spending the budget before a merge; a per-turn cap and an MCT price slider manage that.
2. **One file, a separate allowance for merges.** Merges spend no budget and have their own MCT
   limit. The count is predictable, but two pacing systems sit side by side and the temperaments
   do not shape merges.
3. **Move the Supervisor unchanged into the Director's pack.** The smallest change, but two
   scripts that don't know about each other, two logs and two saves. Not a merge.

The author picked 1 because it is the only one where a single brain decides.

## 5. Decided in conversation

- Both triggers, runaway and last stand, each with its own MCT switch.
- Lore by default means "only what the game allows right now", read through CA's own deal probe
  (§6.4). No per-race override.
- Approach 1.
- Proposed and not objected to: a CA endgame invader counts as a runaway from the turn it
  appears, not only once it leads in regions (§6.3).
- Proposed and not objected to: a human is never absorbed and is never handed a faction.
- Chaos Dwarf houses never merge while a human plays Chaos Dwarfs (§6.4). If the live Tower
  check (§8.3) fails, Chaos Dwarfs become off by default through their race switch; the lords
  pack's annex script is not changed.

## 6. Design

### 6.1 What moves from the Supervisor

| Supervisor part | In the Director |
| --- | --- |
| `measure()`: leader by region count against the runner-up | Kept as is |
| `rung_for()`: tiers at ratio 1.75 / 2.5 / 4.0, `MIN_REGIONS` 10, exit 1.35, hold at the minimum active tier | Kept, **renamed to tier** throughout code, logs and tests (the author bans the word "rung") |
| Threat score 200 / 350 / 500 on the leader, released to 0, carrier saved by key, re-applied once after a load | Kept as is, free of charge. Behind MCT `runaway_threat` |
| Past event `PAST_EVENT_NEGATIVE_MINOR`, leader to each polled faction, only when the tier rises | Kept as is, free of charge (bounded at three rises per runaway, and the Supervisor's rulings say re-firing piles up damage with no inverse) |
| Alliance poll: pairs that met the leader and each other, 8 pairs a turn, a cursor, at most 2 forced alliances per faction, humans never candidates | Kept, but each ask goes through the Director's `beat_ask` / `at_odds` / `beat_force`, forms on the **sum** rule pacts use (both-positive never opened in about 50 live asks), costs `PRICE.force`, and forms at most **2 a turn**. Behind MCT `runaway_alliances` |
| Global AI context slot `special_1` | **Dropped.** The Director spec §12 already ruled it out: the slot is process-global, not save-scoped, and CA's "AI extra aggro" option shares it |
| `save_named_value` with `first_callback` | Replaced by the Director's `cm:set_saved_value` style, one table `derpy_director_runaway` |
| `WorldStartRound` listener of its own | A step in the Director's existing turn-start listener |

Director test 9 currently asserts that no `set_base_strategic_threat_score` call happens, because
it collided with the Supervisor. It becomes: the call happens only from the runaway step and only
on the faction that holds the score.

### 6.2 The turn-start step

Inside the existing `derpy_director_refill` listener, after `refill()` and before
`opportunity()`: measure the leader, set or release the threat score, fire the tier-rise past
event, run the alliance poll. Same logic and same hysteresis as the Supervisor's `tick()`,
including the "no runner-up" release path (its FIX5).

### 6.3 Who counts as a runaway

`is_runaway(key)` is true when either holds:

- `key` is the measured leader and its tier is at least MCT `runaway_merge_tier` (default 1).
- `key` is a CA endgame invader:
  - `wh3_dlc29_chaos_invasion_confederation_owner` (Archaon's End Times invasion),
  - `wh3_dlc29_vermintide_confederation_owner` (the Vermintide),
  - `wh3_dlc29_nag_host_of_nagash`, only while CA's script state `episode_nagash_endgame` is true
    (Nagash's faction is otherwise an ordinary, possibly playable faction),
  - any faction carrying one of the Ultimate Crisis bundles:
    `wh3_main_ie_scripted_endgame_grudge_too_far`, `..._vampires_rise`, `..._waaagh`,
    `..._wild_hunt`, `wh3_dlc23_ie_scripted_endgame_faction_chaos_dwarfs_hashut`.

The keys are read from CA's 9.0 scripts (`episodes/episode_chaos_invasion.lua:11`,
`episode_vermintide.lua:10`, `episode_nagash_endgame.lua:6,28`, `crisis/*.lua`). Invaders get no
threat score (all their diplomacy is locked anyway); they count only for merge decisions.

### 6.4 Merges

**The legality check.** A pair may merge only when
`cm:cai_evaluate_quick_deal_action(a, b, "diplomatic_option_confederation")` returns
`ok = true` in **both** directions (`diplomatic_option_confederation` is in
`diplomacy_quick_deal_offers`, read from db.pack). That flag is CA's "the engine would propose
this deal", which should reflect the DB table, the per-race script locks and CA's 10-turn
post-confederation timeout. **This is unverified and is the first live check (§8).** Both scores
are logged on every ask. By default they are not required; MCT `merge_needs_willing` (off) adds
the pact rule, score sum above zero.

**Hard exclusions**, checked in our code before any probe, whatever the probe says:

- either side human, dead or a rebel faction;
- either side an endgame invader (§6.3);
- the absorber is a runaway, or a vassal, master, military ally or defensive ally of one (never
  feed the runaway or its bloc, in either trigger);
- either side is a vassal of any faction, or the master of a human's vassal (a vassal is part of
  its master's realm, and the probe's and the payload's handling of vassalage is unmeasured);
- either side has risen in an Iron Court secession: `on_secession()` records the rebels' key in
  a saved set, `derpy_director_risings`, and they stay excluded for the rest of the campaign.
  This covers the qb pool factions and a dead house woken to host a rising alike, which would
  otherwise pass the rebel check and let a merge hand the rising's provinces to another house;
- either side is a Chaos Dwarf faction (`wh3_dlc23_sc_chd_chaos_dwarfs`) while any human plays a
  Chaos Dwarf faction. With the lords pack the player absorbs houses by claiming their Tower of
  Zharr seats, and every Director merge would remove one of those targets. This mirrors CA's
  own rule for Dwarfs and High Elves in `wh_campaign_setup.lua`, which blocks confederation
  between their legendary-lord factions while a human plays that race. An all-computer Chaos
  Dwarf world can still consolidate;
- the absorber is the situation's instigator;
- the two are at war with each other;
- the two are of different subcultures (kin only; CA's table is per subculture);
- the subculture's MCT race switch is off;
- the turn is before MCT `merge_from_turn` (default 10).

**Last stand** (MCT `merge_last_stand`, default on). On a `conquest` or `raze` situation, when the
victim is a computer faction and now holds MCT `last_stand_regions` (default 1) regions or fewer,
including none: rank its kin by region count (most first, ties by key), take those that have met
the victim and pass the exclusions, and probe them in order, at most 3. The first legal one
absorbs the victim. This runs **before the feud guard and without the chance roll**: a province
taken in one turn reports one event per town and the feud guard drops all but the first, so a
gated last stand would miss a faction that lost its last towns together. It still pays the price
and counts toward the per-turn limit, and it fires at most once per victim per turn.

**Runaway** (MCT `merge_runaway`, default on). On an answered `sack`, `raze` or `conquest`
situation (after `chosen()`) whose instigator `is_runaway`, when the victim is a computer
faction: rank the victim's kin the
same way, probe at most 3, and merge the victim with the first legal one. The one with more
regions absorbs the other (ties by key). If the last stand already merged the victim this
situation, skip. The other kinds are left out on purpose: opportunism reverses the roles (its
instigator is the faction that LOST ground, so an invader losing a town would merge whoever beat
it), a confederation's victim is already absorbed, and treachery, seizure and secession are not
the runaway taking land.

The per-turn slot and the price are charged only once a legal partner has been found, so a
victim with no willing kin costs nothing.

**Price and limits.** `PRICE.merge` 60 (MCT `merge_price`, 0 to 180), paid through `afford()`.
At most MCT `merges_per_turn` (default 1, 0 to 3) merges in the whole world per turn, tracked the
way `grudge_slot()` tracks grudges. In the answered path the merge comes **first**, before the
cast, so the rest of the beats take what is left: it is the rarest and largest action.

**The call.** The payload route from §3, inside `pcall`. Before `apply_payload`, set a session
flag naming the pair; `from_confederation` drops a confederation that matches it with the log line
`own merge, not a deed`, then clears it. Without this the Director would answer its own merge as
kin-slaying (outrage 1.5) on the spot, since the event fires inside the call.

### 6.5 MCT

A new page, `script/mct/settings/derpy_director.lua`, mod key `derpy_director`, and a reader in
`derpy_director.lua` modelled on `derpy_hll_settings.lua`'s `read_mct`: type-checked, defaults in
multiplayer, read live at each use (a change takes effect at the next read), never at file load.
One defaults table in the Lua is the source; `build_director.py` checks that the page's keys and
defaults match it, by running both under Lua 5.1 the way `tools/check_hll_settings.py` does.

| Key | Kind | Default | Section |
| --- | --- | --- | --- |
| `merge_last_stand` | checkbox | on | Merging |
| `merge_runaway` | checkbox | on | Merging |
| `last_stand_regions` | slider 1-5 | 1 | Merging |
| `runaway_merge_tier` | slider 1-3 | 1 | Merging |
| `merge_price` | slider 0-180 | 60 | Merging |
| `merges_per_turn` | slider 0-3 | 1 | Merging |
| `merge_from_turn` | slider 1-100 | 10 | Merging |
| `merge_needs_willing` | checkbox | off | Merging |
| `race_<subculture>` | checkbox each | on | Races that may merge |
| `runaway_threat` | checkbox | on | Runaway |
| `runaway_alliances` | checkbox | on | Runaway |
| `runaway_min_regions` | slider 5-40 | 10 | Runaway |

The race list is generated by `build_director.py` from db.pack's
`diplomatic_action_subculture_restrictions`: every subculture **not** marked false there, with
its display name from CA's loc. Subcultures absent from that table (Chaos Dwarfs, Vampire Coast)
are included, since absence is not a ban; the live probe settles them. The generator writes the
list into both the page and the reader's defaults so the two cannot drift.

### 6.6 Persistence

All through `cm:set_saved_value`: `derpy_director_runaway` = `{tier, scored_key, cursor,
alliances, last_event_tier}`, plus `derpy_director_merge_turn` / `_merge_count` for the per-turn
limit. The re-apply-after-load flag is session state set in `first_tick()`, as the Supervisor's
`loaded` was.

### 6.7 Log lines

Designed before the feature, as the Director spec requires, so a soak can be read by script:

```text
runaway turn=%d leader=%s regions=%d runner_up=%d ratio=%.2f tier=%d
threat score %d on %s / threat score released on %s
merge ask %s<->%s %s/%s ok=%s/%s
merge %s absorbs %s (%s)            -- last_stand | runaway
no merge for %s: %s                 -- the reason: no kin, all refused, limit, price, switched off
own merge, not a deed: %s + %s
```

### 6.8 Deleting the Supervisor

Back up first to `Modding Files/Backup/director_20261114/coalitions/`, then:

- delete `Modding Files/pack/script/campaign/mod/derpy_ai_coalitions.lua`,
  `Modding Files/Modpacks/derpy_ai_coalitions.pack` and its four `.bak_*` siblings, and
  `tools/build_ai_coalitions.py`;
- update every live reference: `CLAUDE.md` and its copy `GEMINI.md`, `Modding Files/CLAUDE.md`,
  `docs/MY_MODS.md`, `docs/DIPLOMACY.md` and `docs/CAMPAIGN_AI.md` (both name the Supervisor as
  the working consumer of the quick-deal probe), `docs/MODDING_TOOLS.md`, the four
  `docs/knowledge-base/` files, `.agents/skills/pack-build/SKILL.md` and
  `.agents/skills/test-harness/SKILL.md`, `tools/build_no_early_wars.py`'s docstring, the
  comment on `beat_stance` in `derpy_director.lua`, and `tools/README.md` (regenerate with
  `py tools/gen_tools_index.py`);
- leave history alone: the Supervisor's spec gets one "superseded by" line at the top, its
  handoffs stay, and nothing under `Modding Files/Backup/`, `.superpowers/` or the Mod Manager's
  config backups is touched;
- one line in `docs/SESSION_INDEX.md`, and a §20 pointer in the Director spec.

## 7. Testing

`tools/build_director.py --selftest` runs the shipped Lua under Lua 5.1.5. New stubs:
`set_base_strategic_threat_score`, `factions_met`, `defensive_allies_with`,
`military_allies_with`, `has_effect_bundle`, the script-state getter, the confederation deal type
in `cai_evaluate_quick_deal_action`, `create_payload` / `form_confederation` / `apply_payload`
(recorded, and firing `FactionJoinsConfederation` synchronously so the self-suppression is tested
for real), `get_mct` with options, and `cm:is_multiplayer`.

Ported from the Supervisor's selftest: tier boundaries and hysteresis (its 1-3b), score placement,
release and carrier (4-5c), both directions asked (6), met-only pairs (6b), determinism (7),
per-faction alliance limit (8), never re-forcing (9-9b), humans never candidates (9c), the
past event's order, once per faction per turn and only on a rise (12-12c), and total conquest
releasing the score (11e's score half). The context-slot tests (10-11d) are dropped with the slot.

New, each written to fail if its rule is deleted:

- last stand fires at the threshold and not one region above it; at zero regions too;
- the absorber is the largest legal kin; a runaway, the runaway's vassal or ally, a human, a
  vassal, the instigator, an invader, an Iron Court rising, a faction at war with the victim and
  a faction of another subculture are each skipped;
- the runaway merge ignores opportunism, confederation, treachery, seizure and secession;
- two computer Chaos Dwarf houses merge with no human Chaos Dwarf in the game, and do not when
  one human plays any Chaos Dwarf faction;
- a probe `ok=false` in either direction blocks the merge; scores are ignored unless
  `merge_needs_willing`;
- a race switch off blocks it; `merge_from_turn` blocks it; the per-turn limit blocks the second;
  the price is paid, and an empty budget blocks it;
- the last stand runs on the second town of a feud the guard already answered;
- the runaway merge fires only when the instigator `is_runaway`, both for the leader at the tier
  setting and for each invader kind, and the larger side absorbs;
- the Director does not answer its own merge, and does answer a confederation it did not cause;
- multiplayer reads defaults whatever MCT holds; a wrong-typed MCT value falls back;
- the MCT page and the reader agree on every key and default.

`tools/mutate_director.py` gets a mutant for each new rule, aimed at the shipped Lua; the run must
end with no survivors.

## 8. Live checks before shipping

1. **The probe honours CA's locks (gate).** In a live campaign, probe two Vampire Counts factions
   (CA locks them culture-wide), two Greenskin factions (allowed), and a pair one turn after a
   confederation (CA's 10-turn timeout). Expected `ok=false`, `ok=true`, `ok=false`. If the probe
   ignores CA's script locks, stop and bring it back to the author: "only what the game allows"
   would then need our own reading of CA's locks, which is a different build.

   **Passed, 2026-11-14** (Astragoth turn-1 fixture, bridge and intro skip only, turn 1):
   Vampire Counts (Barrow Legion, Mousillon) `0/0 ok=false/false`; Greenskins (Bonerattlaz,
   Slaves of Zharr) `-90.5/-181.6 ok=true/true`; Dwarfs (Clan Helhein, Karak Azul)
   `-118.4/-85.6 ok=true/true`; Chaos Dwarfs (Conclave, Legion of Azgorh) `0/0 ok=false/false`
   with Astragoth human. The payload merged Bonerattlaz into Slaves of Zharr (`form=true`, the
   absorbed faction dead at once), and the absorber against Drippin' Fangs then read
   `ok=false/true`: CA's 10-turn lock stops the absorber proposing, so the both-directions rule
   blocks it. Every score was far below zero, which is why merges must not require willingness
   by default.
2. A forced last stand on a fixture: the merge lands, the log shows `own merge, not a deed`, and
   the game's own confederation message appears.
3. Chaos Dwarfs: a Director merge of two computer Chaos Dwarf houses must leave the Tower of Zharr
   consistent. CA's `wh3_dlc23_campaign_chd_tower_of_zharr.lua:557` hands seats over on any
   confederation, and the lords pack's `zz_derpy_toz_annex.lua` also listens for
   `FactionJoinsConfederation`; confirm it ignores a merge it did not start. Run it with no human
   Chaos Dwarf, since a human one blocks the merge. If the Tower is left inconsistent, the
   `race_wh3_dlc23_sc_chd_chaos_dwarfs` switch defaults to off; the lords pack is not changed.
4. A long soak with the usual set-up (`docs/LIVE_TESTING.md`, the player kept out of wars):
   merges per decade by trigger, budget spent on merges, and whether the world consolidates into
   fewer, larger powers by turn 50.

**Checks 2 to 4, 2026-11-14 evening.** One launch: intro skip, bridge, the Director (MD5
`6c32ce9b`), the lords pack with its asset pack, and MCT. New Immortal Empires campaign as Karl
Franz on Very Hard, lowest graphics, the soak helper with the player shield, and war on the
player blocked with peace forced every turn. 56 turns, then the forced checks on that world.

- **MCT:** the page registers with all 34 options, and the Director reads them through it
  (`merge_price` 60, the Chaos Dwarf switch on).
- **Check 4, the soak:** 8 confederations in 55 turns, all last stands (turns 15, 17, 19, 24,
  39, 43, 46, 53), 480 of the budget spent on them. Examples: Clan Eshin took in Clan Krizzor,
  the Dwarfs took in Karak Kadrin, and Hag Graef took in Naggarond. Every one logged `own merge,
  not a deed`, and none was answered as a situation. Factions holding a region: 176 at turn 11,
  134 at 21, 109 at 31, 90 at 41, 79 at 51 and 75 at 56. The 2026-11-14 morning soak kept no
  such count, so the comparison the plan asked for cannot be made. **No runaway merge**: the
  largest lead was 29 regions against 19 (ratio 1.53, tier 0), and no endgame invader spawned,
  so the runaway half is tested offline only. Refusals: 170 too early (merges start at turn 10),
  118 budget too low (last stands come about 18 a turn, and earlier answers in the turn have
  spent the budget), 36 no kin, 18 slot spent. No script error from the Director or the lords
  pack; the 49 tracebacks in the log are CA's own warnings.
- **Check 2, the forced last stand:** the Lizardmen's Tlaqua folded into the Last Defenders
  (`merge ask ... ok=true/true`, scores near -150), and Argwylon into Orion's Talsyn. The log
  showed `own merge, not a deed` each time, and the game's own **Confederation** event appeared
  for Talsyn and Argwylon, the pair the player had met. A third last stand the same turn was
  refused with "this turn's confederations are spent".
- **Check 3, Chaos Dwarfs:** with no human Chaos Dwarf, Zhatan and the Conclave both read
  `ok=false/false` for taking Astragoth in, and Vampire Coast reads the same. Neither CA's scripts
  nor the lords pack lock it, so the game itself refuses AI confederation for both races (Chaos
  Dwarf houses join only through the Tower's tier-four seats). The Director therefore never
  merges Chaos Dwarf houses, and their switch does nothing while that holds; its tooltip already
  says the game's own rules apply. The Tower would cope anyway: CA's script has no confederation
  listener and frees a dead owner's seat for claiming (lines 511 and 519), and
  `zz_derpy_toz_annex` resolves only the grants it set itself. The switch stays on by default.
- **A bug found:** the per-turn merge count was read after the turn was written, so it ran on
  from turn to turn (it read 8 on turn 53). It made no difference at the default of one merge a
  turn, but with `merges_per_turn` at 2 or more, every turn after the first one with a merge
  allowed only one. Fixed with a test that failed first, and a mutant for it.
- **Final review fixes**, each with a test that failed first and a mutant:
  - A measured runaway below the merge-trigger tier could still take in a dying faction. Only
    the trigger now reads that setting; the rule that never feeds a runaway uses tier 1.
  - Switching the threat score off mid-campaign now lifts a held score the next turn.
  - A tier rise with no pair to poll now keeps its grudge for the first turn a pair has met, as
    the Supervisor did.
  - The race switches and the per-turn and first-turn tooltips now say they govern the
    Director's confederations only, not the game's own diplomacy.

## 9. Risks

- The legality probe may not see CA's script locks (§8.1). Everything in "lore by default" rests
  on it.
- Merges are strong. With the defaults, at most one a turn, from turn 10, at 60 of a 180 budget.
  The soak decides whether that is too many or too few.
- The runaway tiers above 1 have never fired in game (highest measured ratio 2.00 over 85
  Supervisor turns), so `runaway_merge_tier` above 1 may mean "never".
- Region count is the only strength measure, so a horde never counts as the leader. Invaders are
  covered by §6.3 instead.

## 10. Left to the builder

Function names, the exact log wording within §6.7's shape, how the turn-start steps are ordered
around `opportunity()`, the MCT tooltip text (within the player-text rules), where the subculture
display names come from in CA's loc, and how the harness fixtures are laid out.

## 11. Calls made by the designer, for the author to check

- The global AI context slot is dropped, not carried over.
- The tier-rise past event and the threat score stay free; alliances and merges are priced.
- The alliance poll forms at most 2 alliances a turn and uses the pact sum rule.
- Merges ignore the AI's willingness by default, with an MCT switch to require it.
- The last stand skips the chance roll and the feud guard; the runaway merge does not.
- A merge comes before the cast in an answered situation.
- Defaults: price 60, one merge a turn world-wide, none before turn 10, last stand at 1 region,
  runaway merges from tier 1.
- The runaway never absorbs anyone, in either trigger, and neither do its vassals or allies.
- Vassals never merge, on either side.
- Iron Court risings never merge.
- Runaway merges answer sacks, razes and conquests only.
- A merge is charged only once a legal partner is found.
- MCT is read live in single player, never frozen into the save.
- No new event-feed records.
