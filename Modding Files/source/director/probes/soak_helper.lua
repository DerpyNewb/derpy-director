-- Director long soak helper (2026-11-14). Load through wh3_eval inside a pcall, once per campaign load.
-- The player shield (every battle the player fights is a win, its characters cannot die), turns that
-- end even with a lord unmoved, no generated dilemmas, and a 2 s clicker for what the soak cannot
-- clear: war declarations, AI diplomatic offers, and the Empire's Elector Counts dilemmas.
return (function()
  local said = {}
  local f = loadfile('G:/Modding for resources/tools/wh3_player_shield.lua')
  setfenv(f, getfenv(1))
  said[#said + 1] = tostring(f())
  if not cm.derpy_soak_wrapped then
    local orig = cm.end_turn
    cm.end_turn = function(self, force) return orig(self, true) end
    cm.derpy_soak_wrapped = true
  end
  cm:toggle_dilemma_generation(false)
  said[#said + 1] = "dilemma generation off"
  local root = core:get_ui_root()
  cm:remove_real_callback("derpy_director_soakhelp")
  cm:repeat_real_callback(function()
    pcall(function()
      local w = find_uicomponent(root, "war_declared", "diplomacy_hud_war_declared", "button_ok_war_declared")
      if w and w:Visible(true) then w:SimulateLClick(); out("[soakhelp] war ok") end
      local offers = find_uicomponent(root, "diplomacy_dropdown", "offers_panel")
      if offers and offers:Visible(true) then
        local c = find_uicomponent(offers, "button_set2", "button_cancel")
        if c and c:Visible(true) then c:SimulateLClick(); out("[soakhelp] offer cancel") end
      end
      local dl = find_uicomponent(root, "events", "event_layouts", "dilemma_imperial",
        "dilemma_imperial_authority", "dilemma_list")
      -- The first child can be a hidden template, and a choice the player cannot afford is greyed
      -- out ("inactive"): click the first visible choice that can be clicked.
      if dl and dl:Visible(true) then
        for i = 0, dl:ChildCount() - 1 do
          local b = find_uicomponent(UIComponent(dl:Find(i)), "choice_button")
          if b and b:Visible(true) and b:CurrentState() ~= "inactive" then
            b:SimulateLClick(); out("[soakhelp] imperial dilemma choice " .. (i + 1)); break
          end
        end
      end
    end)
  end, 2000, "derpy_director_soakhelp")
  -- How many factions still hold a region, once a round, for the merge soak.
  core:remove_listener("derpy_soak_holders")
  core:add_listener("derpy_soak_holders", "WorldStartRound", true, function()
    pcall(function()
      local n = 0
      for _, f in model_pairs(cm:model():world():faction_list()) do
        if not f:is_dead() and not f:is_rebel() and f:region_list():num_items() > 0 then n = n + 1 end
      end
      out("[soakhelp] holders turn " .. cm:model():turn_number() .. ": " .. n)
    end)
  end, true)
  said[#said + 1] = "difficulty " .. tostring(cm:get_difficulty(true))
  return table.concat(said, "; ")
end)()
