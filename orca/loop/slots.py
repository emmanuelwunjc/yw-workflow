import glob, json, os, re, subprocess, sys, time
# Slots left for new workers of one project (owner decisions 2026-11-24). One definition:
#   SLOTS = WORKER_CAP - (taken tickets with no PR that a worker holds) - LIVE
# A worker holds a taken ticket when a working agent is on its branch or names #<n>, a worktree on its
# branch has a live terminal (an idle worker at its prompt is "done", review BLOCK 2), a start lock
# (start.sh) under 3 hours old exists, or the caller passes <n> (slot.sh passes the ticket it just linked).
# Usage: slots.py [--project <name>] [<ticket> ...]. Prints the free work check (free_tickets.sh), then:
#   DEAD: #<n> <branch>       a taken ticket with no PR that no worker holds. It frees its slot, and the
#                             line stays until someone unlinks the branch
#   LIVE: <n> (<workspaces>)  workspaces under the project's ws_root with a working agent that is no review,
#                             and on no taken branch without a PR (WORKERS counts those). A worker on its PR's
#                             branch counts here: WORKERS stops counting it once the PR is open (review BLOCK 1).
#   SLOTS: <k>                the most workers the sweep may start now. No SLOTS line after a CAP line.
# precheck.sh needs k > 0. slot.sh runs after the sweep linked its own branch and needs k >= 0.
# Exit 1 when free_tickets.sh or orca fails, the ps list is cut, the locks folder is missing, or a <ticket>
# is on no TAKEN line with no PR: a count it could not read starts nothing.
# A workspace on a taken branch is that ticket's worker: it counts once, in the taken count, never in LIVE.
# Two sweeps that link at the same time each see the other's new link as DEAD (no lock yet). The sweep
# holds start-guard.sh around its starts, so one sweep counts and starts at a time.
# ponytail: a review is matched by name ("Review ..."), a "review-" branch, or its task title as review-spec.sh
# and the reviewer specs write it. A worker started a minute ago can count twice: it errs low.
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
import projects  # noqa: E402

NAME, ARGS = projects.from_argv(sys.argv[1:])
WS = projects.project(NAME)["ws_root"].rstrip("/") + "/"
# The bot's home folder (locks): BOT_HOME must be set.
BOT_HOME = os.environ.get("BOT_HOME") or sys.exit("slots: BOT_HOME is not set: export the bot's home folder")
LOCKS = os.environ.get("START_LOCKS") or os.path.join(BOT_HOME, "locks")
# Start locks of every bot home count (cutover, 2026-11-25): a ticket another bot started under 3 hours ago
# keeps its slot here too. BOT_HOMES is the folder of the bot homes, default the one that holds BOT_HOME.
BOT_HOMES = os.environ.get("BOT_HOMES") or os.path.dirname(BOT_HOME)
LOCK_DIRS = [LOCKS] + sorted(set(glob.glob(os.path.join(BOT_HOMES, "*", "locks"))) - {LOCKS})
LOCK_SECS = 3 * 3600
REVIEW = re.compile(r"^(review of pr|fix round)|adversarial review|\breviewer\b", re.I)


def run(*cmd):
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode:
        sys.exit(f"slots: {' '.join(cmd[:3])} failed: {out.stderr.strip()[-500:]}")
    return out.stdout


def title(a):
    return a.get("taskTitle") or a.get("prompt") or ""


def live(worktrees, taken):
    names = []
    for w in worktrees:
        path, branch = w.get("path") or "", (w.get("branch") or "").removeprefix("refs/heads/")
        if (not path.startswith(WS) or branch in taken
                or re.match(r"review\b", w.get("displayName") or "", re.I)
                or branch.split("/")[-1].startswith("review")
                or not any(a.get("state") == "working" and not REVIEW.search(title(a)) for a in w.get("agents") or [])):
            continue
        names.append(path.rstrip("/").split("/")[-1])
    return names


def dead(worktrees, taken, own):
    # Prints a DEAD line per dead branch. Returns the tickets with no held branch: they free their slot.
    held_tickets = set(own)
    for b, n in taken.items():
        on_branch = [w for w in worktrees if (w.get("branch") or "").removeprefix("refs/heads/") == b]
        held = any(w.get("terminalVerdict") == "live" for w in on_branch) or any(
            a.get("state") == "working" and (w in on_branch or re.search(rf"#{n}\b", title(a)))
            for w in worktrees for a in w.get("agents") or [])
        locked = any(os.path.exists(lk) and time.time() - os.path.getmtime(lk) < LOCK_SECS
                     for lk in (os.path.join(d, n) for d in LOCK_DIRS))
        if held or n in own or locked:
            held_tickets.add(n)
        else:
            print(f"DEAD: #{n} {b}")
    return set(taken.values()) - held_tickets


def main():
    out = subprocess.run(["bash", f"{D}/free_tickets.sh", "--project", NAME], capture_output=True, text=True)
    sys.stdout.write(out.stdout)
    if out.returncode:
        if not os.path.exists(f"{D}/free_tickets.sh"):
            print("slots.py: run it by its absolute path, e.g. ~/code/yw-workflow/orca/loop/slots.py", file=sys.stderr)
        sys.exit(f"slots: free_tickets.sh failed: {out.stderr.strip()[-500:]}")
    m = re.search(r"^WORKERS: (\d+)/(\d+)$", out.stdout, re.M)
    if not m:  # a CAP line: start nothing
        return
    taken = {b: n for n, b in re.findall(r"^TAKEN: #(\d+) (\S+)$", out.stdout, re.M)}  # no PR only
    if set(ARGS) - set(taken.values()):
        sys.exit(f"slots: not a taken ticket with no PR: {' '.join(sorted(set(ARGS) - set(taken.values())))}")
    if not os.path.isdir(LOCKS):
        sys.exit(f"slots: no locks folder {LOCKS}")
    ps = json.loads(run("orca", "worktree", "ps", "--since", "1d", "--json"))["result"]
    # ps also sets truncated when a paired host is not covered (hostScope.omittedHostIds), with every local row
    # in the page. Loop workspaces are local (WS), so only a page with fewer rows than totalCount is cut.
    # ponytail: assumes no loop worker runs on a paired host; read omittedHostIds if one ever does.
    if ps.get("truncated") and len(ps["worktrees"]) < ps.get("totalCount", float("inf")):
        sys.exit("slots: orca worktree ps list is truncated: live work may be missing")
    worktrees = [w for w in ps["worktrees"] if not w.get("isArchived")]
    freed = dead(worktrees, taken, set(ARGS))
    names = live(worktrees, taken)
    print(f"LIVE: {len(names)} ({', '.join(names)})")
    print(f"SLOTS: {int(m[2]) - (int(m[1]) - len(freed)) - len(names)}")


if __name__ == "__main__":
    sys.exit(main())
