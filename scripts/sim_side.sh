#!/usr/bin/env bash
# Start the simulated arm and the drawing node in one tmux session. Run it in
# the VirtualBox VM, before capture.
#
#   scripts/sim_side.sh          start the arm (with RViz) and the drawing node
#   RVIZ=false scripts/sim_side.sh    same without RViz, lighter on a small VM
#   scripts/sim_side.sh stop     stop them
#
# Assumes ros2_kortex_ws and the sim packages (sketch_capture, arm_drawing)
# are already built. Override with env vars: WS, SESSION, ROS_SETUP, ROS_DOMAIN_ID.

set -eo pipefail

SESSION=${SESSION:-sim}
WS=${WS:-$HOME/ros2_kortex_ws}
ROS_SETUP=${ROS_SETUP:-/opt/ros/jazzy/setup.bash}
DOMAIN=${ROS_DOMAIN_ID:-30}
RVIZ=${RVIZ:-true}

die() { echo "error: $*" >&2; exit 1; }
ok()  { echo "ok:    $*"; }

if [[ ${1:-} == stop ]]; then
    tmux has-session -t "$SESSION" 2>/dev/null && tmux kill-session -t "$SESSION"
    ok "session '$SESSION' stopped"
    exit 0
fi

command -v tmux >/dev/null            || die "tmux is not installed"
[[ -f $ROS_SETUP ]]                   || die "ROS setup not found: $ROS_SETUP"
[[ -f $WS/install/setup.bash ]]       || die "workspace not built: $WS/install/setup.bash"
[[ -d $WS/install/arm_drawing ]]      || die "arm_drawing is not built (colcon build --packages-select arm_drawing)"
[[ -d $WS/install/sketch_capture ]]   || die "sketch_capture is not built (colcon build --packages-select sketch_capture)"
ok "workspace found"

tmux has-session -t "$SESSION" 2>/dev/null && { tmux kill-session -t "$SESSION"; echo "note:  replaced the old '$SESSION' session"; }
env_cmd="source $(printf %q "$ROS_SETUP") && source $(printf %q "$WS/install/setup.bash") && export ROS_DOMAIN_ID=$DOMAIN"

tmux new-session -d -s "$SESSION" -n arm
tmux send-keys -t "$SESSION:arm" "$env_cmd && ros2 launch kortex_bringup gen3.launch.py robot_ip:=192.168.1.10 use_fake_hardware:=true dof:=7 launch_rviz:=$RVIZ" Enter

tmux new-window -d -t "$SESSION" -n drawing
tmux send-keys -t "$SESSION:drawing" "$env_cmd && ros2 launch arm_drawing arm_drawing.launch.py" Enter

# The drawing node waits for the arm controller by itself, then parks the arm
# at the ready pose, which takes 5 s. Capture must not start before that.
echo "wait:  arm starting (can take a few minutes on the VM) ..."
for ((i = 0; i < 300; i++)); do
    out=$(tmux capture-pane -p -t "$SESSION:drawing" 2>/dev/null || true)
    [[ $out == *"moving to the ready pose"* ]] && break
    sleep 1
done
if ((i == 300)); then
    tmux capture-pane -p -t "$SESSION:drawing" | tail -10
    die "arm did not reach the ready pose. Attach with: tmux attach -t $SESSION"
fi
sleep 7
ok "arm is at the ready pose"

cat <<EOF

Ready. Next: scripts/capture.sh <run-name>
Windows: tmux attach -t $SESSION    (Ctrl-b n = next window, Ctrl-b d = leave it running)
EOF
