#!/usr/bin/env bash
# Start the perception node, the dashboard and a CPU sampler in one tmux
# session. Run it on the machine under test: the Pi (edge) or the cloud VM.
#
#   scripts/perception_side.sh edge       start (perception first, then dashboard)
#   scripts/perception_side.sh cloud      same, dashboard bound to the Tailscale IP
#   scripts/perception_side.sh stop       stop everything and print the CPU summary
#
# Assumes everything is already installed and built. Override with env vars:
#   PERCEPTION_NODE  path to mnist_perception_node.py (the checkout on main)
#   VENV             Python venv with TensorFlow       (default ~/venv-tf)
#   CSV_DIR          where the run CSVs and CPU log go (default ~/dashboard_logs)
#   PORT, SESSION, ROS_SETUP, ROS_DOMAIN_ID

set -eo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
SESSION=${SESSION:-run}
PERCEPTION_NODE=${PERCEPTION_NODE:-$HOME/responsive-cocreation/perception/mnist_perception_node.py}
VENV=${VENV:-$HOME/venv-tf}
CSV_DIR=${CSV_DIR:-$HOME/dashboard_logs}
PORT=${PORT:-8080}
ROS_SETUP=${ROS_SETUP:-/opt/ros/jazzy/setup.bash}
DOMAIN=${ROS_DOMAIN_ID:-30}

die() { echo "error: $*" >&2; exit 1; }
ok()  { echo "ok:    $*"; }

# Poll a tmux window until a line of text shows up in it.
wait_for() {   # target pattern seconds
    local i out
    for ((i = 0; i < $3; i++)); do
        out=$(tmux capture-pane -p -t "$1" 2>/dev/null || true)
        [[ $out == *"$2"* ]] && return 0
        sleep 1
    done
    return 1
}

# Type a command into a window (a normal shell, so Ctrl-C and re-run work).
send() {       # window command
    tmux send-keys -t "$SESSION:$1" "$2" Enter
}

latest_cpu_log() { ls -t "$CSV_DIR"/cpu_*.csv 2>/dev/null | head -1 || true; }

stop() {
    local log
    log=$(latest_cpu_log)
    tmux has-session -t "$SESSION" 2>/dev/null && tmux kill-session -t "$SESSION"
    ok "session '$SESSION' stopped"
    if [[ -n "$log" ]]; then
        echo; echo "CPU during the last run ($log):"
        python3 "$REPO/dashboard/cpu_sample.py" --summary "$log" || true
    fi
}

[[ ${1:-} == stop ]] && { stop; exit 0; }

placement=${1:-}
[[ $placement == edge || $placement == cloud ]] || die "usage: $0 edge|cloud|stop"

# ---- preflight: fail early, say what is missing ----------------------------
command -v tmux >/dev/null            || die "tmux is not installed"
[[ -f $ROS_SETUP ]]                   || die "ROS setup not found: $ROS_SETUP"
[[ -x $VENV/bin/python ]]             || die "venv not found: $VENV"
[[ -f $PERCEPTION_NODE ]]             || die "perception node not found: $PERCEPTION_NODE"
[[ -f $(dirname "$PERCEPTION_NODE")/mnist_cnn_baseline.keras ]] \
                                      || die "model file missing next to $PERCEPTION_NODE"
[[ -f $REPO/dashboard/telemetry_dashboard.py ]] \
                                      || die "dashboard not found in $REPO (is this the simulation branch?)"
ok "files found"

if command -v chronyc >/dev/null; then
    chronyc tracking 2>/dev/null | grep -E "^System time" | sed 's/^/ok:    clock: /' || true
else
    echo "warn:  chronyc not found, end-to-end latency needs synced clocks"
fi

if [[ $placement == cloud ]]; then
    command -v tailscale >/dev/null   || die "tailscale not installed (needed to bind the cloud dashboard)"
    bind=$(tailscale ip -4 | head -1)
    [[ -n $bind ]]                    || die "no Tailscale IPv4 address (is tailscale up?)"
    shown=$bind
else
    bind=0.0.0.0
    shown=$(hostname -I 2>/dev/null | awk '{print $1}' || true)
    shown=${shown:-<this-machine-ip>}
fi

# ---- start ------------------------------------------------------------------
tmux has-session -t "$SESSION" 2>/dev/null && { tmux kill-session -t "$SESSION"; echo "note:  replaced the old '$SESSION' session"; }
mkdir -p "$CSV_DIR"
stamp=$(date +%Y%m%d-%H%M%S)
env_cmd="source $(printf %q "$ROS_SETUP") && export ROS_DOMAIN_ID=$DOMAIN"

tmux new-session -d -s "$SESSION" -n perception
send perception "$env_cmd && $(printf %q "$VENV/bin/python") $(printf %q "$PERCEPTION_NODE")"
echo "wait:  loading the model (the first start is slow on a Pi) ..."
if ! wait_for "$SESSION:perception" "CNN model loaded" 240; then
    tmux capture-pane -p -t "$SESSION:perception" | tail -15
    die "perception did not report 'CNN model loaded'. Attach with: tmux attach -t $SESSION"
fi
ok "perception is up"

tmux new-window -d -t "$SESSION" -n dashboard
send dashboard "$env_cmd && python3 $(printf %q "$REPO/dashboard/telemetry_dashboard.py") --ros-args -p placement:=$placement -p bind:=$bind -p port:=$PORT -p csv_dir:=$(printf %q "$CSV_DIR")"
if ! wait_for "$SESSION:dashboard" "dashboard on" 30; then
    tmux capture-pane -p -t "$SESSION:dashboard" | tail -15
    die "dashboard did not start. Attach with: tmux attach -t $SESSION"
fi
ok "dashboard is up"

tmux new-window -d -t "$SESSION" -n cpu
send cpu "python3 $(printf %q "$REPO/dashboard/cpu_sample.py") --out $(printf %q "$CSV_DIR/cpu_${placement}_$stamp.csv") --match mnist_perception_node.py --match telemetry_dashboard.py"
ok "CPU sampler logging to $CSV_DIR/cpu_${placement}_$stamp.csv"

cat <<EOF

Ready ($placement). Open   http://$shown:$PORT
Then start the simulation side and run capture (scripts/sim_side.sh, scripts/capture.sh).
Windows: tmux attach -t $SESSION    (Ctrl-b n = next window, Ctrl-b d = leave it running)
When the run is over: scripts/perception_side.sh stop
EOF
