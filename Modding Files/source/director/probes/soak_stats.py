"""Per-turn and whole-run Director figures out of one script log.

    py "Modding Files/source/director/probes/soak_stats.py" <script_log_*.txt>

Answers, situations, stance pushes, grudges and unrest per turn and per decade; asks and pacts;
opportunism and treachery; confederations by trigger and the reasons a merge was refused; and the
number of factions holding a region, from the [soakhelp] line soak_helper.lua writes each round.
"""
import collections
import re
import sys

path = sys.argv[1]
T = collections.defaultdict(collections.Counter)
whole = collections.Counter()
refill = {}
unrest_sizes = collections.Counter()
chests = collections.Counter()
asks_pos, asks_victim, asks_all = 0, 0, 0
forced, faded, remembered, no_ask = [], [], 0, 0
opp, betray = [], []
turn = 0
victim = None
merges, no_merge_why, no_pair_why, holders, threat = [], collections.Counter(), collections.Counter(), {}, []
KEY = re.compile(r"\b\w+_\w+\b")
for raw in open(path, encoding="utf-8", errors="replace"):
    m = re.search(r"\[soakhelp\] holders turn (\d+): (\d+)", raw)
    if m:
        holders[int(m.group(1))] = int(m.group(2))
        continue
    if "[director]" not in raw:
        continue
    l = raw.split("[director] ", 1)[1].strip()
    m = re.match(r"merge (\S+) absorbs (\S+) \((\w+)\)", l)
    if m:
        merges.append((turn, m.group(3), m.group(1), m.group(2)))
        continue
    m = re.match(r"no merge for \S+: (.*)", l)
    if m:
        no_merge_why[re.sub(r"\d+", "N", m.group(1))] += 1
        continue
    m = re.match(r"no merge \S+ \+ \S+: (.*)", l)
    if m:
        no_pair_why[KEY.sub("X", m.group(1))] += 1
        continue
    if l.startswith("threat score") or l.startswith("runaway"):
        threat.append((turn, l))
    m = re.match(r"refill turn (\d+): budget (\d+) of (\d+)", l)
    if m:
        refill[int(m.group(1))] = (int(m.group(2)), int(m.group(3)))
        continue
    m = re.match(r"situation kind=(\w+) instigator=(\S+) victim=(\S+) .* turn=(\d+)", l)
    if m:
        turn = int(m.group(4))
        victim = m.group(3)
        T[turn]["sits"] += 1
        if m.group(1) == "opportunism":
            opp.append((turn, m.group(2), m.group(3)))
        if m.group(1) == "treachery":
            betray.append((turn, m.group(2), m.group(3)))
        continue
    c = T[turn]
    if l.startswith("answered:"):
        c["answered"] += 1
    elif l.startswith("passed over: budget"):
        c["broke"] += 1
    elif l.startswith("passed over:"):
        c["passed"] += 1
    elif l.startswith("stance "):
        c["stance"] += 1
    elif l.startswith("past_event "):
        c["grudge"] += 1
    m = re.match(r"unrest (\d+) units", l)
    if m:
        unrest_sizes[int(m.group(1))] += 1
        c["unrest"] += 1
    m = re.match(r"warchest (\d+) to", l)
    if m:
        chests[int(m.group(1))] += 1
    m = re.match(r"ask (\S+)<->(\S+) (\S+)/(\S+) ok=(\w+)/(\w+)", l)
    if m:
        asks_all += 1
        if victim in (m.group(1), m.group(2)):
            asks_victim += 1
        try:
            if float(m.group(3)) + float(m.group(4)) > 0 and m.group(5) == m.group(6) == "true":
                asks_pos += 1
        except ValueError:
            pass
    if l.startswith("no ask "):
        no_ask += 1
    if l.startswith("forced defensive alliance"):
        forced.append((turn, l[len("forced defensive alliance "):]))
    if "has faded" in l:
        faded.append((turn, l))
    if "still remembered" in l:
        remembered += 1
    if l.startswith("plague "):
        c["plague"] += 1

print("turn  sits ans pass broke  stance grudge unrest  budget/cap")
for t in sorted(T):
    if t == 0:
        continue
    c = T[t]
    b = refill.get(t, ("", ""))
    print("%4d %5d %3d %4d %5d %7d %6d %6d  %s/%s" % (t, c["sits"], c["answered"], c["passed"], c["broke"],
                                                      c["stance"], c["grudge"], c["unrest"], b[0], b[1]))
    whole.update(c)
print("total", dict(whole))
def block(a, b):
    ts = [t for t in T if a <= t <= b]
    n = max(1, len(ts))
    return {k: round(sum(T[t][k] for t in ts) / n, 1) for k in ("sits", "answered", "stance", "unrest")}
for a, b in ((1, 10), (11, 20), (21, 30), (31, 40), (41, 50), (51, 56)):
    print("turns %d-%d per turn:" % (a, b), block(a, b))
print("unrest sizes", dict(unrest_sizes), "war chests", dict(chests))
print("asks %d, with the victim %d, positive on both and legal %d, skipped as at odds %d" % (asks_all, asks_victim, asks_pos, no_ask))
print("pacts formed", forced)
print("grudges faded and re-earned", faded)
print("still-remembered refusals", remembered)
print("opportunism", opp)
print("treachery", betray)
print("merges", len(merges), "last_stand", sum(m[1] == "last_stand" for m in merges),
      "runaway", sum(m[1] == "runaway" for m in merges), "spent at 60 each", 60 * len(merges))
for m in merges:
    print("  turn %d %s: %s absorbs %s" % m)
print("no merge for a victim, why", dict(no_merge_why))
print("kin passed over, why", dict(no_pair_why))
print("region-holding factions by decade", {t: n for t, n in sorted(holders.items()) if t % 10 == 1 or t == max(holders)} if holders else "none logged")
print("runaway lines", threat[:20], "..." if len(threat) > 20 else "")
