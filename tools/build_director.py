"""Build and check derpy_director.pack - the Director.

    py tools/build_director.py --selftest   run the shipped Lua under stubs
    py tools/build_director.py --check      regenerate the lore file and verify, no RPFM
    py tools/build_director.py              pack it (rpfm_server starts itself)

The selftest RUNS `Modding Files/pack/script/campaign/mod/derpy_director.lua` under Lua 5.1.5
against a stubbed campaign and asserts on the calls it recorded - it does not re-implement the
logic in Python. See docs/superpowers/specs/2026-09-16-ai-director-design.md
"""
import os
import re
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
MCT_PAGE = os.path.join(ROOT, "Modding Files", "pack", "script", "mct", "settings",
                        "derpy_director.lua")
IN_PACK_MCT = "script/mct/settings/derpy_director.lua"

# ---------------------------------------------------------------- the event feed
#
# FRAG is the fragment name every table and the loc share. Versions are read off CA's own
# shipped tables, not off RPFM's default for the name - those can disagree, and a version that
# does not match the field shape is rejected at load with a bad_mods_report line.
FRAG = "derpy_director_feed"
TSV_DIR = os.path.join(ROOT, "Modding Files", "source", "director_feed")
FEED_TABLES = [
    ("campaign_groups", 0),
    ("campaign_group_members", 1),
    ("campaign_group_member_criteria_values", 0),
    ("event_feed_message_events", 1),
    ("event_feed_strings", 0),
]

# One entry per message the Director can raise. `index` is what the Lua passes as
# show_message_event's last argument; it must be absent from vanilla's 229 used values and well
# clear of vanilla's highest, 1960.
#
# image is the picture in the opened message and MUST NOT be empty - no vanilla row leaves it so.
# Only ui/eventpics/all/ is culture-neutral; everything else is another race's artwork on a
# message that can fire for any of them. Both of these were chosen by extracting the candidates
# and looking at them, not by reading the filenames.
#
# override_icon is the 74x74 badge in the feed strip, a bare filename under
# ui/campaign ui/message_icons/ in ui.pack. event_gen_news_* is CA's own general-news badge,
# which is exactly what this is, and it is one of the few that carries no race mark.
FEED_ROWS = [
    {
        "key": "grudge", "index": 7300,
        "image": "all/carnage_weapons",
        "icon": "event_gen_news_negative.png",
        "sound": "UI_CAM_POPUP_Message_Event_Negative",
        "title": "A Wrong Remembered",
        "primary": "A settlement has been attacked. Powers nearby who already had reason to "
                   "hate the attacker have taken note, and their opinion of them has worsened.",
        "secondary": "They will not forget it. The grudge now colours every dealing they have "
                     "with the attacker.",
    },
    {
        "key": "pact", "index": 7400,
        "image": "all/elector_confederation",
        "icon": "event_gen_news_positive.png",
        "sound": "UI_CAM_POPUP_Message_Event_Positive",
        "title": "Common Cause",
        "primary": "Two powers that share an enemy have signed a defensive alliance. Each "
                   "will now answer if the other is attacked.",
        "secondary": "The attacker now faces two swords where yesterday there was one.",
    },
    # Generic only, no per-culture records: these two are not in FEED_BASE. ivory_road is CA's
    # caravan art, already the Resource Overhaul's raid picture; minor_cult is a cult sigil on
    # parchment. Both looked at, 2026-11-13.
    {
        "key": "raid", "index": 7500,
        "image": "all/ivory_road",
        "icon": "event_gen_news_negative.png",
        "sound": "UI_CAM_POPUP_Message_Event_Negative",
        "title": "A Convoy Seized",
        "primary": "An army has seized a convoy of goods on the road. Powers nearby who already "
                   "had reason to hate the raider have taken note, and their opinion of them has "
                   "worsened.",
        "secondary": "Word travels the trade roads faster than any cart, and it loses nothing "
                     "in the telling.",
    },
    {
        "key": "guild", "index": 7600,
        "image": "all/minor_cult",
        "icon": "event_gen_news_negative.png",
        "sound": "UI_CAM_POPUP_Message_Event_Negative",
        "title": "The Faithful Turn Away",
        "primary": "Your armies have spilled the blood of your own kin, and your temple has heard "
                   "of it. Your Reputation with the temple has fallen.",
        "secondary": "The priests forgive slowly. What was lost must be earned back in the "
                     "temple's service.",
    },
    # An Iron Court secession, told once to the realm that split, whichever beat landed: the
    # grudge and pact records say the realm attacked someone, and it did not. carnage_weapons is
    # the grudge's picture, already looked at.
    {
        "key": "rising", "index": 7700,
        "image": "all/carnage_weapons",
        "icon": "event_gen_news_negative.png",
        "sound": "UI_CAM_POPUP_Message_Event_Negative",
        "title": "Vultures Gather",
        "primary": "Your realm has split, and its neighbours have noticed. Powers that already "
                   "counted you an enemy now think even less of you.",
        "secondary": "A divided realm is a tempting one, and its enemies are always the first to "
                     "see the cracks.",
    },
    # The storyteller (2026-11-14). One of these three is shown once, at the start of a campaign,
    # at the player's capital: the temperament rolled for it. Each says only what that temperament
    # does - how readily the world answers bloodshed, and in what rhythm.
    {
        "key": "temper_rising", "index": 7800,
        "image": "all/elector_confederation",
        "icon": "event_gen_news_positive.png",
        "sound": "UI_CAM_POPUP_Message_Event_Positive",
        "title": "A Restless World",
        "primary": "The powers of this world answer bloodshed in waves. For a time they are quick "
                   "to take offence and band together against an aggressor, then they settle for "
                   "a while before stirring again.",
        "secondary": "Watch for the calm. It never lasts.",
    },
    {
        "key": "temper_patient", "index": 7801,
        "image": "all/elector_confederation",
        "icon": "event_gen_news_positive.png",
        "sound": "UI_CAM_POPUP_Message_Event_Positive",
        "title": "A Patient World",
        "primary": "The powers of this world are slow to anger. Most wrongs pass with little "
                   "said, but every so often they turn on an aggressor together.",
        "secondary": "A long silence is not the same as forgiveness.",
    },
    {
        "key": "temper_wild", "index": 7802,
        "image": "all/elector_confederation",
        "icon": "event_gen_news_positive.png",
        "sound": "UI_CAM_POPUP_Message_Event_Positive",
        "title": "A Fickle World",
        "primary": "The powers of this world cannot be predicted. One wrong goes unremarked, and "
                   "the next sets half the region against the aggressor.",
        "secondary": "Nobody knows what they will do next, least of all you.",
    },
    # Opportunism, told to whoever took the most from the faction that lost ground.
    {
        "key": "blood", "index": 7900,
        "image": "all/carnage_weapons",
        "icon": "event_gen_news_positive.png",
        "sound": "UI_CAM_POPUP_Message_Event_Positive",
        "title": "Blood in the Water",
        "primary": "Your enemy has lost ground, and the powers around it have noticed. Those who "
                   "already counted it an enemy have turned against it too.",
        "secondary": "A wounded beast draws more than one hunter.",
    },
    # A broken treaty, told to the oath-breaker or the betrayed, so it is true for both.
    {
        "key": "betrayal", "index": 8000,
        "image": "all/carnage_weapons",
        "icon": "event_gen_news_negative.png",
        "sound": "UI_CAM_POPUP_Message_Event_Negative",
        "title": "An Oath Broken",
        "primary": "A treaty has been broken, and the powers nearby have noticed. Those who "
                   "already distrusted the oath-breaker now think even less of them.",
        "secondary": "Word of a broken oath travels faster than any army.",
    },
]

# A feed message cannot name a faction: show_message_event takes loc KEYS and the only markup
# vanilla ever uses in event_feed_strings is {{tr:}} (279 uses), [[col:]], [[img:]], [[url:]],
# [[tooltip:]], {{tt:}} and [[sl:]] - every one of which resolves at AUTHORING time. There is no
# runtime substitution token anywhere in the 877 vanilla strings.
#
# What it can do is name a CULTURE, by shipping one record per subculture and pulling the real
# localised name in with {{tr:cultures_subcultures_name_<subculture>}}. That is why these exist:
# the message says who took note and wears their artwork, at the cost of a record apiece.
#
# Keyed on the subculture of the LEAD responder - cast[1], the faction that hates the aggressor
# most - because that is the voice the message speaks in.
CULTURE_FLAVOUR = {
    "wh_main_sc_dwf_dwarfs": ("A Grudge Is Written",
        "A scribe of the Dammaz Kron has already dipped his pen, and the entry will outlast "
        "every living witness to it."),
    "wh_main_sc_emp_empire": ("Word Reaches the Empire",
        "Couriers are already riding for the nearest Elector. It will be read out in his "
        "hall, and the Empire keeps its records."),
    "wh_main_sc_brt_bretonnia": ("A Matter of Honour",
        "The tale is told at table. Knights who have never seen the place have already sworn "
        "it will be answered."),
    "wh_main_sc_teb_teb": ("The Border Princes Hear",
        "Here such news is a warning rather than an outrage. Everyone in these lands is one bad "
        "season from the same fate."),
    "wh3_main_sc_ksl_kislev": ("The Motherland Takes Note",
        "The news travels the ice roads, and the boyars add another name to the long list of "
        "things Kislev does not forgive."),
    "wh3_main_sc_cth_cathay": ("Filed by the Celestial Bureaucracy",
        "A clerk enters the deed in a ledger, stamped and sealed. The Dragon Emperor's officials "
        "are slow, but they are patient."),
    "wh2_main_sc_hef_high_elves": ("The Phoenix Court Is Informed",
        "They discuss it in measured tones. The answer will take a century to arrive, and it "
        "has already been decided."),
    "wh2_main_sc_def_dark_elves": ("Noted in Naggaroth",
        "The Druchii find the news useful rather than shocking, and file it where such leverage "
        "is kept."),
    "wh_dlc05_sc_wef_wood_elves": ("The Forest Stirs",
        "Word passes root to root. The Asrai care nothing for the settlement and a great deal "
        "about who is now strong enough to take one."),
    "wh2_main_sc_lzd_lizardmen": ("The Great Plan Is Consulted",
        "A Slann stirs long enough to mark a deviation, and the geomantic web records what the "
        "warm-blooded have done."),
    "wh2_main_sc_skv_skaven": ("Squeaked of in the Under-Empire",
        "The tale is traded in the tunnels and embellished at every telling. What survives of it "
        "is the part about weakness."),
    "wh_main_sc_grn_greenskins": ("Word Gets Round da Boyz",
        "It gets retold wrong and louder every time. The part about a good scrap going spare "
        "always survives."),
    "wh_main_sc_grn_savage_orcs": ("Word Gets Round da Boyz",
        "It gets retold wrong and louder every time. The part about a good scrap going spare "
        "always survives."),
    "wh_main_sc_vmp_vampire_counts": ("The Dead Are Told",
        "In the silence of the crypts the news is welcome. Battles leave bodies, and bodies are "
        "a resource."),
    # Patch 9.0. Its subculture name loc reads "Undead Legions", so the body says "The Undead
    # Legions have taken note" - plural, like the Vampire Counts. Art is ui/eventpics/nag/.
    "wh3_dlc29_sc_nag_undead_legions": ("Nagash Remembers",
        "The Great Necromancer forgets nothing. Every life the attacker takes is one more soul "
        "he means to claim for himself."),
    "wh2_dlc09_sc_tmb_tomb_kings": ("Set Down by the Mortuary Cult",
        "A liche priest inscribes the offence on a tablet. Nehekhara has waited longer than this "
        "to settle far smaller slights."),
    "wh2_dlc11_sc_cst_vampire_coast": ("It Reaches the Coast",
        "The story is worth a drink in every rotten port, and it grows bigger with every "
        "telling."),
    "wh3_main_sc_ogr_ogre_kingdoms": ("The Tribes Hear of It",
        "The Ogres take a keen interest in anyone strong enough to take what they want. Such "
        "people are either worth hiring or worth eating."),
    "wh_dlc08_sc_nor_norsca": ("The Skalds Have a New Verse",
        "It is sung badly and often. Whether the aggressor is a rival or an example depends "
        "entirely on who is listening."),
    "wh_main_sc_chs_chaos": ("The Host Marks It",
        "Ambition is the only currency here, and somebody has just spent a great deal of it "
        "where everyone could see."),
    "wh_dlc03_sc_bst_beastmen": ("The Herdstones Know",
        "The beasts smell burning and ruin, and they are drawn to it the way flies are drawn to "
        "meat."),
    "wh3_dlc23_sc_chd_chaos_dwarfs": ("Entered in the Ledgers of Zharr",
        "The loss is recorded in slaves and in coin. Both figures will be collected in time, "
        "with interest."),
    "wh3_main_sc_kho_khorne": ("Blood Is Counted",
        "Khorne cares not from whence the blood flows, but his servants keep careful count of "
        "who is spilling it, and where."),
    "wh3_main_sc_nur_nurgle": ("Grandfather Smiles",
        "War breeds fever and famine. The gift is already spreading, and Nurgle's "
        "children are grateful for the invitation."),
    "wh3_main_sc_tze_tzeentch": ("A Thread Is Pulled",
        "The change is noted and immediately turned to use. Tzeentch's servants had other plans "
        "for that town, and now they have new ones."),
    "wh3_main_sc_sla_slaanesh": ("Noted with Interest",
        "The excess of it is appreciated as craftsmanship. Slaanesh's followers judge an attack "
        "by its style, and this one has been judged."),
    "wh3_main_sc_dae_daemons": ("The Realms Take Note",
        "In the Realm of Chaos the deed registers as a small and pleasing tremor, and something "
        "turns its attention outward."),
}
# The prologue subcultures are the same peoples with a different key.
CULTURE_FLAVOUR["wh3_main_pro_sc_ksl_kislev"] = CULTURE_FLAVOUR["wh3_main_sc_ksl_kislev"]
CULTURE_FLAVOUR["wh3_main_pro_sc_kho_khorne"] = CULTURE_FLAVOUR["wh3_main_sc_kho_khorne"]
CULTURE_FLAVOUR["wh3_main_pro_sc_tze_tzeentch"] = CULTURE_FLAVOUR["wh3_main_sc_tze_tzeentch"]

# Southern Realms ship no eventpics folder of their own; they are humans of the Old World.
ART_ALIAS = {"teb": "emp"}

sys.path.insert(0, os.path.join(ROOT, "tools"))

# ---------------------------------------------------------------- the MCT page
#
# The ONE source of the Director's MCT options (2026-11-14). mct_page() writes the page from it and
# build_lore() writes the defaults the campaign reader falls back on, so the page and the reader
# cannot disagree. One checkbox per race in merge_races() is added on top, each defaulting on.
MCT_SECTIONS = [
    ("merging", "Confederations"),
    ("races", "Races the Director may confederate"),
    ("runaway", "A runaway power"),
]
MCT_OPTIONS = [
    {"key": "merge_last_stand", "kind": "checkbox", "default": True, "section": "merging",
     "text": "Last stands",
     "tooltip": "A faction down to its last settlements can join a stronger faction of its own "
                "race instead of being wiped out. Only factions the game itself would let "
                "confederate can do this, and never a player's faction."},
    {"key": "merge_runaway", "kind": "checkbox", "default": True, "section": "merging",
     "text": "Kin unite against a runaway power",
     "tooltip": "When a faction that has grown far larger than everyone else attacks a "
                "settlement, the defender may confederate with its own kin to face it. The "
                "endgame invasions count as runaway powers from the moment they arrive."},
    {"key": "last_stand_regions", "kind": "slider", "default": 1, "lo": 1, "hi": 5,
     "section": "merging", "text": "Last stand at",
     "tooltip": "How few settlements a faction must have left before it can join stronger kin. "
                "At 1, only a faction holding its very last settlement can."},
    {"key": "runaway_merge_tier", "kind": "slider", "default": 1, "lo": 1, "hi": 3,
     "section": "merging", "text": "How far ahead a runaway power must be",
     "tooltip": "How far one faction must outgrow the next largest before its victims' kin "
                "unite against it. At 1 it holds one and three quarters times as many "
                "settlements, at 2 two and a half times, and at 3 four times."},
    {"key": "merge_price", "kind": "slider", "default": 60, "lo": 0, "hi": 180,
     "section": "merging", "text": "Cost of a confederation",
     "tooltip": "The world reacts to events from a pool that refills every turn and starts at "
                "180. Each confederation spends this much of it, so a higher cost means fewer "
                "confederations and fewer other reactions on that turn."},
    {"key": "merges_per_turn", "kind": "slider", "default": 1, "lo": 0, "hi": 3,
     "section": "merging", "text": "Confederations per turn",
     "tooltip": "The most confederations the Director causes in one turn, across the whole "
                "world. At 0 it causes none. Factions can still confederate through the game's "
                "own diplomacy."},
    {"key": "merge_from_turn", "kind": "slider", "default": 10, "lo": 1, "hi": 100,
     "section": "merging", "text": "First turn",
     "tooltip": "The Director causes no confederation before this turn."},
    {"key": "merge_needs_willing", "kind": "checkbox", "default": False, "section": "merging",
     "text": "Only willing factions",
     "tooltip": "Two factions confederate only if they would also accept it in diplomacy. They "
                "almost never would, so turning this on stops most confederations."},
    {"key": "runaway_threat", "kind": "checkbox", "default": True, "section": "runaway",
     "text": "The world turns against a runaway power",
     "tooltip": "When one faction grows far larger than the rest, every other faction likes it "
                "less, and the further ahead it pulls the less they like it. This lifts once it "
                "falls back."},
    {"key": "runaway_alliances", "kind": "checkbox", "default": True, "section": "runaway",
     "text": "Defensive alliances against a runaway power",
     "tooltip": "Factions that have met the runaway power and would agree to a defensive "
                "alliance with each other sign one, at most two a turn."},
    {"key": "runaway_min_regions", "kind": "slider", "default": 10, "lo": 5, "hi": 40,
     "section": "runaway", "text": "Smallest runaway power",
     "tooltip": "A faction needs at least this many settlements before it can count as a "
                "runaway power at all."},
]
RACE_TOOLTIP = ("Whether the Director may confederate factions of this race. The game's own "
                "rules for this race still apply, and the game's own diplomacy is not changed.")


def merge_races():
    """[(subculture, display name)] the brain may ever merge: every subculture in CA's table
    except the frontend filter, the prologue copies, and those CA marks unable to confederate.
    Absent from the restrictions table (Chaos Dwarfs, Vampire Coast) is not a ban."""
    from read_vanilla_db import DB_PACK, load
    from read_vanilla_loc import load as load_loc
    banned = {r["subculture"] for _p, _v, rows in
              load(DB_PACK, "diplomatic_action_subculture_restrictions_tables")
              for r in rows if not r["can_make_confederations"]}
    keys = {r["subculture"] for _p, _v, rows in load(DB_PACK, "cultures_subcultures_tables")
            for r in rows}
    names = load_loc("cultures_subcultures")
    return [(sc, names["cultures_subcultures_name_" + sc]) for sc in sorted(keys)
            if sc != "filter_all" and "_pro_" not in sc and sc not in banned]


def mct_page():
    """The page, generated. It runs in MCT's own environment and cannot see the campaign script."""
    q = lambda s: _lua(s)
    lines = [
        "-- GENERATED by tools/build_director.py from MCT_OPTIONS. Do not edit by hand.",
        "-- MCT loads every .lua under script/mct/settings/, so this only runs when MCT is",
        "-- installed; without it the Director plays on these defaults. It runs in MCT's own",
        "-- environment and cannot see the campaign script.",
        "",
        "local mct = get_mct and get_mct()",
        "if not mct then return end",
        "",
        'local m = mct:register_mod("derpy_director")',
        'm:set_title("The Director")',
        'm:set_author("derpy")',
        "m:set_description(%s)" % q(
            "The world reacts to what factions do: neighbours turn on an aggressor, kin unite "
            "against a runaway power, and a dying faction can join its own kind. Changes take "
            "effect the next time the setting is needed. Multiplayer always uses the defaults, "
            "because two players with different settings would fall out of step."),
    ]
    for key, title in MCT_SECTIONS:
        lines.append("m:add_new_section(%s, %s)" % (q(key), q(title)))
    options = list(MCT_OPTIONS) + [
        {"key": "race_" + sc, "kind": "checkbox", "default": True, "section": "races",
         "text": name, "tooltip": RACE_TOOLTIP} for sc, name in merge_races()]
    for i, o in enumerate(options):
        v = "o%d" % i
        lines += ["", "local %s = m:add_new_option(%s, %s)" % (v, q(o["key"]), q(o["kind"])),
                  "%s:set_text(%s)" % (v, q(o["text"])),
                  "%s:set_tooltip_text(%s)" % (v, q(o["tooltip"]))]
        if o["kind"] == "slider":
            lines += ["%s:slider_set_precision(0)" % v,
                      "%s:slider_set_min_max(%d, %d)" % (v, o["lo"], o["hi"]),
                      "%s:slider_set_step_size(1, 0)" % v]
        lines += ["%s:set_default_value(%s)" % (v, _lua(o["default"])),
                  "%s:set_assigned_section(%s)" % (v, q(o["section"]))]
    return "\n".join(lines) + "\n"


MCT_STUB = r'''
local PAGE, DUMP = ...
local rec = {}
local function option(key, kind)
  local o = {key = key, kind = kind}
  local self_ = {}
  local mt = {__index = function(_, name)
    if name == "set_default_value" then return function(_, v) o.default = v end end
    return function() end
  end}
  setmetatable(self_, mt)
  rec[#rec + 1] = o
  return self_
end
local mod = setmetatable({}, {__index = function(_, name)
  if name == "add_new_option" then return function(_, key, kind) return option(key, kind) end end
  return function() end
end})
function get_mct() return {register_mod = function() return mod end} end
dofile(PAGE)
local fh = io.open(DUMP, "w")
for _, o in ipairs(rec) do fh:write(o.key .. "\t" .. o.kind .. "\t" .. tostring(o.default) .. "\n") end
fh:close()
'''


def run_mct_page():
    """The SHIPPED page, run under a recording MCT stub: {key: (kind, default)}."""
    with tempfile.TemporaryDirectory() as td:
        stub, dump = os.path.join(td, "stub.lua"), os.path.join(td, "dump.txt")
        open(stub, "w", encoding="utf-8").write(MCT_STUB)
        r = subprocess.run([LUA, stub, MCT_PAGE, dump], capture_output=True, text=True)
        assert r.returncode == 0, "the MCT page failed under the stub: %s" % r.stderr
        out = {}
        for line in open(dump, encoding="utf-8").read().splitlines():
            key, kind, default = line.split("\t")
            out[key] = (kind, {"true": True, "false": False}.get(default)
                        if default in ("true", "false") else int(default))
        return out


def outs(calls, s):
    """The log lines containing s."""
    return [c[1] for c in calls if c[0] == "out" and s in c[1]]


def evals(calls):
    """What each Eval pseudo-event returned, in order."""
    return [c[1] for c in calls if c[0] == "eval"]


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
local SPEC_BY_NAME = {}
local ORDER = {}
-- Each faction's regions, by name, so a SetRegions event can grow or shrink them mid-run.
local OWNED = {}

local REGIONS = {}
local OWNERS = {}
local function region(key, adj, pos)
  local r = {}
  function r:name() return key end
  function r:is_null_interface() return false end
  -- A region with no settlement is a real case (a sea region, a razed ruin), so the stub can
  -- return a null one. logical_position_* is what show_message_event_located documents; the
  -- display coordinates a mission location takes are a different pair of numbers entirely.
  function r:settlement()
    if not pos then return {is_null_interface = function() return true end} end
    return {
      is_null_interface = function() return false end,
      key = function() return "set_" .. key end,
      logical_position_x = function() return pos[1] end,
      logical_position_y = function() return pos[2] end,
    }
  end
  function r:owning_faction() return BY_NAME[OWNERS[key]] end
  -- One province per region here; the doc entry says it returns the province KEY.
  function r:province_name() return "p_" .. key end
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
  REGIONS[spec.key] = region(spec.key, spec.adj, spec.pos)
end

local function faction(spec)
  local f = {}
  function f:name() return spec.name end
  function f:is_null_interface() return false end
  function f:is_dead() return spec.dead == true end
  function f:is_rebel() return spec.rebel == true end
  function f:is_human() return spec.human == true end
  function f:subculture() return spec.subculture or "" end
  local owned = {}
  for _, k in ipairs(spec.owns or {}) do
    if REGIONS[k] then owned[#owned + 1] = REGIONS[k] end
  end
  for i = #owned + 1, (spec.regions or 0) do
    owned[i] = region("filler_" .. spec.name .. i, {})
  end
  OWNED[spec.name] = owned
  function f:region_list() return list(OWNED[spec.name]) end
  function f:home_region() return OWNED[spec.name][1] end
  -- CA passes a KEY STRING here, in all five of its own call sites - not an interface.
  function f:diplomatic_attitude_towards(key)
    -- A deliberate engine fault OUTSIDE the builder's own pcall, to prove nothing escapes.
    if spec.throws then error("stub: deliberate fault in diplomatic_attitude_towards") end
    record("diplomatic_attitude_towards", spec.name, key)
    return (spec.attitudes or {})[key] or 0
  end
  -- Resolved through BY_NAME at CALL time, not build time: the faction this one is at war with
  -- may be constructed after it.
  function f:factions_at_war_with()
    local items = {}
    for _, n in ipairs(spec.wars or {}) do
      if BY_NAME[n] then items[#items + 1] = BY_NAME[n] end
    end
    return list(items)
  end
  -- Either side's list counts, as a war in game is one state both factions share.
  local function shared(field, other)
    local o = other:name()
    for _, n in ipairs(spec[field] or {}) do if n == o then return true end end
    local ospec = SPEC_BY_NAME[o]
    for _, n in ipairs(ospec and ospec[field] or {}) do if n == spec.name then return true end end
    return false
  end
  function f:at_war_with(other) return shared("wars", other) end
  function f:defensive_allies_with(other) return shared("allies", other) end
  function f:military_allies_with(other) return shared("military", other) end
  -- `met` absent means this faction has met everyone, which is what every older fixture assumed.
  function f:factions_met()
    local items = {}
    for _, g in ipairs(ORDER) do
      if g:name() ~= spec.name then
        local ok = spec.met == nil
        for _, n in ipairs(spec.met or {}) do if n == g:name() then ok = true end end
        if ok then items[#items + 1] = g end
      end
    end
    return list(items)
  end
  function f:is_vassal() return spec.vassal_of ~= nil end
  function f:is_vassal_of(other) return spec.vassal_of == other:name() end
  function f:has_effect_bundle(key)
    for _, b in ipairs(spec.bundles or {}) do if b == key then return true end end
    return false
  end
  return f
end

for _, spec in ipairs(FACTIONS) do
  for _, k in ipairs(spec.owns or {}) do OWNERS[k] = spec.name end
  SPEC_BY_NAME[spec.name] = spec
  local f = faction(spec)
  BY_NAME[spec.name] = f
  ORDER[#ORDER + 1] = f
end

local CURRENT_TURN = 0

cm = {}
function cm:model()
  return {
    world = function() return {
      faction_list = function() return list(ORDER) end,
      region_manager = function() return {
        region_by_key = function(_, k) return REGIONS[k] end,
      } end,
    } end,
    turn_number = function() return CURRENT_TURN end,
    -- CA's own read of a script state (crisis scenarios, episodes): nil when never set.
    shared_states_manager = function() return {
      get_state_as_bool_value = function(_, key) return SCRIPT_STATE[key] end,
    } end,
  }
end
function cm:is_multiplayer() return MULTIPLAYER == true end
-- MCT exists only when a fixture installs it, as in a game without the mod. An option the
-- fixture does not name answers nil, and the reader falls back to its default.
if MCT_VALUES then
  function get_mct()
    return {get_mod_by_key = function(_, k)
      if k ~= "derpy_director" then return nil end
      return {get_option_by_key = function(_, key)
        local v = MCT_VALUES[key]
        if v == nil then return nil end
        return {get_finalized_setting = function() return v end}
      end}
    end}
  end
end
-- The payload route. FactionJoinsConfederation fires INSIDE apply_payload, as it does in game
-- (measured 2026-10-10), so the Director's own listener runs while the merge is still in the call.
function cm:create_payload()
  local p = {}
  function p:form_confederation(owner, other, awake, convert)
    if type(owner) ~= "table" or type(other) ~= "table" then
      error("form_confederation takes faction INTERFACES")
    end
    p.owner, p.other = owner, other
    return true
  end
  return p
end
function cm:apply_payload(p, faction)
  if PAYLOAD_ERROR then error("stub: deliberate fault in apply_payload") end
  record("apply_payload", p.owner:name(), p.other:name())
  -- As in game: the absorbed faction is dead at once and its regions are the absorber's.
  local gone = p.other:name()
  SPEC_BY_NAME[gone].dead = true
  for _, r in ipairs(OWNED[gone]) do table.insert(OWNED[p.owner:name()], r) end
  OWNED[gone] = {}
  local fns = LISTENERS["FactionJoinsConfederation"]
  local ctx = {confederation = function() return p.owner end, faction = function() return p.other end}
  if fns then for _, fn in ipairs(fns) do fn(ctx) end end
end
function cm:get_faction(key) return BY_NAME[key] or false end
function cm:add_first_tick_callback(fn) FIRST_TICKS[#FIRST_TICKS + 1] = fn end
-- A preload is the value the SAVE carried in, so it seeds the store once and is then written
-- over like any other. Reading PRELOAD ahead of SAVED on every get - as this did until
-- 2026-09-17 - freezes a preloaded key for the whole run: a budget preloaded to 0 could never
-- rise and one preloaded high could never be spent, so every assertion resting on either passed
-- without exercising the budget at all.
for k, v in pairs(PRELOAD) do SAVED[k] = v end
function cm:set_saved_value(name, value) SAVED[name] = value end
function cm:get_saved_value(name) return SAVED[name] end
-- Clamped into [min, max] as the real one is. SEED_ROLL is one number for every call, or a list
-- consumed in order and then repeating its last entry, so a test can script a run of dice.
local ROLL_I = 0
function cm:random_number(max, min)
  max, min = max or 100, min or 1
  record("random_number", max, min)
  local r = SEED_ROLL
  if type(r) == "table" then
    ROLL_I = ROLL_I + 1
    r = r[math.min(ROLL_I, #r)]
  end
  return math.max(min, math.min(max, r))
end
function cm:get_human_factions()
  local out = {}
  for _, f in ipairs(ORDER) do
    if f:is_human() then out[#out + 1] = f:name() end
  end
  return out
end
function cm:cai_evaluate_quick_deal_action(a, b, deal)
  record("cai_evaluate_quick_deal_action", a:name(), b:name(), deal)
  local s = SCORES[a:name() .. "|" .. b:name()]
  local ok = not DENY[a:name() .. "|" .. b:name()]
  if s == nil then return 0, ok end
  return s, ok
end
-- Settlement key, NOT region key - campaign_map_settlements, reached via settlement:key().
function cm:cai_disable_targeting_against_settlement(k) record("shield_on", k) end
function cm:cai_enable_targeting_against_settlement(k) record("shield_off", k) end
-- The 9.0 signature: SPREADER FACTION interface, region interface, plague key. The 8.x call was
-- (region, key); this errors on it, because the engine would read the region as the faction.
function cm:spawn_plague_at_region(faction, region, plague)
  if type(faction) ~= "table" or not faction.subculture then
    error("spawn_plague_at_region: 9.0 takes the spreader FACTION interface first")
  end
  record("spawn_plague_at_region", faction:name(), region:name(), plague)
end
-- Takes the region INTERFACE, a faction KEY, max units and a full-strength flag. The 5th
-- argument (not passed) is "suppress PUBLIC ORDER penalty", not the suppress-MESSAGE flag the
-- old call carried in that slot.
function cm:force_rebellion_with_faction(region, faction, units, full, suppress_po)
  record("force_rebellion_with_faction", region:name(), faction, units)
  return {}
end
-- DELIBERATELY FATAL. This call has no faction argument and spawns into the generic `rebels`
-- faction - a Warriors of Chaos sorcerer lord rose over a Kislev province on 2026-09-22. Left
-- as a recording stub, a regression back to it would have passed every assertion here.
function cm:force_rebellion_in_region(key, units, x, y, suppress)
  error("force_rebellion_in_region spawns into the generic `rebels` faction and takes no "
     .. "faction argument - use force_rebellion_with_faction")
end
-- Documented as "This value must be positive" - it can fund, never fine.
function cm:treasury_mod(key, amount)
  if type(amount) ~= "number" or amount <= 0 then
    error("treasury_mod must be given a POSITIVE amount, got " .. tostring(amount))
  end
  record("treasury_mod", key, amount)
end
function cm:cai_strategic_stance_manager_promote_specified_stance_towards_target_faction(a, b, st)
  record("stance_promote", a, b, st)
end
function cm:set_base_strategic_threat_score(f, score)
  record("set_base_strategic_threat_score", f:name(), score)
end
function cm:force_alliance(a, b, military)
  record("force_alliance", a, b, tostring(military))
end
function cm:force_confederation(a, b) record("force_confederation", a, b) end
function cm:cai_add_diplomatic_event(from, to, action)
  record("cai_add_diplomatic_event", from, to, action)
end
-- Both message calls record `persistent` as well as the index, because passing true at a
-- scripted_transient_event record draws NOTHING and logs a line that reads like success. The
-- argument order is CA's, read off the doc entry: the located variant takes x and y BEFORE
-- persistent, so a stub that put them anywhere else would let a wrong call order pass.
function cm:show_message_event(faction, title, primary, secondary, persistent, index)
  record("show_message_event", faction, title, tostring(persistent) .. "|" .. tostring(index))
end
function cm:show_message_event_located(faction, title, primary, secondary, x, y,
                                       persistent, index)
  record("show_message_event_located", faction, title,
    tostring(x) .. "," .. tostring(y) .. "|" .. tostring(persistent) .. "|" .. tostring(index))
end
-- Errors in multiplayer unless forced, which is why the mod passes true. Returns "" when no
-- faction is flagged human, so a fixture without one models a world the message cannot address.
function cm:get_local_faction_name(force)
  for _, f in ipairs(ORDER) do
    if f:is_human() then return f:name() end
  end
  return ""
end

core = {}
function core:add_listener(_, event, _, fn, _)
  LISTENERS[event] = LISTENERS[event] or {}
  table.insert(LISTENERS[event], fn)
end
-- The environment CA's loader runs every mod file in. Here the stubs are plain globals.
function core:get_env() return _G end

-- Companion mods, when a fixture installs them. Each models only what the Director touches, and
-- the originals RECORD, so a test can see they still ran under the Director's wrapper. Both
-- seizure calls return early for a cargo already gone, as Resource Overhaul's do.
local RO_SHIPS, RO_CONVOYS = {}, {}
if COMPANIONS.ro then
  DERPY_MR_FLOWS = {}
  local F = DERPY_MR_FLOWS
  function F.ship_by_id(id) return RO_SHIPS[id] end
  function F.convoys() return RO_CONVOYS end
  function F.seize(s, captor)
    if RO_SHIPS[s.id] ~= s then return end
    RO_SHIPS[s.id] = nil
    record("ro_seize", s.f, captor:name())
    return "ro_result", nil, 3
  end
  function F.convoy_seize(c, captor)
    for i, x in ipairs(RO_CONVOYS) do
      if x == c then
        table.remove(RO_CONVOYS, i)
        record("ro_convoy_seize", c.f, captor:name())
        return
      end
    end
  end
end
if COMPANIONS.gg then
  GG = {}
  -- Returns what was actually taken: GG.penalise clamps to the Reputation held.
  function GG.penalise(f, guild, n)
    record("gg_penalise", f, guild, n)
    if COMPANIONS.gg_held then return math.min(n, COMPANIONS.gg_held) end
    return n
  end
end
-- The Iron Court: a court is a Chaos Dwarf's or a Dwarf's, and both share the nine party slugs.
-- secede and rebel_sour_all return what IC's do (provinces lost, relations soured), so a test can
-- see the wrapper hands the result back. ic_missing removes one call, to model a moved API.
local IC_PROVINCES = {}
if COMPANIONS.ic then
  IC = {}
  local COURT_SC = {["wh3_dlc23_sc_chd_chaos_dwarfs"] = true, ["wh_main_sc_dwf_dwarfs"] = true}
  function IC.is_human(key) return BY_NAME[key] ~= nil and BY_NAME[key]:is_human() end
  function IC.runs_court(f) return COURT_SC[f:subculture()] == true end
  function IC.loaded(key) record("ic_loaded", key) end
  function IC.save(key) record("ic_save", key) end
  function IC.move_loyalty(key, party, delta)
    record("ic_loyalty", key, party, delta)
    return true
  end
  function IC.defecting_provinces(key, slug) return IC_PROVINCES end
  function IC.secede(key, slug)
    record("ic_secede", key, slug)
    return 2
  end
  function IC.rebel_sour_all(rebels, key)
    record("ic_sour", rebels, key)
    return 5
  end
  if COMPANIONS.ic_missing then IC[COMPANIONS.ic_missing] = nil end
end

dofile(SCRIPT_PATH)
if LORE_PATH then dofile(LORE_PATH) end

for _, fn in ipairs(FIRST_TICKS) do fn() end

-- A turn STARTS before anything happens in it. WorldStartRound is round-scoped so it raises
-- once per turn, including turns nothing else happens on - which is what lets an idle stretch
-- accrue budget. Modelling this is not optional: the refill listener was invisible to a pump
-- that only dispatched the watched event, and the live budget drained to zero and stayed there.
local LAST_TURN = 0
for _, ev in ipairs(EVENTS) do
  CURRENT_TURN = ev.turn or (CURRENT_TURN + 1)
  while LAST_TURN < CURRENT_TURN do
    LAST_TURN = LAST_TURN + 1
    local starts = LISTENERS["WorldStartRound"]
    if starts then for _, fn in ipairs(starts) do fn({}) end end
  end
  local fns = LISTENERS[ev.event]
  -- Not engine events: Resource Overhaul's own seizure calls, made the way its turn makes them.
  -- A stale cargo is one already delivered or taken, which the real calls ignore.
  if ev.event == "ShipmentSeized" then
    local s = {id = "ship_" .. tostring(ev.region), f = ev.victim, from = ev.region, x = 7, y = 9}
    if not ev.stale then RO_SHIPS[s.id] = s end
    local a, b, c = DERPY_MR_FLOWS.seize(s, BY_NAME[ev.instigator])
    record("seize_returned", a, b, c)
  elseif ev.event == "ConvoySeized" then
    local c = {f = ev.victim, buyer = "nobody", from = ev.region, x = 7, y = 9}
    if not ev.stale then RO_CONVOYS[#RO_CONVOYS + 1] = c end
    DERPY_MR_FLOWS.convoy_seize(c, BY_NAME[ev.instigator])
  -- The Iron Court's secession, the way its turn runs it: IC.secede reads the provinces and
  -- starts the rising, and the last of its timed steps sours the rebels' relations. A stale
  -- secession is one whose last step has not run yet (SecessionDone runs it) or never will.
  -- instigator is the realm, victim the rebels, region the province taken.
  elseif ev.event == "Secession" then
    IC_PROVINCES = {"p_" .. tostring(ev.region)}
    record("secede_returned", IC.secede(ev.instigator, "legion"))
    if not ev.stale then record("sour_returned", IC.rebel_sour_all(ev.victim, ev.instigator)) end
  elseif ev.event == "SecessionDone" then
    record("sour_returned", IC.rebel_sour_all(ev.victim, ev.instigator))
  -- Not an engine event: instigator's region count becomes n, for adaptation to measure at the
  -- next turn start. Losing keeps the first n; gaining adds fillers.
  elseif ev.event == "SetRegions" then
    local owned = OWNED[ev.instigator]
    while #owned > ev.n do table.remove(owned) end
    for i = #owned + 1, ev.n do owned[i] = region("gained_" .. ev.instigator .. i, {}) end
  -- Not an engine event: the budget set mid-turn, after the turn start's refill has paid out.
  elseif ev.event == "SetBudget" then
    SAVED["derpy_director_budget"] = ev.n
  -- Not an engine event: instigator has now met exactly ev.met (nil: everyone).
  elseif ev.event == "SetMet" then
    SPEC_BY_NAME[ev.instigator].met = ev.met
  -- Not an engine event: run a line of Lua against the loaded mod and record what it returned.
  elseif ev.event == "Eval" then
    local fn = assert(loadstring(ev.code))
    local v = fn()
    record("eval", tostring(v))
  elseif fns then
    -- The DOCUMENTED shape of CharacterSackedSettlement / CharacterRazedSettlement, not a
    -- convenient one. The event exposes exactly two accessors, character() and
    -- garrison_residence(), and CA's own scripts (wh_grudges.lua, wh2_dlc15_grom_cauldron.lua,
    -- wh3_campaign_followers.lua and two more) reach the factions as
    -- context:character():faction() and context:garrison_residence():faction().
    --
    -- An earlier version of this harness invented context:instigator(). The shipped Lua agreed
    -- with the invention, every offline check passed, and the live game logged "attempt to call
    -- method 'instigator' (a nil value)" nine times in one session. A stub that models the code
    -- instead of the engine cannot catch anything.
    -- One context shape per event, each taken from CA's doc entry and its own scripts:
    --   CharacterSackedSettlement / CharacterRazedSettlement -> character, garrison_residence
    --   RegionFactionChangeEvent                             -> region, previous_faction, reason
    --   FactionJoinsConfederation                            -> confederation, faction
    -- They are deliberately NOT merged into one permissive table. A context that answers every
    -- accessor lets the mod call one the real event does not have, which is exactly how an
    -- invented context:instigator() passed every offline check and died in the live game.
    local ctx
    if ev.event == "NegativeDiplomaticEvent" then
      -- CA's documented accessors, all of them: ev.treaty names the one that is true, and no
      -- treaty at all is a plain declaration of war.
      local function flag(name) return function() return ev.treaty == name end end
      ctx = {
        proposer = function() return BY_NAME[ev.instigator] end,
        recipient = function() return BY_NAME[ev.victim] end,
        is_war = function() return true end,
        was_alliance = flag("was_alliance"),
        was_military_alliance = flag("was_military_alliance"),
        was_defensive_alliance = flag("was_defensive_alliance"),
        was_non_aggression_pact = flag("was_non_aggression_pact"),
        was_trade_agreement = flag("was_trade_agreement"),
        was_military_access = flag("was_military_access"),
        was_vassalage = flag("was_vassalage"),
        result_of_confederation = function() return ev.reason == "confederation" end,
      }
    elseif ev.event == "RegionFactionChangeEvent" then
      ctx = {
        region = function() return REGIONS[ev.region] or region(ev.region, {}) end,
        previous_faction = function() return BY_NAME[ev.victim] end,
        -- "normal capture" is the engine's own word for a capture by force; "conquest" is not
        -- in its vocabulary at all (CA lists every value in wh2_dlc13_empire_politics.lua).
        reason = function() return ev.reason or "normal capture" end,
      }
    elseif ev.event == "FactionJoinsConfederation" then
      ctx = {
        confederation = function() return BY_NAME[ev.instigator] end,
        faction = function() return BY_NAME[ev.victim] end,
      }
    else
      ctx = {
        character = function()
          return {
            is_null_interface = function() return BY_NAME[ev.instigator] == nil end,
            faction = function() return BY_NAME[ev.instigator] end,
          }
        end,
        garrison_residence = function()
          return {
            is_null_interface = function() return BY_NAME[ev.victim] == nil end,
            faction = function() return BY_NAME[ev.victim] end,
            region = function() return REGIONS[ev.region] or region(ev.region, {}) end,
          }
        end,
      }
    end
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
  local v = SAVED[k]
  -- A table's tostring is its ADDRESS, which no assertion can use. Emit its length instead, so
  -- a cap on a ring buffer is testable rather than merely present.
  if type(v) == "table" then
    fh:write(k .. "\ttable:" .. #v .. "\n")
  else
    fh:write(k .. "\t" .. tostring(v) .. "\n")
  end
end
fh:close()
'''

# rising, waving from turn 1: six ON turns at the old numbers plus 10 refill, no hot grudge, no
# ambitious factions.
TEST_SEED = {"temperament": "rising", "phase": 0, "hot": [], "ambitious": []}

STATE_KEYS = ["derpy_director_seed", "derpy_director_budget", "derpy_director_cooldowns",
              "derpy_director_news", "derpy_director_last_tier", "derpy_director_merge_count"]


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
        for flag in ("dead", "rebel", "human", "throws"):
            if f.get(flag):
                parts.append("%s = true" % flag)
        # met absent = met everyone; an EMPTY met list is a real case (met nobody), so it is
        # emitted whenever the key is present.
        for lst in ("owns", "wars", "allies", "military", "bundles"):
            if f.get(lst):
                parts.append("%s = %s" % (lst, _lua(f[lst])))
        if "met" in f:
            parts.append("met = %s" % _lua(f["met"]))
        if f.get("vassal_of"):
            parts.append("vassal_of = %s" % _lua(f["vassal_of"]))
        # {other_faction_key: attitude}. Absent means 0, which leaves the live-attitude term
        # inert and the score exactly as the lore matrix set it.
        if f.get("attitudes"):
            parts.append("attitudes = %s" % _lua(f["attitudes"]))
        rows.append("{" + ", ".join(parts) + "}")
    return "{" + ", ".join(rows) + "}"


def _regions_table(regions):
    rows = []
    for r in regions or []:
        # pos defaults to a real point so every fixture exercises the LOCATED call; give a
        # region pos=None explicitly to model one with no settlement.
        pos = r["pos"] if "pos" in r else [100, 200]
        rows.append("{key = %s, adj = %s, pos = %s}" % (
            _lua(r["key"]), _lua(r.get("adj", [])), _lua(pos)))
    return "{" + ", ".join(rows) + "}"


def _events_table(events):
    rows = []
    for e in events:
        # turn is OPTIONAL and defaults to one event per turn. Give several events the same
        # turn to model a burst - the live game produced nine sacks on turn 65 alone, and a
        # harness that advances a turn per event can never reproduce that contention.
        rows.append(
            "{event = %s, instigator = %s, victim = %s, region = %s, turn = %s, reason = %s, "
            "stale = %s, treaty = %s, n = %s, code = %s, met = %s}"
            % (_lua(e["event"]), _lua(e.get("instigator")), _lua(e.get("victim")),
               _lua(e.get("region")), _lua(e.get("turn")), _lua(e.get("reason")),
               _lua(e.get("stale", False)), _lua(e.get("treaty")), _lua(e.get("n")),
               _lua(e.get("code")), _lua(e.get("met"))))
    return "{" + ", ".join(rows) + "}"


def run_lua(factions, events=None, disable=False, preload=None, seed=1,
            regions_spec=None, scores=None, companions=None, mct=None, multiplayer=False,
            deny=None, payload_error=False, script_state=None, quiet_runaway=True):
    """Run the SHIPPED Lua under the harness. Returns (calls, state).

    quiet_runaway (default True) installs MCT with the runaway step's threat score, grudge and
    alliances and both confederation triggers switched OFF, under any `mct` given. The groups
    written before 2026-11-14 measure situations in worlds where one faction holds 20 regions
    against 3 - a runaway by the rules - and count grudges, asks and pacts that the runaway step
    and the merges would add to. The groups that test those features pass quiet_runaway=False.

    mct: {option key: value} installs MCT holding those finalized values; absent, there is no
    get_mct at all. multiplayer: cm:is_multiplayer() answers true. deny: ["a|b"] makes
    cai_evaluate_quick_deal_action(a, b, *) answer ok=false. payload_error: cm:apply_payload raises.
    script_state: {key: bool} for shared_states_manager():get_state_as_bool_value.

    companions: {"ro": True, "gg": True, "gg_held": n, "ic": True, "ic_missing": call} installs
    stand-ins for Resource Overhaul, the Great Guilds and the Iron Court; absent, none of the
    globals exists, as in a game without them.

    seed is every cm:random_number result (clamped into its range), or a list of them in order.
    The default 1 makes every chance succeed and every weighted draw take the top candidate, so
    the groups written before the storyteller still measure what they were written for; so does
    TEST_SEED, preloaded unless a test brings its own derpy_director_seed (False rolls a new one).
    """
    preload = dict(preload or {})
    preload.setdefault("derpy_director_seed", TEST_SEED)
    if quiet_runaway:
        mct = dict({"runaway_threat": False, "runaway_alliances": False,
                    "merge_runaway": False, "merge_last_stand": False}, **(mct or {}))
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
            "PRELOAD = %s\nDUMP_PATH = %s\nSTATE_KEYS = %s\nSEED_ROLL = %s\n"
            "REGION_SPECS = %s\nSCORES = %s\nCOMPANIONS = %s\nMCT_VALUES = %s\n"
            "MULTIPLAYER = %s\nDENY = %s\nPAYLOAD_ERROR = %s\nSCRIPT_STATE = %s\n" % (
                _lua(script), _lua(lore_path), _faction_table(factions),
                _events_table(events or []), _lua(preload or {}), _lua(dump),
                _lua(STATE_KEYS), _lua(seed), _regions_table(regions_spec),
                _lua(scores or {}), _lua(companions or {}),
                _lua(mct) if mct is not None else "nil", _lua(bool(multiplayer)),
                _lua({k: True for k in (deny or [])}), _lua(bool(payload_error)),
                _lua(script_state or {})))
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
    # The columns are float32. A cache refreshed through RPFM 5.3 widens them (0.1 becomes
    # 0.10000000149011612), which made the baked file look stale with no value changed. Six
    # significant digits is past float32's precision, so the bake is the same on either cache.
    def f32(v):
        return float("%.6g" % v)
    lookup = {}
    for r in rows:
        lookup.setdefault(r["source"], {})[r["target"]] = (
            f32(r["attitude_base"]), f32(r["negative_attitude_multiplier"]),
            f32(r["positive_attitude_multiplier"]))
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

    # The feed index map, generated beside the lore so the Lua and the DB rows cannot drift.
    # Only the INDEX needs a lookup: the loc keys are pure concatenation and the Lua builds them.
    lines += [
        "",
        "-- Which event_feed_message_events index carries each culture's message. Generated from",
        "-- the same table as the DB rows, so the two cannot disagree. A subculture that is not",
        "-- here falls back to the generic pair.",
        "derpy_director_feed_index = {",
    ]
    for kind in sorted(FEED_BASE):
        cells = []
        for r in culture_records():
            if r["key"].startswith(kind + "_"):
                cells.append("\t\t[%s] = %d," % (_lua(r["key"][len(kind) + 1:]), r["index"]))
        lines.append("\t[%s] = {" % _lua(kind))
        lines += cells
        lines.append("\t},")
    lines.append("}")

    # The MCT defaults and the races that have a switch, from MCT_OPTIONS and merge_races(), the
    # same source mct_page() writes the page from.
    lines += [
        "",
        "-- The Director's MCT defaults, generated from the list that also writes the page, so the",
        "-- page and the reader cannot disagree. derpy_director:setting() falls back on these.",
        "derpy_director_mct_defaults = {",
    ]
    for o in MCT_OPTIONS:
        lines.append("\t[%s] = %s," % (_lua(o["key"]), _lua(o["default"])))
    lines += ["}", "", "-- Every race that has a race_<subculture> switch, each on by default.",
              "derpy_director_merge_races = {"]
    for sc, _name in merge_races():
        lines.append("\t[%s] = true," % _lua(sc))
    lines.append("}")
    return "\n".join(lines) + "\n"


def _group(key):
    return "%s_%s" % (FRAG, key)


def _loc_key(key, part):
    return "event_feed_strings_text_%s_%s_%s" % (FRAG, key, part)


def _art(subculture, kind):
    """`<race>/diplomacy` where it exists, else `<race>/faction`, which all 24 races ship.

    The race prefix is DERIVED from the subculture key rather than typed: every real subculture
    is <game>_<...>_sc_<race>_<name>. A typed map went stale the moment a prologue subculture
    turned up.
    """
    if "_sc_" not in subculture:
        return "all/elector_confederation" if kind == "pact" else "all/carnage_weapons"
    race = subculture.split("_sc_", 1)[1].split("_")[0]
    race = ART_ALIAS.get(race, race)
    return "%s/%s" % (race, "diplomacy" if race in ART_DIPLOMACY else "faction")


# Read once off the shipped ui pack rather than typed: four races (kho, nur, sla, tze) have no
# diplomacy picture and every one of the 24 has a faction picture.
ART_DIPLOMACY = {
    "brt", "bst", "chd", "chs", "cst", "cth", "dae", "def", "dwf", "emp", "grn", "hef",
    "ksl", "lzd", "nor", "ogr", "skv", "tmb", "vmp", "wef",
    "nag",  # 9.0: ui/eventpics/nag/diplomacy.png in ui2.pack
}

# The base IS the generic row's index, and the per-culture rows run from base + 1.
# The generic pair was hardcoded 7301/7302 from before per-culture rows existed, so
# when culture_records() began numbering at base + 1 it walked straight over it:
# generic grudge collided with the first culture grudge and generic pact with the
# second. Both shipped. A duplicate criteria value is not a load reject - there is no
# bad_mods_report entry for it - the engine just resolves the index to whichever row
# it finds and draws the wrong card. check_feed() now refuses to build on a repeat.
FEED_BASE = {"grudge": 7300, "pact": 7400}


def culture_records():
    """One (grudge, pact) pair per subculture that has flavour, in a stable sorted order.

    The index is FEED_BASE[kind] + the culture's position in that sorted list, so it is derived
    from the data and cannot drift the way a hand-numbered list does.
    """
    out = []
    for n, sc in enumerate(sorted(CULTURE_FLAVOUR), start=1):
        title, react = CULTURE_FLAVOUR[sc]
        name = "{{tr:cultures_subcultures_name_%s}}" % sc
        out.append({
            "key": "grudge_%s" % sc, "index": FEED_BASE["grudge"] + n,
            "image": _art(sc, "grudge"), "icon": "event_gen_news_negative.png",
            "sound": "UI_CAM_POPUP_Message_Event_Negative",
            "title": title,
            "primary": "A settlement has been attacked. The %s have taken note. They already "
                       "counted the attacker an enemy, and their opinion of them has now "
                       "worsened." % name,
            "secondary": react,
        })
        out.append({
            "key": "pact_%s" % sc, "index": FEED_BASE["pact"] + n,
            "image": _art(sc, "pact"), "icon": "event_gen_news_positive.png",
            "sound": "UI_CAM_POPUP_Message_Event_Positive",
            "title": "Common Cause",
            "primary": "The %s have signed a defensive alliance with another power that "
                       "shares their enemy. Each will now answer if the other is "
                       "attacked." % name,
            "secondary": FEED_ROWS[1]["secondary"],
        })
    return out


def all_feed_rows():
    """The generic pair FIRST, then the per-culture ones.

    The generic pair is the fallback for a subculture nothing ships a record for - a modded race,
    or a rogue army. Without it an unknown culture would draw nothing at all, which is the exact
    silent failure this whole subsystem keeps producing.
    """
    return FEED_ROWS + culture_records()


def feed_rows():
    """{table: [row dicts]} plus the loc rows, so one place decides what ships."""
    groups, members, values, events, strings, loc = [], [], [], [], [], []
    for r in all_feed_rows():
        g = _group(r["key"])
        groups.append({"id": g})
        # group and id are the SAME key on a single-member group; the criteria row then hangs
        # off the member, and its `value` IS the index the script passes.
        members.append({"group": g, "id": g, "priority": "0.0"})
        values.append({"member": g, "value": str(r["index"])})
        events.append({
            # scripted_transient_LOCATED_event, not scripted_transient_event. event_feed_targeted
            # _events declares four scripted types, and the two plain ones carry
            # located = event_feed_none while the two _located_ ones carry
            # event_feed_location_position. The record type is what has to match the CALL: a
            # plain record raised through show_message_event_located resolves, logs a line that
            # reads like success, and puts nothing in the feed. Measured 2026-09-17 - six calls,
            # six log lines, nothing on screen. 21 vanilla rows use this type; only 4 use the
            # plain one. context_located stays event_feed_none - all 21 do, the location
            # capability comes from `event` and not from that column.
            "event": "scripted_transient_located_event",
            "flavour_text": "wh_event_feed_string_all_null",
            "group": g,
            "image": r["image"],
            "secondary_detail": "wh_event_feed_string_scripted_event_secondary_detail",
            "target": "event_feed_target_faction",
            "layout": "standard",
            "layout_data": "event_feed_none",
            "sound_event": r["sound"],
            "context_located": "event_feed_none",
            "override_icon": r["icon"],
            "instant_open": "false",
            "ignore_instant_open_filters": "false",
        })
        # An empty secondary draws an EMPTY PLATE rather than collapsing the slot - the panel
        # reserves the box whatever the script passes, so a blank string is a visible defect and
        # not a tidy omission. Seen on screen 2026-09-17.
        for part in ("title", "primary", "secondary"):
            strings.append({"key": "%s_%s_%s" % (FRAG, r["key"], part)})
            loc.append({"key": _loc_key(r["key"], part), "text": r[part], "tooltip": "false"})
    return {
        "campaign_groups": groups,
        "campaign_group_members": members,
        "campaign_group_member_criteria_values": values,
        "event_feed_message_events": events,
        "event_feed_strings": strings,
    }, loc


FEED_FIELDS = {
    "campaign_groups": ["id"],
    "campaign_group_members": ["group", "id", "priority"],
    "campaign_group_member_criteria_values": ["member", "value"],
    "event_feed_message_events": [
        "event", "flavour_text", "group", "image", "secondary_detail", "target", "layout",
        "layout_data", "sound_event", "context_located", "override_icon", "instant_open",
        "ignore_instant_open_filters"],
    "event_feed_strings": ["key"],
}


def write_feed_tsvs():
    """Write the five table TSVs and the loc TSV. Returns the import plan."""
    from rpfm_client import db
    if not os.path.isdir(TSV_DIR):
        os.makedirs(TSV_DIR)
    tables, loc = feed_rows()
    plan = []
    for table, ver in FEED_TABLES:
        fields = FEED_FIELDS[table]
        name = "%s__%s.tsv" % (table, FRAG)
        path = os.path.join(TSV_DIR, name)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write("\t".join(fields) + "\n")
            fh.write("#%s_tables;%d;db/%s_tables/%s\n" % (table, ver, table, FRAG))
            for row in tables[table]:
                fh.write("\t".join(row[f] for f in fields) + "\n")
        plan.append(("db/%s_tables/%s" % (table, FRAG), db("%s_tables" % table, ver), path))

    path = os.path.join(TSV_DIR, "loc__%s.tsv" % FRAG)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("key\ttext\ttooltip\n")
        fh.write("#Loc;1;text/db/%s.loc\n" % FRAG)
        for row in loc:
            fh.write("%s\t%s\t%s\n" % (row["key"], row["text"], row["tooltip"]))
    plan.append(("text/db/%s.loc" % FRAG, {"type": "loc"}, path))
    return plan


def check_feed():
    """The Lua and the DB must agree on every index and every loc key.

    They are written in two files in two languages and nothing in the engine cross-checks them:
    a wrong index draws NOTHING and logs a line that looks like success, and a loc key with no
    row behind it draws the key itself. Both are silent-forever faults, so they are compared
    here instead.
    """
    src = open(SCRIPT, encoding="utf-8").read()
    _tables, loc = feed_rows()

    # Every index must be unique across ALL rows, generic and per-culture together. The index is
    # the `value` on a campaign_group_member_criteria_values row and it is what the script passes
    # to show_message_event_located; the engine resolves it to whichever member carries that
    # value, so two rows sharing one index means one of them can never be reached and the other
    # draws for both. Nothing reports it - there is no bad_mods_report entry, the DB loads
    # cleanly, and the feed simply shows the wrong card. It shipped that way from the moment
    # culture_records() was added on 2026-09-17 until 2026-09-18: generic grudge sat on 7301
    # against the first culture grudge, and generic pact on 7302 against the second.
    seen = {}
    for r in all_feed_rows():
        clash = seen.get(r["index"])
        assert clash is None, (
            "duplicate feed index %d: %r and %r. The index is a criteria VALUE, so the engine "
            "resolves it to one of them and the other is unreachable." % (r["index"], clash,
                                                                          r["key"]))
        seen[r["index"]] = r["key"]

    for r in FEED_ROWS:
        assert "index = %d," % r["index"] in src, \
            "the Lua does not carry index %d for %s" % (r["index"], r["key"])
    # The Lua no longer names each loc key literally - it CONCATENATES stem + kind + subculture +
    # part, so what has to be checked is that its construction rule reproduces exactly the key
    # set that ships. A key the Lua can build but nothing ships draws the raw key on screen; one
    # that ships but the Lua can never build is dead weight nobody sees.
    stem = re.search(r'local LOC_STEM = "([^"]+)"', src)
    assert stem, "LOC_STEM has moved - this check can no longer rebuild the Lua's keys"
    stem = stem.group(1)
    assert stem == "event_feed_strings_text_%s_" % FRAG, stem
    for part in ("title", "primary", "secondary"):
        assert '"_%s"' % part in src or '.. "%s"' % part in src, \
            "the Lua never builds the _%s suffix" % part

    buildable = set()
    for kind in sorted({r["key"] for r in FEED_ROWS}):
        cultures = sorted(CULTURE_FLAVOUR) if kind in FEED_BASE else []
        for suffix in [""] + ["_" + sc for sc in cultures]:
            for part in ("title", "primary", "secondary"):
                buildable.add("%s%s%s_%s" % (stem, kind, suffix, part))
    shipped = {row["key"] for row in loc}
    assert shipped == buildable, (
        "the shipped loc keys and the keys the Lua can build disagree: %d only shipped, "
        "%d only buildable" % (len(shipped - buildable), len(buildable - shipped)))

    # The generated index map in the lore file must carry exactly the indices the DB rows carry.
    # It is a second copy of the same numbers in a second language; nothing in the engine would
    # report them drifting apart, the message would simply stop drawing.
    if os.path.exists(LORE):
        lore_src = open(LORE, encoding="utf-8").read()
        for r in culture_records():
            kind, sc = r["key"].split("_", 1)
            assert re.search(r'\["%s"\]\s*=\s*%d\b' % (re.escape(sc), r["index"]), lore_src), \
                ("derpy_director_lore.lua has no %s entry for %s at index %d - run "
                 "--check to regenerate it" % (kind, sc, r["index"]))
    # The record TYPE and the CALL must agree, and nothing in the engine checks it. A plain
    # scripted_transient_event raised through show_message_event_located resolved fine, logged a
    # line that read like success and drew nothing - six times in one live session on
    # 2026-09-17. event_feed_targeted_events declares four scripted types and the `located` half
    # of the pair is not interchangeable with the plain half.
    # No loc argument may be blank. The panel reserves a plate for the secondary detail whatever
    # the script passes, so "" draws an empty black box under the body rather than collapsing the
    # slot - which is what shipped on 2026-09-17 and showed up in a screenshot.
    call = re.search(r"cm:show_message_event_located\((.*?)\)", src, re.S)
    assert call, "the located call has moved - this check no longer reads the real arguments"
    args = [a.strip() for a in call.group(1).split(",")]
    for i, name in ((1, "title"), (2, "primary"), (3, "secondary")):
        assert args[i] and args[i] != '""', \
            "the %s argument is blank - the panel draws an empty plate, not nothing" % name
    for r in FEED_ROWS:
        for part in ("title", "primary", "secondary"):
            assert r.get(part), "%s has no %s text" % (r["key"], part)

    located_call = "cm:show_message_event_located(" in src
    plain_call = re.search(r"cm:show_message_event\(", src) is not None
    for row in _tables["event_feed_message_events"]:
        is_located_row = "_located_" in row["event"]
        assert is_located_row == located_call, (
            "the record is %s but the Lua %s show_message_event_located - a mismatched pair "
            "draws nothing at all" % (row["event"], "uses" if located_call else "does not use"))
        assert not (is_located_row and plain_call), (
            "a located record cannot be raised through the plain call: %s" % row["event"])

    indices = [r["index"] for r in FEED_ROWS]
    assert len(set(indices)) == len(indices), "two feed records share an index: %s" % indices
    assert min(indices) > 1960, \
        "vanilla's highest event index is 1960 - %d may collide" % min(indices)


def check():
    """Regenerate the lore file and confirm every shipped Lua file still parses. No RPFM."""
    open(LORE, "w", encoding="utf-8", newline="\n").write(build_lore())
    print("wrote %s" % LORE)
    os.makedirs(os.path.dirname(MCT_PAGE), exist_ok=True)
    open(MCT_PAGE, "w", encoding="utf-8", newline="\n").write(mct_page())
    print("wrote %s" % MCT_PAGE)
    for path in (SCRIPT, LORE, MCT_PAGE):
        r = subprocess.run([LUAC, "-p", path], capture_output=True, text=True)
        assert r.returncode == 0, "luac failed on %s:\n%s" % (path, r.stdout + r.stderr)
    check_feed()
    plan = write_feed_tsvs()
    print("wrote %d feed TSVs to %s" % (len(plan), TSV_DIR))
    print("check ok - lore and MCT page regenerated, feed rows written, every file parses")


NAG = "wh3_dlc29_sc_nag_undead_legions"


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

    # 3. The lore file is present, complete, and carries CA's measured values. These two are the
    # spec's section 4 table: if CA changes them in a patch, this fails rather than silently
    # changing how the Director casts.
    src = open(LORE, encoding="utf-8").read()
    assert "derpy_director_lore" in src, "lore global missing"
    run_lua([{"name": "a", "regions": 1, "subculture": "wh_main_sc_dwf_dwarfs"}],
            events=[{"event": "probe_lore"}])
    rows, _ = load_cache()
    # 675 through 8.x; 9.0 added 51 pairs for Nagash's subculture and changed none of the rest.
    assert len(rows) == 726, len(rows)
    lookup = {}
    for r in rows:
        lookup.setdefault(r["source"], {})[r["target"]] = (
            r["attitude_base"], r["negative_attitude_multiplier"],
            r["positive_attitude_multiplier"])
    dwf = lookup["wh_main_sc_dwf_dwarfs"]
    assert dwf["wh_main_sc_dwf_dwarfs"] == (0.0, 1.0, 1.0), dwf["wh_main_sc_dwf_dwarfs"]
    chd = dwf["wh3_dlc23_sc_chd_chaos_dwarfs"]
    assert chd[0] == -100.0 and chd[1] == 2.0 and abs(chd[2] - 0.1) < 1e-6, chd
    # Nagash is a source AND a target, so he can be cast and his deeds are scored.
    assert lookup[NAG]["wh3_dlc23_sc_chd_chaos_dwarfs"][0] == -100.0, lookup[NAG]
    assert lookup["wh3_dlc23_sc_chd_chaos_dwarfs"][NAG][0] == -40.0
    assert '["%s"] = {' % NAG in src, "the shipped lore has no row for Nagash"

    # 4. The SHIPPED lore file matches the cache. A stale bake is a failure, not a surprise.
    assert src == build_lore(), "derpy_director_lore.lua is stale - run --check to regenerate"
    print("selftest: lore bake ok")

    # 5. A fired event becomes a situation with key STRINGS, and the log records it.
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

    # 7. Cast selection scores on hatred of the INSTIGATOR. Dwarfs hate Chaos Dwarfs at -100;
    # Greenskins are neutral toward them (0) and are not cast.
    CHD = "wh3_dlc23_sc_chd_chaos_dwarfs"
    DWF = "wh_main_sc_dwf_dwarfs"
    # The ONLY subcultures neutral toward Chaos Dwarfs are the Chaos-aligned ones - everybody
    # else is at -100, Greenskins included (they are the mine slaves). Read off the table, not
    # assumed: a fixture that guessed Greenskins were neutral failed here.
    CHS = "wh_main_sc_chs_chaos"
    world = [
        {"name": "sacker", "regions": 20, "subculture": CHD},
        # CHD sacking its OWN culture: kinslaying, so outrage is at its maximum and the cast is
        # the full three. This group tests WHO is cast, so the audience must not be narrowed by
        # the outrage scale - CHD sacking Dwarfs is -100, sworn enemies, and draws only one.
        {"name": "victim", "regions": 5, "subculture": CHD},
        {"name": "hold_a", "regions": 6, "subculture": DWF},
        {"name": "hold_b", "regions": 6, "subculture": DWF},
        {"name": "neutral_chs", "regions": 6, "subculture": CHS},
        {"name": "player", "regions": 6, "subculture": DWF, "human": True},
    ]
    ev = [{"event": "CharacterSackedSettlement", "instigator": "sacker",
           "victim": "victim", "region": "r1"}]
    # Everyone owns a region adjacent to the sacked one, so this fixture isolates the HATRED
    # term: proximity and safety are held equal and only the cultural score can differ.
    # The SACKER is in reach too, deliberately: ten subcultures have a NEGATIVE self-attitude
    # (Chaos Dwarfs worst at -15), so without the instigator guard the sacker casts itself into
    # its own punishment. A fixture that left the sacker out of reach could not catch that.
    adjacent = [{"key": "r1", "adj": ["r2"]}, {"key": "r2", "adj": ["r1"]}]
    for f in world:
        f["owns"] = ["r2"]
    # A dead faction that would otherwise qualify on every other term.
    world.append({"name": "dead_hold", "regions": 6, "subculture": DWF, "owns": ["r2"],
                  "dead": True})
    calls, _ = run_lua(world, events=ev, regions_spec=adjacent)
    cast = [c for c in calls if c[0] == "out" and c[1].find("cast ") == len("[director] ")]
    assert cast, calls
    line = cast[0][1]
    assert "hold_a" in line and "hold_b" in line, line
    assert "neutral_chs" not in line, line
    # The human is NEVER a candidate. cai_evaluate_quick_deal_action asks what the AI would
    # accept and a human faction has no AI to ask; the force beats are unrefusable.
    assert "player" not in line, line
    # The victim is not cast for its own rescue, and the instigator is never cast - even though
    # Chaos Dwarfs are at -15 toward their own kind and the sacker is in reach.
    assert "victim" not in line and "sacker" not in line, line
    assert "dead_hold" not in line, line
    print("selftest: cast selection ok")

    # 7a. The cast sort has a total order. hold_b is listed BEFORE hold_a in the world, and the
    # two are identical on every term, so only the name tiebreak can put hold_a first. Without
    # it the sort leaves them in input order.
    tie_world = [
        {"name": "sacker", "regions": 20, "subculture": CHD, "owns": ["r2"]},
        # Kinslaying again, so the cast is three and both holds fit in it - a two-name tiebreak
        # cannot be read from a cast of one.
        {"name": "victim", "regions": 5, "subculture": CHD, "owns": ["r2"]},
        {"name": "hold_b", "regions": 6, "subculture": DWF, "owns": ["r2"]},
        {"name": "hold_a", "regions": 6, "subculture": DWF, "owns": ["r2"]},
    ]
    calls, _ = run_lua(tie_world, events=ev, regions_spec=adjacent)
    tie_line = [c[1] for c in calls if c[0] == "out"
                and c[1].find("cast ") == len("[director] ")][0]
    assert tie_line.index("hold_a") < tie_line.index("hold_b"), tie_line

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
        {"name": "victim", "subculture": CHD, "owns": ["r_victim"], "regions": 3},
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
        {"name": "victim", "subculture": CHD, "owns": ["r_victim"], "regions": 3},
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

    # 7d. Nagash (9.0). His subculture hates Chaos Dwarfs at -100, so a Nagash neighbour answers
    # a Chaos Dwarf kinslaying - but only because the regenerated lore carries his row; without
    # it hatred() is neutral and he is never cast. The grudge then speaks in his own voice.
    # The player is the victim: only a party to the deed is told.
    nag_world = [
        {"name": "sacker", "regions": 20, "subculture": CHD},
        {"name": "victim", "subculture": CHD, "owns": ["r_victim"], "regions": 3,
         "human": True},
        {"name": "nag_hold", "subculture": NAG, "owns": ["r_near"], "regions": 3},
    ]
    calls, _ = run_lua(nag_world, events=ev2, regions_spec=regions)
    line = [c[1] for c in calls if c[0] == "out"
            and c[1].find("cast ") == len("[director] ")][0]
    assert "nag_hold" in line, line
    feed = [c for c in calls if c[0] == "show_message_event_located"]
    assert feed and "_grudge_%s_title" % NAG in feed[0][2], feed
    nag_rec = [r for r in culture_records() if r["key"] == "grudge_" + NAG]
    assert nag_rec and nag_rec[0]["image"] == "nag/diplomacy", nag_rec
    print("selftest: Nagash ok")

    # 8. ask() passes faction INTERFACES (not key strings), asks both directions, and logs the
    # can-propose flags as well as the scores. The Coalition Supervisor produced 44 sessions of
    # logs that could not answer its one open question because it logged scores alone.
    pair_world = [
        {"name": "sacker", "regions": 20, "subculture": CHD},
        {"name": "victim", "subculture": CHD, "owns": ["r_victim"], "regions": 3},
        {"name": "hold_a", "subculture": DWF, "owns": ["r_near"], "regions": 3},
        {"name": "hold_b", "subculture": DWF, "owns": ["r_near"], "regions": 3},
    ]
    yes = {"hold_a|hold_b": 5, "hold_b|hold_a": 5}
    calls, _ = run_lua(pair_world, events=ev2, regions_spec=regions, scores=yes)
    asked = [(c[1], c[2]) for c in calls if c[0] == "cai_evaluate_quick_deal_action"]
    assert ("hold_a", "hold_b") in asked, asked
    assert ("hold_b", "hold_a") in asked, asked
    ask_line = [c[1] for c in calls if c[0] == "out" and "ask " in c[1]]
    assert ask_line and "ok=" in ask_line[0], ask_line

    # 9. The mood beat pushes a STANCE, one per responder, aimed AT the instigator - so the
    # direction is responder -> aggressor and never the reverse. A situation never touches the
    # global threat score: since the Coalition Supervisor merged in (2026-11-14) the runaway step
    # is its only writer, and the harness switches that step off for these older groups.
    stances = [c for c in calls if c[0] == "stance_promote"]
    assert stances, calls
    for c in stances:
        assert c[2] == "sacker", "the stance must point at the aggressor, got %s" % (c,)
        assert c[1] != "sacker", "the aggressor must not be pushed against itself: %s" % (c,)
        assert c[3] == "CAI_STRATEGIC_STANCE_VERY_UNFRIENDLY", c
    assert not [c for c in calls if c[0] == "set_base_strategic_threat_score"], \
        "only the runaway step may set the threat score"
    print("selftest: cheap beats ok")

    # 10. A pact forms on the SUM of the two evaluations, not on both halves separately.
    # cai_evaluate_quick_deal_action is directional and the two directions disagree hard - the
    # same pair scored -14.93 one way and +5.72 the other in live play. Measured over 151 live
    # evaluations on 2026-09-17, the best min(sa, sb) ever seen was -1.12, so the both-above-zero
    # gate this replaced had never once opened and force, tell, warchest and shield were all
    # unreachable in play. All three cases below are asserted: two keen sides, one keen side
    # carrying the other's doubts, and a pair that between them want it less than not.
    forced = [(c[1], c[2], c[3]) for c in calls if c[0] == "force_alliance"]
    assert forced == [("hold_a", "hold_b", "false")], forced

    one_sided = {"hold_a|hold_b": 5, "hold_b|hold_a": -1}
    calls2, _ = run_lua(pair_world, events=ev2, regions_spec=regions, scores=one_sided)
    assert [c for c in calls2 if c[0] == "force_alliance"], \
        "sum +4 is a pact: one side is keen enough to carry the other's doubts"

    net_against = {"hold_a|hold_b": 5, "hold_b|hold_a": -9}
    calls2b, _ = run_lua(pair_world, events=ev2, regions_spec=regions, scores=net_against)
    assert not [c for c in calls2b if c[0] == "force_alliance"], calls2b

    # 11. The past event fires for the STRONGEST responder only, from the INSTIGATOR, and never
    # twice for the same feud. It has NO inverse - accumulated attitude damage stays for the
    # campaign - so a repeat is permanent over-punishment that nothing can undo.
    # TWO masks had to be removed before this assertion tested what it claims to. The budget is
    # preloaded high because at the shipping budget the past event is priced out after turn 1,
    # and the run is 20 turns long because the 12-turn per-faction cooldown empties the cast
    # from turn 2 to turn 12 - either one alone makes the assertion pass whether or not the
    # once-per-situation guard exists. Past turn 12 the cast returns, so only the seen_key guard
    # can still keep the count down. Both masks were found by mutate_director.py, not by reading.
    calls3, _ = run_lua(pair_world, events=ev2 * 20, regions_spec=regions, scores=yes,
                        preload={"derpy_director_budget": 100000})
    fired = [c for c in calls3 if c[0] == "cai_add_diplomatic_event"]
    assert all(e[1] == "sacker" for e in fired), fired
    assert all(e[3] == "PAST_EVENT_NEGATIVE_MINOR" for e in fired), fired
    assert len(fired) == 1, fired   # cast[1] only, from the FIRST sack only
    assert fired[0][2] == "hold_a", fired    # the head of the cast, not an arbitrary member

    # 11b. One feud is answered once a turn, however many regions it takes. A province falling
    # arrives as one event per REGION: qb2 taking the Conclave billed 13 situations in one turn
    # on 2026-09-17 and emptied the budget before the turn's other 17 situations were read. The
    # situation is still LOGGED each time - only the beats are withheld - so the assertion counts
    # stance pushes and not log lines. Budget preloaded high so that starvation cannot be what
    # holds the count down; without the guard this is 4 stance pushes, not 2.
    burst = [dict(ev2[0], turn=3) for _ in range(4)]
    calls4, _ = run_lua(pair_world, events=burst, regions_spec=regions, scores=yes,
                        preload={"derpy_director_budget": 100000})
    assert len([c for c in calls4 if c[0] == "out" and "situation" in c[1]]) == 4, calls4
    assert len([c for c in calls4 if c[0] == "stance_promote"]) == 2, \
        [c for c in calls4 if c[0] == "stance_promote"]

    # 11c. The world acquires at most one permanent grudge a turn, across DIFFERENT feuds. The
    # BUDGET_START comment claimed this rationing since 2026-09-17 while the code fired one
    # past event per cast member; three responders cost 120 of a 180 budget on the single beat
    # with no inverse, and replaying 26 live logs it starved 14 of the 24 situations that drew an
    # audience out of even the 5-cost stance push. Two victims, one turn, one grudge - and the
    # budget is preloaded high so that the quota is the only thing that can hold it to one.
    feud_world = pair_world + [{"name": "victim2", "subculture": CHD,
                                "owns": ["r_victim"], "regions": 3}]
    two_feuds = [dict(ev2[0], turn=3), dict(ev2[0], turn=3, victim="victim2")]
    calls5, _ = run_lua(feud_world, events=two_feuds, regions_spec=regions, scores=yes,
                        preload={"derpy_director_budget": 100000})
    assert len([c for c in calls5 if c[0] == "out" and "situation" in c[1]]) == 2, calls5
    assert len([c for c in calls5 if c[0] == "cai_add_diplomatic_event"]) == 1, \
        [c for c in calls5 if c[0] == "cai_add_diplomatic_event"]

    # 11d. A feud the quota turned away must not be burnt permanently. seen_key used to be set
    # whichever way the spend went, so a feud that arrived on a turn the world had already spent
    # its grudge was marked answered forever and never got one at all - a permanent consequence
    # of a transient shortage. Same two feuds on turn 3, then the turned-away one again on turn
    # 4: two grudges, not one. This is why 11c cannot simply be extended by a turn - both the
    # quota and the burn produce the same TOTAL, and only the turn they land on tells them apart.
    calls6, _ = run_lua(feud_world, events=two_feuds + [dict(ev2[0], turn=4, victim="victim2")],
                        regions_spec=regions, scores=yes,
                        preload={"derpy_director_budget": 100000})
    assert len([c for c in calls6 if c[0] == "cai_add_diplomatic_event"]) == 2, \
        [c for c in calls6 if c[0] == "cai_add_diplomatic_event"]

    # 12. The feed. A world with no human faction cannot address a message to anybody, so
    # nothing may draw - the same assertion this group used to make for the whole of phase 1.
    assert not [c for c in calls3 if c[0].startswith("show_message_event")], \
        "there is no player in this fixture - the message has no addressee"

    # The player as VICTIM is told, and the message is LOCATED at the sacked region, transient,
    # and carries the index the DB actually ships. Each of those four is a silent failure on its
    # own: a persistent flag at a transient record draws nothing, an unbacked index draws nothing
    # and logs a line that reads like success, and a loc key with no row draws the raw key.
    feed_world = [
        {"name": "sacker", "regions": 20, "subculture": CHD},
        {"name": "victim", "subculture": CHD, "owns": ["r_victim"], "regions": 3,
         "human": True},
        {"name": "hold_a", "subculture": DWF, "owns": ["r_near"], "regions": 3},
        {"name": "hold_b", "subculture": DWF, "owns": ["r_near"], "regions": 3},
    ]
    located = [{"key": "r_victim", "adj": ["r_near"], "pos": [640, 480]},
               {"key": "r_near", "adj": ["r_victim", "r_mid"]},
               {"key": "r_mid", "adj": ["r_near"]}]
    feed_calls, _ = run_lua(feed_world, events=ev2, regions_spec=located, scores=yes)
    shown = [c for c in feed_calls if c[0].startswith("show_message_event")]
    assert shown, feed_calls
    assert all(c[0] == "show_message_event_located" for c in shown), \
        "the region point was read, so every message must carry its zoom-to location"
    grudge = [c for c in shown if "grudge" in c[2]]
    assert grudge, shown
    assert grudge[0][1] == "victim", "addressed to the player, not to a faction in the story"

    # The message speaks in the LEAD responder's voice. hold_a and hold_b are Dwarfs, so the
    # Dwarf record is the one that draws - its own index, its own loc keys, its own artwork -
    # and not the generic pair. Both are derived from the same table the rows are, so a
    # renumbering moves the assertion with the data instead of breaking it.
    want = [r for r in culture_records() if r["key"] == "grudge_" + DWF][0]
    assert grudge[0][2] == "%sgrudge_%s_title" % (
        "event_feed_strings_text_%s_" % FRAG, DWF), grudge[0]
    assert grudge[0][3] == "640,480|false|%d" % want["index"], grudge[0]
    assert want["image"] == "dwf/diplomacy", want
    assert want["index"] != FEED_ROWS[0]["index"], "the culture record must not be the generic one"

    # With a MIXED cast the voice is the lead responder's, not just any member's. Both holds in
    # the fixture above are Dwarfs, so it cannot tell lead from last - and a mutant that read
    # cast[#cast] survived until this case existed. The Cathay hold is given extra wars so its
    # safety term drops it below the Dwarf deterministically rather than by sort luck.
    KSL = "wh3_main_sc_ksl_kislev"
    CTH = "wh3_main_sc_cth_cathay"
    DAE = "wh3_main_sc_dae_daemons"
    mixed = [
        {"name": "sacker", "regions": 20, "subculture": CHD},
        # CHD victim so this is kinslaying and the cast is three - a mixed-culture cast of one
        # cannot show whose voice the message takes.
        {"name": "victim", "subculture": CHD, "owns": ["r_victim"], "regions": 3, "human": True},
        {"name": "hold_a", "subculture": DWF, "owns": ["r_near"], "regions": 3},
        {"name": "zz_cathay", "subculture": CTH, "owns": ["r_near"], "regions": 3,
         "wars": ["sacker", "hold_a", "victim"]},
    ]
    mx_calls, _ = run_lua(mixed, events=ev2, regions_spec=located, scores=yes)
    cast_line = [c[1] for c in mx_calls if c[0] == "out"
                 and c[1].find("cast ") == len("[director] ")][0]
    assert cast_line.index("hold_a") < cast_line.index("zz_cathay"), cast_line
    mx = [c for c in mx_calls if c[0].startswith("show_message_event") and "grudge" in c[2]]
    assert mx, mx_calls
    assert DWF in mx[0][2] and CTH not in mx[0][2], \
        "the message must speak in the LEAD responder's culture, got %s" % (mx[0][2],)

    # A subculture nothing ships a record for falls back to the generic pair rather than drawing
    # nothing, which is what an unknown index would do.
    modded = [dict(f) for f in feed_world]
    for f in modded:
        if f["name"] in ("hold_a", "hold_b"):
            f["subculture"] = "some_mod_sc_invented_people"
    md_calls, _ = run_lua(modded, events=ev2, regions_spec=located, scores=yes)
    md = [c for c in md_calls if c[0].startswith("show_message_event") and "grudge" in c[2]]
    if md:
        assert md[0][3].endswith("|false|%d" % FEED_ROWS[0]["index"]), \
            "an unknown culture must fall back to the generic record, got %s" % (md[0],)
        assert md[0][2] == "event_feed_strings_text_%s_grudge_title" % FRAG, md[0]

    # A pact against the player's attacker is told to the player, never a pact between strangers
    # (the bystander group below).
    pact = [c for c in shown if "pact" in c[2]]
    want_pact = [r for r in culture_records() if r["key"] == "pact_" + DWF][0]
    assert pact and pact[0][3].endswith("|false|%d" % want_pact["index"]), shown

    # A region with no settlement has no point to fly to. Both records are LOCATED types, and
    # CA's wrapper runs is_number() on x and y, so a nil pair script_errors and draws nothing -
    # the situation goes unreported instead.
    unplaced = [dict(r) for r in located]
    unplaced[0] = {"key": "r_victim", "adj": ["r_near"], "pos": None}
    up_calls, _ = run_lua(feed_world, events=ev2, regions_spec=unplaced, scores=yes)
    assert not [c for c in up_calls if c[0].startswith("show_message_event")], \
        "a located record must never be raised without a point"
    assert [c for c in up_calls if c[0] == "out" and "no map point" in c[1]], up_calls
    assert [c for c in up_calls if c[0] == "cai_add_diplomatic_event"], \
        "the beats still run - only the telling is skipped"

    # A grudge the player is only a witness to is NOT news. Until 2026-11-14 the first one a turn
    # was told, and a six-turn soak put six strangers' quarrels over the map; the author's ruling
    # is the Great Guilds' rule, told only when the player is one of the two parties.
    # Four sacks of four different victims, each with its OWN responder in its own isolated
    # region pair, all on one turn. Distinct responders because a shared one goes on cooldown
    # after the first past event and the later situations then cast nobody - which makes the
    # count come out right for entirely the wrong reason. That mask hid this assertion on its
    # first run, and hid two others before it.
    bystander = [{"name": "sacker", "regions": 20, "subculture": CHD},
                 {"name": "watcher", "subculture": DWF, "owns": ["r_mid"], "regions": 3,
                  "human": True}]
    burst_feed, burst_rg = [], [{"key": "r_mid", "adj": []}]
    for i in range(1, 5):
        burst_rg += [{"key": "rb%d" % i, "adj": ["rh%d" % i], "pos": [i, i]},
                     {"key": "rh%d" % i, "adj": ["rb%d" % i]}]
        bystander += [
            {"name": "prey%d" % i, "subculture": CHD, "owns": ["rb%d" % i], "regions": 3},
            {"name": "guard%d" % i, "subculture": DWF, "owns": ["rh%d" % i], "regions": 3}]
        burst_feed.append({"event": "CharacterSackedSettlement", "instigator": "sacker",
                           "victim": "prey%d" % i, "region": "rb%d" % i, "turn": 1})
    by_calls, _ = run_lua(bystander, events=burst_feed, regions_spec=burst_rg, scores=yes)
    told = [c for c in by_calls if c[0].startswith("show_message_event")]
    assert not told, "a witness is told nothing - got %s" % (told,)
    assert [c for c in by_calls if c[0] == "cai_add_diplomatic_event"], \
        "withholding the message must not withhold the beat"
    # The world's one grudge a turn turns the other three away.
    assert len([c for c in by_calls if c[0] == "out"
                and "grudge for this turn is already spent" in c[1]]) == 3, by_calls

    # The same four sacks one turn apart: four grudges land, and the witness still hears of none.
    spread_feed = [dict(e, turn=i + 1) for i, e in enumerate(burst_feed)]
    sp_calls, _ = run_lua(bystander, events=spread_feed, regions_spec=burst_rg, scores=yes)
    assert len([c for c in sp_calls if c[0] == "cai_add_diplomatic_event"]) == 4, sp_calls
    assert not [c for c in sp_calls if c[0].startswith("show_message_event")], sp_calls

    # The player as the AGGRESSOR is a party too. Spread over four turns, so each sack gets its
    # grudge: four grudges, four messages, and every one addressed to the sacker.
    aggressor = [dict(f, human=(f["name"] == "sacker")) for f in bystander]
    ag_calls, _ = run_lua(aggressor, events=spread_feed, regions_spec=burst_rg, scores=yes)
    ag_told = [c for c in ag_calls if c[0].startswith("show_message_event") and "grudge" in c[2]]
    assert len(ag_told) == 4 and all(c[1] == "sacker" for c in ag_told), ag_told

    # The Lua and the shipped DB rows agree on every index and loc key.
    check_feed()

    # ...and check_feed() actually REFUSES a duplicate index. A gate nobody has watched fail
    # proves nothing, and this one was added on 2026-09-18 after the collision it catches had
    # already shipped for a day. Collide the generic grudge with the first culture grudge, which
    # is the exact fault that shipped, and put FEED_ROWS back whatever happens.
    saved_index = FEED_ROWS[0]["index"]
    FEED_ROWS[0]["index"] = FEED_BASE["grudge"] + 1
    try:
        check_feed()
        raise AssertionError("check_feed accepted a duplicate index - the gate is not wired up")
    except AssertionError as e:
        assert "duplicate feed index" in str(e), "wrong failure: %s" % e
    finally:
        FEED_ROWS[0]["index"] = saved_index
    check_feed()
    print("selftest: expensive beats ok")

    # 13. The budget is spent and saved. A world with no budget LEFT IN THE TURN runs no
    # expensive beat, while cheap reads still happen - the budget is a safety mechanism, not an
    # off switch. The refill is per turn, so a budget preloaded to 0 is no longer a way to make
    # the Director broke; spending it inside one turn is.
    calls4, state = run_lua(pair_world, events=ev2, regions_spec=regions, scores=yes)
    assert state["derpy_director_budget"] not in ("nil", "None"), state

    # Distinct victims and responders per situation, all landing on ONE turn. Distinct because a
    # shared responder would go on cooldown after the first past event and a shared victim would
    # be deduplicated by the seen key, either of which empties the later casts and would starve
    # them for a reason that has nothing to do with the budget.
    # Thirty, not twelve. Until 2026-09-18 a permanent grudge fired once per CAST MEMBER with no
    # per-turn cap, so twelve situations drained a 180 budget on past events alone. The cap is
    # one grudge a turn, which is 40 of the turn's money, and the rest of the spend is the
    # 5-cost stance push - so it now takes thirty situations in one turn to go broke. That is
    # the fix working, and the fixture has to grow with it or it stops measuring contention.
    burst_regions, burst_world = [], [{"name": "sacker", "regions": 20, "subculture": CHD}]
    burst = []
    for i in range(1, 31):
        burst_regions += [{"key": "rv%d" % i, "adj": ["rh%d" % i]},
                          {"key": "rh%d" % i, "adj": ["rv%d" % i]}]
        burst_world += [
            # CHD victims, so every situation is a kinslaying and clears the outrage floor.
            # This group measures BUDGET contention, so nothing may be starved for any other
            # reason - a low-outrage victim would suppress the grudge before the budget could.
            {"name": "victim%02d" % i, "subculture": CHD, "owns": ["rv%d" % i], "regions": 3},
            {"name": "hold%02d" % i, "subculture": DWF, "owns": ["rh%d" % i], "regions": 3}]
        burst.append({"event": "CharacterSackedSettlement", "instigator": "sacker",
                      "victim": "victim%02d" % i, "region": "rv%d" % i, "turn": 1})

    calls5, _ = run_lua(burst_world, events=burst, regions_spec=burst_regions)
    one_turn = len([c for c in calls5 if c[0] == "cai_add_diplomatic_event"])
    assert one_turn == 1, \
        "the world takes one permanent grudge a turn however busy the turn is, got %d" % one_turn
    # The budget guard still bites, on the beat that is NOT quota-limited: thirty stance pushes
    # at 5 plus the turn's one grudge at 40 outruns a 180 budget topped up once. Since
    # 2026-11-14 a budget below one push is passed over before the roll, not answered and skipped.
    assert [c for c in calls5 if c[0] == "out" and "cannot pay for anything" in c[1]], calls5
    assert len([c for c in calls5 if c[0] == "out" and "situation kind=" in c[1]]) == 30, \
        "every situation is still DETECTED when broke - only its beats are skipped"
    starved = len([c for c in calls5 if c[0] == "stance_promote"])
    assert 0 < starved < 30, "some pushes funded, some starved, got %d of 30" % starved

    # 14. The same thirty situations, one per turn, are all funded: the refill keeps up. This is
    # the assertion the mod shipped without. Until 2026-09-17 the refill lived only in
    # first_tick, which fires once per campaign LOAD, so the budget was a one-way drain and this
    # run would score the same as the burst above.
    spread = [dict(e, turn=i + 1) for i, e in enumerate(burst)]
    calls6, _ = run_lua(burst_world, events=spread, regions_spec=burst_regions)
    over_turns = len([c for c in calls6 if c[0] == "cai_add_diplomatic_event"])
    assert over_turns == 30, \
        "one situation a turn must never be starved, got %d of 30" % over_turns
    assert over_turns > one_turn, (over_turns, one_turn)
    assert len([c for c in calls6 if c[0] == "stance_promote"]) == 30, calls6

    # 15. A faction on cooldown is not cast again.
    calls7, _ = run_lua(pair_world, events=ev2, regions_spec=regions, scores=yes,
                        preload={"derpy_director_cooldowns": {"hold_a": 99}})
    cd_line = [c[1] for c in calls7 if c[0] == "out"
               and c[1].find("cast ") == len("[director] ")]
    assert cd_line and "hold_a" not in cd_line[0], cd_line

    # 16. The coalition is attempted BEFORE the grudge. Both draw on one budget, force is cheap
    # and reversible and past_event is expensive with no inverse, so ordering them the other way
    # lets the grudge price out the alliance. That is not hypothetical: on 2026-09-16 the only
    # mutually willing pair the mod has ever found was refused for 15 budget that two past
    # events had already spent.
    kinds = [c[0] for c in calls4
             if c[0] in ("force_alliance", "cai_add_diplomatic_event")]
    assert "force_alliance" in kinds and "cai_add_diplomatic_event" in kinds, kinds
    assert kinds.index("force_alliance") < kinds.index("cai_add_diplomatic_event"), kinds

    # 17. A situation nobody is in reach to witness spends NOTHING - not even the cheap mood.
    # Three of 26 live situations cast an empty audience and were still billed for one.
    lonely = [
        {"name": "sacker", "regions": 20, "subculture": CHD},
        {"name": "victim", "subculture": CHD, "owns": ["r_victim"], "regions": 3},
        {"name": "far_hold", "subculture": DWF, "owns": ["r_far2"], "regions": 3},
    ]
    calls8, state8 = run_lua(lonely, events=ev2, regions_spec=regions)
    assert [c for c in calls8 if c[0] == "out" and "situation kind=" in c[1]], calls8
    assert not [c for c in calls8 if c[0] == "set_base_strategic_threat_score"], calls8
    assert not [c for c in calls8 if c[0] == "out" and "beat skipped" in c[1]], \
        "an empty cast must not even ATTEMPT a beat"
    assert state8["derpy_director_budget"] == "180", state8

    # 18. The once-only guard keys on the FEUD, not the settlement. A grinding war takes town
    # after town off the same victim; keying the guard on the region made each one a fresh story
    # worth fresh permanent attitude damage, and live logs show Sayl vs Zhatan billing three
    # times over four turns from three different regions.
    # Spaced past the 12-turn per-faction cooldown on purpose. Bunched up, the first past event
    # puts the whole cast on cooldown, later situations cast nobody and the count stays at 2
    # whether the guard keys on the feud or on the region - which is exactly how the equivalent
    # mask hid itself in assertion 11.
    same_feud = [dict(ev2[0], region=r, turn=t)
                 for t, r in zip([1, 14, 27], ["r_victim", "r_near", "r_mid"])]
    calls9, _ = run_lua(pair_world, events=same_feud, regions_spec=regions, scores=yes)
    assert len([c for c in calls9 if c[0] == "out" and "situation kind=" in c[1]]) == 3, calls9
    per_feud = len([c for c in calls9 if c[0] == "cai_add_diplomatic_event"])
    assert per_feud == 1, \
        "one past event for the whole feud, not one per settlement, got %d" % per_feud
    print("selftest: budget, cooldown and persistence ok")

    # 15. News entries are keys and numbers only. A news entry is written in a LISTENER and read
    # much later by a panel; a loc call from a listener CTDs at turn 1 and pcall does not catch
    # it, so no resolved text may ever enter this buffer.
    _, state2 = run_lua(pair_world, events=ev2, regions_spec=regions, scores=yes)
    assert state2["derpy_director_news"] == "table:1", state2

    # 15b. The ring buffer is CAPPED. Every entry rides in the save for the life of the
    # campaign, so an unbounded buffer is a save that grows without limit.
    many = [{"event": "CharacterSackedSettlement", "instigator": "sacker",
             "victim": "victim", "region": "r_victim"} for _ in range(60)]
    _, state3 = run_lua(pair_world, events=many, regions_spec=regions, scores=yes)
    assert state3["derpy_director_news"] == "table:50", state3

    # 16. Nothing in either shipped file resolves loc, anywhere.
    for path in (SCRIPT, LORE):
        text = open(path, encoding="utf-8").read()
        for banned in ("effect.get_localised_string", "common.get_localised_string",
                       "get_localised_string"):
            assert banned not in text, "loc call CTDs at turn 1: %s in %s" % (banned, path)

    # 17. luac, the API check and the undeclared-global check all pass on both shipped files. The
    # API check indexes CA's scripting docs, which a public clone does not carry: skipped, and said.
    api = os.path.isdir(os.path.join(ROOT, "Modding Files", "reference", "ca_script_docs_wh3"))
    if not api:
        print("selftest: API check skipped, CA's scripting docs are not in this checkout")
    for path in (SCRIPT, LORE):
        for cmd in ([LUAC, "-p", path],
                    [sys.executable, os.path.join(ROOT, "tools", "check_lua_api.py"), path],
                    [sys.executable, os.path.join(ROOT, "tools", "check_lua_undeclared.py"),
                     path]):
            if "check_lua_api.py" in cmd[-2] and not api:
                continue
            r = subprocess.run(cmd, capture_output=True, text=True)
            assert r.returncode == 0, "%s failed on %s:\n%s" % (
                os.path.basename(cmd[0]), path, r.stdout + r.stderr)
    # 19. Outrage. The same aggressor sacking three different victims produces three different
    # verdicts, read straight out of the lore matrix: sworn enemies shrug, an unprovoked attack
    # does not, and kinslaying is the worst of the three. Measured bases, not guessed:
    # Chaos Dwarfs -> Dwarfs is -100, -> Cathay is -40, -> Chaos Dwarfs is the kin case.
    CTH2 = "wh3_main_sc_cth_cathay"
    for victim_sc, want_word, want_grudge in ((DWF, "sworn_enemies", False),
                                              (CTH2, "old_enmity", True),
                                              (CHD, "kinslaying", True)):
        w = [
            {"name": "sacker", "regions": 20, "subculture": CHD},
            {"name": "victim", "subculture": victim_sc, "owns": ["r_victim"], "regions": 3},
            {"name": "hold_a", "subculture": DWF, "owns": ["r_near"], "regions": 3},
            {"name": "hold_b", "subculture": DWF, "owns": ["r_near"], "regions": 3},
        ]
        c, _ = run_lua(w, events=ev2, regions_spec=regions)
        line = [x[1] for x in c if x[0] == "out" and "situation kind=" in x[1]][0]
        assert "(%s)" % want_word in line, (want_word, line)
        got_grudge = bool([x for x in c if x[0] == "cai_add_diplomatic_event"])
        assert got_grudge == want_grudge, (victim_sc, want_word, got_grudge, line)
        # Whatever the verdict, the reversible stance push always happens. A shrug is a smaller
        # reaction, never no reaction.
        assert [x for x in c if x[0] == "stance_promote"], (want_word, c)

    # A shrug draws a smaller audience than an atrocity, from the same world.
    def cast_size(victim_sc):
        w = [
            {"name": "sacker", "regions": 20, "subculture": CHD},
            {"name": "victim", "subculture": victim_sc, "owns": ["r_victim"], "regions": 3},
            {"name": "hold_a", "subculture": DWF, "owns": ["r_near"], "regions": 3},
            {"name": "hold_b", "subculture": DWF, "owns": ["r_near"], "regions": 3},
            {"name": "hold_c", "subculture": DWF, "owns": ["r_near"], "regions": 3},
        ]
        c, _ = run_lua(w, events=ev2, regions_spec=regions)
        line = [x[1] for x in c if x[0] == "out"
                and x[1].find("cast ") == len("[director] ")][0]
        return len([p for p in line[len("[director] cast "):].split(", ") if p])
    assert cast_size(DWF) < cast_size(CHD), (cast_size(DWF), cast_size(CHD))

    # The LIVE attitude outranks the inherited one. These two holds are identical on culture,
    # proximity, wars and region count - the only difference is that zz_bitter actually loathes
    # the aggressor right now. Its name sorts LAST, so if the live term were inert the
    # alphabetical tiebreak would put aa_calm first and this would fail.
    live_world = [
        {"name": "sacker", "regions": 20, "subculture": CHD},
        {"name": "victim", "subculture": CHD, "owns": ["r_victim"], "regions": 3},
        {"name": "aa_calm", "subculture": DWF, "owns": ["r_near"], "regions": 3},
        {"name": "zz_bitter", "subculture": DWF, "owns": ["r_near"], "regions": 3,
         "attitudes": {"sacker": -100}},
    ]
    c, _ = run_lua(live_world, events=ev2, regions_spec=regions)
    line = [x[1] for x in c if x[0] == "out"
            and x[1].find("cast ") == len("[director] ")][0]
    assert line.index("zz_bitter") < line.index("aa_calm"), line
    # And it is asked about the AGGRESSOR, by key string - all five CA call sites pass a key.
    att = [x for x in c if x[0] == "diplomatic_attitude_towards"]
    assert att and all(x[2] == "sacker" for x in att), att
    print("selftest: outrage ok")

    # 20. The three new scenarios. Each context is built to the shape CA documents and NOT to a
    # convenient one; the pump refuses to answer an accessor the real event does not have.
    raze_ev = [{"event": "CharacterRazedSettlement", "instigator": "sacker",
                "victim": "victim", "region": "r_victim"}]
    c, _ = run_lua(pair_world, events=raze_ev, regions_spec=regions)
    assert [x for x in c if x[0] == "out" and "kind=raze" in x[1]], c

    # Conquest: previous_faction lost it, region:owning_faction holds it now.
    conq_world = [
        {"name": "sacker", "regions": 20, "subculture": CHD, "owns": ["r_victim"]},
        {"name": "victim", "subculture": CHD, "regions": 3},
        {"name": "hold_a", "subculture": DWF, "owns": ["r_near"], "regions": 3},
    ]
    conq = [{"event": "RegionFactionChangeEvent", "instigator": "sacker", "victim": "victim",
             "region": "r_victim"}]
    c, _ = run_lua(conq_world, events=conq, regions_spec=regions)
    line = [x[1] for x in c if x[0] == "out" and "situation kind=" in x[1]]
    assert line and "kind=conquest" in line[0], c
    assert "instigator=sacker" in line[0] and "victim=victim" in line[0], line

    # Only a capture by force is an atrocity. The values are the engine's own: CA's Custom Starts
    # hand regions over on turn 1, and until 2026-09-25 those raised rebels before the player
    # had moved, because the filter listed words reason() never returns.
    for peaceful in ("startpos setup", "campaign director", "diplomacy trade", "payload"):
        c, _ = run_lua(conq_world, events=[dict(conq[0], reason=peaceful)],
                       regions_spec=regions)
        assert not [x for x in c if x[0] == "out" and "situation kind=" in x[1]], (peaceful, c)
        assert [x for x in c if x[0] == "out" and "not by force" in x[1]], (peaceful, c)
        # One line per drop: the builder already said why, so "incomplete context" would be a
        # second, false reason. It doubled the October log, 75 of its 150 lines.
        assert not [x for x in c if x[0] == "out" and "incomplete context" in x[1]], (peaceful, c)
    c, _ = run_lua(conq_world, events=[dict(conq[0], reason="unopposed capture")],
                   regions_spec=regions)
    assert [x for x in c if x[0] == "out" and "situation kind=conquest" in x[1]], c

    # Confederation: confederation() absorbs, faction() is absorbed, and the anchor is the
    # absorber's home region because the absorbed faction owns nothing by now.
    conf = [{"event": "FactionJoinsConfederation", "instigator": "sacker", "victim": "victim"}]
    c, _ = run_lua(conq_world, events=conf, regions_spec=regions)
    line = [x[1] for x in c if x[0] == "out" and "situation kind=" in x[1]]
    assert line and "kind=confederation" in line[0], c
    assert "region=r_victim" in line[0], "the absorber's home region anchors reach: %s" % line

    # Every scenario in WATCHED must name a builder that exists, or it dies silently in game.
    src_l = open(SCRIPT, encoding="utf-8").read()
    for b in re.findall(r'build = "([a-z_]+)"', src_l):
        assert "function derpy_director:%s(" % b in src_l, \
            "WATCHED names builder %s and nothing defines it" % b
    print("selftest: scenarios ok")

    # 24. Companion mods. Resource Overhaul's seizures become situations and the Great Guilds'
    # temple hears of kin-slaying, each only when that mod is installed. The wrapped calls must
    # still run, return what they returned, and never see a Director fault.
    sz_world = [
        {"name": "raider", "regions": 20, "subculture": CHD, "human": True},
        {"name": "owner", "subculture": CHD, "owns": ["r_victim"], "regions": 3},
        {"name": "hold_a", "subculture": DWF, "owns": ["r_near"], "regions": 3},
        {"name": "hold_b", "subculture": DWF, "owns": ["r_near"], "regions": 3},
    ]
    both = {"ro": True, "gg": True}
    c, _ = run_lua(sz_world, companions=both, regions_spec=regions)
    line = [x[1] for x in c if x[0] == "out" and "companions:" in x[1]]
    assert line and "Resource Overhaul (seizures)" in line[0], c
    assert "Great Guilds (temple)" in line[0], line
    c, _ = run_lua(sz_world, regions_spec=regions)
    assert [x for x in c if x[0] == "out" and "companions: none" in x[1]], c

    seize = [{"event": "ShipmentSeized", "instigator": "raider", "victim": "owner",
              "region": "r_victim"}]
    c, _ = run_lua(sz_world, events=seize, companions={"ro": True}, regions_spec=regions)
    assert ("ro_seize", "owner", "raider", "nil") in c, "the wrapped call did not run: %s" % c
    assert ("seize_returned", "ro_result", "nil", "3") in c, \
        "the wrapper changed what Resource Overhaul's call returned: %s" % c
    line = [x[1] for x in c if x[0] == "out" and "situation kind=seizure" in x[1]]
    assert line and "instigator=raider" in line[0] and "victim=owner" in line[0], c
    # Kin-slaying is 1.5; a seizure counts at half.
    assert "outrage=0.75" in line[0], line
    # Its grudge speaks with the convoy record, not the sacked-settlement one, at the cargo.
    assert [x for x in c if x[0] == "show_message_event_located" and x[3] == "7,9|false|7500"], c
    assert not [x for x in c if x[0] == "show_message_event_located" and "|730" in x[3]], c

    # A cargo already delivered or taken: the real call ignores it, so must the Director.
    for ev in ("ShipmentSeized", "ConvoySeized"):
        c, _ = run_lua(sz_world, events=[dict(seize[0], event=ev, stale=True)],
                       companions={"ro": True}, regions_spec=regions)
        assert not [x for x in c if x[0] == "out" and "situation kind=" in x[1]], (ev, c)
    c, _ = run_lua(sz_world, events=[dict(seize[0], event="ConvoySeized")],
                   companions={"ro": True}, regions_spec=regions)
    assert ("ro_convoy_seize", "owner", "raider", "nil") in c, c
    assert [x for x in c if x[0] == "out" and "situation kind=seizure" in x[1]], c

    # A fault inside the Director's response stays out of Resource Overhaul's turn.
    boom = [dict(f) for f in sz_world]
    boom[2]["throws"] = True
    c, _ = run_lua(boom, events=seize, companions={"ro": True}, regions_spec=regions)
    assert [x for x in c if x[0] == "out" and "companion hook errored" in x[1]], c
    assert ("seize_returned", "ro_result", "nil", "3") in c, c

    # Off means nothing hooked: the call runs as if the Director were absent.
    c, _ = run_lua(sz_world, events=seize, companions=both, regions_spec=regions, disable=True)
    assert [x[0] for x in c] == ["ro_seize", "seize_returned"], c

    # The temple. An Empire faction sacking its own kin loses Reputation, once a feud a turn,
    # and hears of it only when it is the player and something was taken.
    EMP = "wh_main_sc_emp_empire"
    emp_world = [
        {"name": "slayer", "regions": 20, "subculture": EMP, "human": True},
        {"name": "kin", "subculture": EMP, "owns": ["r_victim"], "regions": 3},
        {"name": "hold_a", "subculture": DWF, "owns": ["r_near"], "regions": 3},
    ]
    sack = [{"event": "CharacterSackedSettlement", "instigator": "slayer", "victim": "kin",
             "region": "r_victim"}]
    temple = ("gg_penalise", "slayer", "temple", "25")
    told = lambda calls: [x for x in calls if x[0] == "show_message_event_located"
                          and x[3].endswith("|7600")]
    c, _ = run_lua(emp_world, events=sack, companions={"gg": True}, regions_spec=regions)
    assert temple in c and told(c), c
    burst = [dict(sack[0], turn=1, region=r) for r in ("r_victim", "r_near", "r_mid")]
    c, _ = run_lua(emp_world, events=burst, companions={"gg": True}, regions_spec=regions)
    assert len([x for x in c if x[0] == "gg_penalise"]) == 1, c
    # The player as the VICTIM: a party to the sack, so the party gate lets it through, and the
    # slayer's own message must still not reach them.
    ai = [dict(f) for f in emp_world]
    ai[0]["human"], ai[1]["human"] = False, True
    c, _ = run_lua(ai, events=sack, companions={"gg": True}, regions_spec=regions)
    assert temple in c and not told(c), "only the slayer hears of it: %s" % c
    c, _ = run_lua(emp_world, events=sack, companions={"gg": True, "gg_held": 0},
                   regions_spec=regions)
    assert temple in c and not told(c), "nothing was lost, so nothing is said: %s" % c
    # No temple loss for a race that knifes its own, for a confederation, for a different
    # culture, or with no Guilds installed.
    chd_sack = [{"event": "CharacterSackedSettlement", "instigator": "raider", "victim": "owner",
                 "region": "r_victim"}]
    c, _ = run_lua(sz_world, events=chd_sack, companions={"gg": True}, regions_spec=regions)
    assert not [x for x in c if x[0] == "gg_penalise"], c
    conf = [{"event": "FactionJoinsConfederation", "instigator": "slayer", "victim": "kin"}]
    c, _ = run_lua(emp_world, events=conf, companions={"gg": True}, regions_spec=regions)
    assert [x for x in c if x[0] == "out" and "kind=confederation" in x[1]], c
    assert not [x for x in c if x[0] == "gg_penalise"], c
    other = [dict(f) for f in emp_world]
    other[1]["subculture"] = DWF
    c, _ = run_lua(other, events=sack, companions={"gg": True}, regions_spec=regions)
    assert not [x for x in c if x[0] == "gg_penalise"], c
    c, _ = run_lua(emp_world, events=sack, regions_spec=regions)
    assert [x for x in c if x[0] == "out" and "situation kind=sack" in x[1]] and not told(c), c

    # The Iron Court (2026-11-14). A secession becomes a situation once its rising is done: the
    # neighbours turn on the realm that split, and the shield a pact buys covers the rebels' new
    # settlement. The realm is told once, with its own record, and its court hears of it.
    ic = {"ic": True}
    ic_world = [
        {"name": "realm", "regions": 20, "subculture": CHD, "human": True},
        {"name": "rebels", "subculture": CHD, "owns": ["r_victim"], "regions": 1},
        {"name": "hold_a", "subculture": DWF, "owns": ["r_near"], "regions": 3},
        {"name": "hold_b", "subculture": DWF, "owns": ["r_near"], "regions": 3},
    ]
    secede = [{"event": "Secession", "instigator": "realm", "victim": "rebels",
               "region": "r_victim"}]
    situations = lambda calls: [x[1] for x in calls
                                if x[0] == "out" and "situation kind=" in x[1]]
    c, _ = run_lua(ic_world, companions=ic, regions_spec=regions)
    line = [x[1] for x in c if x[0] == "out" and "companions:" in x[1]]
    assert line and "Iron Court (secessions, loyalty)" in line[0], c
    c, _ = run_lua(ic_world, events=secede, companions=ic, regions_spec=regions, scores=yes)
    assert ("ic_secede", "realm", "legion", "nil") in c and ("ic_sour", "rebels", "realm", "nil") in c
    assert ("secede_returned", "2", "nil", "nil") in c and ("sour_returned", "5", "nil", "nil") in c, \
        "the wrapper changed what the Iron Court's calls returned: %s" % c
    sits = situations(c)
    assert len(sits) == 1 and "kind=secession instigator=realm victim=rebels region=r_victim" \
        in sits[0], sits
    order = [x[0] for x in c]
    assert order.index("ic_sour") < order.index("stance_promote"), \
        "raised before the last step, while the provinces were still the realm's: %s" % order
    assert {x[1] for x in c if x[0] == "stance_promote" and x[2] == "realm"} == {"hold_a", "hold_b"}
    assert ("force_alliance", "hold_a", "hold_b", "false") in c, c
    assert ("shield_on", "set_r_victim", "nil", "nil") in c, "the rebels' town is shielded: %s" % c
    shown = [x for x in c if x[0].startswith("show_message_event")]
    assert len(shown) == 1 and shown[0][1] == "realm" and shown[0][3] == "100,200|false|7700", \
        "one message, the secession's own, never the sack or pact records: %s" % shown
    # The war party gains and the merchants lose, once each for a pact AND a grudge, read from the
    # save before the move and saved after it.
    moved = [x for x in c if x[0] == "ic_loyalty"]
    assert moved == [("ic_loyalty", "realm", "legion", "3"),
                     ("ic_loyalty", "realm", "ledger", "-3")], moved
    assert order.index("ic_loaded") < order.index("ic_loyalty") < order.index("ic_save"), order
    # An AI realm with the player watching: the beats run, nobody is told, no court moves.
    witness = [dict(f, human=False) for f in ic_world] + [
        {"name": "player", "subculture": EMP, "owns": ["r_far2"], "regions": 3, "human": True}]
    c, _ = run_lua(witness, events=secede, companions=ic, regions_spec=regions, scores=yes)
    assert ("force_alliance", "hold_a", "hold_b", "false") in c, c
    assert not [x for x in c if x[0].startswith("show_message_event")], c
    assert not [x for x in c if x[0] == "ic_loyalty"], "an AI court is never moved: %s" % c
    # Two parties leaving one realm in one turn, the second rising finishing first: each is sited
    # on what it took.
    two = ic_world[:1] + [
        {"name": "rebels_a", "subculture": CHD, "owns": ["r_victim"], "regions": 1},
        {"name": "rebels_b", "subculture": CHD, "owns": ["r_mid"], "regions": 1},
    ] + ic_world[2:]
    both_out = [dict(secede[0], victim="rebels_a", turn=1, stale=True),
                dict(secede[0], victim="rebels_b", region="r_mid", turn=1, stale=True),
                {"event": "SecessionDone", "instigator": "realm", "victim": "rebels_b", "turn": 1},
                {"event": "SecessionDone", "instigator": "realm", "victim": "rebels_a", "turn": 1}]
    c, _ = run_lua(two, events=both_out, companions=ic, regions_spec=regions, scores=yes)
    sits = situations(c)
    assert len(sits) == 2 and "victim=rebels_b region=r_mid" in sits[0] \
        and "victim=rebels_a region=r_victim" in sits[1], sits
    # A rising that never finished raises nothing; rebels holding none of what was taken are
    # dropped, not sited on other land.
    c, _ = run_lua(ic_world, events=[dict(secede[0], stale=True)], companions=ic,
                   regions_spec=regions)
    assert ("secede_returned", "2", "nil", "nil") in c and not situations(c), c
    c, _ = run_lua(ic_world, events=[dict(secede[0], region="r_mid")], companions=ic,
                   regions_spec=regions)
    assert [x for x in c if x[0] == "out" and "left rebels no region" in x[1]], c
    assert not situations(c), c
    # A Director fault stays out of the Iron Court's turn; off, nothing is hooked; a moved call
    # is reported and nothing is hooked.
    boom = [dict(f) for f in ic_world]
    boom[2]["throws"] = True
    c, _ = run_lua(boom, events=secede, companions=ic, regions_spec=regions)
    assert [x for x in c if x[0] == "out" and "companion hook errored" in x[1]], c
    assert ("sour_returned", "5", "nil", "nil") in c, c
    c, _ = run_lua(ic_world, events=secede, companions=ic, regions_spec=regions, disable=True)
    assert [x[0] for x in c] == ["ic_secede", "secede_returned", "ic_sour", "sour_returned"], c
    c, _ = run_lua(ic_world, events=secede, companions={"ic": True, "ic_missing": "move_loyalty"},
                   regions_spec=regions)
    assert [x for x in c if x[0] == "out" and "IC.move_loyalty has moved" in x[1]], c
    assert not situations(c) and ("sour_returned", "5", "nil", "nil") in c, c

    # The court hears of any situation that turns neighbours against the player's realm: here a
    # Chaos Dwarf sack, which keeps its own records. Chaos Dwarfs do not condemn kin-slaying, so
    # the temple party is not moved.
    c, _ = run_lua(sz_world, events=chd_sack, companions=ic, regions_spec=regions, scores=yes)
    moved = [x for x in c if x[0] == "ic_loyalty"]
    assert moved == [("ic_loyalty", "raider", "legion", "3"),
                     ("ic_loyalty", "raider", "ledger", "-3")], moved
    assert not [x for x in c if x[0].startswith("show_message_event") and x[3].endswith("|7700")]
    # A cold shoulder is not news at court: sworn enemies draw one responder, so no pact, and
    # fall under the grudge floor. The stance still moved.
    foe_world = [dict(f) for f in sz_world]
    foe_world[1]["subculture"] = DWF
    c, _ = run_lua(foe_world, events=chd_sack, companions=ic, regions_spec=regions, scores=yes)
    assert [x for x in c if x[0] == "stance_promote"], c
    assert not [x for x in c if x[0] == "ic_loyalty"], c
    c, _ = run_lua([dict(f, human=False) for f in sz_world], events=chd_sack, companions=ic,
                   regions_spec=regions, scores=yes)
    assert ("force_alliance", "hold_a", "hold_b", "false") in c, c
    assert not [x for x in c if x[0] == "ic_loyalty"], c

    # Kin-slaying in a Dwarf court costs the temple party, with or without the Guilds, once a
    # feud a turn. Neither an Empire faction (no court) nor an AI court is moved.
    dwf_world = [dict(f, subculture=DWF) if f["name"] in ("slayer", "kin") else dict(f)
                 for f in emp_world]
    kin_loss = ("ic_loyalty", "slayer", "temple", "-5")
    c, _ = run_lua(dwf_world, events=sack, companions=ic, regions_spec=regions)
    assert kin_loss in c and ("ic_save", "slayer", "nil", "nil") in c, c
    assert not [x for x in c if x[0] == "gg_penalise"], c
    c, _ = run_lua(dwf_world, events=burst, companions=ic, regions_spec=regions)
    assert len([x for x in c if x == kin_loss]) == 1, c
    c, _ = run_lua(dwf_world, events=sack, companions={"ic": True, "gg": True},
                   regions_spec=regions)
    assert kin_loss in c and ("gg_penalise", "slayer", "temple", "25") in c, c
    c, _ = run_lua(emp_world, events=sack, companions=ic, regions_spec=regions)
    assert not [x for x in c if x[0] == "ic_loyalty"], c
    c, _ = run_lua([dict(f, human=False) for f in dwf_world], events=sack, companions=ic,
                   regions_spec=regions)
    assert not [x for x in c if x[0] == "ic_loyalty"], c
    print("selftest: companions ok")

    # 9.0 runs listener callbacks bare (lib_core's event_unprotected_callback), so an error that
    # escapes one stops every callback after it on that event, CA's and other mods' included. A
    # fault anywhere in on_event - here in cast(), outside the builder's own pcall - must stay
    # inside the Director. run_lua raises if it escapes, because the harness pump is bare too.
    boom = [dict(f) for f in pair_world]
    boom[2]["throws"] = True
    c, _ = run_lua(boom, events=ev2, regions_spec=regions)
    assert [x for x in c if x[0] == "out" and "errored:" in x[1]], c
    print("selftest: a fault stays inside the Director")

    # 21. Protection (E). A pact shields the settlement the coalition formed over, and the shield
    # is LIFTED on a later turn - a protection never released is a permanent hole in the AI's
    # target list, and that is the sort of thing noticed fifty turns later.
    shield_world = [
        {"name": "sacker", "regions": 20, "subculture": CHD},
        {"name": "victim", "subculture": CHD, "owns": ["r_victim"], "regions": 3},
        {"name": "hold_a", "subculture": DWF, "owns": ["r_near"], "regions": 3},
        {"name": "hold_b", "subculture": DWF, "owns": ["r_near"], "regions": 3},
    ]
    c, _ = run_lua(shield_world, events=ev2, regions_spec=regions, scores=yes)
    on = [x for x in c if x[0] == "shield_on"]
    assert on and on[0][1] == "set_r_victim", \
        "the SETTLEMENT key is what this call takes, not the region key: %s" % (on,)
    assert len(on) == 1, "one shield per situation, not one per willing pair: %s" % (on,)

    # Sixteen quiet turns later it is released, exactly once.
    quiet = [dict(ev2[0], turn=1)] + [{"event": "CharacterSackedSettlement",
                                       "instigator": "sacker", "victim": "victim",
                                       "region": "r_victim", "turn": t} for t in (16, 17)]
    c2, _ = run_lua(shield_world, events=quiet, regions_spec=regions, scores=yes)
    off = [x for x in c2 if x[0] == "shield_off"]
    assert len(off) == 1 and off[0][1] == "set_r_victim", \
        "the shield must be lifted once and only once: %s" % (off,)

    # A settlement the victim no longer holds is NOT shielded - after a conquest that would hand
    # the aggressor a free garrison.
    conq_shield = [
        {"name": "sacker", "regions": 20, "subculture": CHD, "owns": ["r_victim"]},
        {"name": "victim", "subculture": CHD, "regions": 3},
        {"name": "hold_a", "subculture": DWF, "owns": ["r_near"], "regions": 3},
        {"name": "hold_b", "subculture": DWF, "owns": ["r_near"], "regions": 3},
    ]
    c3, _ = run_lua(conq_shield, events=conq, regions_spec=regions, scores=yes)
    assert not [x for x in c3 if x[0] == "shield_on"], \
        "shielding a settlement the aggressor now owns arms the wrong side"
    assert [x for x in c3 if x[0] == "out" and "not the victim's any more" in x[1]], c3

    # 22. Economy and disaster (F). A new coalition funds a muster, for BOTH members, and
    # treasury_mod is only ever given a positive amount - the stub errors on anything else
    # because the engine documents it as positive-only and would simply do nothing.
    paid = [x for x in c if x[0] == "treasury_mod"]
    assert len(paid) == 2, paid
    assert {x[1] for x in paid} == {"hold_a", "hold_b"}, paid
    assert all(int(x[2]) > 0 for x in paid), paid

    # Razing breeds plague; sacking does not. Same world, same factions, different deed.
    raze2 = [{"event": "CharacterRazedSettlement", "instigator": "sacker", "victim": "victim",
              "region": "r_victim"}]
    c4, _ = run_lua(shield_world, events=raze2, regions_spec=regions)
    plagues = [x for x in c4 if x[0] == "spawn_plague_at_region"]
    # 9.0 order: spreader faction (the razer), region, key.
    assert plagues and plagues[0][1] == "sacker" and plagues[0][2] == "r_victim", c4
    assert plagues[0][3].startswith("wh3_main_nur_base_"), plagues
    c5, _ = run_lua(shield_world, events=ev2, regions_spec=regions)
    assert not [x for x in c5 if x[0] == "spawn_plague_at_region"], \
        "a sack is not a razing - the plague belongs to the deed that destroyed the place"

    # An unrighteous conquest breeds rebellion, and it carries the map point.
    c6, _ = run_lua(conq_shield, events=conq, regions_spec=regions)
    reb = [x for x in c6 if x[0] == "force_rebellion_with_faction"]
    assert reb and reb[0][1] == "r_victim", c6
    # THE DISPOSSESSED OWNER'S OWN REBELS, not the conqueror's and not the generic pool. Both
    # sides of this fixture are Chaos Dwarfs, so a map keyed on the wrong faction would still
    # answer CHD here - the 0.85 case below is what separates them.
    assert reb[0][2] == "wh3_dlc23_chd_chaos_dwarfs_rebels", reb
    assert int(reb[0][3]) > 0, reb
    assert not [x for x in c6 if x[0] == "spawn_plague_at_region"], \
        "conquest raises rebels, not disease"

    # WHOSE REBELS - the victim's, never the conqueror's. Both sides of the conquest fixture
    # above are Chaos Dwarfs, so a map keyed on the INSTIGATOR would answer CHD there and pass.
    # Cathay against Kislev is the pair that separates them: the lore matrix reads +10, which
    # falls off the end of OUTRAGE_STEPS to unprovoked 1.0 - over the unrest floor - while the
    # two subcultures stay different. Kislev loses the province, so Kislev rises.
    CTH = "wh3_main_sc_cth_cathay"
    whose = [
        {"name": "sacker", "regions": 20, "subculture": CTH, "owns": ["r_victim"]},
        {"name": "victim", "subculture": KSL, "regions": 3},
        # NEIGHBOURS WHO MIND CATHAY, which is not the same as neighbours who like the victim.
        # The cast is built from how much a candidate hates the INSTIGATOR, so Kislev kin make
        # this vacuous - they read +10 toward Cathay and nobody turns up. An empty cast drops
        # the situation before any consequence is priced, and the test failed that way twice.
        # Daemons read -100 toward Cathay.
        {"name": "hold_a", "subculture": DAE, "owns": ["r_near"], "regions": 3},
        {"name": "hold_b", "subculture": DAE, "owns": ["r_near"], "regions": 3},
    ]
    c6c, _ = run_lua(whose, events=conq, regions_spec=regions)
    wreb = [x for x in c6c if x[0] == "force_rebellion_with_faction"]
    assert wreb, "an unprovoked conquest at 1.00 must raise rebels: %s" % (c6c,)
    assert wreb[0][2] == "wh3_main_ksl_kislev_rebels",         "the DISPOSSESSED owner rises, not the conqueror: %s" % (wreb,)

    # THE MIDDLE BAND EARNS A GRUDGE AND NO REBELS - the whole point of UNREST_FLOOR being a
    # separate constant from OUTRAGE_FLOOR. Chaos Dwarfs taking a KISLEV holding reads out of
    # the shipped lore matrix as 0.60 - comfortably over the 0.5 grudge floor and under the 1.0
    # unrest floor. This is the author's OWN pairing, and 0.60 is the number every one of his ten
    # logged conquests scored. Before 2026-09-22 both used one floor and this conquest raised
    # four rebels, which is the bug the author reported - every capture he made, ten for ten.
    #
    # Read off the REAL lore file, not a hand-set number: run_lua loads the shipped
    # derpy_director_lore.lua, so if that matrix is regenerated and CHD/KSL moves bands, this
    # assertion changes meaning and should fail rather than quietly stop testing anything.
    mid = [
        {"name": "sacker", "regions": 20, "subculture": CHD, "owns": ["r_victim"]},
        {"name": "victim", "subculture": KSL, "regions": 3},
        {"name": "hold_a", "subculture": DWF, "owns": ["r_near"], "regions": 3},
        {"name": "hold_b", "subculture": DWF, "owns": ["r_near"], "regions": 3},
    ]
    c6b, _ = run_lua(mid, events=conq, regions_spec=regions)
    assert not [x for x in c6b if x[0] == "force_rebellion_with_faction"],         "a 0.85 conquest must not raise rebels - that is what the 1.0 unrest floor is for: %s"         % (c6b,)
    assert [x for x in c6b if x[0] == "out" and "no grudge" in x[1]] == [],         "0.85 clears the 0.5 grudge floor, so the grudge branch must NOT have been skipped"

    # Both are irreversible once loose, so both sit behind the outrage floor. Chaos Dwarfs
    # razing Dwarfs is sworn enemies at -100 and earns neither.
    shrug = [dict(f) for f in shield_world]
    shrug[1]["subculture"] = DWF
    c7, _ = run_lua(shrug, events=raze2, regions_spec=regions)
    assert not [x for x in c7 if x[0] == "spawn_plague_at_region"], \
        "a shrug must not loose a plague: %s" % (c7,)
    print("selftest: protection, economy and disaster ok")
    _selftest_storyteller(CHD, DWF, EMP, regions, pair_world, feud_world, ev2, yes, conq_world,
                          conq)
    _selftest_long_run(CHD, DWF, regions, pair_world, ev2, yes)
    _selftest_mct()
    _selftest_runaway()
    _selftest_poll()
    _selftest_merge()
    _selftest_runaway_merge()
    print("selftest: news buffer and static checks ok")


def _selftest_runaway_merge():
    """32. Kin unite against a runaway (2026-11-14): the measured leader at the tier setting, or one
    of CA's endgame invaders from the moment it exists, sacks, razes or takes a town, and the
    victim's kin confederate with it, the larger taking the smaller in. Invaders never merge.
    """
    run = lambda *a, **k: run_lua(*a, quiet_runaway=False, **k)
    EMP, GRN, DWF, CHD = ("wh_main_sc_emp_empire", "wh_main_sc_grn_greenskins",
                          "wh_main_sc_dwf_dwarfs", "wh3_dlc23_sc_chd_chaos_dwarfs")
    merges = lambda calls: [(c[1], c[2]) for c in calls if c[0] == "apply_payload"]
    regions = [{"key": "r_vic", "adj": ["r_k"]}, {"key": "r_k", "adj": ["r_vic"]},
               {"key": "r_b", "adj": []}, {"key": "r_x", "adj": []}]

    def world(attacker="big", attacker_regions=25, **over):
        w = [{"name": attacker, "regions": attacker_regions, "subculture": EMP},
             {"name": "second", "regions": 10, "subculture": DWF},
             {"name": "vic", "regions": 4, "subculture": GRN, "owns": ["r_vic"]},
             {"name": "kin_a", "regions": 6, "subculture": GRN, "owns": ["r_k"]}]
        w = [dict(f, **over.get(f["name"], {})) for f in w]
        return w + [dict(f) for k, f in over.items() if k.startswith("+")]

    def sack(who="big", kind="CharacterSackedSettlement"):
        return [{"event": "SetBudget", "n": 180, "turn": 12},
                {"event": kind, "instigator": who, "victim": "vic", "region": "r_vic", "turn": 12}]

    def go(w=None, events=None, **k):
        return run(w or world(), events=events or sack(), regions_spec=regions, **k)

    # big is tier 2 (25 against 10): kin_a has more regions and takes vic in.
    c, _ = go()
    assert merges(c) == [("kin_a", "vic")], merges(c)
    assert outs(c, "merge kin_a absorbs vic (runaway)"), c
    # The larger side absorbs: vic at 8 takes kin_a in.
    assert merges(go(world(vic={"regions": 8}))[0]) == [("vic", "kin_a")]
    # A razed town too.
    assert merges(go(events=sack(kind="CharacterRazedSettlement"))[0]) == [("kin_a", "vic")]
    # The tier setting and the switch.
    assert merges(go(mct={"runaway_merge_tier": 3})[0]) == []
    assert merges(go(mct={"merge_runaway": False})[0]) == []
    # First of the answered beats: before any stance push of the same situation.
    pay = [i for i, x in enumerate(c) if x[0] == "apply_payload"][0]
    stance = [i for i, x in enumerate(c) if x[0] == "stance_promote"]
    assert stance and pay < stance[0], (pay, stance)
    # Not a runaway: 12 against 10.
    assert merges(go(world(attacker_regions=12))[0]) == []

    # CA's endgame invaders are runaways from the moment they exist, at any size.
    INV = "wh3_dlc29_chaos_invasion_confederation_owner"
    assert merges(go(world(attacker=INV, attacker_regions=5), sack(INV))[0]) == [("kin_a", "vic")]
    VT = "wh3_dlc29_vermintide_confederation_owner"
    assert merges(go(world(attacker=VT, attacker_regions=5), sack(VT))[0]) == [("kin_a", "vic")]
    waaagh = world(attacker_regions=5, big={"bundles": ["wh3_main_ie_scripted_endgame_waaagh"]})
    assert merges(go(waaagh)[0]) == [("kin_a", "vic")]
    NAG = "wh3_dlc29_nag_host_of_nagash"
    nag = world(attacker=NAG, attacker_regions=5)
    assert merges(go(nag, sack(NAG), script_state={"episode_nagash_endgame": True})[0]) \
        == [("kin_a", "vic")]
    assert merges(go(nag, sack(NAG))[0]) == []
    # An invader never merges: as kin it is skipped, and as the victim nothing happens.
    hordes = world(kin_a={"bundles": ["wh3_main_ie_scripted_endgame_wild_hunt"]},
                   **{"+kin_b": {"name": "kin_b", "regions": 3, "subculture": GRN}})
    c, _ = go(hordes)
    assert merges(c) == [("vic", "kin_b")] and outs(c, "kin_a is an endgame invader"), c
    c, _ = go(world(vic={"bundles": ["wh3_main_ie_scripted_endgame_waaagh"]}))
    assert merges(c) == [], merges(c)

    # The other kinds never start a runaway merge. Opportunism: big lost two towns to vic last
    # round, so big is the "instigator" of the turn start's opportunism.
    lost = world(vic={"owns": ["r_vic", "r_b"]})
    take = {"event": "RegionFactionChangeEvent", "instigator": "vic", "victim": "big",
            "region": "r_b", "turn": 12}
    c, _ = go(lost, [take, take, {"event": "Tick", "turn": 13}])
    assert outs(c, "situation kind=opportunism instigator=big"), c
    assert merges(c) == [], merges(c)
    c, _ = go(events=[{"event": "FactionJoinsConfederation", "instigator": "big", "victim": "vic",
                       "turn": 12}])
    assert outs(c, "situation kind=confederation instigator=big") and merges(c) == [], c
    c, _ = go(events=[{"event": "NegativeDiplomaticEvent", "instigator": "big", "victim": "vic",
                       "treaty": "was_alliance", "turn": 12}])
    assert outs(c, "situation kind=treachery instigator=big") and merges(c) == [], c
    court = world(big={"subculture": CHD},
                  **{"+rebels": {"name": "rebels", "regions": 1, "subculture": CHD,
                                 "owns": ["r_x"]}})
    c, _ = go(court, [{"event": "Secession", "instigator": "big", "victim": "rebels",
                       "region": "r_x", "turn": 12}], companions={"ic": True})
    assert outs(c, "situation kind=secession instigator=big") and merges(c) == [], c

    # Review focus 3: no invader on this map and no crisis bundle anywhere is no error, and the
    # measured leader is the only runaway.
    c, _ = go(events=[{"event": "Eval", "turn": 12,
                       "code": "return table.concat(derpy_director:runaway_keys(), ',')"}])
    assert evals(c) == ["big"], evals(c)
    check_invader_keys()
    print("selftest: runaway merge ok")


CA_EPISODES = os.path.join(ROOT, "Modding Files", "reference", "ca_scripts_wh3", "campaign",
                           "main_warhammer")


def check_invader_keys():
    """Every invader key, the Nagash state and every crisis bundle the Director names appears in
    CA's own episode or crisis scripts. A key fails silently in game, so a typo here would make an
    invasion invisible to the merges with no test to say so. Skipped where CA's scripts are absent
    (the public repository ships none of CA's files)."""
    if not os.path.isdir(CA_EPISODES):
        print("selftest: invader keys skipped, CA's scripts are not in this checkout")
        return
    src = open(SCRIPT, encoding="utf-8").read()
    block = src[src.index("local INVADERS"):src.index("function derpy_director:is_invader")]
    keys = re.findall(r'"([a-z0-9_]+)"', block)
    assert len(keys) == 9, keys
    ca = ""
    for sub in ("episodes", "crisis"):
        for name in sorted(os.listdir(os.path.join(CA_EPISODES, sub))):
            if name.endswith(".lua"):
                ca += open(os.path.join(CA_EPISODES, sub, name), encoding="utf-8",
                           errors="replace").read()
    missing = [k for k in keys if k not in ca]
    assert not missing, "keys in no CA episode or crisis script: %s" % missing


MERGE_REGIONS = [{"key": "r_vic", "adj": ["r_k"]}, {"key": "r_k", "adj": ["r_vic"]},
                 {"key": "r_vic2", "adj": ["r_k"]}, {"key": "r_x", "adj": []}]


def _merge_world(**over):
    """sacker (Empire, 8 regions: nobody leads by 1.75) takes the town of vic (Greenskins, down to
    its last region). Its kin: kin_big (6) and kin_small (3). over: {name: {field: value}}."""
    EMP, GRN = "wh_main_sc_emp_empire", "wh_main_sc_grn_greenskins"
    w = [{"name": "sacker", "regions": 8, "subculture": EMP, "owns": ["r_vic"]},
         {"name": "vic", "regions": 1, "subculture": GRN},
         {"name": "kin_big", "regions": 6, "subculture": GRN, "owns": ["r_k"]},
         {"name": "kin_small", "regions": 3, "subculture": GRN}]
    w = [dict(f, **over.get(f["name"], {})) for f in w]
    return w + [dict(f) for k, f in over.items() if k.startswith("+")]


def _merge_conq(turn=12, who="sacker", victim="vic", region="r_vic", budget=180, before=None):
    return [{"event": "SetBudget", "n": budget, "turn": turn}] + (before or []) + [
        {"event": "RegionFactionChangeEvent", "instigator": who, "victim": victim,
         "region": region, "turn": turn}]


def _selftest_merge():
    """31. Confederations, the last stand (2026-11-14): only what the game allows (both directions
    of the deal probe), never a player, the runaway's bloc, a vassal, a rising or a Chaos Dwarf house
    while a player plays one; priced, limited per turn, and never answered as somebody's deed.
    """
    run = lambda *a, **k: run_lua(*a, quiet_runaway=False, **k)
    EMP, GRN, DWF, CHD = ("wh_main_sc_emp_empire", "wh_main_sc_grn_greenskins",
                          "wh_main_sc_dwf_dwarfs", "wh3_dlc23_sc_chd_chaos_dwarfs")
    merges = lambda calls: [(c[1], c[2]) for c in calls if c[0] == "apply_payload"]
    budget = lambda st: int(st["derpy_director_budget"])

    def go(w=None, events=None, **k):
        return run(w or _merge_world(), events=events or _merge_conq(),
                   regions_spec=MERGE_REGIONS, **k)

    def off_budget(w=None, events=None, **k):
        k = dict(k)
        k["mct"] = dict(k.get("mct") or {}, merge_last_stand=False)
        return budget(go(w, events, **k)[1])

    # The base case: the largest kin takes the dying faction in, it is not answered as a deed, and
    # it costs 60.
    c, st = go()
    assert merges(c) == [("kin_big", "vic")], merges(c)
    assert outs(c, "merge kin_big absorbs vic (last_stand)"), c
    assert outs(c, "own merge, not a deed: kin_big + vic"), c
    assert not outs(c, "situation kind=confederation"), c
    assert off_budget() - budget(st) == 60, (off_budget(), budget(st))
    assert st["derpy_director_merge_count"] == "1", st

    # The threshold: 2 regions left is not a last stand at the default, 0 is, and the setting moves it.
    assert merges(go(_merge_world(vic={"regions": 2}))[0]) == []
    assert merges(go(_merge_world(vic={"regions": 0}))[0]) == [("kin_big", "vic")]
    assert merges(go(_merge_world(vic={"regions": 2}), mct={"last_stand_regions": 2})[0]) \
        == [("kin_big", "vic")]

    # The probe: either direction refusing moves on to the next kin; all refusing costs nothing and
    # leaves the turn's slot for a second dying faction.
    assert merges(go(deny=["kin_big|vic"])[0]) == [("kin_small", "vic")]
    assert merges(go(deny=["vic|kin_big"])[0]) == [("kin_small", "vic")]
    both = ["kin_big|vic", "kin_small|vic"]
    c, st = go(deny=both)
    assert merges(c) == [] and outs(c, "no merge for vic"), c
    assert budget(st) == off_budget(deny=both), (budget(st), off_budget(deny=both))
    two = _merge_world(**{"+vic2": {"name": "vic2", "regions": 1, "subculture": GRN},
                          "sacker": {"owns": ["r_vic", "r_vic2"]}})
    ev2 = _merge_conq() + [{"event": "RegionFactionChangeEvent", "instigator": "sacker",
                            "victim": "vic2", "region": "r_vic2", "turn": 12}]
    # vic2 is kin too, so it is refused for vic as well.
    assert merges(go(two, ev2, deny=both + ["vic2|vic"])[0]) == [("kin_big", "vic2")]
    # The AI's willingness is ignored by default; merge_needs_willing makes it the pact rule.
    sour = {"kin_big|vic": -50, "vic|kin_big": -50, "kin_small|vic": 5, "vic|kin_small": 5}
    assert merges(go(scores=sour)[0]) == [("kin_big", "vic")]
    assert merges(go(scores=sour, mct={"merge_needs_willing": True})[0]) == [("kin_small", "vic")]

    # Each exclusion skips kin_big, and kin_small takes vic in instead.
    def skips(w=None, events=None, **k):
        c, _ = go(w, events, **k)
        assert merges(c) == [("kin_small", "vic")], merges(c)
        return c
    skips(_merge_world(kin_big={"human": True}))
    skips(_merge_world(kin_big={"vassal_of": "sacker"}))
    skips(_merge_world(kin_big={"wars": ["vic"]}))
    skips(_merge_world(kin_big={"subculture": DWF}))
    c = skips(_merge_world(kin_big={"dead": True}))
    assert outs(c, "kin_big is dead"), c
    skips(_merge_world(kin_big={"rebel": True}))
    skips(_merge_world(kin_big={"met": ["sacker"]}))
    skips(preload={"derpy_director_risings": {"kin_big": True}})
    # The attacker itself, a kin-slayer, never takes in its own victim.
    skips(_merge_world(sacker={"owns": []}, kin_big={"owns": ["r_vic", "r_k"]}),
          _merge_conq(who="kin_big"))
    # The runaway (25 against sacker's 8 is tier 2) and anyone standing with it.
    c = skips(_merge_world(kin_big={"regions": 25}))
    assert outs(c, "kin_big is the runaway"), c
    # The bloc rule ignores the trigger slider: kin_big at tier 1 (15 against 8) is still never
    # fed, even when merges against a runaway wait for tier 2.
    c = skips(_merge_world(kin_big={"regions": 15}), mct={"runaway_merge_tier": 2})
    assert outs(c, "kin_big is the runaway"), c
    runaway = {"+emp_big": {"name": "emp_big", "regions": 25, "subculture": EMP}}
    skips(_merge_world(kin_big={"allies": ["emp_big"]}, **runaway))
    skips(_merge_world(kin_big={"military": ["emp_big"]}, **runaway))
    skips(_merge_world(kin_big={"vassal_of": "emp_big"}, **runaway))
    c = skips(_merge_world(**{"+emp_big": dict(runaway["+emp_big"], vassal_of="kin_big")}))
    assert outs(c, "kin_big stands with the runaway emp_big"), c
    # The master of a player's vassal.
    skips(_merge_world(**{"+pv": {"name": "pv", "regions": 2, "subculture": DWF,
                                  "human": True, "vassal_of": "kin_big"}}))
    # A player is never absorbed, whatever the probe says.
    assert merges(go(_merge_world(vic={"human": True}))[0]) == []
    # Chaos Dwarf houses never merge while a player plays a Chaos Dwarf faction.
    chd = _merge_world(vic={"subculture": CHD}, kin_big={"subculture": CHD},
                       kin_small={"subculture": CHD})
    assert merges(go(chd)[0]) == [("kin_big", "vic")]
    chd_p = chd + [{"name": "player", "regions": 2, "subculture": CHD, "human": True}]
    c, _ = go(chd_p)
    assert merges(c) == [] and outs(c, "a player plays the Chaos Dwarfs"), c
    # The race switch, the first turn, the merge_last_stand switch.
    c, _ = go(mct={"race_wh_main_sc_grn_greenskins": False})
    assert merges(c) == [] and outs(c, "the race switch is off"), c
    # A race the game never lets confederate is refused before its switch is read.
    SAV = "wh_main_sc_grn_savage_orcs"
    c, _ = go(_merge_world(vic={"subculture": SAV}, kin_big={"subculture": SAV},
                           kin_small={"subculture": SAV}))
    assert merges(c) == [] and outs(c, "the game does not let this race confederate"), c
    c, _ = go(events=_merge_conq(turn=9))
    assert merges(c) == [] and outs(c, "no merge for vic: too early"), c
    # Said once a turn: a dozen last stands a turn before the first merge turn is normal.
    early = _merge_conq(turn=9) + [{"event": "RegionFactionChangeEvent", "instigator": "sacker",
                                    "victim": "vic2", "region": "r_vic2", "turn": 9}]
    c, _ = go(two, early)
    assert len(outs(c, "too early")) == 1, outs(c, "too early")
    assert merges(go(mct={"merge_last_stand": False})[0]) == []

    # Limits: one a turn, none at 0, free at price 0, and not on a budget that cannot pay.
    assert merges(go(two, ev2)[0]) == [("kin_big", "vic")]
    assert merges(go(two, ev2, mct={"merges_per_turn": 0})[0]) == []
    # The count is per turn: three merges on turn 5 leave turn 12's two slots free. Found live
    # 2026-11-14: the turn was saved before the count was read, so the count ran on from turn to turn.
    old = {"derpy_director_merge_turn": 5, "derpy_director_merge_count": 3}
    c, _ = go(two, ev2, mct={"merges_per_turn": 2}, preload=old)
    assert merges(c) == [("kin_big", "vic"), ("kin_big", "vic2")], outs(c, "merge")
    c, st = go(mct={"merge_price": 0})
    assert merges(c) == [("kin_big", "vic")] and budget(st) == off_budget(mct={"merge_price": 0})
    c, _ = go(events=_merge_conq(budget=59))
    assert merges(c) == [] and outs(c, "no merge for vic: budget 59 cannot pay 60"), c
    # At most 3 kin are asked: kin_d, fourth by size, is never reached once the first three refuse.
    four = _merge_world(**{"+kin_c": {"name": "kin_c", "regions": 2, "subculture": GRN},
                           "+kin_d": {"name": "kin_d", "regions": 1, "subculture": GRN}})
    assert merges(go(four, deny=both)[0]) == [("kin_c", "vic")]
    assert merges(go(four, deny=both + ["kin_c|vic"])[0]) == []
    # A refused last stand is tried once per victim a turn, not once per town that falls.
    c, _ = go(events=_merge_conq() + _merge_conq()[1:], deny=both)
    assert len(outs(c, "no merge for vic:")) == 1, outs(c, "no merge for vic:")

    # A province of three towns falls in one turn. The feud guard answers the first conquest only;
    # the last stand still runs on the second, when vic is down to 1.
    setr = lambda n: {"event": "SetRegions", "instigator": "vic", "n": n, "turn": 12}
    take = {"event": "RegionFactionChangeEvent", "instigator": "sacker", "victim": "vic",
            "region": "r_vic", "turn": 12}
    c, _ = go(_merge_world(vic={"regions": 3}),
              [{"event": "SetBudget", "n": 180, "turn": 12}, setr(2), take, setr(1), take,
               setr(0), take])
    assert merges(c) == [("kin_big", "vic")], merges(c)
    sits = [i for i, x in enumerate(c) if x[0] == "out" and "situation kind=conquest" in x[1]]
    pay = [i for i, x in enumerate(c) if x[0] == "apply_payload"][0]
    assert sits[1] < pay < sits[2], (sits, pay)
    assert outs(c, "already answered this feud this turn"), c

    # Review focus 1: a merge that throws charges nothing, takes no slot, and clears the own-merge
    # flag, so the next confederation in the turn is answered as a deed.
    after = [{"event": "FactionJoinsConfederation", "instigator": "kin_big", "victim": "vic",
              "turn": 12}]
    c, st = go(events=_merge_conq() + after, payload_error=True)
    assert merges(c) == [] and outs(c, "merge failed"), c
    assert st["derpy_director_merge_count"] == "nil", st
    assert budget(st) == off_budget(events=_merge_conq() + after, payload_error=True)
    assert outs(c, "situation kind=confederation instigator=kin_big victim=vic"), c
    # Review focus 5: CA's own confederation, the same turn as ours, is still a deed.
    others = _merge_world(**{"+oa": {"name": "oa", "regions": 3, "subculture": DWF},
                             "+ob": {"name": "ob", "regions": 3, "subculture": DWF}})
    c, _ = go(others, _merge_conq() + [{"event": "FactionJoinsConfederation", "instigator": "oa",
                                        "victim": "ob", "turn": 12}])
    assert merges(c) == [("kin_big", "vic")]
    assert outs(c, "situation kind=confederation instigator=oa victim=ob"), c

    # An Iron Court rising is recorded the moment the Director hears of it.
    court = [{"name": "realm", "regions": 6, "subculture": CHD},
             {"name": "rebels", "regions": 1, "subculture": CHD, "owns": ["r_x"]}]
    c, _ = run(court, events=[{"event": "Secession", "instigator": "realm", "victim": "rebels",
                               "region": "r_x", "turn": 12},
                              {"event": "Eval", "turn": 12, "code": "return (cm:get_saved_value("
                               "'derpy_director_risings') or {})['rebels']"}],
               regions_spec=MERGE_REGIONS, companions={"ic": True})
    assert evals(c) == ["true"], evals(c)
    print("selftest: merge ok")


def _selftest_poll():
    """30. The runaway step's alliance poll (2026-11-14), ported from the Coalition Supervisor but
    run through the pact machinery: the sum rule, at_odds, a price, at most 2 forced alliances per
    faction and at most 2 formed a turn.
    """
    run = lambda *a, **k: run_lua(*a, quiet_runaway=False, **k)
    DWF, GRN, EMP = "wh_main_sc_dwf_dwarfs", "wh_main_sc_grn_greenskins", "wh_main_sc_emp_empire"
    asks = lambda calls: [(c[1], c[2]) for c in calls if c[0] == "cai_evaluate_quick_deal_action"]
    forced = lambda calls: [(c[1], c[2]) for c in calls if c[0] == "force_alliance"]
    t1 = [{"event": "Tick", "turn": 1}]
    # leader 25 against p1's 10 is tier 2. p1 and p2 are the only pair.
    base = [{"name": "leader", "regions": 25, "subculture": EMP},
            {"name": "p1", "regions": 10, "subculture": DWF},
            {"name": "p2", "regions": 5, "subculture": DWF}]
    # Both directions are asked, and the line carries the can-propose flags.
    c, _ = run(base, events=t1)
    assert ("p1", "p2") in asks(c) and ("p2", "p1") in asks(c), asks(c)
    assert [l for l in outs(c, "ask p1<->p2") if "ok=" in l], c
    # The SUM rule, as pacts use: -5 and 8 forms, -5 and 4 does not.
    c, _ = run(base, events=t1, scores={"p1|p2": -5, "p2|p1": 8})
    assert forced(c) == [("p1", "p2")], forced(c)
    c, _ = run(base, events=t1, scores={"p1|p2": -5, "p2|p1": 4})
    assert forced(c) == [], forced(c)
    # A pair that has not met EACH OTHER is never asked and does not use up the batch: far0-far8
    # sort ahead of near_a/near_b, and only the near pair has met.
    far = [{"name": "far%d" % i, "regions": 3, "subculture": DWF, "met": ["leader"]}
           for i in range(9)]
    near = [{"name": "near_a", "regions": 3, "subculture": DWF, "met": ["leader", "near_b"]},
            {"name": "near_b", "regions": 3, "subculture": DWF, "met": ["leader", "near_a"]}]
    w = [{"name": "leader", "regions": 25, "subculture": EMP},
         {"name": "second", "regions": 10, "subculture": EMP, "met": []}] + far + near
    c, _ = run(w, events=t1)
    assert asks(c) == [("near_a", "near_b"), ("near_b", "near_a")], asks(c)
    # Determinism: the same world listed in another order gives the same calls. The engine's
    # faction order is not something to lean on, so every choice here goes through a sort.
    assert run(w, events=t1)[0] == run(w[:1] + w[1:][::-1], events=t1)[0]
    willing = {"p1|p2": 5, "p2|p1": 5}
    # A faction already in 2 forced alliances is not a candidate at all.
    held = {"derpy_director_runaway": {"alliances": {"p1": 2}}}
    c, _ = run(base, events=t1, scores=willing, preload=held)
    assert asks(c) == [] and forced(c) == [], c
    # ...and takes no slot in the batch of 8: a0 sorts first and pairs with all five others, so
    # its five pairs would leave room for only three real ones. Unwilling, so nothing forms early.
    six = [{"name": "leader", "regions": 25, "subculture": EMP},
           {"name": "a0", "regions": 10, "subculture": DWF}] + [
        {"name": "a%d" % i, "regions": 4, "subculture": DWF} for i in range(1, 6)]
    sour = {"a%d|a%d" % (i, j): -5 for i in range(6) for j in range(6) if i != j}
    c, _ = run(six, events=t1, scores=sour,
               preload={"derpy_director_runaway": {"alliances": {"a0": 2}}})
    assert len(asks(c)) == 16 and not [p for p in asks(c) if "a0" in p], asks(c)
    # An existing alliance, defensive or military, is never re-forced or asked about.
    for kind in ("allies", "military"):
        allied = [dict(f, **{kind: ["p2"]}) if f["name"] == "p1" else f for f in base]
        c, _ = run(allied, events=t1, scores=willing)
        assert asks(c) == [] and forced(c) == [], (kind, c)
    # A human is never a candidate.
    human = [dict(f, human=(f["name"] == "p2")) for f in base]
    c, _ = run(human, events=t1, scores=willing)
    assert asks(c) == [], asks(c)
    # A pair at odds is logged and not asked: Dwarfs and Greenskins hate each other.
    odds = [dict(f, subculture=GRN) if f["name"] == "p2" else f for f in base]
    c, _ = run(odds, events=t1, scores=willing)
    assert asks(c) == [] and outs(c, "no ask p1<->p2"), c
    # Five willing pairs: 2 form in the turn, each paid 15 out of the budget.
    five = [{"name": "leader", "regions": 25, "subculture": EMP}] + [
        {"name": "q%d" % i, "regions": 4 if i else 10, "subculture": DWF} for i in range(4)]
    yes_all = {"q%d|q%d" % (a, b): 5 for a in range(4) for b in range(4) if a != b}
    c, st = run(five, events=t1, scores=yes_all)
    _, off = run(five, events=t1, scores=yes_all, mct={"runaway_alliances": False})
    assert len(forced(c)) == 2, forced(c)
    assert int(off["derpy_director_budget"]) - int(st["derpy_director_budget"]) == 30, (off, st)
    # q0 already holds one forced alliance: it takes one more this turn, never two.
    c, _ = run(five, events=t1, scores=yes_all,
               preload={"derpy_director_runaway": {"alliances": {"q0": 1}}})
    assert len(forced(c)) == 2 and sum("q0" in p for p in forced(c)) == 1, forced(c)
    # No budget, no alliance.
    c, _ = run(base, events=t1, scores=willing, preload={"derpy_director_budget": -100})
    assert forced(c) == [] and outs(c, "cannot afford 15"), c
    # Switched off, nothing is asked.
    c, _ = run(base, events=t1, scores=willing, mct={"runaway_alliances": False})
    assert asks(c) == [], asks(c)
    print("selftest: poll ok")


def _runaway_world(leader=25, second=10):
    """A leader, a runner-up and two more who have all met each other. 25 against 10 is ratio 2.5,
    tier 2, threat score 350."""
    EMP, DWF = "wh_main_sc_emp_empire", "wh_main_sc_dwf_dwarfs"
    return [{"name": "leader", "regions": leader, "subculture": EMP},
            {"name": "second", "regions": second, "subculture": DWF},
            {"name": "c1", "regions": 5, "subculture": DWF},
            {"name": "c2", "regions": 5, "subculture": DWF}]


def _selftest_runaway():
    """29. The runaway step (2026-11-14), the Coalition Supervisor merged in: the leader by region
    count against the runner-up, a threat score per tier, released on the faction that carries it,
    and a grudge only when the tier rises. Ported from the Supervisor's builder, "rung" now "tier".
    """
    run = lambda *a, **k: run_lua(*a, quiet_runaway=False, **k)
    W1 = [{"name": "a", "regions": 1, "subculture": "wh_main_sc_dwf_dwarfs"}]
    tier = lambda r, n, cur: evals(run(W1, events=[{"event": "Eval",
               "code": "return derpy_director:tier_for(%s, %d, %d)" % (r, n, cur)}])[0])[0]
    assert [tier(r, 10, 0) for r in (1.74, 1.75, 2.5, 4.0)] == ["0", "1", "2", "3"]
    assert tier(1.5, 10, 2) == "1" and tier(1.5, 10, 3) == "1"      # held at the minimum tier
    assert tier(1.5, 10, 0) == "0" and tier(1.34, 10, 2) == "0"     # never starts; exits below 1.35
    assert tier(4.0, 9, 0) == "0"                                   # runaway_min_regions 10
    W1m = lambda: evals(run(W1, mct={"runaway_min_regions": 9}, events=[{"event": "Eval",
               "code": "return derpy_director:tier_for(4.0, 9, 0)"}])[0])[0]
    assert W1m() == "3", W1m()

    scores = lambda calls: [(c[1], c[2]) for c in calls if c[0] == "set_base_strategic_threat_score"]
    grudges = lambda calls: [(c[1], c[2], c[3]) for c in calls if c[0] == "cai_add_diplomatic_event"]
    tick = lambda t: {"event": "Tick", "turn": t}
    setr = lambda who, n, t: {"event": "SetRegions", "instigator": who, "n": n, "turn": t}

    # The score lands on the leader at its tier's value, once, not every turn it holds.
    c, _ = run(_runaway_world(), events=[tick(3)])
    assert scores(c) == [("leader", "350")], scores(c)
    # The harness reports the event's turn for every catch-up turn start, so all three say 3.
    assert outs(c, "runaway turn=3 leader=leader regions=25 runner_up=10 ratio=2.50 tier=2"), c
    assert outs(c, "threat score 350 on leader")
    # Falling below the exit ratio releases it to 0, once.
    c, _ = run(_runaway_world(), events=[tick(2), setr("leader", 13, 2), tick(4)])
    assert scores(c) == [("leader", "350"), ("leader", "0")], scores(c)
    assert len(outs(c, "threat score released on leader")) == 1
    # A new leader: the old carrier is released BEFORE the new one is scored.
    c, _ = run(_runaway_world(), events=[tick(1), setr("second", 60, 1), tick(2)])
    assert scores(c) == [("leader", "350"), ("leader", "0"), ("second", "200")], scores(c)
    # Nobody else holds a region: a held score is released rather than leaked.
    lone = [dict(f, regions=(25 if f["name"] == "leader" else 0)) for f in _runaway_world()]
    held = {"derpy_director_runaway": {"tier": 2, "scored_key": "leader", "last_event_tier": 2,
                                       "cursor": 0, "alliances": {}}}
    c, _ = run(lone, events=[tick(1)], preload=held)
    assert scores(c) == [("leader", "0")], scores(c)
    # Switched off, the score is never set.
    c, _ = run(_runaway_world(), events=[tick(3)], mct={"runaway_threat": False})
    assert scores(c) == [], scores(c)
    # A load mid-runaway re-applies the saved score exactly once, and fires no new grudge.
    c, _ = run(_runaway_world(), events=[tick(2)], preload=held)
    assert scores(c) == [("leader", "350")], scores(c)
    assert grudges(c) == [], grudges(c)

    # The grudge: once per faction polled, sorted, the turn the tier first rises; never while it
    # holds; again after a fall and a fresh rise.
    once = [("leader", n, "PAST_EVENT_NEGATIVE_MINOR") for n in ("c1", "c2", "second")]
    c, _ = run(_runaway_world(), events=[tick(3)])
    assert grudges(c) == once, grudges(c)
    c, _ = run(_runaway_world(), events=[tick(2), setr("leader", 13, 2), tick(3),
                                             setr("leader", 25, 3), tick(4)])
    assert grudges(c) == once + once, grudges(c)
    # A rise with nobody to poll keeps its grudge for the first turn a pair has met, as the
    # Supervisor did. c1 and c2 have met only the leader until turn 2.
    strangers = [dict(f, met=["leader"]) for f in _runaway_world()]
    meet = {"event": "SetMet", "instigator": "c1", "met": ["leader", "c2"], "turn": 2}
    c, _ = run(strangers, events=[tick(1), meet, tick(3)])
    assert grudges(c) == [("leader", n, "PAST_EVENT_NEGATIVE_MINOR") for n in ("c1", "c2")], \
        grudges(c)
    # Switched off mid-campaign while the tier holds: the held score is released next turn, once.
    flip = {"event": "Eval", "turn": 2, "code": "MCT_VALUES.runaway_threat = false return 1"}
    c, _ = run(_runaway_world(), events=[tick(1), flip, tick(3), tick(4)],
               mct={"runaway_threat": True})
    assert scores(c) == [("leader", "350"), ("leader", "0")], scores(c)
    # A fault in the runaway step stays in it: the opportunity roll after it still runs.
    breaker = {"event": "Eval", "turn": 1, "code":
               "derpy_director.runaway_turn = function() error('stub: runaway fault') end "
               "local o = derpy_director.opportunity "
               "derpy_director.opportunity = function(self) out('opportunity ran') "
               "return o(self) end return 1"}
    c, _ = run(_runaway_world(), events=[breaker, tick(2)])
    assert outs(c, "runaway step errored") and outs(c, "opportunity ran"), outs(c, "")
    print("selftest: runaway ok")


def _selftest_mct():
    """28. The MCT page (2026-11-14): one list in this file generates the page and the reader's
    defaults, so the two cannot drift; the reader falls back on a wrong type and in multiplayer.
    """
    run = lambda *a, **k: run_lua(*a, quiet_runaway=False, **k)
    races = [sc for sc, _ in merge_races()]
    assert len(races) == 23, races
    for sc in ("wh3_dlc23_sc_chd_chaos_dwarfs", "wh2_dlc11_sc_cst_vampire_coast",
               "wh_main_sc_vmp_vampire_counts", "wh3_dlc29_sc_nag_undead_legions"):
        assert sc in races, sc
    for sc in ("wh2_dlc09_sc_tmb_tomb_kings", "wh_main_sc_chs_chaos",
               "wh_main_sc_grn_savage_orcs", "wh_main_sc_teb_teb", "wh2_main_rogue",
               "wh3_main_pro_sc_ksl_kislev"):
        assert sc not in races, sc
    page = open(MCT_PAGE, encoding="utf-8").read()
    assert page == mct_page(), "the MCT page is stale - run --check"
    # The page, run under a recording MCT stub, registers exactly MCT_OPTIONS plus one checkbox
    # per race, with these defaults.
    reg = run_mct_page()
    want = {o["key"]: (o["kind"], o["default"]) for o in MCT_OPTIONS}
    want.update({"race_" + sc: ("checkbox", True) for sc in races})
    assert reg == want, set(reg) ^ set(want)
    w = [{"name": "a", "regions": 1, "subculture": "wh_main_sc_dwf_dwarfs"}]
    ev = lambda k: [{"event": "Eval", "code": "return derpy_director:setting(%r)" % k}]
    get = lambda calls: evals(calls)
    assert get(run(w, events=ev("merge_price"))[0]) == ["60"]
    assert get(run(w, events=ev("merge_price"), mct={"merge_price": 90})[0]) == ["90"]
    # A wrong type falls back; multiplayer ignores MCT; races default on and read MCT.
    assert get(run(w, events=ev("merge_price"), mct={"merge_price": "90"})[0]) == ["60"]
    assert get(run(w, events=ev("merge_price"), mct={"merge_price": 90},
                       multiplayer=True)[0]) == ["60"]
    k = "race_wh_main_sc_grn_greenskins"
    assert get(run(w, events=ev(k))[0]) == ["true"]
    assert get(run(w, events=ev(k), mct={k: False})[0]) == ["false"]
    # A race CA forbids has no switch, so it reads as unknown, like any other unknown key.
    calls, _ = run(w, events=ev("race_wh_main_sc_chs_chaos"))
    assert get(calls) == ["nil"] and outs(calls, "unknown setting race_wh_main_sc_chs_chaos")
    assert get(run(w, events=ev("no_such_key"))[0]) == ["nil"]
    print("selftest: mct ok")


def _selftest_long_run(CHD, DWF, regions, pair_world, ev2, yes):
    """27. The long run (2026-11-14): answers sized to the aggressor, rising's ramp, a feud that
    can be remembered again once its grudge fades, and pact partners that might accept.
    """
    GRN = "wh_main_sc_grn_greenskins"
    outs = lambda calls, s: [x[1] for x in calls if x[0] == "out" and s in x[1]]
    grudges = lambda calls: [x for x in calls if x[0] == "cai_add_diplomatic_event"]
    asks = lambda calls: [(x[1], x[2]) for x in calls if x[0] == "cai_evaluate_quick_deal_action"]

    # Sizes follow the aggressor: 4 rebels and 2,500 gold up to 20 regions, one time more for
    # every 20 after, at most three times.
    conq_world = [
        {"name": "sacker", "regions": 20, "subculture": CHD, "owns": ["r_victim"]},
        {"name": "victim", "subculture": CHD, "regions": 3},
        {"name": "hold_a", "subculture": DWF, "owns": ["r_near"], "regions": 3},
    ]
    conq = [{"event": "RegionFactionChangeEvent", "instigator": "sacker", "victim": "victim",
             "region": "r_victim"}]
    def rebels(n):
        w = [dict(f) for f in conq_world]
        w[0]["regions"] = n
        c, _ = run_lua(w, events=conq, regions_spec=regions)
        return [x[3] for x in c if x[0] == "force_rebellion_with_faction"]
    sizes = [rebels(n) for n in (20, 30, 40, 60, 100)]
    assert sizes == [["4"], ["6"], ["8"], ["12"], ["12"]], sizes
    def chest(n):
        w = [dict(f) for f in pair_world]
        w[0]["regions"] = n
        c, _ = run_lua(w, events=ev2, regions_spec=regions, scores=yes)
        return sorted(x[2] for x in c if x[0] == "treasury_mod")
    assert chest(20) == ["2500", "2500"] and chest(40) == ["5000", "5000"], (chest(20), chest(40))
    assert chest(80) == ["7500", "7500"], chest(80)

    # Rising ramps: its ON-turn refill of 70 is 1.5 times at turn 51, twice at 101, and held at 2.5
    # times from 151. The ceiling grows with it. Patient and wild do not ramp.
    rise = dict(TEST_SEED)
    def budget_at(turn, start, seed_tbl=rise):
        evs = [{"event": "SetBudget", "n": start, "turn": turn - 1}, {"event": "Tick", "turn": turn}]
        _, st = run_lua(pair_world, events=evs, regions_spec=regions,
                        preload={"derpy_director_seed": seed_tbl})
        return st["derpy_director_budget"]
    got = [budget_at(51, 0), budget_at(101, 0), budget_at(201, 0)]
    assert got == ["105", "140", "175"], got
    assert budget_at(101, 300) == "360" and budget_at(201, 400) == "450"
    assert budget_at(101, 0, dict(rise, temperament="patient", phase=8)) == "70"
    assert budget_at(101, 0, dict(rise, temperament="wild")) == "20"
    # The chance reads the ramped ceiling: 180 of turn 101's 360 is half full, 63% for kin.
    evs = [{"event": "SetBudget", "n": 180, "turn": 101}, dict(ev2[0], turn=101)]
    c, _ = run_lua(pair_world, events=evs, regions_spec=regions, seed=100)
    assert outs(c, "passed over: rolled 100 against 63%"), outs(c, "over:")

    # A feud's grudge is remembered for 50 turns, CA's falloff, then the feud can earn another.
    seen = "derpy_director_seen_sacker_victim"
    def feud(turns, preload=None):
        c, _ = run_lua(pair_world, events=[dict(ev2[0], turn=t) for t in turns],
                       regions_spec=regions, preload=preload or {})
        return c
    c = feud([1, 50])
    assert len(grudges(c)) == 1 and outs(c, "grudge from turn 1 is still remembered"), c
    c = feud([1, 51])
    assert len(grudges(c)) == 2 and outs(c, "grudge from turn 1 has faded"), c
    # The mark holds the turn it fired, not just that it fired.
    c = feud([5, 54])
    assert len(grudges(c)) == 1 and outs(c, "grudge from turn 5 is still remembered"), c
    # A save from before 2026-11-14 holds true, read as turn 1.
    c = feud([50], {seen: True})
    assert not grudges(c) and outs(c, "grudge from turn 1 is still remembered"), c
    assert len(grudges(feud([51], {seen: True}))) == 1

    # Pact partners. Responders who hate each other are not asked: Dwarfs and Greenskins both
    # read -100 toward the Chaos Dwarfs, and -100 toward each other.
    mixed = [
        {"name": "sacker", "regions": 20, "subculture": CHD},
        {"name": "victim", "subculture": CHD, "owns": ["r_victim"], "regions": 3},
        {"name": "hold_a", "subculture": DWF, "owns": ["r_near"], "regions": 3},
        {"name": "hold_g", "subculture": GRN, "owns": ["r_near"], "regions": 3},
    ]
    c, _ = run_lua(mixed, events=ev2, regions_spec=regions)
    assert not asks(c), asks(c)
    assert [l for l in outs(c, "no ask ") if "hold_a" in l and "hold_g" in l], c
    # Nor is a pair at war, whichever side's list holds the war.
    warring = [dict(f) for f in pair_world]
    warring[3] = dict(warring[3], wars=["hold_a"])
    c, _ = run_lua(warring, events=ev2, regions_spec=regions, scores=yes)
    assert not asks(c) and not [x for x in c if x[0] == "treasury_mod"], c
    # The victim is a partner: already at war with the aggressor, which a lone responder shares.
    kin = [
        {"name": "sacker", "regions": 20, "subculture": CHD},
        {"name": "victim", "subculture": DWF, "owns": ["r_victim"], "regions": 3},
        {"name": "hold_a", "subculture": DWF, "owns": ["r_near"], "regions": 3},
    ]
    both = {"hold_a|victim": 5, "victim|hold_a": 5}
    c, _ = run_lua(kin, events=ev2, regions_spec=regions, scores=both)
    assert ("hold_a", "victim") in asks(c) and ("victim", "hold_a") in asks(c), asks(c)
    assert outs(c, "forced defensive alliance hold_a + victim"), c
    assert sorted(x[1] for x in c if x[0] == "treasury_mod") == ["hold_a", "victim"], c
    # Hatred is read BOTH ways. Wood Elves rate Dwarfs -20 and Dwarfs rate Wood Elves -40, so a
    # Wood Elf responder and a Dwarf victim are not asked, though the first direction alone allows it.
    lopsided = [dict(f) for f in kin]
    lopsided[2] = dict(lopsided[2], subculture="wh_dlc05_sc_wef_wood_elves")
    c, _ = run_lua(lopsided, events=ev2, regions_spec=regions, scores=both)
    assert outs(c, "cast hold_a") and not asks(c), asks(c)
    # A player victim is never forced into a treaty.
    human = [dict(f, human=(f["name"] == "victim")) for f in kin]
    c, _ = run_lua(human, events=ev2, regions_spec=regions, scores=both)
    assert not asks(c), asks(c)
    print("selftest: long run ok")


def _selftest_storyteller(CHD, DWF, EMP, regions, pair_world, feud_world, ev2, yes, conq_world,
                          conq):
    """26. The storyteller (2026-11-14), after RimWorld's: the campaign seed, the temperament's
    pacing, the chance of an answer, the weighted draw, adaptation, opportunism and treachery.
    """
    HEF = "wh2_main_sc_hef_high_elves"
    BST = "wh_dlc03_sc_bst_beastmen"
    outs = lambda calls, s: [x[1] for x in calls if x[0] == "out" and s in x[1]]
    casts = lambda calls: [x[1][len("[director] cast "):] for x in calls if x[0] == "out"
                           and x[1].startswith("[director] cast ")]
    sits = lambda calls: [x[1] for x in calls if x[0] == "out" and "situation kind=" in x[1]]
    shown = lambda calls: [x for x in calls if x[0].startswith("show_message_event")]
    tick = [{"event": "Tick", "turn": 1}]
    roll = {"derpy_director_seed": False}

    # The seed: rolled once, from the world as it stands, and named to the player at the capital.
    home = [{"key": "r_home", "adj": [], "pos": [30, 40]}] + regions
    seed_world = [
        {"name": "aa_dead", "subculture": DWF, "regions": 3, "dead": True},
        {"name": "ab_landless", "subculture": DWF, "regions": 0},
        {"name": "ac_player", "subculture": EMP, "owns": ["r_home"], "regions": 4, "human": True},
        {"name": "ba_chd", "subculture": CHD, "regions": 3},
        {"name": "bb_dwf", "subculture": DWF, "regions": 3},
        {"name": "bc_dwf", "subculture": DWF, "regions": 2},
    ]
    c, _ = run_lua(seed_world, preload=roll, regions_spec=home)
    rolled = outs(c, "seed rolled:")
    assert rolled and "temperament=rising phase=0" in rolled[0], c
    # The first pair, sorted, that hates BOTH ways: Chaos Dwarfs and Dwarfs. Dwarfs and Empire
    # are friends, and are never a hot grudge.
    assert "hot=%s/%s " % (CHD, DWF) in rolled[0], rolled
    # Three ambitious factions, never the player, the dead or the landless.
    assert rolled[0].endswith("ambitious=ba_chd,bb_dwf,bc_dwf"), rolled
    told = shown(c)
    assert len(told) == 1 and told[0][1] == "ac_player" and told[0][3] == "30,40|false|7800" \
        and told[0][2].endswith("temper_rising_title"), told
    for dice, name, idx in ((2, "patient", 7801), (3, "wild", 7802)):
        c, _ = run_lua(seed_world, preload=roll, regions_spec=home, seed=dice)
        assert "temperament=%s" % name in outs(c, "seed rolled:")[0], c
        assert [x for x in shown(c) if x[3].endswith("|%d" % idx)], (name, shown(c))
    # A hatred one way only is no hot grudge: Chaos Dwarfs read -40 to Beastmen, Beastmen -10 back.
    # No Empire player here: Empire and Chaos Dwarfs read -40 both ways, a hot pair of their own.
    c, _ = run_lua([{"name": "ba_chd", "subculture": CHD, "regions": 3},
                    {"name": "bd_bst", "subculture": BST, "regions": 3}],
                   preload=roll, regions_spec=home)
    assert "hot= " in outs(c, "seed rolled:")[0], c
    # A reload finds the seed: no roll, no second message, and no budget paid out for loading.
    c, state = run_lua(seed_world, regions_spec=home, preload={"derpy_director_budget": 50})
    assert not outs(c, "seed rolled:") and not shown(c), c
    assert state["derpy_director_budget"] == "50", state
    # No capital to point at, nobody told; the seed is still rolled.
    homeless = [dict(r) for r in home]
    homeless[0] = {"key": "r_home", "adj": [], "pos": None}
    c, _ = run_lua(seed_world, preload=roll, regions_spec=homeless)
    assert outs(c, "seed rolled:") and not shown(c), c

    # Pacing. A turn's refill by temperament and phase, from an empty budget.
    def budget_after(seed_tbl, dice=1):
        _, st = run_lua(seed_world, events=tick, regions_spec=home, seed=dice,
                        preload={"derpy_director_seed": seed_tbl, "derpy_director_budget": 0})
        return st["derpy_director_budget"]
    rise = dict(TEST_SEED)
    pat = dict(TEST_SEED, temperament="patient")
    wild = dict(TEST_SEED, temperament="wild")
    assert budget_after(rise) == "70" and budget_after(dict(rise, phase=6)) == "30"
    assert budget_after(pat) == "70" and budget_after(dict(pat, phase=3)) == "20"
    assert budget_after(wild, 1) == "20" and budget_after(wild, 100) == "100"

    # The chance of an answer. Chaos Dwarfs sacking Dwarfs is sworn enemies, 0.25 of the
    # kin-slaying 1.5: a 17% chance between strangers, three times that with the player a party.
    # On turn 2, because turn 1 has its own damping, tested below.
    sworn = [dict(f) for f in pair_world]
    sworn[1]["subculture"] = DWF
    turn2 = [dict(ev2[0], turn=2)]
    def chance(world, dice=100, events=turn2, **kw):
        cc, _ = run_lua(world, events=events, regions_spec=regions, seed=dice, **kw)
        return outs(cc, "passed over:") + outs(cc, "answered:"), cc
    lines, c = chance(sworn)
    assert lines == ["[director] passed over: rolled 100 against 17%"], lines
    assert not [x for x in c if x[0] == "stance_promote"], "a situation passed over spends nothing"
    party = [dict(f, human=(f["name"] == "victim")) for f in sworn]
    assert chance(party)[0] == ["[director] passed over: rolled 100 against 50%"]
    assert chance(pair_world)[0] == ["[director] answered: rolled 100 against 100%"]
    # The calm answers at 0.4 of it; a thin budget at no less than a quarter.
    calm = {"derpy_director_seed": dict(rise, phase=6)}
    assert chance(pair_world, preload=calm)[0] == ["[director] passed over: rolled 100 against 40%"]
    thin = [{"event": "SetBudget", "n": 70, "turn": 2}] + turn2
    assert chance(pair_world, events=thin)[0] == \
        ["[director] passed over: rolled 100 against 54%"]
    # A budget that cannot pay even a stance push would answer and do nothing, so it is passed
    # over without a roll. Five pays for one, so five still rolls.
    empty = [{"event": "SetBudget", "n": 4, "turn": 2}] + turn2
    lines, c = chance(pair_world, events=empty, dice=1)
    assert lines == ["[director] passed over: budget 4 cannot pay for anything"], lines
    assert not casts(c) and not outs(c, "cannot afford"), c
    lines, c = chance(pair_world, events=[dict(empty[0], n=5)] + turn2, dice=1)
    assert lines == ["[director] answered: rolled 1 against 27%"], lines
    assert [x for x in c if x[0] == "stance_promote"], c
    # The push spends all five, so the grudge after it is refused by the beat's own price check.
    assert outs(c, "budget 0 cannot afford 40") and \
        not [x for x in c if x[0] == "cai_add_diplomatic_event"], c
    # Turn 1 is the start position's wars all at once: the world's own quarrels are answered at a
    # third of the chance, a player's at the full one.
    first = [dict(ev2[0], turn=1)]
    assert chance(pair_world, events=first)[0] == \
        ["[director] passed over: rolled 100 against 33%"]
    assert chance(party, events=first)[0] == ["[director] passed over: rolled 100 against 50%"]
    # A feud passed over is decided for the turn: the next town is not a second roll.
    lines, c = chance(sworn, events=[dict(ev2[0], turn=1), dict(ev2[0], turn=1)])
    assert len(lines) == 1 and outs(c, "already answered this feud"), c

    # The weighted draw. Two holds equal on every term weigh 2000 each (200 in tenths), so after
    # the chance roll a draw of 2000 takes the first by name and 2001 the second.
    c, _ = run_lua(pair_world, events=ev2, regions_spec=regions, seed=[1, 2000, 1])
    assert casts(c) == ["hold_a, hold_b"], casts(c)
    c, _ = run_lua(pair_world, events=ev2, regions_spec=regions, seed=[1, 2001, 1])
    assert casts(c) == ["hold_b, hold_a"], casts(c)

    # The hot grudge doubles a responder's score, whichever way round the pair was stored. High
    # Elves score 150 against Chaos Dwarfs and Dwarfs 200, so doubling the elves puts them first.
    hot_world = [
        {"name": "sacker", "regions": 20, "subculture": CHD},
        {"name": "victim", "subculture": CHD, "owns": ["r_victim"], "regions": 3},
        {"name": "aa_dwf", "subculture": DWF, "owns": ["r_near"], "regions": 3},
        {"name": "zz_hef", "subculture": HEF, "owns": ["r_near"], "regions": 3},
    ]
    c, _ = run_lua(hot_world, events=ev2, regions_spec=regions)
    assert casts(c) == ["aa_dwf, zz_hef"], casts(c)
    for pair in ([CHD, HEF], [HEF, CHD]):
        c, _ = run_lua(hot_world, events=ev2, regions_spec=regions,
                       preload={"derpy_director_seed": dict(TEST_SEED, hot=pair)})
        assert casts(c) == ["zz_hef, aa_dwf"], (pair, casts(c))
    # An ambitious faction scores half again and is back in half the cooldown: hold_b leads, takes
    # the grudge on turn 1, and is cast again on turn 7, when rising's twelve turns would bar it.
    amb = {"derpy_director_seed": dict(TEST_SEED, ambitious=["hold_b"])}
    c, _ = run_lua(pair_world, events=ev2, regions_spec=regions, preload=amb)
    assert casts(c) == ["hold_b, hold_a"], casts(c)
    later = [dict(ev2[0], turn=1), dict(ev2[0], turn=7, victim="victim2")]
    c, _ = run_lua(feud_world, events=later, regions_spec=regions, preload=amb)
    assert [x for x in c if x[0] == "cai_add_diplomatic_event" and x[2] == "hold_b"], c
    assert "hold_b" in casts(c)[1], casts(c)
    c, _ = run_lua(feud_world, events=later, regions_spec=regions)
    assert "hold_a" not in casts(c)[1], "rising's twelve-turn cooldown: %s" % casts(c)
    # A wild world's cooldown is eight: the turn-1 grudge's responder is back on turn 10.
    wild_seed = {"derpy_director_seed": wild}
    later10 = [dict(ev2[0], turn=1), dict(ev2[0], turn=10, victim="victim2")]
    c, _ = run_lua(feud_world, events=later10, regions_spec=regions, preload=wild_seed)
    first = casts(c)[0].split(", ")[0]
    assert first in casts(c)[1], casts(c)
    # A wild world swings the cast one either way (the first die is the turn's refill), and pays
    # 50 to 150 percent of a war chest.
    three = pair_world + [{"name": "hold_c", "subculture": DWF, "owns": ["r_near"], "regions": 3}]
    c, _ = run_lua(three, events=ev2, regions_spec=regions, preload=wild_seed)
    assert len(casts(c)[0].split(", ")) == 2, casts(c)
    c, _ = run_lua(three, events=ev2, regions_spec=regions, preload=wild_seed, seed=[50, 1, 2, 1])
    assert len(casts(c)[0].split(", ")) == 3, casts(c)
    c, _ = run_lua(pair_world, events=ev2, regions_spec=regions, preload=wild_seed, scores=yes,
                   seed=[50, 1, 2, 1, 1, 150])
    assert [x[2] for x in c if x[0] == "treasury_mod"] == ["3750", "3750"], c
    c, _ = run_lua(pair_world, events=ev2, regions_spec=regions, preload=wild_seed, scores=yes)
    assert [x[2] for x in c if x[0] == "treasury_mod"] == ["1250", "1250"], c

    # Adaptation. The player loses five regions on turn 2: at turn 3's start that is -75, held
    # at -60, so the world turns on them at 0.4 of the chance - 20% where it was 50%.
    adapt_world = [dict(f, human=(f["name"] == "sacker")) for f in sworn]
    lost = [{"event": "SetRegions", "instigator": "sacker", "n": 15, "turn": 2},
            dict(ev2[0], turn=3)]
    lines, c = chance(adapt_world, events=lost)
    assert outs(c, "adapt sacker -5 regions, now -60"), c
    assert lines == ["[director] passed over: rolled 100 against 20%"], lines
    # It drifts back five a turn: -50 by turn 5.
    lines, _ = chance(adapt_world, events=lost[:1] + [dict(ev2[0], turn=5)])
    assert lines == ["[director] passed over: rolled 100 against 25%"], lines
    # Ten gained is +30: 65%.
    gained = [dict(lost[0], n=30), dict(ev2[0], turn=3)]
    assert chance(adapt_world, events=gained)[0] == \
        ["[director] passed over: rolled 100 against 65%"]
    # A struggling player who is the VICTIM is helped more readily: 1.6 times, 80%.
    vic_world = [dict(f, human=(f["name"] == "victim")) for f in sworn]
    vic_world[1]["regions"] = 5
    vic_lost = [{"event": "SetRegions", "instigator": "victim", "n": 1, "turn": 2},
                dict(ev2[0], turn=3)]
    assert chance(vic_world, events=vic_lost)[0] == \
        ["[director] passed over: rolled 100 against 80%"]

    # Opportunism: at a turn start, a faction that lost ground last round is the target, and the
    # neighbours who already hated it turn on it. Whoever took the most from it hears of it, once.
    opp_world = [
        {"name": "taker", "regions": 10, "subculture": DWF, "human": True},
        {"name": "weak", "subculture": CHD, "owns": ["r_victim"], "regions": 3},
        {"name": "weak2", "subculture": CHD, "owns": ["r_mid"], "regions": 3},
        {"name": "hold_a", "subculture": DWF, "owns": ["r_near"], "regions": 3},
        {"name": "hold_b", "subculture": DWF, "owns": ["r_near"], "regions": 3},
    ]
    one_loss = {"weak": {"n": 2, "by": {"aa_minor": 1, "taker": 2}}}
    c, _ = run_lua(opp_world, events=tick, regions_spec=regions, scores=yes,
                   preload={"derpy_director_losses": one_loss})
    s = sits(c)
    assert len(s) == 1 and "kind=opportunism instigator=weak victim=taker region=r_victim" \
        in s[0] and "outrage=1.00 (weakness)" in s[0], s
    assert {x[2] for x in c if x[0] == "stance_promote"} == {"weak"}, c
    told = shown(c)
    assert len(told) == 1 and told[0][1] == "taker" and told[0][3].endswith("|7900"), told
    # The clock's chance: 25% on a rising ON turn, 10% in the calm.
    c, _ = run_lua(opp_world, events=tick, regions_spec=regions, seed=100,
                   preload={"derpy_director_losses": one_loss})
    assert outs(c, "no opportunity this turn: rolled 100 against 25%") and not sits(c), c
    c, _ = run_lua(opp_world, events=tick, regions_spec=regions, seed=100,
                   preload={"derpy_director_losses": one_loss,
                            "derpy_director_seed": dict(rise, phase=6)})
    assert outs(c, "against 10%"), c
    # Drawn by settlements lost: weak lost 1 and weak2 3, so a draw of 2 is weak2's.
    two_loss = {"weak": {"n": 1, "by": {"taker": 1}}, "weak2": {"n": 3, "by": {"taker": 3}}}
    c, _ = run_lua(opp_world, events=tick, regions_spec=regions, seed=[1, 2, 1],
                   preload={"derpy_director_losses": two_loss})
    assert "instigator=weak2 " in sits(c)[0], sits(c)
    # The player is never the target, and last round's losses do not carry into the next.
    c, _ = run_lua(opp_world, events=tick, regions_spec=regions,
                   preload={"derpy_director_losses": {"taker": {"n": 5, "by": {"weak": 5}}}})
    assert not sits(c) and not outs(c, "opportunity"), c
    c, _ = run_lua(opp_world, events=tick + [{"event": "Tick", "turn": 2}],
                   regions_spec=regions, preload={"derpy_director_losses": one_loss})
    assert len(sits(c)) == 1, sits(c)
    # A conquest counts toward it on its own: taken on turn 1, the loser is the target on turn 2.
    c, _ = run_lua(conq_world, events=conq + [{"event": "Tick", "turn": 2}],
                   regions_spec=regions)
    assert [x for x in sits(c) if "kind=opportunism instigator=victim victim=sacker" in x], \
        sits(c)

    # Treachery: breaking an alliance or a non-aggression pact is a situation at the betrayed
    # faction's home, never a shrug (Chaos Dwarfs and Dwarfs are sworn enemies, here 1.00), and
    # told once with its own record. A plain declaration of war, ending trade and a
    # confederation's dissolved treaties are none of it, and not a log line each either.
    betray_world = [
        {"name": "traitor", "regions": 10, "subculture": CHD},
        {"name": "betrayed", "subculture": DWF, "owns": ["r_victim"], "regions": 3, "human": True},
        {"name": "hold_a", "subculture": DWF, "owns": ["r_near"], "regions": 3},
        {"name": "hold_b", "subculture": DWF, "owns": ["r_near"], "regions": 3},
    ]
    broke_ev = [{"event": "NegativeDiplomaticEvent", "instigator": "traitor",
                 "victim": "betrayed", "treaty": "was_defensive_alliance"}]
    c, _ = run_lua(betray_world, events=broke_ev, regions_spec=regions, scores=yes)
    s = sits(c)
    assert len(s) == 1 and "kind=treachery instigator=traitor victim=betrayed region=r_victim" \
        in s[0] and "outrage=1.00 (betrayal)" in s[0], s
    told = shown(c)
    assert len(told) == 1 and told[0][1] == "betrayed" and told[0][3].endswith("|8000"), told
    for treaty in ("was_alliance", "was_military_alliance", "was_non_aggression_pact"):
        c, _ = run_lua(betray_world, events=[dict(broke_ev[0], treaty=treaty)],
                       regions_spec=regions)
        assert sits(c), treaty
    for quiet in ({"treaty": None}, {"treaty": "was_trade_agreement"},
                  {"treaty": "was_military_access"}, {"reason": "confederation"}):
        c, _ = run_lua(betray_world, events=[dict(broke_ev[0], **quiet)], regions_spec=regions)
        assert not sits(c) and not outs(c, "dropped"), (quiet, c)
    print("selftest: storyteller ok")


def pack():
    """Create or refresh derpy_director.pack. Needs rpfm_server, which starts itself."""
    import datetime
    import shutil
    from rpfm_client import call, ensure_game, exists, new_pack, open_pack

    _selftest()

    # The feed tables are created at explicit versions, so nothing here needs the vanilla data.
    ensure_game()

    if os.path.exists(PACK):
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(PACK, "%s.bak_%s" % (PACK, stamp))
        print("backed up the existing pack")
        key = open_pack(PACK)
    else:
        key = new_pack()

    call("add_files_from_disk", {"pack": key, "paths": [SCRIPT, LORE, MCT_PAGE],
                                 "pack_paths": [IN_PACK, IN_PACK_LORE, IN_PACK_MCT]})

    # The feed's five tables and its loc. create_file makes the empty fragment (a refreshed pack
    # already has it), import_tsv fills it - and import_tsv REPLACES the whole file, so the TSV
    # must always carry every row the fragment should end up with, never just the new ones.
    check_feed()
    for path, kind, tsv in write_feed_tsvs():
        if not exists(key, path):
            call("create_file", {"pack": key, "path": path, "kind": kind})
        call("import_tsv", {"pack": key, "path": path, "tsv_path": tsv})
        print("  imported %s" % path)

    call("save_pack", {"pack": key, "path": PACK})
    print("saved %s" % PACK)

    # A file that is merely present proves nothing. Re-open the SAVED pack and read it back -
    # with the build pack closed first, so the second key is the file on disk and not the one in
    # memory. exists() matches the exact path among list_files' prefix hits.
    call("close_pack", {"pack": key})
    again = open_pack(PACK)
    wanted = [IN_PACK, IN_PACK_LORE, IN_PACK_MCT, "text/db/%s.loc" % FRAG]
    wanted += ["db/%s_tables/%s" % (t, FRAG) for t, _v in FEED_TABLES]
    missing = [w for w in wanted if not exists(again, w)]
    assert not missing, "not in the saved pack: %s" % missing
    print("verified: all %d files are in the saved pack" % len(wanted))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    elif "--check" in sys.argv:
        check()
    else:
        pack()
