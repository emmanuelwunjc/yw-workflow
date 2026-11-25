# Sourced by every loop script, with the script's own arguments:
#   LOOP=$(cd "$(dirname "$0")" && pwd); . "$LOOP/project.sh" "$@"; set -- ${ARGS[@]+"${ARGS[@]}"}
# It takes `--project <name>` and `--all-projects` out of the arguments, and leaves the rest in ARGS.
# PROJECT is the project to use: the one named, or the only one in projects.json. With two or more
# projects and none named it stops (exit 2): a script never guesses a repo. With --all-projects,
# PROJECT stays empty and ALL_PROJECTS is 1. A script that has no --all-projects mode refuses it.
# pget <key> prints one value of PROJECT (projects.py get). The loop needs BOT_HOME, the bot's home
# folder (locks, logs, bot.json): it stops when BOT_HOME is unset.
PROJECT= ALL_PROJECTS=0 ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --project) [ $# -ge 2 ] || { echo "--project needs a name" >&2; exit 2; }; PROJECT=$2; shift 2 ;;
    --project=*) PROJECT=${1#*=}; shift ;;
    --all-projects) ALL_PROJECTS=1; shift ;;
    *) ARGS+=("$1"); shift ;;
  esac
done
[ -n "${BOT_HOME:-}" ] || { echo "BOT_HOME is not set: export the bot's home folder, e.g. BOT_HOME=~/.orca/bots/<bot>" >&2; exit 2; }
if [ "$ALL_PROJECTS" = 1 ]; then
  [ -z "$PROJECT" ] || { echo "--project and --all-projects together: name one or the other" >&2; exit 2; }
else
  PROJECT=$(python3 -I "$LOOP/projects.py" name "$PROJECT") || exit 2
fi
pget() { python3 -I "$LOOP/projects.py" get "$PROJECT" "$1"; }
# Every project name, one per line, for an --all-projects run.
pall() { python3 -I "$LOOP/projects.py" list; }
