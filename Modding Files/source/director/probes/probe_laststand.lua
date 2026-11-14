-- Live check 8.2 / 8.3 (2026-11-14): force a last stand and let the Director answer it.
-- Set derpy_probe_sc to the subculture first (default Greenskins) and derpy_probe_go = true to act;
-- without it the probe only names the pair it would use. Load through wh3_eval; everything is in pcall.
return (function()
  local ok, res = pcall(function()
    local SC = derpy_probe_sc or "wh_main_sc_grn_greenskins"
    local w = cm:model():world()
    local function ai(f)
      return f and not f:is_null_interface() and not f:is_dead() and not f:is_rebel() and not f:is_human()
    end
    local pick
    for _, v in model_pairs(w:faction_list()) do
      if not pick and ai(v) and v:subculture() == SC and not v:is_vassal()
          and v:region_list():num_items() >= 2 then
        for _, k in model_pairs(v:factions_met()) do
          if ai(k) and k:subculture() == SC and not k:is_vassal() and not k:at_war_with(v)
              and k:region_list():num_items() > v:region_list():num_items() then
            pick = {v = v, k = k}
            break
          end
        end
      end
    end
    if not pick then return "no pair for " .. SC end
    local x
    for _, f in model_pairs(w:faction_list()) do
      if ai(f) and f:subculture() ~= SC and f:region_list():num_items() > 0 then x = f break end
    end
    if not x then return "no taker" end
    local v = pick.v
    local desc = string.format("victim %s (%d regions), kin %s (%d), taker %s, turn %d",
      v:name(), v:region_list():num_items(), pick.k:name(), pick.k:region_list():num_items(),
      x:name(), cm:model():turn_number())
    if not derpy_probe_go then return "would use: " .. desc end
    local keys = {}
    for _, r in model_pairs(v:region_list()) do keys[#keys + 1] = r:name() end
    for i = 2, #keys do cm:transfer_region_to_faction(keys[i], x:name()) end
    local last = cm:get_region(keys[1])
    local px, py = derpy_director:map_point(last)
    derpy_director:respond{kind = "conquest", instigator = x:name(), victim = v:name(),
      region = keys[1], turn = cm:model():turn_number(), x = px, y = py}
    return "raised: " .. desc .. ", left " .. keys[1]
  end)
  return tostring(ok) .. ": " .. tostring(res)
end)()
