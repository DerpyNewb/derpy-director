# Diplomacy

What is moddable in WH3 diplomacy, what the ceilings are, and what the highly-rated Workshop
mods actually do. Everything below was measured on 2026-09-17 against the shipped game:
vanilla rows out of `.skilltree_cache` via `tools/read_vanilla_cache.py`, the API out of
`Modding Files/reference/ca_script_docs_wh3/`, and the mod evidence out of the 681 `.pack`
files installed on this machine, read with `tools/read_pack_index.py`.

`docs/CAMPAIGN_AI.md` is the companion and takes priority where the two overlap: it covers the
campaign AI's architecture, the diplomatic-event -> attitude -> stance -> behaviour chain, and
the `cai_*` write calls. This file covers the diplomacy *system* — the deal menu, the deal
evaluator, and what a mod may change about them.

---

## 1. The six layers, and which one you actually want

Diplomacy is not one system. Six separable layers ship under the name, and almost every
"diplomacy is broken" complaint belongs to exactly one of them. Pick the layer before picking
a table.

| Layer | What it decides | Where it lives | Moddable? |
|---|---|---|---|
| 1. **Deal menu** | which of the 27 diplomacy types are offerable between two parties | `cm:force_diplomacy` (Lua) | Yes, fully |
| 2. **Attitude** | the number on the diplomacy screen | `cai_personality_diplomatic_event*`, `cai_personality_cultural_relations_overrides` | Yes |
| 3. **Attitude bands** | where "friendly" starts | `diplomatic_relations_attitudes` (7 rows) | Yes, trivially |
| 4. **Deal evaluation** | whether the AI says yes | `cai_personality_deal_evaluation_*` (~1,100 rows) | Yes, this is the real one |
| 5. **Deal generation** | what the AI offers you unprompted | `cai_personality_deal_generation_*` (217 rows) | Yes |
| 6. **Dialogue** | the words and the voice line | `diplomacy_strings`, `diplomacy_negotiation_string_options`, `campaign_group_member_criteria_diplomatic_attitudes` | Yes, and it is enormous |

**The most-modded tables are layer 6, and that is a trap for a reader surveying the Workshop.**
Of the 28 installed Workshop mods that touch any diplomacy table, the top three tables by mod
count are `campaign_group_member_criteria_diplomatic_attitudes` (18 mods),
`diplomacy_negotiation_string_options` (13) and `diplomacy_strings` (11). None of those change
behaviour. They are the negotiation voice-over: any mod adding a faction or subculture needs
rows there or its envoys are mute. Counting mods per table ranks the dialogue layer first and
the behaviour layer last, which is the opposite of what a diplomacy mod is for.

---

## 2. Layer 1 — the deal menu is Lua, not DB

This is the single most important structural fact, and it is not obvious from the table names.

`diplomatic_action_subculture_restrictions` (26 rows) and
`diplomatic_action_faction_restrictions` (4 rows) sound like the per-culture restriction tables.
They are not. Both carry exactly two columns beyond the key:

```
diplomatic_action_subculture_restrictions  v1: can_make_confederations, can_make_vassals, subculture
diplomatic_action_faction_restrictions     v1: can_make_vassals, can_make_confederations, faction
```

Confederation and vassalage. That is the whole DB vocabulary. **There is no DB table that stops
the Empire signing a non-aggression pact with the Skaven.** Every mod that does this does it in
Lua, through `campaign_manager:force_diplomacy`.

### The shipped idiom

`!!!awd_vanilla_plus_expanded.pack` and `!!!hecleas_grand_strategy.pack` both ship
`doo_diplomacy_options_overhaul.lua` — 128 KB of nothing but this call, 721 and 929 instances
respectively. The pattern, verbatim from the shipped file:

```lua
cm:add_first_tick_callback(function()
    local ALL_BUT = "trade agreement,hard military access,cancel hard military access," ..
        "military alliance,technology,state gift,payments,vassal,peace,war,break trade," ..
        "break alliance,hostages,non aggression pact,soft military access," ..
        "cancel soft military access,defensive alliance,client state,form confederation," ..
        "break non aggression pact,break soft military access,break defensive alliance," ..
        "break vassal,break client state,state gift unilateral"

    cm:force_diplomacy("culture:wh_main_vmp_vampire_counts", "culture:wh_main_emp_empire",
                       ALL_BUT, false, false, true, true)
    cm:force_diplomacy("culture:wh_main_vmp_vampire_counts", "culture:wh_main_emp_empire",
                       "war", true, true, true, true)
end)
```

Deny everything, then re-permit the handful that stays in fiction. Note three things CA's own
documentation does not say:

- **The `type` parameter takes a comma-separated list.** CA's doc says "Type of diplomacy to
  restrict", singular, and the underlying `cm:force_diplomacy_new` takes a bitmask. The
  campaign_manager wrapper splits on commas. 721 shipped calls rely on it.
- **These mods pass `true` for the 7th argument**, which force-restricts "payments". CA's doc
  warns in as many words that "this may cause crashes" because the AI assumes payments are
  always available. Two mods with 21,000 and 5,000 lifetime subscribers ship it anyway and the
  reports do not mention crashes. Treat it as empirically survivable, not as documented-safe:
  CA wrote that warning about their own AI code, and it is the kind of thing a patch can make
  true again.
- **Specifiers are `all`, `faction:<key>`, `subculture:<key>` or `culture:<key>`.** Culture is
  the coarse one (`wh_main_vmp_vampire_counts`), subculture the fine one
  (`wh2_main_sc_def_dark_elves`). They are different vocabularies and neither validates.

### The 27 diplomacy types

From `cm:force_diplomacy_new`'s bitmask table — this is the authoritative list, and it is the
one the comma-separated string names in words:

| Type | Bit | Type | Bit |
|---|---|---|---|
| trade agreement | 2^0 | war | 2^10 |
| hard military access | 2^1 | join war | 2^11 |
| cancel hard military access | 2^2 | break trade | 2^12 |
| military alliance | 2^3 | break alliance | 2^13 |
| regions | 2^4 | hostages | 2^14 |
| technology | 2^5 | non aggression pact | 2^15 |
| state gift | 2^6 | soft military access | 2^16 |
| payments | 2^7 | cancel soft military access | 2^17 |
| vassal | 2^8 | defensive alliance | 2^18 |
| peace | 2^9 | client state | 2^19 |
| form confederation | 2^20 | break non aggression pact | 2^21 |
| break soft military access | 2^22 | break defensive alliance | 2^23 |
| break vassal | 2^24 | break client state | 2^25 |
| state gift unilateral | 2^26 | | |

`diplomatic_actions` (v0, 34 rows) holds the option keys the UI sorts —
`diplomatic_option_trade_agreement` and friends, in 4 categories. It is a display and ordering
table. **Deleting a row there does not remove the option**; the bitmask above is what gates it.

### The hard DB gate, for the two cases it covers

`diplomacy_disabled_between_factions` (v1, 3 rows) turns diplomacy off wholesale between a
campaign group and a faction set. Vanilla uses it exactly three times — Daemons of Chaos,
Kurgan warbands, Realm factions. It is a campaign-group-to-faction-set junction, so it needs
both objects to exist; it is the blunt instrument, not a per-option gate.

---

## 3. Layer 3 — the attitude bands are 7 rows

`diplomatic_relations_attitudes` (v0) is the entire scale the diplomacy screen draws against:

```
hostile          -230
very_unfriendly   -70
unfriendly        -30
neutral             0
friendly           30
very_friendly      70
best_friends      230
```

Seven rows, two columns. This is the highest leverage-per-row table in the whole system and
**nothing** touches it: zero of the 416 installed Workshop mods, and only CA's own `db.pack`. Widening the
bands makes attitude changes feel slower without touching a single AI value; narrowing them
makes the AI's existing attitude drift cross thresholds it currently never reaches.

The asymmetry is load-bearing and worth reading before you change it: the outer bands are
**3.3x** the width of the inner ones (160 points from `very_friendly` to `best_friends`, 40
from `friendly` to `very_friendly`). "Best friends" is deliberately far away.

---

## 4. Layer 2 — moving attitude

Two independent sources, and they compose.

### 4a. Events — 104 of them, and the magnitude is not in your call

`cm:cai_add_diplomatic_event(from_key, to_key, action_key)` takes a key from
`cai_personality_diplomatic_events` (v4, **104 rows**). See `docs/CAMPAIGN_AI.md` §3 for the
chain this feeds. The call has no strength argument: the magnitude lives in
`cai_personality_diplomatic_event_values` (v0, **198 rows**, columns `component_id`,
`event_id`, `falloff`, `value`), keyed by personality component. `wh3_default` covers most of
it — for example `ALLY_REFUSED_TO_JOIN_WAR` is `-30.0` with a `falloff` of 25 turns.

So: **to change how much an event hurts, edit the values table; to fire one, call the API.**
Editing the events table itself only changes which of the 28 `diplomatic_factor_*` groups the
event is filed under, which is what the diplomacy screen tooltip groups by.

The 28 factor groups are the tooltip vocabulary: `agent_actions`, `broken_treaties`, `caravan`,
`confederation`, `confederation_subculture_penalty`, `cultural_differences`,
`cultural_differences_personality`, `cultural_similarities`,
`cultural_similarities_personality`, `dilemma_events`, `expansion`, `gifts`, `liberation`,
`past_events`, `past_treaties`, `past_war`, `raiding`, `rebellion`, `reinforcements`,
`renounced_allied_slot`, `rituals`, `technology`, `treaties`, `trespass_warning`,
`trespassing`, `ultimatem` (CA's spelling), `war`, `war_atrocities`.

`cm:apply_dilemma_diplomatic_bonus(a, b, n)` is the blunt alternative: `n` from -6 to +6,
mapping to `PENALTY_XXXLARGE` through `BONUS_XXXLARGE`. No DB row needed, no fiction attached.

### 4b. Cultural aversion — 83 rows, and most pairs are empty

`cai_personality_cultural_relations_overrides` (v1, **83 rows**) is the race-hates-race matrix
that "loreful diplomacy" mods mean when they say aversion:

```
attitude_base | component_id | negative_attitude_multiplier | positive_attitude_multiplier | source | target
50.0          | anti_chaos   | 0.75                         | 1.5                          | wh2_main_sc_hef_high_elves | wh_main_sc_dwf_dwarfs
```

`attitude_base` is a flat offset (measured range -100 to +50 across 11 distinct values), and the
two multipliers scale how hard later positive and negative events land. That second half is the
subtle one: a pair can start neutral and still be effectively unreachable because every good
thing you do is multiplied by 0.75 and every bad thing by 1.5.

**It is an override table, and it is mostly empty.** 83 rows across **16 source subcultures**,
in a game with roughly 45. Every pair with no row defaults to 0 and a multiplier of 1.0. Ogres,
Khorne, Nurgle, Tzeentch, Slaanesh, Chaos Dwarfs as a *source*, and every modded subculture have
no rows at all. That is not a gap to be filled carelessly — it is why Ogres will deal with
anyone — but it is enormous headroom, and it is the cheapest place to give a modded culture a
personality.

The `component_id` column points at `cai_personality_cultural_components` (v2, 25 rows), which
carries four multipliers of its own plus the `short_description`/`long_description` loc keys
the diplomacy screen shows. A new component is 1 row plus 2 loc strings.

---

## 5. Layer 4 — deal evaluation, where "the AI never accepts anything" lives

This is the layer worth your time, and the one with the most measurable slack.

### 5a. `cai_personality_deal_evaluation_components` — 82 rows, 25 dead columns

v16, 82 rows (one per race, times major/minor/base), 32 columns. Measured distinct values per
column across all 82 rows:

```
id                                                        82  varies
max_payment_value                                          2  {15.0, 30.0}
payment_offered_multiplier_under                           2  {5.0, 10.0}
payment_requested_multiplier                               3  {1.0, 2.0, 4.0}
payment_offered_multiplier_over                            2  {20.0, 50.0}
war_break_treaty_bonus_towards_victory_region_owners       2  {0.0, 8.0}
peace_sign_treaty_penalty_towards_victory_region_owners    2  {0.0, 8.0}
...and the other 25 columns have exactly ONE distinct value across all 82 rows.
```

CA built a per-race deal evaluator with 32 knobs and then set 25 of them identically for every
race in the game. `peace_penalty`, `war_penalty`, `confederation_bonus`,
`recent_treaty_broken_modifier`, `trade_agreement_modifier_per_exceeded_trade_agreements`,
`min_gdp_for_payment_evaluation` — all uniform. This is the same pattern
`docs/CAMPAIGN_AI.md` §2 measures in `cai_personalities`: CA varies targeting and leaves the
behavioural knobs flat.

**Consequence for a mod:** these 25 columns are free differentiation. Changing one for a single
race is a one-row edit that no vanilla row is relying on being uniform, because nothing in
vanilla ever reads a difference there.

This is precisely what the "AI Diplomacy" mod's description is describing when it says "many of
the tables were severely truncated and had missing or nonexistent entries for many factions".

### 5b. `cai_personality_deal_evaluation_deal_component_values` — 823 rows, 35 columns

v17. The real scoring matrix: for each of 45 deal components (from
`cai_personality_deal_evaluation_deal_component_names`, e.g. `BREAK_MILITARY_ALLIANCE`,
`DEFENSIVE_ALLIANCE`, `CANCEL_TRADE_AGREEMENT`) times each personality component, a score at
each of the 7 attitude bands plus ~28 situational modifiers.

The columns worth knowing by name:

- `best_friends_value` ... `bitter_enemies_value` — the seven per-band base scores.
- `*_balance_factor` (peace / tension / war / total_war / last_stand) — how much the AI's own
  strategic context reweights this deal. These are the five contexts the whole `cai_*` system
  speaks in.
- `long_distance_penalty_min` / `_max` — Katsuko's "wars can't be declared from across the
  world anymore" is these two columns.
- `same_subculture_modifier`, `have_common_threat`, `main_threat`, `main_threat_ally`.
- `diplomatic_score_bound_lower` / `_upper` — vanilla is -5 / +5 on every row measured. This is
  the clamp on how far attitude alone can move a deal decision, and it is small.
- `existing_treaties_multiplier`, `recent_ultimatum_penalty_modifier`,
  `vassal_master_strength_multiplier`.

### 5c. The `is_player` column — CA scores you differently, and it is 9 rows

`cai_personality_deal_evaluation_deal_component_opponent_context_modifiers` (v2, 45 rows) has an
`is_player` boolean. **Nine rows have it set, and all nine are the `WAR` deal component.** No
other deal type gets a player-specific row. Measured, player row against its AI counterpart:

| personality | context | vs AI | vs player |
|---|---|---|---|
| `wh3_deal_eval_default` | peace | 0.0 | **2.0** |
| `wh3_deal_eval_default` | last_stand | -6.0 | **-9.0** |
| `wh3_deal_eval_default` | total_war | -3.0 | **-6.0** |
| `wh3_deal_eval_beastmen` | peace | 2.0 | **6.0** |
| `wh3_deal_eval_beastmen` | tension | 1.0 | **2.0** |
| `wh3_deal_eval_chaos` | peace | 0.0 | **4.0** |
| `wh3_deal_eval_chaos` | war | 0.0 | **-1.0** |

Every peacetime modifier is 2x to 4x higher against a human. If you want the one-line answer to
"why does everyone declare war on me", it is these 9 rows, and a diplomacy mod that ignores them
has not addressed the complaint most players are making.

**Caveat on direction.** The sign convention is inferred from the column being a modifier on the
`WAR` deal component's score, where a higher score means a more desirable deal. The peacetime
numbers read unambiguously (more war-inclined toward the player). The `last_stand` and
`total_war` numbers go the other way and could equally mean "an AI in its death throes
deprioritises new wars, more so against a player". **Verify in game before writing a changelog
line about the negative contexts.** The peacetime ones are safe to state.

### 5d. Layer 5 — what the AI offers unprompted

`cai_personality_deal_generation_generator_priorities` (v2, 139 rows) crossed with
`cai_personality_deal_generation_generators` (33) and `_components` (45). Generators have names
that read like intent — `DECLARE_WAR_ON_FACTIONS_I_DISLIKE`, `DECLARE_WAR_ON_NEARBY_FACTIONS`,
`BREAK_TREATIES_WITH_DISLIKED_FACTIONS`, `PEACE`,
`DEMAND_VASSALAGE_OR_CLIENT_STATE_FROM_ENEMIES` — and each carries a priority per strategic
context plus `failure_timeout`, `min_payment_cap`, `max_payment_cap`, `max_payment_pct`.

Per `docs/CAMPAIGN_AI.md` §2, diplomacy picks by **weighted random among good deals**, not
argmax. Priorities here are weights in that sample, so a 2x priority is not a 2x outcome, and a
priority of 0 is not a veto. To veto, restrict the option in layer 1.

---

## 6. The script API, complete

Every diplomacy call CA documents. The receiver convention differs per call and is not flagged
in CA's docs — see the CLAUDE.md rule. All of these take **faction key strings**.

| Call | Notes |
|---|---|
| `cm:force_diplomacy_new(src, tgt, bitmask, can_offer, can_accept)` | the raw one; CA says use the wrapper |
| `cm:force_diplomacy(src, tgt, types, can_offer, can_accept, [both], [force_payments])` | the wrapper; `types` is a comma list (§2) |
| `cm:force_make_peace(a, b)` | raises **no** `PositiveDiplomaticEvent` (measured 2026-10-19), so a peace listener cannot be tested by script |
| `cm:force_declare_war(attacker, target, invite_attacker_allies, invite_defender_allies)` | raises `NegativeDiplomaticEvent` **synchronously**, attacker as proposer and target as recipient; breaks through a `force_diplomacy` war lock; an invited AI ally broke its alliance (a war=false event first) rather than join. Measured 2026-10-19, `sessions/LIVE_TEST_20261019_IRON_COURT_WAR_CLAIMS_SECRETS.md` |
| `cm:force_alliance(a, b, is_military)` | `false` = defensive alliance |
| `cm:force_confederation(a, b)` | **crashes if a == b**; always self-check. **Since the 2026-10-09 patch it silently does nothing for Chaos Dwarfs**, AI or human, vanilla or `cr_` factions, with or without a `form confederation` force_diplomacy first; Greenskins AI to AI still land in under 5s - use the payload row below |
| `cm:create_payload()` + `p:form_confederation(absorber, target, awake_from_death, convert_agent_types)` + `cm:apply_payload(p, absorber)` | confederates in under 0.5s, measured 2026-10-10. `FactionJoinsConfederation` fires **inside** `apply_payload`. Interfaces, not keys. `zz_derpy_toz_annex.lua`'s `confederate()` is the working consumer |
| `cm:force_grant_military_access(granter, recipient, is_hard)` | CA: hard access "is currently unused" |
| `cm:force_make_trade_agreement(a, b)` | "If no agreement is possible then nothing will happen". A scripted agreement raises no `PositiveDiplomaticEvent`, and a declaration's event fires after the agreement is already gone, so snapshot trade partners first (measured 2026-10-19) |
| `cm:force_make_vassal(master, vassal)` | |
| `cm:faction_offers_peace_to_other_faction(proposer, target)` | an offer; the target may decline |
| `cm:force_non_aggression_pact(granter, recipient)` | **first documented in 9.0** |
| `cm:force_break_non_aggression_pact(breaker, recipient, dissolved)` | 9.0. `dissolved = false` raises a negative diplomatic event and may lower the breaker's reliability |
| `cm:force_break_military_access(breaker, recipient, dissolved, is_hard)` | 9.0, same `dissolved` rule |
| `cm:force_break_vassalage(vassal)` | 9.0 |
| `cm:force_awake_from_death_and_confederate(proposer, target)` | 9.0; revives `target`, then confederates it |
| `cm:make_diplomacy_available(a, b)` | as if they had discovered each other |
| `cm:cai_add_diplomatic_event(from, to, action)` | action from `cai_personality_diplomatic_events` |
| `cm:cai_insert_caravan_diplomatic_event(...)` | caravan variant |
| `cm:apply_dilemma_diplomatic_bonus(a, b, n)` | `n` in [-6, +6] |
| `cm:create_force_with_full_diplomatic_discovery(...)` | spawn helper |
| `cm:cai_evaluate_quick_deal_action(faction, met_faction, deal_type)` | **read**, not write — see below |

### The one read call

`cm:cai_evaluate_quick_deal_action` is the "would you accept this?" probe. It takes faction
**interfaces** (not keys) and a `deal_type` from `diplomatic_actions`, and returns **two**
values — a score and a boolean. `docs/CAMPAIGN_AI.md` §8 has the full write-up and
`derpy_director.lua`'s `beat_ask` is a working consumer: it asks before it forces, so the
alliances and confederations the Director makes are ones the game would already allow.

`diplomacy_quick_deal_offers` (v0, 9 rows) is the list of deal types the quick-deal path
supports: client state, confederation, defensive alliance, military alliance, non-aggression
pact, peace, soft access, trade agreement. **Not** war, and not any of the break options.

### Moving attitude by script, measured

**War does not make a faction dislike you.** Measured on 2026-09-18 in a live
campaign: two factions created by script, handed provinces and put at war with the
human by `cm:force_declare_war`, read **+76 and +67** on his diplomacy screen —
"very friendly" and "friendly" against §3's seven bands. Attitude is a *sum of
factors* and `CULTURAL_SIMILARITIES` is one of them, so a faction of the player's
own subculture starts liked and a war does not subtract enough to cross zero.
`cm:set_base_strategic_threat_score` does not help either: that is layer 4,
targeting, and this is layer 2.

**`cm:apply_dilemma_diplomatic_bonus(a, b, n)` is the practical lever.** Faction
**key strings**; `n` an integer in `[-6, +6]` mapping to `DILEMMA_PENALTY_XXXLARGE`
… `DILEMMA_BONUS_XXXLARGE`, all six pairs on factor group
`diplomatic_factor_dilemma_events`.

- **Argument order: the one who ACTS first, the faction whose regard MOVES second.**
  CA's doc names them only "first" and "second"; all five of CA's calls read that
  way - Neferata's treasury theft `(neferata, victim, -3)`
  (`wh3_dlc29_vampire_web_of_power.lua:145`), her Giselle "Diplomacy boost"
  `(neferata, region_owner, 6)`, the Intrigue at the Court slot penalty
  `(new_occupier, displaced, n)`, the foreign-slot bonuses `(builder, region_owner, n)`.
  Inferred from usage, not yet measured; whether the modifier is also mirrored is
  unknown, so `(actor, affected)` is right either way. The Iron Court's Send Diplomats
  carried the other order through its spec, plan and first build, until the final
  review read CA's calls (2026-09-29).
- **It accumulates.** Not an inference — `wh3_campaign_bonus_values.lua`'s
  `alter_attitude_each_turn_from_foreign_slot` listener applies it to the same pair
  on every `FactionTurnStart` for as long as the building stands. CA also clamps
  the value to `[-6, 6]` with `math.clamp` at both of their call sites, so out-of-
  range is their problem too, not a thing to pass and hope.
- **The magnitude is in the DB, not in the call**, exactly as for
  `cai_add_diplomatic_event`. So "how many applications reach hostile" has no
  written-down answer, and it differs per pair because the starting attitude does.
  Read it back instead: `faction:diplomatic_standing_with(other_key)` is
  documented on `FACTION_SCRIPT_INTERFACE`, returns an `int32`, and CA's caravan
  code is its one vanilla consumer. It takes a faction **key string**: passed an
  interface it does not error, it returns 0 for every faction (measured live,
  `sessions/TESTLOG_20260907_AI_TRADERS_LIVE.md` §15; `IC.rebel_sour` carried the
  interface form until `HANDOFF_20260929_IRON_COURT_FULL_SWEEP.md` §6). **Cap any such loop** — nothing says the engine
  settles an attitude inside the frame that changed it, and a stale read should
  cost extra applications rather than hang.
- **`REBELLED_AGAINST` exists and nobody calls it.** `cai_personality_diplomatic_
  events` carries it on factor group `diplomatic_factor_rebellion`, `is_transitive =
  true`, and a grep of all 5,778 shipped CA scripts returns **zero hits** (still zero in
  9.0's 7,540, re-checked 2026-10-09) — CA's own
  three `cai_add_diplomatic_event` calls all pass a generic `PAST_EVENT_*` under the
  comment `-- CHANGE THIS TO A NEW EVENT`. Transitivity is the reason to want it: a
  generic past event stays between the two factions, this one would spread the
  grudge to third parties.

`tools/../zzz_derpy_iron_court.lua`'s `IC.rebel_sour` is a working consumer, and
`docs/sessions/HANDOFF_20260917_IRON_COURT_SECESSION_CRASH.md` §8g is its write-up.

---

## 7. Effects from a diplomatic stance

`diplomatic_relationship_effects` (v0, 12 rows): `(faction_set, faction_set_relation_with,
diplomatic_stance) -> campaign_effect_list`. Vanilla uses it for exactly one thing — the four
Warriors of Chaos legendary lords each grant a different bundle to their vassals
(`wh3_dlc20_diplomacy_effect_azazel_to_vassal` and so on). It generalises: any faction set, any
stance, any effect list. Twelve rows in the shipped game is not a ceiling, it is a feature CA
built for one DLC and never reused.

`confederation_effect_bundles` (v0, 20 rows) fires on confederation.
`foreign_building_level_diplomatic_stance_requirements` (v0, 88 rows) gates allied-outpost
building levels on stance (`master`, `military_allies`) — this is the table an allied-recruitment
mod needs.

`ritual_payload_form_confederations` is how a rite confederates; 7 of the 28 installed diplomacy-
touching mods use it, which makes it the most-used *behavioural* diplomacy table on the Workshop.
`ritual_payload_diplomatic_attitude_changes` exists and is **0 rows in vanilla** — an attitude
change as a ritual payload is a shape CA built and never shipped, so there is no donor row to
clone and it is unproven.

---

## 8. What you cannot do

- **Add a diplomacy type.** The 27 types are a hardcoded bitmask in `force_diplomacy_new`. A new
  row in `diplomatic_actions` gets a UI entry with nothing behind it.
- **Change how the AI weighs deals *structurally*.** You can retune every number in layers 4 and
  5; you cannot add a term. There is no scripting hook inside the evaluator.
- **Veto a deal the AI wants, from the AI side, in the DB.** Priority 0 still samples (§5d).
  Restriction is layer 1 and layer 1 only.
- **Read another faction's attitude toward a third party cheaply.** `diplomatic_standing_with()`
  exists, but see `docs/CAMPAIGN_AI.md` §3 for the feedback loop that reading it inside a stance
  calculation creates.
- **Preview what an AI would counter-offer.** `cai_evaluate_quick_deal_action` answers yes/no on
  a deal you name, over the 8 quick-deal types only. There is no "what do you want" call.

---

## 9. The Workshop, with numbers

Subscriber counts read from the Steam Workshop API on 2026-09-17 (`current` / `lifetime`), not
from store-page impressions. Ranked by current subscribers.

| Mod | Current | Lifetime | Updated | What it actually changes |
|---|---|---|---|---|
| [Diplomacy Logic and Balance (Katsuko)](https://steamcommunity.com/sharedfiles/filedetails/?id=3503667132) | 13,606 | 27,041 | 2026-06-22 | Layers 4-5. Claims distance-gated war declarations (`long_distance_penalty_*`), strength-aware war choice, alliance logic. Advertises DB-only, no scripts — which is consistent with a pure `cai_personality_deal_evaluation_*` retune |
| [Hecleas Grand Strategy](https://steamcommunity.com/sharedfiles/filedetails/?id=3575054982) | 9,777 | 21,037 | 2026-07-18 | Full overhaul. **10 diplomacy tables plus 929 `force_diplomacy` calls.** The only installed mod touching layers 1, 2, 4 and 5 together. Declares itself incompatible with any other campaign-AI mod |
| [Loreful Diplomacy](https://steamcommunity.com/sharedfiles/filedetails/?id=2789902959) | 5,114 | 18,426 | 2025-12-05 | Layers 1 and 2. Per-culture option denial plus cultural-relations edits. 0.8 MB, the smallest of the serious ones |
| [Wyccc Campaign AI Enhancement](https://steamcommunity.com/sharedfiles/filedetails/?id=3786311456) | 4,237 | 5,043 | 2026-09-07 | Mostly military AI, not diplomacy — touches only `cai_personality_variables` and its junction. Listed because it is the current AI-mod-of-the-moment and people expect diplomacy from it |
| [AI Diplomacy](https://steamcommunity.com/sharedfiles/filedetails/?id=3402623051) | 2,653 | 6,592 | 2025-12-15 | Layer 4, deep. The description is the best free documentation of the evaluator that exists: money capped at a -10 factor, trade-agreement penalties relaxed, treaty-breach durations cut, priorities "increased between 5 and 7 times" |
| [Diplomacy For All](https://steamcommunity.com/sharedfiles/filedetails/?id=2971408094) | 1,644 | 3,762 | 2025-12-13 | Layer 1, inverted — opens every option between everyone |
| [Diplomacy Options Overhaul](https://steamcommunity.com/sharedfiles/filedetails/?id=3386782526) | 619 | 1,420 | 2026-06-19 | Layer 1 plus MCT toggles. **Its Lua is the file Hecleas bundles** (`doo_diplomacy_options_overhaul.lua`), so its reach is far past its own subscriber count |
| [All Diplomacy Unlocked](https://steamcommunity.com/sharedfiles/filedetails/?id=3153209500) | 261 | 789 | 2024-02-03 | Layer 1. Stale, listed for completeness |

**Read AI Diplomacy's description before touching layer 4.** It is a plain-language account of
what each evaluator knob does, written by someone who tuned all of them, and there is no
equivalent in CA's docs or on tw-modding.com.

### What the survey found on this machine

681 packs scanned, 0 unreadable. 28 Workshop mods touch at least one diplomacy table. Of those,
**three** touch the behaviour layer (`cai_personality_deal_evaluation_*`,
`_deal_generation_*` or `cai_personality_cultural_relations_overrides`): Hecleas Grand Strategy,
`!cr_oldworld_campaign` and `!ak_teb3`. Wyccc is *not* one of them despite its billing — it
touches `cai_personality_variables` and its junction only. Everything else is dialogue,
confederation payloads, or new-faction plumbing. The behaviour layer is much less contested than the table count suggests — which is
good news for compatibility and bad news for anyone hoping a reference implementation already
exists for their idea.

---

## 10. Table versions

The version a TSV declares must match CA's, not RPFM's newest. See the
`wh3-table-version-must-match-field-shape` memory — a mismatch is a hard crash during loading
with no `bad_mods_report.txt` line. Read off the shipped files on 2026-09-17:

```
diplomatic_actions                                   v0     diplomatic_relations_attitudes       v0
diplomacy_quick_deal_offers                          v0     diplomatic_relationship_effects      v0
confederation_effect_bundles                         v0     cai_personality_diplomatic_event_values  v0
foreign_building_level_diplomatic_stance_requirements v0
diplomatic_action_subculture_restrictions            v1     diplomatic_action_faction_restrictions   v1
cai_personality_cultural_relations_overrides         v1     cai_personality_strategic_desired_attitudes v1
diplomacy_disabled_between_factions                  v1     cai_diplomacy_excluded_factions      v1
diplomatic_faction_sets                              v1
cai_personality_cultural_components                  v2     cai_personality_deal_generation_generator_priorities v2
cai_personality_deal_evaluation_deal_component_opponent_context_modifiers v2
cai_personality_diplomatic_events                    v4
cai_personality_deal_evaluation_components           v16
cai_personality_deal_evaluation_deal_component_values v17
```

Re-read them after a game patch:
`py tools/fetch_vanilla_tables.py <name>` then `read_vanilla_cache.version(<name>)`.

---

## 11. Checklist for a diplomacy change

1. **Name the layer** (§1). If the complaint is "the AI won't accept", it is layer 4, not layer 1.
2. **If it is a per-culture option block, write Lua**, not DB (§2). `cm:force_diplomacy` inside
   `cm:add_first_tick_callback`. Deny broadly, re-permit narrowly.
3. **Verify every culture/subculture/faction key against `db/`.** They are unvalidated strings;
   a typo does nothing, forever, with no error. The two vocabularies (`culture:` vs
   `subculture:`) are easy to cross.
4. **If it is a DB change, pin the version** from §10 before writing the TSV.
5. **Check the 25 uniform columns first** (§5a) — a differentiating change there collides with
   nothing.
6. **`py tools/check_lua_api.py`** on any script, then `luac -p`. Neither catches typo'd keys.
7. **Check collisions.** `cai_personality_deal_evaluation_*` is contested by exactly one
   installed mod (Hecleas), but Hecleas declares itself incompatible with all campaign-AI mods and means
   it. The WH3 Mod Manager's compatibility checker (`docs/MOD_MANAGER.md`) will name the table
   overlaps.
8. **Measure the before state in game**, not from the table. `docs/CAMPAIGN_AI.md` §3 documents
   a feedback loop where a plausible-looking change moves attitude and stance in opposite
   directions.

---

## 12. Open questions

- The sign convention on `*_opponent_context_modifier` for the non-peace contexts (§5c).
  Measurable in one campaign with a save-scum.
- Whether `ritual_payload_diplomatic_attitude_changes` works at all. 0 vanilla rows means no
  donor and no precedent; per the `wh3-vanilla-row-count-is-not-behaviour` memory, a schema entry
  proves the game parses it, never that it does anything.
- `diplomacy_components` ships **1 row, value `placeholder`**. Either dead or a hook CA never
  used. Untested.
- `diplomatic_relations_religion` ships **0 rows** with a live schema entry. Same status.
- Whether the 7th `force_diplomacy` argument (force-restrict payments) is genuinely safe. CA
  documents it as crash-prone; two large mods ship it. Nobody has isolated it.
