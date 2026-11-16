# Changelog

## 2026-11-16, empires

- New: three computer factions a campaign set out to build empires, a great power aiming for 50 settlements by turn
  50 on Immortal Empires and two lesser ones for 25. An empire behind schedule gets peace on a losing front, kin who
  join it, a hostile stance towards its weakest neighbour and, for the great power, a friendly one towards its
  strongest. An empire that dies or stalls is replaced, and the great power's title passes to the strongest.
- An empire storms every siege it lays once its army has 1.5 times the garrison's strength, instead of waiting the
  siege out. A player's settlements are never stormed this way.
- The great power takes an endgame personality where its race has one, and a raised faction potential while it
  holds the title.
- The empires are kept out of the runaway power's measurement while they are behind schedule, so the Director does
  not build one up and punish it in the same campaign.
- Optional cheats in MCT, off by default: Generous pays an empire far behind 5,000 gold, and Relentless also gives it
  a copy of its largest army and an abandoned settlement next to its land, at most once every 5 turns.
- The World Chronicle lists the empires' rise, fall and goals.
- Five new MCT options: the empires switch, both goals, the goal turn and the cheats.

## 2026-11-15, the World Chronicle

- New panel: the World Chronicle. It lists what happened this campaign, newest first and grouped by turn, under the
  campaign's temperament, old hatred and ambitious factions. Its button sits beside the resource bar, or in the
  shared button hub when another of Derpy's hub mods is installed.
- A war is listed with its cause when the Chronicle already records one: a sack, a betrayal, a seized convoy and the
  rest, or fear of a runaway power. Wars with no recorded cause are left out.
- The defensive alliance line now says who it is against, and how much gold each side raised for the war when the
  alliance was funded.
- A story no longer says neighbours turned against a faction when the Director had no budget left to turn them.
- The Chronicle replaces the old 50-entry news buffer, which is cleared from a save the first time the Chronicle
  writes. It holds the newest 100 entries.

## 2026-11-14, first public release

- The Coalition Supervisor is part of the Director. The runaway power's threat score, its grudge and the defensive
  alliances against it now come from the Director, and the Supervisor's own pack is gone.
- The Director now decides which computer factions confederate. A faction down to its last settlement can join
  stronger kin, and kin can unite against a runaway power or one of CA's endgame invasions. Only what the game itself
  allows, never a player's faction, and never Chaos Dwarf houses while a player plays Chaos Dwarfs.
- An MCT settings page with 34 options. Multiplayer always uses the defaults.
- Fixed: with more than one confederation allowed a turn, only one happened on every turn after the first.
- Fixed: a runaway power that had not yet reached the confederation setting's step could still take in a dying
  faction.
- Fixed: switching the runaway threat off mid-campaign now lifts it on the next turn.
- Fixed: a runaway's grudge for a new step is no longer lost when nobody near it has met each other yet.
- A fault in the runaway step no longer stops the opportunity roll that follows it.
- "Too early" is logged once a turn instead of once for every last stand before the first confederation turn.
