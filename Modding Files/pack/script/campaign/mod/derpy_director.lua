-- The Director. Watches for situations, decides who would plausibly care, and changes inputs the
-- campaign AI already reads. Since 2026-11-14 it also carries the Coalition Supervisor's runaway
-- step (the threat score's only writer) and decides confederations. See
-- docs/superpowers/specs/2026-09-16-ai-director-design.md and
-- docs/superpowers/specs/2026-11-14-director-merges-coalitions-design.md

local ENABLED = true
local LOG_PREFIX = "[director]"

derpy_director = {
	loaded = false,
}

local function log(msg)
	out(LOG_PREFIX .. " " .. msg)
end
derpy_director.log = log

-- Each event names the builder that reads its context; contexts come from CA's docs, never guessed.
-- FactionLeaderDeclaresWar is absent: its context names the declarer but not the target.
local WATCHED = {
	{event = "CharacterSackedSettlement", build = "from_settlement", kind = "sack"},
	{event = "CharacterRazedSettlement", build = "from_settlement", kind = "raze"},
	{event = "RegionFactionChangeEvent", build = "from_region_change", kind = "conquest"},
	{event = "FactionJoinsConfederation", build = "from_confederation", kind = "confederation"},
	{event = "NegativeDiplomaticEvent", build = "from_treaty_broken", kind = "treachery"},
}

local CAST_TAKE = 3
local NEUTRAL = {0, 1, 1}

-- CA's campaign_cultural_relations, baked at build time. Read lazily: the lore file sorts after
-- this one, so the global is still nil at file scope.
function derpy_director:hatred(source, target)
	local tbl = derpy_director_lore
	if not tbl then return NEUTRAL[1], NEUTRAL[2], NEUTRAL[3] end
	local row = tbl[source]
	if not row then return NEUTRAL[1], NEUTRAL[2], NEUTRAL[3] end
	local cell = row[target]
	if not cell then return NEUTRAL[1], NEUTRAL[2], NEUTRAL[3] end
	return cell[1], cell[2], cell[3]
end

-- The AI's assist distances are 3.0 on all 78 personalities; it never sends help further.
local MAX_HOPS = 3
local WAR_PENALTY = 0.25

local STANCE_HOSTILE = "CAI_STRATEGIC_STANCE_VERY_UNFRIENDLY"
local STANCE_FRIENDLY = "CAI_STRATEGIC_STANCE_FRIENDLY"

-- How wrong the deed was: how much the aggressor's culture already hates the victim's. Same
-- culture is kin-slaying. The thresholds are guesses; the shape is measured.
local OUTRAGE_KIN = 1.5
local OUTRAGE_STEPS = {
	{-75, 0.25},   -- sworn enemies: this is what they are for
	{-25, 0.60},
	{0, 0.85},
}
local OUTRAGE_UNPROVOKED = 1.0
-- A seized convoy is a lesser deed than a sacked town, so its outrage counts at half: only kin
-- and the unprovoked clear the grudge floor, and the audience is smaller.
local OUTRAGE_WEIGHT = {seizure = 0.5}

-- With the Great Guilds installed, a faction whose faith condemns kin-slaying loses Reputation
-- with its temple. Chaos Dwarfs, Dark Elves, Skaven and the Warriors of Chaos knife their own as a
-- matter of course, so their temples say nothing. Keyed on the slayer's subculture.
local KIN_CONDEMNED = {
	["wh_main_sc_brt_bretonnia"] = true, ["wh_main_sc_dwf_dwarfs"] = true,
	["wh_main_sc_emp_empire"] = true, ["wh2_main_sc_hef_high_elves"] = true,
	["wh3_main_sc_cth_cathay"] = true, ["wh3_main_sc_ksl_kislev"] = true,
}
-- Deeds that spill blood. A confederation is same-culture by nature and a seizure takes goods.
local KIN_DEEDS = {sack = true, raze = true, conquest = true}
-- A guess, like every threshold here. The Guilds' ranks sit at 0/100/300/700/1500.
local KIN_TEMPLE_LOSS = 25
-- Iron Court loyalty runs 0-100 a party, and the court's own one-off moves for a war it was not
-- asked about are -10 and +3. Guesses too. A pact or grudge against the realm: the war party gains
-- and the merchants lose. Kin-slaying: the temple party, in a court whose faith condemns it, which
-- of the two courts is the Dwarfs' alone.
local COURT_THREAT_GAIN = 3
local COURT_THREAT_LOSS = 3
local COURT_KIN_LOSS = 5

-- Rebellions only; OUTRAGE_FLOOR also gates grudges. Outrage is constant per culture pairing, so
-- the old 0.50 floor raised rebels on every capture. 1.0 admits kin-slaying and unprovoked only.
local UNREST_FLOOR = 1.0

-- The is_rebel faction for each subculture that has one (24 of 45, read from db.pack), keyed on
-- the dispossessed owner so the locals rise. Where there are several, the territorial one wins.
local REBEL_FACTIONS = {
	["wh2_dlc09_sc_tmb_tomb_kings"]      = "wh2_dlc09_tmb_tomb_kings_rebels",
	["wh2_dlc11_sc_cst_vampire_coast"]   = "wh2_dlc11_cst_vampire_coast_rebellion_rebels",
	["wh2_main_sc_def_dark_elves"]       = "wh2_main_def_dark_elves_rebels",
	["wh2_main_sc_hef_high_elves"]       = "wh2_main_hef_high_elves_rebels",
	["wh2_main_sc_lzd_lizardmen"]        = "wh2_main_lzd_lizardmen_rebels",
	["wh2_main_sc_skv_skaven"]           = "wh2_main_skv_skaven_rebels",
	["wh3_dlc23_sc_chd_chaos_dwarfs"]    = "wh3_dlc23_chd_chaos_dwarfs_rebels",
	["wh3_main_sc_cth_cathay"]           = "wh3_main_cth_cathay_rebels",
	["wh3_main_sc_kho_khorne"]           = "wh3_main_kho_khorne_rebels",
	["wh3_main_sc_ksl_kislev"]           = "wh3_main_ksl_kislev_rebels",
	["wh3_main_sc_nur_nurgle"]           = "wh3_main_nur_nurgle_rebels",
	["wh3_main_sc_ogr_ogre_kingdoms"]    = "wh3_main_ogr_ogre_rebels",
	["wh3_main_sc_sla_slaanesh"]         = "wh3_main_sla_slaanesh_rebels",
	["wh3_main_sc_tze_tzeentch"]         = "wh3_main_tze_tzeentch_rebels",
	["wh_dlc03_sc_bst_beastmen"]         = "wh_dlc03_bst_beastmen_rebels",
	["wh_dlc05_sc_wef_wood_elves"]       = "wh_dlc05_wef_wood_elves_rebels",
	["wh_dlc08_sc_nor_norsca"]           = "wh_main_nor_norsca_rebels",
	["wh_main_sc_brt_bretonnia"]         = "wh_main_brt_bretonnia_rebels",
	["wh_main_sc_chs_chaos"]             = "wh_main_chs_chaos_rebels",
	["wh_main_sc_dwf_dwarfs"]            = "wh_main_dwf_dwarf_rebels",
	["wh_main_sc_emp_empire"]            = "wh_main_emp_empire_rebels",
	["wh_main_sc_grn_greenskins"]        = "wh_main_grn_greenskins_rebels",
	["wh_main_sc_teb_teb"]               = "wh_main_teb_border_princes_rebels",
	["wh_main_sc_vmp_vampire_counts"]    = "wh_main_vmp_vampire_rebels",
}
-- Below this the deed is not worth a permanent grudge, however cheap the budget makes it.
local OUTRAGE_FLOOR = 0.5
-- Also the cap the per-turn refill tops up to. One live turn produced nine sacks, so a
-- per-campaign budget drained inside it.
local BUDGET_START = 180
-- Priced by how hard a beat is to undo: reversible effects are released, irreversible ones stay.
local PRICE = {ask = 0, mood = 5, force = 15, past_event = 40, tell = 0,
               shield = 10, warchest = 25, unrest = 30, plague = 35}

-- How long the AI is kept off a shielded settlement; released by the turn-start sweep.
local SHIELD_TURNS = 8
-- Gold for each member of a new coalition.
local WARCHEST = 2500
local REBEL_UNITS = 4
-- The answers' sizes follow the aggressor (2026-11-14): 4 rebels and 2,500 gold mean something
-- against a 10-region faction and nothing against a 60-region empire. Above SIZE_FROM regions both
-- grow by one time for every SIZE_STEP more, to SIZE_MAX times.
local SIZE_FROM = 20
local SIZE_STEP = 20
local SIZE_MAX = 3
-- A grudge is CA's PAST_EVENT_NEGATIVE_MINOR, whose falloff is 50 for most personalities. After
-- that long the same feud can be remembered again.
local GRUDGE_MEMORY = 50
-- The ordinary base diseases, not tied to any faction's storyline the way the crimson plague is.
local PLAGUES = {
	"wh3_main_nur_base_Ague",
	"wh3_main_nur_base_Buboes",
	"wh3_main_nur_base_Pox",
	"wh3_main_nur_base_Rot",
	"wh3_main_nur_base_Shakes",
}

-- `index` resolves through campaign_groups -> _members -> _member_criteria_values, and one with
-- no record behind it draws nothing. FEED_ROWS in tools/build_director.py is the source.
-- Generic rows sit on each range's base, culture rows from base + 1. Two records on one index
-- draw one card for both, silently; check_feed() refuses it.
local FEED = {
	grudge = {index = 7300, key = "grudge"},
	pact = {index = 7400, key = "pact"},
	raid = {index = 7500, key = "raid"},
	guild = {index = 7600, key = "guild"},
	rising = {index = 7700, key = "rising"},
	temper_rising = {index = 7800, key = "temper_rising"},
	temper_patient = {index = 7801, key = "temper_patient"},
	temper_wild = {index = 7802, key = "temper_wild"},
	blood = {index = 7900, key = "blood"},
	betrayal = {index = 8000, key = "betrayal"},
	empire_rise = {index = 8100, key = "empire_rise"},
}

-- Situations told ONCE, with their own record, after the beats: the pact and grudge records say
-- the instigator attacked someone, and a realm that split, a faction that lost ground and an
-- oath-breaker did not.
local ONE_TELL = {secession = "rising", opportunism = "blood", treachery = "betrayal"}
local LOC_STEM = "event_feed_strings_text_derpy_director_feed_"

-- The lead responder's culture record, else the generic pair. Feed text has no runtime tokens, so
-- a faction name can never appear; a culture name can, one record per culture.
-- derpy_director_feed_index is generated into the lore file, so it is read lazily too.
function derpy_director:feed_record(kind, subculture)
	local rec = FEED[kind]
	if not rec then return nil end
	local map = derpy_director_feed_index
	local index = map and map[kind] and subculture and map[kind][subculture]
	if not index then
		return {index = rec.index,
		        title = LOC_STEM .. rec.key .. "_title",
		        body = LOC_STEM .. rec.key .. "_primary",
		        tail = LOC_STEM .. rec.key .. "_secondary"}
	end
	local stem = LOC_STEM .. rec.key .. "_" .. subculture .. "_"
	return {index = index, title = stem .. "title", body = stem .. "primary",
	        tail = stem .. "secondary"}
end

-- The message speaks for cast[1], the responder who hates the aggressor most.
function derpy_director:voice_of(cast)
	if not cast or #cast == 0 then return nil end
	local f = cm:get_faction(cast[1])
	if not f or f:is_null_interface() then return nil end
	return f:subculture()
end


-- Permanent grudges the whole world may get per turn. One per responder spent 120 of 180 on
-- the one beat with no inverse and starved the cheap beats.
local GRUDGES_PER_TURN = 1

-- THE STORYTELLER (2026-11-14), after RimWorld's. Three temperaments, one rolled per campaign:
-- `rising` is Cassandra (waves of anger, then calm), `patient` Phoebe (long quiet spells),
-- `wild` Randy (no rhythm, sizes that swing). A cycled temperament is ON for `on` turns of every
-- `cycle`: on turns it refills more and answers at full chance, off turns refill less and answer
-- at `tension_off` of it. `opportunity` is the percent chance a turn starts an opportunism
-- situation (on turns; off turns scale it the same way). rising's ON turns are the pre-storyteller
-- numbers plus 10 refill, so its waves sit around the old average of 60.
-- `ramp` makes a temperament live up to its name: its refill and the budget's ceiling grow by one
-- time every RAMP_TURNS turns, to RAMP_MAX, so a late campaign answers more often than an early one.
-- RimWorld's Cassandra escalates the same way; patient and wild do not.
local RAMP_TURNS = 100
local RAMP_MAX = 2.5
local TEMPERAMENTS = {
	rising = {cycle = 10, on = 6, refill_on = 70, refill_off = 30, tension_off = 0.4,
	          cooldown = 12, opportunity = 25, ramp = true},
	patient = {cycle = 12, on = 3, refill_on = 70, refill_off = 20, tension_off = 0.25,
	           cooldown = 18, opportunity = 10},
	wild = {refill_min = 20, refill_max = 100, cooldown = 8, opportunity = 30, swing = true},
}
local TEMPERAMENT_ORDER = {"rising", "patient", "wild"}
-- The seed's other two fields, both multipliers on the cast score that already exists: one pair
-- of cultures whose hatred burns hotter this campaign, and three factions quicker to take sides
-- (and back sooner, at half the cooldown).
local HOT_MULT = 2.0
local HOT_FLOOR = -25
local AMBITIOUS_MULT = 1.5
local AMBITIOUS_COUNT = 3
-- Since 2026-11-15 the ambitious factions are the campaign's empires (the EMPIRES section): no two
-- capitals within this many region hops, so they do not block each other and more of the map gets
-- a rival.
local EMPIRE_SPREAD_HOPS = 6
-- Choosing what to answer. Every situation is answered with a CHANCE, so the turn's money is not
-- spent on whoever moved first: outrage against the kin-slaying maximum, times PARTY_WEIGHT when the
-- player is one of the two parties, times how full the budget is (never below BUDGET_FLOOR, so a
-- thin budget still lets the beats price themselves), times the temperament's tension.
local PARTY_WEIGHT = 3
local BUDGET_FLOOR = 0.25
-- The start position's wars all report on turn 1: 96 situations in the 2026-11-14 soak against
-- 22 to 44 later, and 15 answers against 1 to 10. The world's own quarrels are answered at a third
-- of the chance then. A player's are not, so the first turn still answers what the player does.
local FIRST_TURN_DAMP = 0.33
-- Adaptation, per player, -60 to 60: each region lost last round takes ADAPT_LOSS, each gained adds
-- ADAPT_GAIN, and it drifts ADAPT_FORGET back toward 0 a turn. The chance that the world turns on
-- the player is multiplied by 1 + adapt / 100, and the chance it helps them by 1 - adapt / 100.
local ADAPT_LOSS = 15
local ADAPT_GAIN = 3
local ADAPT_FORGET = 5
local ADAPT_MIN, ADAPT_MAX = -60, 60
-- Opportunism: a faction that lost at least this many settlements by force last round can be the
-- target. Its outrage is fixed at an unprovoked deed's, since the "deed" is only weakness.
local OPPORTUNITY_LOSSES = 1
local OPPORTUNITY_OUTRAGE = 1.0

local function is_human_key(key)
	local f = key and cm:get_faction(key)
	return f and not f:is_null_interface() and f:is_human() or false
end

-- MCT (2026-11-14). The options and their defaults are generated into the lore file from the one
-- list in tools/build_director.py that also writes the page, so the two cannot disagree. Read at
-- each use, never at file load (MCT has not read the player's settings then), so a change takes
-- effect the next time it is needed. TYPE-CHECKED, not nil-checked: a mis-registered option can
-- hand back a string for a slider. MULTIPLAYER IGNORES MCT: every value steers a cm: write or a
-- cm:random_number that must match on every machine.
local MCT_KEY = "derpy_director"

function derpy_director:setting(key)
	local default
	local defaults = derpy_director_mct_defaults
	if defaults then default = defaults[key] end
	-- One switch per race the game lets confederate at all; a race CA forbids has none.
	if default == nil and type(key) == "string" and key:sub(1, 5) == "race_" then
		local races = derpy_director_merge_races
		if races and races[key:sub(6)] then default = true end
	end
	if default == nil then
		log("unknown setting " .. tostring(key))
		return nil
	end
	local ok_mp, mp = pcall(function() return cm:is_multiplayer() end)
	if ok_mp and mp == true then return default end
	local v = default
	pcall(function()
		local mct = get_mct and get_mct()
		local mod = mct and mct:get_mod_by_key(MCT_KEY)
		local opt = mod and mod:get_option_by_key(key)
		local got = opt and opt:get_finalized_setting()
		if type(got) == type(default) then v = got end
	end)
	return v
end

-- The seed is rolled once, at the first tick that finds none, and frozen into the save: a reload
-- must never re-roll the world. Nil until then.
function derpy_director:seed()
	local s = cm:get_saved_value("derpy_director_seed")
	if type(s) == "table" then return s end
	return nil
end

function derpy_director:temperament()
	local s = self:seed()
	local name = s and TEMPERAMENTS[s.temperament] and s.temperament or "rising"
	return TEMPERAMENTS[name], name
end

-- Wild has no cycle and is always on. The phase is rolled with the seed, so two campaigns with the
-- same temperament still wave on different turns.
function derpy_director:is_on(turn)
	local t = self:temperament()
	if not t.cycle then return true end
	local s = self:seed()
	return ((turn - 1 + (s and s.phase or 0)) % t.cycle) < t.on
end

function derpy_director:tension(turn)
	if self:is_on(turn) then return 1.0 end
	return self:temperament().tension_off
end

function derpy_director:ramp(turn)
	if not self:temperament().ramp then return 1 end
	local r = 1 + (turn - 1) / RAMP_TURNS
	if r > RAMP_MAX then r = RAMP_MAX end
	return r
end

function derpy_director:budget_cap(turn)
	return math.floor(BUDGET_START * self:ramp(turn))
end

function derpy_director:refill_amount(turn)
	local t = self:temperament()
	if t.refill_min then return cm:random_number(t.refill_max, t.refill_min) end
	return math.floor((self:is_on(turn) and t.refill_on or t.refill_off) * self:ramp(turn))
end

-- 1 up to SIZE_FROM regions, then one more for every SIZE_STEP, to SIZE_MAX. A horde holds none.
function derpy_director:size_scale(key)
	local f = cm:get_faction(key)
	if not f or f:is_null_interface() then return 1 end
	local s = 1 + math.max(0, f:region_list():num_items() - SIZE_FROM) / SIZE_STEP
	if s > SIZE_MAX then s = SIZE_MAX end
	return s
end

-- One pair of present cultures that already hate each other both ways, read off CA's matrix.
-- Sorted before the roll, so every machine in a multiplayer game draws the same pair.
function derpy_director:roll_hot_grudge()
	local present, seen = {}, {}
	for _, f in model_pairs(cm:model():world():faction_list()) do
		if not f:is_null_interface() and not f:is_dead() and not f:is_rebel() then
			local sc = f:subculture()
			if sc and sc ~= "" and not seen[sc] then
				seen[sc] = true
				present[#present + 1] = sc
			end
		end
	end
	table.sort(present)
	local pairs_list = {}
	for i = 1, #present do
		for j = i + 1, #present do
			local a, b = present[i], present[j]
			if self:hatred(a, b) <= HOT_FLOOR and self:hatred(b, a) <= HOT_FLOOR then
				pairs_list[#pairs_list + 1] = {a, b}
			end
		end
	end
	if #pairs_list == 0 then return {} end
	return pairs_list[cm:random_number(#pairs_list, 1)]
end

-- The empires: drawn at random from the factions a player could have picked, then from the rest
-- only if too few are left, each capital clear of the others'. Most settlements first, so the
-- first is the great power.
function derpy_director:roll_ambitious()
	local strict, loose = {}, {}
	for _, f in model_pairs(cm:model():world():faction_list()) do
		if self:empire_candidate(f, true) then
			strict[#strict + 1] = f:name()
		elseif self:empire_candidate(f, false) then
			loose[#loose + 1] = f:name()
		end
	end
	table.sort(strict)
	table.sort(loose)
	local chosen = {}
	for _, pool in ipairs({strict, loose}) do
		while #chosen < AMBITIOUS_COUNT and #pool > 0 do
			local key = table.remove(pool, cm:random_number(#pool, 1))
			if self:spread_ok(key, chosen) then chosen[#chosen + 1] = key end
		end
	end
	return self:by_size(chosen)
end

-- The temperament, named to every player at the start: variety a player cannot see is no variety.
-- At the capital; a horde with no home is not told.
function derpy_director:announce(name)
	local rec = self:feed_record("temper_" .. name)
	for _, key in ipairs(cm:get_human_factions()) do
		local f = cm:get_faction(key)
		local home = f and not f:is_null_interface() and f:home_region()
		local x, y = self:map_point(home)
		if rec and x and y then
			cm:show_message_event_located(key, rec.title, rec.body, rec.tail, x, y, false, rec.index)
			log(string.format("feed temper_%s index=%d to=%s", name, rec.index, key))
		end
	end
end

function derpy_director:roll_seed()
	local s = self:seed()
	if s then return s end
	local name = TEMPERAMENT_ORDER[cm:random_number(#TEMPERAMENT_ORDER, 1)]
	local t = TEMPERAMENTS[name]
	s = {temperament = name, phase = t.cycle and (cm:random_number(t.cycle, 1) - 1) or 0,
	     hot = self:roll_hot_grudge(), ambitious = self:roll_ambitious()}
	cm:set_saved_value("derpy_director_seed", s)
	log(string.format("seed rolled: temperament=%s phase=%d hot=%s ambitious=%s", name, s.phase,
		table.concat(s.hot, "/"), table.concat(s.ambitious, ",")))
	-- The empires set out: the first is the great power, saved now so the first turn start does not
	-- re-rank them (a neighbour's town taken on turn 1 tied two of them on 2026-11-15, and the title
	-- moved while the Chronicle still named the first).
	if self:setting("empires") then
		local st = self:empires()
		st.great = s.ambitious[1]
		cm:set_saved_value("derpy_director_empires", st)
		for i, key in ipairs(s.ambitious) do
			self:chronicle({t = cm:model():turn_number(), k = "empire", i = key, n = i == 1 and 1 or 2})
		end
	end
	self:announce(name)
	return s
end

function derpy_director:is_hot(sc_a, sc_b)
	local s = self:seed()
	local h = s and s.hot
	if not h or #h ~= 2 then return false end
	return (h[1] == sc_a and h[2] == sc_b) or (h[1] == sc_b and h[2] == sc_a)
end

function derpy_director:is_ambitious(key)
	local s = self:seed()
	for _, k in ipairs(s and s.ambitious or {}) do
		if k == key then return true end
	end
	return false
end

-- 1 + adapt / 100 for a player, 1 for anyone else.
function derpy_director:adapt_factor(key)
	local all = cm:get_saved_value("derpy_director_adapt")
	local a = type(all) == "table" and all[key]
	return 1 + (type(a) == "table" and a.adapt or 0) / 100
end

-- At each turn start: each player's regions against last turn's.
function derpy_director:adapt_turn()
	local all = cm:get_saved_value("derpy_director_adapt")
	if type(all) ~= "table" then all = {} end
	for _, key in ipairs(cm:get_human_factions()) do
		local f = cm:get_faction(key)
		if f and not f:is_null_interface() and not f:is_dead() then
			local now = f:region_list():num_items()
			local a = all[key] or {adapt = 0, regions = now}
			local n = a.adapt
			if n > 0 then n = math.max(0, n - ADAPT_FORGET) else n = math.min(0, n + ADAPT_FORGET) end
			local d = now - a.regions
			n = n + (d < 0 and d * ADAPT_LOSS or d * ADAPT_GAIN)
			n = math.max(ADAPT_MIN, math.min(ADAPT_MAX, n))
			if d ~= 0 then
				log(string.format("adapt %s %+d regions, now %d", key, d, n))
			end
			all[key] = {adapt = n, regions = now}
		end
	end
	cm:set_saved_value("derpy_director_adapt", all)
end

-- The chance this situation is answered, 0 to 1.
function derpy_director:chance(sit)
	local inst, vic = is_human_key(sit.instigator), is_human_key(sit.victim)
	local p = sit.outrage / OUTRAGE_KIN
	if inst or vic then p = p * PARTY_WEIGHT end
	local fill = self:budget() / self:budget_cap(sit.turn)
	if fill > 1 then fill = 1 end
	p = p * (BUDGET_FLOOR + (1 - BUDGET_FLOOR) * fill) * self:tension(sit.turn)
	if sit.turn == 1 and not (inst or vic) then p = p * FIRST_TURN_DAMP end
	if inst then p = p * self:adapt_factor(sit.instigator) end
	if vic then p = p * (2 - self:adapt_factor(sit.victim)) end
	if p > 1 then p = 1 end
	return p
end

function derpy_director:chosen(sit)
	-- Every priced beat costs at least a stance push, so a budget below it could answer and then
	-- do nothing: 10 of the soak's 52 answers did. Pass it without a roll.
	local b = self:budget()
	if b < PRICE.mood then
		log(string.format("passed over: budget %d cannot pay for anything", b))
		return false
	end
	local pct = math.floor(self:chance(sit) * 100 + 0.5)
	local roll = cm:random_number(100, 1)
	if roll > pct then
		log(string.format("passed over: rolled %d against %d%%", roll, pct))
		return false
	end
	log(string.format("answered: rolled %d against %d%%", roll, pct))
	return true
end

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

-- A province falls as one event per region. Answer each pair once a turn, not once per town;
-- keyed on the pair and not the kind, so a sack then a capture is one deed.
function derpy_director:first_of_feud_this_turn(sit)
	local feud = sit.instigator .. "_" .. sit.victim
	local when = cm:get_saved_value("derpy_director_feud_turn")
	local set = cm:get_saved_value("derpy_director_feud_set")
	if when ~= sit.turn or type(set) ~= "table" then set = {} end
	if set[feud] then return false end
	set[feud] = true
	cm:set_saved_value("derpy_director_feud_turn", sit.turn)
	cm:set_saved_value("derpy_director_feud_set", set)
	return true
end

-- Asking claims the slot. Burning it on a situation that then cannot afford 40 is harmless:
-- the budget only falls within a turn. Above one a turn, the feed would need its own quota.
function derpy_director:grudge_slot(turn)
	local spent = cm:get_saved_value("derpy_director_grudge_turn")
	local n = 0
	if spent == turn then n = cm:get_saved_value("derpy_director_grudge_count") or 0 end
	if n >= GRUDGES_PER_TURN then
		log("no grudge: the world's grudge for this turn is already spent")
		return false
	end
	cm:set_saved_value("derpy_director_grudge_turn", turn)
	cm:set_saved_value("derpy_director_grudge_count", n + 1)
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
	local turns = self:temperament().cooldown
	if self:is_ambitious(key) then turns = math.floor(turns / 2) end
	c[key] = cm:model():turn_number() + turns
	cm:set_saved_value("derpy_director_cooldowns", c)
end

-- Region keys within max_hops, breadth-first. Never asks who owns anything: `owning_faction` is
-- shared by several interfaces, and --explain returns the pooled resource manager's.
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

-- 1.0 at peace, falling per war, floored so a busy faction is outranked, not excluded. Wars
-- stand in for strength: no column holds it, and military_force_list counts garrisons.
function derpy_director:safety(f)
	local wars = f:factions_at_war_with():num_items()
	local s = 1.0 - (wars * WAR_PENALTY)
	if s < 0.1 then s = 0.1 end
	return s
end

-- Kin-slaying first, then the natural-enmity scale. Returns the multiplier and a word for the log.
function derpy_director:outrage(sit)
	if sit.kind == "opportunism" then return OPPORTUNITY_OUTRAGE, "weakness" end
	local a = cm:get_faction(sit.instigator)
	local b = cm:get_faction(sit.victim)
	if not a or a:is_null_interface() then return OUTRAGE_UNPROVOKED, "unknown" end
	if not b or b:is_null_interface() then return OUTRAGE_UNPROVOKED, "unknown" end
	local a_sc, b_sc = a:subculture(), b:subculture()
	if a_sc == b_sc then return OUTRAGE_KIN, "kinslaying" end
	local base = self:hatred(a_sc, b_sc)
	for i = 1, #OUTRAGE_STEPS do
		if base <= OUTRAGE_STEPS[i][1] then
			return OUTRAGE_STEPS[i][2], (i == 1 and "sworn_enemies" or "old_enmity")
		end
	end
	return OUTRAGE_UNPROVOKED, "unprovoked"
end

-- `take` responders, scored by hatred of the instigator and drawn by weight. Not affinity with the
-- victim: CA rates Dwarfs to Dwarfs at 0, so there is no kin affinity to score on.
function derpy_director:cast(sit, take)
	local instigator = cm:get_faction(sit.instigator)
	if not instigator or instigator:is_null_interface() then return {} end
	local inst_sc = instigator:subculture()
	-- Once per situation; a BFS per candidate would walk the map up to 100 times.
	local reach = self:within_reach(sit.region, MAX_HOPS)
	local scored = {}
	for _, f in model_pairs(cm:model():world():faction_list()) do
		if not f:is_null_interface() and not f:is_dead() and not f:is_rebel()
				and not f:is_human()
				and f:name() ~= sit.instigator
				and f:name() ~= sit.victim
				and f:region_list():num_items() >= 2
				and not self:on_cooldown(f:name()) then
			local base, neg = self:hatred(f:subculture(), inst_sc)
			if base < 0 then
				local reachable = false
				for _, r in model_pairs(f:region_list()) do
					if reach[r:name()] then reachable = true break end
				end
				if reachable then
					-- Live attitude on top of the matrix: a faction that already loathes the
					-- aggressor beats one that merely ought to. A non-number changes nothing.
					-- The name is cached so the sort makes no engine calls.
					local live = 1.0
					local att = instigator and f:diplomatic_attitude_towards(sit.instigator)
					if type(att) == "number" and att < 0 then
						local bump = -att / 100.0
						if bump > 1.0 then bump = 1.0 end
						live = 1.0 + bump
					end
					local score = (-base) * neg * self:safety(f) * live
					if self:is_hot(f:subculture(), inst_sc) then score = score * HOT_MULT end
					if self:is_ambitious(f:name()) then score = score * AMBITIOUS_MULT end
					scored[#scored + 1] = {name = f:name(), score = score}
				end
			end
		end
	end
	-- Sorted, never raw pairs(): undefined order diverges across reloads and MP clients.
	-- Ties break on name so the order is total, not merely mostly-defined.
	table.sort(scored, function(x, y)
		if x.score ~= y.score then return x.score > y.score end
		return x.name < y.name
	end)
	-- Drawn by weight, not taken from the top, so the same deed brings different neighbours in
	-- different campaigns, and the strongest is still the likeliest. The draw walks the sorted
	-- order, so a roll of 1 takes the top and every machine draws the same names. Tenths of a
	-- point, at least 1, keep the totals inside random_int.
	local out_list = {}
	for i = 1, math.min(take, #scored) do
		local total = 0
		for j = 1, #scored do
			scored[j].weight = math.max(1, math.floor(scored[j].score * 10))
			total = total + scored[j].weight
		end
		local roll, run, pick = cm:random_number(total, 1), 0, #scored
		for j = 1, #scored do
			run = run + scored[j].weight
			if roll <= run then pick = j break end
		end
		out_list[i] = table.remove(scored, pick).name
	end
	return out_list
end

local DEAL = "diplomatic_option_defensive_alliance"

-- Who may be asked to stand together: the responders, and the victim when it is a computer
-- faction still standing. The victim is already at war with the aggressor, the common cause CA's
-- deal scoring looks for. No pact formed in three soaks of responder pairs alone (2026-11-14).
-- A player is never forced into a treaty.
function derpy_director:partners(sit, cast)
	local out_list = {}
	for i = 1, #cast do out_list[#out_list + 1] = cast[i] end
	local v = cm:get_faction(sit.victim)
	if v and not v:is_null_interface() and not v:is_dead() and not v:is_rebel()
			and not v:is_human() then
		out_list[#out_list + 1] = sit.victim
	end
	return out_list
end

-- A pair that hates each other, either way, as hard as a hot grudge, or that is at war, is not
-- asked: the soaks' casts mixed Wood Elves with Nurgle and Vampires, and every such ask scored
-- below zero.
function derpy_director:at_odds(a_key, b_key)
	local a, b = cm:get_faction(a_key), cm:get_faction(b_key)
	if not a or not b or a:is_null_interface() or b:is_null_interface() then return true end
	local sa, sb = a:subculture(), b:subculture()
	if self:hatred(sa, sb) <= HOT_FLOOR or self:hatred(sb, sa) <= HOT_FLOOR then return true end
	return a:at_war_with(b)
end

-- Takes a settlement key (settlement:key()), not a region key. Global, so no AI targets it at
-- all; released on a timer through the documented inverse. Only while the victim still holds it.
function derpy_director:beat_shield(sit)
	local rm = cm:model():world():region_manager()
	local region = rm:region_by_key(sit.region)
	if not region or region:is_null_interface() then return false end
	local owner = region:owning_faction()
	if not owner or owner:is_null_interface() then return false end
	if owner:name() ~= sit.victim then
		log("no shield: " .. sit.region .. " is not the victim's any more")
		return false
	end
	local settlement = region:settlement()
	if not settlement or settlement:is_null_interface() then return false end
	local key = settlement:key()
	if not key or key == "" then return false end
	cm:cai_disable_targeting_against_settlement(key)
	local held = cm:get_saved_value("derpy_director_shields")
	if type(held) ~= "table" then held = {} end
	held[key] = cm:model():turn_number() + SHIELD_TURNS
	cm:set_saved_value("derpy_director_shields", held)
	log(string.format("shield %s for %d turns", key, SHIELD_TURNS))
	return true
end

-- Swept at turn start. A shield never released is a permanent hole in the AI's target list.
function derpy_director:release_shields()
	local held = cm:get_saved_value("derpy_director_shields")
	if type(held) ~= "table" then return 0 end
	local now = cm:model():turn_number()
	local keys, freed = {}, 0
	for k in pairs(held) do keys[#keys + 1] = k end
	table.sort(keys)
	for i = 1, #keys do
		local k = keys[i]
		if now >= held[k] then
			cm:cai_enable_targeting_against_settlement(k)
			held[k] = nil
			freed = freed + 1
			log("shield lifted on " .. k)
		end
	end
	if freed > 0 then cm:set_saved_value("derpy_director_shields", held) end
	return freed
end

-- THE RUNAWAY STEP (2026-11-14): the Coalition Supervisor, merged in. Once a turn, the faction
-- holding the most regions is measured against the runner-up. Far enough ahead, it is a runaway:
-- its strategic threat score rises with the tier, which CA turns into -5 to -30 attitude with
-- everyone, and the factions polled against it take one grudge the turn the tier rises. Region
-- count, not strength: no column holds strength, and military_force_list counts garrisons, so a
-- horde never leads. This step is the threat score's ONLY writer. The global AI context slot the
-- Supervisor also claimed is gone: it carries over between campaigns in one session, and CA's "AI
-- extra aggro" option shares it.
-- The one grudge: CA's PAST_EVENT_NEGATIVE_MINOR, -10 with falloff 50. Declared here, above both
-- the runaway step and beat_past_event, because a local is only visible below its line.
local PAST_EVENT = "PAST_EVENT_NEGATIVE_MINOR"
local TIER_RATIOS = {1.75, 2.5, 4.0}
local TIER_EXIT = 1.35
local TIER_SCORES = {200, 350, 500}
assert(#TIER_RATIOS == #TIER_SCORES,
	"TIER_RATIOS and TIER_SCORES are index-coupled: a tier with no score passes nil to " ..
	"set_base_strategic_threat_score and fails quietly under pcall, every turn")

-- Saved as one table. scored_key is the only record of which faction carries a scripted score,
-- so a release targets that faction even after it stops leading.
function derpy_director:runaway()
	local st = cm:get_saved_value("derpy_director_runaway")
	if type(st) ~= "table" then st = {} end
	st.tier = st.tier or 0
	st.cursor = st.cursor or 0
	st.alliances = type(st.alliances) == "table" and st.alliances or {}
	st.last_event_tier = st.last_event_tier or 0
	st.formed_turn = st.formed_turn or 0
	st.formed_count = st.formed_count or 0
	return st
end

-- Pure: no game calls but the setting. Holds at the MINIMUM active tier inside the exit band, not
-- at whatever tier was active, or a less dominant leader (fresh tier 1) would score worse than a
-- more dominant one that merely fell into the band from tier 3.
function derpy_director:tier_for(ratio, leader_regions, current)
	if leader_regions < (self:setting("runaway_min_regions") or 10) then return 0 end
	if current > 0 and ratio < TIER_EXIT then return 0 end
	local tier = 0
	for i = 1, #TIER_RATIOS do
		if ratio >= TIER_RATIOS[i] then tier = i end
	end
	if current > 0 and tier == 0 then return math.min(current, 1) end
	return tier
end

-- The leader is the largest faction the empires' shelter does not cover; the runner-up is the
-- largest of all the rest, sheltered or not, so the ratio stays honest for everyone else.
function derpy_director:measure()
	local all = {}
	for _, f in model_pairs(cm:model():world():faction_list()) do
		if not f:is_null_interface() and not f:is_dead() and not f:is_rebel() then
			all[#all + 1] = {f = f, n = f:region_list():num_items()}
		end
	end
	local leader, best, second = nil, 0, 0
	for _, e in ipairs(all) do
		if e.n > best and not self:shelters(e.f:name()) then leader, best = e.f, e.n end
	end
	if not leader then return nil end
	for _, e in ipairs(all) do
		if e.n > second and e.f:name() ~= leader:name() then second = e.n end
	end
	if second == 0 then return nil end
	return leader, best, second, best / second
end

function derpy_director:release_threat(st)
	if not st.scored_key then return end
	-- cm:get_faction returns false, not nil, for a key it does not know.
	local previous = cm:get_faction(st.scored_key)
	if previous and not previous:is_null_interface() then
		cm:set_base_strategic_threat_score(previous, 0)
		log("threat score released on " .. st.scored_key)
	end
	st.scored_key = nil
end

-- Reversible by writing 0, and visible on the diplomacy screen.
function derpy_director:apply_threat(leader, tier, st)
	if tier > 0 and leader and self:setting("runaway_threat") then
		if st.scored_key and st.scored_key ~= leader:name() then self:release_threat(st) end
		cm:set_base_strategic_threat_score(leader, TIER_SCORES[tier])
		st.scored_key = leader:name()
		log(string.format("threat score %d on %s", TIER_SCORES[tier], leader:name()))
		return
	end
	self:release_threat(st)
end

-- The alliance poll: POLL_PAIRS pairs a turn from a rotating cursor, a faction in at most
-- MAX_FORCED_ALLIANCES of them, and at most FORMS_PER_TURN formed in one turn.
local POLL_PAIRS = 8
local MAX_FORCED_ALLIANCES = 2
local FORMS_PER_TURN = 2

-- This turn's batch: pairs of computer factions with two regions or more that have met the leader
-- AND each other, under the alliance limit, sorted by name. Returns the batch's factions (sorted,
-- once each) and the pairs. The met-each-other test belongs here, not in the ask: the Supervisor
-- spent its whole budget on strangers it then dropped, and its cursor never left the factions whose
-- keys sort first. Never raw pairs(): undefined order diverges across reloads and MP clients.
function derpy_director:poll_batch(leader, st)
	local leader_key = leader:name()
	local cands = {}
	for _, f in model_pairs(cm:model():world():faction_list()) do
		if not f:is_null_interface() and not f:is_dead() and not f:is_rebel() and not f:is_human()
				and f:name() ~= leader_key and f:region_list():num_items() >= 2
				and (st.alliances[f:name()] or 0) < MAX_FORCED_ALLIANCES then
			local met = {}
			for _, m in model_pairs(f:factions_met()) do
				if not m:is_null_interface() then met[m:name()] = true end
			end
			if met[leader_key] then cands[#cands + 1] = {name = f:name(), met = met} end
		end
	end
	table.sort(cands, function(x, y) return x.name < y.name end)
	local list_of_pairs = {}
	for i = 1, #cands do
		for j = i + 1, #cands do
			if cands[i].met[cands[j].name] then
				list_of_pairs[#list_of_pairs + 1] = {cands[i].name, cands[j].name}
			end
		end
	end
	if #list_of_pairs == 0 then return {}, {} end
	-- ponytail: the cursor indexes a list that changes as factions die and meet, so the rotation is
	-- approximate. Good enough to spread the asks; revisit if the log shows pairs re-asked forever.
	local idx, batch = st.cursor, {}
	for _ = 1, math.min(POLL_PAIRS, #list_of_pairs) do
		idx = (idx % #list_of_pairs) + 1
		batch[#batch + 1] = list_of_pairs[idx]
	end
	st.cursor = idx
	local seen, names = {}, {}
	for _, pair in ipairs(batch) do
		for k = 1, 2 do
			if not seen[pair[k]] then
				seen[pair[k]] = true
				names[#names + 1] = pair[k]
			end
		end
	end
	table.sort(names)
	return names, batch
end

-- Through the pact machinery: at_odds first, both directions asked, the SUM rule (both-positive
-- never opened in about 50 live Supervisor asks), and PRICE.force out of the budget.
function derpy_director:poll_alliances(batch, st, leader_key)
	local turn = cm:model():turn_number()
	if st.formed_turn ~= turn then st.formed_turn, st.formed_count = turn, 0 end
	for _, pair in ipairs(batch) do
		if st.formed_count >= FORMS_PER_TURN then
			log(string.format("no more alliances this turn: %d formed", st.formed_count))
			return
		end
		local a_key, b_key = pair[1], pair[2]
		if (st.alliances[a_key] or 0) < MAX_FORCED_ALLIANCES
				and (st.alliances[b_key] or 0) < MAX_FORCED_ALLIANCES then
			local a, b = cm:get_faction(a_key), cm:get_faction(b_key)
			if a:defensive_allies_with(b) or a:military_allies_with(b) then
				-- Already allies: the engine keeps them so, and a second force does nothing.
			elseif self:at_odds(a_key, b_key) then
				log(string.format("no ask %s<->%s: they hate each other or are at war", a_key, b_key))
			else
				local sa, sb, oa, ob = self:beat_ask(a_key, b_key, DEAL)
				if oa and ob and sa and sb and sa + sb > 0 and self:afford(PRICE.force) then
					self:beat_force(a_key, b_key)
					self:chronicle({t = turn, k = "runaway_pact", i = leader_key, p = {{a_key, b_key}}})
					st.alliances[a_key] = (st.alliances[a_key] or 0) + 1
					st.alliances[b_key] = (st.alliances[b_key] or 0) + 1
					st.formed_count = st.formed_count + 1
				end
			end
		end
	end
end

-- The Chronicle hears of a runaway when the world's fear of it rises (or a new faction takes the
-- lead) and when it ends; a tier merely holding, or easing a step, is not news. Under the threat
-- score's switch, because the threat is what the fear is: with it off, nothing fears anyone.
-- Called before st.tier is overwritten.
function derpy_director:chronicle_runaway(turn, leader_key, tier, st)
	if not self:setting("runaway_threat") then return end
	if tier > 0 and (tier > st.tier or st.leader_key ~= leader_key) then
		self:chronicle({t = turn, k = "runaway_rise", i = leader_key, n = tier})
	elseif tier == 0 and st.tier > 0 and st.leader_key then
		self:chronicle({t = turn, k = "runaway_end", i = st.leader_key})
	end
end

function derpy_director:runaway_turn()
	local st = self:runaway()
	local turn = cm:model():turn_number()
	local leader, best, second, ratio = self:measure()
	if not leader then
		-- One faction owns everything: tier 0, and the held score released rather than leaked for
		-- the rest of the campaign.
		log(string.format("runaway turn=%d no runner-up, releasing", turn))
		self:apply_threat(nil, 0, st)
		self:chronicle_runaway(turn, nil, 0, st)
		if st.tier > 0 then st.last_event_tier = 0 end
		st.tier, st.leader_key = 0, nil
		cm:set_saved_value("derpy_director_runaway", st)
		return
	end
	local tier = self:tier_for(ratio, best, st.tier)
	log(string.format("runaway turn=%d leader=%s regions=%d runner_up=%d ratio=%.2f tier=%d",
		turn, leader:name(), best, second, ratio, tier))
	-- The last clause lets a player switch the threat off mid-campaign and see it lifted next turn.
	if self.runaway_reapply or tier ~= st.tier
			or (tier > 0 and st.scored_key ~= leader:name())
			or (st.scored_key and not self:setting("runaway_threat")) then
		self:apply_threat(leader, tier, st)
		self.runaway_reapply = false
	end
	-- A falling tier forgets how high the grudge fired, or a later rise to the same tier would
	-- never cross last_event_tier again.
	if tier < st.tier then st.last_event_tier = tier end
	if tier > 0 then
		local names, batch = self:poll_batch(leader, st)
		-- Only when the tier rises: the grudge has no inverse, so firing it every turn the tier
		-- holds would pile up attitude damage for as long as the runaway leads. It sits under the
		-- threat score's switch: both are the world turning against the runaway. With nobody to
		-- poll yet, the rise is kept for the first turn a pair has met, as the Supervisor did.
		if tier > st.last_event_tier and self:setting("runaway_threat") and #names > 0 then
			for _, n in ipairs(names) do
				log(string.format("past_event from=%s to=%s %s", leader:name(), n, PAST_EVENT))
				cm:cai_add_diplomatic_event(leader:name(), n, PAST_EVENT)
			end
			st.last_event_tier = tier
		end
		if self:setting("runaway_alliances") then self:poll_alliances(batch, st, leader:name()) end
	end
	self:chronicle_runaway(turn, leader:name(), tier, st)
	st.tier = tier
	st.leader_key = tier > 0 and leader:name() or nil
	cm:set_saved_value("derpy_director_runaway", st)
end

-- CONFEDERATIONS (2026-11-14). The brain merges kin: a faction at its last stand into stronger
-- kin, and the victim of a runaway with its kin (the runaway trigger is further down). Only what the
-- game itself allows: CA's deal probe must say ok in BOTH directions, which carries the DB table,
-- every per-race script lock and CA's 10-turn lock after a confederation (measured live 2026-11-14:
-- Vampire Counts ok=false/false, Greenskins ok=true/true, an absorber one turn after a merge
-- ok=false/true). The AI's scores are not asked for by default: every live score was far below zero.
local CONFED_DEAL = "diplomatic_option_confederation"
local CHD_SC = "wh3_dlc23_sc_chd_chaos_dwarfs"
-- Kin probed per attempt, after the exclusions: one probe is two engine calls.
local MERGE_PROBES = 3

-- CA's endgame invaders (9.0): the End Times episodes' owner factions, Nagash while his endgame
-- episode runs (his faction is otherwise an ordinary one), and any faction carrying an Ultimate
-- Crisis bundle. Read off episodes/episode_chaos_invasion.lua:11, episode_vermintide.lua:10,
-- episode_nagash_endgame.lua:6,28 and crisis/*.lua. They never merge and count as runaways from
-- the moment they exist; CA locks all their diplomacy, so they get no threat score.
local INVADERS = {"wh3_dlc29_chaos_invasion_confederation_owner",
                  "wh3_dlc29_vermintide_confederation_owner"}
local NAGASH, NAGASH_STATE = "wh3_dlc29_nag_host_of_nagash", "episode_nagash_endgame"
local CRISIS_BUNDLES = {"wh3_main_ie_scripted_endgame_grudge_too_far",
                        "wh3_main_ie_scripted_endgame_vampires_rise",
                        "wh3_main_ie_scripted_endgame_waaagh",
                        "wh3_main_ie_scripted_endgame_wild_hunt",
                        "wh3_dlc23_ie_scripted_endgame_faction_chaos_dwarfs_hashut"}

function derpy_director:is_invader(f)
	if not f or f:is_null_interface() then return false end
	local key = f:name()
	for _, k in ipairs(INVADERS) do
		if key == k then return true end
	end
	if key == NAGASH then
		local ok, on = pcall(function()
			return cm:model():shared_states_manager():get_state_as_bool_value(NAGASH_STATE)
		end)
		if ok and on == true then return true end
	end
	for _, b in ipairs(CRISIS_BUNDLES) do
		if f:has_effect_bundle(b) then return true end
	end
	return false
end

-- The confederations made this turn, by any route; merge_first reads and writes it.
local function merge_count(turn)
	if cm:get_saved_value("derpy_director_merge_turn") ~= turn then return 0 end
	return cm:get_saved_value("derpy_director_merge_count") or 0
end

-- EMPIRES (2026-11-15). Phase 4 of the design: each campaign the Director grows three computer
-- empires, a great power and two lesser ones, on a schedule. Design:
-- docs/superpowers/specs/2026-11-15-director-empires-design.md.

-- A faction that could be an empire: alive, a computer faction's, not a rebel, an endgame invader
-- or a vassal, holding land of a race that can hold land. strict also asks can_be_human(), CA's own
-- "is this a major faction" test (campaign/mod/battle_logging.lua:75).
function derpy_director:empire_candidate(f, strict)
	if not f or f:is_null_interface() or f:is_dead() or f:is_human() or f:is_rebel() then
		return false
	end
	if f:is_vassal() or self:is_invader(f) then return false end
	if f:region_list():num_items() < 1 or not f:is_allowed_to_capture_territory() then return false end
	if strict and not f:can_be_human() then return false end
	return true
end

-- Whether key's capital is clear of every chosen empire's by EMPIRE_SPREAD_HOPS. Hops run both
-- ways, so one reach from the candidate answers for every pair. No capital, no empire.
function derpy_director:spread_ok(key, chosen)
	local f = cm:get_faction(key)
	local home = f and not f:is_null_interface() and f:home_region()
	if not home or home:is_null_interface() then return false end
	local reach = self:within_reach(home:name(), EMPIRE_SPREAD_HOPS)
	for _, k in ipairs(chosen) do
		local o = cm:get_faction(k)
		local oh = o and not o:is_null_interface() and o:home_region()
		if oh and not oh:is_null_interface() and reach[oh:name()] then return false end
	end
	return true
end

-- Keys sorted most settlements first, ties by key, in place.
function derpy_director:by_size(keys)
	local n = {}
	for _, k in ipairs(keys) do
		local f = cm:get_faction(k)
		n[k] = (f and not f:is_null_interface()) and f:region_list():num_items() or 0
	end
	table.sort(keys, function(a, b)
		if n[a] ~= n[b] then return n[a] > n[b] end
		return a < b
	end)
	return keys
end

-- The goals are set for vanilla Immortal Empires, whose region list counts this many regions in
-- game (measured 2026-11-15; campaign_map_regions holds 644 rows for the map, so the DB count is
-- not the one to use). A smaller map scales every goal down.
local IE_REGIONS = 572
-- The schedule: nothing is expected before EMPIRE_ZERO_TURN, the goal by the goal-turn setting.
-- Far behind is under EMPIRE_FAR of it, from EMPIRE_FAR_FROM on. A check, on EMPIRE_CHECK_FIRST
-- and every EMPIRE_CHECK_EVERY after, replaces an empire under EMPIRE_STALLED of it.
local EMPIRE_ZERO_TURN = 10
local EMPIRE_FAR, EMPIRE_FAR_FROM = 0.6, 25
local EMPIRE_STALLED = 0.5
local EMPIRE_CHECK_FIRST, EMPIRE_CHECK_EVERY = 20, 10
-- Settlement counts kept, one per check: the oldest is the baseline a replacement's growth is
-- measured from, so two make it the last 20 turns.
local EMPIRE_SNAPS = 2

local function alive(key)
	local f = key and cm:get_faction(key)
	if not f or f:is_null_interface() or f:is_dead() then return nil end
	return f
end

-- Every strict candidate's settlement count, now.
function derpy_director:empire_snapshot()
	local n = {}
	for _, f in model_pairs(cm:model():world():faction_list()) do
		if self:empire_candidate(f, true) then n[f:name()] = f:region_list():num_items() end
	end
	return {t = cm:model():turn_number(), n = n}
end

-- Saved as one table. Missing, as in a save from before 2026-11-15, it is built from the seed's
-- ambitious factions; empire_turn saves it.
function derpy_director:empires()
	local st = cm:get_saved_value("derpy_director_empires")
	if type(st) ~= "table" then st = {} end
	for _, field in ipairs({"graduated", "chosen", "help", "merged", "cheat", "temper"}) do
		if type(st[field]) ~= "table" then st[field] = {} end
	end
	local s = self:seed()
	for _, k in ipairs(s and s.ambitious or {}) do
		if not st.chosen[k] then st.chosen[k] = cm:model():turn_number() end
	end
	if type(st.snaps) ~= "table" or #st.snaps == 0 then st.snaps = {self:empire_snapshot()} end
	return st
end

function derpy_director:map_scale()
	return cm:model():world():region_manager():region_list():num_items() / IE_REGIONS
end

function derpy_director:is_great(key, st)
	if st.great then return st.great == key end
	local s = self:seed()
	return s and s.ambitious and s.ambitious[1] == key or false
end

function derpy_director:empire_goal(key, st)
	st = st or self:empires()
	local setting = self:setting(self:is_great(key, st) and "empire_great_goal" or "empire_lesser_goal")
	return math.max(1, math.floor(setting * self:map_scale() + 0.5))
end

function derpy_director:expected(key, turn, st)
	local span = self:setting("empire_goal_turn") - EMPIRE_ZERO_TURN
	local share = (turn - EMPIRE_ZERO_TURN) / span
	if share < 0 then share = 0 elseif share > 1 then share = 1 end
	return self:empire_goal(key, st) * share
end

-- "graduated", "ahead", "behind" or "far"; nil for a faction that is not a living empire, or with
-- the Empires switch off.
function derpy_director:empire_band(key, turn)
	if not self:setting("empires") or not self:is_ambitious(key) then return nil end
	local f = alive(key)
	if not f then return nil end
	local st = self:empires()
	if st.graduated[key] then return "graduated" end
	local n, e = f:region_list():num_items(), self:expected(key, turn, st)
	if n > e then return "ahead" end
	if turn >= EMPIRE_FAR_FROM and n < EMPIRE_FAR * e then return "far" end
	return "behind"
end

-- Shelter: an empire at or behind its schedule is not named the runaway leader, and the Director
-- funds nothing against it. Ahead of schedule or graduated, the world answers it in full.
function derpy_director:shelters(key)
	local band = self:empire_band(key, cm:model():turn_number())
	return band == "behind" or band == "far"
end

-- A deed against a player is never sheltered.
function derpy_director:sheltered(sit)
	return self:shelters(sit.instigator) and not is_human_key(sit.victim)
end

-- The great power: a graduate keeps the title, else the living empire with most settlements
-- (ties by key). It goes first in the seed's list, which the Chronicle's header reads.
function derpy_director:assign_roles(st)
	local s = self:seed()
	if not s or not s.ambitious then return end
	if not (st.great and st.graduated[st.great] and self:is_ambitious(st.great)) then
		local best, best_n
		for _, k in ipairs(s.ambitious) do
			local f = alive(k)
			if f and not st.graduated[k] then
				local n = f:region_list():num_items()
				if not best or n > best_n or (n == best_n and k < best) then best, best_n = k, n end
			end
		end
		st.great = best
	end
	if not st.great then return end
	local order = {st.great}
	for _, k in ipairs(s.ambitious) do
		if k ~= st.great then order[#order + 1] = k end
	end
	s.ambitious = order
	cm:set_saved_value("derpy_director_seed", s)
end

-- Reaching the goal is for good. The great power's is told to every player, at its capital.
function derpy_director:graduate(key, st, turn, n)
	st.graduated[key] = turn
	local great = self:is_great(key, st)
	self:chronicle({t = turn, k = "empire_goal", i = key, n = n, g = great and 1 or 2})
	log(string.format("empire %s reached its goal with %d settlements", key, n))
	if not great then return end
	local rec = self:feed_record("empire_rise")
	local f = cm:get_faction(key)
	local x, y = self:map_point(f:home_region())
	if not (rec and x and y) then return end
	for _, h in ipairs(cm:get_human_factions()) do
		cm:show_message_event_located(h, rec.title, rec.body, rec.tail, x, y, false, rec.index)
		log(string.format("feed empire_rise index=%d to=%s", rec.index, h))
	end
end

-- The candidate that grew most since the oldest snapshot (ties: more settlements, then key), never
-- an empire before, its capital clear of others'. Players' choices first, then the rest.
function derpy_director:empire_grower(st, others)
	local base = st.snaps[1] and st.snaps[1].n or {}
	for _, strict in ipairs({true, false}) do
		local pool = {}
		for _, f in model_pairs(cm:model():world():faction_list()) do
			local k = f:name()
			if not st.chosen[k] and self:empire_candidate(f, true) == strict
				and self:empire_candidate(f, false) then
				local n = f:region_list():num_items()
				pool[#pool + 1] = {k = k, n = n, gain = n - (base[k] or 0)}
			end
		end
		table.sort(pool, function(a, b)
			if a.gain ~= b.gain then return a.gain > b.gain end
			if a.n ~= b.n then return a.n > b.n end
			return a.k < b.k
		end)
		for _, c in ipairs(pool) do
			if self:spread_ok(c.k, others) then return c.k end
		end
	end
	return nil
end

-- A dead empire fades; one under EMPIRE_STALLED of its schedule fades only if a grower takes its
-- place. A graduate is never replaced. Empty places are filled after.
function derpy_director:empire_check(st, turn)
	local s = self:seed()
	local keep, stalled, fades, picks = {}, {}, {}, {}
	for _, k in ipairs(s.ambitious) do
		local f = alive(k)
		if st.graduated[k] then
			keep[#keep + 1] = k
		elseif not f then
			fades[#fades + 1] = k
		else
			keep[#keep + 1] = k
			if f:region_list():num_items() < EMPIRE_STALLED * self:expected(k, turn, st) then
				stalled[#stalled + 1] = k
			end
		end
	end
	for _, k in ipairs(stalled) do
		local others = {}
		for _, o in ipairs(keep) do
			if o ~= k then others[#others + 1] = o end
		end
		local pick = self:empire_grower(st, others)
		if pick then
			for i, o in ipairs(keep) do
				if o == k then keep[i] = pick end
			end
			fades[#fades + 1] = k
			picks[#picks + 1] = pick
			st.chosen[pick] = turn
		end
	end
	while #keep < AMBITIOUS_COUNT do
		local pick = self:empire_grower(st, keep)
		if not pick then break end
		keep[#keep + 1] = pick
		picks[#picks + 1] = pick
		st.chosen[pick] = turn
	end
	s.ambitious = keep
	cm:set_saved_value("derpy_director_seed", s)
	self:assign_roles(st)
	for _, k in ipairs(fades) do
		self:chronicle({t = turn, k = "empire_fade", i = k})
		log("empire " .. k .. " faded")
	end
	for _, k in ipairs(picks) do
		self:chronicle({t = turn, k = "empire", i = k, n = self:is_great(k, st) and 1 or 2})
		log("empire " .. k .. " rises")
	end
	self:promote(st, turn)
	st.snaps[#st.snaps + 1] = self:empire_snapshot()
	while #st.snaps > EMPIRE_SNAPS do table.remove(st.snaps, 1) end
end

-- Spec 15.2: the title follows the winner. The largest faction that could be an empire takes it
-- from a great power short of its goal: an empire, a graduate among them, or a newcomer never
-- chosen before that is spread from the two empires that stay and takes the weakest lesser
-- empire's place. Never a measured runaway or an invader. Ties change nothing.
function derpy_director:promote(st, turn)
	local s = self:seed()
	local old = st.great
	local great = old and alive(old)
	if not great or st.graduated[old] then return nil end
	local blocked = {}
	for _, k in ipairs(self:runaway_keys(1)) do blocked[k] = true end
	local floor_n = great:region_list():num_items()
	local pool = {}
	for _, f in model_pairs(cm:model():world():faction_list()) do
		local k = f:name()
		local n = f:region_list():num_items()
		if n > floor_n and not blocked[k] and not f:is_dead() and (self:is_ambitious(k)
			or (not st.chosen[k] and self:empire_candidate(f, true))) then
			pool[#pool + 1] = {k = k, n = n}
		end
	end
	table.sort(pool, function(a, b)
		if a.n ~= b.n then return a.n > b.n end
		return a.k < b.k
	end)
	-- The weakest lesser empire: the place a newcomer takes.
	local lesser, drop, drop_n = {}, nil, nil
	for _, k in ipairs(s.ambitious) do
		if k ~= old then
			lesser[#lesser + 1] = k
			local f = alive(k)
			local n = f and f:region_list():num_items() or -1
			if not drop or n < drop_n or (n == drop_n and k > drop) then drop, drop_n = k, n end
		end
	end
	if #s.ambitious < AMBITIOUS_COUNT then drop = nil end
	for _, c in ipairs(pool) do
		local stays = {old}
		for _, k in ipairs(lesser) do
			if k ~= drop and k ~= c.k then stays[#stays + 1] = k end
		end
		if self:is_ambitious(c.k) or self:spread_ok(c.k, stays) then
			local newcomer = not self:is_ambitious(c.k)
			local order = {c.k}
			for _, k in ipairs(stays) do order[#order + 1] = k end
			if not newcomer and drop and drop ~= c.k then order[#order + 1] = drop end
			s.ambitious = order
			cm:set_saved_value("derpy_director_seed", s)
			st.great = c.k
			st.graduated[c.k] = nil
			if newcomer then
				st.chosen[c.k] = turn
				if drop then
					self:chronicle({t = turn, k = "empire_fade", i = drop})
					log("empire " .. drop .. " faded")
				end
			end
			self:chronicle({t = turn, k = "empire", i = c.k, n = 1})
			log(string.format("empire %s takes the title from %s (%d settlements)", c.k, old, c.n))
			return c.k
		end
	end
	return nil
end

-- Spec 15.3: a passive race's great power takes its race's endgame personality, the call CA's
-- endgame crises make (crisis_grudge_too_far.lua). Once per faction, and for good: no call reads a
-- personality back, so it could not be restored.
local TEMPER = {
	wh2_main_sc_skv_skaven = "wh3_combi_skaven_endgame",
	wh_main_sc_dwf_dwarfs = "wh3_combi_dwarf_endgame",
	wh_main_sc_emp_empire = "wh3_combi_empire_endgame",
	wh_main_sc_vmp_vampire_counts = "wh3_combi_vampire_endgame",
	wh_dlc05_sc_wef_wood_elves = "wh3_combi_woodelf_endgame",
	wh2_dlc09_sc_tmb_tomb_kings = "wh3_combi_tombking_endgame",
}

function derpy_director:temper(st, turn)
	local k = st.great
	if not k or st.temper[k] then return end
	local f = alive(k)
	local p = f and TEMPER[f:subculture()]
	if not p then return end
	st.temper[k] = turn
	cm:force_change_cai_faction_personality(k, p)
	log(string.format("temper %s -> %s turn %d", k, p, turn))
end

-- Spec 16.1: CA's own lever for a rival it builds up (wh3_campaign_ai.lua raises Bhashiva's
-- Western Provinces to 210). Measured live 2026-11-15: (f, true, X) sets the total potential to X
-- and (f, false, 0) restores the game's own value, which ran 350 to 555 for majors at turn 99.
-- Held while the faction holds the title, handed back when the title moves or the switch goes off.
local GREAT_POTENTIAL = 750

function derpy_director:release_potential(st)
	local old = st.potential and alive(st.potential)
	if old then
		cm:faction_set_total_potential_override_value(old, false, 0)
		log("potential released on " .. st.potential)
	end
	st.potential = nil
end

function derpy_director:pace(st)
	if st.potential == st.great then return end
	self:release_potential(st)
	local f = st.great and alive(st.great)
	if not f then return end
	cm:faction_set_total_potential_override_value(f, true, GREAT_POTENTIAL)
	st.potential = st.great
	log(string.format("potential %d on %s", GREAT_POTENTIAL, st.great))
end

-- Spec 16.2: an empire storms what it besieges once its army is SIEGE_ODDS times the
-- garrison's, as CA's turn-one openings order (wh3_campaign_ai.lua:451), instead of sitting the
-- siege out. Autoresolve still decides it. Never a player's town. Every empire, and free
-- (2026-11-16): soak 3 turned 6 of 9 presses into captures and left 3 unpressed on an empty budget.
local SIEGE_ODDS = 1.5

function derpy_director:press_siege(character, r)
	if not self:setting("empires") or not character or character:is_null_interface() then return false end
	local f = character:faction()
	if not f or f:is_null_interface() or f:is_human() then return false end
	if not self:is_ambitious(f:name()) then return false end
	local owner = r:owning_faction()
	if not owner or owner:is_null_interface() or owner:is_human() then return false end
	if not character:has_military_force() then return false end
	local mine = character:military_force():strength()
	local g = r:garrison_residence()
	local army = g and not g:is_null_interface() and g:army()
	local theirs = (army and not army:is_null_interface()) and army:strength() or 0
	if mine < SIEGE_ODDS * theirs then
		log(string.format("siege of %s held: %s %.0f against %.0f", r:name(), f:name(), mine, theirs))
		return false
	end
	cm:attack_region(cm:char_lookup_str(character), r:name())
	log(string.format("siege of %s pressed: %s %.0f against %.0f", r:name(), f:name(), mine, theirs))
	return true
end

-- THE LEVERS. Every HELP_EVERY turns for an empire at or behind its schedule, each priced from the
-- one budget. Never with, against or about a player, and never against another empire.
-- No war target: the payload builder's war_coordination_target returned false for every shape tried
-- on two AI factions at war (2026-11-15), so there is no script route to aim an AI at a town.
local HELP_EVERY = 3
local EMPIRE_MERGE_EVERY = 10
local PEACE_DEAL = "diplomatic_option_peace"

-- Each settlement next to f's land and the computer faction holding it, once each, weakest
-- holder first (fewest settlements, then the region key).
function derpy_director:borders(f)
	local seen, found = {}, {}
	for _, r in model_pairs(f:region_list()) do
		for _, adj in model_pairs(r:adjacent_region_list()) do
			local o = adj:owning_faction()
			if not seen[adj:name()] and o and not o:is_null_interface() and not o:is_dead()
				and not o:is_human() and o:name() ~= f:name() and not self:is_ambitious(o:name()) then
				seen[adj:name()] = true
				found[#found + 1] = {r = adj:name(), o = o, n = o:region_list():num_items()}
			end
		end
	end
	table.sort(found, function(a, b)
		if a.n ~= b.n then return a.n < b.n end
		return a.r < b.r
	end)
	return found
end

-- The weakest enemy next door, if it is fighting one: the war it can win, left for it to win.
function derpy_director:empire_front(key)
	local f = alive(key)
	if not f then return nil end
	for _, b in ipairs(self:borders(f)) do
		if f:at_war_with(b.o) then return b.o:name() end
	end
	return nil
end

-- With no war to point: the weakest neighbour it is not bound to, nor could later absorb.
function derpy_director:empire_stance(key)
	local f = alive(key)
	if not f then return nil end
	for _, b in ipairs(self:borders(f)) do
		local o = b.o
		if not f:at_war_with(o) and not f:defensive_allies_with(o) and not f:military_allies_with(o)
			and not f:is_vassal_of(o) and not o:is_vassal_of(f) and o:subculture() ~= f:subculture() then
			return o:name()
		end
	end
	return nil
end

-- Far behind: peace with the weakest enemy stronger than it, so it turns on the war it can win.
function derpy_director:empire_peace(key, skip_key)
	local f = alive(key)
	if not f then return nil end
	local n = f:region_list():num_items()
	local foes = {}
	for _, o in model_pairs(f:factions_at_war_with()) do
		if not o:is_null_interface() and not o:is_dead() and not o:is_human() and o:name() ~= skip_key
			and o:region_list():num_items() > n then
			foes[#foes + 1] = {k = o:name(), n = o:region_list():num_items()}
		end
	end
	table.sort(foes, function(a, b)
		if a.n ~= b.n then return a.n < b.n end
		return a.k < b.k
	end)
	if #foes == 0 then return nil end
	local foe = foes[1].k
	local sa, sb, oa, ob = self:beat_ask(key, foe, PEACE_DEAL, "peace ask")
	if not (oa and ob and sa and sb and sa + sb > 0) or not self:afford(PRICE.force) then return nil end
	cm:force_make_peace(key, foe)
	log(string.format("peace %s + %s", key, foe))
	return foe
end

-- Far behind: a weaker kin it has met folds in, by the merge route's own rules, one every
-- EMPIRE_MERGE_EVERY turns, through merge_first like every other merge.
function derpy_director:empire_merge(key, st, turn)
	if turn - (st.merged[key] or -99) < EMPIRE_MERGE_EVERY then return nil end
	local f = alive(key)
	if not f then return nil end
	local merged = self:merge_first(key, function()
		local n = f:region_list():num_items()
		local kin = {}
		for _, m in model_pairs(f:factions_met()) do
			local mn = m:region_list():num_items()
			if m:subculture() == f:subculture() and mn < n and not self:is_ambitious(m:name()) then
				kin[#kin + 1] = {k = m:name(), n = mn}
			end
		end
		table.sort(kin, function(a, b)
			if a.n ~= b.n then return a.n < b.n end
			return a.k < b.k
		end)
		local found = {}
		for i, c in ipairs(kin) do found[i] = {key, c.k} end
		return found
	end, nil, "empire")
	if not merged then return nil end
	st.merged[key] = turn
	self:chronicle({t = turn, k = "empire_merge", i = key, v = merged[2]})
	return merged[2]
end

-- The great power's back: its strongest AI neighbour it is not at war with, other than skip_key.
function derpy_director:empire_friend(key, skip_key)
	local f = alive(key)
	if not f then return nil end
	local b = self:borders(f)
	for i = #b, 1, -1 do
		local o = b[i].o
		if o:name() ~= skip_key and not f:at_war_with(o) then return o:name() end
	end
	return nil
end

function derpy_director:help(key, band, st, turn)
	st.help[key] = turn
	log(string.format("empire %s helped (%s) turn %d", key, band, turn))
	local great = self:is_great(key, st)
	-- With no war next door, a hostile stance toward the weakest neighbour; the AI decides the rest.
	-- The great power is also turned friendly toward its strongest, so it opens one front at a time.
	-- One beat, one price.
	local front = self:empire_front(key)
	if not front then
		local n = self:empire_stance(key)
		local friend = great and self:empire_friend(key, n) or nil
		if (n or friend) and self:afford(PRICE.mood) then
			if n then self:beat_stance(key, n, STANCE_HOSTILE) end
			if friend then self:beat_stance(key, friend, STANCE_FRIENDLY) end
		end
	end
	-- Peace and kin: far behind, or for the great power as soon as it is behind (spec 15.1).
	if band ~= "far" and not great then return end
	local foe = self:empire_peace(key, front)
	if foe then self:chronicle({t = turn, k = "empire_peace", i = key, v = foe}) end
	self:empire_merge(key, st, turn)
end

-- THE CHEATS (spec 6b), only when the player picks them in MCT: multiplayer falls back to the
-- default, "natural". Only for an empire far behind, once every CHEAT_EVERY turns. Not charged to
-- the budget and not chronicled, since the player chose them.
-- 5, not 10 (2026-11-16): soak 4's great power gained about 10 settlements every 10 turns against a
-- schedule rising 12.5, with the cheats firing every 10.
local CHEAT_EVERY = 5
local EMPIRE_GOLD = 5000

function derpy_director:empire_cheats(key, st, turn)
	local level = self:setting("empire_help")
	if level ~= "generous" and level ~= "relentless" then return end
	st.cheat[key] = turn
	cm:treasury_mod(key, EMPIRE_GOLD)
	log(string.format("empire %s cheat turn %d: %s, %d gold", key, turn, level, EMPIRE_GOLD))
	if level ~= "relentless" then return end
	self:cheat_army(key)
	self:cheat_ruin(key)
end

-- A copy of its largest army at its capital: the same units without the general, item 0, as CA's
-- own scripts skip it. create_force puts a generic general at its head.
function derpy_director:cheat_army(key)
	local f = alive(key)
	local home = f and f:home_region()
	if not home or home:is_null_interface() then return end
	local best, best_n = nil, 0
	for _, mf in model_pairs(f:military_force_list(true)) do
		if mf:has_general() and not mf:is_armed_citizenry() and mf:unit_list():num_items() > best_n then
			best, best_n = mf, mf:unit_list():num_items()
		end
	end
	if not best then return end
	local units = {}
	for i = 1, best_n - 1 do units[#units + 1] = best:unit_list():item_at(i):unit_key() end
	if #units == 0 then return end
	local x, y = cm:find_valid_spawn_location_for_character_from_settlement(key, home:name(), false,
		true, 5)
	if x == -1 then
		log("empire " .. key .. " cheat army: no room at " .. home:name())
		return
	end
	cm:create_force(key, table.concat(units, ","), home:name(), x, y, true)
	log(string.format("empire %s cheat army: %d units at %s", key, #units, home:name()))
end

-- The abandoned settlement next to its land with the lowest key. A ruin has no owner, so no player
-- ever loses one.
function derpy_director:cheat_ruin(key)
	local f = alive(key)
	if not f then return end
	local best
	for _, r in model_pairs(f:region_list()) do
		for _, adj in model_pairs(r:adjacent_region_list()) do
			if adj:is_abandoned() and (not best or adj:name() < best) then best = adj:name() end
		end
	end
	if not best then return end
	cm:transfer_region_to_faction(best, key)
	log("empire " .. key .. " cheat ruin: " .. best)
end

-- Once a turn, from the WorldStartRound listener.
function derpy_director:empire_turn()
	if not self:setting("empires") then
		-- Switched off mid-campaign: hand back a raised potential, and write nothing else.
		local saved = cm:get_saved_value("derpy_director_empires")
		if type(saved) == "table" and saved.potential then
			self:release_potential(saved)
			cm:set_saved_value("derpy_director_empires", saved)
		end
		return
	end
	local s = self:seed()
	if not s or not s.ambitious then return end
	local turn = cm:model():turn_number()
	local st = self:empires()
	if not st.great then self:assign_roles(st) end
	for _, k in ipairs(self:seed().ambitious) do
		local f = alive(k)
		if f and not st.graduated[k] then
			local n = f:region_list():num_items()
			if n >= self:empire_goal(k, st) then self:graduate(k, st, turn, n) end
		end
	end
	if turn >= EMPIRE_CHECK_FIRST and (turn - EMPIRE_CHECK_FIRST) % EMPIRE_CHECK_EVERY == 0 then
		self:empire_check(st, turn)
	end
	self:temper(st, turn)
	self:pace(st)
	for _, k in ipairs(self:seed().ambitious) do
		local band = self:empire_band(k, turn)
		if (band == "behind" or band == "far") and turn - (st.help[k] or -99) >= HELP_EVERY then
			self:help(k, band, st, turn)
		end
		if band == "far" and turn - (st.cheat[k] or -99) >= CHEAT_EVERY then
			self:empire_cheats(k, st, turn)
		end
	end
	cm:set_saved_value("derpy_director_empires", st)
end

-- The factions nobody may feed: the measured leader at runaway_merge_tier or above, and every
-- living invader. Sorted, once each.
-- min_tier: the merge trigger passes the runaway_merge_tier setting; merge_blocked passes 1, so a
-- merge never feeds a measured runaway whatever that setting says.
function derpy_director:runaway_keys(min_tier)
	local found = {}
	local st = self:runaway()
	if st.tier > 0 and st.leader_key and st.tier >= (min_tier or 1) then
		found[st.leader_key] = true
	end
	for _, f in model_pairs(cm:model():world():faction_list()) do
		if not f:is_null_interface() and not f:is_dead() and self:is_invader(f) then
			found[f:name()] = true
		end
	end
	local out_list = {}
	for k in pairs(found) do out_list[#out_list + 1] = k end
	table.sort(out_list)
	return out_list
end

function derpy_director:is_runaway(key)
	for _, r in ipairs(self:runaway_keys(self:setting("runaway_merge_tier") or 1)) do
		if r == key then return true end
	end
	return false
end

-- Only the runaway TAKING land: opportunism reverses the roles (its instigator is the faction that
-- lost ground), a confederation's victim is already absorbed, and treachery, a seized convoy and a
-- secession are not land taken.
local RUNAWAY_KINDS = {sack = true, raze = true, conquest = true}

function derpy_director:runaway_merge(sit)
	if sit.merged or not RUNAWAY_KINDS[sit.kind] then return false end
	local v = cm:get_faction(sit.victim)
	if not v or v:is_null_interface() or v:is_dead() or v:is_human() then return false end
	if not self:is_runaway(sit.instigator) then return false end
	return self:try_merge(sit, "runaway")
end

local function humans()
	local out_list = {}
	for _, k in ipairs(cm:get_human_factions()) do
		local f = cm:get_faction(k)
		if f and not f:is_null_interface() then out_list[#out_list + 1] = f end
	end
	return out_list
end

-- Why absorber may not take in target, or nil. Checked before any probe, whatever the probe says.
-- runaways is runaway_keys(1), worked out once per try_merge rather than once per kin.
function derpy_director:merge_blocked(a_key, t_key, sit, runaways)
	local a, t = cm:get_faction(a_key), cm:get_faction(t_key)
	if not a or not t or a:is_null_interface() or t:is_null_interface() then
		return "a faction is missing"
	end
	for _, f in ipairs({a, t}) do
		if f:is_dead() then return f:name() .. " is dead" end
		if f:is_rebel() then return f:name() .. " is a rebel faction" end
		if f:is_human() then return f:name() .. " is a player" end
		if self:is_invader(f) then return f:name() .. " is an endgame invader" end
		-- A vassal is part of its master's realm, and what the probe and the payload do with a
		-- vassalage is unmeasured.
		if f:is_vassal() then return f:name() .. " is a vassal" end
	end
	local players = humans()
	for _, h in ipairs(players) do
		if h:is_vassal_of(a) or h:is_vassal_of(t) then return "a player is a vassal of one of them" end
	end
	-- A rising's provinces would go to another house, and the player could never win them back.
	local risings = cm:get_saved_value("derpy_director_risings")
	if type(risings) == "table" and (risings[a_key] or risings[t_key]) then
		return "one of them rose in an Iron Court secession"
	end
	local sc = a:subculture()   -- kin_for hands over kin only, so t:subculture() is the same
	local races = derpy_director_merge_races
	if not (races and races[sc]) then return "the game does not let this race confederate" end
	if not self:setting("race_" .. sc) then return "the race switch is off" end
	-- The Tower of Zharr: a player annexes Chaos Dwarf houses by claiming their seats, so while one
	-- plays them, the houses stay for the player to take. CA does the same for Dwarfs and High Elves.
	if sc == CHD_SC then
		for _, h in ipairs(players) do
			if h:subculture() == CHD_SC then return "a player plays the Chaos Dwarfs" end
		end
	end
	if a:at_war_with(t) then return "they are at war" end
	-- Never feed the runaway, nor anyone standing with it.
	for _, r in ipairs(runaways) do
		if r == a_key then return a_key .. " is the runaway" end
		local rf = cm:get_faction(r)
		-- a:is_vassal_of(rf) needs no test: a vassal was refused above.
		if rf and not rf:is_null_interface() and (rf:is_vassal_of(a)
				or a:military_allies_with(rf) or a:defensive_allies_with(rf)) then
			return a_key .. " stands with the runaway " .. r
		end
	end
	if sit and a_key == sit.instigator then return a_key .. " is the attacker" end
	return nil
end

-- The victim's kin who have met it, most regions first, ties by key. The dead are left in for
-- merge_blocked to refuse, so the log says why a kin was passed over.
function derpy_director:kin_for(victim_key)
	local v = cm:get_faction(victim_key)
	if not v or v:is_null_interface() then return {} end
	local sc = v:subculture()
	local scored = {}
	for _, f in model_pairs(cm:model():world():faction_list()) do
		if not f:is_null_interface() and f:name() ~= victim_key
				and f:subculture() == sc then
			for _, m in model_pairs(f:factions_met()) do
				if m:name() == victim_key then
					scored[#scored + 1] = {name = f:name(), n = f:region_list():num_items()}
					break
				end
			end
		end
	end
	table.sort(scored, function(x, y)
		if x.n ~= y.n then return x.n > y.n end
		return x.name < y.name
	end)
	local out_list = {}
	for i = 1, #scored do out_list[i] = scored[i].name end
	return out_list
end

-- The payload route, the one that works for every race (force_confederation has done nothing for
-- Chaos Dwarfs since the 2026-10-09 patch). FactionJoinsConfederation fires INSIDE apply_payload,
-- so self.merging names the pair while the call runs and from_confederation drops exactly that
-- one; it is cleared on every path, or a fault would swallow the next real confederation.
function derpy_director:merge(absorber_key, target_key, mode)
	self.merging = absorber_key .. "|" .. target_key
	local ok, err = pcall(function()
		local a, t = cm:get_faction(absorber_key), cm:get_faction(target_key)
		local p = cm:create_payload()
		if not p:form_confederation(a, t, false, false) then error("form_confederation refused") end
		cm:apply_payload(p, a)
	end)
	self.merging = nil
	if not ok then
		log(string.format("merge failed: %s + %s: %s", absorber_key, target_key, tostring(err)))
		return false
	end
	log(string.format("merge %s absorbs %s (%s)", absorber_key, target_key, mode))
	return true
end

-- mode is "last_stand" (the kin takes the victim in) or "runaway" (the side with more regions
-- takes the other in). The price and the turn's slot are charged only once a legal partner is found.
function derpy_director:try_merge(sit, mode)
	local victim = sit.victim
	if not self:setting(mode == "last_stand" and "merge_last_stand" or "merge_runaway") then
		return false
	end
	local merged = self:merge_first(victim, function()
		local v = cm:get_faction(victim)
		local found = {}
		for _, k in ipairs(self:kin_for(victim)) do
			local absorber, target = k, victim
			if mode == "runaway" then
				local nk, nv = cm:get_faction(k):region_list():num_items(), v:region_list():num_items()
				if nv > nk or (nv == nk and victim < k) then absorber, target = victim, k end
			end
			found[#found + 1] = {absorber, target}
		end
		return found
	end, sit, mode)
	if not merged then return false end
	sit.merge = {merged[1], merged[2], mode}
	return true
end

-- The end of every merge route, the empires' included: the turn's gate, then each pair from
-- candidates() in order until one is legal, willing and done. Returns that pair, or nil. who names
-- the merge in the log. candidates() runs only past the gate, so a dozen early last stands a turn
-- cost no kin scan.
function derpy_director:merge_first(who, candidates, sit, mode)
	local turn = cm:model():turn_number()
	local price = self:setting("merge_price") or 60
	local why
	if turn < (self:setting("merge_from_turn") or 10) then
		-- A dozen last stands a turn is normal before the first merge turn: said once a turn.
		if self.too_early_turn == turn then return nil end
		self.too_early_turn = turn
		why = "too early"
	elseif merge_count(turn) >= (self:setting("merges_per_turn") or 1) then
		why = "this turn's confederations are spent"
	elseif self:budget() < price then
		why = string.format("budget %d cannot pay %d", self:budget(), price)
	end
	if why then
		log(string.format("no merge for %s: %s", who, why))
		return nil
	end
	local runaways = self:runaway_keys(1)
	local probed = 0
	for _, pair in ipairs(candidates()) do
		if probed >= MERGE_PROBES then break end
		local absorber, target = pair[1], pair[2]
		local blocked = self:merge_blocked(absorber, target, sit, runaways)
		if blocked then
			log(string.format("no merge %s + %s: %s", absorber, target, blocked))
		else
			probed = probed + 1
			local sa, sb, oa, ob = self:beat_ask(absorber, target, CONFED_DEAL, "merge ask")
			local willing = not self:setting("merge_needs_willing")
				or (sa and sb and sa + sb > 0)
			if oa and ob and willing then
				if not self:merge(absorber, target, mode) then return nil end
				-- Read before the turn is written: merge_count trusts the count only when the turn matches.
				local n = merge_count(turn) + 1
				self:afford(price)
				cm:set_saved_value("derpy_director_merge_turn", turn)
				cm:set_saved_value("derpy_director_merge_count", n)
				return pair
			end
		end
	end
	log(string.format("no merge for %s: no kin would or could take it in", who))
	return nil
end

-- A computer faction down to its last regions by force folds into stronger kin. Once per victim a
-- turn: a province falls as one event per town.
function derpy_director:last_stand(sit)
	if sit.kind ~= "conquest" and sit.kind ~= "raze" then return false end
	local v = cm:get_faction(sit.victim)
	if not v or v:is_null_interface() or v:is_dead() or v:is_human() or v:is_rebel() then
		return false
	end
	if v:region_list():num_items() > (self:setting("last_stand_regions") or 1) then return false end
	local when = cm:get_saved_value("derpy_director_last_stand_turn")
	local seen = cm:get_saved_value("derpy_director_last_stand_set")
	if when ~= sit.turn or type(seen) ~= "table" then seen = {} end
	if seen[sit.victim] then return false end
	seen[sit.victim] = true
	cm:set_saved_value("derpy_director_last_stand_turn", sit.turn)
	cm:set_saved_value("derpy_director_last_stand_set", seen)
	return self:try_merge(sit, "last_stand")
end

-- treasury_mod only takes a positive value, so this can fund a muster but never fine anyone.
function derpy_director:beat_warchest(faction_key, amount)
	local f = cm:get_faction(faction_key)
	if not f or f:is_null_interface() then return false end
	cm:treasury_mod(faction_key, amount)
	log(string.format("warchest %d to %s", amount, faction_key))
	return true
end

-- Razing breeds disease. Since 9.0 the call is (spreader faction interface, region, plague key);
-- CA's own callers pass whoever caused the plague, so the razer spreads it.
function derpy_director:beat_plague(sit)
	local rm = cm:model():world():region_manager()
	local region = rm:region_by_key(sit.region)
	if not region or region:is_null_interface() then return false end
	local spreader = cm:get_faction(sit.instigator)
	if not spreader or spreader:is_null_interface() then return false end
	local roll = cm:random_number(#PLAGUES, 1)
	local key = PLAGUES[roll] or PLAGUES[1]
	cm:spawn_plague_at_region(spreader, region, key)
	log(string.format("plague %s in %s", key, sit.region))
	return true
end

function derpy_director:rebel_faction(faction_key)
	local f = cm:get_faction(faction_key)
	-- get_faction returns false, not nil, for an unknown key. A faction that just lost its last
	-- region still has a subculture, so a wiped-out owner can still raise its own rebels.
	if not f or f:is_null_interface() then return nil end
	return REBEL_FACTIONS[f:subculture()]
end

-- With a faction, not force_rebellion_in_region, whose generic `rebels` belong to nobody.
-- Args: region interface, faction key, units, full strength. The unpassed 5th suppresses the
-- public order penalty, not the message.
function derpy_director:beat_unrest(sit, units)
	local rm = cm:model():world():region_manager()
	local region = rm:region_by_key(sit.region)
	if not region or region:is_null_interface() then
		log("no unrest: " .. tostring(sit.region) .. " is not a region on this map")
		return false
	end
	-- No rebel faction, no rising: the generic call is the anonymous uprising this replaced.
	local faction = self:rebel_faction(sit.victim)
	if not faction then
		log(string.format("no unrest in %s: %s has no rebel faction", tostring(sit.region),
			tostring(sit.victim)))
		return false
	end
	cm:force_rebellion_with_faction(region, faction, units, false)
	log(string.format("unrest %d units in %s as %s", units, sit.region, faction))
	return true
end

-- Takes faction interfaces and returns (score, can be proposed). CA: a score above zero means
-- it would likely be accepted.
function derpy_director:beat_ask(a_key, b_key, deal, label)
	local a, b = cm:get_faction(a_key), cm:get_faction(b_key)
	if not a or not b or a:is_null_interface() or b:is_null_interface() then
		return nil, nil, false, false
	end
	local score_a, ok_a = cm:cai_evaluate_quick_deal_action(a, b, deal)
	local score_b, ok_b = cm:cai_evaluate_quick_deal_action(b, a, deal)
	-- Log both: ok=false means the engine will not propose it, a score <= 0 means the AI refused.
	log(string.format("%s %s<->%s %s/%s ok=%s/%s", label or "ask", a_key, b_key,
		tostring(score_a), tostring(score_b), tostring(ok_a), tostring(ok_b)))
	return score_a, score_b, ok_a, ok_b
end

-- Per pair and directional, with clear calls, so it is reversible. A situation never writes the
-- global threat score: the runaway step is its only writer. Promote leans; block_all_but steers.
function derpy_director:beat_stance(who_key, target_key, stance)
	local a = cm:get_faction(who_key)
	local b = cm:get_faction(target_key)
	if not a or a:is_null_interface() then return false end
	if not b or b:is_null_interface() then return false end
	cm:cai_strategic_stance_manager_promote_specified_stance_towards_target_faction(
		who_key, target_key, stance)
	log(string.format("stance %s -> %s %s", who_key, target_key, stance))
	return true
end

-- The force_* family takes KEY STRINGS for both factions, unlike the cai_ calls above.
function derpy_director:beat_force(a_key, b_key)
	-- force_confederation(X, X) crashes the game; the self-check stays with the whole family.
	if a_key == b_key then
		log("force refused: a faction cannot treat with itself")
		return false
	end
	cm:force_alliance(a_key, b_key, false)
	log("forced defensive alliance " .. a_key .. " + " .. b_key)
	return true
end

-- No strength argument (the magnitude lives in the event's DB row) and no inverse, so the caller
-- fires it once per feud.
function derpy_director:beat_past_event(from_key, to_key)
	cm:cai_add_diplomatic_event(from_key, to_key, PAST_EVENT)
	log(string.format("past_event from=%s to=%s %s", from_key, to_key, PAST_EVENT))
	return true
end

-- The text is loc keys only, so every line must be true of every situation it fires for; the map
-- point carries the specifics. The records are scripted_transient_located: persistent must be
-- false, the plain show_message_event draws nothing for them, and a blank secondary draws an
-- empty black box.
function derpy_director:beat_tell(sit, kind, cast)
	local rec = self:feed_record(kind, self:voice_of(cast))
	if not rec then return false end
	-- Safe inside an event handler; at script root a local-faction call CTDs uncatchably.
	local player = cm:get_local_faction_name(true)
	if not player or player == "" then return false end
	-- Only when the player is one of the two parties, as the Great Guilds do: other people's
	-- quarrels put a popup over the map every turn (six in six turns, 2026-11-14). The cast is
	-- never human, so instigator and victim are the only ways in. The beats still ran.
	if player ~= sit.instigator and player ~= sit.victim then return false end
	-- No settlement, no point to fly to; 0,0 is the map origin, not nowhere.
	if not (sit.x and sit.y) then
		log("feed " .. kind .. " withheld, region has no map point")
		return false
	end
	cm:show_message_event_located(player, rec.title, rec.body, rec.tail, sit.x, sit.y,
		false, rec.index)
	log(string.format("feed %s index=%d to=%s", kind, rec.index, player))
	return true
end

-- Loyalty moves in the player's Iron Court, as {party, delta} pairs. Human courts only, as the
-- court's own war council reacts. IC.court builds an empty court for a key it has not read yet, so
-- the court is read from the save first, as IC's own listeners do, and saved after a move. A party
-- the court does not have moves nothing. There is no Record line: IC.log refuses a kind it does
-- not know, so the move shows only on the party's loyalty.
function derpy_director:court_moves(faction_key, moves, why)
	local ic = self.ic
	if not ic or not ic.is_human(faction_key) then return false end
	local f = cm:get_faction(faction_key)
	if not f or f:is_null_interface() or not ic.runs_court(f) then return false end
	ic.loaded(faction_key)
	local moved = false
	for i = 1, #moves do
		local party, delta = moves[i][1], moves[i][2]
		if ic.move_loyalty(faction_key, party, delta) then
			moved = true
			log(string.format("court %s %s loyalty %+d (%s)", faction_key, party, delta, why))
		end
	end
	if moved then ic.save(faction_key) end
	return moved
end

-- Kin-slaying, priced by the slayer's own faith: the Iron Court's temple party, and the Great
-- Guilds' temple Reputation. GG.penalise clamps to what is held and re-applies the rank, so a fall
-- through a threshold takes the rank bundle off. It takes a faction key. Only the slayer hears of
-- the Reputation, and only when something was actually lost.
function derpy_director:beat_temple(sit, why)
	if why ~= "kinslaying" or not KIN_DEEDS[sit.kind] then return false end
	local f = cm:get_faction(sit.instigator)
	if not f or f:is_null_interface() or not KIN_CONDEMNED[f:subculture()] then return false end
	local court = self:court_moves(sit.instigator, {{"temple", -COURT_KIN_LOSS}}, "kinslaying")
	local gg = self.guilds
	if not gg then return court end
	local lost = gg.penalise(sit.instigator, "temple", KIN_TEMPLE_LOSS)
	if type(lost) ~= "number" or lost <= 0 then return court end
	log(string.format("temple Reputation %s -%d", sit.instigator, lost))
	if cm:get_local_faction_name(true) == sit.instigator then self:beat_tell(sit, "guild", {}) end
	return true
end

local CHRONICLE_CAP = 100

-- THE CHRONICLE (2026-11-15), which derpy_director_chronicle.lua draws. Keys and numbers only: a
-- loc call from a listener CTDs at turn 1, past pcall, so every name and sentence is resolved when
-- the panel draws. Capped, because it rides in the save all campaign. Written only from model
-- events, so every machine in a multiplayer game writes the same one.
function derpy_director:chronicle(entry)
	local buf = cm:get_saved_value("derpy_director_chronicle")
	if type(buf) ~= "table" then
		buf = {}
		-- The news buffer this replaced (50 entries of another shape), freed by the first write.
		-- clear_saved_value, never set_saved_value(key, nil): CA's set refuses nil with a script
		-- error and keeps the old value (lib_campaign_manager.lua:1860).
		if cm:get_saved_value("derpy_director_news") ~= nil then
			cm:clear_saved_value("derpy_director_news")
		end
	end
	buf[#buf + 1] = entry
	while #buf > CHRONICLE_CAP do table.remove(buf, 1) end
	cm:set_saved_value("derpy_director_chronicle", buf)
end

-- A story: the deed and what answered it, as the beats noted it on the situation. A deed nobody
-- answered and nobody confederated over is not one.
function derpy_director:news(sit, cast)
	-- A cast the budget could not turn (a runaway merge can spend it first) turned against nobody,
	-- and every beat after the stance push costs more than it, so nothing else was done either.
	if not sit.turned then cast = {} end
	if #cast == 0 and not sit.merge then return end
	local c = {}
	for i = 1, #cast do c[i] = cast[i] end
	self:chronicle({t = sit.turn, k = sit.kind, i = sit.instigator, v = sit.victim,
		r = sit.region or "", c = c, p = sit.pacts, g = sit.grudge, u = sit.rebels,
		pl = sit.plague, m = sit.merge})
end

-- A war is a story only when the Chronicle already holds its cause: a deed by the target that the
-- declarer suffered or was turned against, within WAR_MEMORY turns, or the target being the power
-- the world fears. A war with no recorded cause is the AI's own business, and is not guessed at.
local WAR_MEMORY = 10
function derpy_director:note_war(context)
	if not context:is_war() or context:result_of_confederation() then return end
	local d, t = context:proposer(), context:recipient()
	if not d or d:is_null_interface() or not t or t:is_null_interface() then return end
	local dk, tk = d:name(), t:name()
	if dk == tk then return end
	local turn = cm:model():turn_number()
	local buf = cm:get_saved_value("derpy_director_chronicle")
	if type(buf) ~= "table" then buf = {} end
	for i = #buf, 1, -1 do
		local e = buf[i]
		if turn - (e.t or 0) > WAR_MEMORY then break end
		if e.k == "war" and e.i == dk and e.v == tk then return end
		-- Only a story carries a cast; the runaway step's entries do not.
		if e.c and e.i == tk then
			local wronged = e.v == dk
			for j = 1, #e.c do if e.c[j] == dk then wronged = true end end
			if wronged then
				self:chronicle({t = turn, k = "war", i = dk, v = tk, w = e.k, r = e.r, x = e.v})
				return
			end
		end
	end
	local st = cm:get_saved_value("derpy_director_runaway")
	if self:setting("runaway_threat") and type(st) == "table" and (st.tier or 0) > 0
			and st.leader_key == tk then
		self:chronicle({t = turn, k = "war", i = dk, v = tk, w = "runaway"})
	end
end

-- The settlement's logical position, which show_message_event_located takes. Nil without one.
function derpy_director:map_point(region)
	if not region or region:is_null_interface() then return nil, nil end
	local settlement = region:settlement()
	if not settlement or settlement:is_null_interface() then return nil, nil end
	return settlement:logical_position_x(), settlement:logical_position_y()
end

-- Builders store faction keys, never interfaces, because a situation is saved and compared.
-- Sack and raze share a context: character() did it, garrison_residence() is who and where.
-- There is no context:instigator(); an invented one passed every offline check and failed live.
function derpy_director:from_settlement(context, kind)
	local char = context:character()
	if not char or char:is_null_interface() then return nil end
	local garrison = context:garrison_residence()
	if not garrison or garrison:is_null_interface() then return nil end
	local instigator = char:faction()
	local victim = garrison:faction()
	if not instigator or instigator:is_null_interface() then return nil end
	if not victim or victim:is_null_interface() then return nil end
	local region = garrison:region()
	if not region or region:is_null_interface() then return nil end
	local x, y = self:map_point(region)
	return {
		kind = kind,
		instigator = instigator:name(),
		victim = victim:name(),
		region = region:name(),
		turn = cm:model():turn_number(),
		x = x,
		y = y,
	}
end

-- previous_faction() lost the region, region():owning_faction() holds it now. Only a capture by
-- force counts. Every value reason() returns, per CA's wh2_dlc13_empire_politics.lua:
-- "normal capture", "campaign director", "unopposed capture", "bribery", "surrendered region",
-- "diplomacy trade", "cli command", "startpos setup", "abandoned", "abandoned to rebels",
-- "civil war", "payload", "unknown reason".
local CONQUEST_REASONS = {
	["normal capture"] = true, ["unopposed capture"] = true,
}

function derpy_director:from_region_change(context, kind)
	local region = context:region()
	if not region or region:is_null_interface() then return nil end
	local loser = context:previous_faction()
	if not loser or loser:is_null_interface() then return nil end
	local winner = region:owning_faction()
	if not winner or winner:is_null_interface() then return nil end
	if winner:name() == loser:name() then return nil end
	local ok, reason = pcall(function() return context:reason() end)
	if ok and type(reason) == "string" and not CONQUEST_REASONS[reason] then
		log("dropped: region changed hands by " .. reason .. ", not by force")
		return false
	end
	local x, y = self:map_point(region)
	return {
		kind = kind,
		instigator = winner:name(),
		victim = loser:name(),
		region = region:name(),
		turn = cm:model():turn_number(),
		x = x,
		y = y,
	}
end

-- confederation() absorbs faction(); the point is neighbours noticing a bloc form. outrage()
-- scores a same-culture pair as kin-slaying (1.5), so this draws a full cast and can earn a grudge.
-- The absorbed faction owns nothing by now, so reach anchors on the absorber's home region.
function derpy_director:from_confederation(context, kind)
	local absorber = context:confederation()
	if not absorber or absorber:is_null_interface() then return nil end
	local absorbed = context:faction()
	if not absorbed or absorbed:is_null_interface() then return nil end
	if absorber:name() == absorbed:name() then return nil end
	-- The Director's own merge, raised inside its own apply_payload: not anybody's deed.
	if self.merging == absorber:name() .. "|" .. absorbed:name() then
		log(string.format("own merge, not a deed: %s + %s", absorber:name(), absorbed:name()))
		return false
	end
	local home = absorber:home_region()
	if not home or home:is_null_interface() then return nil end
	local x, y = self:map_point(home)
	return {
		kind = kind,
		instigator = absorber:name(),
		victim = absorbed:name(),
		region = home:name(),
		turn = cm:model():turn_number(),
		x = x,
		y = y,
	}
end

-- A treaty broken: proposer() broke it and recipient() was betrayed. Alliances of the three kinds
-- and non-aggression pacts only; ending trade or military access is business, not betrayal, and a
-- confederation ends treaties as a matter of course. Every war declaration raises this event too,
-- so a plain one is returned as false with no log line: a line each would bury the log.
local BETRAYALS = {"was_alliance", "was_military_alliance", "was_defensive_alliance",
                   "was_non_aggression_pact"}

function derpy_director:from_treaty_broken(context, kind)
	if context:result_of_confederation() then return false end
	local broken = false
	for i = 1, #BETRAYALS do
		if context[BETRAYALS[i]](context) then broken = true break end
	end
	if not broken then return false end
	local traitor, betrayed = context:proposer(), context:recipient()
	if not traitor or traitor:is_null_interface() then return nil end
	if not betrayed or betrayed:is_null_interface() then return nil end
	if traitor:name() == betrayed:name() then return nil end
	-- At the betrayed faction's home, where its neighbours are.
	local home = betrayed:home_region()
	if not home or home:is_null_interface() then return nil end
	local x, y = self:map_point(home)
	return {
		kind = kind,
		instigator = traitor:name(),
		victim = betrayed:name(),
		region = home:name(),
		turn = cm:model():turn_number(),
		x = x,
		y = y,
	}
end

-- Each town taken by force this round, by loser and taker, for the next turn start.
function derpy_director:note_loss(sit)
	local losses = cm:get_saved_value("derpy_director_losses")
	if type(losses) ~= "table" then losses = {} end
	local l = losses[sit.victim] or {n = 0, by = {}}
	l.n = l.n + 1
	l.by[sit.instigator] = (l.by[sit.instigator] or 0) + 1
	losses[sit.victim] = l
	cm:set_saved_value("derpy_director_losses", losses)
end

-- The Director's own clock, RimWorld's storyteller in miniature. At each turn start, with the
-- temperament's chance, one faction that lost settlements by force last round is drawn by how
-- many it lost, and the neighbours who already hated it smell blood. Its victim is whoever took
-- the most from it, so that is who hears of it. A player is never the target: when the player is
-- losing ground, adaptation says ease off, not pile on.
function derpy_director:opportunity()
	local losses = cm:get_saved_value("derpy_director_losses")
	cm:set_saved_value("derpy_director_losses", {})
	if type(losses) ~= "table" then return false end
	local turn = cm:model():turn_number()
	local keys = {}
	for k, l in pairs(losses) do
		local f = cm:get_faction(k)
		if f and not f:is_null_interface() and not f:is_dead() and not f:is_human()
				and not f:is_rebel() and f:region_list():num_items() > 0
				and l.n >= OPPORTUNITY_LOSSES then
			keys[#keys + 1] = k
		end
	end
	if #keys == 0 then return false end
	table.sort(keys)
	local pct = math.floor(self:temperament().opportunity * self:tension(turn) + 0.5)
	local roll = cm:random_number(100, 1)
	if roll > pct then
		log(string.format("no opportunity this turn: rolled %d against %d%%", roll, pct))
		return false
	end
	local total = 0
	for i = 1, #keys do total = total + losses[keys[i]].n end
	local pick, run, draw = keys[#keys], 0, cm:random_number(total, 1)
	for i = 1, #keys do
		run = run + losses[keys[i]].n
		if draw <= run then pick = keys[i] break end
	end
	local takers = {}
	for k in pairs(losses[pick].by) do takers[#takers + 1] = k end
	table.sort(takers)
	local victor = takers[1]
	for i = 2, #takers do
		if losses[pick].by[takers[i]] > losses[pick].by[victor] then victor = takers[i] end
	end
	local weak = cm:get_faction(pick)
	local home = weak:home_region()
	if not home or home:is_null_interface() then home = weak:region_list():item_at(0) end
	local x, y = self:map_point(home)
	self:respond({kind = "opportunism", instigator = pick, victim = victor, region = home:name(),
		turn = turn, x = x, y = y})
	return true
end

function derpy_director:on_event(context, scenario)
	if not ENABLED then return end
	-- Caught here so the log names the builder that failed.
	local builder = scenario and scenario.build
	if not builder or not self[builder] then
		log("dropped: no builder for " .. tostring(scenario and scenario.event))
		return
	end
	local ok, sit = pcall(function() return self[builder](self, context, scenario.kind) end)
	if not ok then
		log("dropped: " .. builder .. " errored: " .. tostring(sit))
		return
	end
	-- false: the builder dropped it and logged why. nil: the context was missing a part.
	if not sit then
		if sit == nil then log("dropped: incomplete context") end
		return
	end
	self:respond(sit)
end

-- Everything after the situation is built, shared by the watched events and the companion hooks.
function derpy_director:respond(sit)
	local outrage, why = self:outrage(sit)
	outrage = outrage * (OUTRAGE_WEIGHT[sit.kind] or 1)
	-- Betraying an ally is never a shrug, whatever the two cultures think of each other.
	if sit.kind == "treachery" and outrage < OUTRAGE_UNPROVOKED then
		outrage, why = OUTRAGE_UNPROVOKED, "betrayal"
	end
	sit.outrage = outrage
	log(string.format("situation kind=%s instigator=%s victim=%s region=%s turn=%d "
		.. "outrage=%.2f (%s)",
		sit.kind, sit.instigator, sit.victim, tostring(sit.region), sit.turn, outrage, why))
	-- Every town a conquest takes counts toward next turn's opportunism, answered or not.
	if sit.kind == "conquest" then self:note_loss(sit) end

	-- Before the feud guard and with no roll: a province falls as one event per town and the guard
	-- answers only the first, so a gated last stand would miss a faction that lost its last towns
	-- together.
	if self:last_stand(sit) then sit.merged = true end

	-- Before anything is priced. Every town is still logged; the feud is answered once.
	if not self:first_of_feud_this_turn(sit) then
		log("already answered this feud this turn, nothing further")
		self:news(sit, {})
		return
	end

	-- Before the cast: the slayer's own temple hears of it whether or not any neighbour cares.
	self:beat_temple(sit, why)

	-- After the feud guard, so a province of towns is one roll, not one per town.
	if not self:chosen(sit) then
		self:news(sit, {})
		return
	end

	-- First of the answered beats, before the cast: the rarest and largest. The rest take what is
	-- left of the budget.
	if self:runaway_merge(sit) then sit.merged = true end

	local t = self:temperament()
	-- Outrage sizes the audience: sworn enemies draw one neighbour, kin-slaying a full three.
	-- A wild world swings it one either way.
	local take = math.floor(CAST_TAKE * outrage + 0.5)
	if take < 1 then take = 1 end
	if take > CAST_TAKE then take = CAST_TAKE end
	if t.swing then
		take = math.max(1, math.min(CAST_TAKE, take + cm:random_number(3, 1) - 2))
	end
	local cast = self:cast(sit, take)
	log("cast " .. table.concat(cast, ", "))

	-- Nobody in reach cared, so spend nothing.
	if #cast == 0 then
		self:news(sit, cast)
		return
	end

	-- An empire behind its schedule still draws its neighbours' anger, and nothing the Director
	-- would fund against it.
	local sheltered = self:sheltered(sit)
	if sheltered then log("sheltered: " .. sit.instigator .. " is an empire behind its schedule") end

	-- One stance push per responder, aimed at the aggressor alone.
	if self:afford(PRICE.mood) then
		for i = 1, #cast do
			self:beat_stance(cast[i], sit.instigator, STANCE_HOSTILE)
		end
		sit.turned = true
	end

	-- The coalition runs before the grudge: force is cheap and reversible, past_event costly and
	-- permanent, so the grudge takes what is left.
	local pact_shielded = false
	-- A pact or a grudge against the instigator: what the court hears of, and what a ONE_TELL
	-- situation tells once.
	local landed = false
	local one_tell = ONE_TELL[sit.kind]
	local partners = sheltered and {} or self:partners(sit, cast)
	for i = 1, #partners do
		for j = i + 1, #partners do
			local pa, pb = partners[i], partners[j]
			local sa, sb, oa, ob
			if self:at_odds(pa, pb) then
				log(string.format("no ask %s<->%s: they hate each other or are at war", pa, pb))
			else
				sa, sb, oa, ob = self:beat_ask(pa, pb, DEAL)
			end
			-- The sum, not both halves: the directions disagree hard (-14.93 vs +5.72), and in
			-- 151 live asks min(sa, sb) never rose above -1.12, so both-positive never opened.
			if oa and ob and sa and sb and sa + sb > 0 and self:afford(PRICE.force) then
				self:beat_force(pa, pb)
				sit.pacts = sit.pacts or {}
				sit.pacts[#sit.pacts + 1] = {pa, pb}
				landed = true
				if not one_tell then self:beat_tell(sit, "pact", cast) end
				-- A new coalition funds a muster and shields the settlement it formed over, sized
				-- to the aggressor. A wild world pays 50 to 150 percent of it, as Randy sizes his
				-- raids.
				if self:afford(PRICE.warchest) then
					local gold = math.floor(WARCHEST * self:size_scale(sit.instigator))
					if t.swing then gold = math.floor(gold * cm:random_number(150, 50) / 100) end
					local paid_a = self:beat_warchest(pa, gold)
					local paid_b = self:beat_warchest(pb, gold)
					-- The Chronicle says what each side was given, so only when both were.
					if paid_a and paid_b then sit.pacts[#sit.pacts][3] = gold end
				end
				if not pact_shielded and self:afford(PRICE.shield) then
					pact_shielded = self:beat_shield(sit)
				end
			end
		end
	end

	-- Once per feud, not per settlement, and only for a deed above the outrage floor.
	-- Holds the turn the feud's grudge fired; a save from before 2026-11-14 holds true, read as 1.
	local seen_key = "derpy_director_seen_" .. sit.instigator .. "_" .. sit.victim
	local seen = cm:get_saved_value(seen_key)
	if seen == true then seen = 1 end
	if sheltered then
		log("no grudge: sheltered")
	elseif outrage < OUTRAGE_FLOOR then
		log(string.format("no grudge: outrage %.2f (%s) is below %.2f", outrage, why,
			OUTRAGE_FLOOR))
	elseif type(seen) == "number" and sit.turn < seen + GRUDGE_MEMORY then
		log(string.format("no grudge: this feud's grudge from turn %d is still remembered", seen))
	else
		if seen then
			log(string.format("the grudge from turn %d has faded; the feud can be remembered again",
				seen))
		end
		-- The strongest responder only. seen_key is set only when the grudge fires, so a turn
		-- with no budget does not burn the feud.
		if self:grudge_slot(sit.turn) and self:afford(PRICE.past_event) then
			self:beat_past_event(sit.instigator, cast[1])
			sit.grudge = cast[1]
			self:set_cooldown(cast[1])
			landed = true
			-- The grudge records say a settlement was sacked; a seized convoy has its own.
			if not one_tell then
				self:beat_tell(sit, sit.kind == "seizure" and "raid" or "grudge", cast)
			end
			cm:set_saved_value(seen_key, sit.turn)
		end
	end

	if landed then
		if one_tell then self:beat_tell(sit, one_tell, cast) end
		self:court_moves(sit.instigator, {{"legion", COURT_THREAT_GAIN},
			{"ledger", -COURT_THREAT_LOSS}}, "neighbours turned against it")
	end

	-- Per-kind consequences. Both are irreversible, so both sit behind the outrage floor too.
	if outrage >= OUTRAGE_FLOOR and not sheltered then
		if sit.kind == "raze" and self:afford(PRICE.plague) then
			sit.plague = self:beat_plague(sit) or nil
		-- Unrest also needs UNREST_FLOOR; razing is rarer, so the plague keeps the lower one.
		elseif sit.kind == "conquest" and outrage >= UNREST_FLOOR
			   and self:afford(PRICE.unrest) then
			local units = math.floor(REBEL_UNITS * self:size_scale(sit.instigator) + 0.5)
			if self:beat_unrest(sit, units) then sit.rebels = units end
		end
	end

	self:news(sit, cast)
end

-- At each turn start, by the temperament: more on its ON turns than its OFF ones, and a wild
-- world's at random.
function derpy_director:refill()
	local turn = cm:model():turn_number()
	local b = self:budget() + self:refill_amount(turn)
	local cap = self:budget_cap(turn)
	if b > cap then b = cap end
	log(string.format("refill turn %d: budget %d of %d", turn, b, cap))
	cm:set_saved_value("derpy_director_budget", b)
	return b
end

-- Another mod's global, by name. CA's loader runs every mod file in core:get_env(), so this sees
-- what they declare; _G does not. Read at first tick, when every mod file has loaded.
local function companion(name)
	local t = core:get_env()[name]
	if type(t) == "table" then return t end
	return nil
end

-- A seized convoy, after Resource Overhaul has moved the goods. `region` is where it set out.
function derpy_director:on_seizure(owner_key, captor, region_key, x, y)
	if not ENABLED then return end
	if not (captor and not captor:is_null_interface() and owner_key and region_key) then
		log("dropped: seizure with no captor, owner or region")
		return
	end
	if captor:name() == owner_key then return end
	self:respond({kind = "seizure", instigator = captor:name(), victim = owner_key,
		region = region_key, turn = cm:model():turn_number(), x = x, y = y})
end

-- The wrapped call has already run; its results go back untouched, and a Director fault is
-- logged here rather than raised into Resource Overhaul's turn.
local function after(notify, ...)
	local ok, err = pcall(notify)
	if not ok then log("companion hook errored: " .. tostring(err)) end
	return ...
end

-- Resource Overhaul's two seizure calls. Both return early for a cargo already gone, so whether
-- it was still on the road is read first and only a real seizure is reported. Bandits take
-- cargo by another path and are not a faction's deed.
function derpy_director:hook_seizures(F)
	if F.derpy_director_hooked then return true end
	if type(F.seize) ~= "function" or type(F.convoy_seize) ~= "function"
			or type(F.ship_by_id) ~= "function" or type(F.convoys) ~= "function" then
		log("Resource Overhaul is installed but its seizure calls have moved: not hooked")
		return false
	end
	local seize, convoy_seize = F.seize, F.convoy_seize
	F.seize = function(s, captor)
		local ok, live = pcall(function() return F.ship_by_id(s.id) == s end)
		return after(function()
			if ok and live then self:on_seizure(s.f, captor, s.from, s.x, s.y) end
		end, seize(s, captor))
	end
	F.convoy_seize = function(c, captor)
		local ok, live = pcall(function()
			for _, x in ipairs(F.convoys()) do if x == c then return true end end
			return false
		end)
		return after(function()
			if ok and live then self:on_seizure(c.f, captor, c.from, c.x, c.y) end
		end, convoy_seize(c, captor))
	end
	F.derpy_director_hooked = true
	return true
end

-- A party has seceded from an Iron Court and its rising is done: the rebels hold their provinces
-- and are at war with the realm. The neighbours turn on the realm, so it stands where an aggressor
-- does; the rebels are the victim, and the shield a pact buys covers their settlement.
function derpy_director:on_secession(realm, rebels, provinces)
	if not ENABLED or not (realm and rebels) or realm == rebels then return end
	local f = cm:get_faction(rebels)
	if not f or f:is_null_interface() then return end
	-- A rising never merges: a pool faction or a dead house woken to host it passes the rebel test.
	local risings = cm:get_saved_value("derpy_director_risings")
	if type(risings) ~= "table" then risings = {} end
	risings[rebels] = true
	cm:set_saved_value("derpy_director_risings", risings)
	-- The first by key of the regions they took, not of all they hold: a house rising under its own
	-- banner may own land elsewhere.
	local site
	for _, r in model_pairs(f:region_list()) do
		if provinces[r:province_name()] and (not site or r:name() < site:name()) then site = r end
	end
	if not site then
		log("dropped: the secession from " .. realm .. " left " .. rebels .. " no region")
		return
	end
	local x, y = self:map_point(site)
	self:respond({kind = "secession", instigator = realm, victim = rebels, region = site:name(),
		turn = cm:model():turn_number(), x = x, y = y})
end

-- The Iron Court's secession. IC.secede only starts it: the rising, the hand-over and the war run
-- as timed steps after it returns, and the last step sours the rebels' relations. So the provinces
-- are read as the secession starts, the way IC.secede reads them, and the situation is raised from
-- that last step, once the map has moved.
function derpy_director:hook_court(IC)
	if IC.derpy_director_hooked then return true end
	for _, k in ipairs({"secede", "rebel_sour_all", "defecting_provinces", "move_loyalty",
			"is_human", "runs_court", "loaded", "save"}) do
		if type(IC[k]) ~= "function" then
			log("Iron Court is installed but IC." .. k .. " has moved: not hooked")
			return false
		end
	end
	local secede, sour = IC.secede, IC.rebel_sour_all
	-- Every province a realm's secessions have taken this session, so two parties leaving in one
	-- turn each find theirs whichever rising finishes first. ponytail: never cleared; a rebel
	-- faction a later party joins could be sited on an older rising's land, which is still theirs.
	local taken = {}
	IC.secede = function(faction_key, slug)
		pcall(function()
			taken[faction_key] = taken[faction_key] or {}
			for _, p in ipairs(IC.defecting_provinces(faction_key, slug)) do
				taken[faction_key][p] = true
			end
		end)
		return secede(faction_key, slug)
	end
	IC.rebel_sour_all = function(rebels, faction_key)
		return after(function()
			if taken[faction_key] then self:on_secession(faction_key, rebels, taken[faction_key]) end
		end, sour(rebels, faction_key))
	end
	IC.derpy_director_hooked = true
	self.ic = IC
	return true
end

-- Which of the other derpy mods are installed, and what the Director does with each.
function derpy_director:find_companions()
	local found = {}
	local ro = companion("DERPY_MR_FLOWS")
	if ro and self:hook_seizures(ro) then found[#found + 1] = "Resource Overhaul (seizures)" end
	local gg = companion("GG")
	if gg and type(gg.penalise) == "function" then
		self.guilds = gg
		found[#found + 1] = "Great Guilds (temple)"
	end
	local ic = companion("IC")
	if ic and self:hook_court(ic) then found[#found + 1] = "Iron Court (secessions, loyalty)" end
	-- Named only, for now. EX is a short name, so it is checked for a call of its own.
	local ex = companion("EX")
	if ex and type(ex.dump_state) == "function" then found[#found + 1] = "Zharr Exchange" end
	log("companions: " .. (#found > 0 and table.concat(found, ", ") or "none"))
end

function derpy_director:first_tick()
	if not ENABLED then return end
	self.loaded = true
	-- Re-apply a held threat score once after a load, rather than re-deriving it.
	self.runaway_reapply = true
	-- Read, not refilled: first tick fires on every load, so a refill here paid out per reload.
	log("first tick, watching " .. #WATCHED .. " event(s), budget " .. tostring(self:budget()))
	local s = self:roll_seed()
	log(string.format("temperament %s, phase %d", s.temperament, s.phase or 0))
	self:find_companions()
end

-- Since 9.0 listener callbacks run bare, so one error stops every later callback on that event,
-- CA's included. Everything this file registers goes through here.
local function guarded(what, fn)
	local ok, err = pcall(fn)
	if not ok then log(what .. " errored: " .. tostring(err)) end
end

cm:add_first_tick_callback(function()
	guarded("first tick", function() derpy_director:first_tick() end)
end)

-- Once a turn: WorldStartRound is round-scoped, and first tick fires per load, not per turn.
core:add_listener(
	"derpy_director_refill",
	"WorldStartRound",
	true,
	function()
		if ENABLED then
			guarded("turn start", function()
				derpy_director:refill()
				derpy_director:release_shields()
				derpy_director:adapt_turn()
			end)
			-- Each its own guard: a fault in one must not skip the other every turn after.
			guarded("runaway step", function() derpy_director:runaway_turn() end)
			guarded("opportunity", function() derpy_director:opportunity() end)
			guarded("empires", function() derpy_director:empire_turn() end)
		end
	end,
	true
)

-- Spec 16.2. CA's own siege listener reads context:character() as well as the documented region().
core:add_listener(
	"derpy_director_siege",
	"CharacterBesiegesSettlement",
	true,
	function(context)
		if ENABLED then
			guarded("siege", function() derpy_director:press_siege(context:character(), context:region()) end)
		end
	end,
	true
)

core:add_listener(
	"derpy_director_war",
	"NegativeDiplomaticEvent",
	true,
	function(context)
		if ENABLED then guarded("war", function() derpy_director:note_war(context) end) end
	end,
	true
)

for i = 1, #WATCHED do
	local scenario = WATCHED[i]
	core:add_listener(
		"derpy_director_" .. scenario.event,
		scenario.event,
		true,
		function(context)
			guarded(scenario.event, function() derpy_director:on_event(context, scenario) end)
		end,
		true
	)
end
