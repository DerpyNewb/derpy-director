-- Player shield for live tests and soaks (author's rule, 2026-10-30): every battle a human faction fights is
-- autoresolved as a win with no losses on its side, and its characters cannot die. Use it for any test that
-- does not need the player to lose. Load it once per campaign load through wh3_eval, inside a pcall:
--   local f = loadfile('G:/Modding for resources/tools/wh3_player_shield.lua'); setfenv(f, getfenv(1)); return f()
-- WH3_SHIELD.n counts the battles it set; WH3_SHIELD.off() removes it.
-- Set from inside PendingBattle only, before it is fought: the bridge warns that win_next_autoresolve_battle with
-- no battle pending is an instant crash. A battle between two computer factions is left alone. Do not combine
-- with the soak's rig_battles, which sets the next autoresolve too.
return (function()
local ok, err = pcall(function()
WH3_SHIELD = WH3_SHIELD or {}
local S = WH3_SHIELD
S.n = S.n or 0
local function human(f) return f and not f:is_null_interface() and f:is_human() and f:name() or nil end
-- the human faction key on each side, or nil
function S.side()
    local pb = cm:model():pending_battle()
    local att = pb:has_attacker() and human(pb:attacker():faction())
    local def = (pb:has_defender() and human(pb:defender():faction()))
        or (pb:has_contested_garrison() and human(pb:contested_garrison():faction()))
    return att, def
end
function S.immortal()
    for _, k in ipairs(cm:get_human_factions()) do
        local cl = cm:get_faction(k):character_list()
        for i = 0, cl:num_items() - 1 do
            local c = cl:item_at(i)
            pcall(function() cm:set_character_immortality(cm:char_lookup_str(c), true) end)
        end
    end
end
core:remove_listener('wh3_shield_battle')
core:add_listener('wh3_shield_battle', 'PendingBattle', true, function()
    pcall(function()
        if cm:model():pending_battle():has_been_fought() then return end
        local att, def = S.side()
        -- CA's own pairing (episode_chaos_invasion.lua): win_next_autoresolve_battle picks the winner, and
        -- modify_next_autoresolve_battle alone does not (measured 2026-10-30: a shielded player still lost).
        -- Then win chances as unary values, and the attacker's and the defender's loss multipliers.
        if att and not def then
            cm:win_next_autoresolve_battle(att); cm:modify_next_autoresolve_battle(1, 0, 0, 1, false); S.n = S.n + 1
        elseif def and not att then
            cm:win_next_autoresolve_battle(def); cm:modify_next_autoresolve_battle(0, 1, 1, 0, false); S.n = S.n + 1
        end
    end)
end, true)
-- characters recruited later are covered at the next human turn start
core:remove_listener('wh3_shield_turn')
core:add_listener('wh3_shield_turn', 'FactionTurnStart', function(c) return c:faction():is_human() end,
    function() pcall(S.immortal) end, true)
S.immortal()
function S.off()
    core:remove_listener('wh3_shield_battle')
    core:remove_listener('wh3_shield_turn')
end
end)
return ok and 'player shield on' or ('player shield failed: ' .. tostring(err))
end)()
