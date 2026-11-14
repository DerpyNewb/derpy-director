# Coalition Supervisor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship one campaign Lua file that makes the AI turn on a runaway faction — raising its strategic threat score and forming defensive alliances the AI would already accept — with zero DB rows, plus the build tool whose `--selftest` runs that file under real Lua against stubs.

**Architecture:** `measure()` reads region counts, the pure `rung_for()` maps the leader/runner-up ratio to a rung 0-3 with hysteresis, and `tick()` applies three responses (threat score, polled alliances, global context slot). State survives saves through `cm:save_named_value`. The build tool copies the shipped file, runs it under `lua.exe` with a stubbed `cm`/`core`/faction model that records every call, and asserts on the recorded list — the test runs the artefact rather than re-implementing it.

**Tech Stack:** Lua 5.1.5 (`C:\Program Files (x86)\Lua\5.1\lua.exe`, `luac.exe`), Python 3 (`py`), RPFM MCP server at `127.0.0.1:45127` for packing only.

**Spec:** `docs/superpowers/specs/2026-09-13-ai-coalition-supervisor-design.md`

## Global Constraints

- **This workspace is not a git repo.** There are no commit steps. Each task ends with a checkpoint that runs `py tools/build_ai_coalitions.py --selftest` and requires it to exit 0. Before re-packing an existing pack, copy it to `<name>.pack.bak_<YYYYMMDD_HHMMSS>` first — the house convention.
- **Zero DB rows.** This mod ships exactly one file: `script/campaign/mod/derpy_ai_coalitions.lua`. If a task seems to need a DB table, stop and re-read the spec §1 non-goals.
- **No emojis anywhere** — not in code, comments, log strings or docs.
- **No loc calls from the turn handler.** A loc lookup there CTDs at turn 1 and `pcall` does not catch it. Log faction **keys**, never display names.
- **Never raw `pairs()` on anything whose order reaches a game call.** Sorted keys or `model_pairs` only; undefined order diverges across reloads and multiplayer clients.
- Exact constant values, copied from the spec: `MIN_REGIONS = 10`, `RUNG_RATIOS = {1.75, 2.5, 4.0}`, `EXIT_RATIO = 1.35`, `RUNG_SCORES = {200, 350, 500}`, `POLL_PAIRS = 8`, `MAX_FORCED_ALLIANCES = 2`, `PAST_EVENT = "PAST_EVENT_NEGATIVE_MINOR"`, `LOG_PREFIX = "[coalitions]"`.
- Exact keys, each verified against the vanilla DB on 2026-09-13. A wrong one fails silently forever: `diplomatic_option_defensive_alliance`, `cai_global_script_context_special_1`, `cai_global_script_context_type_default`.
- Static checks that must pass before packing: `luac -p` exit 0, `py tools/check_lua_api.py <file>` exit 0, `py tools/check_lua_undeclared.py <file>` exit 0.

## File Structure

| File | Responsibility |
|---|---|
| `Modding Files/pack/script/campaign/mod/derpy_ai_coalitions.lua` | Create. The entire shipped mod: constants, measurement, rung logic, the three responses, persistence, logging |
| `tools/build_ai_coalitions.py` | Create. `--selftest` (stub harness + assertions) and, with no flag, packs the file into `Modding Files/Modpacks/derpy_ai_coalitions.pack` via RPFM |

Two files, because the Lua is the product and the Python is the only thing that can test it offline. Nothing else in the workspace changes until the final task adds the two documentation pointers.

---

### Task 1: The harness, and the pure rung function

**Files:**
- Create: `tools/build_ai_coalitions.py`
- Create: `Modding Files/pack/script/campaign/mod/derpy_ai_coalitions.lua`

**Interfaces:**
- Consumes: nothing.
- Produces: `run_lua(factions, context=..., scores=None, turns=1, disable=False, preload=None, probe_rungs=None)` returning the **3-tuple** `(calls, state, rungs)` where `calls` is a list of `(name, arg1, arg2, arg3)` string tuples in call order and `state` is a dict of the mod's saved values. In Lua: the global table `coalitions` with `coalitions:rung_for(ratio, leader_regions, current)` returning a number 0-3, and `coalitions:measure()` returning `leader_interface, leader_regions, runner_up_regions, ratio` or `nil`.

- [x] **Step 1: Write the failing test**

Create `tools/build_ai_coalitions.py`:

```python
"""Build and check derpy_ai_coalitions.pack - the Coalition Supervisor.

    py tools/build_ai_coalitions.py --selftest   run the shipped Lua under stubs
    py tools/build_ai_coalitions.py              pack it (needs RPFM open)

The selftest RUNS `Modding Files/pack/script/campaign/mod/derpy_ai_coalitions.lua` under
Lua 5.1.5 against a stubbed campaign and asserts on the calls it recorded - it does not
re-implement the logic in Python. See docs/superpowers/specs/2026-09-13-ai-coalition-supervisor-design.md
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "Modding Files", "pack", "script", "campaign", "mod",
                      "derpy_ai_coalitions.lua")
LUA = r"C:\Program Files (x86)\Lua\5.1\lua.exe"
LUAC = r"C:\Program Files (x86)\Lua\5.1\luac.exe"

HARNESS = r'''
-- Stand-ins for the campaign environment: enough to load the mod file and record what it does.
local CALLS = {}
local SAVED = {}
local LISTENER, LOADER, SAVER

local function record(name, a, b, c)
  CALLS[#CALLS + 1] = {name, tostring(a), tostring(b), tostring(c)}
end

function out(msg) record("out", msg) end
function is_table(t) return type(t) == "table" end

-- A list interface over a plain array, walked the way CA walks model lists.
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

-- Faction stubs built from the FACTIONS preamble table.
local BY_NAME = {}
local ORDER = {}

local function faction(spec)
  local f = {}
  function f:name() return spec.name end
  function f:is_null_interface() return false end
  function f:is_dead() return spec.dead == true end
  function f:is_rebel() return spec.rebel == true end
  function f:is_human() return spec.human == true end
  function f:region_list() return list({}) end
  function f:region_count() return spec.regions or 0 end
  function f:factions_met()
    local met = {}
    for _, n in ipairs(spec.met or {}) do
      if BY_NAME[n] then met[#met + 1] = BY_NAME[n] end
    end
    return list(met)
  end
  function f:defensive_allies_with(other)
    for _, n in ipairs(spec.allies or {}) do if n == other:name() then return true end end
    return false
  end
  function f:military_allies_with(_) return false end
  return f
end

-- region_list():num_items() is how the mod counts regions, so give it a real list.
local function with_regions(f, n)
  local regions = {}
  for i = 1, n do regions[i] = {} end
  f.region_list = function() return list(regions) end
  return f
end

for _, spec in ipairs(FACTIONS) do
  local f = with_regions(faction(spec), spec.regions or 0)
  BY_NAME[spec.name] = f
  ORDER[#ORDER + 1] = f
end

local CURRENT_CONTEXT = CONTEXT

cm = {}
function cm:model()
  return {world = function() return {faction_list = function() return list(ORDER) end} end}
end
function cm:get_faction(key) return BY_NAME[key] or false end
function cm:set_base_strategic_threat_score(f, score)
  record("set_base_strategic_threat_score", f:name(), score)
end
function cm:cai_evaluate_quick_deal_action(a, b, deal)
  record("cai_evaluate_quick_deal_action", a:name(), b:name(), deal)
  local key = a:name() .. "|" .. b:name()
  local s = SCORES[key]
  if s == nil then return 0, true end
  return s, true
end
function cm:force_alliance(a, b, military)
  record("force_alliance", a, b, tostring(military))
end
function cm:cai_add_diplomatic_event(from, to, action)
  record("cai_add_diplomatic_event", from, to, action)
end
function cm:cai_get_global_script_context() return CURRENT_CONTEXT end
function cm:cai_set_global_script_context(key)
  record("cai_set_global_script_context", key)
  CURRENT_CONTEXT = key
end
function cm:cai_clear_global_script_context()
  record("cai_clear_global_script_context")
  CURRENT_CONTEXT = "cai_global_script_context_type_default"
end
function cm:add_first_tick_callback(fn) fn() end
function cm:add_saving_game_callback(fn) SAVER = fn end
function cm:add_loading_game_callback(fn) LOADER = fn end
function cm:save_named_value(name, value, _) SAVED[name] = value end
function cm:load_named_value(name, default, _)
  if PRELOAD[name] ~= nil then return PRELOAD[name] end
  if SAVED[name] ~= nil then return SAVED[name] end
  return default
end

core = {}
function core:add_listener(_, event, _, fn, _)
  if event == "WorldStartRound" then LISTENER = fn end
end

dofile(SCRIPT_PATH)

assert(LISTENER, "the mod registered no WorldStartRound listener")
-- A load happens before the first turn of a resumed campaign, and a save after the last:
-- drive both, or PRELOAD is ignored and SAVED is never written.
if LOADER then LOADER({}) end
for _ = 1, TURNS do LISTENER({}) end
if SAVER then SAVER({}) end

-- Hand the recorded calls and the saved state back as JSON-ish lines for the Python side.
local fh = io.open(DUMP_PATH, "w")
for _, c in ipairs(CALLS) do
  fh:write(c[1] .. "\t" .. c[2] .. "\t" .. c[3] .. "\t" .. c[4] .. "\n")
end
fh:write("===STATE\n")
for _, k in ipairs({"derpy_coalitions_rung", "derpy_coalitions_owns_context",
                    "derpy_coalitions_scored_key", "derpy_coalitions_cursor"}) do
  fh:write(k .. "\t" .. tostring(SAVED[k]) .. "\n")
end
fh:close()

-- Direct probes of the pure function, so its boundaries are pinned without a whole turn.
if PROBE_RUNGS then
  local fh2 = io.open(PROBE_PATH, "w")
  for _, p in ipairs(PROBE_RUNGS) do
    fh2:write(tostring(coalitions:rung_for(p[1], p[2], p[3])) .. "\n")
  end
  fh2:close()
end
'''


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
    out = []
    for f in factions:
        parts = ['name = %s' % _lua(f["name"]), 'regions = %s' % _lua(f.get("regions", 0))]
        for flag in ("dead", "rebel", "human"):
            if f.get(flag):
                parts.append("%s = true" % flag)
        for lst in ("met", "allies"):
            if f.get(lst):
                parts.append("%s = %s" % (lst, _lua(f[lst])))
        out.append("{" + ", ".join(parts) + "}")
    return "{" + ", ".join(out) + "}"


def run_lua(factions, context="cai_global_script_context_type_default", scores=None,
            turns=1, disable=False, preload=None, probe_rungs=None):
    """Run the SHIPPED Lua under the harness. Returns (calls, state, rungs)."""
    src = open(SCRIPT, encoding="utf-8").read()
    if disable:
        needle = "local ENABLED = true"
        assert src.count(needle) == 1, "cannot find the single ENABLED constant to flip"
        src = src.replace(needle, "local ENABLED = false")
    with tempfile.TemporaryDirectory() as td:
        script = os.path.join(td, "mod.lua")
        open(script, "w", encoding="utf-8").write(src)
        dump = os.path.join(td, "calls.txt")
        probe = os.path.join(td, "rungs.txt")
        preamble = (
            "SCRIPT_PATH = %s\nFACTIONS = %s\nCONTEXT = %s\nSCORES = %s\nTURNS = %s\n"
            "PRELOAD = %s\nDUMP_PATH = %s\nPROBE_PATH = %s\nPROBE_RUNGS = %s\n" % (
                _lua(script), _faction_table(factions), _lua(context),
                _lua(scores or {}), _lua(turns), _lua(preload or {}),
                _lua(dump), _lua(probe), _lua(probe_rungs) if probe_rungs else "nil"))
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
        rungs = []
        if probe_rungs and os.path.exists(probe):
            rungs = [int(x) for x in open(probe, encoding="utf-8").read().split()]
        return calls, state, rungs


def _selftest():
    # 1. rung_for maps ratios to rungs, with enough regions and no prior state.
    _, _, rungs = run_lua([{"name": "a", "regions": 20}, {"name": "b", "regions": 10}],
                          probe_rungs=[[1.0, 20, 0], [1.8, 20, 0], [2.6, 20, 0], [4.5, 20, 0]])
    assert rungs == [0, 1, 2, 3], rungs

    # 2. Hysteresis both ways: 1.5 holds an existing rung and never starts one.
    _, _, rungs = run_lua([{"name": "a", "regions": 20}, {"name": "b", "regions": 10}],
                          probe_rungs=[[1.5, 20, 0], [1.5, 20, 1], [1.2, 20, 1]])
    assert rungs == [0, 1, 0], rungs

    # 3. MIN_REGIONS gates a lopsided but tiny leader.
    _, _, rungs = run_lua([{"name": "a", "regions": 9}, {"name": "b", "regions": 1}],
                          probe_rungs=[[9.0, 9, 0]])
    assert rungs == [0], rungs
    print("selftest: rung logic ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        raise SystemExit("packing is added in Task 6")
```

- [x] **Step 2: Run it to verify it fails**

Run: `py tools/build_ai_coalitions.py --selftest`
Expected: FAIL — `lua failed: ...derpy_ai_coalitions.lua: No such file or directory` (the mod file does not exist yet).

**Amendment — ruling A8, made during Task 3.** The faction stub's `defensive_allies_with` was
static, so a pair allied by a `force_alliance` earlier in the same run still read as unallied —
the stub was more permissive than the engine, where that call makes the guard true from the next
turn. Give the stub a mutable `_allies` set seeded from the spec, have `defensive_allies_with`
read it, and have `cm:force_alliance` set it on both sides. Measured: against the old stub a
willing pair was forced **twice** over six turns; against the corrected stub, once. Assertion
`9b` pins it.

Also for the record: the RED step here surfaces as a Python `FileNotFoundError` rather than the
Lua error above, because `run_lua` reads the script file before shelling out to Lua. Same root
cause, still a correct failure.

- [x] **Step 3: Write the minimal implementation**

Create `Modding Files/pack/script/campaign/mod/derpy_ai_coalitions.lua`:

```lua
-- Coalition Supervisor. The campaign AI has no central brain to persuade, so this changes
-- inputs its existing departments already read: a runaway faction's strategic threat score,
-- and defensive alliances among factions that would already accept one.
-- Zero DB rows. See docs/superpowers/specs/2026-09-13-ai-coalition-supervisor-design.md

local ENABLED = true

local MIN_REGIONS = 10
local RUNG_RATIOS = {1.75, 2.5, 4.0}
local EXIT_RATIO = 1.35
local RUNG_SCORES = {200, 350, 500}
local POLL_PAIRS = 8
local MAX_FORCED_ALLIANCES = 2
local CLAIM_CONTEXT = true
local PAST_EVENT = "PAST_EVENT_NEGATIVE_MINOR"
local LOG_PREFIX = "[coalitions]"

local DEAL = "diplomatic_option_defensive_alliance"
local CONTEXT_KEY = "cai_global_script_context_special_1"
local CONTEXT_DEFAULT = "cai_global_script_context_type_default"

coalitions = {
	rung = 0,
	owns_context = false,
	scored_key = nil,
	alliances = {},
	cursor = 0,
}

local function log(msg)
	out(LOG_PREFIX .. " " .. msg)
end

-- Pure: no game calls, so the selftest can pin every boundary directly.
function coalitions:rung_for(ratio, leader_regions, current)
	if leader_regions < MIN_REGIONS then return 0 end
	if current > 0 and ratio < EXIT_RATIO then return 0 end
	local rung = 0
	for i = 1, #RUNG_RATIOS do
		if ratio >= RUNG_RATIOS[i] then rung = i end
	end
	if current > 0 and rung == 0 then return current end
	return rung
end

-- Region count, not strength: faction strength is no DB column and military_force_list
-- counts garrisons, so army-based measures overstate.
function coalitions:measure()
	local leader, best, second = nil, 0, 0
	for _, f in model_pairs(cm:model():world():faction_list()) do
		if not f:is_null_interface() and not f:is_dead() and not f:is_rebel() then
			local n = f:region_list():num_items()
			if n > best then
				leader, second, best = f, best, n
			elseif n > second then
				second = n
			end
		end
	end
	if not leader or second == 0 then return nil end
	return leader, best, second, best / second
end

function coalitions:tick()
	local leader, best, second, ratio = self:measure()
	if not leader then return end
	local rung = self:rung_for(ratio, best, self.rung)
	log(string.format("leader=%s regions=%d runner_up=%d ratio=%.2f rung=%d",
		leader:name(), best, second, ratio, rung))
	self.rung = rung
end

function coalitions:turn()
	if not ENABLED then return end
	local ok, err = pcall(function() self:tick() end)
	if not ok then log("error: " .. tostring(err)) end
end

core:add_listener(
	"derpy_coalitions_turn",
	"WorldStartRound",
	true,
	function() coalitions:turn() end,
	true
)
```

- [x] **Step 4: Run it to verify it passes**

Run: `py tools/build_ai_coalitions.py --selftest`
Expected: PASS — `selftest: rung logic ok`

- [x] **Step 5: Checkpoint**

Run all three static checks; each must exit 0:

```powershell
& "C:\Program Files (x86)\Lua\5.1\luac.exe" -p "Modding Files\pack\script\campaign\mod\derpy_ai_coalitions.lua"
py tools\check_lua_api.py "Modding Files\pack\script\campaign\mod\derpy_ai_coalitions.lua"
py tools\check_lua_undeclared.py "Modding Files\pack\script\campaign\mod\derpy_ai_coalitions.lua"
```

If `check_lua_undeclared.py` flags `out`, `core`, `cm` or `model_pairs`, they are engine globals — add them to that tool's allowlist rather than changing the mod.

---

### Task 2: The threat score, applied on change and released exactly once

**Files:**
- Modify: `Modding Files/pack/script/campaign/mod/derpy_ai_coalitions.lua`
- Modify: `tools/build_ai_coalitions.py`

**Interfaces:**
- Consumes: `coalitions:rung_for`, `coalitions:measure`, `coalitions:tick`, `run_lua`.
- Produces: `coalitions:apply_threat(leader, rung)`, and the state field `coalitions.scored_key` (a faction key string or nil) naming the faction currently carrying a scripted score.

- [x] **Step 1: Write the failing test**

Add to `_selftest()` in `tools/build_ai_coalitions.py`, before the final `print`:

```python
    # 4. The score lands on the leader, at the rung's value, once per change.
    big = [{"name": "runaway", "regions": 40}, {"name": "rival", "regions": 10},
           {"name": "third", "regions": 8}]
    calls, state, _ = run_lua(big, turns=3)
    scores = [c for c in calls if c[0] == "set_base_strategic_threat_score"]
    assert len(scores) == 1, scores                      # three turns, one write
    assert scores[0][1] == "runaway", scores
    assert scores[0][2] == "500.0" or scores[0][2] == "500", scores
    assert state["derpy_coalitions_scored_key"] == "runaway", state

    # 5. Falling back below EXIT_RATIO releases the score to 0, exactly once.
    calm = [{"name": "runaway", "regions": 11}, {"name": "rival", "regions": 10}]
    calls, _, _ = run_lua(calm, turns=3, preload={"derpy_coalitions_rung": 3,
                                                  "derpy_coalitions_scored_key": "runaway"})
    scores = [c for c in calls if c[0] == "set_base_strategic_threat_score"]
    assert len(scores) == 1, scores
    assert scores[0][1] == "runaway" and scores[0][2] in ("0", "0.0"), scores
    print("selftest: threat score ok")
```

- [x] **Step 2: Run it to verify it fails**

Run: `py tools/build_ai_coalitions.py --selftest`
Expected: FAIL — `assert len(scores) == 1, []` (nothing calls the threat score yet).

- [x] **Step 3: Write the minimal implementation**

In the Lua file, add `apply_threat` after `measure`, and replace `tick` with the version that calls it:

```lua
-- The threat score maps onto faction_strategic_threat_levels (0/100/200/350/500) and each
-- level applies wh_main_bundle_faction_imperium_level_N: -5/-10/-20/-30 attitude with
-- everyone. Reversible by writing 0, and visible on the diplomacy screen.
function coalitions:apply_threat(leader, rung)
	if rung > 0 then
		cm:set_base_strategic_threat_score(leader, RUNG_SCORES[rung])
		self.scored_key = leader:name()
		log("threat score " .. RUNG_SCORES[rung] .. " on " .. leader:name())
		return
	end
	if not self.scored_key then return end
	-- cm:get_faction returns false, not nil, for a key it does not know.
	local previous = cm:get_faction(self.scored_key)
	if previous and not previous:is_null_interface() then
		cm:set_base_strategic_threat_score(previous, 0)
		log("threat score released on " .. self.scored_key)
	end
	self.scored_key = nil
end

function coalitions:tick()
	local leader, best, second, ratio = self:measure()
	if not leader then return end
	local rung = self:rung_for(ratio, best, self.rung)
	log(string.format("leader=%s regions=%d runner_up=%d ratio=%.2f rung=%d",
		leader:name(), best, second, ratio, rung))
	if rung ~= self.rung or (rung > 0 and self.scored_key ~= leader:name()) then
		self:apply_threat(leader, rung)
	end
	self.rung = rung
end
```

Then add persistence at the end of the file, above the listener. The **loading** half lands
here too, not in Task 5: this task's release test restores a rung from a save, so without it
the test cannot express what it is testing. Task 5 extends both halves with the alliance
counts.

```lua
function coalitions:load(context)
	self.rung = cm:load_named_value("derpy_coalitions_rung", 0, context)
	self.owns_context = cm:load_named_value("derpy_coalitions_owns_context", false, context)
	self.cursor = cm:load_named_value("derpy_coalitions_cursor", 0, context)
	-- scored_key is read but deliberately NOT restored: leaving it nil is what makes the next
	-- tick write the threat score again, which is how engine state comes back after a load.
	local key = cm:load_named_value("derpy_coalitions_scored_key", "", context)
	self.scored_key = nil
	log(string.format("loaded rung=%s owns_context=%s cursor=%s prior_scored=%s",
		tostring(self.rung), tostring(self.owns_context), tostring(self.cursor),
		tostring(key)))
end

cm:add_loading_game_callback(function(context) coalitions:load(context) end)

cm:add_saving_game_callback(function(context)
	cm:save_named_value("derpy_coalitions_rung", coalitions.rung, context)
	cm:save_named_value("derpy_coalitions_owns_context", coalitions.owns_context, context)
	cm:save_named_value("derpy_coalitions_scored_key", coalitions.scored_key or "", context)
	cm:save_named_value("derpy_coalitions_cursor", coalitions.cursor, context)
end)
```

- [x] **Step 4: Run it to verify it passes**

Run: `py tools/build_ai_coalitions.py --selftest`
Expected: PASS — both `selftest: rung logic ok` and `selftest: threat score ok`.

Note: the harness records `SAVED` only after the saving callback runs, and the harness calls it at the end of the run, so `state` reflects the final turn.

**Amendment — ruling A6, made during Task 2's review.** `apply_threat`'s `rung > 0` branch
scores the new leader and reassigns `scored_key` to it without ever releasing the faction the
key previously named. A leads at rung 3 and carries 500; B later overtakes A while still
clearing a rung; the guard fires, B is scored, `scored_key` becomes B — and A keeps a -30
diplomatic penalty for the rest of the campaign with no path that ever revisits it. Spec §11
requires the release to happen exactly once, and nothing in the spec sanctions an orphan.

Extract the release so both branches use it, and release the previous carrier before scoring a
new one:

```lua
function coalitions:release_threat()
	if not self.scored_key then return end
	-- cm:get_faction returns false, not nil, for a key it does not know.
	local previous = cm:get_faction(self.scored_key)
	if previous and not previous:is_null_interface() then
		cm:set_base_strategic_threat_score(previous, 0)
		log("threat score released on " .. self.scored_key)
	end
	self.scored_key = nil
end

function coalitions:apply_threat(leader, rung)
	if rung > 0 then
		if self.scored_key and self.scored_key ~= leader:name() then
			self:release_threat()
		end
		cm:set_base_strategic_threat_score(leader, RUNG_SCORES[rung])
		self.scored_key = leader:name()
		log("threat score " .. RUNG_SCORES[rung] .. " on " .. leader:name())
		return
	end
	self:release_threat()
end
```

And the assertion for it — a swap is expressed as a load whose stored carrier is not the
current leader:

```python
    # 5c. A leader swap releases the previous carrier BEFORE scoring the new one.
    swap = [{"name": "new_leader", "regions": 40}, {"name": "old_runaway", "regions": 10}]
    calls, _, _ = run_lua(swap, turns=2, preload={"derpy_coalitions_rung": 3,
                                                  "derpy_coalitions_scored_key": "old_runaway"})
    writes = [(c[1], c[2]) for c in calls if c[0] == "set_base_strategic_threat_score"]
    assert any(w[0] == "old_runaway" and w[1] in ("0", "0.0") for w in writes), writes
    order = [w[0] for w in writes]
    assert order.index("old_runaway") < order.index("new_leader"), writes
```

**Amendment — ruling A4, made during Task 2.** The code above cannot both release correctly and
re-apply after a load, and the plan as first written chose wrong. Wiping `scored_key` in `load`
makes the next tick re-write the score, but it also destroys the only record of *which* faction
carries it — so a save taken at rung 3 and loaded into a calmed world releases the score on
whoever leads at that moment. If the old runaway was beaten while the save sat, it keeps its
-30 attitude forever and an innocent faction is zeroed instead.

Restore the key and make re-application explicit with a one-shot flag. In the `coalitions`
table initialiser add `loaded = false`. Then:

```lua
-- in coalitions:load, replacing the two scored_key lines
	-- Restore the key: it is the only record of which faction carries a scripted score, and a
	-- release must target that faction even if it is no longer the leader. Re-application
	-- after a load is handled by the one-shot `loaded` flag instead.
	local key = cm:load_named_value("derpy_coalitions_scored_key", "", context)
	self.scored_key = (key ~= "" and key) or nil
	self.loaded = true

-- in coalitions:apply_threat, the release branch keeps the strict guard
	if not self.scored_key then return end

-- in coalitions:tick, replacing the apply condition
	if self.loaded or rung ~= self.rung
			or (rung > 0 and self.scored_key ~= leader:name()) then
		self:apply_threat(leader, rung)
		self.loaded = false
	end
```

And add the assertion that the rejected fallback would have failed — the leader changed while
the save sat:

```python
    # 5b. A release targets the faction that CARRIES the score, not whoever leads now.
    moved = [{"name": "new_leader", "regions": 11}, {"name": "old_runaway", "regions": 10}]
    calls, _, _ = run_lua(moved, turns=2, preload={"derpy_coalitions_rung": 3,
                                                   "derpy_coalitions_scored_key": "old_runaway"})
    released = [c for c in calls if c[0] == "set_base_strategic_threat_score"
                and c[2] in ("0", "0.0")]
    assert released and released[0][1] == "old_runaway", calls
```

- [x] **Step 5: Checkpoint**

Re-run the three static checks from Task 1 Step 5. All must exit 0.

---

### Task 3: Coalition polling — ask both sides, force only mutual yes

**Files:**
- Modify: `Modding Files/pack/script/campaign/mod/derpy_ai_coalitions.lua`
- Modify: `tools/build_ai_coalitions.py`

**Interfaces:**
- Consumes: `coalitions:tick`, `coalitions.alliances`, `coalitions.cursor`, `run_lua`.
- Produces: `coalitions:candidates(leader)` returning a key-sorted array of faction interfaces, `coalitions:poll(leader)`, `coalitions:consider(a, b)` returning `true` when it forced an alliance.

- [x] **Step 1: Write the failing test**

Add to `_selftest()`:

```python
    # 6. Both directions are asked, and only a mutual yes is forced.
    world = [
        {"name": "runaway", "regions": 40},
        {"name": "ally_a", "regions": 10, "met": ["runaway", "ally_b", "loner"]},
        {"name": "ally_b", "regions": 9, "met": ["runaway", "ally_a", "loner"]},
        {"name": "loner", "regions": 8, "met": ["runaway", "ally_a", "ally_b"]},
    ]
    scores = {"ally_a|ally_b": 5, "ally_b|ally_a": 5,      # mutual yes
              "ally_a|loner": 5, "loner|ally_a": -1,       # one-sided
              "ally_b|loner": -1, "loner|ally_b": 5}
    calls, _, _ = run_lua(world, scores=scores, turns=1)
    asked = [(c[1], c[2]) for c in calls if c[0] == "cai_evaluate_quick_deal_action"]
    forced = [(c[1], c[2], c[3]) for c in calls if c[0] == "force_alliance"]
    assert ("ally_a", "ally_b") in asked and ("ally_b", "ally_a") in asked, asked
    assert forced == [("ally_a", "ally_b", "false")], forced   # defensive, and only the pair
    assert all(c[3] == "diplomatic_option_defensive_alliance"
               for c in calls if c[0] == "cai_evaluate_quick_deal_action"), calls

    # 7. Determinism: two identical runs produce the identical ordered call list.
    a, _, _ = run_lua(world, scores=scores, turns=2)
    b, _, _ = run_lua(world, scores=scores, turns=2)
    assert a == b, "call order is not deterministic"

    # 8. The per-faction cap holds across many turns.
    yes = {}
    names = ["f%d" % i for i in range(6)]
    web = [{"name": "runaway", "regions": 40}]
    for n in names:
        web.append({"name": n, "regions": 5, "met": ["runaway"] + [m for m in names if m != n]})
    for x in names:
        for y in names:
            if x != y:
                yes["%s|%s" % (x, y)] = 9
    calls, _, _ = run_lua(web, scores=yes, turns=12)
    per = {}
    for c in calls:
        if c[0] == "force_alliance":
            per[c[1]] = per.get(c[1], 0) + 1
            per[c[2]] = per.get(c[2], 0) + 1
    assert per and max(per.values()) <= 2, per

    # 9. An existing defensive alliance is never re-forced.
    paired = [{"name": "runaway", "regions": 40},
              {"name": "x", "regions": 10, "met": ["runaway", "y"], "allies": ["y"]},
              {"name": "y", "regions": 9, "met": ["runaway", "x"], "allies": ["x"]}]
    calls, _, _ = run_lua(paired, scores={"x|y": 9, "y|x": 9}, turns=2)
    assert not [c for c in calls if c[0] == "force_alliance"], calls
    print("selftest: coalition polling ok")
```

- [x] **Step 2: Run it to verify it fails**

Run: `py tools/build_ai_coalitions.py --selftest`
Expected: FAIL — `assert ("ally_a", "ally_b") in asked and ...` against an empty list.

- [x] **Step 3: Write the minimal implementation**

Add to the Lua file after `apply_threat`:

**Amendment — ruling A9, made during this task's review.** `candidates` must also skip
`f:is_human()`. See the spec's §7 for the reasoning; the one-line effect is the added
`and not f:is_human()` below, plus assertion `9c`.

```lua
function coalitions:candidates(leader)
	local out_list = {}
	for _, f in model_pairs(cm:model():world():faction_list()) do
		if not f:is_null_interface() and not f:is_dead() and not f:is_rebel()
				and not f:is_human()
				and f:name() ~= leader:name()
				and f:region_list():num_items() >= 2
				and (self.alliances[f:name()] or 0) < MAX_FORCED_ALLIANCES then
			for _, m in model_pairs(f:factions_met()) do
				if m:name() == leader:name() then
					out_list[#out_list + 1] = f
					break
				end
			end
		end
	end
	-- Sorted, never raw pairs(): undefined order diverges across reloads and MP clients.
	table.sort(out_list, function(x, y) return x:name() < y:name() end)
	return out_list
end

function coalitions:consider(a, b)
	if a:defensive_allies_with(b) or a:military_allies_with(b) then return false end
	local met = false
	for _, m in model_pairs(a:factions_met()) do
		if m:name() == b:name() then met = true break end
	end
	if not met then return false end
	-- Asking is the whole point: the AI would accept these, it just never proposes them.
	local score_a, ok_a = cm:cai_evaluate_quick_deal_action(a, b, DEAL)
	local score_b, ok_b = cm:cai_evaluate_quick_deal_action(b, a, DEAL)
	log(string.format("ask %s<->%s %s/%s", a:name(), b:name(),
		tostring(score_a), tostring(score_b)))
	if not (ok_a and ok_b and score_a and score_b) then return false end
	if score_a <= 0 or score_b <= 0 then return false end
	cm:force_alliance(a:name(), b:name(), false)
	self.alliances[a:name()] = (self.alliances[a:name()] or 0) + 1
	self.alliances[b:name()] = (self.alliances[b:name()] or 0) + 1
	log("forced defensive alliance " .. a:name() .. " + " .. b:name())
	return true
end

function coalitions:poll(leader)
	local cands = self:candidates(leader)
	local list_of_pairs = {}
	for i = 1, #cands do
		for j = i + 1, #cands do
			list_of_pairs[#list_of_pairs + 1] = {cands[i], cands[j]}
		end
	end
	if #list_of_pairs == 0 then return end
	-- ponytail: the cursor indexes a list that changes as factions die, so rotation is
	-- approximate rather than exact. Good enough to spread polling; revisit only if the log
	-- shows the same pairs re-asked forever.
	local idx = self.cursor
	local budget = POLL_PAIRS
	if budget > #list_of_pairs then budget = #list_of_pairs end
	for _ = 1, budget do
		idx = (idx % #list_of_pairs) + 1
		local pair = list_of_pairs[idx]
		if (self.alliances[pair[1]:name()] or 0) < MAX_FORCED_ALLIANCES
				and (self.alliances[pair[2]:name()] or 0) < MAX_FORCED_ALLIANCES then
			self:consider(pair[1], pair[2])
		end
	end
	self.cursor = idx
end
```

Then extend `tick` to poll while the state holds. **Do not paste an apply condition here** —
rulings A4 and A6 changed it during Task 2, and retyping the older form would silently revert
them. Leave the existing `if self.loaded or rung ~= self.rung or ...` block exactly as it
stands, and insert ONE line between it and the final `self.rung = rung`:

```lua
	if rung > 0 then self:poll(leader) end
```

- [x] **Step 4: Run it to verify it passes**

Run: `py tools/build_ai_coalitions.py --selftest`
Expected: PASS — three `selftest: ... ok` lines.

- [x] **Step 5: Checkpoint**

Re-run the three static checks. All must exit 0.

---

### Task 4: The global context slot, and the past-event probe

**Files:**
- Modify: `Modding Files/pack/script/campaign/mod/derpy_ai_coalitions.lua`
- Modify: `tools/build_ai_coalitions.py`

**Interfaces:**
- Consumes: `coalitions:tick`, `coalitions.owns_context`, `run_lua`.
- Produces: `coalitions:claim_context(want)` where `want` is a boolean.

- [x] **Step 1: Write the failing test**

Add to `_selftest()`:

```python
    # 10. A free slot is claimed once; an occupied slot is left alone and never cleared.
    big = [{"name": "runaway", "regions": 40}, {"name": "rival", "regions": 10}]
    calls, state, _ = run_lua(big, turns=3)
    sets = [c for c in calls if c[0] == "cai_set_global_script_context"]
    assert len(sets) == 1 and sets[0][1] == "cai_global_script_context_special_1", sets
    assert state["derpy_coalitions_owns_context"] == "true", state

    calls, state, _ = run_lua(big, turns=3, context="cai_global_script_context_special_2")
    assert not [c for c in calls if c[0] == "cai_set_global_script_context"], calls
    assert not [c for c in calls if c[0] == "cai_clear_global_script_context"], calls
    assert state["derpy_coalitions_owns_context"] == "false", state

    # 11. Releasing clears only a slot we own.
    calm = [{"name": "runaway", "regions": 11}, {"name": "rival", "regions": 10}]
    calls, _, _ = run_lua(calm, turns=2, context="cai_global_script_context_special_1",
                          preload={"derpy_coalitions_rung": 3,
                                   "derpy_coalitions_owns_context": True,
                                   "derpy_coalitions_scored_key": "runaway"})
    assert len([c for c in calls if c[0] == "cai_clear_global_script_context"]) == 1, calls

    calls, _, _ = run_lua(calm, turns=2, context="cai_global_script_context_special_1",
                          preload={"derpy_coalitions_rung": 3,
                                   "derpy_coalitions_owns_context": False,
                                   "derpy_coalitions_scored_key": "runaway"})
    assert not [c for c in calls if c[0] == "cai_clear_global_script_context"], calls

    # 12. The past event fires with its argument order logged, leader first.
    world = [{"name": "runaway", "regions": 40},
             {"name": "ally_a", "regions": 10, "met": ["runaway", "ally_b"]},
             {"name": "ally_b", "regions": 9, "met": ["runaway", "ally_a"]}]
    calls, _, _ = run_lua(world, turns=1)
    events = [c for c in calls if c[0] == "cai_add_diplomatic_event"]
    assert events, "no past event raised"
    assert all(e[1] == "runaway" for e in events), events
    assert all(e[3] == "PAST_EVENT_NEGATIVE_MINOR" for e in events), events
    assert [c for c in calls if c[0] == "out" and "from=runaway" in c[1]], "direction not logged"
    print("selftest: context slot and past event ok")
```

- [x] **Step 2: Run it to verify it fails**

Run: `py tools/build_ai_coalitions.py --selftest`
Expected: FAIL — `assert len(sets) == 1 and ...` against an empty list.

- [x] **Step 3: Write the minimal implementation**

Add to the Lua file after `poll`:

```lua
-- One global slot exists game-wide. CA's "AI extra aggro" campaign option uses special_1
-- too, so read before writing and clear only what we set. Worth about 6% on two numbers -
-- cheap, and the only place another mod can collide with this file.
function coalitions:claim_context(want)
	if not CLAIM_CONTEXT then return end
	if want then
		if self.owns_context then return end
		local current = cm:cai_get_global_script_context()
		if current == nil or current == "" or current == CONTEXT_DEFAULT then
			cm:cai_set_global_script_context(CONTEXT_KEY)
			self.owns_context = true
			log("claimed the global context slot")
		else
			log("global context slot already held by " .. tostring(current) .. ", skipping")
		end
	elseif self.owns_context then
		cm:cai_clear_global_script_context()
		self.owns_context = false
		log("released the global context slot")
	end
end
```

Add the past event inside `consider`, immediately after the `met` guard and before the two
evaluate calls:

```lua
	-- CA's own three uses leave (from, to) ambiguous, so log the order we passed and let the
	-- first soak settle it. from = the leader's key, supplied by poll().
	if self.leader_key then
		log(string.format("past_event from=%s to=%s %s", self.leader_key, a:name(), PAST_EVENT))
		cm:cai_add_diplomatic_event(self.leader_key, a:name(), PAST_EVENT)
	end
```

In `poll`, set the field the event reads, as its first line:

```lua
	self.leader_key = leader:name()
```

And extend `tick`, replacing `if rung > 0 then self:poll(leader) end`:

```lua
	self:claim_context(rung > 0)
	if rung > 0 then self:poll(leader) end
```

- [x] **Step 4: Run it to verify it passes**

Run: `py tools/build_ai_coalitions.py --selftest`
Expected: PASS — four `selftest: ... ok` lines.

- [x] **Step 5: Checkpoint**

Re-run the three static checks. All must exit 0.

---

### Task 5: Persistence, and re-applying engine state on load

**Files:**
- Modify: `Modding Files/pack/script/campaign/mod/derpy_ai_coalitions.lua`
- Modify: `tools/build_ai_coalitions.py`

**Interfaces:**
- Consumes: the saving callback from Task 2, `coalitions.alliances`, `run_lua(preload=...)`.
- Produces: `coalitions:load(context)` and the fifth saved value `derpy_coalitions_alliances`.

**Deviation from the spec, deliberate:** spec §9 lists four saved values; this ships **five**. `derpy_coalitions_scored_key` is needed so a release can zero the score on the faction that actually carries it, which may no longer be the leader. The spec's §9 table should be read as four plus that one.

- [x] **Step 1: Write the failing test**

Add to `_selftest()`:

```python
    # 13. Loaded state is honoured: a saved cap is not spent twice.
    names = ["f0", "f1", "f2"]
    web = [{"name": "runaway", "regions": 40}]
    for n in names:
        web.append({"name": n, "regions": 5, "met": ["runaway"] + [m for m in names if m != n]})
    yes = {}
    for x in names:
        for y in names:
            if x != y:
                yes["%s|%s" % (x, y)] = 9
    calls, _, _ = run_lua(web, scores=yes, turns=4,
                          preload={"derpy_coalitions_alliances": {"f0": 2, "f1": 2, "f2": 2}})
    assert not [c for c in calls if c[0] == "force_alliance"], calls

    # 14. A rung restored from a save re-applies the engine state it implies.
    big = [{"name": "runaway", "regions": 40}, {"name": "rival", "regions": 10}]
    calls, _, _ = run_lua(big, turns=1, context=CONTEXT_DEFAULT_KEY,
                          preload={"derpy_coalitions_rung": 3,
                                   "derpy_coalitions_scored_key": "runaway",
                                   "derpy_coalitions_owns_context": False})
    assert [c for c in calls if c[0] == "set_base_strategic_threat_score"
            and c[1] == "runaway" and c[2] in ("500", "500.0")], calls
    print("selftest: persistence ok")
```

Add this module-level constant near the top of `tools/build_ai_coalitions.py`, under `LUAC`:

```python
CONTEXT_DEFAULT_KEY = "cai_global_script_context_type_default"
```

- [x] **Step 2: Run it to verify it fails**

Run: `py tools/build_ai_coalitions.py --selftest`
Expected: FAIL — `assert not [c for c in calls if c[0] == "force_alliance"]` lists forced alliances, because the saved caps are ignored.

- [x] **Step 3: Write the minimal implementation**

Task 2 already created `coalitions:load` and registered the loading callback. **Extend** both
halves rather than re-adding them — one line in `load`, one in the saving callback.

In `coalitions:load`, after the `self.cursor` line:

```lua
	self.alliances = cm:load_named_value("derpy_coalitions_alliances", {}, context)
```

In the saving callback, alongside the other four:

```lua
	cm:save_named_value("derpy_coalitions_alliances", coalitions.alliances, context)
```

That is the whole change. `coalitions:load` also restores `scored_key` and sets the one-shot
`loaded` flag (ruling A4 in Task 2) — leave both alone. If `coalitions:load` is missing, Task 2
was not completed as written —
stop and report `BLOCKED` rather than re-creating it here, because a second registration of the
loading callback would run the load twice.

The re-application in Task 2's `tick` already fires, because its condition is
`rung ~= self.rung or (rung > 0 and self.scored_key ~= leader:name())` and `scored_key` is nil
after a load.

- [x] **Step 4: Run it to verify it passes**

Run: `py tools/build_ai_coalitions.py --selftest`
Expected: PASS — five `selftest: ... ok` lines.

- [x] **Step 5: Checkpoint**

Re-run the three static checks. All must exit 0.

---

### Task 6: The off switch, the no-loc guarantee, and packing

**Files:**
- Modify: `tools/build_ai_coalitions.py`
- Modify: `docs/superpowers/plans/2026-09-13-ai-coalition-supervisor.md` (tick the boxes as you go)
- Modify: `docs/SESSION_INDEX.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: everything above.
- Produces: `pack()`, and `derpy_ai_coalitions.pack` in `Modding Files/Modpacks/`.

- [x] **Step 1: Write the failing test**

Add to `_selftest()`, then replace the `__main__` block:

```python
    # 15. Disabled makes ZERO calls - not calls that clear.
    big = [{"name": "runaway", "regions": 40}, {"name": "rival", "regions": 10}]
    calls, _, _ = run_lua(big, turns=5, disable=True)
    assert calls == [], calls

    # 16. Nothing in the shipped file resolves loc from the turn handler.
    src = open(SCRIPT, encoding="utf-8").read()
    for banned in ("effect.get_localised_string", "common.get_localised_string",
                   "get_localised_string"):
        assert banned not in src, "loc call in a turn handler CTDs at turn 1: %s" % banned

    # 17. luac, the API check and the undeclared-global check all pass.
    for cmd in ([LUAC, "-p", SCRIPT],
                [sys.executable, os.path.join(ROOT, "tools", "check_lua_api.py"), SCRIPT],
                [sys.executable, os.path.join(ROOT, "tools", "check_lua_undeclared.py"), SCRIPT]):
        r = subprocess.run(cmd, capture_output=True, text=True)
        assert r.returncode == 0, "%s failed:\n%s" % (cmd[0], r.stdout + r.stderr)
    print("selftest: off switch, no-loc and static checks ok")
```

```python
if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        pack()
```

- [x] **Step 2: Run it to verify it fails**

Run: `py tools/build_ai_coalitions.py --selftest`
Expected: FAIL — `NameError: name 'pack' is not defined` at import of the `__main__` block, or, if you added the tests only, the off-switch assertion passes and the run stops at the missing `pack`.

- [x] **Step 3: Write the minimal implementation**

Add `pack()` above `_selftest()` in `tools/build_ai_coalitions.py`. It reuses the workspace's
RPFM-over-HTTP helpers — the same `_rpc` / `_call` pair `fetch_vanilla_tables.py` and
`import_victory_routes.py` use — rather than a second client:

```python
PACK = os.path.join(ROOT, "Modding Files", "Modpacks", "derpy_ai_coalitions.pack")
IN_PACK = "script/campaign/mod/derpy_ai_coalitions.lua"

sys.path.insert(0, os.path.join(ROOT, "tools"))


def pack():
    """Create or refresh derpy_ai_coalitions.pack. Needs RPFM open.

    The RPFM MCP server only exists while RPFM is running; a connection refusal means RPFM is
    shut, and there is no fallback - never hand-edit a .pack.
    """
    import datetime
    import shutil
    from check_skill_trees import _rpc, _call

    _selftest()

    _rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                        "clientInfo": {"name": "build_ai_coalitions", "version": "1"}})
    _rpc("notifications/initialized", notify=True)
    # rebuild_dependencies=False binds the schema without the 105MB rebuild; this pack has no
    # DB rows, so nothing here needs the dependency cache.
    _call("set_game_selected", {"game_name": "warhammer_3", "rebuild_dependencies": False})

    if os.path.exists(PACK):
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(PACK, "%s.bak_%s" % (PACK, stamp))
        print("backed up the existing pack")
        key = _call("open_packfiles", {"paths": [PACK]})["StringContainerInfo"][0]
    else:
        created = _call("new_pack", {})
        # new_pack's return shape is not documented; accept either and fail loudly otherwise.
        if isinstance(created, dict):
            key = created.get("StringContainerInfo", [None])[0] or created.get("pack_key")
        else:
            key = created
        assert isinstance(key, str) and key, "new_pack returned %r" % (created,)
        _call("set_pack_file_type", {"pack_key": key, "pack_file_type": '"Mod"'})

    _call("add_packed_files", {"pack_key": key, "source_paths": [SCRIPT],
                               "destination_paths": json.dumps([{"File": IN_PACK}])})
    _call("save_pack_as", {"pack_key": key, "path": PACK})
    print("saved %s (%dB of Lua)" % (PACK, os.path.getsize(SCRIPT)))

    # A file that is merely present proves nothing. Re-open the SAVED pack and read it back.
    again = _call("open_packfiles", {"paths": [PACK]})["StringContainerInfo"][0]
    # get_packed_files_info takes `values`: a list of PLAIN STRINGS, not a JSON ContainerPath
    # array. It is the one call in this function that does not follow the ContainerPath
    # convention - checked against the live tool schema, not inferred from its neighbours.
    info = _call("get_packed_files_info", {"pack_key": again, "values": [IN_PACK]})
    assert IN_PACK in json.dumps(info), "%s is not in the saved pack: %s" % (IN_PACK, info)
    print("verified: %s is in the saved pack" % IN_PACK)
```

`set_pack_file_type` takes the enum as a **JSON string**, so the value really is `'"Mod"'` with
both sets of quotes — that is RPFM's API, not a typo.

- [x] **Step 4: Run it to verify it passes**

Run: `py tools/build_ai_coalitions.py --selftest`
Expected: PASS — six `selftest: ... ok` lines.

Then, with RPFM open, run `py tools/build_ai_coalitions.py` and carry out the five printed
steps through the RPFM MCP tools. Verify step 5 by re-opening the saved pack in a fresh MCP
session and reading the file back: a file that is merely present proves nothing about whether
it still decodes.

- [x] **Step 5: Checkpoint and document**

1. Copy the built pack to the game: `F:\SteamLibrary\steamapps\common\Total War WARHAMMER III\data\derpy_ai_coalitions.pack`. **A new pack in `data/` starts unticked** — enable it in the launcher and confirm it appears in `used_mods.txt` before concluding it did nothing.
2. Append one line to `docs/SESSION_INDEX.md` pointing at the handoff that covers this work (`HANDOFF_20260913_AI_GAPS_AND_COALITIONS.md`), noting that §5's design is now built.
3. Add one `tools/` entry to `CLAUDE.md` in the established style: `build_ai_coalitions.py` (the Coalition Supervisor — one Lua file, zero DB rows; `--selftest` runs the shipped Lua under Lua 5.1.5 against a stubbed campaign and asserts on the recorded call list, and no flag packs it after the selftest passes).
4. First campaign run: play 10-15 turns with the log open and check the `[coalitions]` lines for the rung entering at the right ratio, both scores on each ask, and the `past_event from=` direction. That direction is the one thing offline testing cannot settle.

---

## Notes for the executor

- **The tests run the artefact.** If an assertion fails, fix the Lua, not the harness — unless the harness is genuinely missing a stub, in which case add the stub and say so in the checkpoint.
- **`run_lua(disable=True)` flips the real constant** in a copy of the shipped file and asserts the replacement matched exactly once. If you rename or reformat `local ENABLED = true`, that test breaks loudly rather than silently passing.
- **Thresholds are guesses**, every one of them. They live in one block at the top of the Lua file for exactly that reason, and the spec §13 records that the workspace has no autorun harness to tune them against.
