-- Task 1 gate (2026-11-14): does cai_evaluate_quick_deal_action's ok flag honour CA's confederation
-- locks? Load through wh3_eval: loadfile + setfenv inside a pcall. MODE is "probe" or "merge".
local MODE = ...
local DEAL = "diplomatic_option_confederation"
local SUBS = {"wh_main_sc_vmp_vampire_counts", "wh_main_sc_grn_greenskins", "wh_main_sc_dwf_dwarfs",
              "wh3_dlc23_sc_chd_chaos_dwarfs"}

local function members(sc)
  local l = {}
  for _, f in model_pairs(cm:model():world():faction_list()) do
    if not f:is_null_interface() and not f:is_dead() and not f:is_human() and not f:is_rebel()
        and f:subculture() == sc and f:region_list():num_items() > 0 then
      l[#l + 1] = f
    end
  end
  table.sort(l, function(a, b) return a:name() < b:name() end)
  return l
end

local function met(a, b)
  for _, m in model_pairs(a:factions_met()) do
    if m:name() == b:name() then return true end
  end
  return false
end

local function first_pair(sc, skip)
  local l = members(sc)
  for i = 1, #l do
    for j = i + 1, #l do
      local a, b = l[i], l[j]
      if not (skip and (skip[a:name()] or skip[b:name()])) and met(a, b) and not a:at_war_with(b) then
        return a, b
      end
    end
  end
end

local function ask(a, b)
  local s1, o1 = cm:cai_evaluate_quick_deal_action(a, b, DEAL)
  local s2, o2 = cm:cai_evaluate_quick_deal_action(b, a, DEAL)
  return string.format("%s %s %s/%s ok=%s/%s", a:name(), b:name(), tostring(s1), tostring(s2),
    tostring(o1), tostring(o2))
end

local said = {"turn " .. cm:model():turn_number()}
if MODE == "probe" then
  for _, sc in ipairs(SUBS) do
    local a, b = first_pair(sc)
    said[#said + 1] = sc .. ": " .. (a and ask(a, b) or "no met pair at peace")
  end
elseif MODE == "merge" then
  local a, b = first_pair("wh_main_sc_grn_greenskins")
  if not a then return "no greenskin pair" end
  if b:region_list():num_items() > a:region_list():num_items() then a, b = b, a end
  said[#said + 1] = "before: " .. ask(a, b)
  local p = cm:create_payload()
  local formed = p:form_confederation(a, b, false, false)
  if formed then cm:apply_payload(p, a) end
  said[#said + 1] = string.format("payload %s absorbs %s: form=%s, %s dead=%s", a:name(), b:name(),
    tostring(formed), b:name(), tostring(cm:get_faction(b:name()):is_dead()))
  -- The absorber against the next met Greenskin, both ways.
  for _, c in ipairs(members("wh_main_sc_grn_greenskins")) do
    if c:name() ~= a:name() and c:name() ~= b:name() and met(a, c) and not a:at_war_with(c) then
      said[#said + 1] = "after: " .. ask(a, c)
      break
    end
  end
end
return table.concat(said, " | ")
