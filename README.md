# The Director

A campaign mod for **Total War: WARHAMMER III** that makes the world react to what factions do. When a faction sacks
a town, breaks a treaty or grows far larger than everyone else, the factions that would plausibly care take notice.
They turn hostile to the aggressor, sign pacts against it and hold grudges, and a dying faction can join its own kind
rather than be wiped out.

The Director has no Steam Workshop item yet. This repository is its source: the campaign script, the generator that
bakes its lore table and settings page, the Lua test harness, the mutation runner, the live-game probes and the
design record.

## What it does

- **Neighbours notice.** Sacks, razes, conquests, confederations and broken treaties become situations. The Director
  picks the factions that would care, by culture, distance and history, and changes what the campaign AI already
  reads: their stance towards the aggressor, a defensive pact between them, a lasting grudge. The player is told in
  the event feed when the world turns against them.
- **One budget.** Every reaction is paid for from a pool that refills each turn, and the permanent ones cost the
  most, so the world answers a few stories each turn instead of everything at once.
- **A storyteller.** Each campaign rolls a temperament (rising, patient or wild), a pair of cultures that hate each
  other, and three ambitious factions. They are saved with the campaign and never rolled again, so no two campaigns
  play quite the same.
- **Opportunism and treachery.** A faction that lost land by force may be set upon by those who hate it, and a broken
  alliance or non-aggression pact is answered.
- **A runaway power.** When one faction holds 1.75 times as many settlements as the next largest, the AI treats it as
  a growing threat in three steps. Each time it climbs a step, the factions that have met it gain a grudge against
  it, and while it leads, those that would accept a defensive alliance with each other sign one, at most two a
  turn. The threat is lifted when its lead collapses; the grudges and alliances stay, as they would after any war.
- **Confederations.** A computer faction down to its last settlement folds into stronger kin of its own race. When a
  runaway power, or one of CA's endgame invasions, takes a town, the defender's kin confederate to face it, the
  larger taking in the smaller. Only what the game itself would allow happens, and never to a player's faction. In
  a 56-turn test campaign, eight factions joined their kin this way.
- **Settings.** An MCT (Mod Configuration Tool) page with 34 options: each trigger, the cost, the per-turn limit, the
  first turn, and a switch per race. Multiplayer always uses the defaults, so two players cannot fall out of step.
- **Works with Derpy's other mods when they are installed**, with no edit to them: Resource Overhaul's seized
  convoys become situations, kin-slaying costs Great Guilds temple Reputation, and Iron Court secessions become
  situations.

## How it works

The campaign AI has no central brain to persuade. It is a set of departments, each reading its own inputs, so the
Director changes those inputs instead of fighting the AI: diplomatic stances, forced defensive alliances, past
diplomatic events, the AI's threat score for a faction, and confederation through a payload, the route CA's own
Tower of Zharr seats use. `docs/CAMPAIGN_AI.md` and `docs/DIPLOMACY.md` are the research behind every one of those
levers.

Before any confederation, the Director asks the game whether each side would accept the deal. That answer honours
CA's own locks: Vampire Counts, Chaos Dwarfs and Vampire Coast are refused, and so is a faction inside CA's ten-turn
pause after a confederation. Willingness is not required by default, because in live tests every score came back far
below zero even for pairs the game allows.

This repository also holds the **Coalition Supervisor**'s history. It was a separate mod for the runaway power; it
was merged into the Director on 2026-11-14 and deleted, and its design and session notes are kept in `docs/`.

## What is here

```text
Modding Files/pack/script/campaign/mod/derpy_director.lua        the campaign script
Modding Files/pack/script/campaign/mod/derpy_director_lore.lua   generated: CA's cultural relations, MCT defaults, races
Modding Files/pack/script/mct/settings/derpy_director.lua        generated: the MCT page
Modding Files/source/director_feed/*.tsv                          generated: the event-feed rows and their text
Modding Files/source/director/probes/                             live-game probes and the soak statistics
tools/build_director.py                                           generator, Lua harness and packer
tools/mutate_director.py                                          the mutation runner
tools/*.py, tools/wh3_player_shield.lua                           what those two need, and the soak's player shield
docs/superpowers/specs, docs/superpowers/plans                    designs and plans, the Supervisor's included
docs/history/                                                     the session handoffs, in order
docs/CAMPAIGN_AI.md, docs/DIPLOMACY.md                            the campaign AI and diplomacy, measured
```

The generated files are committed so the repository reads without running anything. `py tools/build_director.py
--check` rewrites them from CA's tables in your own install; a clean `git diff` afterwards means nothing has drifted.

## How it is tested

- **The shipped script, run for real.** `py tools/build_director.py --selftest` runs `derpy_director.lua` under
  Lua 5.1.5 against a stubbed campaign: factions, regions, events, saves, MCT and the deal probe. It reads back every
  engine call the script made and asserts on those calls, not on a re-implementation. The stubbed events take the
  shapes CA documents and uses, because an earlier, friendlier stub once let a call the real event does not have
  pass every test and then fail in game.
- **Every rule, broken on purpose.** `py tools/mutate_director.py` breaks the script one rule at a time (a guard
  removed, a limit lifted, a sort dropped, a key misspelt), runs the self-test against each break, and restores the
  file. A break the self-test does not notice is a missing test. The current run: 214 breaks, all caught.
- **In the game.** A 56-turn campaign as Karl Franz on Very Hard, with the player kept out of wars, followed by
  forced last stands on that world. The results are in section 8 of
  `docs/superpowers/specs/2026-11-14-director-merges-coalitions-design.md`, including a bug the run found and the
  test that now pins it.

## Running it

You need:

- Python 3 with `zstandard`, and [Lua 5.1.5](https://luabinaries.sourceforge.net/). The scripts expect Lua in
  `C:\Program Files (x86)\Lua\5.1\`;
- a Total War: WARHAMMER III install. The paths point at the author's Steam library: `DB_PACK` in
  `tools/read_vanilla_db.py` and `GAME` in `tools/read_vanilla_loc.py`;
- [RPFM](https://github.com/Frodo45127/rpfm)'s WH3 schema (`schema_wh3.ron` in its config folder), which the database
  reader uses, and RPFM's server to build the pack or the vanilla cache;
- the vanilla table cache, which both `--check` and `--selftest` read. Fetch it once with
  `py tools/fetch_vanilla_tables.py campaign_cultural_relations`.

Two checks need CA's own files, which are not published here, and the self-test skips each one and says so when they
are absent: the API check reads CA's scripting docs from the Assembly Kit in
`Modding Files/reference/ca_script_docs_wh3/`, and the invader-key check reads CA's shipped episode and crisis scripts
in `Modding Files/reference/ca_scripts_wh3/`.

`py tools/build_director.py` builds `Modding Files/Modpacks/derpy_director.pack`. The probes run inside a live
campaign through the WH3 MCP bridge (`loadfile`, then call, inside a `pcall`).

## Credits

The temperaments are modelled on RimWorld's storytellers. The approach to the campaign AI follows CA's own talk on
analysing its AI's behaviour.

## Licence

MIT, see `LICENSE`.

This is an unofficial fan mod. Warhammer is a trademark of Games Workshop. Total War and Total War: WARHAMMER III are
trademarks of Creative Assembly and SEGA. Nothing of theirs is published here: no art, no game files, no database
tables, and none of CA's scripts or documentation. The lore table holds numbers the generator reads from your own
install.
