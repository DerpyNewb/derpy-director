"""Mirror the Director into repos/derpy-director, the public repo.

The workspace is the source of truth; the repo is a copy with the same layout, so every tool's relative paths
("Modding Files/...", "tools/...") work from either root. README.md, CHANGELOG.md, LICENSE, .gitignore and
.gitattributes are written in the repo itself and never touched here. The copying is sync_guilds_repo's.

    py tools/sync_director_repo.py            # copy every changed file into the repo
    py tools/sync_director_repo.py --check    # list drift, copy nothing; exit 1 on drift
    py tools/sync_director_repo.py --selftest

Then commit and push from inside the repo folder.

Published: the campaign script, its generated lore table and MCT page, the event-feed rows, the builder with its Lua
harness and the mutation runner, their import closure (the offline vanilla readers, the RPFM client, the Lua checks),
the live-game probes and the player shield they load, the design specs and plans (the Coalition Supervisor's included,
since the Director absorbed it), the session handoffs as docs/history/, and the campaign-AI and diplomacy references.

NOTHING OF CA'S OR GW'S IS PUBLISHED: no .pack, no .loc, no game art, and nothing under Modding Files/reference/,
where CA's scripting docs and shipped scripts live. The builder reads CA's tables from the player's own install, and
the self-test skips the two checks that need CA's files when they are absent. Nor is any file naming a Windows user
profile. `refused()` checks every manifest entry, by path, extension and content, and the sync will not run while it
reports anything.
"""
import os
import re
import sys

import sync_guilds_repo as SG

ROOT = SG.ROOT
REPO = os.path.join(ROOT, "repos", "derpy-director")

PACKED = [
    "Modding Files/pack/script/campaign/mod/derpy_director.lua",
    "Modding Files/pack/script/campaign/mod/derpy_director_lore.lua",
    "Modding Files/pack/script/mct/settings/derpy_director.lua",
]
SOURCES = ["Modding Files/source/director_feed", "Modding Files/source/director"]
TOOLS = [
    # the builder (generator, Lua harness, packer) and the mutation runner
    "build_director.py", "mutate_director.py",
    # the import closure: reading CA's tables from your own install, and RPFM for the pack
    "read_vanilla_db.py", "read_vanilla_loc.py", "read_vanilla_cache.py", "read_pack_index.py",
    "fetch_vanilla_tables.py", "check_skill_trees.py", "rpfm_client.py", "rpfm_mcp_bridge.py",
    # the Lua checks the self-test runs, and the game-compiler check
    "check_lua_api.py", "check_lua_undeclared.py", "check_lua_literal_left.py",
    # the player shield the soak helper loads
    "wh3_player_shield.lua",
    # this file and its copier
    "sync_guilds_repo.py", "sync_director_repo.py",
]
DESIGN = [
    "specs/2026-09-13-ai-coalition-supervisor-design.md", "plans/2026-09-13-ai-coalition-supervisor.md",
    "specs/2026-09-16-ai-director-design.md", "plans/2026-09-16-ai-director-phase1.md",
    "specs/2026-11-14-director-merges-coalitions-design.md", "plans/2026-11-14-director-merges-coalitions.md",
]
HISTORY = ["HANDOFF_20260913_AI_GAPS_AND_COALITIONS.md", "HANDOFF_20260913_AI_COALITION_SUPERVISOR_BUILT.md",
           "HANDOFF_20260916_COALITION_SOAK_AND_AI_DIRECTOR_RESEARCH.md",
           "HANDOFF_20260922_LISTENER_CHAIN_FIX_AND_DIRECTOR_REBELLIONS.md",
           "HANDOFF_20260925_DIRECTOR_9_0_NAGASH.md"]
REFERENCE = ["CAMPAIGN_AI.md", "DIPLOMACY.md"]

REFUSED_EXT = (".png", ".gif", ".mp4", ".dds", ".jpg", ".jpeg", ".webp", ".tga", ".pack", ".bin", ".loc", ".anim",
               ".wem", ".twui.xml", ".xlsx", ".json", ".npz", ".txt", ".html")
PRIVATE = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s]+", re.I)
DECOMPILED = re.compile(r"^```c\s*$", re.M)


def _walk(rel, exts):
    out = []
    for dp, dns, fns in os.walk(os.path.join(ROOT, rel)):
        dns[:] = sorted(d for d in dns if d != "__pycache__")
        for fn in sorted(fns):
            if fn.endswith(exts):
                out.append(os.path.relpath(os.path.join(dp, fn), ROOT).replace("\\", "/"))
    return out


def manifest():
    out = [(p, p) for p in PACKED]
    for rel in SOURCES:
        out += [(p, p) for p in _walk(rel, (".tsv", ".lua", ".py"))]
    out += [("tools/" + n, "tools/" + n) for n in TOOLS]
    out += [("docs/superpowers/" + n, "docs/superpowers/" + n) for n in DESIGN]
    out += [("docs/sessions/" + n, "docs/history/" + n) for n in HISTORY]
    out += [("docs/" + n, "docs/" + n) for n in REFERENCE]
    return out


def refused(m, root=ROOT):
    """Every manifest entry that must never be published, with why."""
    bad = []
    for src, _dst in m:
        if src.startswith("Modding Files/reference/") or src.lower().endswith(REFUSED_EXT):
            bad.append((src, "CA's file or docs, game art, a game binary or a data dump"))
            continue
        p = os.path.join(root, src)
        if os.path.isfile(p):
            with open(p, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            hit = PRIVATE.search(text)
            if hit:
                bad.append((src, "names a user profile: %s" % hit.group(0)))
            elif DECOMPILED.search(text):
                bad.append((src, "holds a C block: decompiled exe code is never published"))
    return bad


def _selftest():
    import tempfile
    m = manifest()
    assert not refused(m), refused(m)
    if os.path.isdir(os.path.join(ROOT, "docs", "sessions")):  # the workspace, not a clone of the repo
        missing = [s for s, _d in m if not os.path.isfile(os.path.join(ROOT, s))]
        assert not missing, "manifest names files that do not exist: %s" % missing
    assert len({d for _s, d in m}) == len(m), "two entries land on one repo path"
    srcs = {s for s, _d in m}
    for must in PACKED + ["tools/build_director.py", "tools/mutate_director.py",
                          "Modding Files/source/director_feed/loc__derpy_director_feed.tsv"]:
        assert must in srcs, "%s is not published" % must
    for probe in ("Modding Files/Modpacks/derpy_director.pack", "Modding Files/pack/text/db/derpy_director_feed.loc",
                  "Modding Files/reference/ca_script_docs_wh3/campaign/episodic_scripting.html",
                  "Modding Files/reference/ca_scripts_wh3/campaign/main_warhammer/crisis/crisis_waaagh.lua",
                  ".skilltree_cache/campaign_cultural_relations.json"):
        assert refused([(probe, probe)]), "refused() let %s through" % probe
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, "a.lua"), "w") as fh:
            fh.write("-- see C:" + "\\Users\\someone\\notes.md")
        assert refused([("a.lua", "a.lua")], td), "refused() let a user-profile path through"
        with open(os.path.join(td, "b.md"), "w") as fh:
            fh.write("notes\n```c\nif (h->has != 1) return 0;\n```\n")
        assert refused([("b.md", "b.md")], td), "refused() let a decompiled C block through"
    print("selftest ok: %d files, nothing refused" % len(m))


if __name__ == "__main__":
    unknown = [a for a in sys.argv[1:] if a not in ("--check", "--selftest")]
    if unknown:
        print("unknown argument(s): %s" % " ".join(unknown))
        sys.exit(2)
    m = manifest()
    bad = refused(m)
    if bad:
        for s, why in bad:
            print("REFUSED  %s  (%s)" % (s, why))
        sys.exit(1)
    if "--selftest" in sys.argv:
        _selftest()
    elif "--check" in sys.argv:
        found = SG.drift(ROOT, REPO, m)
        for s, _d, why in found:
            print("%-22s %s" % (why, os.path.relpath(s, ROOT)))
        print("%d file(s) drift" % len(found))
        sys.exit(1 if found else 0)
    else:
        found = SG.sync(ROOT, REPO, m)
        for s, _d, why in found:
            print("%-22s %s" % (why, os.path.relpath(s, ROOT)))
        print("synced %d file(s) into %s" % (len(found), REPO))
