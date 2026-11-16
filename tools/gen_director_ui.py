"""The Director's Chronicle panel: the five .twui.xml files derpy_director_chronicle.lua creates at
runtime, written to Modding Files/pack/ui/campaign ui/.

    py tools/gen_director_ui.py              # write the five files
    py tools/gen_director_ui.py --check      # write nothing; exit 1 if a file on disk differs
    py tools/gen_director_ui.py --selftest   # scroll parts, GUIDs, CA art, sounds, STYLE vs the Lua

THE FILES. derpy_director_panel (the frame, title, header and close button), derpy_director_list
(the scrolling list, created into the panel and rebuilt on every open so it opens at the top),
derpy_director_line (one line of text, created into list_box once per line),
derpy_director_rule (the line between one turn and the next, also a list_box row) and
derpy_director_button (the HUD opener). GUID prefixes DR01-DR05 (docs/CUSTOM_UI.md).

TWUI TEXT NEVER WRAPS, so an entry is several derpy_director_line components, broken in the Lua
with TextDimensionsForText; the list box stacks them (docs/CUSTOM_UI.md, "Which way to fill it":
text rows straight into list_box, confirmed on the Great Guilds' faction list).

POSITIONS ARE THE LUA'S. A runtime-created component ignores dockpoint, so these files carry sizes
only and DC.LAYOUT in the Lua MoveTo's every part. The list's size is fixed here (the header has a
fixed number of lines) so the slider's travel is right as generated.

THE EMITTER is the Great Guilds' (gen_guilds_emitter), as the Exchange's and the Iron Court's lists
use it, with CA's own slider (gen_guilds_ui.ca_vslider). The art constants are COPIED, not imported
from gen_exchange_ui: a fix to that mod's look must not change this one's.
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_guilds_emitter as EU                                    # noqa: E402

OUT = os.path.join(ROOT, "Modding Files", "pack", "ui", "campaign ui")
LUA = os.path.join(ROOT, "Modding Files", "pack", "script", "campaign", "mod",
                   "derpy_director_chronicle.lua")

# EVERY SIZE AND COLOUR, once. DC.STYLE in the Lua carries the same values and --selftest compares
# them, because a size typed into a cell drifts from the rest.
STYLE = {
    "panel_w": 640, "panel_h": 730,
    # The list: 26 lines of 20 under a fixed header. line_w leaves the slider's 18 and a 6px gap.
    "list_x": 20, "list_y": 218, "list_rows": 25, "line_w": 576, "line_h": 20,
    # The row between two turns, with its 1px line across the middle.
    "rule_h": 17,
    # A continuation line's hang under the turn, and the text's own inset in its cell.
    "indent": 18, "inset": 6,
    # The header's value column, which the Lua wraps the temperament and the ambitious against.
    "value_w": 430,
    "handle_h": 40,
    # Colours. The game ignores a runtime text cell's font_m_colour (measured 2026-11-15: labels
    # set gold drew cream), so every cell is CA's body cream and anything else is [[col:]] markup:
    # muted is CA's faded font colour, which the Lua wraps the temperament's description in.
    "text": "#FFF8D7FF", "muted": "ui_font_faded_grey_beige",
    "title_font": "header_24_bold", "label_font": "header_14", "body_font": "body_12",
    # The [[col:]] name the turn is drawn in: one of ui_colours_tables' names, as the Guilds use it.
    "accent": "yellow",
}
# Header slots: row -> how many value lines. Row 1 is the temperament (its name and three lines of
# what it means), row 2 the old hatred, row 3 the three ambitious factions.
HEADER_LINES = {1: 4, 2: 1, 3: 2}
LABEL_W, VALUE_W, HEADER_LINE_H = 150, STYLE["value_w"], 18
TITLE_W, TITLE_H = 560, 34

# CA's two-layer panel, as the Exchange draws it (copied from gen_exchange_ui.PANEL_LAYERS).
PANEL_LAYERS = [
    {"path": "ui/skins/default/panel_back_tile.png",
     "offset": (0, 0), "dw": 0, "dh": 0, "margin": 5, "tile": True, "dock": None},
    {"path": "ui/skins/default/panel_back_border.png",
     "offset": (0, 0), "dw": 0, "dh": 0, "margin": 30, "tile": True, "dock": None},
]
CLOSE_LAYERS = [
    {"path": "ui/skins/default/button_round_small_active.png",
     "offset": (0, 0), "dw": 0, "dh": 0, "margin": 0, "dock": None},
    {"path": "ui/skins/default/icon_cross_small.png",
     "offset": (5, 5), "dw": -10, "dh": -10, "margin": 0, "dock": "Center"},
]
CLOSE_HOVER = [
    {"path": "ui/skins/default/button_round_small_hover.png",
     "offset": (0, 0), "dw": 0, "dh": 0, "margin": 0, "dock": None},
    {"path": "ui/skins/default/icon_cross_small.png",
     "offset": (5, 5), "dw": -10, "dh": -10, "margin": 0, "dock": "Center"},
]
# The opener: CA's round medium button with its records scroll, a glyph no race owns.
ICON = "ui/skins/default/icon_records.png"
OPENER_LAYERS = [
    {"path": "ui/skins/default/button_round_medium_underlay.png",
     "offset": (0, 0), "dw": 0, "dh": 0, "margin": 0, "dock": None},
    {"path": "ui/skins/default/button_round_medium_active.png",
     "offset": (0, 0), "dw": 0, "dh": 0, "margin": 0, "dock": None},
    {"path": ICON, "offset": (9, 9), "dw": -18, "dh": -18, "margin": 0, "dock": "Center"},
]
OPENER_HOVER = [
    {"path": "ui/skins/default/button_round_medium_underlay.png",
     "offset": (0, 0), "dw": 0, "dh": 0, "margin": 0, "dock": None},
    {"path": "ui/skins/default/button_round_medium_hover.png",
     "offset": (0, 0), "dw": 0, "dh": 0, "margin": 0, "dock": None},
    {"path": ICON, "offset": (9, 9), "dw": -18, "dh": -18, "margin": 0, "dock": "Center"},
]
# A hairline under the header: a white pixel tinted the muted parchment at half alpha.
DIVIDER = "ui/skins/default/1x1_blank_white.png"
DIVIDER_COLOUR = "#C8B48C80"
SND_OPEN = "UI_GBL_TMP_Round_Medium_Button"
SND_CLOSE = "UI_GBL_TMP_Round_Small_Button"
# Literal tooltips, as the Exchange's are. The opener's too: the Lua places it from the first tick,
# and a loc lookup there crashes a fresh campaign on turn 1 (the final review, 2026-11-15).
TIP_CLOSE = "Close"
TIP_OPEN = ("The World Chronicle||What the powers of this world have done this campaign, and who "
            "answered them.")

PREFIX = {"derpy_director_panel": "DR01", "derpy_director_list": "DR02",
          "derpy_director_line": "DR03", "derpy_director_button": "DR04",
          "derpy_director_rule": "DR05"}

# THE CHRONICLE'S TEXT, under derpy_director_chronicle_<name> in the Director's loc file
# (build_director.write_feed_tsvs appends these). {i} is the instigator, {v} the victim, {r} the
# region, {a}/{b} a pair, {g} the grudge holder, {list} the factions that answered, {t} the turn.
# Opportunism's instigator is the faction that LOST ground and its victim the one that took most;
# a secession's instigator is the realm. A last stand's {a} took {b} in. A war's {i} declared it
# on {v}, the cause's instigator; {r} and {x} are the cause's region and victim.
LOC_PREFIX = "derpy_director_chronicle_"
CHRONICLE_LOC = {
    "title": "The World Chronicle",
    "label_temper": "This World",
    "label_hatred": "An Old Hatred",
    "label_ambitious": "The Ambitious",
    "unknown": "Not yet known",
    "none": "None",
    "empty": "Nothing worth recording has happened yet.",
    "turn": "Turn {t}",
    "list_two": "{a} and {b}",
    "deed_sack": "{i} sacked {r}, a settlement of {v}.",
    "deed_raze": "{i} razed {r}, a settlement of {v}.",
    "deed_conquest": "{i} took {r} from {v}.",
    "deed_confederation": "{i} took {v} into a confederation.",
    "deed_treachery": "{i} broke its treaty with {v}.",
    "deed_opportunism": "{i} lost ground to {v}, and old enemies saw their chance.",
    "deed_seizure": "{i} seized a convoy belonging to {v}.",
    "deed_secession": "{r} broke away from {i}.",
    "answered": "{list} turned against {i}.",
    "pact": "{a} and {b} signed a defensive alliance against {i}.",
    "pact_chest": "{a} and {b} signed a defensive alliance against {i} and raised {n} gold each for the war.",
    "grudge": "{g} will not forget it.",
    "rebels": "Rebels rose in {r}.",
    "plague": "Plague broke out in the ruins of {r}.",
    "merge_last_stand": "Close to defeat, {b} joined {a} in a confederation.",
    "merge_runaway": "{b} joined {a} in a confederation to stand against {i}.",
    "rise_1": "The world began to fear {i}.",
    "rise_2": "Fear of {i} spread across the world.",
    "rise_3": "{i} became the terror of the world.",
    "runaway_end": "{i} is no longer feared above all others.",
    "runaway_pact": "{a} and {b} allied against {i}.",
    "war_sack": "{i} declared war on {v} over the sack of {r}.",
    "war_raze": "{i} declared war on {v} over the razing of {r}.",
    "war_conquest": "{i} declared war on {v} over the fall of {r}.",
    "war_confederation": "{i} declared war on {v}, which had taken {x} into a confederation.",
    "war_treachery": "{i} declared war on {v}, which had broken its treaty with {x}.",
    "war_opportunism": "{i} declared war on {v}, seeing it weakened.",
    "war_seizure": "{i} declared war on {v}, which had seized a convoy belonging to {x}.",
    "war_secession": "{i} declared war on {v} after {r} broke away from it.",
    "war_runaway": "{i} declared war on {v}, fearing its power.",
    "empire_great": "{i} set out to become a great power.",
    "empire_lesser": "{i} set out to build an empire.",
    "empire_fade": "The ambitions of {i} came to nothing.",
    "empire_goal_great": "{i} now rules {n} settlements, a great power the world cannot ignore.",
    "empire_goal_lesser": "{i} now rules {n} settlements, an empire in its own right.",
    "empire_merge": "{v} joined {i} in a confederation.",
    "empire_peace": "{i} made peace with {v} to turn its armies elsewhere.",
}
MODEL = os.path.join(ROOT, "Modding Files", "pack", "script", "campaign", "mod", "derpy_director.lua")


def check_loc():
    """The UI script's loc names against CHRONICLE_LOC, both ways, and every kind of entry the
    model writes against a sentence. A name with no row draws an empty line in game; a kind with no
    sentence is an entry the panel silently skips."""
    out = []
    if not os.path.isfile(LUA):
        return ["derpy_director_chronicle.lua does not exist"]
    src = io.open(LUA, encoding="utf-8").read()
    model = io.open(MODEL, encoding="utf-8").read()
    used = set(re.findall(r'DC\.loc\("([a-z_0-9]+)"\)', src))
    used |= set(re.findall(r'\badd\("([a-z_0-9]+)"', src))
    for block in ("DEED", "RISE", "MERGE", "WAR"):
        m = re.search(r"DC\.%s = \{(.*?)\}" % block, src, re.S)
        if not m:
            out.append("DC.%s is not declared" % block)
            continue
        used |= set(re.findall(r'"([a-z_0-9]+)"', m.group(1)))
    for n in sorted(used - set(CHRONICLE_LOC)):
        out.append("the Chronicle uses %s%s, which has no loc row" % (LOC_PREFIX, n))
    for n in sorted(set(CHRONICLE_LOC) - used):
        out.append("CHRONICLE_LOC carries %s, which nothing uses" % n)
    deed = re.search(r"DC\.DEED = \{(.*?)\}", src, re.S)
    deeds = set(re.findall(r"(\w+) = \"", deed.group(1))) if deed else set()
    for k in sorted(set(re.findall(r'kind = "(\w+)"', model)) - deeds):
        out.append("the model writes %s stories and DC.DEED has no sentence for them" % k)
    for k in sorted(set(re.findall(r'\bk = "(\w+)"', model))):
        if 'e.k == "%s"' % k not in src:
            out.append("the model writes %s entries and DC.sentence has no case for them" % k)
    # A war's cause is a story's kind or a literal the model names.
    war = re.search(r"DC\.WAR = \{(.*?)\}", src, re.S)
    wars = set(re.findall(r"(\w+) = \"", war.group(1))) if war else set()
    causes = set(re.findall(r'kind = "(\w+)"', model)) | set(re.findall(r'\bw = "(\w+)"', model))
    for k in sorted(causes - wars):
        out.append("the model blames wars on %s and DC.WAR has no sentence for it" % k)
    return out


def list_h():
    return STYLE["list_rows"] * STYLE["line_h"]


def _text(name, w, h, size, colour, font, align="Left"):
    return EU.C(name, w, h, text=True, size=size, colour=colour, fontcat=font, align=align,
                valign="Center", tx="%d.00,0.00" % STYLE["inset"], ty="0.00,0.00", leading=0)


def build_panel():
    S = STYLE
    root = EU.C("root", S["panel_w"], S["panel_h"])
    p = root.add(EU.C("derpy_director_panel", S["panel_w"], S["panel_h"], layers=PANEL_LAYERS,
                      priority=60))
    p.add(_text("title_text", TITLE_W, TITLE_H, 24, S["text"], S["title_font"]))
    for r, n in sorted(HEADER_LINES.items()):
        p.add(_text("hdr_label_%d" % r, LABEL_W, HEADER_LINE_H, 14, S["text"], S["label_font"]))
        for line in range(1, n + 1):
            p.add(_text("hdr_text_%d_%d" % (r, line), VALUE_W, HEADER_LINE_H, 12, S["text"],
                        S["body_font"]))
    p.add(EU.C("divider", S["panel_w"] - 2 * S["list_x"], 2, image=DIVIDER,
               colour_img=DIVIDER_COLOUR))
    p.add(EU.C("close_button", 30, 30, interactive=True, layers=CLOSE_LAYERS, hover=CLOSE_HOVER,
               sound=SND_CLOSE, tooltip=TIP_CLOSE))
    return root


def build_list():
    import gen_guilds_ui as GG
    S = STYLE
    h, w = list_h(), S["line_w"] + GG.CA_SLIDER["w"] + 6
    root = EU.C("root", w, h)
    lst = root.add(EU.C("listview", w, h, interactive=True, callbacks=["Listview"]))
    clip = lst.add(EU.C("list_clip", S["line_w"], h, clipchildren=True, relativeresize=True,
                        interactive=True))
    clip.add(EU.C("list_box", S["line_w"], 1, interactive=True, callbacks=["List"],
                  docking="Top Left",
                  layoutengine={"type": "List", "sizetocontent": True,
                                "margins": "0.00,0.00", "columns": [S["line_w"]]}))
    # CA's event-message slider; its track stops a cap short of each end, as the Guilds' does.
    lst.add(GG.ca_vslider(h - 2 * GG.CA_SLIDER["cap"], S["handle_h"]))
    return root


def build_line():
    S = STYLE
    root = EU.C("root", S["line_w"], S["line_h"])
    root.add(_text("derpy_director_line", S["line_w"], S["line_h"], 12, S["text"], S["body_font"]))
    return root


def build_rule():
    """A list row as tall as the gap between two turns, drawing the header divider's tinted pixel as
    a 1px line across its middle. An image layer of the row itself, so the List layout that stacks
    the rows places the line with it; a child would need a MoveTo of its own."""
    S = STYLE
    root = EU.C("root", S["line_w"], S["rule_h"])
    root.add(EU.C("derpy_director_rule", S["line_w"], S["rule_h"],
                  layers=[{"path": DIVIDER, "offset": (0, S["rule_h"] // 2), "dw": 0,
                           "dh": 1 - S["rule_h"], "margin": 0, "colour": DIVIDER_COLOUR,
                           "dock": None}]))
    return root


def build_button():
    root = EU.C("root", 48, 48)
    root.add(EU.C("derpy_director_button", 48, 48, interactive=True, sound=SND_OPEN,
                  tooltip=TIP_OPEN, layers=OPENER_LAYERS, hover=OPENER_HOVER))
    return root


FILES = [
    ("derpy_director_panel", build_panel, "the Chronicle's frame, title, header and close button"),
    ("derpy_director_list", build_list, "the Chronicle's scrolling list, rebuilt on every open"),
    ("derpy_director_line", build_line, "one line of a Chronicle entry"),
    ("derpy_director_rule", build_rule, "the line between two turns in the Chronicle's list"),
    ("derpy_director_button", build_button, "the Chronicle's HUD opener"),
]


def build():
    """{file name: xml text}."""
    out = {}
    for name, fn, what in FILES:
        root = EU.assign(fn(), PREFIX[name])
        out[name + ".twui.xml"] = EU.layout(
            root, "derpy: The Director - %s. Created at runtime by derpy_director_chronicle.lua. "
                  "Generated by tools/gen_director_ui.py; do not hand-edit." % what)
    return out


def lua_style():
    """DC.STYLE as the Lua declares it, {key: value as Python}, or None with no Lua yet."""
    if not os.path.isfile(LUA):
        return None
    src = io.open(LUA, encoding="utf-8").read()
    m = re.search(r"DC\.STYLE = \{(.*?)\n\}", src, re.S)
    if not m:
        return None
    out = {}
    for k, v in re.findall(r"(\w+) = (\"[^\"]*\"|-?\d+)", m.group(1)):
        out[k] = v.strip('"') if v.startswith('"') else int(v)
    return out


def check(files):
    """Every reason these files would draw wrong or not at all, as sentences."""
    import gen_guilds_ui as GG
    out = []
    out += GG.check_scroll_parts({"derpy_gg_list.twui.xml": files["derpy_director_list.twui.xml"]})
    owner = {}
    for name, text in sorted(files.items()):
        pre = PREFIX[name[:-len(".twui.xml")]]
        for g in set(re.findall(r'this="([^"]+)"', text)):
            if g in owner:
                out.append("%s and %s share the GUID %s" % (owner[g], name, g))
            owner[g] = name
            if not g.startswith(pre):
                out.append("%s carries %s, outside its prefix %s" % (name, g, pre))
        hier = text.split("<components>")[0]
        comps = text.split("<components>")[1] if "<components>" in text else ""
        for g in re.findall(r'<\w+ this="([^"]+)"', hier):
            if 'this="%s"' % g not in comps:
                out.append("%s: hierarchy node %s has no component, a silent non-draw" % (name, g))
    assets = EU._game_assets()
    for name, text in sorted(files.items()):
        for p in sorted(set(re.findall(r'imagepath="([^"]+)"', text))):
            if p not in assets:
                out.append("%s draws %s, which no CA ui pack ships: a white square" % (name, p))
    sounds = EU._game_sound_categories()
    for name, text in sorted(files.items()):
        for s in sorted(set(re.findall(r'soundcategory="([^"]+)"', text))):
            if s not in sounds:
                out.append("%s plays %s, a category CA never uses: silent" % (name, s))
    out += check_loc()
    lua = lua_style()
    if lua is None:
        out.append("derpy_director_chronicle.lua declares no DC.STYLE to compare with STYLE")
    else:
        for k in sorted(set(STYLE) | set(lua)):
            if STYLE.get(k) != lua.get(k):
                out.append("STYLE[%s] is %r here and %r in DC.STYLE" % (k, STYLE.get(k), lua.get(k)))
    # A [[col:]] name resolves against CA's ui_colours; an unknown one draws the default, silently.
    # Skipped without the vanilla cache (the public repository ships none of CA's tables).
    try:
        import read_vanilla_cache as V
        names = {r["blue"] for r in V.load("ui_colours")[0]}
    except (ImportError, FileNotFoundError, IndexError, ValueError):
        names = None
    for k in ("muted", "accent"):
        if names is not None and STYLE[k] not in names:
            out.append("STYLE[%s] is %r, which is not a colour in CA's ui_colours" % (k, STYLE[k]))
    # A header line the script fills and this file never made draws nothing, silently.
    src = io.open(LUA, encoding="utf-8").read() if os.path.isfile(LUA) else ""
    m = re.search(r"DC\.HEADER_LINES = \{([\d, ]*)\}", src)
    lines = [int(n) for n in re.findall(r"\d+", m.group(1))] if m else None
    if lines != [HEADER_LINES[r] for r in sorted(HEADER_LINES)]:
        out.append("HEADER_LINES is %r here and %r in DC.HEADER_LINES" % (HEADER_LINES, lines))
    return out


def _selftest():
    files = build()
    assert set(files) == {n + ".twui.xml" for n, _f, _w in FILES}
    found = check(files)
    assert not found, "\n".join(found)
    # The check can fail: a list with its container callback gone, and a GUID shared between two
    # files, must each be reported, or a clean report means nothing.
    broken = dict(files)
    broken["derpy_director_list.twui.xml"] = files["derpy_director_list.twui.xml"].replace(
        'callback_id="Listview"', 'callback_id="Nothing"')
    assert [x for x in check(broken) if "Listview" in x], check(broken)
    g = re.search(r'this="(DR03[^"]+)"', files["derpy_director_line.twui.xml"]).group(1)
    broken = dict(files)
    broken["derpy_director_button.twui.xml"] += '<x this="%s"/>' % g
    assert [x for x in check(broken) if "share the GUID" in x], check(broken)
    # And the loc check: a row taken away is reported, and so is a row nobody uses.
    saved = dict(CHRONICLE_LOC)
    try:
        del CHRONICLE_LOC["deed_raze"]
        CHRONICLE_LOC["orphan"] = "x"
        got = check_loc()
        assert [x for x in got if "deed_raze, which has no loc row" in x], got
        assert [x for x in got if "orphan, which nothing uses" in x], got
    finally:
        CHRONICLE_LOC.clear()
        CHRONICLE_LOC.update(saved)
    print("selftest ok: %d files, %d checks clean" % (len(files), len(files)))


def main(argv):
    unknown = [a for a in argv if a not in ("--check", "--selftest")]
    if unknown:
        print("unknown argument(s): %s" % " ".join(unknown))
        return 2
    if "--selftest" in argv:
        _selftest()
        return 0
    files = build()
    faults = check(files)
    for f in faults:
        print("FAULT   " + f)
    if faults:
        return 1
    drift = []
    for name, text in sorted(files.items()):
        path = os.path.join(OUT, name)
        old = io.open(path, encoding="utf-8").read() if os.path.isfile(path) else None
        if old != text:
            drift.append(name)
            if "--check" not in argv:
                io.open(path, "w", encoding="utf-8", newline="\n").write(text)
    for name in drift:
        print(("drift   " if "--check" in argv else "wrote   ") + name)
    if "--check" in argv:
        return 1 if drift else 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
