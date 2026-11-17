# The Director grows empires: design

2026-11-15. Phase 4 of `2026-09-16-ai-director-design.md` (section 18): the `target` beat, and the
great power the author asked for. The Director is `derpy_director.pack`, built by
`tools/build_director.py`; read `2026-11-14-director-merges-coalitions-design.md` and
`2026-11-15-director-chronicle-design.md` first, because this design leans on the merges, the
runaway step and the Chronicle.

## 1. Intent

The author, in their own words:

- "there should be atleast 1 faction that has 50 settlements during a play"
- "the great power are there so that the player will have someone to fight with, there should be
  more empires being built at turn 50 to make the campaign much more appreciated in the late game.
  the empires can be greater or lesser than the player's strength"
- On how: "go with C, should feel natural and no cheats be allowed"

Today nothing gets that big. In the 55-turn Immortal Empires soak of 2026-11-14, with the Director
running, the largest empire was 25 regions at turn 56 (`2026-09-16-ai-director-design.md` section
19). Part of the reason is the Director itself: the runaway step and the stories turn the world
against whoever grows.

## 2. Goals, non-goals, anti-goals

**Goals.**

- Every campaign, the Director grows three AI empires: one **great power**, whose goal is 50
  settlements on Immortal Empires, and two **lesser empires**, whose goal is 25.
- By turn 50 the three are visibly the largest AI powers on the map, so the late game has rivals.
- Every settlement an empire gains, it takes itself in war, or gains through a confederation the
  game allows.

**Non-goals.**

- Sizing the empires to the player. They can end up stronger or weaker.
- Aiming them at the player. The AI may still choose to attack a player; the Director's growth never
  pushes it to. The existing stories still answer a player's own deeds, and an empire answers them
  like any other neighbour (section 7).
- Guaranteeing 50. Without cheats, the Director raises the odds and cannot force the outcome.

**Anti-goals: it fails, even if it works, when**

- a settlement or an army appears from nowhere (the author's "no cheats");
- an empire's growth reads as scripted: one faction surging while everything around it stands still;
- one empire swallows a continent by turn 40 and the late game has one rival instead of several.

## 3. Approaches

- **A. Steer and fund.** War targets, stance pushes, a more aggressive personality, gold, and first
  pick in confederations. Invisible and compatible, but growth is not assured.
- **B. Hand it over.** Region transfers and spawned armies on a schedule. Reaches 50 reliably,
  looks artificial, cannot be undone.
- **C. Steer, then catch up.** A every turn, plus a growth schedule; an empire that falls behind gets
  stronger help.

**The author chose C**, with "no cheats". That removes two things from C as first offered: the
spawned armies of its catch-up step, and A's gold and personality change. What remains is listed in
section 6, and all of it is something the AI or the diplomacy screen could have produced: a war
target, a hostile stance, a peace, a confederation.

## 4. Which factions become empires

The seed already rolls three **ambitious** factions at the first tick, and the Chronicle's header
names them. They become the empires. The roll changes in two ways, because a one-town minor
squeezed between giants cannot grow to 50 naturally:

**Candidates.** An AI faction that is alive, not a rebel, not an endgame invader, not a vassal, and
holds at least one settlement, with two more tests:

- `faction:can_be_human()`, a faction a player could have picked. CA uses it as its own "is this a
  major faction" test (`campaign/mod/battle_logging.lua:75`). These are the factions with a
  legendary lord, a start position built to grow, and room in the lore to rule. In the 2026-11-14
  merges soak, 176 factions held a region at turn 11 and most were minors, so without this test a
  random draw is almost always three one-town minors.
- `faction:is_allowed_to_capture_territory()`, which leaves out the races that cannot hold
  settlements.

If fewer than three factions pass, which only a small map or a heavily modded one would produce,
the rest of the draw falls back to any faction that passes everything but `can_be_human()`. The same
rules as `merge_blocked` apply where they overlap.

**Spread.** No two empires' capitals within `EMPIRE_SPREAD` of each other, so they do not block each
other and different parts of the map get a rival. Picked at random among candidates, under that rule.

**Roles.** At each check (below), the empire with the most settlements holds the great-power goal and
the others the lesser one. An empire that reaches the great goal keeps the title.

**Replacement.** From turn 20 and every 10 turns, an empire that is dead, or holds fewer than half
of what its schedule expects, is replaced by the candidate that gained the most settlements in the
last 20 turns, under the spread rule and the same candidate tests. An empire that another empire
conquered or absorbed is dead, and is replaced the same way. The Director backs a winner rather than reviving a loser,
which is also what reads as natural.

**Existing saves.** A save whose seed already holds ambitious factions keeps them. The first check
that runs under the new code applies the replacement rule to them, so a weak old pick is replaced
then, not on load.

## 5. Goals and the schedule

**Goals scale with the map.** `goal = setting * map_regions / IE_REGIONS`, rounded. Immortal Empires
has 644 regions in `campaign_map_regions` (`wh3_main_combi_map_7`), so the defaults are 50 and 25
there and about 22 and 11 on Realm of Chaos (279). `IE_REGIONS` is the count the region list reports
on vanilla Immortal Empires at runtime, measured in the live spike; 644 is the DB's figure.

**The schedule.** `expected(t) = goal * clamp((t - 10) / (T - 10), 0, 1)`, with `T` the goal turn
(setting, default 80). On Immortal Empires the great power is expected to hold about 29 settlements
at turn 50 and 50 at turn 80.

- **Ahead** (`settlements > expected(t)`): no help, and no shelter (section 7). The world reacts to
  it as to anyone, which is the natural brake on growing too fast.
- **Behind** (`settlements <= expected(t)`): sheltered, and helped with the first two levers.
- **Far behind** (`settlements < 0.6 * expected(t)`, from turn 25): all four levers.
- **At the goal**: it graduates (section 8).

## 6. What the Director does for an empire

At the turn start, once per empire every `HELP_EVERY` (3) turns, priced from the Director's one
budget like every other beat. Never with, against or about a human faction. **Never against another
empire either:** no war target on another empire's settlement and no hostile stance toward one,
because helping one rival eat another leaves the late game with fewer of them. Peace between two
empires is allowed. Steering clear of three factions out of a few hundred does not show.

1. **A war target (the `target` beat).** The empire's weakest enemy settlement next to its own
   territory, owned by an AI faction it is already at war with: `cm:create_payload()`,
   `payload:war_coordination_target(empire, region, true)`, `cm:apply_payload(payload, empire)`. No DB
   rows, which settles the open question of section 15 of the parent design. **Gated on the live
   spike** (section 11): if an AI faction does not act on a target set this way, the beat ships
   switched off and the rest stands.
2. **A hostile stance.** When the empire has no war to target, its stance toward its weakest AI
   neighbour is pushed to hostile (`beat_stance`, the existing beat). The AI decides whether to
   declare war. Not toward an ally, a vassal, or a faction it could later absorb (kin).
3. **Peace on a losing front** (far behind only). If it is at war with an AI faction that holds more
   settlements than it, and that faction is not the target's owner, the two are asked about peace
   (`diplomatic_option_peace` through `beat_ask`) and, if the sum of both scores is positive, peace is
   forced (`cm:force_make_peace`). It stops fighting the war it is losing and turns on the one it can
   win.
4. **Kin join it** (far behind only). A weaker kin it has met folds into it through the existing
   merge route (`merge`, payload confederation), as a new mode `"empire"`. Every rule of
   `merge_blocked` applies, the willing ask applies when that setting is on, it counts against the
   turn's confederations and pays `merge_price`, and each empire takes at most one every 10 turns.

**Not used by default, as cheats:** region transfers, spawned armies and gold, which section 6b
makes optional; effect bundles, AI difficulty bonuses and personality changes are not used at all.

## 6b. Optional cheats

Added by the author at approval: "the cheats as an optional mct option or difficulty preset". An
MCT dropdown, **Empire help**, with three steps. Each adds to the one before, and each applies only
to an empire that is far behind, once every 10 turns:

- **Natural** (the default): section 6 and nothing else.
- **Generous**: the empire is also paid 5,000 gold.
- **Relentless**: it is also given a copy of its own largest army at its capital (the same units,
  without the lord, as CA's own scripts skip `unit_list()` item 0), and one abandoned settlement
  next to its territory is settled for it.

Cheats never touch a player, are not charged to the Director's budget (the player chose them), and
are logged but not written into the Chronicle. Multiplayer always uses Natural, as every Director
setting falls back to its default there.

## 7. Shelter

While an empire is at or behind its schedule:

- **The runaway step** does not name it as the leader. It still counts as the runner-up, so the
  ratio the step measures stays honest for everyone else.
- **Its own deeds against an AI faction** still draw the cast's stance push and the tell, so
  neighbours still dislike it. The Director does not fund pacts, war chests or shields against it,
  nor give its victims a grudge, unrest or a plague. The Chronicle records what was done, which is
  less.
- **Its deeds against a player are not sheltered.** When the victim is a human faction, the Director
  answers exactly as it does today: pacts with the player, a shield on the player's settlement, and
  the rest. Shelter never weakens the defence a player already gets.

Ahead of schedule, all of that returns. It is the same faction the world now reacts to fully,
which is what holds it near the schedule from above.

**A player's own deeds** are unchanged. Today the cast scores ambitious factions half again and
halves their cooldown, so when a player sacks or takes a town, an empire nearby is a likely
responder: its stance toward the player turns hostile and it may take the grudge. That stays. It is
the world reacting to what the player did, not the Director aiming an empire, and it is a large part
of how an empire becomes someone for the player to fight.

## 8. When an empire reaches its goal

It **graduates**: it is never helped or sheltered again, even if it later shrinks. From then on the
runaway step may name it, and the coalitions that form against it are the late-game fight the author
asked for. No new empire replaces a graduate.

## 9. What the player sees

**The Chronicle.** New entries, keys and numbers only, like every other:

| Entry | Written when | Reads |
|---|---|---|
| `{k="empire", i, n=1\|2}` | an empire is chosen (1 great, 2 lesser) | "{i} set out to become a great power." / "{i} set out to build an empire." |
| `{k="empire_fade", i}` | it is replaced | "The ambitions of {i} came to nothing." (as built, section 14) |
| `{k="empire_goal", i, n, g=1\|2}` | it graduates (n settlements) | "{i} now rules {n} settlements, a great power the world cannot ignore." / "... an empire in its own right." |
| `{k="empire_merge", i, v}` | kin join it | "{v} joined {i} in a confederation." |
| `{k="empire_peace", i, v}` | peace on a losing front | "{i} made peace with {v} to turn its armies elsewhere." |

War targets and stance pushes are not recorded: they are many and say nothing a player can see.
The header's "The Ambitious" row lists the empires, the great power first.

**The event feed.** One message to every player when the great power graduates, located at its
capital. Feed text takes no runtime tokens, so it names no faction or number: the location does
the naming. Draft: title "A Great Power Rises", text "One power has grown into an empire the world
cannot ignore. Its capital is marked on the map."

The sentences above are drafts in CA's voice; the author approves the final text.

## 10. Settings

A new MCT section, **Empires**: on or off (default on), the great power's goal on Immortal Empires
(50), the lesser empires' goal (25), the goal turn (80), and Empire help (Natural, section 6b). Multiplayer always uses the defaults,
as every other Director setting does.

## 11. Testing

- **The live spike, first.** Load an Immortal Empires save, give an AI faction already at war a war
  target on an adjacent enemy settlement through the payload, and play five turns with the player
  shielded. It passes if that faction's armies move on or besiege the target. The same run measures
  `IE_REGIONS` from the region list.
- **The harness** (`build_director.py --selftest`): candidates and spread; roles; replacement and the
  old-save path; the schedule's three bands; each lever's conditions, including "never a human";
  shelter both ways; graduation; the new merge mode under `merge_blocked`; the Chronicle entries.
- **Mutants** (`mutate_director.py`) for each rule above.
- **The preview** (`preview_director.py`): every new sentence word for word.
- **The soak.** A new Immortal Empires campaign to turn 50 with the player shielded, logging each
  empire's settlements every 5 turns. It passes if, at turn 50, each empire holds at least 60% of
  its expected count and the great power is the largest AI faction, with no Director error. A run to
  turn 80 checks the goal itself.

## 12. Calls made by the designer, for the author to check

1. "No cheats" means nothing appears from nowhere, so C's spawned armies are gone. Peace and
   confederation count as natural, because the diplomacy screen offers both.
2. The seed's three ambitious factions are the empires: one great power and two lesser.
3. The goals scale with the map, so Realm of Chaos asks about 22 settlements of its great power.
4. Shelter holds only while an empire is at or behind its schedule. Ahead of it, the world reacts as
   normal.
5. A graduate is never helped again, and the runaway step may then turn the world on it.
6. A failing empire is replaced from turn 20 by the fastest grower.
7. The Director's levers never touch a player: no target, push or peace involves a human faction.
8. Only the great power's graduation sends a feed message; the rest is in the Chronicle.
9. Help is paid from the Director's one budget, so a busy turn of stories leaves less for empires.
10. Empires are drawn from the factions a player could have picked (`can_be_human()`), the factions
    with a legendary lord. A minor is chosen only when too few of those are left.
11. Shelter covers an empire's deeds against AI factions only. When it attacks a player, the
    Director defends the player as it does today.
12. Empires still answer a player's own deeds, more often than other neighbours, as the ambitious
    factions do today.
13. The levers never aim one empire at another. If one falls anyway, it is replaced.
14. The optional cheats (6b) are three steps, Natural, Generous and Relentless, and the top step
    settles only abandoned ruins, never a settlement someone holds.

## 13. Left to the builder

`EMPIRE_SPREAD` and how distance is measured; how "weakest" is measured for a settlement and for a
neighbour; the beat prices; the log lines; and the MCT text.

## 14. As built (2026-11-15)

Built from `docs/superpowers/plans/2026-11-15-director-empires.md`. Every ruling is in the plan's
ledger; the ones that change what this spec says are below.

**The live spike changed two things.**

- **No war target.** The payload builder's `war_coordination_target` returned `false` for every
  shape tried on vanilla Immortal Empires, turn 1: Laurelorn at war with the Black Pit and Red Cloud
  at war with Carcassonne, both about 30 apart; offensive and defensive; the town's owner first; an
  army as the target; and the player's own faction. `apply_payload` raised nothing, so a beat built
  on it would have charged the budget and set nothing. No documented `cai_` call aims an AI at a
  town (`docs/CAMPAIGN_AI.md` lists only the suppression levers), so the beat is removed, not
  switched off. What stays is section 6.2's condition: an empire with a war against an AI neighbour
  is left to fight it, and one with none gets the hostile stance push. Peace still skips the weakest
  enemy next door, the war it can win.
- **`IE_REGIONS` is 572**, what `region_list():num_items()` counts on vanilla Immortal Empires, not
  the DB's 644. On the 644 the goals would have been 11% high. Realm of Chaos now asks about 24 and
  12 of its empires, from the DB's 279, which the live game has not measured.

**Smaller changes from sections 4 to 9.**

- Replacement measures growth against the oldest of two snapshots, one per check, so "the last 20
  turns" holds. A faction once chosen is never chosen again. A dead empire with no grower to take
  its place is dropped, and an empty place is filled at the next check that finds one.
- A stalled empire's replacement must be spread from the other empires only, not from the one it
  replaces.
- Both merge routes go through one `merge_first(who, candidates, sit, mode)`: the gates (merge
  turn, merges per turn, price), `merge_blocked`, the probe limit and the willing ask. `try_merge`
  and `empire_merge` only build their candidate pairs. A first build repeated the gates, and the
  mutation run found nine mutants that had stopped running because of it.
- The roll names the great power and saves it, so the first turn start does not re-rank the three.
  Live, a town taken on turn 1 tied two of them and the title moved on turn 2 while the Chronicle
  still named the first.
- The Chronicle's fade line reads "The ambitions of {i} came to nothing." A possessive on a faction's
  name drew "The Terrors of the Dark Straits's" in the preview.
- `cm:create_force` is called the 9.0 way, `(faction, units, region, x, y, true)`: CA's wrapper
  makes the id itself and refuses a sixth argument that is not a boolean.

**The first soak** (2026-11-15, Immortal Empires, the player Astragoth shielded and kept out of
every war, natural help, turns 1 to 80 with one reload from the turn-17 autosave). The Director
logged no error.

| Turn | What happened |
|---|---|
| 1 | Yvresse, the Wood Elves and the Cult of Sigmar set out |
| 20 | The Cult of Sigmar was dead: Clan Mors, the fastest grower, replaced it and, at 12, took the title |
| 28, 46 | Clan Mors took in Clan Verms and Clan Rictus by last-stand merges |
| 40 | The Wood Elves had stalled: Golgfag replaced them |
| 49 | Golgfag reached the lesser goal, 25 |
| 50 | Clan Mors 20 of an expected 28.6, Yvresse 9 of 14.3. The largest AI factions held 24 |
| 54 | Yvresse, far behind: peace with the Cult of Pleasure, and Avelorn joined it (17) |
| 57 | Clan Mors, far behind: peace with the Last Defenders, and Clan Carrion joined it |
| 60 | Clan Mors had stalled: Naggarond took the title |
| 80 | Naggarond 37 of 50, Yvresse 17 of 25, Golgfag 27. Clan Pestilens, never an empire, 43. Budget 322 unspent |

Nobody reached 50 by turn 80. Two reasons, both in this design: an empire behind but not far behind
got only a stance push, and only with no war next door, which is almost never; and the title stayed
among the three, so neither a graduate that kept growing nor the fastest faction on the map could
hold it. Section 15 is the author's answer.

## 15. The great power plays to win (amendment, approved 2026-11-15)

The author's ruling on the first soak: "both and gives smarter decisions for that AI", then "Build
all of it". This section overrides sections 4 to 6 where they differ, and lifts section 6's ban on
personality changes for the one case below. Lesser empires are unchanged.

**1. Help from behind.** The great power gets section 6's peace and kin levers whenever it is behind,
not only far behind. Same prices, same cadence (`HELP_EVERY`, and one merge every
`EMPIRE_MERGE_EVERY`).

**2. The title follows the winner.** At each check, after the replacements, the largest AI faction
on the map that could be an empire takes the title if it holds more settlements than the great
power. It must pass the strict candidate test (section 4), must not be a measured runaway or an
invader (`runaway_keys(1)`, the factions no merge may feed), and, if it is not already an empire,
must be spread from the two empires that stay. The old great power becomes a lesser empire. A
newcomer takes the place of the weakest lesser empire, which fades; an empire promoted from lesser
loses its lesser graduation, since its goal is now the great one. A great power that has reached
the great goal keeps the title. Ties change nothing.

**3. Smarter decisions.**

- **A warlike temper.** When a faction becomes the great power and its race plays passively, it
  takes its race's `_endgame` personality, `cm:force_change_cai_faction_personality`, the call CA's
  endgame crises make on living majors (`crisis_grudge_too_far.lua:76`). Six races, chosen from the
  strategic profiles their lords carry in `cai_personalities`:

  | Subculture | Its lords play | Becomes |
  |---|---|---|
  | `wh2_main_sc_skv_skaven` | cowardly | `wh3_combi_skaven_endgame` |
  | `wh_main_sc_dwf_dwarfs` | defensive, holds grudges | `wh3_combi_dwarf_endgame` |
  | `wh_main_sc_emp_empire` | default | `wh3_combi_empire_endgame` |
  | `wh_main_sc_vmp_vampire_counts` | vampire | `wh3_combi_vampire_endgame` |
  | `wh_dlc05_sc_wef_wood_elves` | defensive | `wh3_combi_woodelf_endgame` |
  | `wh2_dlc09_sc_tmb_tomb_kings` | half defensive | `wh3_combi_tombking_endgame` |

  The races already aggressive keep their own. High Elves (aloof) have no endgame personality and
  keep theirs. It happens once per faction and lasts: no call reads a faction's personality, so it
  could not be put back, and CA's crises never do. If the live test shows an endgame personality
  governing badly, the switch ships off and the rest of this section stands.
- **One war at a time.** Section 6's peace already asks a stronger enemy for peace while the great
  power fights the weakest one next door. With no war next door, it gets the hostile push at its
  weakest neighbour as before, and now also a friendly push toward its strongest AI neighbour that is
  not an empire, so it does not open a second front.

**The pass mark** for the next soak: a faction at 50 settlements by turn 80 on Immortal Empires, the
great power the largest AI faction at turn 80, and no Director error.

## 16. The great power's pace, by script alone (amendment, approved 2026-11-15)

The second soak (section 15 in force) passed at turn 50, with the great power on schedule and the
largest AI faction, but nobody reached 50 by turn 80 or 100: the leaders levelled off at 40 to 43.
A turn-99 reading of every AI's main rival (CCO `MainRivalDiplomaticThreatLevelContext`) found 30
of 32 naming the Chaos invasion and none the great power, so a lower threat score and more peace
had nothing to act on. What limits it is its own campaign AI's pace. The author's ruling: "avoid
memreader, and do the script changes" - no database rows, no memory patching.

**1. A raised potential.** While a faction holds the title, its total potential is set to 750 with
`cm:faction_set_total_potential_override_value(faction, true, 750)`, CA's own lever for a rival it
builds up (`wh3_campaign_ai.lua` raises the Western Provinces to 210 when Bhashiva is the player).
Undocumented; measured live: `true` sets the total outright and `(faction, false, 0)` restores the
game's own value exactly. Majors ran 350 to 555 at turn 99, so 750 sits above any of them. Handed
back when the title moves, and when the Empires switch is turned off mid-campaign.

**2. Sieges pressed.** When the great power besieges an AI settlement (`CharacterBesiegesSettlement`)
with an army at least 1.5 times the garrison army's strength, it is ordered to assault at once with
`cm:attack_region`, as CA's turn-one openings do, instead of sitting the siege out. Autoresolve still
decides it. Never a player's settlement; the budget's mood price.

**The test** is a soak of up to 30 turns from soak 2's turn-99 save, looking for an effect on the
great power's army count, its sieges and its growth.

**What the tests found (2026-11-16).** Two 10-turn runs from the turn-99 save, one with both levers
switched off in the session: the Host of Nagash fell from 42 to 37 settlements in both, and the run
without the levers ended with the Cult of Pleasure at 49 against 35 in the other, so one run's spread
is larger than anything the levers did there. Nagash besieged nothing in the run with the levers on.
A third soak from turn 1 to 30 (same roll, Relentless help) showed the press working: nine sieges
pressed, six of them captured in the same second (Parravon, Montfort, Bordeleaux, Ruins End, Lybaras,
Bitterstone Mine), two sacked, one unresolved. Clan Mors's whole net gain from turn 20 to 30 (12 to
15) came from pressed sieges. Three more sieges at good odds went unpressed on an empty budget. No
cheat fired: on the 80-turn schedule nobody fell under 60% of it, and Clan Mors at 15 on turn 30
counted as ahead, so it got no help at all. The potential showed no measurable effect; it stays,
by the author's ruling ("still add").

## 17. Pace changes (amendment, approved 2026-11-16)

The author: "do 1 and 2".

**1. 50 by turn 50.** `empire_goal_turn` defaults to 50 (was 80; the slider still runs 40 to 150).
The schedule still counts from turn 10, so on Immortal Empires the great power is expected to hold
25 settlements on turn 30 and 50 on turn 50, and the help and the cheats start when it falls behind
that.

**2. Every empire presses its sieges, for free.** Section 16.2 applies to every living empire, not
the great power alone, and no longer charges the budget. Still never a player's settlement, still
at 1.5 times the garrison army's strength.

**Soak 4 (2026-11-16, section 17 in force, Relentless help, turns 1 to 50, same roll).** 39 sieges
pressed by all three empires, 4 held. The cheats fired for the first time in any soak (turns 25,
29, 33, 39 and 44). Avelorn took the title on turn 20 and held 16 of 25 on turn 30, 25 of 37.5 on
turn 40 and 35 of 50 on turn 50: no faction at 50, but the great power the largest AI faction by 13
and the best turn-50 total of the four soaks (20, 28, 35). No Director error.

**3. The cheats every 5 turns** (author, 2026-11-16: "add that as default"). `CHEAT_EVERY` is 5,
was 10: Avelorn gained about 10 settlements every 10 turns against a schedule rising 12.5. The
cheats stay off unless chosen in MCT.

**Soak 5 (2026-11-16, the cheats every 5 turns, otherwise as soak 4).** 42 sieges pressed, 3 held.
The Caravan of Blue Roses rose when the Cult of Sigmar faded on turn 30 and took the title from
Avelorn on turn 50 with 29; Avelorn got three cheats against soak 4's two and ended on 26. Largest
AI faction on turn 50: 30, against soak 4's 35. One run's spread decides more than the cadence
does. A great power on an island (Avelorn on Ulthuan) gets its army copies at its capital, far
from anything left to take. No Director error.

**4. Relentless is hidden (2026-11-16, author: "apply and test it out during a soak").** Relentless no
longer copies an army or hands over a ruin, since both are visible. Instead an empire behind
schedule runs a hidden economy, the way CA's own AI background bonuses do (`wh3_campaign_ai.lua`
1012): a runtime bundle on `wh_main_bundle_dummy` with upkeep -30%, recruitment cost -30%, income
+30%, construction cost -30%, replenishment +10% and one more recruitment slot per army, all in
`unseen` scopes. It is taken away when the empire catches up, loses its place, or the setting or
the Empires switch goes off. Under Relentless an empire's kin merges have no 10-turn wait, no
per-turn limit and no price; a last stand still pays.

**Soak 6 (turns 1 to 50, same roll).** The bundle was on the Wood Elves with all six effects by
turn 15. Noctilus (Vampire Coast, which the game never lets confederate) took the title on turn 20
and ended on 28 of 50 with 20 armies; the Oracles of Tzeentch, a lesser empire, ended on 16 with
16 armies and 313,515 gold unspent. More money and armies did not become more settlements: the AI
hoards gold, and its conquest rate is not bound by what it can afford. 47 sieges pressed, 1 held.

## 18. Better picks and the stall rule (amendments, 2026-11-16 and 2026-11-17)

**1. Better picks (author: "better picks first").** An empire grows fastest by taking in its kin, so
a good pick is a faction whose race may confederate under computer control (in
`derpy_director_merge_races`, switched on in MCT, and not Vampire Counts, Vampire Coast or Chaos
Dwarfs, which the game refuses) with at least two living computer kin. The dead, players, rebels,
vassals and invaders are no kin. The roll draws good picks first and the great power is the largest
of them; a faction taking the title as a newcomer must be one.

**Soak 7 (turns 1 to 50).** The Great Orthodoxy (Kislev, seven kin), Yvresse and Tlaqua; the
Orthodoxy had 15 on turn 25, the best turn 25 then. It was faded on turn 40 for a smaller faction,
grew on alone and ended as the largest computer faction on 25.

**2. A stalled empire gives way only to a larger faction (author: "make the fix").** Soak 8, same
roll: the Orthodoxy was again faded on turn 40, this time for Schwartzhafen (Vampire Counts, no kin,
20 against about 17), and again ended as the largest computer faction, on 28, the great power on 27.

**3. ...only to a larger good pick, and never the largest empire (author, 2026-11-17: "do both").**
The largest empire is never faded for stalling; a stalled empire that is the largest computer
faction is the largest empire, so that case needs no check of its own. Ties protect both. A dead
empire's place still goes to the fastest grower, good picks first, because an empty place helps
nobody.

**Soak 9 (turns 1 to 50, same roll).** The Orthodoxy had 17 on turn 25 and kept the title all game,
ending on 30 of 50, the largest faction on the map, with 18 armies and 459,256 gold unspent. It took
in the Ice Court and Ropsmenn and has no kin left. Tlaqua gave way to Clan Mors on turn 30 (17 on
turn 50) and Yvresse, after taking in Saphery and Ellyrion, to Sayl on turn 40 (22). 36 sieges
pressed, 1 held. No Director error. What holds it back now is conquest: the kin lever is spent and
the gold is not spent.
