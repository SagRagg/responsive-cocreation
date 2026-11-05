#!/usr/bin/env bash
# Run one benchmark: check the other side is up, then start sketch_capture in
# this terminal. Run it in the VirtualBox VM after sim_side.sh.
#
#   scripts/capture.sh <run-name> [trials-per-digit=3] [seed=42]
#
#   scripts/capture.sh edge_01          30 trials (3 per digit), seed 42
#   scripts/capture.sh dry_01 1         10-trial dry run
#
# Use the same seed for the edge and the cloud run so both see the same digits.
# The trial log goes to ~/runs/<run-name>.csv. Before starting it waits up to
# 45 s (WAIT=) for perception, the arm and the dashboard to be matched.
# NO_DASHBOARD=1 runs without the dashboard, FORCE=1 skips the checks.

set -eo pipefail

name=${1:-}
per_digit=${2:-3}
seed=${3:-42}
WS=${WS:-$HOME/ros2_kortex_ws}
ROS_SETUP=${ROS_SETUP:-/opt/ros/jazzy/setup.bash}
DOMAIN=${ROS_DOMAIN_ID:-30}

die() { echo "error: $*" >&2; exit 1; }
[[ -n $name ]] || die "usage: $0 <run-name> [trials-per-digit=3] [seed=42]"
[[ -f $ROS_SETUP && -f $WS/install/setup.bash ]] || die "ROS or the workspace is not set up ($ROS_SETUP, $WS/install/setup.bash)"

set +e   # the ROS setup scripts are not written for `set -e`
# shellcheck disable=SC1090
source "$ROS_SETUP"
# shellcheck disable=SC1091
source "$WS/install/setup.bash"
set -e
export ROS_DOMAIN_ID=$DOMAIN

count() {   # topic "Publisher|Subscription"
    ros2 topic info "$1" 2>/dev/null | awk -v k="$2" '$0 ~ k " count" {print $3}' || true
}

# Discovery across the VPN is gradual: the dashboard can be matched seconds
# after perception. Capture publishes trial 1 as soon as anything listens, so
# wait until everything is matched, or trial 1 reaches perception but not the
# dashboard (no ground truth, no compute time for that row).
if [[ ${FORCE:-} != 1 ]]; then
    want_dashboard=1
    [[ ${NO_DASHBOARD:-} == 1 ]] && want_dashboard=0
    deadline=$((SECONDS + ${WAIT:-45}))
    while :; do
        missing=()
        [[ $(count /strokes Publisher) -ge 1 ]]        || missing+=("perception is not publishing /strokes")
        [[ $(count /strokes Subscription) -ge 1 ]]       || missing+=("arm_drawing is not listening on /strokes")
        [[ $(count /turn_done Publisher) -ge 1 ]]        || missing+=("arm_drawing is not publishing /turn_done")
        if [[ $want_dashboard == 1 ]]; then
            [[ $(count /sketch_image Subscription) -ge 2 ]] || missing+=("perception and the dashboard are not both listening on /sketch_image")
            [[ $(count /ground_truth Subscription) -ge 1 ]] || missing+=("the dashboard is not listening on /ground_truth")
        else
            [[ $(count /sketch_image Subscription) -ge 1 ]] || missing+=("perception is not listening on /sketch_image")
        fi
        [[ ${#missing[@]} -eq 0 ]] && break
        if ((SECONDS >= deadline)); then
            printf 'FAIL:  %s\n' "${missing[@]}"
            die "the other side is not ready. Start scripts/perception_side.sh on the Pi/cloud and scripts/sim_side.sh here (NO_DASHBOARD=1 runs without the dashboard, FORCE=1 skips all checks)"
        fi
        printf 'wait:  %s\n' "${missing[0]}"
        sleep 3
    done
    echo "ok:    everything required is matched"
fi

mkdir -p "$HOME/runs"
csv=$HOME/runs/$name.csv
[[ ! -e $csv ]] || die "$csv already exists, pick another run name"
echo "starting capture: $((per_digit * 10)) trials, seed $seed, log $csv"
exec ros2 launch sketch_capture sketch_capture.launch.py \
    seed:="$seed" per_digit:="$per_digit" csv_path:="$csv"
