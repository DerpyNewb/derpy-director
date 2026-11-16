# -*- coding: utf-8 -*-
"""The Director's Chronicle, drawn and tested with the game shut.

    py tools/preview_director.py              # .skilltree_cache/ui_preview/dr_chronicle.png
    py tools/preview_director.py --selftest   # the UI script's behaviour, scene by scene

WHAT IS REAL. derpy_director_chronicle.lua runs under Lua 5.1 against fake components built from
the four .twui.xml files gen_director_ui.py writes; its own DC.show opens the panel, and what it
left on screen is read back: every position, every line of text, every hidden part. The list box
stacks its rows as the engine's List layout does. The art is CA's, through TWUI Studio's
rasteriser, as preview_exchange.py draws the Exchange.

WHAT IS APPROXIMATE. Glyphs are Segoe UI, not the game's font. TextDimensionsForText answers with
Segoe UI's own widths, so the Lua wraps against the same font this draws with and a line that
measures too wide here is a real fault in the wrap; in game the font is CA's and lines break a
word or two differently.

THE DEMO IS THE HARDEST CASE THE MODEL CAN WRITE: 100 entries, every kind, every consequence at
once, the longest faction and region names on the map, and a key with no loc at all.
"""
import io
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_director_ui as U                                          # noqa: E402
import preview_guilds_panel as PG                                    # noqa: E402

LUA = U.LUA
LUA_EXE = r"C:\Program Files (x86)\Lua\5.1\lua.exe"
FILES = {"panel": "derpy_director_panel.twui.xml", "list": "derpy_director_list.twui.xml",
         "line": "derpy_director_line.twui.xml", "button": "derpy_director_button.twui.xml",
         "rule": "derpy_director_rule.twui.xml"}
SCREEN = (1600, 900)
FONT = "C:/Windows/Fonts/segoeui.ttf"
FEED_LOC = os.path.join(ROOT, "Modding Files", "source", "director_feed",
                        "loc__derpy_director_feed.tsv")

# The hardest names CA ships (read_vanilla_loc, 2026-11-15): the longest faction and region screen
# names, and the longest culture names. NOLOC has no loc at all and must read as its key.
F = ["wh_main_grn_necksnappers_waaagh", "wh2_dlc11_cst_rogue_terrors_of_the_dark_straights",
     "wh2_dlc11_cst_rogue_boyz_of_the_forbidden_coast",
     "wh2_dlc11_cst_rogue_tyrants_of_the_black_ocean",
     "wh2_dlc11_cst_pirates_of_sartosa_separatists"]
R = ["wh3_main_combi_region_monolith_of_borkill_the_bloody_handed",
     "wh3_main_combi_region_northern_straits_of_the_great_ocean"]
SC = ["wh_main_sc_chs_chaos", "wh3_main_sc_dae_daemons"]
NOLOC = "derpy_no_such_faction"
# CA's [[col:]] colours this panel uses, as db/ui_colours_tables defines them; the selftest checks
# the table still says so.
INK = dict(PG.INK, ui_font_faded_grey_beige=(0xA9, 0x9F, 0x89, 255))


def _loc():
    """Every string the scenes can look up: the Chronicle's rows, the temperament records, and the
    real names of the demo keys."""
    from read_vanilla_loc import load
    out = {U.LOC_PREFIX + k: v for k, v in U.CHRONICLE_LOC.items()}
    for line in io.open(FEED_LOC, encoding="utf-8").read().splitlines()[2:]:
        k, v = line.split("\t")[:2]
        # The Chronicle's own rows come from the generator, never from a TSV an older build wrote.
        if not k.startswith(U.LOC_PREFIX):
            out[k] = v
    fac, reg, cul = load("factions"), load("regions"), load("cultures_subcultures")
    for k in F:
        out["factions_screen_name_" + k] = fac["factions_screen_name_" + k]
    for k in R:
        out["regions_onscreen_" + k] = reg["regions_onscreen_" + k]
    for k in SC:
        out["cultures_subcultures_name_" + k] = cul["cultures_subcultures_name_" + k]
    # Short names for the sentence scene, as a player would read them.
    out.update({"factions_screen_name_mors": "Clan Mors", "factions_screen_name_azul": "Karak Azul",
                "factions_screen_name_hirn": "Karak Hirn", "factions_screen_name_zhuf": "Zhufbar",
                "regions_onscreen_r_azul": "Karak Azul",
                "factions_screen_name_waaagh": "Grimgor's Waaagh!"})
    return out


def _hard_chronicle():
    """100 entries, oldest first: every kind in turn, each carrying every consequence it can."""
    a, b, c, d, e = F
    kinds = [
        {"k": "sack", "i": a, "v": b, "r": R[0], "c": [c, d, e], "p": [[c, d, 12500], [c, e]], "g": c,
         "m": [d, b, "runaway"]},
        {"k": "raze", "i": a, "v": b, "r": R[1], "c": [c, d, e], "g": c, "pl": True},
        {"k": "conquest", "i": a, "v": b, "r": R[0], "c": [c, d, e], "p": [[c, d]], "u": 12,
         "m": [c, b, "last_stand"]},
        {"k": "confederation", "i": a, "v": NOLOC, "r": "", "c": [c, d]},
        {"k": "treachery", "i": a, "v": b, "r": R[1], "c": [c, d, e], "g": d},
        {"k": "opportunism", "i": b, "v": a, "r": R[0], "c": [c, d, e]},
        {"k": "seizure", "i": a, "v": b, "r": R[1], "c": [c]},
        {"k": "secession", "i": a, "v": b, "r": R[0], "c": [c, d]},
        {"k": "runaway_rise", "i": a, "n": 3},
        {"k": "runaway_pact", "i": a, "p": [[c, d]]},
        {"k": "runaway_end", "i": a},
        {"k": "war", "i": c, "v": a, "w": "seizure", "r": R[1], "x": b},
        {"k": "war", "i": d, "v": a, "w": "confederation", "r": "", "x": NOLOC},
        {"k": "war", "i": e, "v": a, "w": "runaway"},
        {"k": "empire", "i": a, "n": 1},
        {"k": "empire_goal", "i": a, "n": 100, "g": 1},
        {"k": "empire_goal", "i": b, "n": 100, "g": 2},
        {"k": "empire_merge", "i": a, "v": b},
        {"k": "empire_peace", "i": a, "v": b},
        {"k": "empire_fade", "i": b},
    ]
    out = []
    for n in range(1, 101):
        out.append(dict(kinds[(n - 1) % len(kinds)], t=1 + (n - 1) // 3))
    return out


# Short fixtures with the sentence each must read as, word for word.
SENTENCES = [
    ({"t": 34, "k": "sack", "i": "mors", "v": "azul", "r": "r_azul", "c": ["hirn", "zhuf"],
      "p": [["hirn", "zhuf"]], "g": "hirn", "u": 4},
     "Clan Mors sacked Karak Azul, a settlement of Karak Azul. "
     "Karak Hirn and Zhufbar turned against Clan Mors. "
     "Karak Hirn and Zhufbar signed a defensive alliance against Clan Mors. "
     "Karak Hirn will not forget it. Rebels rose in Karak Azul."),
    ({"t": 36, "k": "war", "i": "hirn", "v": "mors", "w": "sack", "r": "r_azul", "x": "azul"},
     "Karak Hirn declared war on Clan Mors over the sack of "
     "Karak Azul."),
    ({"t": 37, "k": "war", "i": "zhuf", "v": "mors", "w": "treachery", "r": "r_azul",
      "x": "azul"},
     "Zhufbar declared war on Clan Mors, which had broken its "
     "treaty with Karak Azul."),
    ({"t": 38, "k": "war", "i": "zhuf", "v": "mors", "w": "runaway"},
     "Zhufbar declared war on Clan Mors, fearing its power."),
    ({"t": 39, "k": "war", "i": "zhuf", "v": "mors", "w": "no_such_cause"}, "nil"),
    # A name that ends in its own mark takes no full stop after it.
    ({"t": 44, "k": "runaway_rise", "i": "waaagh", "n": 1},
     "The world began to fear Grimgor's Waaagh!"),
    ({"t": 40, "k": "conquest", "i": "mors", "v": "azul", "r": "r_azul", "c": [],
      "m": ["hirn", "azul", "last_stand"]},
     "Clan Mors took Karak Azul from Karak Azul. "
     "Close to defeat, Karak Azul joined Karak Hirn in a confederation."),
    ({"t": 41, "k": "runaway_rise", "i": "mors", "n": 2},
     "Fear of Clan Mors spread across the world."),
    ({"t": 42, "k": "runaway_pact", "i": "mors", "p": [["hirn", "zhuf"]]},
     "Karak Hirn and Zhufbar allied against Clan Mors."),
    ({"t": 43, "k": "nothing_known", "i": "mors"}, "nil"),
    # A pact the Director funded says what each side was given.
    ({"t": 45, "k": "sack", "i": "mors", "v": "azul", "r": "r_azul", "c": ["hirn", "zhuf"],
      "p": [["hirn", "zhuf", 1250]]},
     "Clan Mors sacked Karak Azul, a settlement of Karak Azul. "
     "Karak Hirn and Zhufbar turned against Clan Mors. "
     "Karak Hirn and Zhufbar signed a defensive alliance against Clan Mors and raised 1250 gold "
     "each for the war."),
    # The empires (2026-11-15, phase 4).
    ({"t": 1, "k": "empire", "i": "mors", "n": 1}, "Clan Mors set out to become a great power."),
    ({"t": 1, "k": "empire", "i": "hirn", "n": 2}, "Karak Hirn set out to build an empire."),
    # Not "{i}'s": a possessive on a faction's name reads "Straits's" and "Waaagh!'s".
    ({"t": 30, "k": "empire_fade", "i": "waaagh"},
     "The ambitions of Grimgor's Waaagh! came to nothing."),
    ({"t": 50, "k": "empire_goal", "i": "mors", "n": 50, "g": 1},
     "Clan Mors now rules 50 settlements, a great power the world cannot ignore."),
    ({"t": 60, "k": "empire_goal", "i": "hirn", "n": 25, "g": 2},
     "Karak Hirn now rules 25 settlements, an empire in its own right."),
    ({"t": 33, "k": "empire_merge", "i": "mors", "v": "azul"},
     "Karak Azul joined Clan Mors in a confederation."),
    ({"t": 34, "k": "empire_peace", "i": "mors", "v": "hirn"},
     "Clan Mors made peace with Karak Hirn to turn its armies elsewhere."),
]


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
        return "{" + ", ".join("[%s] = %s" % (_lua(k), _lua(x)) for k, x in sorted(v.items())) + "}"
    raise TypeError(type(v))


def _widths():
    """Segoe UI 12's advance per byte, for TextDimensionsForText. A byte above 127 is half of a
    two-byte character."""
    from PIL import ImageFont
    f = ImageFont.truetype(FONT, 12)
    return {i: round(f.getlength(chr(i)), 2) for i in range(32, 127)}


def _tree(fname):
    t = io.open(os.path.join(PG.OURS, fname), encoding="utf-8").read()
    h = t[t.index("<hierarchy>"):t.index("</hierarchy>")]
    stack, top = [], None
    for m in re.finditer(r"<(/?)([A-Za-z0-9_]+)[^>]*?(/?)>", h):
        close, tag, selfc = m.groups()
        if tag == "hierarchy":
            continue
        if close:
            stack.pop()
            continue
        node = [tag, []]
        if stack:
            stack[-1][1].append(node)
        else:
            top = node
        if not selfc:
            stack.append(node)
    return top[1][0]


def _lua_tree(n):
    return '{"%s",{%s}}' % (n[0], ",".join(_lua_tree(k) for k in n[1]))


def _docs():
    model, _r = PG._studio()
    out = {}
    for f in FILES.values():
        d = model.Document(io.open(os.path.join(PG.OURS, f), encoding="utf-8").read())
        for c in d.components:
            out.setdefault(c.get("id", c.tag), (d, c, d.state(c)))
    return out


DRIVER = r"""
local TREES = @@TREES@@
local CW = @@CW@@
local LOC = @@LOC@@
local SAVED = @@SAVED@@
local WRITES = {}
-- What the first tick may and may not do: a loc lookup there crashes a fresh campaign on turn 1, and
-- a model timer started from UI-only code can differ between multiplayer machines.
local LOC_CALLS, MODEL_TIMERS, REAL_TIMERS = 0, 0, 0
cm = setmetatable({
    add_first_tick_callback = function() end,
    callback = function() MODEL_TIMERS = MODEL_TIMERS + 1 end,
    real_callback = function() REAL_TIMERS = REAL_TIMERS + 1 end,
    repeat_real_callback = function() end,
    get_saved_value = function(_, k) return SAVED[k] end,
    set_saved_value = function(_, k) WRITES[#WRITES + 1] = k end,
}, {__index = function(_, k) return function() WRITES[#WRITES + 1] = "cm:" .. k end end})
common = {get_localised_string = function(k) LOC_CALLS = LOC_CALLS + 1 return LOC[k] or "" end}
function out() end
local ROOT
core = {add_listener = function() end, get_ui_root = function() return ROOT end,
        get_screen_resolution = function() return @@SW@@, @@SH@@ end, event_listeners = {}}
events = {}

local build
local function comp(name, parent, node)
    node = node or name
    local c = {name = name, xid = node, x = 0, y = 0, vis = true, kids = {}, order = {},
               parent = parent, text = ""}
    c.MoveTo = function(_, x, y)
        local dx, dy = x - c.x, y - c.y
        local function shift(k) k.x, k.y = k.x + dx, k.y + dy for _, g in ipairs(k.order) do shift(g) end end
        shift(c)
    end
    c.Position = function() return c.x, c.y end
    c.Dimensions = function() return c.w or (TREES.size[node] or {100})[1], c.h or (TREES.size[node] or {0, 20})[2] end
    c.Resize = function(_, w, h) c.w, c.h = w, h end
    c.SetVisible = function(_, v) c.vis = v and true or false end
    c.Visible = function() return c.vis end
    c.SetInteractive = function(_, v) c.inter = v end
    c.SetText = function(_, t) c.text = t end
    c.SetTextXOffset = function(_, l) c.txo = l end
    c.SetTooltipText = function(_, t) c.tip = t end
    c.Id = function() return c.name end
    c.Parent = function() return c.parent end
    c.Destroy = function()
        local p = c.parent
        if p then
            p.kids[c.name] = nil
            for i, k in ipairs(p.order) do if k == c then table.remove(p.order, i) break end end
        end
        c.dead = true
    end
    c.TextDimensionsForText = function(_, s)
        local w = 0
        for i = 1, #s do
            local b = string.byte(s, i)
            w = w + (CW[b] or 3.5)
        end
        return w, 16, 1
    end
    -- THE LIST LAYOUT: list_box stacks its children top to bottom, each its own height.
    c.Layout = function()
        local y = c.y
        for _, k in ipairs(c.order) do
            k:MoveTo(c.x, y)
            local _, h = k:Dimensions()
            y = y + h
        end
    end
    c.CreateComponent = function(_, n, file)
        if c.kids[n] then return end
        local which = (string.find(file, "director_panel", 1, true) and "panel")
            or (string.find(file, "director_list", 1, true) and "list")
            or (string.find(file, "director_line", 1, true) and "line")
            or (string.find(file, "director_button", 1, true) and "button")
            or (string.find(file, "director_rule", 1, true) and "rule")
        local k = comp(n, c, which and TREES[which][1] or n)
        if which then for _, sub in ipairs(TREES[which][2]) do build(sub, k) end end
    end
    if parent then parent.kids[name] = c; parent.order[#parent.order + 1] = c end
    return c
end
build = function(node, parent)
    local c = comp(node[1], parent)
    for _, sub in ipairs(node[2]) do build(sub, c) end
end
ROOT = comp("root")
function find_uicomponent(from, name)
    if not from then return false end
    if from.name == name then return from end
    for _, k in ipairs(from.order or {}) do
        local hit = find_uicomponent(k, name)
        if hit then return hit end
    end
    return false
end
function is_uicomponent(c) return type(c) == "table" and c.MoveTo ~= nil end
function UIComponent(c) return c end

dofile([[@@LUA@@]])
local function ok(tag, f, ...)
    local args = {...}
    local good, err = xpcall(function() return f(unpack(args)) end, debug.traceback)
    if not good then print("ERR\t" .. tag .. "\t" .. string.gsub(tostring(err), "[\t\n]+", " | ")) end
end
local function rows()
    local box = find_uicomponent(ROOT, "list_box")
    return box and #box.order or -1
end
@@SCENE@@
local function shown(c)
    while c do if not c.vis then return false end c = c.parent end
    return true
end
local function esc(s) return (string.gsub(tostring(s or ""), "[\t\n]", " ")) end
local function emit(c, depth, clip)
    if not shown(c) then return end
    local w, h = c:Dimensions()
    print(table.concat({"C", depth, c.xid, c.name, c.x, c.y, w, h, esc(c.text), tostring(c.txo or ""),
        c.parent and c.parent.name or "", clip or ""}, "\t"))
    if c.name == "list_clip" then
        local cw, ch = c:Dimensions()
        clip = table.concat({c.x, c.y, cw, ch}, ",")
    end
    for _, k in ipairs(c.order) do emit(k, depth + 1, clip) end
end
for _, k in ipairs(ROOT.order) do emit(k, 0) end
print("WRITES\t" .. table.concat(WRITES, ","))
"""

SCENES = {
    # The hardest chronicle the model can write, under the longest header.
    "hard": ("hard", 'ok("open", DC.show, true)'),
    # Opened, closed, opened: the list is rebuilt, never doubled.
    "reopen": ("hard", 'ok("open", DC.show, true) print("ROWS\\t" .. rows()) '
                       'ok("close", DC.show, false) ok("open2", DC.show, true) '
                       'print("ROWS\\t" .. rows())'),
    # The first tick's path, DC.init, with no resource bar to anchor to yet, so the button retries.
    "init": ("hard", 'ok("init", DC.init) print("S\\tinit\\t" .. LOC_CALLS .. "," .. MODEL_TIMERS '
                     '.. "," .. REAL_TIMERS)'),
    # A save from before the Chronicle: no chronicle, the old news buffer, no seed.
    "empty": ("old", 'ok("open", DC.show, true)'),
    # More ambitious factions than the header's lines hold, so its last line ends in " ...".
    "crowded": ("crowded", 'ok("open", DC.show, true)'),
    # Every fixture through DC.sentence, word for word, and a turn's heading.
    "sentences": ("hard", "for i, e in ipairs(SENTENCE_ENTRIES) do "
                          'print("S\\t" .. i .. "\\t" .. tostring(DC.sentence(e))) end '
                          'print("S\\t0\\t" .. tostring(DC.turn_label(34)))'),
}


def _saved(which):
    if which == "old":
        return {"derpy_director_news": [[1, "sack", "a", "b", "r", 2]]}
    return {"derpy_director_chronicle": _hard_chronicle(),
            "derpy_director_seed": {"temperament": "rising", "phase": 2, "hot": SC,
                                    # crowded: found by search, the list whose second line is
                                    # fullest (416 of 424px) with a third still to come
                                    "ambitious": [F[0]] * 5 if which == "crowded"
                                    else [F[0], F[1], F[2]]}}


def snapshot(scene):
    """(components, sentences, row counts, cm writes, errors) for one scene."""
    docs = _docs()
    size = ",".join('["%s"]={%s,%s}' % (k, st.get("width"), st.get("height"))
                    for k, (_d, _c, st) in docs.items() if st is not None)
    trees = "{%s,size={%s}}" % (",".join("%s=%s" % (k, _lua_tree(_tree(f)))
                                         for k, f in FILES.items()), size)
    saved, body = SCENES[scene]
    scene_lua = "SENTENCE_ENTRIES = %s\n%s" % (_lua([e for e, _s in SENTENCES]), body)
    src = (DRIVER.replace("@@TREES@@", trees).replace("@@CW@@", _lua(_widths()))
           .replace("@@LOC@@", _lua(_loc())).replace("@@SAVED@@", _lua(_saved(saved)))
           .replace("@@SW@@", str(SCREEN[0])).replace("@@SH@@", str(SCREEN[1]))
           .replace("@@LUA@@", LUA).replace("@@SCENE@@", scene_lua))
    fd, tmp = tempfile.mkstemp(suffix=".lua")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(src)
    try:
        run = subprocess.run([LUA_EXE, tmp], capture_output=True, text=True, encoding="utf-8")
    finally:
        os.remove(tmp)
    if run.returncode:
        raise SystemExit("scene %s: lua failed:\n%s" % (scene, run.stderr))
    comps, sents, counts, writes, errs = [], {}, [], [], []
    for line in run.stdout.splitlines():
        f = line.split("\t")
        if f[0] == "C":
            comps.append(dict(depth=int(f[1]), xid=f[2], name=f[3], x=float(f[4]), y=float(f[5]),
                              w=float(f[6]), h=float(f[7]), text=f[8],
                              txo=float(f[9]) if f[9] else None, parent=f[10],
                              clip=tuple(float(v) for v in f[11].split(",")) if f[11] else None))
        elif f[0] == "S":
            sents[int(f[1]) if f[1].isdigit() else f[1]] = f[2]
        elif f[0] == "ROWS":
            counts.append(int(f[1]))
        elif f[0] == "WRITES":
            writes = [w for w in f[1].split(",") if w]
        elif f[0] == "ERR":
            errs.append("%s: %s" % (f[1], f[2]))
    return comps, sents, counts, writes, errs


def _bare(s):
    return PG.MARKUP.sub("", s)


def line_faults(comps):
    """Every list line wider than the room its cell gives it, measured with the font drawn."""
    from PIL import ImageFont
    f = ImageFont.truetype(FONT, 12)
    S = U.STYLE
    out = []
    for c in comps:
        if c["name"].startswith("derpy_director_line_") and c["text"]:
            room = S["line_w"] - (c["txo"] if c["txo"] is not None else S["inset"])
            need = f.getlength(_bare(c["text"]))
            if need > room + 2:
                out.append("%s is %.0fpx in %dpx: %r" % (c["name"], need, room, c["text"][:60]))
    return out


def selftest():
    fails = []
    comps, _s, _c, writes, errs = snapshot("hard")
    fails += ["hard: " + e for e in errs]
    fails += ["hard: wrote %s" % w for w in writes]
    S = U.STYLE
    rows = [c for c in comps if c["parent"] == "list_box"]
    lines = [c for c in rows if c["name"].startswith("derpy_director_line_")]
    if not lines:
        fails.append("hard: no list lines drawn")
    head = "[[col:%s]]" % S["accent"]
    heads = [k for k, c in enumerate(rows) if c["text"].startswith(head)]
    turns = [_bare(rows[k]["text"]) for k in heads]
    # One heading a turn, newest first: 34 turns of three entries (the newest has one).
    if turns != ["Turn %d" % t for t in range(34, 0, -1)]:
        fails.append("hard: the turn headings read %r" % turns[:4])
    if heads and heads[0] != 0:
        fails.append("hard: the list does not open on its newest turn's heading")
    # A rule above every heading but the first, and nowhere else.
    rules = [k for k, c in enumerate(rows) if c["name"].startswith("derpy_director_rule_")]
    if rules != [k - 1 for k in heads[1:]]:
        fails.append("hard: rules at %r, headings at %r" % (rules[:4], heads[:4]))
    # No entry carries its turn any more; a heading is not indented; a continuation is.
    for c in lines:
        if c["text"].startswith(head) and _bare(c["text"]) not in turns:
            fails.append("hard: an entry still carries its turn: %r" % c["text"][:40])
    for k in heads:
        if rows[k]["txo"] is not None:
            fails.append("hard: the heading %r is indented" % _bare(rows[k]["text"]))
            break
    conts = [c for c in lines if c["txo"] is not None]
    if not conts or any(c["txo"] != S["inset"] + S["indent"] for c in conts):
        fails.append("hard: %d continuation lines, not all indented by %d"
                     % (len(conts), S["inset"] + S["indent"]))
    fails += ["hard: " + x for x in line_faults(comps)]
    # Rows stack: each starts where the one above it ended, rules included.
    for a, b in zip(rows, rows[1:]):
        if abs(b["y"] - (a["y"] + a["h"])) > 0.5:
            fails.append("hard: %s does not follow %s" % (b["name"], a["name"]))
            break
    text = {c["name"]: c["text"] for c in comps}
    for want in ("hdr_text_1_1", "hdr_text_2_1", "hdr_text_3_1", "title_text"):
        if not text.get(want):
            fails.append("hard: %s is empty" % want)
    if "Warriors of Chaos and Daemons of Chaos" != text.get("hdr_text_2_1"):
        fails.append("hard: the old hatred reads %r" % text.get("hdr_text_2_1"))
    # The game ignores a runtime text cell's font_m_colour (measured 2026-11-15: labels drawn
    # gold here came out cream); the description is faded by CA's markup colour instead.
    faded = "[[col:%s]]" % U.STYLE["muted"]
    for n in ("hdr_text_1_2", "hdr_text_1_3", "hdr_text_1_4"):
        if not (text.get(n) or "").startswith(faded) or not text[n].endswith("[[/col]]"):
            fails.append("hard: %s is not wrapped in %s: %r" % (n, faded, text.get(n)))
    if text.get("hdr_text_1_1", "").startswith("[[col:"):
        fails.append("hard: the temperament's name is faded with its description")
    if not any(c["name"] == "vslider" for c in comps):
        fails.append("hard: 100 entries and no slider")
    _c2, _s2, counts, _w2, errs = snapshot("reopen")
    fails += ["reopen: " + e for e in errs]
    if len(counts) != 2 or counts[0] != counts[1] or counts[0] <= 0:
        fails.append("reopen: rows %r, not the same count twice" % counts)
    # A value longer than its header lines ends in " ...", and that line still fits WITH it on
    # (the final review: it used to be added after the line was measured).
    from PIL import ImageFont
    comps, _s, _c, _w, errs = snapshot("crowded")
    fails += ["crowded: " + e for e in errs]
    last = {c["name"]: c["text"] for c in comps}.get("hdr_text_3_%d" % U.HEADER_LINES[3]) or ""
    need = ImageFont.truetype(FONT, 12).getlength(_bare(last))
    if not last.endswith(" ...") or need > S["value_w"] - S["inset"] + 2:
        fails.append("crowded: the header's last line is %.0fpx in %dpx: %r"
                     % (need, S["value_w"] - S["inset"], last[-50:]))
    comps, _s, _c, writes, errs = snapshot("empty")
    fails += ["empty: " + e for e in errs] + ["empty: wrote %s" % w for w in writes]
    lines = [c for c in comps if c["name"].startswith("derpy_director_line_")]
    if [c["text"] for c in lines] != [U.CHRONICLE_LOC["empty"]]:
        fails.append("empty: the list reads %r" % [c["text"] for c in lines])
    if any(c["name"] == "vslider" for c in comps):
        fails.append("empty: a slider over one line")
    # The first tick: no loc lookup (the turn-1 crash), no model timer, and the button's retry
    # scheduled on the real, UI-synchronised timer.
    _c, sents, _n, _w, errs = snapshot("init")
    fails += ["init: " + e for e in errs]
    loc_calls, model_timers, real_timers = (int(n) for n in sents.get("init", "-1,-1,-1").split(","))
    if loc_calls != 0:
        fails.append("init: the first tick looked up %d loc strings" % loc_calls)
    if model_timers != 0 or real_timers < 1:
        fails.append("init: the button's retry used %d model and %d real timers"
                     % (model_timers, real_timers))
    _c, sents, _n, _w, errs = snapshot("sentences")
    fails += ["sentences: " + e for e in errs]
    for i, (_e, want) in enumerate(SENTENCES, 1):
        if sents.get(i) != want:
            fails.append("sentence %d reads %r, not %r" % (i, sents.get(i), want))
    if sents.get(0) != "[[col:%s]]Turn 34[[/col]]" % U.STYLE["accent"]:
        fails.append("the turn heading reads %r" % sents.get(0))
    try:
        import read_vanilla_cache as V
        table = {r["blue"]: r["description"].upper() for r in V.load("ui_colours")[0]}
    except (ImportError, FileNotFoundError, IndexError, ValueError):
        table = {}
    for name in (U.STYLE["muted"], U.STYLE["accent"]):
        if table and table.get(name) != "%02X%02X%02X" % INK[name][:3]:
            fails.append("ui_colours calls %s %s; the preview draws it otherwise" % (name, table.get(name)))
    for f in fails:
        print("FAIL", f)
    print("selftest %s: %d scenes" % ("ok" if not fails else "FAILED", len(SCENES)))
    return not fails


def _rgba(hexs, default=(255, 248, 215, 255)):
    if not hexs or not hexs.startswith("#"):
        return default
    h = hexs[1:]
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4, 6)) if len(h) == 8 else default


def _lum(rgb):
    def ch(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(rgb[0]) + 0.7152 * ch(rgb[1]) + 0.0722 * ch(rgb[2])


def render(path=None):
    """Draw the hard scene; returns (png path, contrast faults, width faults)."""
    from PIL import Image, ImageDraw, ImageFont
    from pathlib import Path
    model, rendering = PG._studio()
    docs = _docs()
    comps, _s, _c, _w, errs = snapshot("hard")
    if errs:
        raise SystemExit("\n".join(errs))
    PG.extract_art("derpy_director_")
    canvas = Image.new("RGBA", SCREEN, (14, 12, 10, 255))
    T = {"img": canvas}
    font = ImageFont.truetype(FONT, 12)
    fonts = {}
    low = []

    def art(p):
        return Path(os.path.join(PG.UI, os.path.relpath(p, "ui").replace("/", os.sep)))

    def images(c):
        d, comp, st = docs.get(c["xid"], (None, None, None))
        if st is None or st.child("imagemetrics") is None:
            return
        pics = {n.get("this"): n.get("imagepath") for n in comp.child("componentimages").children} \
            if comp.child("componentimages") is not None else {}
        xw, xh = float(st.get("width")), float(st.get("height"))
        for n in st.child("imagemetrics").children:
            a = art(pics.get(n.get("componentimage"), ""))
            if not a.is_file():
                continue
            iw, ih = float(n.get("width") or xw), float(n.get("height") or xh)
            iw = c["w"] if abs(iw - xw) < 1 else iw
            ih = c["h"] if abs(ih - xh) < 1 else ih
            if n.get("dockpoint") == "Center":
                ox, oy = (c["w"] - iw) / 2, (c["h"] - ih) / 2
            else:
                ox, oy = model.pair(n.get("offset"), (0, 0))
            img = rendering.raster(a, max(1, int(iw)), max(1, int(ih)), n)
            T["img"].alpha_composite(img, (int(c["x"] + ox), int(c["y"] + oy)))

    def text(c):
        if not c["text"]:
            return
        d, comp, st = docs.get(c["xid"], (None, None, None))
        ct = st.child("component_text") if st is not None else None
        if ct is None:
            return
        size = int(float(ct.get("font_m_size") or 12))
        if size not in fonts:
            fonts[size] = ImageFont.truetype(FONT, size)
        f = fonts[size]
        base = _rgba(ct.get("font_m_colour"))
        x = c["x"] + (c["txo"] if c["txo"] is not None else model.pair(ct.get("textxoffset"), (0, 0))[0])
        y = c["y"] + (c["h"] - size) / 2 - 3
        # THE GROUND UNDER THE CELL, before the text goes on: its brightest 5% against the ink.
        box = T["img"].crop((int(c["x"]), int(c["y"]), int(c["x"] + c["w"]), int(c["y"] + c["h"])))
        px = sorted(_lum(p) for p in box.convert("RGB").getdata())
        ground = px[int(len(px) * 0.95)] if px else 0
        draw = ImageDraw.Draw(T["img"])
        pos, colour = 0, base
        t = c["text"]
        for m in PG.MARKUP.finditer(t):
            seg = t[pos:m.start()]
            draw.text((x, y), seg, fill=colour, font=f)
            x += draw.textlength(seg, font=f)
            colour = base if m.group(1) else INK.get(m.group(2), base)
            pos = m.end()
            for ink in (colour,):
                ratio = (max(_lum(ink), ground) + 0.05) / (min(_lum(ink), ground) + 0.05)
                if ratio < 4.5:
                    low.append("%s %.1f:1 %r" % (c["name"], ratio, _bare(t)[:30]))
        draw.text((x, y), t[pos:], fill=colour, font=f)
        ratio = (max(_lum(base), ground) + 0.05) / (min(_lum(base), ground) + 0.05)
        if ratio < 4.5:
            low.append("%s %.1f:1 %r" % (c["name"], ratio, _bare(t)[:30]))

    clip_now = None
    for c in comps:
        if c["clip"] != clip_now:
            if clip_now is not None:
                cx, cy, cw, ch = (int(v) for v in clip_now)
                canvas.alpha_composite(T["img"].crop((cx, cy, cx + cw, cy + ch)), (cx, cy))
            clip_now = c["clip"]
            T["img"] = canvas if clip_now is None else Image.new("RGBA", SCREEN, (0, 0, 0, 0))
            if clip_now is not None:
                T["img"].alpha_composite(canvas)
        images(c)
        text(c)
    if clip_now is not None:
        cx, cy, cw, ch = (int(v) for v in clip_now)
        canvas.alpha_composite(T["img"].crop((cx, cy, cx + cw, cy + ch)), (cx, cy))
    ImageDraw.Draw(canvas).text((16, SCREEN[1] - 24), "The World Chronicle, the hardest case: 100 "
                                "entries, the longest names. Drawn offline by tools/preview_director.py "
                                "from the shipped Lua; glyphs approximate.", fill=(150, 140, 120, 255),
                                font=font)
    out = path or os.path.join(PG.CACHE, "dr_chronicle.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    canvas.convert("RGB").save(out)
    return out, low, line_faults(comps)


def main(argv):
    unknown = [a for a in argv if a not in ("--selftest",)]
    if unknown:
        print("unknown argument(s): %s" % " ".join(unknown))
        return 2
    if "--selftest" in argv:
        return 0 if selftest() else 1
    out, low, wide = render()
    print(out)
    for x in low:
        print("  LOW CONTRAST", x)
    for x in wide:
        print("  TOO WIDE", x)
    return 1 if (low or wide) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
