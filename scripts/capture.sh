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
# The trial log goes to ~/runs/<run-name>.csv. FORCE=1 skips the checks.

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

if [[ ${FORCE:-} != 1 ]]; then
    problems=0
    check() {   # description actual minimum
        if [[ ${2:-0} -ge $3 ]]; then
            echo "ok:    $1 ($2)"
        else
            echo "FAIL:  $1 (found ${2:-0}, need $3)"; problems=1
        fi
    }
    check "perception publishes /strokes"          "$(count /strokes Publisher)"           1
    check "arm_drawing listens on /strokes"        "$(count /strokes Subscription)"        1
    check "arm_drawing publishes /turn_done"       "$(count /turn_done Publisher)"         1
    check "perception listens on /sketch_image"    "$(count /sketch_image Subscription)"   1
    sketch_subs=$(count /sketch_image Subscription)
    if [[ ${sketch_subs:-0} -lt 2 ]]; then
        echo "warn:  the dashboard is not listening on /sketch_image, so no CSV will be recorded"
    fi
    if [[ $problems == 1 ]]; then
        die "the other side is not ready. Start scripts/perception_side.sh on the Pi/cloud and scripts/sim_side.sh here, or use FORCE=1"
    fi
fi

mkdir -p "$HOME/runs"
csv=$HOME/runs/$name.csv
[[ ! -e $csv ]] || die "$csv already exists, pick another run name"
echo "starting capture: $((per_digit * 10)) trials, seed $seed, log $csv"
exec ros2 launch sketch_capture sketch_capture.launch.py \
    seed:="$seed" per_digit:="$per_digit" csv_path:="$csv"
