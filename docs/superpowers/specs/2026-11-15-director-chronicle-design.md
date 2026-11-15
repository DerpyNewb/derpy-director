# The Director's Chronicle (phase 3) - design

Status: **draft for approval, 2026-11-15.** Phase 3 of `2026-09-16-ai-director-design.md` §18, which
§10 of that spec describes and this file makes concrete. Phases 4 (the target beat, with a great
power the Director grows) and 5 (the call-to-arms pack) follow in that order, each with its own
design.

## 1. Intent

The Director's work is mostly invisible. A player hears of it only when they are one of the two
parties, and the campaign's rolled rivalry and its three ambitious factions are never named,
because event-feed text cannot carry a faction name. The base spec's own rule is that variety the
player cannot perceive is no variety. The Chronicle is a panel that lists what the world did this
campaign and who answered whom, newest first, with the campaign's temperament, rivalry and
ambitious factions named at the top.

## 2. Goals, non-goals

Goals:

- Every answered story is recorded, with what was done: who turned against the aggressor, which
  pacts formed, who swore a grudge, where rebels rose or a plague broke out, and who confederated.
- The Director's own events are recorded too: the seed at campaign start, a runaway power's
  threat rising or lifting, a runaway alliance, a last-stand confederation.
- The panel names factions, regions and cultures in the player's language.

Non-goals, from the base spec §1 and kept: no filters, no sorting, no per-entry detail view, no
timeline. No click on an entry to move the camera (a later idea, not this phase).

## 3. What is recorded

`news()` becomes the chronicle. An entry is **keys and numbers only**, written in the model event
that did the deed, never resolved text: a loc call from a turn handler crashes at turn 1 and
`pcall` does not catch it.

- A **story** entry for each answered situation that did anything (a cast, or a merge): turn, kind,
  instigator, victim, region, up to three responders, the pact pairs, the grudge holder, the rebel
  units, a plague, a confederation (absorber and absorbed) and the war chest's gold.
- A **Director** entry for: the seed roll, a runaway tier rising or lifting (leader, tier), an
  alliance from the runaway poll, a last stand.
- Passed-over situations are **not** recorded. Turn 1 alone reports about 96, and they are noise.
- A **war** entry, added at the author's request on 2026-11-15 ("add an extra why ... e.g. the
  Empire declared war on a Norsca faction due to being raided"). On `NegativeDiplomaticEvent` with
  `is_war()` (and not `result_of_confederation()`), the Director looks back at most ten turns in the
  Chronicle for the newest story whose instigator is the target and whose victim or cast includes
  the declarer. Found, it records declarer, target, the story's kind as the cause, and the story's
  region and victim: "Karak Hirn declared war on Clan Mors over the sack of Karak Azul." Failing
  that, a war on the faction the runaway step currently scores (threat switched on) is recorded
  with the cause "runaway": "... fearing its power." A war with no recorded cause is **not**
  recorded. The Chronicle does not guess at the AI's own reasons, and recording every war on a
  280-faction map would bury the stories. Each declarer-target pair is told once per cause window.
  The pact line names its cause as well: "... signed a defensive alliance against Clan Mors."

Capped at 100 entries, oldest dropped, under a new save key `derpy_director_chronicle`. The old
`derpy_director_news` (50 entries of the old shape) is cleared on the first write.

**Multiplayer.** Entries are written inside model events, which run identically on every machine,
like all of the Director's saved state. The panel only reads, and only on the local machine.

## 4. The panel

**Brief.** The content shape of CA's Book of Grudges (`ui/campaign ui/book_of_grudges.twui.xml`):
a header, then entries that each read as one short paragraph. Not its two-page book art, which is
the Dwarfs' own: the Director serves every race. Drawn on CA's neutral two-layer panel, as the
Zharr Exchange is. A `brand_header` title at 22, section labels in `la_gioconda_uppercase`, entry
text at 12 in `#FFF8D7` on an opaque plate, the turn in the one accent colour. Every colour and size
in one dict in the generator, asserted against the Lua.

**Layout.** About 640 wide and 760 tall, centred.

- Header: the title, then the temperament's name and one line on what it means, the old hatred
  ("Chaos Dwarfs and the Empire"), and the three ambitious factions.
- Below it a scrolling list, newest first. Each entry is a short paragraph: the turn, the deed,
  then what answered it. For example: "Turn 34. Clan Mors sacked Karak Azul. Karak Hirn and
  Zhufbar turned against Clan Mors, and Karak Hirn swore a grudge. Rebels rose in Karak Azul."
- CA's close button.

**Twui text never wraps** (no `texthbehaviour` value does it; measured on the Exchange), so a
paragraph is broken into lines in Lua, measured with `TextDimensionsForText` as `GGUI.wrap` does,
and **every line is its own one-line row** in `list_box`, with continuation lines indented. That
is the recipe confirmed on the Great Guilds' faction list (`docs/CUSTOM_UI.md`, "Which way to fill
it"): text rows straight into `list_box`, no drawn-whole holder. An empty row separates entries.
(Corrected while planning: the first draft had one component carrying three wrapped lines.)

**Text.** Sentence templates live in the Director's loc file as new rows with `{tokens}`, and the
panel fills them at draw time from `factions_screen_name_<key>`, `regions_onscreen_<key>` and the
culture names. The temperament lines reuse the 7800-7802 feed records' text.

**Opener.** The Director's own HUD button, placed as the Exchange's is, plus a `DERPY_HUB_QUEUE`
entry (`key = "dr"`, order 5, `label`, `live`), so with the derpy hub installed it joins the hub's
column. The Director ships its own hub copy under a new tag `dr` (GUID prefixes DH11 and DH12) from
`tools/sync_derpy_hub.py`. The icon is one of CA's, referenced by path, not copied.

## 5. Files

- `tools/gen_director_ui.py` (new): the panel, row and button `.twui.xml`, built with
  `gen_exchange_ui`'s `C` / `assign` / `hierarchy` / `component` / `layout` and the Guilds' scroll
  parts, checked by `GG.check_scroll_parts` and the Exchange's GUID checks.
- `derpy_director.lua`: the chronicle writes, the panel, the opener, the hub entry.
- `tools/build_director.py`: the chronicle loc rows, the UI files and the hub copy in `pack()`, and
  harness tests for every kind of entry.
- `tools/preview_director.py` (new): renders the panel from the shipped Lua against fake
  components, as `preview_exchange.py` does, with the hardest chronicle the model can write (100
  entries, the longest names, every consequence at once).

## 6. Testing

- Harness: each beat writes what it should into its entry, passed-over situations write nothing,
  the cap drops the oldest, and the old key is cleared. Mutants for each in `mutate_director.py`.
- Preview: the panel drawn headless, with no text wider than its box and every text cell at 4.5:1
  or better. Compared with CA's panel and refined.
- Live: open the panel in a campaign, scroll it, close it, with and without the hub; screenshot.

## 7. Calls made by the designer, for the author to check

- The panel's name is **Chronicle** ("The World Chronicle" as its title).
- The ambitious factions and the old hatred are named openly.
- Only answered stories and the Director's own events are recorded, 100 at most.
- One-line text rows, an entry spanning as many rows as it wraps to, not cards.

## 8. As built and results (2026-11-15)

**Where it differs from the sections above.**

- The panel's script is its own file, `derpy_director_chronicle.lua` (global `DC`), not part of
  `derpy_director.lua`. It only reads two saved values and writes nothing to the model or the save.
- The UI is five files, not three: `derpy_director_panel`, `_list`, `_line`, `_rule` and
  `_button`, GUID prefixes DR01 to DR05. `tools/gen_director_ui.py` writes them with the shared
  emitter (`gen_guilds_emitter`) and the Great Guilds' slider; the Chronicle's loc rows live there
  too (`CHRONICLE_LOC`) and `build_director.feed_rows()` ships them in the Director's loc file.
- **The list is grouped by turn** (the author's request during the build): a "Turn N" heading in the
  accent colour, a 1px rule row above every heading but the first, a small gap between entries of
  one turn. Entries no longer carry the turn.
- **Wars carry their cause** (section 3, added during the build): 9 sentences, one per cause.
- **Colours.** The game ignored `font_m_colour` on these runtime cells: labels set gold drew cream,
  measured off a live frame. Every cell is cream; the temperament's description is faded with
  `[[col:ui_font_faded_grey_beige]]`, CA's own faded font colour. The header's first row has four
  lines, so the longest temperament description fits.
- A last stand is recorded as its story's `m` field, not as a separate kind.

**The final review** found two faults, and both are fixed with a test that failed first:

- The button's tooltip was a loc lookup made from the first tick, and a loc lookup there crashes a
  fresh campaign on turn 1, which pcall does not catch. The tooltip is now literal text in the
  button's `.twui.xml` (`TIP_OPEN`), and the preview's `init` scene asserts the first tick makes no
  loc lookup.
- Clearing the old news buffer used `cm:set_saved_value(name, nil)`, which CA refuses with a
  script error and leaves the value in place. It now uses `cm:clear_saved_value`, and the harness's
  stub refuses `nil` the way CA does.

A third finding, re-graded during the fix pass: the button's retry used `cm:callback`, a model
timer, from code that depends on this machine's screen. It now uses `cm:real_callback`.

**Offline.** `build_director.py --selftest` green; `mutate_director.py` 241 mutants, 0 survived,
0 stale (12 of them aim at the war entries, one at the cleared news buffer). `preview_director.py --selftest` checks every sentence
word for word, the turn headings and rules, indents, stacking and the header; the render reports no
line wider than its cell and no text below 4.5:1. `gen_director_ui.py --check` now runs its checks
(it used to compare files only) and refuses to write on a fault.

**Live** (vanilla IE turn-1 fixture, Astragoth, bridge + intro skip + the pack; before the grouping
by turn):

- Opened by a real click on its button: 507 rows for the hardest chronicle, no line wider than its
  cell in CA's own font, the list at the designed y, rows 20px apart.
- CA's arrow scrolled the list 340px in 20 clicks; closing hid it and stopped it taking the mouse;
  reopening rebuilt it at the top with the same 507 rows.
- A forced war between two computer factions fired `NegativeDiplomaticEvent` with the declarer as
  `proposer()`, and the Director recorded `k=war, w=sack` against the seeded story: "The Drakenhof
  Conclave declared war on Eataine over the sack of Altdorf."
- With the Zharr Exchange also loaded, the hub took both buttons, and the Director's opened the
  Chronicle from the hub's column; the empty Chronicle showed the campaign's real seed.
- The string library stayed clean after every Chronicle step. Three bridge wedges in the session
  were the test probes' own plain-flag `string.find`, not the panel.

**Live after the review fixes** (pack MD5 `e9b60b7d`, same fixture, a seeded chronicle of three
entries per turn over 34 turns):

- 521 rows: 34 turn headings, 33 rule rows, all created and visible at 576x17, 66 gap rows, and no
  line wider than its cell (the widest is 1px inside).
- Measured off a 1280x720 frame: the rule draws as a 1px line of (110,100,80) on the (19,19,19)
  ground, the headings are yellow (236,172,1), and the temperament's description draws at
  (159,150,129), which is `A99F89` after anti-aliasing, against the body text's (234,228,198).
- A brand-new Realm of Chaos campaign (Zhao Ming, `is_new_game` true) placed the button on turn 1
  with no crash and no script error, and the Chronicle opened over the intro screen with its empty
  line under the campaign's real seed.
