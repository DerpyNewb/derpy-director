-- THE DIRECTOR'S CHRONICLE (2026-11-15): the panel that lists what the Director did this campaign,
-- newest first, under a header naming the temperament, the old hatred and the ambitious factions.
-- Design: docs/superpowers/specs/2026-11-15-director-chronicle-design.md.
--
-- UI-ONLY AND LOCAL. It reads two saved values derpy_director.lua writes (derpy_director_chronicle
-- and derpy_director_seed) and writes nothing to the model or the save, so it cannot desync
-- multiplayer. The chronicle holds keys and numbers only: every name and sentence is looked up
-- here, from a click, because a loc call from a turn handler crashes the game at turn 1.
--
-- THE FILES are tools/gen_director_ui.py's, and DC.STYLE must equal its STYLE (its --selftest
-- compares them). A runtime-created component ignores dockpoint, so DC.LAYOUT places every part.
-- TWUI TEXT NEVER WRAPS: an entry is broken into lines here with TextDimensionsForText, and every
-- line is its own derpy_director_line row in the list box.

DC = DC or {}

DC.PANEL = "derpy_director_panel"
DC.PANEL_FILE = "ui/campaign ui/derpy_director_panel"
DC.LIST = "derpy_director_list"
DC.LIST_FILE = "ui/campaign ui/derpy_director_list"
DC.LINE = "derpy_director_line"
DC.LINE_FILE = "ui/campaign ui/derpy_director_line"
DC.RULE = "derpy_director_rule"
DC.RULE_FILE = "ui/campaign ui/derpy_director_rule"
DC.PROBE = "derpy_director_probe"
DC.BUTTON = "derpy_director_button"
DC.BUTTON_FILE = "ui/campaign ui/derpy_director_button"
DC.HUB_KEY = "dr"

DC.STYLE = {
	panel_w = 640,
	panel_h = 730,
	list_x = 20,
	list_y = 218,
	list_rows = 25,
	line_w = 576,
	line_h = 20,
	rule_h = 17,
	indent = 18,
	inset = 6,
	value_w = 430,
	handle_h = 40,
	text = "#FFF8D7FF",
	muted = "ui_font_faded_grey_beige",
	title_font = "header_24_bold",
	label_font = "header_14",
	body_font = "body_12",
	accent = "yellow",
}

-- Panel-relative positions. The header is three rows of a label and its value lines; row r starts
-- below row r-1's lines and a gap. The list sits at STYLE.list_x / list_y.
DC.LAYOUT = {
	title_text = {28, 18},
	close_button = {594, 16},
	header_y = 64,
	label_x = 28,
	value_x = 182,
	divider = {20, 208},
}
DC.HEADER_LINES = {4, 1, 2}
DC.HEADER_LINE_H = 18
DC.HEADER_GAP = 6
-- The gap between two entries of one turn: an empty row this tall. Two turns are parted by a
-- rule row (STYLE.rule_h) instead.
DC.GAP_H = 8
-- CA's slider: its end parts are MoveTo'd from the track (gen_guilds_ui.CA_SLIDER).
DC.SLIDER_PARTS = {{"frame_top", -1, -24}, {"frame_bottom", -1, 0}, {"top", 1, -23}, {"bottom", 1, -1}}
DC.SLIDER_CAP = 24
DC.BUTTON_SIZE = 48
DC.BUTTON_GAP = 4
DC.PLACE_TRIES = 150
DC.FOLLOW_MS = 300

-- THE LOC. Every name below is a row of gen_director_ui.CHRONICLE_LOC, under this prefix; its
-- check fails on a name used here with no row, and on a row nothing here uses.
DC.LOC_PREFIX = "derpy_director_chronicle_"
DC.DEED = {
	sack = "deed_sack", raze = "deed_raze", conquest = "deed_conquest",
	confederation = "deed_confederation", treachery = "deed_treachery",
	opportunism = "deed_opportunism", seizure = "deed_seizure", secession = "deed_secession",
}
DC.RISE = {"rise_1", "rise_2", "rise_3"}
DC.MERGE = {last_stand = "merge_last_stand", runaway = "merge_runaway"}
-- A war, by the cause the model found for it: a story's kind, or the feared power.
DC.WAR = {
	sack = "war_sack", raze = "war_raze", conquest = "war_conquest",
	confederation = "war_confederation", treachery = "war_treachery",
	opportunism = "war_opportunism", seizure = "war_seizure", secession = "war_secession",
	runaway = "war_runaway",
}

local function log(msg) out("[director] chronicle: " .. tostring(msg)) end

local function comp(name, parent)
	local ok, c = pcall(function() return find_uicomponent(parent or core:get_ui_root(), name) end)
	if ok and is_uicomponent(c) then return c end
	return nil
end

local function set_text(c, text)
	if c then pcall(function() c:SetText(text, "") end) end
end

-- A loc string, or "" when the key has none. common.get_localised_string answers "" for a missing
-- key in the cases measured; the key itself is treated the same, in case a build answers that.
function DC.lookup(key)
	local ok, s = pcall(function() return common.get_localised_string(key) end)
	if not ok or type(s) ~= "string" or s == key then return "" end
	return s
end

function DC.loc(name) return DC.lookup(DC.LOC_PREFIX .. name) end

-- Names in the player's language. A faction's name resolves by key whether or not it still lives,
-- which is what an entry about a faction since destroyed needs. A key with no loc reads as itself.
function DC.faction(key)
	if not key then return "" end
	local s = DC.lookup("factions_screen_name_" .. key)
	return s ~= "" and s or key
end

function DC.region(key)
	if not key or key == "" then return "" end
	local s = DC.lookup("regions_onscreen_" .. key)
	return s ~= "" and s or key
end

function DC.culture(key)
	local s = DC.lookup("cultures_subcultures_name_" .. tostring(key))
	return s ~= "" and s or tostring(key)
end

-- {i} in a template becomes vals.i. A function replacement, so a name holding % is taken as is.
function DC.fill(template, vals)
	return (string.gsub(template, "{(%w+)}", function(k) return vals[k] or "" end))
end

-- "A", "A and B", "A, B and C".
function DC.join(names)
	if #names == 0 then return "" end
	if #names == 1 then return names[1] end
	local head = {}
	for i = 1, #names - 1 do head[i] = names[i] end
	return DC.fill(DC.loc("list_two"), {a = table.concat(head, ", "), b = names[#names]})
end

-- AN ENTRY AS A PARAGRAPH, or nil for a kind this file does not know (a newer model's entry in an
-- older UI is skipped, not drawn as a blank).
function DC.sentence(e)
	if type(e) ~= "table" then return nil end
	local I, V, R = DC.faction(e.i), DC.faction(e.v), DC.region(e.r)
	local parts = {}
	-- "Waaagh!." reads as a typo: a name that ends in its own mark takes no full stop after it.
	local function add(name, vals)
		parts[#parts + 1] = (string.gsub(DC.fill(DC.loc(name), vals), "([!?])%.", "%1"))
	end
	if e.k == "runaway_rise" then
		add(DC.RISE[e.n] or DC.RISE[1], {i = I})
	elseif e.k == "runaway_end" then
		add("runaway_end", {i = I})
	elseif e.k == "war" then
		if not DC.WAR[e.w] then return nil end
		add(DC.WAR[e.w], {i = I, v = V, r = R, x = DC.faction(e.x)})
	elseif e.k == "runaway_pact" then
		for _, p in ipairs(e.p or {}) do add("runaway_pact", {a = DC.faction(p[1]), b = DC.faction(p[2]), i = I}) end
	elseif DC.DEED[e.k] then
		add(DC.DEED[e.k], {i = I, v = V, r = R})
		if e.c and #e.c > 0 then
			local names = {}
			for n, k in ipairs(e.c) do names[n] = DC.faction(k) end
			add("answered", {list = DC.join(names), i = I})
		end
		-- A pact the Director funded carries each side's gold as its third field.
		for _, p in ipairs(e.p or {}) do
			local vals = {a = DC.faction(p[1]), b = DC.faction(p[2]), i = I, n = tostring(p[3])}
			if p[3] then add("pact_chest", vals) else add("pact", vals) end
		end
		if e.g then add("grudge", {g = DC.faction(e.g), i = I}) end
		if e.u then add("rebels", {r = R}) end
		if e.pl then add("plague", {r = R}) end
		if type(e.m) == "table" then
			add(DC.MERGE[e.m[3]] or DC.MERGE.last_stand, {a = DC.faction(e.m[1]), b = DC.faction(e.m[2]), i = I})
		end
	else
		return nil
	end
	if #parts == 0 then return nil end
	return table.concat(parts, " ")
end

-- A turn's heading, in the accent colour, over the entries of that turn.
function DC.turn_label(t)
	return "[[col:" .. DC.STYLE.accent .. "]]" .. DC.fill(DC.loc("turn"), {t = tostring(t or "")})
		.. "[[/col]]"
end

-- Markup costs no width: [[col:]] is a colour, not glyphs.
local function bare(s) return (string.gsub(s, "%[%[/?col[^%]]*%]%]", "")) end

-- Words into lines no wider than first_w (the first line) and rest_w (the rest), measured by
-- measure(s) -> pixels. A word wider than a line gets a line of its own and is clipped there.
function DC.wrap(text, first_w, rest_w, measure)
	local lines, cur = {}, nil
	for word in string.gmatch(text, "%S+") do
		local try = cur and (cur .. " " .. word) or word
		local need = measure(bare(try))
		local budget = (#lines == 0) and first_w or rest_w
		if need and need > budget and cur then
			lines[#lines + 1] = cur
			cur = word
		else
			cur = try
		end
	end
	if cur then lines[#lines + 1] = cur end
	return lines
end

function DC.panel() return comp(DC.PANEL) end

function DC.is_open()
	local p = DC.panel()
	return p ~= nil and p:Visible()
end

-- Created once and kept: closing hides it. The list inside is rebuilt on every open.
function DC.build_panel()
	local p = DC.panel()
	if p then return p end
	local root = core:get_ui_root()
	pcall(function() root:CreateComponent(DC.PANEL, DC.PANEL_FILE) end)
	p = DC.panel()
	if not p then
		log("could not create the panel from " .. DC.PANEL_FILE)
		return nil
	end
	-- The measuring line: the same file, font and size as every row, never shown.
	pcall(function() p:CreateComponent(DC.PROBE, DC.LINE_FILE) end)
	local probe = comp(DC.PROBE, p)
	if probe then probe:SetVisible(false) end
	return p
end

-- Every part, from the panel's top-left. Centred on the screen each open, so a resolution change
-- heals on the next one.
function DC.layout(p)
	local sw, sh = core:get_screen_resolution()
	local pw, ph = p:Dimensions()
	p:MoveTo(math.floor((sw - pw) / 2), math.floor((sh - ph) / 2))
	local px, py = p:Position()
	local L = DC.LAYOUT
	for _, name in ipairs({"title_text", "close_button", "divider"}) do
		local c = comp(name, p)
		if c then c:MoveTo(px + L[name][1], py + L[name][2]) end
	end
	local y = L.header_y
	for r, n in ipairs(DC.HEADER_LINES) do
		local lab = comp("hdr_label_" .. r, p)
		if lab then lab:MoveTo(px + L.label_x, py + y) end
		for line = 1, n do
			local c = comp("hdr_text_" .. r .. "_" .. line, p)
			if c then c:MoveTo(px + L.value_x, py + y + (line - 1) * DC.HEADER_LINE_H) end
		end
		y = y + n * DC.HEADER_LINE_H + DC.HEADER_GAP
	end
end

local function measurer(p)
	local probe = comp(DC.PROBE, p)
	return function(s)
		if not probe then return nil end
		local ok, w = pcall(function() return probe:TextDimensionsForText(s) end)
		if ok and type(w) == "number" then return w end
		return nil
	end
end

-- A line cut short: " ..." on the end, words dropped until it fits WITH it on. No measure (no probe
-- yet) keeps every word.
function DC.ellipsize(text, w, measure)
	local words = {}
	for word in string.gmatch(text, "%S+") do words[#words + 1] = word end
	while #words > 1 do
		local need = measure(bare(table.concat(words, " ") .. " ..."))
		if not need or need <= w then break end
		words[#words] = nil
	end
	return table.concat(words, " ") .. " ..."
end

-- The header: what kind of world this is, the old hatred, the ambitious. From the seed the model
-- rolled at the first tick; a campaign that has none yet reads as "not yet known".
function DC.draw_header(p)
	local S, seed = DC.STYLE, cm:get_saved_value("derpy_director_seed")
	if type(seed) ~= "table" then seed = {} end
	set_text(comp("title_text", p), DC.loc("title"))
	local measure = measurer(p)
	local w = S.value_w - S.inset
	local rows = {}
	local stem = "event_feed_strings_text_derpy_director_feed_temper_" .. tostring(seed.temperament)
	local name = DC.lookup(stem .. "_title")
	rows[1] = {DC.loc("label_temper"), name ~= "" and name or DC.loc("unknown")}
	local said = DC.lookup(stem .. "_primary")
	for _, l in ipairs(DC.wrap(said, w, w, measure)) do rows[1][#rows[1] + 1] = l end
	local hot = type(seed.hot) == "table" and seed.hot or {}
	rows[2] = {DC.loc("label_hatred"), #hot == 2
		and DC.fill(DC.loc("list_two"), {a = DC.culture(hot[1]), b = DC.culture(hot[2])})
		or DC.loc("none")}
	local names = {}
	for n, k in ipairs(type(seed.ambitious) == "table" and seed.ambitious or {}) do names[n] = DC.faction(k) end
	rows[3] = {DC.loc("label_ambitious")}
	for _, l in ipairs(#names > 0 and DC.wrap(DC.join(names), w, w, measure) or {DC.loc("none")}) do
		rows[3][#rows[3] + 1] = l
	end
	for r, n in ipairs(DC.HEADER_LINES) do
		set_text(comp("hdr_label_" .. r, p), rows[r][1])
		for line = 1, n do
			local c = comp("hdr_text_" .. r .. "_" .. line, p)
			local text = rows[r][line + 1]
			-- A value longer than its slots ends in an ellipsis rather than mid-thought.
			if line == n and rows[r][n + 2] then text = DC.ellipsize(text, w, measure) end
			-- What the temperament means, under its name, in CA's faded font colour: the game
			-- ignores the cell's own font_m_colour, and markup is the route that draws.
			if text and r == 1 and line > 1 then
				text = "[[col:" .. S.muted .. "]]" .. text .. "[[/col]]"
			end
			set_text(c, text or "")
			if c then c:SetVisible(text ~= nil) end
		end
	end
end

-- The chronicle as rows, newest first and grouped by turn: a turn's heading, then its entries with
-- a gap between two, and a rule above every heading but the first. A row is {kind, text, cont}:
-- kind is "turn", "line", "gap" or "rule", and cont marks an entry's second line onwards.
function DC.lines(p)
	local S = DC.STYLE
	local measure = measurer(p)
	local first = S.line_w - S.inset
	local rest = first - S.indent
	local buf = cm:get_saved_value("derpy_director_chronicle")
	local out, turn = {}, nil
	if type(buf) == "table" then
		for i = #buf, 1, -1 do
			local e = buf[i]
			local text = DC.sentence(e)
			if text then
				if e.t ~= turn then
					if #out > 0 then out[#out + 1] = {kind = "rule"} end
					out[#out + 1] = {kind = "turn", text = DC.turn_label(e.t)}
					turn = e.t
				else
					out[#out + 1] = {kind = "gap"}
				end
				for n, l in ipairs(DC.wrap(text, first, rest, measure)) do
					out[#out + 1] = {kind = "line", text = l, cont = n > 1}
				end
			end
		end
	end
	if #out == 0 then out[1] = {kind = "line", text = DC.loc("empty")} end
	return out
end

-- THE LIST, destroyed and created again on every open, so it opens at the top. Its parts are
-- MoveTo'd; list_box and handle never are, because the List and VSlider callbacks own them.
function DC.draw_list(p)
	local S = DC.STYLE
	local old = comp(DC.LIST, p)
	if old then pcall(function() old:Destroy() end) end
	pcall(function() p:CreateComponent(DC.LIST, DC.LIST_FILE) end)
	local list = comp(DC.LIST, p)
	if not list then
		log("could not create the list from " .. DC.LIST_FILE)
		return 0
	end
	local px, py = p:Position()
	local lx, ly = px + S.list_x, py + S.list_y
	list:MoveTo(lx, ly)
	local clip = comp("list_clip", list)
	if clip then clip:MoveTo(lx, ly) end
	local vs = comp("vslider", list)
	if vs then
		vs:MoveTo(lx + S.line_w + 6, ly + DC.SLIDER_CAP)
		pcall(function()
			local sx, sy = vs:Position()
			local _, th = vs:Dimensions()
			for _, part in ipairs(DC.SLIDER_PARTS) do
				local c = comp(part[1], vs)
				local base = (part[1] == "frame_bottom" or part[1] == "bottom") and sy + th or sy
				if c then c:MoveTo(sx + part[2], base + part[3]) end
			end
		end)
	end
	local box = clip and comp("list_box", clip)
	if not box then return 0 end
	local lines = DC.lines(p)
	local rows_px = 0
	for i, l in ipairs(lines) do
		local rule = l.kind == "rule"
		local name = (rule and DC.RULE or DC.LINE) .. "_" .. i
		pcall(function() box:CreateComponent(name, rule and DC.RULE_FILE or DC.LINE_FILE) end)
		local row = comp(name, box)
		if row then
			if rule then
				rows_px = rows_px + S.rule_h
			elseif l.kind == "gap" then
				set_text(row, "")
				pcall(function() row:Resize(S.line_w, DC.GAP_H) end)
				rows_px = rows_px + DC.GAP_H
			else
				set_text(row, l.text)
				if l.cont then pcall(function() row:SetTextXOffset(S.inset + S.indent, 0) end) end
				rows_px = rows_px + S.line_h
			end
		end
	end
	-- Without it the rows sit stacked at the box's origin until something else lays it out.
	pcall(function() box:Layout() end)
	-- Nothing below the fold: no slider to drag.
	if vs then vs:SetVisible(rows_px > S.list_rows * S.line_h) end
	return #lines
end

-- Open or close. Interactive follows visible, in this one place: a hidden panel that still eats
-- the mouse is a dead zone in the middle of the map (docs/CUSTOM_UI.md).
function DC.show(visible)
	local p = visible and DC.build_panel() or DC.panel()
	if not p then return end
	if visible then
		DC.layout(p)
		DC.draw_header(p)
		DC.draw_list(p)
	end
	p:SetVisible(visible)
	p:SetInteractive(visible)
end

-- THE OPENER, on the right end of the top resource strip, as the Zharr Exchange places its own
-- (zzz_derpy_chd_exchange.lua EX.place_button: the strip is a ruler, never a parent; it slides
-- away for the intro and end turn, so a read off the screen is retried, never trusted).
function DC.hubbed()
	return DERPY_HUB ~= nil and DERPY_HUB.manages ~= nil and DERPY_HUB.manages(DC.HUB_KEY) == true
end

function DC.anchor()
	local root = core:get_ui_root()
	local bar = find_uicomponent(root, "resources_bar")
	if is_uicomponent(bar) then
		local bx, by = bar:Position()
		local bw, bh = bar:Dimensions()
		return bx + bw + DC.BUTTON_GAP, by + math.floor((bh - DC.BUTTON_SIZE) / 2), "resources_bar"
	end
	local docker = find_uicomponent(root, "faction_buttons_docker")
	if is_uicomponent(docker) then
		local dx, dy = docker:Position()
		local _, dh = docker:Dimensions()
		return dx - DC.BUTTON_SIZE - DC.BUTTON_GAP, dy + math.floor((dh - DC.BUTTON_SIZE) / 2),
			"faction_buttons_docker"
	end
	return nil
end

function DC.fit(x, y)
	local sw, sh = core:get_screen_resolution()
	local t = DC.BUTTON_SIZE
	if not x or x < -t or y < -t or x + t > sw + t or y + t > sh + t then return nil end
	return math.max(0, math.min(x, sw - t)), math.max(0, math.min(y, sh - t))
end

function DC.place_button(attempt)
	local root = core:get_ui_root()
	local b = comp(DC.BUTTON)
	local function retry()
		if DC.button_at or attempt >= DC.PLACE_TRIES then return end
		-- The real timer: whether this retries depends on this machine's screen, and a model timer
		-- started on one multiplayer machine and not the other is a desync.
		cm:real_callback(function() DC.place_button(attempt + 1) end, 2000, "derpy_director_button_" .. attempt)
	end
	if not b then
		pcall(function() root:CreateComponent(DC.BUTTON, DC.BUTTON_FILE) end)
		b = comp(DC.BUTTON)
	end
	if not b then return retry() end
	if DC.hubbed() then return end
	local x, y = DC.fit(DC.anchor())
	if not x then return retry() end
	b:MoveTo(x, y)
	b:SetVisible(true)
	DC.button_at = x .. "," .. y
end

-- The strip's right end moves when an icon appears on it, with no event: follow it.
function DC.follow()
	if not DC.button_at or DC.hubbed() then return end
	local b = comp(DC.BUTTON)
	local x, y, anchor = DC.anchor()
	if not b or anchor ~= "resources_bar" then return end
	x, y = DC.fit(x, y)
	if not x then return end
	local ax, ay = b:Position()
	if ax ~= x or ay ~= y then b:MoveTo(x, y) end
end

-- THE HUB'S REGISTRATION (tools/sync_derpy_hub.py). A plain table, so load order against the hub
-- copies does not matter.
DERPY_HUB_QUEUE = DERPY_HUB_QUEUE or {}
table.insert(DERPY_HUB_QUEUE, {
	key = DC.HUB_KEY, button = DC.BUTTON, order = 5,
	label = function() return DC.loc("title") end,
	live = function() return true end,
})

-- The click on the opener, and on the close button OF THIS PANEL: "close_button" is a name CA
-- uses on many panels, so its parent is checked.
function DC.click(context)
	local s = context.string
	if s == DC.BUTTON then
		DC.show(not DC.is_open())
	elseif s == "close_button" then
		local ok, id = pcall(function() return UIComponent(UIComponent(context.component):Parent()):Id() end)
		if ok and id == DC.PANEL then DC.show(false) end
	end
end

-- Since 9.0 lib_core calls listeners unprotected and tests every condition before any callback,
-- so one mod's throwing condition drops the whole click. This lifts the listener into the
-- engine's own events.ComponentLClickUp list, ahead of core's dispatcher, as EX.click_first does
-- (zzz_derpy_chd_exchange.lua).
function DC.click_first(name)
	pcall(function()
		local list = core.event_listeners.ComponentLClickUp
		for i = #list, 1, -1 do
			local l = list[i]
			if l.name == name then
				table.insert(events.ComponentLClickUp, 1, function(context)
					pcall(function()
						if l.condition == true or l.condition(context) then l.callback(context) end
					end)
				end)
				table.remove(list, i)
				return
			end
		end
	end)
end

function DC.init()
	if DC.started then return end
	DC.started = true
	core:add_listener("derpy_director_chronicle_click", "ComponentLClickUp",
		function(context) return context.string == DC.BUTTON or context.string == "close_button" end,
		function(context)
			local ok, err = pcall(DC.click, context)
			if not ok then log("click failed: " .. tostring(err)) end
		end, true)
	DC.click_first("derpy_director_chronicle_click")
	DC.place_button(1)
	cm:repeat_real_callback(function() pcall(DC.follow) end, DC.FOLLOW_MS, "derpy_director_follow")
end

cm:add_first_tick_callback(function()
	local ok, err = pcall(DC.init)
	if not ok then log("init failed: " .. tostring(err)) end
end)
