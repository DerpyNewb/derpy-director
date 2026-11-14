# The Director — design

Status: **approved in chat 2026-09-16, nothing built.** Supersedes nothing; it absorbs
`2026-09-13-ai-coalition-supervisor-design.md`, whose whole feature becomes one scenario in §9.

Read `docs/sessions/HANDOFF_20260916_COALITION_SOAK_AND_AI_DIRECTOR_RESEARCH.md` first. Every
measured number in this spec comes from there, and §2 of that handoff lists the corrections that
were found the hard way. Read `HANDOFF_20260913_AI_COALITION_SUPERVISOR_BUILT.md` §3 before
touching any behaviour the Coalition Supervisor already has: eighteen rulings, and **the past
diplomatic event is the one lever with no inverse**.

## 1. Purpose

Make the world react to what the player does, across diplomacy and economics, friendly and
destructive — not war alone. The campaign AI has no central brain to persuade, so the Director does
not try to persuade it. It watches for situations, decides who would plausibly care, and changes
inputs the AI's existing departments already read — plus, where the AI cannot act in time, it acts
directly.

The canonical scenario: the player sacks a settlement of Karak Azul. Nearby holds that hate the
attacker take notice, assess whether they can afford to care, declare or send support, and are
pointed at the attacker's nearest army. The player is told why, in the event feed.

### Non-goals

- **Not a difficulty mod.** The Director does not scale numbers against the player.
- **Not a randomness engine.** Exactly one roll happens per campaign (§8).
- **Not an AI overhaul.** It buys no `cai_personality_*` rows. The one table worth editing ships
  as a separate optional pack (§16).
- **Not a replacement for the AI.** Where the AI would refuse, the Director mostly lets it refuse.
- **No UI beyond a news list.** No filters, no sorting, no per-entry detail view, no timeline.

## 2. Architecture

Two halves with a real interface between them.

**The core** owns the event bus, cast selection, the budget, the campaign seed, state and
persistence, the off switch, logging, and the six **beat primitives**. It knows nothing about any
particular scenario.

**The scenario library** is data. A scenario is a row: trigger, condition, cast rule, beats,
cooldown, weight. Adding a scenario adds no machinery.

The split exists because every documented trap lives in a beat — the past event has no inverse,
`force_confederation(X, X)` crashes, favour points have no documented scale, mission locations are
display coordinates while `force_rebellion_in_region` takes logical ones. Handled and tested once,
in the beat, rather than once per scenario.

Global table `derpy_director`, not `director` — a mod whose point is composing with other mods must
not squat a generic global. Same ruling as `derpy_coalitions`.

## 3. Data flow, one situation

1. A registered listener fires. The core builds a **situation**: `{kind, instigator, victim,
   region, turn}`. Nothing else. The core does not know what a war is.
2. Scenarios whose `trigger` matches are filtered by their `when` condition, each call wrapped
   (§11 — an erroring listener condition is dropped silently by the engine, with no log line).
3. Surviving scenarios are ranked by `weight`, adjusted by the seed, and one is chosen. A scenario
   on cooldown is skipped.
4. The core builds the **cast** (§5) and truncates to `cast.take`.
5. Beats execute in order against the cast, each priced against the budget (§7) and each isolated
   (§11). A beat that cannot afford its price is skipped, logged, and the scenario continues.
6. A news entry is appended — **keys and numbers only, never resolved text** (§10).

Only the core touches the world. A scenario is data and cannot call the engine.

## 4. The lore layer

`campaign_cultural_relations`, **675 rows**. Columns: `attitude_base`,
`negative_attitude_multiplier`, `positive_attitude_multiplier`, and `campaign` (empty on every
dwarf row, so global).

**CORRECTED 2026-09-16, before any code was written: campaign Lua cannot read a DB table.** There
is no `cm:` database accessor in `episodic_scripting.html`, and a grep of all 5,778 shipped CA Lua
files for `campaign_cultural_relations` returns **zero hits**. The earlier wording here ("read once
at load") was not implementable.

The table is therefore **baked into the shipped Lua at build time**. `build_director.py` reads
`.skilltree_cache/campaign_cultural_relations.json` through `read_vanilla_cache` and emits a nested
`[source][target] = {base, neg, pos}` literal, 26 subcultures square. This is strictly better than a
runtime read would have been: the bake is verifiable, so `check()` re-reads the cache and fails on a
stale table, and a game patch that changes CA's values shows up as a failing check rather than as
silently wrong behaviour in a campaign.

It is still CA's own encoding of who hates whom rather than a hand-written lore table, which is the
point — a typed table is wrong the next time CA adds a race, and this one regenerates.

**The finding that shapes §5: Dwarfs toward Dwarfs is `+0`.** Kin are neutral in CA's data. There
is no kin affinity to lean on. What the data gives instead is the grudge against the attacker:

| Dwarfs toward | base | neg | pos |
|---|---|---|---|
| **Chaos Dwarfs** | **-100** | **x2.00** | **x0.10** |
| Daemons and the four gods | -100 | x2.00 | x0.10 |
| Skaven, Greenskins, Savage Orcs, Chaos, Beastmen | -100 | x1.50 | x0.50 |
| Vampire Coast, Dark Elves, Wood Elves, Norsca, Vampire Counts | -40 | x1.25 | x0.75 |
| Tomb Kings | -20 | x1.00 | x1.00 |
| High Elves, Lizardmen, Bretonnia | -10 | x1.00 | x1.00 |
| Cathay, Kislev, Ogres, **Dwarfs**, Empire, Tilea/Estalia | **0** | x1.00 | x1.00 |

The attitude bands these scores land in are fixed game-wide, from
`cai_personality_strategic_desired_attitudes` (78 rows, at most 2 distinct values per column):

`bitter enemies -230/-90 | very unfriendly -70/-60 | unfriendly -30 | neutral 0 | friendly +30 |
very friendly +60/70 | best friends +90/230`

So a -100 cultural base already places Dwarfs at **very unfriendly toward Chaos Dwarfs before the
campaign begins.**

**The durability half is derived; the behaviour half is authored.** The multipliers genuinely vary
(negative x1.00 to x2.00, positive x0.10 to x1.00) and are read directly for cooldown length,
commitment duration, and how much later goodwill can buy a grudge off. Dwarfs at neg x2.00 /
pos x0.10 *is* the Book of Grudges as arithmetic. What a culture actually *does* about a grudge is
not in any CA table — `cai_personality_strategic_desired_attitudes` is near-constant — so the
per-subculture response profile is a small, explicit, hand-written table that does not pretend to
be derived.

## 5. Cast selection

Scores every candidate faction, sums three terms, takes the top `cast.take`:

| Term | Source | Note |
|---|---|---|
| Hatred of the **instigator** | §4 lookup | **Not** affinity with the victim. There is none. |
| Proximity | region adjacency hops to the victim's region | **Beyond 3 hops the engine will not assist regardless of intent** — `war_coordination_assist_attack_{force,settlement}_max_distance` is 3.0 on all 78 personalities, one distinct value |
| Own safety | the candidate's own threat exposure | The "self priority first" rule as a scoring term, not a special case |

Candidate pool excludes: null interfaces, dead factions, rebels, **the human player**, the
instigator, and factions already at their per-faction cooldown.

**The human is never a candidate** — `cai_evaluate_quick_deal_action` asks what the campaign AI
would accept and a human faction has no AI to ask, while the `force` beats are unrefusable. A human
instigator is still fully targeted. This is ruling A9 from the 2026-09-13 handoff, carried forward
unchanged.

**Sorted, never raw `pairs()`.** Undefined table order diverges across reloads and multiplayer
clients. Cache `f:name()` once — the sort comparator otherwise makes O(n log n) engine calls over
up to 100 factions, every situation.

**Candidate pairs are filtered to factions that have met each other before any budget is spent.**
This is the 2026-09-16 patch to the Coalition Supervisor, generalised: the met test belongs in
enumeration, not in the ask. Measured before the fix — a turn polled 8 pairs and asked 2.

## 6. Beats — the call inventory, with receiver conventions

**Receivers are inconsistent and unmarked in CA's docs. Every one below was read from the doc
entry, not inferred from the signature.**

| Beat | Calls | Receiver |
|---|---|---|
| `ask` | `cm:cai_evaluate_quick_deal_action(a, b, deal)` -> `score, can_issue` | **faction interfaces**; `deal` from `diplomatic_actions` (34 rows) |
| `force` | `cm:force_declare_war(a, b, invite_a_allies, invite_b_allies[, suppress_war_messages])` | **key strings**. Args 3 and 4 are the call-to-arms path exposed to script; the 5th is undocumented but present in CA's lib |
| | `cm:force_alliance(a, b, is_military)` | key strings |
| | `cm:force_make_peace(a, b)` | key strings |
| | `cm:force_make_trade_agreement(a, b)` | key strings. "If no agreement is possible then nothing will happen" — silent no-op, must be logged |
| | `cm:force_grant_military_access(granter, recipient, is_hard)` | key strings; hard access "is currently unused" |
| | `cm:force_confederation(a, b)` | key strings. **`force_confederation(X, X)` crashes** — self-check required |
| `mood` | `cm:set_base_strategic_threat_score(faction, score)` | **faction interface**. Maps to `faction_strategic_threat_levels` 0/100/200/350/500 -> -5/-10/-20/-30 attitude with everyone. Reversible with 0 |
| | `cm:war_coordination():set_faction_favour_points_toward_faction(owner, toward, amount)` | **faction interfaces**. Float, **no documented scale, bounds or default** |
| | `cm:cai_set_faction_script_context(fkey, context)` | key strings. **Per-faction, 9 values, not the contended global slot** |
| | `cm:cai_add_diplomatic_event(from, to, action)` | key strings. **No inverse exists.** See §7 |
| `target` | `war_coordination_target(faction, REGION\|MILITARY_FORCE, offensive) -> bool` | **payload builder, not `cm:`**. See §15 |
| `muster` | `cm:force_rebellion_in_region(region_key, units, x, y, suppress)` | **logical** coordinates — mission locations are **display** coordinates, the opposite convention |
| `tell` | `cm:show_message_event(...)` | last argument indexes `event_feed_message_events`; **0 draws nothing** |

**`force_diplomacy` uses a different vocabulary from everything above** — space-separated plain
names (`"join war"`, `"defensive alliance"`, `"form confederation"`), not `diplomatic_option_*`
keys. Mixing them is an unvalidated string and fails silently forever.

`cm:war_coordination()` returns an interface whose doc prose claims war-coordination requests can
be made through it. **It exposes three methods and none of them make a request.** Favour points are
all it offers.

## 7. The budget, priced in irreversibility

The budget is denominated in **how hard a beat is to undo**, not in how many beats ran. This is
ruling A16 generalised: when a situation passes, reversible effects are released and irreversible
ones stay for the campaign.

| Beat | Reversible | Price |
|---|---|---|
| `ask` | reads only | free |
| `mood` — threat score, favour points, faction context | yes, all three written back | cheap |
| `force` — war, alliance, trade, peace, access | yes, a `force_` call exists for the opposite | moderate |
| `target` | expires with its mission | moderate |
| `mood` — **past diplomatic event** | **no inverse exists** | expensive |
| `muster` — spawned force | cannot be unspawned gracefully | expensive |

Three limits, all constants at the top of the file: a world budget that refills slowly, a
per-faction cooldown so the same faction is not conscripted repeatedly, and a hard cap on scenarios
in flight.

**The Director is a scheduler, not a reflex.** This is the only thing standing between "the world
reacts to me" and "my campaign is unplayable", and it is a safety mechanism as much as a pacing one.

Past events fire only when a situation **enters or escalates**, never while it merely holds —
carried directly from A16, which measured five steady turns going from 10 events to 2.

## 8. The campaign seed

**One roll, at campaign start, frozen into the save, never rolled again.**

Rolled in `cm:add_first_tick_callback`, which is documented to fire "regardless of what mode the
campaign is being loaded in" — so it fires on every load, and without a guard on
`cm:get_saved_value("derpy_director_seed") == nil` a reload re-rolls the world mid-campaign.

`cm:random_number([max], [min])` is documented **"safe to use in multiplayer scripts"**, unlike the
battle-only `random_number`. **Note the argument order: max first, min second**, defaults 100 and 1.
Most APIs take `(min, max)`. Reversing it is silent.

Three fields, and that is the whole seed:

| Field | Holds | Effect |
|---|---|---|
| `hot_grudge` | one subculture pair | multiplies the existing hatred term when a situation matches |
| `ambitious` | two or three faction keys | adds to cast score, shortens cooldown |
| `temperament` | one world mood | re-weights the §7 beat prices |

**Every field is a multiplier on a term that already exists.** No new code path, no new beat, no new
scoring dimension. That is what stops the seed becoming a randomness subsystem.

Deliberately cut: a fourth field marking one live treaty "brittle". It needs a pass over existing
treaties at campaign start and earns less than the other three.

The seed's disposition is **named to the player** at campaign start through `tell`. Variety the
player cannot perceive is indistinguishable from no variety.

## 9. The scenario library, version one

Four scenarios, one per approved trigger.

| Scenario | Trigger | Cast scores on |
|---|---|---|
| Kin avenge a sacking | `CharacterSackedSettlement`, `CharacterRazedSettlement` | hatred of the sacker |
| Runaway dominance | turn tick, region ratio | hatred of the leader |
| Weakness and opportunism | settlement lost, army strength drop | pre-existing hostility to the weakened faction |
| Treachery | `NegativeDiplomaticEvent`, broken treaties | transitive propagation is engine-native here — 79 of the 104 `cai_personality_diplomatic_events` rows propagate to third parties, and the six script-facing generics do not |

**Runaway dominance is the existing Coalition Supervisor, demoted to one scenario.** Its measured
behaviour carries forward as-is: tiers at ratio 1.75 / 2.5 / 4.0, `MIN_REGIONS` 10, exit at 1.35,
hysteresis holding the **minimum** active tier (A17). Its thresholds remain guesses — the highest
ratio measured across 85 supervised turns is 2.00, so tiers 2 and 3 have never fired in game.

Available triggers not used in version one, recorded so they are not re-derived:
`FactionLeaderDeclaresWar`, `FactionLeaderSignsPeaceTreaty`, `FactionJoinsConfederation`,
`PendingBankruptcy`, `LandTradeRouteRaided`, `DiplomaticOfferRejected`, `PositiveDiplomaticEvent`,
`FactionCapturesWorldCapital`, `WarCoordinationRequestIssued` (carries `context:faction()`).
`events.lua` declares 379 in total; the core registers only the ones scenarios ask for.

## 10. The news surfaces

**Two surfaces, built in this order.**

**The event feed message** is the `tell` beat. Engine-native, no UI file, and it is what makes the
Director perceptible at all. `cm:show_message_event`'s last argument indexes
`event_feed_message_events` through the four-table chain in `docs/RITUALS.md`; 0 draws nothing.

**The panel** is the archive — scrollable, opened from a HUD button, newest first. Built only once
the feed proves there is enough happening to archive.

**The constraint that defines both:**

> A news entry is generated in a turn handler and displayed much later. **A loc call from a turn
> handler CTDs at turn 1 and `pcall` does not catch it.**

The turn handler stores **keys and numbers only** — turn, scenario id, faction keys, region key.
Every name and sentence is resolved at **draw time**, inside the panel. This is not style; it is the
difference between working and crashing on the first scenario. It also keeps the saved log tiny.

Storage is a bounded ring buffer through `cm:set_saved_value`, which accepts nested tables of
booleans, numbers and strings and registers its own save/load. **Cap it** — every entry rides in the
save for the life of the campaign.

The panel ships its own `.twui.xml` and is created at runtime with `CreateComponent`, never as a CA
file override. `dockpoint` is ignored outright on a runtime-created component and a layout group
beats `MoveTo`; `MoveTo` positions everything. Generated by `gen_director_ui.py` in the shape of
`gen_exchange_ui.py` and `gen_ic_ui.py`, previewed headless against TWUI Studio's vendored reader
the way `preview_iron_court.py` does.

**The list is the hard part and `docs/CUSTOM_UI.md` already documents it** — the five reserved
names, the four reserved callbacks, the container everybody forgets, and the CA donor that is the
wrong donor. Use that recipe. A list that does not scroll fails silently.

Rows carry `[[img:]]` and `[[col:]]` markup, both of which work from Lua. An image costs a line box
of width; a colour name outside the 42 in `ui_colours_tables` drops the colour silently.

## 11. Error handling

**Catchable, and handled:** the turn handler is wrapped, as now. Each **beat** is isolated
individually — one failing beat must not abort its scenario, one failing scenario must not abort the
turn. Every failure logs.

**Not catchable, so designed out structurally:**

- A loc call from a turn handler CTDs at turn 1. §10's keys-only rule exists for this.
- A local-faction call at script root CTDs. Nothing resolves the player at load time.

**Neither, and the worst of the three:** an erroring **listener condition** is dropped by the engine
with **no log line at all**. For a Director whose scenarios are defined by their conditions, that is
a scenario that silently never fires. Every `when` gets its own wrapper that logs on error.

Unvalidated keys fail silently forever — faction, region, unit and character keys are unchecked
strings. Every key in the scenario library is verified against `db/` before shipping.

## 12. Persistence

Through `cm:set_saved_value` / `get_saved_value`, which self-register. Saved: the seed, per-faction
cooldowns, per-scenario cooldowns, the world budget, scenarios in flight, the news ring buffer, and
the carrier of any held threat score.

**The score carrier is saved by key.** It is the only record of which faction carries a scripted
score, and a release must target that faction even if it no longer leads (A4/A6). Re-application
after a load is a one-shot `loaded` flag, not a re-derivation.

**The global AI context slot is process-global, not save-scoped** — a fresh campaign inherits the
previous one's value. The Director uses **per-faction** contexts (§6) and does not contend for the
global slot at all, which removes the whole class of problem the Coalition Supervisor has with it.

## 13. Off switch

`ENABLED = false` makes **zero** calls out of the turn handler. Not calls that clean up — zero.
A13's ruling stands: a disabled mod that still calls into the AI every turn to check for cleanup is
the worse failure. Save and load callbacks stay registered unconditionally so state round-trips
while the feature is off.

## 14. Testing

`tools/build_director.py --selftest` runs the **shipped** Lua under Lua 5.1.5 against a stubbed
`cm` and world and reads back every recorded call. No flag packs, and **refuses to pack on a failing
selftest**. Static checks wired in: `luac -p`, `check_lua_api.py`, `check_lua_undeclared.py`.

Two additions earn their place:

**`tools/mutate_director.py`**, in the shape of `mutate_iron_court.py`. Scoring, budgets and a seed
are exactly where assertions quietly become unbreakable — that tool has already caught three such
assertions in this workspace. Mutate the budget cap, each cooldown, the self-priority term and the
seed multipliers one at a time, into the **shipped** Lua, restored in a `finally`, harness green
before and after. A stale anchor is a finding, not a skip.

**The seed test:** the same situation under two different seeds must produce different casts. A
seeded system's characteristic failure is being wired up and inert.

**And the lesson that cost 44 sessions:** nothing offline can tell you whether the AI responds —
only a soak can — so **the log lines are a deliverable, designed before the feature**. The Coalition
Supervisor passed every offline check and then produced 44 sessions of logs that could not answer
the one question that mattered, because its ask line recorded scores but not the can-propose flags.
Every beat logs what it asked, what it got, and why it stopped.

## 15. The DB half

**Open question to settle first, because it decides whether the Director has a DB component at
all:** `war_coordination_target` is a payload-builder function, which normally means a mission row.
But this workspace already ships missions built from strings — `cm:trigger_custom_mission_from_string(faction_key, mission_string[, whitelist])`,
the route `gen_victory_routes.py` uses, documented in `docs/VICTORY_CONDITIONS.md` §11. **If the
payload is expressible in mission-string syntax, the `target` beat needs no DB rows.** Resolve this
in planning before anything else.

Certainly required: loc for every scenario, and `event_feed_message_events` rows for the feed
messages through the four-table index chain. Loc is a binary `.loc` and RPFM is the only way in.

## 16. Compatibility and packaging

Adding rows is low-collision. The Director's missions, loc and feed rows will not fight other mods.

**The dangerous edit is the one deliberately excluded from version one.** Buying the war-coordination
numbers means rewriting `cai_personality_strategic_components`, a 78-row table every AI overhaul
also rewrites. The prize is real — measured, those columns are **global constants** in WH3:

- `war_coordination_assist_attack_{force,settlement}_max_distance` is **3.0 on all 78 rows**
- `call_to_arms_chance_*` is 1.0 / 1.0 / 0.5 / **0.1** on all 72 live rows; the six that differ are
  all `wh3_strategic_component_prologue*`

So "my allies never join my offensive wars" is a literal 10% roll, and an ally only diverts to
assist within 3 of the target. Hecleas' AI Overhaul rewrites all 78 rows but leaves these columns
alone.

**Ship it as a separate optional pack.** The Director stays broadly compatible; a player who wants
allies that answer a call to arms enables a second small pack and knowingly accepts the conflict.
Two packs, no hard dependency, and the compatibility cost lands only on those who opt in.

## 17. Open risks

1. **Layer 2 of the Coalition Supervisor has never fired** — about 50 asks, every result at or below
   zero. The 2026-09-16 patch (pair filter plus `ok=` logging) is deployed but **no turn has been
   played with it in**. If `ok=` comes back false in bulk,
   `diplomatic_option_defensive_alliance` is the wrong lever and the `ask`-then-`force` idiom this
   whole spec leans on needs rethinking before the library is written.
2. **Favour points have no documented scale, bounds or default.** Same shape as the stance manager's
   `_level`, for which no vanilla precedent exists because CA never calls it. Any value chosen is
   unvalidated and nothing fails loudly.
3. **`(from, to)` on `cai_add_diplomatic_event` is still unsettled.** The mod logs its argument
   rather than assuming; the log alone cannot settle it, it needs the diplomacy screen.
4. **Every threshold is a guess.** `CAMPAIGN_AI.md` §9 is the standing warning: CA ran thousands of
   overnight AI-vs-AI games and still shipped a defend-priority tuned wrong.
5. **A Director with 379 possible triggers and the power to spawn armies can ruin a campaign**, and
   several beats have no undo. §7 is the mitigation and it must exist before any scenario does.
6. **The seed gives campaign-to-campaign variety; the responses stay deterministic.** The early game
   runs off fixed start positions, so the first thirty turns will look similar across campaigns
   apart from the seed's multipliers. Describing this as "procedural" promises more than it
   delivers; "the world reacts to what you do" is the honest pitch.

## 18. Build order

**This spec is too large for one implementation plan and must be decomposed.** Each phase below is
a plan-sized unit that ships something testable on its own.

**Phase 0 — a free de-risk, before any code.** Play a campaign with the deployed 2026-09-16
Coalition Supervisor patch and read the `ok=` flags. §17.1 is not a minor risk: the
`ask`-then-`force` idiom is the spine of every scenario in this spec, and it has never once
succeeded in 85 supervised turns. If `ok=` comes back false in bulk, the deal type is the wrong
lever and §6 needs rewriting before anything is built on it. This costs one campaign of ordinary
play and nothing else.

**Phase 1 — the core, proven by one scenario.** Event bus, situation, cast selection (§5), the lore
lookup (§4), the budget (§7), persistence (§12), the off switch (§13), all six beats (§6) except
`target`, and exactly one scenario: kin avenge a sacking. Output is event-feed messages only, no
panel. Plus `build_director.py --selftest` and `mutate_director.py`. This is the phase that proves
or disproves the architecture.

**Phase 2 — the library and the seed.** The remaining three scenarios of §9, the campaign seed
(§8), and the seed test. Runaway dominance migrates from `derpy_ai_coalitions` here, which is also
when that mod is retired or reduced.

**Phase 3 — the news panel.** §10's second surface, `gen_director_ui.py`, and the headless preview.
Only worth starting once phases 1 and 2 have produced enough events to be worth archiving.

**Phase 4 — the `target` beat and the DB half.** Gated on the §15 open question: settle whether
`war_coordination_target` is reachable from a mission string before committing to DB rows.

**Phase 5, optional and separable — the call-to-arms pack.** §16. Independent of everything above
and shippable on its own.

Phases 1 and 2 have no DB component at all, so the Director stays zero-DB and broadly compatible
until phase 4 — which means the compatibility decision taken in chat can still be reversed cheaply
if phases 1 to 3 turn out to be enough.

## 19. As built, 2026-11-14: the storyteller

Phase 2 shipped in a different shape from §8 and §9, modelled on RimWorld's storytellers at the
author's request ("so that not every campaign would be the same"). The constants are at the top of
`derpy_director.lua`; the behaviour is pinned by `build_director.py` group 26 and 39 mutants.

- **The seed (§8) as designed, plus a phase.** Rolled at the first tick that finds none, frozen
  into the save, never rolled again. `temperament` is one of three; `hot` is one pair of present
  cultures that hate each other both ways (both at -25 or lower), which doubles a responder's cast
  score; `ambitious` is three AI factions with land, which score half again and come off cooldown
  in half the time. The temperament is named to every player at the capital, with records 7800-7802.
  The hot pair and the ambitious factions are not named: feed text has no runtime tokens, and five
  start-of-campaign popups would be the spam the party gate was built to stop.
- **Temperaments instead of §8's re-weighted prices.** `rising` (Cassandra): 6 ON turns of 10.
  `patient` (Phoebe): 3 of 12. `wild` (Randy): no cycle, a random refill of 20-100, a cast size that
  swings one either way and a war chest of 50-150%. ON turns refill 70, OFF turns 20-30 and answer
  at a quarter to 0.4 of the chance. Cooldowns are 12, 18 and 8.
- **Choosing, not queueing.** The live run of 2026-11-14 spent the whole turn's budget on the first
  3 to 7 of 27 to 41 situations, so the factions' turn order decided which stories were told. Each
  situation is now answered with a chance: outrage over the kin-slaying 1.5, times 3 with a player
  as a party, times how full the budget is (floor 0.25), times the tension. One roll per feud a
  turn, after the feud guard.
- **The weighted draw.** The cast is drawn by score from the sorted list, not taken from the top.
  A roll of 1 takes the top, which is why the older test groups still hold under dice of 1.
- **Adaptation.** Per player, -60 to 60: -15 per region lost last round, +3 per region gained,
  drifting 5 a turn back to 0. It multiplies the chance the world turns on that player by
  1 + adapt/100 and the chance it helps them by 1 - adapt/100. §1 says "not a difficulty mod": this
  changes how readily the world reacts, never the size of anything.
- **Two of §9's three scenarios.** Weakness and opportunism is the Director's own clock: at a turn
  start, with the temperament's chance (25, 10 or 30 percent), one AI faction that lost settlements
  by force last round is drawn by how many it lost, and its haters turn on it; whoever took the
  most is told (record 7900). A player is never the target. Treachery is `NegativeDiplomaticEvent`
  with an alliance of any kind or a non-aggression pact broken, never a shrug (outrage at least
  1.0), told with record 8000. Runaway dominance stays in `derpy_ai_coalitions`, which already does
  it, because two mods pushing the same leader would double the pressure.
- **A reload no longer refills.** `first_tick` called `refill()`, so every load paid out a turn's
  budget.

**Soak, 2026-11-14, 10 turns on the Astragoth fixture** (`script_log_141126_1234.txt`). The seed
rolled rising at phase 3, so turns 1-3 and 8-10 were on and 4-7 were calm. The hot pair was the
Chaos Dwarfs and the Empire, and the ambitious factions were Clan Mors, Clan Carrion and Bordeleaux.
"A Restless World" reached the player's event feed on turn 1. There were 392 situations: 32 were
repeats of a feud already answered, 308 were passed over and 52 were answered. The log has 24
`cannot afford` lines. In 10 of them an answer found the budget at 0 and could not pay for even a
stance push, so it did nothing, because the chance formula's budget term never drops below 0.25.
The other 14 were a costlier beat skipped after a cheaper one had landed. The cycle shows in the
numbers. The average answer
chance was 15-20% on the on turns and 5-9% on the calm ones, and stance changes ran at 13.5 a turn
on against 4.5 calm. This morning's soak, before the storyteller, ran at 12.7 a turn throughout.
Opportunism fired 3 times and treachery once (Seducers of Slaanesh against Saphery, turn 7), with
8 grudges, 3 unrest and 1 plague. There were no Director errors. Astragoth was never the
instigator or the victim of any situation, so the party gate correctly sent no other message. This
soak therefore says nothing about how often a player who is fighting gets one. Turn 1 is the
busiest turn by far (96 situations, 15 answered), because the start position's wars all report at
once.

**Two fixes from the soak, the same day.** `chosen()` now passes a situation over without a roll
when the budget is below `PRICE.mood`, the cheapest beat, and logs `passed over: budget N cannot
pay for anything`. An "answered" line now always means something was paid for. `chance()`
multiplies by `FIRST_TURN_DAMP` (0.33) on turn 1 when no player is a party, which should bring
turn 1's 15 answers down to about the 5 of a later on turn. A player's own turn-1 situations keep
the full chance. The harness gained a `SetBudget` pseudo-event, because the turn start's refill
always runs before the first event and no preload can reach an empty budget at the roll.

**Verification soaks, the same afternoon** (`script_log_141126_1312.txt`, `_1324.txt`). On the
Astragoth fixture the seed rolled rising at phase 3 again, so the run compares directly. Turn 1 went
from 15 answers to 7 (average chance 19% to 10%), and there were 27 `cannot pay for anything`
pass-overs and no answer that did nothing. A new Empire campaign rolled wild on its own: cast sizes
varied (10 of one, 8 of two, 29 of three), the refill landed on odd budgets, and turn 1 answered 6 of
98 at 8%. Neither run formed a pact, as in every soak so far, so the war chest and the shield have
never run live. The Empire was party to nothing in 10 turns, so its capture of Grunburg from the
Separatists on turn 11 was staged. It was answered at 100%: temple Reputation -25 with the guild
message, three neighbours turned very unfriendly, the Wood Elves took the grudge with its message,
and Grunburg got 4 rebel units. Both messages are logged as sent but were not read on screen.
**Found:** all 31 grudge records open "A settlement has been sacked", but the grudge fires for a
conquest and a raze too. Fixed the same day: "A settlement has been attacked", and six culture
flavour lines that assumed a sack, a raze or loot reworded.

**The long run, 2026-11-14.** Four changes, after a read of how the Director behaves over 100+ turns:

- **Sizes follow the aggressor.** Rebels (4) and the war chest (2,500) grow by one time for every 20
  regions the instigator holds above 20, to three times (`SIZE_FROM`, `SIZE_STEP`, `SIZE_MAX`).
- **Rising ramps.** A temperament with `ramp` (rising only) multiplies its refill and the budget's
  ceiling by `1 + (turn - 1) / 100`, to 2.5. `chance()` reads the ramped ceiling. Patient and wild do not.
- **A feud's grudge fades.** The seen mark holds the turn it fired (an old save's `true` reads as 1) and
  the feud can be grudged again after `GRUDGE_MEMORY` = 50 turns, CA's falloff on the past event.
- **Pact partners.** The victim is asked too when it is a computer faction still standing, and a pair
  that hates each other either way at `HOT_FLOOR` or worse, or is at war, is not asked.

**Long soak, 55 turns, Very Hard, new Empire campaign** (`script_log_141126_1416.txt`). It rolled rising.
1,419 situations, 196 answered, 378 stance pushes, 46 grudges, 8 unrest, 12 plague, 8 opportunism, 23
treachery, no Director error. **Six pacts formed, the first in any soak**: 307 asks, 149 of them with the
victim, 281 pairs skipped as at odds, 6 positive both ways and legal; three of the six included the victim.
The ceiling grew from 180 to 279 and the budget stopped running dry after turn 33 (117 empty-budget
passes, all before). Situations per turn fell from 39 to 17 as the world settled, and answers held at
3-4 a turn, so the ramp kept the Director's volume flat while the world got quieter. The largest empire
was 25 regions at turn 56, so rebels never grew and war chests reached only 2,875. No feud's grudge
faded and recurred inside the run; 26 repeats were refused as still remembered. The player shield lost
10 battles (see `docs/LIVE_TESTING.md`), so peace was forced on the player from turn 31.

Still unchecked: whether `NegativeDiplomaticEvent` fires once or twice when an ally is attacked
(the feud guard makes a second one harmless), the patient and wild temperaments, and whether the
chances feel right. They are all guesses, like every threshold in this file.

## 20. The Coalition Supervisor merged in, 2026-11-14

The Director now carries the Coalition Supervisor's runaway step (the threat score on a runaway
leader and alliances among those who would accept one) and decides which computer factions
confederate: a faction down to its last region by force folds into stronger kin, and kin unite
when a runaway or one of CA's endgame invaders takes their towns. By default only what the game
allows confederates, and almost all of it is adjustable through MCT. The Supervisor's pack, script
and builder were deleted. The design, the rulings and the live checks are in
`2026-11-14-director-merges-coalitions-design.md`; the tests are `build_director.py` groups 29-32.
