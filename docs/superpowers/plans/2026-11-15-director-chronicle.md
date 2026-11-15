# The Director's Chronicle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Chronicle panel that lists what the Director did this campaign, newest first, under a header
naming the temperament, the old hatred and the ambitious factions.

**Architecture:** The model script (`derpy_director.lua`) records each answered story and each of its
own events as keys and numbers in a capped saved table. A new UI-only script
(`derpy_director_chronicle.lua`) opens a runtime-created panel, turns entries into sentences from loc
templates at draw time, wraps them in Lua and writes one one-line row per line into a scrolling
`list_box`. A generator emits the four `.twui.xml` files; a preview renders the panel headless from the
shipped UI Lua.

**Tech Stack:** Lua 5.1.5 (game scripts, run headless by Python harnesses), Python 3 generators, RPFM
for the pack, TWUI Studio's reader and rasteriser for the preview.

**Spec:** `docs/superpowers/specs/2026-11-15-director-chronicle-design.md`, under
`docs/superpowers/specs/2026-09-16-ai-director-design.md` §10.

## Global Constraints

- Entries hold keys and numbers only. No loc call in `derpy_director.lua` or its lore file, ever
  (self-test 16 enforces it); every loc call lives in the UI script and runs only from a click.
- The chronicle is written inside model events only; the UI script reads and never writes model or
  save state (multiplayer).
- Cap 100 entries, oldest dropped, key `derpy_director_chronicle`; the old `derpy_director_news` is
  cleared on the first chronicle write.
- Passed-over situations are not recorded.
- No filters, sorting, detail views or camera clicks.
- UI: CA fonts only; title `brand_header` 22, labels `la_gioconda_uppercase`, body 12 `#FFF8D7`, the
  turn in one accent colour; every colour and size in one generator dict asserted against the Lua;
  contrast 4.5:1 measured. Twui text never wraps: one component per line.
- GUID prefixes: `DR01` panel, `DR02` list, `DR03` line row, `DR04` opener; hub copy `DH11`, plate
  `DH12`. Record them in `docs/CUSTOM_UI.md`'s prefix table.
- Player text: plain spoken English, CA's voice, no emojis, never "rung".

## Review Focus

1. A save from before this build carries `derpy_director_news` in the old shape and no chronicle: the
   panel must open on an empty chronicle without error, and the first write must clear the old key.
2. An entry naming a faction that has since died or been confederated: the name must still resolve
   (loc by key works for dead factions) and the panel must not call anything on a null interface.
3. The longest names the map has, at every consequence at once: no line wider than its row.
4. The panel opened, closed, reopened and opened after a turn passed: rows rebuilt, never duplicated.
5. Multiplayer: two machines record identical chronicles because writes run in model events only.

Each line has a test in the task that owns it: 1 and 5 in Task 1, 2-4 in Task 4.

---

### Task 1: Record the chronicle

**Files:**
- Modify: `Modding Files/pack/script/campaign/mod/derpy_director.lua` (`news()` at ~1414, `answer` at
  ~1640-1788, `beat_force`/grudge/unrest/plague call sites, the merge functions, `runaway_turn`, the
  runaway alliance poll, `last_stand`)
- Modify: `tools/build_director.py` (STATE_KEYS, tests 15/15b, new `_selftest_chronicle()` called from
  `_selftest()`)
- Modify: `tools/mutate_director.py` (the news cap mutant re-anchored, new mutants)

**Interfaces:**
- Produces: saved value `derpy_director_chronicle`, a list (oldest first) of entries. Story entry:
  `{t = turn, k = kind, i = instigator, v = victim, r = region key or "", c = {responder keys},
  p = {{a, b}, ...}, g = grudge holder key or nil, u = rebel units or nil, pl = true or nil,
  m = {absorber, absorbed} or nil}`. Director entry kinds: `runaway_rise` (`i` leader, `n` tier),
  `runaway_end` (`i`), `runaway_pact` (`i` leader, `p = {{a, b}}`), `last_stand` (`i` absorber,
  `v` absorbed, `r`). `derpy_director:chronicle(entry)` appends, caps and clears the old key.

- [ ] **Step 1: Write the failing tests** in a new `_selftest_chronicle()`. Read entries with an
  `Eval` event: `"local c = cm:get_saved_value('derpy_director_chronicle') or {} return ..."`.
  Assert, each in its own run:
  - an answered sack writes one entry with `k == "sack"`, `i`, `v`, `r` and `c` equal to the cast;
  - a sack the roll passes over (seed 100 with a chance below 100) writes nothing;
  - a pact landing writes `p[1]` as the pair, a grudge writes `g`, a conquest's unrest writes `u`, a
    raze's plague writes `pl == true`;
  - a runaway merge sets `m`; a forced last stand writes a `last_stand` entry;
  - a runaway tier rise writes `runaway_rise` with `n == 1`, a collapse writes `runaway_end`, a polled
    alliance writes `runaway_pact`;
  - 120 answered sacks leave 100 entries, the newest last;
  - a preloaded `derpy_director_news` of the old shape is nil after the first write;
  - no entry holds a value that is not a string, number, boolean or table of those (walk it).
  Move tests 15/15b to the new key and shape; add `"derpy_director_chronicle"` to `STATE_KEYS`.
- [ ] **Step 2: Run** `py tools/build_director.py --selftest`. Expected: FAIL at the first chronicle
  assertion.
- [ ] **Step 3: Implement.** `news(sit, cast)` becomes: return when `#cast == 0` and no `sit.merge`;
  otherwise build the story entry from `sit` and `cast` and call `self:chronicle(entry)`. The beats
  note what they did on `sit` (`sit.pacts`, `sit.grudge`, `sit.rebels`, `sit.plague`, `sit.merge`)
  where `answer` calls them. The runaway step and `last_stand` call `self:chronicle` directly.
  `NEWS_CAP` becomes `CHRONICLE_CAP = 100`.
- [ ] **Step 4: Run** the self-test. Expected: PASS, every group.
- [ ] **Step 5: Mutants.** Add to `mutate_director.py`: the cap removed, passed-over situations
  recorded, the old key not cleared, each consequence field not written (pacts, grudge, rebels,
  plague, merge), the runaway entries not written. Run `py tools/mutate_director.py`. Expected: 0
  survived, 0 stale.

### Task 2: The Chronicle's loc

**Files:** Modify `tools/build_director.py` (a `CHRONICLE_LOC` dict appended to the loc TSV that
`write_feed_tsvs()` writes; a check that the UI script's loc keys all exist).

**Interfaces:**
- Produces: loc keys `derpy_director_chronicle_<name>` for the panel title, header labels, button
  tooltip, one deed template per kind, one consequence template per field, one template per
  Director entry kind, and the three temperament lines. Tokens: `{i}`, `{v}`, `{r}`, `{a}`, `{b}`,
  `{g}`, `{list}`, `{n}`, `{t}`.

- [ ] **Step 1: Failing check** `check_chronicle_loc()`: every `DC.loc("<name>")` in the UI script
  has a `CHRONICLE_LOC` row and every row is used; every kind the model can write has a deed
  template. Run the self-test. Expected: FAIL (no rows yet; the UI script does not exist, so the check
  reads the model's kinds from `derpy_director.lua`'s situation table and the Director kinds above).
- [ ] **Step 2: Write the rows** in CA's voice (read CA's grudge loc first). Run. Expected: PASS.

### Task 3: The UI files

**Files:** Create `tools/gen_director_ui.py`, writing to `Modding Files/pack/ui/campaign ui/`:
`derpy_director_panel`, `derpy_director_list`, `derpy_director_line`, `derpy_director_button`
(`.twui.xml`).

**Interfaces:**
- Consumes: `gen_exchange_ui`'s `C`, `assign`, `layout`, `PANEL_LAYERS`, `CLOSE_LAYERS`,
  `CLOSE_HOVER`, `OPENER_LAYERS` shape, `SND_*`; `gen_guilds_ui.EU` and `GG.ca_vslider` for the list.
- Produces: component ids the Lua finds: `derpy_director_panel`, `title_text`, `hdr_label_1..3`,
  `hdr_text_1..3`, `close_button`, `listview > list_clip > list_box`, `vslider > handle`,
  `derpy_director_line`, `derpy_director_button`. `STYLE` dict: sizes, colours, fonts, `PANEL_W`,
  `PANEL_H`, `LINE_W`, `LINE_H`, `INDENT`.

- [ ] **Step 1: Failing selftest** `--selftest`: the five scroll names and callbacks (call
  `GG.check_scroll_parts({"derpy_gg_list.twui.xml": list_xml})`), GUIDs unique across the four files
  and each present twice, prefixes as above, every `imagepath` one of CA's (reuse the Exchange's
  pack check), every `STYLE` value equal to the Lua's `DC.STYLE` (regex). Expected: FAIL (no module).
- [ ] **Step 2: Write the generator**; `--check` writes nothing and exits 1 on drift. Run
  `--selftest`. Expected: PASS once Task 4's `DC.STYLE` exists; until then the style comparison is the
  only failure.

### Task 4: The UI script

**Files:** Create `Modding Files/pack/script/campaign/mod/derpy_director_chronicle.lua` (global `DC`).

**Interfaces:**
- Consumes: Task 1's entries, Task 2's loc names, Task 3's component ids and `STYLE`.
- Produces: `DC.sentence(e)` -> string (pure: entry to paragraph, loc through `DC.loc`, names through
  `DC.name(key)`); `DC.wrap(c, text, lead)` -> lines; `DC.draw()`; `DC.show(visible)`;
  `DC.place_button()`; the `DERPY_HUB_QUEUE` entry `{key = "dr", button = DC.BUTTON, order = 5,
  label = fn, live = fn}`; a `ComponentLClickUp` listener moved to the front of the queue as
  `EX.click_first` does, its handler pcall'd.

- [ ] **Step 1: Failing tests** in a new `tools/preview_director.py --selftest`, which runs the UI
  script under fake components (the `preview_exchange.py` DRIVER pattern) with a demo chronicle: one
  entry of every kind, every consequence at once, the longest faction and region names on the map,
  a dead faction, 100 entries. Assert: `DC.sentence` gives the expected paragraph for each kind;
  the list holds one row per wrapped line plus one blank per gap; no row's text measures wider than
  `LINE_W - inset`; opening, closing and reopening leaves the same row count; an empty chronicle and
  an old `derpy_director_news` both open without error; no `cm:` write is reached. Expected: FAIL.
- [ ] **Step 2: Write the script**: open builds the panel once (centred from
  `core:get_screen_resolution()`), fills the header from the seed, draws the list newest first,
  rebuilds on every open; the button is placed as `EX.place_button` places the Exchange's unless the
  hub owns it. `luac -p` and `py tools/check_lua_api.py` on it. Run the preview selftest. Expected:
  PASS.

### Task 5: Preview and refine

**Files:** `tools/preview_director.py` (render half).

- [ ] **Step 1:** Render `.skilltree_cache/ui_preview/dr_chronicle.png` from the selftest's demo
  world with `PG._studio()` and `PG.extract_art`; exit 1 on text below 4.5:1 or wider than its box.
- [ ] **Step 2:** Compare with CA's Book of Grudges list and our Exchange panel under typography,
  colour, spacing and layout; fix; render again. Show the picture to the author before packing.

### Task 6: Hub and pack

**Files:** Modify `tools/sync_derpy_hub.py` (`TAGS["dr"] = "DH11"`, `PLATE_TAGS["dr"] = "DH12"`),
`tools/build_director.py` (`pack()` adds the four UI files, the UI script and `sync_derpy_hub.pack_files("dr")`,
and its verify step re-reads them), `docs/CUSTOM_UI.md` (prefix table).

- [ ] **Step 1:** `py tools/sync_derpy_hub.py`, then `--check` on it. Expected: the three `dr` files
  written, check clean.
- [ ] **Step 2:** `py tools/build_director.py` (builds, verifies, saves). Expected: the verify step
  lists the new files. Deploy to `data/` with the game shut, MD5 both sides.

### Task 7: Live check and records

- [ ] **Step 1:** Live test per `docs/LIVE_TESTING.md` (mod list: bridge, intro skip, the Director;
  test prefs applied then reverted): a few turns, open the Chronicle, scroll, close, reopen,
  screenshot; then once with another hub mod installed. Quit the game after.
- [ ] **Step 2:** Records: spec status and results, `docs/MY_MODS.md`, `docs/SESSION_INDEX.md`,
  `tools/README.md` (`gen_tools_index.py`), `sync_director_repo.py` (add the new files), the repo
  README and CHANGELOG, then sync, commit and push.
