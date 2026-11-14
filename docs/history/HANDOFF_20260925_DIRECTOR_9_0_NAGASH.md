# The Director on 9.0 - plague signature, guarded callbacks, Nagash, and the turn-1 rebels

2026-09-25. Asked: "fix the director mod so it supports nagash and fix the 9.0 bugs".
**Built, verified offline, deployed to `data/`. Not on the Workshop (it never was). Not yet seen
in game at the time of writing** - see §6 for the launch check.

## 1. What shipped

`derpy_director.pack` rebuilt by `py tools/build_director.py` (RPFM open), deployed over
`F:\...\Total War WARHAMMER III\data\derpy_director.pack`. The Director has **no Workshop item** -
its only live copy is `data/`, and it is enabled in `used_mods.txt`.

| | MD5 | Where |
|---|---|---|
| new | `38e472bd8a841ecf08ed946fe4dde666` | `data/derpy_director.pack` and `Modding Files/Modpacks/derpy_director.pack` |
| old (09-22) | `b4be6fc820450967758e73980beffcbe` | `data/derpy_director.pack.bak_pre_9_0_fix_20260925`, `Modpacks/derpy_director.pack.bak_20260925_104208` |

Before editing, the staged `derpy_director.lua` / `_lore.lua` were carved out of the deployed
pack and compared: byte-identical, so the staged copy was a safe base.

### 1a. The two 9.0 breaks
1. **`cm:spawn_plague_at_region`** is `(spreader FACTION interface, region interface, plague key)`
   in 9.0 (9.0 docdiff, `docs/sessions/update_9_0_capability/lua/docdiff.json`); 8.x was
   `(region, key)`. `beat_plague` now passes `cm:get_faction(sit.instigator)` - the razer - first.
   CA's own 9.0 callers pass whoever caused the plague (Bloodgrounds owner, Glottkin, Sayl's
   spreader), read out of 9.0 `data_script.pack`.
2. **Unprotected listeners.** Confirmed in 9.0 `_lib/lib_core.lua`: `core_object:new()` picks
   `event_unprotected_callback` unless the `USE_PROTECTED_EVENT_CALLBACKS` tweaker is set, and
   `event_callback` loops the callbacks bare - one throw stops every later callback on that event,
   CA's and other mods' included. A condition that is literally `true` skips `evt_callback`
   entirely, so only callbacks needed guarding. A local `guarded(what, fn)` (`pcall` + log line
   `<what> errored: <err>`) now wraps the first-tick callback, the `WorldStartRound` refill and all
   four watched-event callbacks.

### 1b. Nagash (`wh3_dlc29_sc_nag_undead_legions`)
- **Lore regenerated** (`--check`): 675 -> 726 rows, 51 new pairs, all Nagash's, none of the old
  ones changed. Without it `hatred()` returned neutral for him, so he was **never cast** and every
  deed he was party to scored `unprovoked` 1.00 (over the unrest floor). Nagash -> Chaos Dwarfs
  -100; Chaos Dwarfs -> Nagash -40.
- **Own feed record** in `CULTURE_FLAVOUR`: "Nagash Remembers". Name loc
  `cultures_subcultures_name_wh3_dlc29_sc_nag_undead_legions` = "Undead Legions" (plural, reads
  "The Undead Legions have taken note"). Art `nag/diplomacy` - `ui/eventpics/nag/diplomacy.png`
  exists in 9.0 `ui2.pack`; `nag` added to `ART_DIPLOMACY`.
- **No rebel faction.** 9.0 `factions_tables` has 30 `is_rebel` rows and none for Nagash's
  subculture (his factions: `wh3_dlc29_nag_host_of_nagash`, `_qb1`). `REBEL_FACTIONS` unchanged; a
  town taken from him logs `no unrest ... has no rebel faction`. Aliasing him to
  `wh_main_vmp_vampire_rebels` is a one-line design call, offered and not made.

### 1c. A pre-9.0 bug, found in the 9.0 log
`script_log_250926_0801.txt`: at 67.4s, **before the Director's own first tick (70.5s)**, CA's
"Custom Starts" (`wh3_campaign_custom_starts`) hand regions over and the Director raised 4-unit
rebels in Eilhart, Hag Graef and three Bretonnian towns. Present in every new-campaign log since
`180926_2303` (up to 101 turn-1 situations in one log). Cause: `PEACEFUL_TRANSFERS` listed
confederation/gift/diplomacy/script, **none of which `reason()` ever returns** - zero
`dropped: region changed hands` lines in any log, ever. Now an allowlist,
`CONQUEST_REASONS = {"normal capture", "unopposed capture"}`; anything else is dropped with its
reason in the log line.

## 2. Verification (offline)

- `build_director.py --selftest` green. New: lore pin 726 + Nagash rows (§3), **7d** a Nagash
  neighbour is cast against a Chaos Dwarf kinslaying and the grudge uses his loc key, a fault
  thrown in `cast()` (outside the builder's own pcall) must log `errored:` and must not escape
  (the harness pump is bare, so an escape fails `run_lua`), four real peaceful `reason()` values
  dropped and `unopposed capture` kept, plague asserted as `(sacker, r_victim, key)`.
- Harness stubs changed to model 9.0: `spawn_plague_at_region` **errors** unless arg 1 is a
  faction (has `subculture`), so the 8.x call cannot pass; `reason()` defaults to
  `"normal capture"` (it said `"conquest"`, which the engine never returns); faction spec flag
  `throws` makes `diplomatic_attitude_towards` error.
- `mutate_director.py`: **49 mutants, 0 survived, 0 stale.** New mutants: 8.x plague call back,
  `pcall` removed from `guarded`, allowlist bypassed, `unopposed capture` removed.
- `check_lua_api.py`, `check_lua_undeclared.py`, `check_lua_literal_left.py`, `luac -p`: clean.
  (`check_lua_api` reads the 8.x doc mirror, so it is blind to the plague signature either way.)
- **Saved pack read back** with RPFM shut (`read_pack_index` + `read_vanilla_db` + `read_vanilla_loc`):
  both Lua files byte-identical to staged; all five tables 62 rows (strings 186), 0 duplicate
  criteria values, loc 186 rows with the Nagash text.
- Every other key the Director hardcodes resolves in 9.0 `db.pack`: the five
  `wh3_main_nur_base_*` plagues, `PAST_EVENT_NEGATIVE_MINOR`, all 24 rebel factions. Feed table
  versions (0/1/0/1/0) match CA's 9.0 ones. No other call it makes changed in the 9.0 docdiff or
  `lib_campaign_manager` diff (`random_number` got more permissive; `cm:model()` now errors
  before `is_ready_for_script_access`, irrelevant inside listeners).

## 3. Corrections found the hard way

- `RegionFactionChangeEvent:reason()` has a fixed 13-value vocabulary, listed in a comment in
  CA's `wh2_dlc13_empire_politics.lua` ~1593. A denylist of guessed words is dead code. Memory
  `wh3-region-change-reason-vocabulary`.
- The Director reacts to setup-time events: turn-1 region transfers fire before the player moves,
  and some before the Director's own first tick. A first-tick gate would NOT have fixed it -
  the mixer/Bretonnia transfers arrive after it.
- The feed indices are **positional**: `culture_records()` numbers by sorted subculture key, so
  adding Nagash (sorts after `wh3_dlc23_*`) shifted every later culture's index by +1. Harmless
  because the Lua map and the DB rows are generated together and ship in one pack - never ship
  one without the other.
- `SESSION_INDEX.md` is CRLF; a Python bytes edit inserting `\n` left one LF line (fixed).

## 4. Do not re-derive

- 9.0 plague family (`_at_region`, `_at_settlement`, `_at_military_force`) all take the spreader
  faction interface first.
- 9.0 `lib_core.lua` dispatch: `event_unprotected_callback` = bare call; `condition == true`
  short-circuits. Extract of the 9.0 Lua used here: `%TEMP%\claude_v90\` (only the 8 files that
  mention `spawn_plague_at` or the callback functions).
- Nagash has 51 lore pairs, no rebel faction, 21 eventpics under `ui/eventpics/nag/`.
- The Director is not a Workshop item; deploy is `data/` only.

## 5. Open

1. **In-game check** (§6). Specifically unconfirmed: the `reason()` value an ordinary AI conquest
   reports. If it is not one of the two allowlisted, every conquest logs
   `dropped: region changed hands by <value>` and the conquest scenario goes dark.
2. Whether a plague spawned into a freshly razed (abandoned) region with the razer as spreader
   behaves - the call is right by signature; the effect is unseen.
3. Nagash rebel alias (§1b) - a design call for the author.
4. Other derpy packs' listeners under 9.0's bare dispatch - the new-capability handoff §8.2; this
   session guarded the Director only.

## 6. Launch check - PASSED, 2026-09-25 13:02 session

`script_log_250926_1302.txt` (new Conclave campaign, played into turn 2; `1257` loaded a save to
first tick and quit, `1300` was front end only). `derpy_director` enabled in `used_mods.txt`.

- Loaded: `first tick, watching 4 event(s), budget 180`. 573 Director lines, **0 `errored:`**, 0
  `SCRIPT HAS FAILED`.
- **Turn-1 setup fixed:** 0 situations before the first tick (the 0801 log had 11 and 5 rebellions).
  17 hand-overs dropped with LIVE reason values: `payload` 11, `diplomacy trade` 4,
  `abandoned` 1, `unknown reason` 1.
- **The allowlist matches live values.** 92 conquests passed (91 on turn 1, all at 448-467s, the
  AI's end-of-turn phase - real captures, not setup). reason() was readable on the 17 dropped, so
  the kept ones reported "normal capture"/"unopposed capture". §5.1 is closed.
- 2 rebellions (Zoishenk as Kislev rebels, Grimtop as Ogre rebels), 1 grudge feed (index 7330).
- **Plague call still unexercised:** the one raze (Redhorn at Flensburg, victim `rebels`) hit
  `budget 0 cannot afford 35`. §5.2 stays open.
- The 7 `SCRIPT ERROR` blocks are all CA's: Conclave has no `main_warhammer` faction intro,
  9.0 `wh3_dlc29_vampire_lairs.lua` "no longer has a home region", narrative query templates
  passing a nil faction, three initiative `remove_listener` warnings. None names a derpy file.
- Budget reads 0 for most of turn 1's end phase: 96 situations in one turn drain it. Not new and
  not a fault, but it means consequence beats are mostly skipped on turn 1.
