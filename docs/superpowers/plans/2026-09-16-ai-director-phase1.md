# The Director, Phase 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Director core and prove it with exactly one scenario — a sacked settlement draws
a response from factions that hate the sacker — producing event-feed messages and nothing else.

**Architecture:** One hand-written Lua file holds the core (event bus, situation, cast selection,
budget, beats, persistence) plus the single Phase 1 scenario. One generated Lua file holds CA's
cultural-relations matrix, baked at build time because campaign Lua cannot read a DB table. A Python
build script runs the **shipped** Lua under Lua 5.1.5 against a stubbed campaign and asserts on the
calls it recorded; it refuses to pack on a failing selftest.

**Tech Stack:** Lua 5.1.5, Python 3, RPFM MCP server over HTTP, Total War WARHAMMER III.

**Spec:** `docs/superpowers/specs/2026-09-16-ai-director-design.md` — read §1 through §14 and §18
before starting. Phase 1 is §18's second phase.

## Global Constraints

Copied verbatim from the spec and from `CLAUDE.md`. Every task's requirements implicitly include
this section.

- **This workspace is NOT a git repo.** There are no commits, no branches and no worktrees. Every
  task's final step is a **snapshot**, not a commit: copy the files you touched into
  `<scratchpad>/director_snapshots/taskNN/`. Review packages are `diff -u` between snapshots.
- **Lua is 5.1.5**, at `C:\Program Files (x86)\Lua\5.1\lua.exe` and `luac.exe`. The game matches.
- **The only test command is `py tools\build_director.py --selftest`.** There is no pytest, no
  framework, no fixtures. Assertions live inside `_selftest()` in that file.
- **The selftest runs the SHIPPED Lua file**, not a copy and not a re-implementation.
- Global table is **`derpy_director`**, never `director`. A mod whose point is composing with other
  mods must not squat a generic global.
- **No loc calls from any turn handler or listener.** `effect.get_localised_string`,
  `common.get_localised_string` and bare `get_localised_string` CTD at turn 1 and `pcall` does not
  catch it. News entries store keys and numbers only.
- **No local-faction call at script root.** It CTDs and `pcall` does not catch it.
- **Sorted, never raw `pairs()`** over anything that affects behaviour. Undefined table order
  diverges across reloads and multiplayer clients.
- **The human player is never a cast candidate.** A human instigator is still targeted.
- **`cm:force_confederation(X, X)` crashes.** Any confederation path needs a self-check.
- **The past diplomatic event has no inverse.** It fires only when a situation enters or escalates.
- **`cm:random_number([max], [min])` takes max FIRST**, defaults 100 and 1.
- **Off makes zero calls** out of the turn handler — not calls that clean up.
- **Phase 1 ships ZERO DB rows.** No loc, no tables, no missions. Event-feed output only.
- Keys are unvalidated strings and fail silently forever. Every faction, region and subculture key
  in shipped Lua is verified against `db/` or the vanilla cache before it ships.

## File Structure

| File | Responsibility |
|---|---|
| Create: `Modding Files/pack/script/campaign/mod/derpy_director.lua` | The whole core plus the one Phase 1 scenario. Hand-written. |
| Create: `Modding Files/pack/script/campaign/mod/derpy_director_lore.lua` | **Generated.** CA's cultural-relations matrix as a Lua literal. Data only, no logic. |
| Create: `tools/build_director.py` | Lua stub harness, `_selftest()`, the lore generator, `check()`, and `pack()`. |
| Create: `tools/mutate_director.py` | Mutation runner proving the selftest's assertions can fail. |
| Create: `Modding Files/Modpacks/derpy_director.pack` | Build output. |

**Load order note:** `derpy_director.lua` sorts before `derpy_director_lore.lua`, so the core loads
first and the lore global does not exist yet at that moment. The core therefore reads the lore
**lazily at first tick**, never at file scope, and asserts with a clear log line if it is absent.

---

### Task 1: The harness, the skeleton, and the off switch

**Files:**
- Create: `tools/build_director.py`
- Create: `Modding Files/pack/script/campaign/mod/derpy_director.lua`

**Interfaces:**
- Consumes: nothing.
- Produces: `run_lua(factions, events=None, turns=1, disable=False, preload=None, seed=None)
  -> (calls, state)`. `calls` is a list of tuples `(name, a, b, c)` with every element a string.
  `state` is a dict of saved-value name to string. `events` is a list of
  `{"event": str, "instigator": str, "victim": str, "region": str}` fired in order, one per turn.
  Also produces the Lua globals `derpy_director` and the constant `local ENABLED = true`.

- [ ] **Step 1: Write the failing test**

Create `tools/build_director.py` with this content:

```python
"""Build and check derpy_director.pack - the Director.

    py tools/build_director.py --selftest   run the shipped Lua under stubs
    py tools/build_director.py --check      regenerate the lore file and verify, no RPFM
    py tools/build_director.py              pack it (needs RPFM open)

The selftest RUNS `Modding Files/pack/script/campaign/mod/derpy_director.lua` under Lua 5.1.5
against a stubbed campaign and asserts on the calls it recorded - it does not re-implement the
logic in Python. See docs/superpowers/specs/2026-09-16-ai-director-design.md
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODDIR = os.path.join(ROOT, "Modding Files", "pack", "script", "campaign", "mod")
SCRIPT = os.path.join(MODDIR, "derpy_director.lua")
LORE = os.path.join(MODDIR, "derpy_director_lore.lua")
LUA = r"C:\Program Files (x86)\Lua\5.1\lua.exe"
LUAC = r"C:\Program Files (x86)\Lua\5.1\luac.exe"
PACK = os.path.join(ROOT, "Modding Files", "Modpacks", "derpy_director.pack")
IN_PACK = "script/campaign/mod/derpy_director.lua"
IN_PACK_LORE = "script/campaign/mod/derpy_director_lore.lua"

sys.path.insert(0, os.path.join(ROOT, "tools"))

HARNESS = r'''
-- Stand-ins for the campaign environment: enough to load the mod and record what it does.
local CALLS = {}
local SAVED = {}
local LISTENERS = {}
local FIRST_TICKS = {}

local function record(name, a, b, c)
  CALLS[#CALLS + 1] = {name, tostring(a), tostring(b), tostring(c)}
end

function out(msg) record("out", msg) end
function is_table(t) return type(t) == "table" end

local function list(items)
  return {
    num_items = function() return #items end,
    item_at = function(_, i) return items[i + 1] end,
    _items = items,
  }
end

function model_pairs(l)
  local i = 0
  local items = l._items
  return function()
    i = i + 1
    if items[i] then return i, items[i] end
  end
end

local BY_NAME = {}
local ORDER = {}

local function faction(spec)
  local f = {}
  function f:name() return spec.name end
  function f:is_null_interface() return false end
  function f:is_dead() return spec.dead == true end
  function f:is_rebel() return spec.rebel == true end
  function f:is_human() return spec.human == true end
  function f:subculture() return spec.subculture or "" end
  local regions = {}
  for i = 1, (spec.regions or 0) do regions[i] = {} end
  function f:region_list() return list(regions) end
  return f
end

for _, spec in ipairs(FACTIONS) do
  local f = faction(spec)
  BY_NAME[spec.name] = f
  ORDER[#ORDER + 1] = f
end

local CURRENT_TURN = 0

cm = {}
function cm:model()
  return {
    world = function() return {faction_list = function() return list(ORDER) end} end,
    turn_number = function() return CURRENT_TURN end,
  }
end
function cm:get_faction(key) return BY_NAME[key] or false end
function cm:add_first_tick_callback(fn) FIRST_TICKS[#FIRST_TICKS + 1] = fn end
function cm:set_saved_value(name, value) SAVED[name] = value end
function cm:get_saved_value(name)
  if PRELOAD[name] ~= nil then return PRELOAD[name] end
  return SAVED[name]
end
function cm:random_number(max, min) record("random_number", max, min); return SEED_ROLL end

core = {}
function core:add_listener(_, event, _, fn, _)
  LISTENERS[event] = LISTENERS[event] or {}
  table.insert(LISTENERS[event], fn)
end

dofile(SCRIPT_PATH)
if LORE_PATH then dofile(LORE_PATH) end

for _, fn in ipairs(FIRST_TICKS) do fn() end

for _, ev in ipairs(EVENTS) do
  CURRENT_TURN = CURRENT_TURN + 1
  local fns = LISTENERS[ev.event]
  if fns then
    local ctx = {
      instigator = function() return BY_NAME[ev.instigator] end,
      victim = function() return BY_NAME[ev.victim] end,
      region_key = function() return ev.region end,
    }
    for _, fn in ipairs(fns) do fn(ctx) end
  else
    record("no_listener", ev.event)
  end
end

local fh = io.open(DUMP_PATH, "w")
for _, c in ipairs(CALLS) do
  fh:write(c[1] .. "\t" .. c[2] .. "\t" .. c[3] .. "\t" .. c[4] .. "\n")
end
fh:write("===STATE\n")
for _, k in ipairs(STATE_KEYS) do
  fh:write(k .. "\t" .. tostring(SAVED[k]) .. "\n")
end
fh:close()
'''

STATE_KEYS = ["derpy_director_seed", "derpy_director_budget", "derpy_director_cooldowns",
              "derpy_director_news", "derpy_director_last_tier"]


def _lua(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if v is None:
        return "nil"
    if isinstance(v, str):
        return '"%s"' % v.replace("\\", "\\\\").replace('"', '\\"')
    if isinstance(v, (list, tuple)):
        return "{" + ", ".join(_lua(x) for x in v) + "}"
    if isinstance(v, dict):
        return "{" + ", ".join("[%s] = %s" % (_lua(k), _lua(val)) for k, val in
                               sorted(v.items())) + "}"
    raise TypeError(type(v))


def _faction_table(factions):
    rows = []
    for f in factions:
        parts = ["name = %s" % _lua(f["name"]),
                 "regions = %s" % _lua(f.get("regions", 0)),
                 "subculture = %s" % _lua(f.get("subculture", ""))]
        for flag in ("dead", "rebel", "human"):
            if f.get(flag):
                parts.append("%s = true" % flag)
        rows.append("{" + ", ".join(parts) + "}")
    return "{" + ", ".join(rows) + "}"


def _events_table(events):
    rows = []
    for e in events:
        rows.append("{event = %s, instigator = %s, victim = %s, region = %s}" % (
            _lua(e["event"]), _lua(e.get("instigator")), _lua(e.get("victim")),
            _lua(e.get("region"))))
    return "{" + ", ".join(rows) + "}"


def run_lua(factions, events=None, disable=False, preload=None, seed=50):
    """Run the SHIPPED Lua under the harness. Returns (calls, state)."""
    src = open(SCRIPT, encoding="utf-8").read()
    if disable:
        needle = "local ENABLED = true"
        assert src.count(needle) == 1, "cannot find the single ENABLED constant to flip"
        src = src.replace(needle, "local ENABLED = false")
    with tempfile.TemporaryDirectory() as td:
        script = os.path.join(td, "mod.lua")
        open(script, "w", encoding="utf-8").write(src)
        lore_path = None
        if os.path.exists(LORE):
            lore_path = os.path.join(td, "lore.lua")
            open(lore_path, "w", encoding="utf-8").write(
                open(LORE, encoding="utf-8").read())
        dump = os.path.join(td, "calls.txt")
        preamble = (
            "SCRIPT_PATH = %s\nLORE_PATH = %s\nFACTIONS = %s\nEVENTS = %s\n"
            "PRELOAD = %s\nDUMP_PATH = %s\nSTATE_KEYS = %s\nSEED_ROLL = %s\n" % (
                _lua(script), _lua(lore_path), _faction_table(factions),
                _events_table(events or []), _lua(preload or {}), _lua(dump),
                _lua(STATE_KEYS), _lua(seed)))
        harness = os.path.join(td, "h.lua")
        open(harness, "w", encoding="utf-8").write(preamble + HARNESS)
        r = subprocess.run([LUA, harness], capture_output=True, text=True)
        if r.returncode != 0:
            raise AssertionError("lua failed: %s" % (r.stderr.strip() or r.stdout.strip()))
        calls, state, seen_state = [], {}, False
        for line in open(dump, encoding="utf-8").read().splitlines():
            if line == "===STATE":
                seen_state = True
                continue
            parts = line.split("\t")
            if seen_state:
                state[parts[0]] = parts[1]
            else:
                calls.append(tuple(parts))
        return calls, state


def _selftest():
    # 1. The mod loads, registers its listener, and logs once at first tick.
    world = [{"name": "sacker", "regions": 10, "subculture": "wh3_dlc23_sc_chd_chaos_dwarfs"},
             {"name": "victim", "regions": 5, "subculture": "wh_main_sc_dwf_dwarfs"}]
    calls, _ = run_lua(world)
    assert [c for c in calls if c[0] == "out" and "[director]" in c[1]], calls

    # 2. Disabled makes ZERO calls out of the listener, across several events.
    events = [{"event": "CharacterSackedSettlement", "instigator": "sacker",
               "victim": "victim", "region": "r1"}] * 3
    calls, _ = run_lua(world, events=events, disable=True)
    assert calls == [], calls
    print("selftest: load and off switch ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)
        sys.exit(1)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py tools\build_director.py --selftest`

Expected: FAIL. `AssertionError: lua failed:` with a message about the missing
`derpy_director.lua`, because the file does not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Create `Modding Files/pack/script/campaign/mod/derpy_director.lua`:

```lua
-- The Director. Watches for situations, decides who would plausibly care, and changes inputs the
-- campaign AI already reads. Zero DB rows in phase 1.
-- See docs/superpowers/specs/2026-09-16-ai-director-design.md

local ENABLED = true
local LOG_PREFIX = "[director]"

derpy_director = {
	loaded = false,
}

local function log(msg)
	out(LOG_PREFIX .. " " .. msg)
end
derpy_director.log = log

-- Registered from the scenario table in a later task. Phase 1 registers exactly one event.
local WATCHED = {"CharacterSackedSettlement"}

function derpy_director:on_event(context)
	if not ENABLED then return end
	log("event received")
end

function derpy_director:first_tick()
	if not ENABLED then return end
	self.loaded = true
	log("first tick, watching " .. #WATCHED .. " event(s)")
end

cm:add_first_tick_callback(function() derpy_director:first_tick() end)

for i = 1, #WATCHED do
	core:add_listener(
		"derpy_director_" .. WATCHED[i],
		WATCHED[i],
		true,
		function(context) derpy_director:on_event(context) end,
		true
	)
end
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `py tools\build_director.py --selftest`

Expected: PASS, printing `selftest: load and off switch ok`.

Note why assertion 2 is exact rather than approximate: with `ENABLED = false`, both
`first_tick` and `on_event` return before any `log` call, so the recorded list is genuinely
empty. If a future change logs before the `ENABLED` check, this assertion catches it.

- [ ] **Step 5: Snapshot**

```bash
SNAP="$TMPDIR/director_snapshots/task01"; mkdir -p "$SNAP"
cp "tools/build_director.py" "$SNAP/"
cp "Modding Files/pack/script/campaign/mod/derpy_director.lua" "$SNAP/"
```

---

### Task 2: Bake the lore table, and make a stale bake a failure

**Files:**
- Modify: `tools/build_director.py` (add `build_lore()`, `check()`, and the `--check` flag)
- Create: `Modding Files/pack/script/campaign/mod/derpy_director_lore.lua` (generated)

**Interfaces:**
- Consumes: `run_lua` from Task 1.
- Produces: the Lua global `derpy_director_lore`, a table where
  `derpy_director_lore[source_subculture][target_subculture]` is `{base, neg, pos}` — three numbers.
  Also produces `build_lore() -> str` and `check() -> None` in Python.

- [ ] **Step 1: Write the failing test**

Add to `_selftest()` in `tools/build_director.py`, after assertion 2:

```python
    # 3. The lore file is present, complete, and carries CA's measured values. These four are the
    # spec's section 4 table: if CA changes them in a patch, this fails rather than silently
    # changing how the Director casts.
    import re
    src = open(LORE, encoding="utf-8").read()
    assert "derpy_director_lore" in src, "lore global missing"
    calls, _ = run_lua([{"name": "a", "regions": 1, "subculture": "wh_main_sc_dwf_dwarfs"}],
                       events=[{"event": "probe_lore"}])
    rows, _ = load_cache()
    assert len(rows) == 675, len(rows)
    lookup = {}
    for r in rows:
        lookup.setdefault(r["source"], {})[r["target"]] = (
            r["attitude_base"], r["negative_attitude_multiplier"],
            r["positive_attitude_multiplier"])
    dwf = lookup["wh_main_sc_dwf_dwarfs"]
    assert dwf["wh_main_sc_dwf_dwarfs"] == (0.0, 1.0, 1.0), dwf["wh_main_sc_dwf_dwarfs"]
    assert dwf["wh3_dlc23_sc_chd_chaos_dwarfs"] == (-100.0, 2.0, 0.1), \
        dwf["wh3_dlc23_sc_chd_chaos_dwarfs"]

    # 4. The SHIPPED lore file matches the cache. A stale bake is a failure, not a surprise.
    assert src == build_lore(), "derpy_director_lore.lua is stale - run --check to regenerate"
    print("selftest: lore bake ok")
```

Add these functions to `tools/build_director.py` above `_selftest()`:

```python
def load_cache():
    """CA's cultural relations, out of the vanilla cache. Returns (rows, fields)."""
    from read_vanilla_cache import load
    return load("campaign_cultural_relations")


def build_lore():
    """The lore matrix as a Lua literal. Campaign Lua cannot read a DB table - there is no cm:
    accessor and a grep of all 5,778 CA scripts for this table name returns zero hits - so the
    values are baked in at build time and verified against the cache by check().
    """
    rows, _ = load_cache()
    lookup = {}
    for r in rows:
        lookup.setdefault(r["source"], {})[r["target"]] = (
            r["attitude_base"], r["negative_attitude_multiplier"],
            r["positive_attitude_multiplier"])
    lines = [
        "-- GENERATED by tools/build_director.py. Do not edit by hand.",
        "-- CA's campaign_cultural_relations, %d rows, baked because campaign Lua cannot read"
        % len(rows),
        "-- a DB table. Regenerate with: py tools/build_director.py --check",
        "derpy_director_lore = {",
    ]
    for src_key in sorted(lookup):
        cells = ["[%s] = {%s, %s, %s}" % (_lua(t), repr(v[0]), repr(v[1]), repr(v[2]))
                 for t, v in sorted(lookup[src_key].items())]
        lines.append("\t[%s] = {%s}," % (_lua(src_key), ", ".join(cells)))
    lines.append("}")
    return "\n".join(lines) + "\n"


def check():
    """Regenerate the lore file and confirm every shipped Lua file still parses. No RPFM."""
    open(LORE, "w", encoding="utf-8", newline="\n").write(build_lore())
    print("wrote %s" % LORE)
    for path in (SCRIPT, LORE):
        r = subprocess.run([LUAC, "-p", path], capture_output=True, text=True)
        assert r.returncode == 0, "luac failed on %s:\n%s" % (path, r.stdout + r.stderr)
    print("check ok - lore regenerated, both files parse")
```

And extend the `__main__` block:

```python
if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    elif "--check" in sys.argv:
        check()
    else:
        print(__doc__)
        sys.exit(1)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py tools\build_director.py --selftest`

Expected: FAIL with `FileNotFoundError` on `derpy_director_lore.lua`, because nothing has
generated it yet.

- [ ] **Step 3: Generate the lore file**

Run: `py tools\build_director.py --check`

Expected output: `wrote ...derpy_director_lore.lua` then `check ok - lore regenerated, both files
parse`.

If `load_cache()` raises `IndexError: list index out of range`, the cache entry is **poisoned** —
`fetch_vanilla_tables.py` writes a 0-row file for a table it could not read. Delete
`.skilltree_cache/campaign_cultural_relations.json`, re-run
`py tools\fetch_vanilla_tables.py campaign_cultural_relations` with RPFM open, and try again.

- [ ] **Step 4: Run the test to verify it passes**

Run: `py tools\build_director.py --selftest`

Expected: PASS, printing `selftest: lore bake ok`.

- [ ] **Step 5: Snapshot**

```bash
SNAP="$TMPDIR/director_snapshots/task02"; mkdir -p "$SNAP"
cp "tools/build_director.py" "$SNAP/"
cp "Modding Files/pack/script/campaign/mod/derpy_director.lua" "$SNAP/"
cp "Modding Files/pack/script/campaign/mod/derpy_director_lore.lua" "$SNAP/"
```

---

### Task 3: The situation

**Files:**
- Modify: `Modding Files/pack/script/campaign/mod/derpy_director.lua`
- Modify: `tools/build_director.py` (`_selftest` only)

**Interfaces:**
- Consumes: `derpy_director.log` and the listener registration from Task 1.
- Produces: `derpy_director:situation_from(context) -> table or nil`, returning
  `{kind = string, instigator = string, victim = string, region = string, turn = number}` with all
  faction fields as **key strings**, never interfaces.

- [ ] **Step 1: Write the failing test**

Add to `_selftest()`:

```python
    # 5. A fired event becomes a situation with key STRINGS, and the log records it.
    world = [{"name": "sacker", "regions": 10, "subculture": "wh3_dlc23_sc_chd_chaos_dwarfs"},
             {"name": "victim", "regions": 5, "subculture": "wh_main_sc_dwf_dwarfs"}]
    calls, _ = run_lua(world, events=[{"event": "CharacterSackedSettlement",
                                       "instigator": "sacker", "victim": "victim",
                                       "region": "wh3_main_combi_region_karak_azul"}])
    sit = [c for c in calls if c[0] == "out" and "situation" in c[1]]
    assert sit, calls
    assert "instigator=sacker" in sit[0][1], sit
    assert "victim=victim" in sit[0][1], sit
    assert "region=wh3_main_combi_region_karak_azul" in sit[0][1], sit
    assert "turn=1" in sit[0][1], sit

    # 6. A malformed context produces NO situation and no crash. The engine drops an erroring
    # listener condition silently, with no log line, so the guard has to be ours.
    calls, _ = run_lua(world, events=[{"event": "CharacterSackedSettlement",
                                       "instigator": "ghost", "victim": "victim",
                                       "region": "r1"}])
    assert not [c for c in calls if c[0] == "out" and "situation" in c[1]], calls
    assert [c for c in calls if c[0] == "out" and "dropped" in c[1]], calls
    print("selftest: situation ok")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py tools\build_director.py --selftest`

Expected: FAIL at assertion 5 with `AssertionError` and the call list, because nothing logs a
situation yet.

- [ ] **Step 3: Write the implementation**

Replace `derpy_director:on_event` in `derpy_director.lua` with:

```lua
-- Build a situation from an event context. Faction fields are KEY STRINGS, never interfaces:
-- a situation is stored, compared and logged, and an interface does none of those safely.
-- cm:get_faction returns FALSE, not nil, for a key it does not know.
function derpy_director:situation_from(context)
	local instigator = context:instigator()
	local victim = context:victim()
	if not instigator or instigator:is_null_interface() then return nil end
	if not victim or victim:is_null_interface() then return nil end
	return {
		kind = "sack",
		instigator = instigator:name(),
		victim = victim:name(),
		region = context:region_key(),
		turn = cm:model():turn_number(),
	}
end

function derpy_director:on_event(context)
	if not ENABLED then return end
	-- An erroring listener condition is dropped by the engine with NO log line at all, so a
	-- scenario that silently never fires is indistinguishable from one that never matched.
	-- Wrap it ourselves and say so.
	local ok, sit = pcall(function() return self:situation_from(context) end)
	if not ok then
		log("dropped: situation_from errored: " .. tostring(sit))
		return
	end
	if not sit then
		log("dropped: incomplete context")
		return
	end
	log(string.format("situation kind=%s instigator=%s victim=%s region=%s turn=%d",
		sit.kind, sit.instigator, sit.victim, tostring(sit.region), sit.turn))
end
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `py tools\build_director.py --selftest`

Expected: PASS, printing `selftest: situation ok`.

- [ ] **Step 5: Snapshot**

```bash
SNAP="$TMPDIR/director_snapshots/task03"; mkdir -p "$SNAP"
cp "tools/build_director.py" "Modding Files/pack/script/campaign/mod/derpy_director.lua" "$SNAP/"
```

---

### Task 4: Cast selection

**Files:**
- Modify: `Modding Files/pack/script/campaign/mod/derpy_director.lua`
- Modify: `tools/build_director.py` (`_selftest` only)

**Interfaces:**
- Consumes: `situation_from` from Task 3, `derpy_director_lore` from Task 2.
- Produces: `derpy_director:hatred(source_subculture, target_subculture) -> base, neg, pos` and
  `derpy_director:cast(sit, take) -> array of key strings, sorted by score descending then by name`.

- [ ] **Step 1: Write the failing test**

Add to `_selftest()`:

```python
    # 7. hatred() is pure, so pin its boundaries directly. Unknown pairs are neutral, never nil.
    CHD = "wh3_dlc23_sc_chd_chaos_dwarfs"
    DWF = "wh_main_sc_dwf_dwarfs"
    GRN = "wh_main_sc_grn_greenskins"
    world = [
        {"name": "sacker", "regions": 20, "subculture": CHD},
        {"name": "victim", "regions": 5, "subculture": DWF},
        {"name": "hold_a", "regions": 6, "subculture": DWF},
        {"name": "hold_b", "regions": 6, "subculture": DWF},
        {"name": "orcs", "regions": 6, "subculture": GRN},
        {"name": "player", "regions": 6, "subculture": DWF, "human": True},
    ]
    ev = [{"event": "CharacterSackedSettlement", "instigator": "sacker",
           "victim": "victim", "region": "r1"}]
    calls, _ = run_lua(world, events=ev)
    cast = [c for c in calls if c[0] == "out" and c[1].find("cast ") == len("[director] ")]
    assert cast, calls
    line = cast[0][1]

    # The two dwarf holds are cast: Dwarfs hate Chaos Dwarfs at -100. Greenskins do not (0).
    assert "hold_a" in line and "hold_b" in line, line
    assert "orcs" not in line, line
    # The human is NEVER a candidate. cai_evaluate_quick_deal_action asks what the AI would
    # accept and a human faction has no AI to ask; the force beats are unrefusable.
    assert "player" not in line, line
    # The victim is not cast for its own rescue, and the instigator is never cast.
    assert "victim" not in line and "sacker" not in line, line
    print("selftest: cast selection ok")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py tools\build_director.py --selftest`

Expected: FAIL at assertion 7 with `AssertionError` and the call list — nothing logs a cast line.

- [ ] **Step 3: Write the implementation**

Add to `derpy_director.lua`, above `on_event`:

```lua
local CAST_TAKE = 3
local NEUTRAL = {0, 1, 1}

-- CA's campaign_cultural_relations, baked at build time (campaign Lua cannot read a DB table).
-- Read LAZILY: derpy_director.lua sorts before derpy_director_lore.lua, so the global does not
-- exist yet at file scope. An undeclared Lua global is nil, not an error.
function derpy_director:hatred(source, target)
	local tbl = derpy_director_lore
	if not tbl then return NEUTRAL[1], NEUTRAL[2], NEUTRAL[3] end
	local row = tbl[source]
	if not row then return NEUTRAL[1], NEUTRAL[2], NEUTRAL[3] end
	local cell = row[target]
	if not cell then return NEUTRAL[1], NEUTRAL[2], NEUTRAL[3] end
	return cell[1], cell[2], cell[3]
end

-- Scores every candidate and takes the top `take`. Scores on hatred of the INSTIGATOR, not on
-- affinity with the victim: CA's matrix puts Dwarfs toward Dwarfs at 0, so there is no kin
-- affinity in the data to lean on. The grudge against the attacker is the whole signal.
function derpy_director:cast(sit, take)
	local instigator = cm:get_faction(sit.instigator)
	if not instigator or instigator:is_null_interface() then return {} end
	local inst_sc = instigator:subculture()
	local scored = {}
	for _, f in model_pairs(cm:model():world():faction_list()) do
		if not f:is_null_interface() and not f:is_dead() and not f:is_rebel()
				and not f:is_human()
				and f:name() ~= sit.instigator
				and f:name() ~= sit.victim
				and f:region_list():num_items() >= 2 then
			local base, neg = self:hatred(f:subculture(), inst_sc)
			if base < 0 then
				-- Cache the name now: the sort comparator would otherwise make O(n log n)
				-- engine calls over up to 100 factions, every situation.
				scored[#scored + 1] = {
					name = f:name(),
					score = (-base) * neg,
				}
			end
		end
	end
	-- Sorted, never raw pairs(): undefined order diverges across reloads and MP clients.
	-- Ties break on name so the order is total, not merely mostly-defined.
	table.sort(scored, function(x, y)
		if x.score ~= y.score then return x.score > y.score end
		return x.name < y.name
	end)
	local out_list = {}
	for i = 1, math.min(take, #scored) do out_list[i] = scored[i].name end
	return out_list
end
```

And append to the end of `on_event`, after the situation log line:

```lua
	local cast = self:cast(sit, CAST_TAKE)
	log("cast " .. table.concat(cast, ", "))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `py tools\build_director.py --selftest`

Expected: PASS, printing `selftest: cast selection ok`.

- [ ] **Step 5: Snapshot**

```bash
SNAP="$TMPDIR/director_snapshots/task04"; mkdir -p "$SNAP"
cp "tools/build_director.py" "Modding Files/pack/script/campaign/mod/derpy_director.lua" "$SNAP/"
```

---

### Task 4b: Proximity and self-priority — the other two cast terms

Spec §5 specifies **three** scoring terms and Task 4 built one. This task adds the rest. Without
them the Director casts factions on the far side of the map who could never arrive, and conscripts
factions already fighting for their lives.

**Files:**
- Modify: `Modding Files/pack/script/campaign/mod/derpy_director.lua`
- Modify: `tools/build_director.py` (harness stubs and `_selftest`)

**Interfaces:**
- Consumes: `cast` and `hatred` from Task 4.
- Produces: `derpy_director:within_reach(region_key, max_hops) -> set of region keys` and
  `derpy_director:safety(faction) -> number` (1.0 for a faction at peace, falling as its war count
  rises). `cast` gains the two terms.

- [ ] **Step 1: Verify the REGION members before writing any code**

Run:

```bash
py tools\check_lua_api.py --explain adjacent_region_list
py tools\check_lua_api.py --explain factions_at_war_with
```

Expected: `adjacent_region_list` returns `REGION_LIST_SCRIPT_INTERFACE`, described as "the list of
regions adjacent to this one (including where the connection is not traversable)".
`factions_at_war_with` returns `FACTION_LIST_SCRIPT_INTERFACE`.

Then open `Modding Files/reference/ca_script_docs_wh3/scripting_doc.html`, find the
**`REGION_SCRIPT_INTERFACE`** block specifically, and confirm `name()` is listed on it and returns
the region key. **Do not take `--explain` at face value for `name` or `owning_faction`: both names
appear on several interfaces and the tool returns the first match — for `owning_faction` that is
the pooled resource manager, not the region.** If `name()` is not on REGION, stop and report it;
the design below depends on it and there is no point building on a guess.

This step exists because `SetImagePath`'s third argument and `region:province_name()` both shipped
to a player's screen from reading a signature and inferring the rest.

- [ ] **Step 2: Write the failing test**

Add a region model to `HARNESS`, above `local BY_NAME = {}`:

```lua
local REGIONS = {}
local function region(key, adj)
  local r = {}
  function r:name() return key end
  function r:is_null_interface() return false end
  function r:adjacent_region_list()
    local items = {}
    for _, k in ipairs(adj or {}) do
      if REGIONS[k] then items[#items + 1] = REGIONS[k] end
    end
    return list(items)
  end
  return r
end
for _, spec in ipairs(REGION_SPECS) do
  REGIONS[spec.key] = region(spec.key, spec.adj)
end
```

Inside `faction(spec)`, replace the `regions` block with:

```lua
  local owned = {}
  for _, k in ipairs(spec.owns or {}) do
    if REGIONS[k] then owned[#owned + 1] = REGIONS[k] end
  end
  for i = #owned + 1, (spec.regions or 0) do
    owned[i] = region("filler_" .. spec.name .. i, {})
  end
  function f:region_list() return list(owned) end
  function f:factions_at_war_with()
    local items = {}
    for _, n in ipairs(spec.wars or {}) do
      if BY_NAME[n] then items[#items + 1] = BY_NAME[n] end
    end
    return list(items)
  end
```

`factions_at_war_with` resolves through `BY_NAME` **at call time**, not at build time: the faction
it names may be constructed after this one.

Add the region manager to the `cm:model()` stub, alongside `world`:

```lua
    world = function() return {
      faction_list = function() return list(ORDER) end,
      region_manager = function() return {
        region_by_key = function(_, k) return REGIONS[k] end,
      } end,
    } end,
```

In `run_lua`, add a `regions_spec=None` parameter, emit `REGION_SPECS` into the preamble with a
helper mirroring `_faction_table`, and add `owns` and `wars` to `_faction_table`'s per-faction parts
using the same `_lua(f[lst])` treatment the `met`/`allies` lists get in `build_ai_coalitions.py`.

Add to `_selftest()`:

```python
    # 7b. Proximity: a hold 1 hop from the victim is cast, one 4 hops away is not, though both
    # hate the sacker identically. The engine will not assist beyond 3 hops regardless of intent -
    # war_coordination_assist_attack_*_max_distance is 3.0 on all 78 personalities, measured.
    regions = [
        {"key": "r_victim", "adj": ["r_near"]},
        {"key": "r_near", "adj": ["r_victim", "r_mid"]},
        {"key": "r_mid", "adj": ["r_near", "r_far1"]},
        {"key": "r_far1", "adj": ["r_mid", "r_far2"]},
        {"key": "r_far2", "adj": ["r_far1"]},
    ]
    near_world = [
        {"name": "sacker", "regions": 20, "subculture": CHD},
        {"name": "victim", "subculture": DWF, "owns": ["r_victim"], "regions": 3},
        {"name": "near_hold", "subculture": DWF, "owns": ["r_near"], "regions": 3},
        {"name": "far_hold", "subculture": DWF, "owns": ["r_far2"], "regions": 3},
    ]
    ev2 = [{"event": "CharacterSackedSettlement", "instigator": "sacker",
            "victim": "victim", "region": "r_victim"}]
    calls, _ = run_lua(near_world, events=ev2, regions_spec=regions)
    line = [c[1] for c in calls if c[0] == "out"
            and c[1].find("cast ") == len("[director] ")][0]
    assert "near_hold" in line, line
    assert "far_hold" not in line, line

    # 7c. Self-priority: of two equally-placed, equally-hateful holds, the one already fighting
    # three wars ranks below the one at peace. "Self priority first" as a scoring TERM, not a
    # special case - a besieged faction is outranked, never excluded.
    busy_world = [
        {"name": "sacker", "regions": 20, "subculture": CHD},
        {"name": "victim", "subculture": DWF, "owns": ["r_victim"], "regions": 3},
        {"name": "aa_busy", "subculture": DWF, "owns": ["r_near"], "regions": 3,
         "wars": ["sacker", "victim", "zz_calm"]},
        {"name": "zz_calm", "subculture": DWF, "owns": ["r_near"], "regions": 3},
    ]
    calls, _ = run_lua(busy_world, events=ev2, regions_spec=regions)
    line = [c[1] for c in calls if c[0] == "out"
            and c[1].find("cast ") == len("[director] ")][0]
    # The names are chosen so the alphabetical tiebreak would put aa_busy FIRST if the safety
    # term were absent or inert. It must not be first.
    assert line.index("zz_calm") < line.index("aa_busy"), line
    print("selftest: proximity and self-priority ok")
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `py tools\build_director.py --selftest`

Expected: FAIL at 7b — `far_hold` appears in the cast line, because nothing measures distance yet.

- [ ] **Step 4: Write the implementation**

Add to `derpy_director.lua`, above `cast`:

```lua
local MAX_HOPS = 3
local WAR_PENALTY = 0.25

-- Every region within max_hops of the origin, as a set of region keys. Breadth-first, so the
-- first time a region is seen is by its shortest path. Works in region KEYS only and never asks
-- who owns anything: `owning_faction` is a name shared by several interfaces, and the one
-- --explain returns is the pooled resource manager's, not the region's.
--
-- MAX_HOPS is 3 because war_coordination_assist_attack_force_max_distance and
-- _settlement_max_distance are both 3.0 on ALL 78 personalities - one distinct value, measured.
-- Beyond 3 the engine will not send help regardless of how much a faction wants to.
function derpy_director:within_reach(origin_key, max_hops)
	local seen = {[origin_key] = true}
	local frontier = {origin_key}
	local rm = cm:model():world():region_manager()
	for _ = 1, max_hops do
		local next_frontier = {}
		for _, key in ipairs(frontier) do
			local r = rm:region_by_key(key)
			if r and not r:is_null_interface() then
				for _, adj in model_pairs(r:adjacent_region_list()) do
					local k = adj:name()
					if not seen[k] then
						seen[k] = true
						next_frontier[#next_frontier + 1] = k
					end
				end
			end
		end
		frontier = next_frontier
	end
	return seen
end

-- 1.0 at peace, falling as the war count rises, floored so a faction fighting ten wars is
-- outranked rather than excluded. Counting wars is the readable proxy for "can this faction
-- afford to care": faction strength is no DB column, and military_force_list counts garrisons,
-- so any army-based measure overstates.
function derpy_director:safety(f)
	local wars = f:factions_at_war_with():num_items()
	local s = 1.0 - (wars * WAR_PENALTY)
	if s < 0.1 then s = 0.1 end
	return s
end
```

Immediately before the candidate loop in `cast`, add:

```lua
	-- Computed ONCE per situation, not once per candidate: a BFS per faction would walk the map
	-- up to 100 times a turn.
	local reach = self:within_reach(sit.region, MAX_HOPS)
```

and replace the `if base < 0 then` block with:

```lua
			if base < 0 then
				local reachable = false
				for _, r in model_pairs(f:region_list()) do
					if reach[r:name()] then reachable = true break end
				end
				if reachable then
					scored[#scored + 1] = {
						name = f:name(),
						score = (-base) * neg * self:safety(f),
					}
				end
			end
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `py tools\build_director.py --selftest`

Expected: PASS, printing `selftest: proximity and self-priority ok`.

- [ ] **Step 6: Snapshot**

```bash
SNAP="$TMPDIR/director_snapshots/task04b"; mkdir -p "$SNAP"
cp "tools/build_director.py" "Modding Files/pack/script/campaign/mod/derpy_director.lua" "$SNAP/"
```

---

### Task 5: The cheap beats — `ask` and `mood`

**Files:**
- Modify: `Modding Files/pack/script/campaign/mod/derpy_director.lua`
- Modify: `tools/build_director.py` (harness stubs and `_selftest`)

**Interfaces:**
- Consumes: `cast` from Task 4.
- Produces: `derpy_director:beat_ask(a_key, b_key, deal) -> score_a, score_b, ok_a, ok_b` and
  `derpy_director:beat_mood(target_key, score)`.

- [ ] **Step 1: Write the failing test**

Add these stubs to `HARNESS` in `tools/build_director.py`, immediately after the `cm:random_number`
definition:

```lua
function cm:cai_evaluate_quick_deal_action(a, b, deal)
  record("cai_evaluate_quick_deal_action", a:name(), b:name(), deal)
  local s = SCORES[a:name() .. "|" .. b:name()]
  if s == nil then return 0, true end
  return s, true
end
function cm:set_base_strategic_threat_score(f, score)
  record("set_base_strategic_threat_score", f:name(), score)
end
```

Add `SCORES = %s\n` to the preamble in `run_lua` and a `scores=None` parameter:

```python
def run_lua(factions, events=None, disable=False, preload=None, seed=50, scores=None):
```

and inside the preamble string add `"SCORES = %s\n"` with `_lua(scores or {})` in the matching
position.

Add to `_selftest()`:

```python
    # 8. ask() passes faction INTERFACES (not key strings), asks both directions, and logs the
    # can-propose flags as well as the scores. The Coalition Supervisor produced 44 sessions of
    # logs that could not answer its one open question because it logged scores alone.
    calls, _ = run_lua(world, events=ev, scores={"hold_a|hold_b": 5, "hold_b|hold_a": 5})
    asked = [(c[1], c[2]) for c in calls if c[0] == "cai_evaluate_quick_deal_action"]
    assert ("hold_a", "hold_b") in asked, asked
    assert ("hold_b", "hold_a") in asked, asked
    line = [c[1] for c in calls if c[0] == "out" and "ask " in c[1]]
    assert line and "ok=" in line[0], line

    # 9. mood() writes the threat score onto the INSTIGATOR, which is the faction the world is
    # reacting to - not onto the cast.
    scored = [c for c in calls if c[0] == "set_base_strategic_threat_score"]
    assert scored and scored[0][1] == "sacker", scored
    print("selftest: cheap beats ok")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py tools\build_director.py --selftest`

Expected: FAIL at assertion 8 — `asked` is empty because no beat asks anything yet.

- [ ] **Step 3: Write the implementation**

Add to `derpy_director.lua`, above `on_event`:

```lua
local DEAL = "diplomatic_option_defensive_alliance"
local THREAT_SCORE = 200

-- cai_evaluate_quick_deal_action takes faction INTERFACES for both parties (the force_* family
-- takes key strings - the conventions are inconsistent and unmarked in CA's docs). It returns
-- TWO values: the score, and whether the deal can be proposed at all. CA: "a quick deal score
-- greater than zero means it would likely be accepted".
function derpy_director:beat_ask(a_key, b_key, deal)
	local a, b = cm:get_faction(a_key), cm:get_faction(b_key)
	if not a or not b or a:is_null_interface() or b:is_null_interface() then
		return nil, nil, false, false
	end
	local score_a, ok_a = cm:cai_evaluate_quick_deal_action(a, b, deal)
	local score_b, ok_b = cm:cai_evaluate_quick_deal_action(b, a, deal)
	-- Both halves: a rejection has two unrelated causes and the scores alone cannot tell them
	-- apart. ok=false is "the engine will not propose this at all"; a score <= 0 is the AI
	-- having considered it and refused.
	log(string.format("ask %s<->%s %s/%s ok=%s/%s", a_key, b_key,
		tostring(score_a), tostring(score_b), tostring(ok_a), tostring(ok_b)))
	return score_a, score_b, ok_a, ok_b
end

-- set_base_strategic_threat_score takes a faction INTERFACE. The score maps onto
-- faction_strategic_threat_levels (0/100/200/350/500), each applying
-- wh_main_bundle_faction_imperium_level_N: -5/-10/-20/-30 attitude with everyone. Reversible by
-- writing 0, and visible on the diplomacy screen.
function derpy_director:beat_mood(target_key, score)
	local f = cm:get_faction(target_key)
	if not f or f:is_null_interface() then return false end
	cm:set_base_strategic_threat_score(f, score)
	log("mood threat=" .. tostring(score) .. " on " .. target_key)
	return true
end
```

And append to `on_event`, after the cast log line:

```lua
	self:beat_mood(sit.instigator, THREAT_SCORE)
	for i = 1, #cast do
		for j = i + 1, #cast do
			self:beat_ask(cast[i], cast[j], DEAL)
		end
	end
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `py tools\build_director.py --selftest`

Expected: PASS, printing `selftest: cheap beats ok`.

- [ ] **Step 5: Snapshot**

```bash
SNAP="$TMPDIR/director_snapshots/task05"; mkdir -p "$SNAP"
cp "tools/build_director.py" "Modding Files/pack/script/campaign/mod/derpy_director.lua" "$SNAP/"
```

---

### Task 6: The expensive beats — `force`, the past event, and `tell`

**Files:**
- Modify: `Modding Files/pack/script/campaign/mod/derpy_director.lua`
- Modify: `tools/build_director.py` (harness stubs and `_selftest`)

**Interfaces:**
- Consumes: `beat_ask` from Task 5.
- Produces: `derpy_director:beat_force(a_key, b_key)`,
  `derpy_director:beat_past_event(from_key, to_key)`, `derpy_director:beat_tell(key, a, b)`.

- [ ] **Step 1: Write the failing test**

Add these stubs to `HARNESS`, after the ones from Task 5:

```lua
function cm:force_alliance(a, b, military)
  record("force_alliance", a, b, tostring(military))
end
function cm:force_confederation(a, b) record("force_confederation", a, b) end
function cm:cai_add_diplomatic_event(from, to, action)
  record("cai_add_diplomatic_event", from, to, action)
end
function cm:show_message_event(faction, title, primary, secondary, persistent, index)
  record("show_message_event", faction, title, tostring(index))
end
```

Add to `_selftest()`:

```python
    # 10. A mutual yes is forced; a one-sided or refused pair never is.
    calls, _ = run_lua(world, events=ev, scores={"hold_a|hold_b": 5, "hold_b|hold_a": 5})
    forced = [(c[1], c[2], c[3]) for c in calls if c[0] == "force_alliance"]
    assert forced == [("hold_a", "hold_b", "false")], forced

    calls, _ = run_lua(world, events=ev, scores={"hold_a|hold_b": 5, "hold_b|hold_a": -1})
    assert not [c for c in calls if c[0] == "force_alliance"], calls

    # 11. The past event fires once per cast faction, from the INSTIGATOR, and never twice for
    # the same situation. It has NO inverse - accumulated attitude damage stays for the campaign -
    # so a repeat is permanent over-punishment that nothing can undo.
    calls, _ = run_lua(world, events=ev * 3, scores={"hold_a|hold_b": 5, "hold_b|hold_a": 5})
    events_fired = [c for c in calls if c[0] == "cai_add_diplomatic_event"]
    assert all(e[1] == "sacker" for e in events_fired), events_fired
    assert all(e[3] == "PAST_EVENT_NEGATIVE_MINOR" for e in events_fired), events_fired
    assert len(events_fired) == 2, events_fired   # hold_a and hold_b, from the FIRST sack only

    # 12. tell() never passes index 0 - show_message_event's last argument indexes
    # event_feed_message_events and 0 draws nothing at all.
    told = [c for c in calls if c[0] == "show_message_event"]
    assert told, calls
    assert all(t[3] not in ("0", "0.0", "nil") for t in told), told
    print("selftest: expensive beats ok")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py tools\build_director.py --selftest`

Expected: FAIL at assertion 10 — `forced` is `[]` because nothing forces anything yet.

- [ ] **Step 3: Write the implementation**

Add to `derpy_director.lua`, above `on_event`:

```lua
local PAST_EVENT = "PAST_EVENT_NEGATIVE_MINOR"
local FEED_INDEX = 1

-- The force_* family takes KEY STRINGS for both factions, unlike the cai_ calls above.
function derpy_director:beat_force(a_key, b_key)
	-- force_confederation(X, X) crashes the game. This beat does not confederate, but the
	-- self-check belongs with the family so it is never reintroduced by a later scenario.
	if a_key == b_key then
		log("force refused: a faction cannot treat with itself")
		return false
	end
	cm:force_alliance(a_key, b_key, false)
	log("forced defensive alliance " .. a_key .. " + " .. b_key)
	return true
end

-- cai_add_diplomatic_event has NO strength argument: the magnitude lives in the DB row, so you
-- choose the event whose factor group already carries the weight you want. It also has no
-- inverse - nothing undoes accumulated attitude damage - so this fires once per situation and
-- never again, however long the situation persists.
function derpy_director:beat_past_event(from_key, to_key)
	cm:cai_add_diplomatic_event(from_key, to_key, PAST_EVENT)
	log(string.format("past_event from=%s to=%s %s", from_key, to_key, PAST_EVENT))
	return true
end

-- The last argument indexes event_feed_message_events; 0 draws NOTHING. Phase 1 ships no DB
-- rows, so FEED_INDEX points at an existing vanilla row and the strings are vanilla keys.
-- NO loc is resolved here: this runs inside a listener, and a loc call from one CTDs at turn 1
-- with pcall unable to catch it.
function derpy_director:beat_tell(faction_key, title_key, body_key)
	cm:show_message_event(faction_key, title_key, body_key, body_key, true, FEED_INDEX)
	log("told " .. faction_key .. " " .. title_key)
	return true
end
```

Replace the ask loop at the end of `on_event` with:

```lua
	self:beat_mood(sit.instigator, THREAT_SCORE)

	-- Once per situation, not once per turn the situation persists.
	local seen_key = "derpy_director_seen_" .. sit.instigator .. "_" .. tostring(sit.region)
	local already = cm:get_saved_value(seen_key)
	if not already then
		for i = 1, #cast do
			self:beat_past_event(sit.instigator, cast[i])
		end
		self:beat_tell(sit.instigator, "director_kin_avenge", "director_kin_avenge_body")
		cm:set_saved_value(seen_key, true)
	end

	for i = 1, #cast do
		for j = i + 1, #cast do
			local sa, sb, oa, ob = self:beat_ask(cast[i], cast[j], DEAL)
			if oa and ob and sa and sb and sa > 0 and sb > 0 then
				self:beat_force(cast[i], cast[j])
			end
		end
	end
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `py tools\build_director.py --selftest`

Expected: PASS, printing `selftest: expensive beats ok`.

- [ ] **Step 5: Snapshot**

```bash
SNAP="$TMPDIR/director_snapshots/task06"; mkdir -p "$SNAP"
cp "tools/build_director.py" "Modding Files/pack/script/campaign/mod/derpy_director.lua" "$SNAP/"
```

---

### Task 7: The budget, cooldowns, and persistence

**Files:**
- Modify: `Modding Files/pack/script/campaign/mod/derpy_director.lua`
- Modify: `tools/build_director.py` (`_selftest` only)

**Interfaces:**
- Consumes: all beats from Tasks 5 and 6.
- Produces: `derpy_director:afford(price) -> bool`, `derpy_director:on_cooldown(key) -> bool`,
  and the saved values `derpy_director_budget` (number) and `derpy_director_cooldowns` (table of
  faction key to turn number).

- [ ] **Step 1: Write the failing test**

Add to `_selftest()`:

```python
    # 13. The budget is spent and saved. A world already out of budget runs NO expensive beat,
    # while cheap reads still happen - the budget is a safety mechanism, not an off switch.
    calls, state = run_lua(world, events=ev, scores={"hold_a|hold_b": 5, "hold_b|hold_a": 5})
    assert state["derpy_director_budget"] not in ("nil", "None"), state
    spent = float(state["derpy_director_budget"])

    calls, _ = run_lua(world, events=ev, scores={"hold_a|hold_b": 5, "hold_b|hold_a": 5},
                       preload={"derpy_director_budget": 0})
    assert not [c for c in calls if c[0] == "cai_add_diplomatic_event"], calls
    assert not [c for c in calls if c[0] == "force_alliance"], calls
    assert [c for c in calls if c[0] == "cai_evaluate_quick_deal_action"], \
        "asks are free and must still happen"
    assert [c for c in calls if c[0] == "out" and "budget" in c[1]], calls

    # 14. A faction on cooldown is not cast again.
    calls, _ = run_lua(world, events=ev, scores={"hold_a|hold_b": 5, "hold_b|hold_a": 5},
                       preload={"derpy_director_cooldowns": {"hold_a": 99}})
    line = [c[1] for c in calls if c[0] == "out" and c[1].find("cast ") == len("[director] ")]
    assert line and "hold_a" not in line[0], line
    print("selftest: budget, cooldown and persistence ok")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py tools\build_director.py --selftest`

Expected: FAIL at assertion 13 with a `KeyError` or a `nil` budget — nothing saves a budget yet.

- [ ] **Step 3: Write the implementation**

Add to `derpy_director.lua`, above `cast`:

```lua
local BUDGET_START = 100
local BUDGET_REFILL = 5
local COOLDOWN_TURNS = 12
-- Priced by how hard a beat is to UNDO, not by how many ran. When a situation passes, reversible
-- effects are released and irreversible ones stay for the whole campaign.
local PRICE = {ask = 0, mood = 5, force = 15, past_event = 40, tell = 0}

function derpy_director:budget()
	local b = cm:get_saved_value("derpy_director_budget")
	if b == nil then return BUDGET_START end
	return b
end

function derpy_director:afford(price)
	if price <= 0 then return true end
	local b = self:budget()
	if b < price then
		log(string.format("budget %d cannot afford %d, beat skipped", b, price))
		return false
	end
	cm:set_saved_value("derpy_director_budget", b - price)
	return true
end

function derpy_director:cooldowns()
	local c = cm:get_saved_value("derpy_director_cooldowns")
	if type(c) ~= "table" then return {} end
	return c
end

function derpy_director:on_cooldown(key)
	local c = self:cooldowns()[key]
	if not c then return false end
	return cm:model():turn_number() < c
end

function derpy_director:set_cooldown(key)
	local c = self:cooldowns()
	c[key] = cm:model():turn_number() + COOLDOWN_TURNS
	cm:set_saved_value("derpy_director_cooldowns", c)
end
```

In `cast`, add the cooldown test to the candidate guard, immediately after the region-count check:

```lua
				and not self:on_cooldown(f:name()) then
```

(replacing `and f:region_list():num_items() >= 2 then` with
`and f:region_list():num_items() >= 2` followed by the line above).

In `on_event`, gate every priced beat. Replace the block added in Task 6 with:

```lua
	if self:afford(PRICE.mood) then
		self:beat_mood(sit.instigator, THREAT_SCORE)
	end

	local seen_key = "derpy_director_seen_" .. sit.instigator .. "_" .. tostring(sit.region)
	if not cm:get_saved_value(seen_key) then
		local fired = false
		for i = 1, #cast do
			if self:afford(PRICE.past_event) then
				self:beat_past_event(sit.instigator, cast[i])
				self:set_cooldown(cast[i])
				fired = true
			end
		end
		if fired then
			self:beat_tell(sit.instigator, "director_kin_avenge", "director_kin_avenge_body")
		end
		cm:set_saved_value(seen_key, true)
	end

	for i = 1, #cast do
		for j = i + 1, #cast do
			local sa, sb, oa, ob = self:beat_ask(cast[i], cast[j], DEAL)
			if oa and ob and sa and sb and sa > 0 and sb > 0 and self:afford(PRICE.force) then
				self:beat_force(cast[i], cast[j])
			end
		end
	end
```

And in `first_tick`, refill:

```lua
	local b = self:budget() + BUDGET_REFILL
	if b > BUDGET_START then b = BUDGET_START end
	cm:set_saved_value("derpy_director_budget", b)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `py tools\build_director.py --selftest`

Expected: PASS, printing `selftest: budget, cooldown and persistence ok`.

- [ ] **Step 5: Snapshot**

```bash
SNAP="$TMPDIR/director_snapshots/task07"; mkdir -p "$SNAP"
cp "tools/build_director.py" "Modding Files/pack/script/campaign/mod/derpy_director.lua" "$SNAP/"
```

---

### Task 8: The static checks, and the news ring buffer

**Files:**
- Modify: `Modding Files/pack/script/campaign/mod/derpy_director.lua`
- Modify: `tools/build_director.py` (`_selftest` only)

**Interfaces:**
- Consumes: everything above.
- Produces: the saved value `derpy_director_news`, an array of
  `{turn, kind, instigator, victim, region}` capped at `NEWS_CAP` entries, **keys and numbers only**.

- [ ] **Step 1: Write the failing test**

Add to `_selftest()`:

```python
    # 15. News entries are keys and numbers only. A news entry is written in a LISTENER and read
    # much later by a panel; a loc call from a listener CTDs at turn 1 and pcall does not catch
    # it, so no resolved text may ever enter this buffer.
    calls, state = run_lua(world, events=ev)
    assert state["derpy_director_news"] not in ("nil", "None"), state

    # 16. Nothing in either shipped file resolves loc, anywhere.
    for path in (SCRIPT, LORE):
        src = open(path, encoding="utf-8").read()
        for banned in ("effect.get_localised_string", "common.get_localised_string",
                       "get_localised_string"):
            assert banned not in src, "loc call CTDs at turn 1: %s in %s" % (banned, path)

    # 17. luac, the API check and the undeclared-global check all pass on both shipped files.
    for path in (SCRIPT, LORE):
        for cmd in ([LUAC, "-p", path],
                    [sys.executable, os.path.join(ROOT, "tools", "check_lua_api.py"), path],
                    [sys.executable, os.path.join(ROOT, "tools", "check_lua_undeclared.py"),
                     path]):
            r = subprocess.run(cmd, capture_output=True, text=True)
            assert r.returncode == 0, "%s failed on %s:\n%s" % (
                os.path.basename(cmd[0]), path, r.stdout + r.stderr)
    print("selftest: news buffer and static checks ok")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py tools\build_director.py --selftest`

Expected: FAIL at assertion 15 — `derpy_director_news` is `nil` because nothing writes it.

- [ ] **Step 3: Write the implementation**

Add to `derpy_director.lua`, above `on_event`:

```lua
local NEWS_CAP = 50

-- KEYS AND NUMBERS ONLY. This buffer is written in a listener and read much later by a panel.
-- Resolving a name here would mean a loc call from a listener, which CTDs at turn 1 with pcall
-- unable to catch it. Every name and sentence is resolved at DRAW time instead. It also keeps
-- the buffer small, and every entry of it rides in the save for the life of the campaign.
function derpy_director:news(sit, cast_size)
	local buf = cm:get_saved_value("derpy_director_news")
	if type(buf) ~= "table" then buf = {} end
	buf[#buf + 1] = {sit.turn, sit.kind, sit.instigator, sit.victim, tostring(sit.region),
		cast_size}
	while #buf > NEWS_CAP do table.remove(buf, 1) end
	cm:set_saved_value("derpy_director_news", buf)
end
```

And as the final line of `on_event`:

```lua
	self:news(sit, #cast)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `py tools\build_director.py --selftest`

Expected: PASS, printing `selftest: news buffer and static checks ok`.

If `check_lua_undeclared.py` reports a finding, it has found an ALL_CAPS name the file reads but
nothing declares. An undeclared Lua global is nil rather than an error, so `luac -p` passes over it
and the branch reading it dies silently. Declare the constant; do not suppress the check.

- [ ] **Step 5: Snapshot**

```bash
SNAP="$TMPDIR/director_snapshots/task08"; mkdir -p "$SNAP"
cp "tools/build_director.py" "Modding Files/pack/script/campaign/mod/derpy_director.lua" "$SNAP/"
```

---

### Task 9: `mutate_director.py` — prove the assertions can fail

**Files:**
- Create: `tools/mutate_director.py`

**Interfaces:**
- Consumes: `tools/build_director.py --selftest`.
- Produces: a command-line tool with `--selftest`.

- [ ] **Step 1: Write the tool**

A check nobody has watched fail proves nothing. `mutate_iron_court.py` has already found three
assertions in this workspace that had quietly become unbreakable, and the Director has more
scoring, budget and cooldown logic than the Iron Court does.

Create `tools/mutate_director.py`:

```python
"""Break the Director's rules one at a time and prove the selftest notices.

    py tools/mutate_director.py             run every mutant
    py tools/mutate_director.py --selftest  prove the runner reports a survivor and a stale anchor

Each mutant is a plausible implementation mistake, not a typo: the guard somebody forgets, the
clamp somebody thinks is redundant. The mutation goes into the SHIPPED Lua and is restored in a
finally. A STALE ANCHOR is a finding, not a skip - it means the code a mutant was aimed at has
moved, and nobody has checked whether the assertion aimed at it moved too.
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "Modding Files", "pack", "script", "campaign", "mod",
                      "derpy_director.lua")
BUILD = os.path.join(ROOT, "tools", "build_director.py")

MUTANTS = [
    ("human is castable",
     "and not f:is_human()", "and true"),
    ("dead factions are castable",
     "and not f:is_dead()", "and true"),
    ("the instigator casts itself",
     'and f:name() ~= sit.instigator', "and true"),
    ("cooldown is ignored",
     "and not self:on_cooldown(f:name())", "and true"),
    ("neutral cultures are cast",
     "if base < 0 then", "if base <= 0 then"),
    ("the budget never refuses",
     "if b < price then", "if false then"),
    ("the past event re-fires every turn",
     'if not cm:get_saved_value(seen_key) then', "if true then"),
    ("a one-sided yes is forced",
     "sa > 0 and sb > 0", "sa > 0 or sb > 0"),
    ("the news buffer is unbounded",
     "while #buf > NEWS_CAP do", "while false do"),
    ("distance is ignored",
     "if reach[r:name()] then reachable = true break end", "reachable = true"),
    ("the safety term is inert",
     "* self:safety(f)", "* 1.0"),
    ("reach is unbounded",
     "local MAX_HOPS = 3", "local MAX_HOPS = 99"),
    ("the cast sort has no tiebreak",
     "return x.name < y.name", "return false"),
]


def _selftest_passes():
    r = subprocess.run([sys.executable, BUILD, "--selftest"], capture_output=True, text=True)
    return r.returncode == 0


def run(mutants=None):
    mutants = mutants or MUTANTS
    original = open(SCRIPT, encoding="utf-8", newline="").read()
    assert _selftest_passes(), "the selftest is RED before mutating - fix that first"
    survivors, stale = [], []
    try:
        for name, find, replace in mutants:
            if original.count(find) != 1:
                stale.append("%s (anchor %r appears %d times, expected 1)"
                             % (name, find, original.count(find)))
                continue
            open(SCRIPT, "w", encoding="utf-8", newline="").write(
                original.replace(find, replace, 1))
            if _selftest_passes():
                survivors.append(name)
    finally:
        open(SCRIPT, "w", encoding="utf-8", newline="").write(original)
    assert open(SCRIPT, encoding="utf-8", newline="").read() == original, \
        "the shipped file was NOT restored byte for byte"
    assert _selftest_passes(), "the selftest is RED after restoring - the file is damaged"
    for s in stale:
        print("STALE ANCHOR: %s" % s)
    for s in survivors:
        print("SURVIVED (no assertion catches this): %s" % s)
    print("%d mutants, %d survived, %d stale anchors"
          % (len(mutants), len(survivors), len(stale)))
    return survivors, stale


def _selftest():
    # A mutant that changes nothing must SURVIVE, and a bad anchor must be reported STALE.
    # If the runner cannot report either, a clean report from it means nothing.
    survivors, stale = run([
        ("no-op control", "local ENABLED = true", "local ENABLED = true "),
        ("deliberately bad anchor", "this string is not in the file", "x"),
    ])
    assert survivors == ["no-op control"], survivors
    assert len(stale) == 1 and "deliberately bad anchor" in stale[0], stale
    print("selftest ok - the runner reports survivors and stale anchors, and restores the file")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        survivors, stale = run()
        sys.exit(1 if (survivors or stale) else 0)
```

- [ ] **Step 2: Run the runner's own selftest**

Run: `py tools\mutate_director.py --selftest`

Expected: PASS, printing `selftest ok - the runner reports survivors and stale anchors, and
restores the file`.

- [ ] **Step 3: Run every mutant**

Run: `py tools\mutate_director.py`

Expected: `13 mutants, 0 survived, 0 stale anchors`, exit 0.

- [ ] **Step 4: Fix any survivor by adding an assertion, never by deleting the mutant**

A survivor means no assertion in `build_director.py` catches that mistake. Add one to
`_selftest()`, re-run both commands, and only then continue. A stale anchor means the code moved —
go and check whether the assertion aimed at it moved too.

- [ ] **Step 5: Snapshot**

```bash
SNAP="$TMPDIR/director_snapshots/task09"; mkdir -p "$SNAP"
cp "tools/mutate_director.py" "tools/build_director.py" "$SNAP/"
cp "Modding Files/pack/script/campaign/mod/derpy_director.lua" "$SNAP/"
```

---

### Task 10: Pack it

**Files:**
- Modify: `tools/build_director.py` (add `pack()`)

**Interfaces:**
- Consumes: `_selftest`, `check`, `SCRIPT`, `LORE`, `PACK`, `IN_PACK`, `IN_PACK_LORE`.
- Produces: `Modding Files/Modpacks/derpy_director.pack`.

- [ ] **Step 1: Write the packer**

The RPFM MCP server only exists while RPFM is open. A connection refusal means RPFM is shut, and
there is no fallback — never hand-edit a `.pack`.

Add to `tools/build_director.py`:

```python
def pack():
    """Create or refresh derpy_director.pack. Needs RPFM open."""
    import datetime
    import shutil
    from check_skill_trees import _rpc, _call

    _selftest()

    _rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                        "clientInfo": {"name": "build_director", "version": "1"}})
    _rpc("notifications/initialized", notify=True)
    # rebuild_dependencies=False binds the schema without the 105MB rebuild. This pack has no DB
    # rows, so nothing here needs the dependency cache. get_game_selected already answers
    # warhammer_3 while is_schema_loaded is still false - the game key is global, the schema
    # binding is per-session, and that pairing is not a fault.
    _call("set_game_selected", {"game_name": "warhammer_3", "rebuild_dependencies": False})

    if os.path.exists(PACK):
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(PACK, "%s.bak_%s" % (PACK, stamp))
        print("backed up the existing pack")
        key = _call("open_packfiles", {"paths": [PACK]})["StringContainerInfo"][0]
    else:
        key = _call("new_pack", {})["String"]
        assert key, "new_pack returned no key"
        _call("set_pack_file_type", {"pack_key": key, "pack_file_type": '"Mod"'})

    _call("add_packed_files", {"pack_key": key, "source_paths": [SCRIPT, LORE],
                               "destination_paths": json.dumps(
                                   [{"File": IN_PACK}, {"File": IN_PACK_LORE}])})
    _call("save_pack_as", {"pack_key": key, "path": PACK})
    print("saved %s" % PACK)

    # A file that is merely present proves nothing. Re-open the SAVED pack and read it back.
    # get_packed_files_info takes `values` as a list of PLAIN STRINGS - the one call here that
    # does not use the ContainerPath convention its neighbours use. A miss returns
    # {"VecRFileInfo": []}, with no echo of the queried path, so matching on the "path" field of
    # a returned entry genuinely discriminates rather than riding on a coincidence.
    again = _call("open_packfiles", {"paths": [PACK]})["StringContainerInfo"][0]
    info = _call("get_packed_files_info", {"pack_key": again,
                                           "values": [IN_PACK, IN_PACK_LORE]})
    assert isinstance(info, dict) and "VecRFileInfo" in info, \
        "unexpected get_packed_files_info response shape: %s" % (info,)
    paths = {e.get("path") for e in info["VecRFileInfo"]}
    for want in (IN_PACK, IN_PACK_LORE):
        assert want in paths, "%s is not in the saved pack: %s" % (want, info)
    print("verified: both files are in the saved pack")
```

And change `__main__` so the no-flag path packs:

```python
if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    elif "--check" in sys.argv:
        check()
    else:
        pack()
```

- [ ] **Step 2: Confirm RPFM is running**

Run: `curl -s -m 4 http://127.0.0.1:45127/sessions`

Expected: a JSON array of sessions. Connection refused means RPFM is shut — open it and retry.
Do not proceed without it.

- [ ] **Step 3: Pack**

Run: `py tools\build_director.py`

Expected: the nine selftest lines, then `saved ...derpy_director.pack`, then
`verified: both files are in the saved pack`.

- [ ] **Step 4: Verify the pack from the outside**

Run:

```bash
py tools/read_pack_index.py "Modding Files/Modpacks/derpy_director.pack"
```

Expected: both `script/campaign/mod/derpy_director.lua` and
`script/campaign/mod/derpy_director_lore.lua` listed. A pack is **not** byte-reproducible (DB
tables carry a per-save GUID), so never compare two builds by hash — compare contents.

- [ ] **Step 5: Snapshot**

```bash
SNAP="$TMPDIR/director_snapshots/task10"; mkdir -p "$SNAP"
cp "tools/build_director.py" "$SNAP/"
cp "Modding Files/pack/script/campaign/mod/derpy_director.lua" "$SNAP/"
cp "Modding Files/pack/script/campaign/mod/derpy_director_lore.lua" "$SNAP/"
```

**Deployment is deliberately NOT part of this plan.** A new pack copied into
`F:\SteamLibrary\steamapps\common\Total War WARHAMMER III\data\` is listed but **unticked**, and
`derpy_ai_coalitions` is still live and still supervises runaway leaders. Decide whether the two
run together before enabling either.

---

## Phase 1 exit criteria

- `py tools\build_director.py --selftest` prints nine `selftest:` lines and exits 0.
- `py tools\mutate_director.py` reports `0 survived, 0 stale anchors`.
- `py tools\build_director.py --check` regenerates the lore file with no diff.
- `derpy_director.pack` contains both Lua files, verified by re-reading the saved pack.
- Not deployed, not played.

## What Phase 1 deliberately does not build

Per spec §18: the `target` beat and its DB half (Phase 4), the campaign seed (Phase 2), the other
three scenarios (Phase 2), the news panel (Phase 3), and the separate call-to-arms pack (Phase 5).
`muster` is specified in §6 but is **not** built here either — it is the only remaining beat with no
inverse, and Phase 1 has no scenario that needs it. Adding it before something needs it would be the
one irreversible lever built purely on speculation.
