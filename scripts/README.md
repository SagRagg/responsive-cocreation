# scripts

One command per machine to start a benchmark run. They assume everything is
already installed and built (ROS 2 Jazzy, the TensorFlow venv, `ros2_kortex_ws`
with `sketch_capture` and `arm_drawing`). They install and build nothing, check
what they need first, and stop with a clear message if something is missing.

| Script | Run it on | Does |
|---|---|---|
| `perception_side.sh edge\|cloud` | the Pi (edge) or the cloud VM (cloud) | Starts perception, then the dashboard, then a CPU sampler, in a `tmux` session called `run`. Waits for each to report it is up |
| `sim_side.sh` | the VirtualBox VM | Starts the simulated arm and the drawing node in a `tmux` session called `sim`. Waits until the arm is at its ready pose |
| `capture.sh <run-name> [per-digit] [seed]` | the VirtualBox VM | Checks the other side is up, then runs `sketch_capture` in the terminal. Defaults: 3 per digit (30 trials), seed 42 |

`dashboard/cpu_sample.py` is the sampler the first script starts. It reads
`/proc` every 2 s and writes one CPU/memory row per watched process.

## A run

Update the code on each machine first (`git pull` on the `simulation` branch;
on the Pi that is the worktree `~/rc-simulation`).

1. Pi (or cloud VM):

   ```bash
   ~/rc-simulation/scripts/perception_side.sh edge
   ```

   On the cloud VM use `cloud`: the dashboard then binds to the VM's Tailscale
   address instead of every interface. It prints the URL to open.

2. VM:

   ```bash
   ~/responsive-cocreation/scripts/sim_side.sh
   ```

3. VM, after step 2 says the arm is ready:

   ```bash
   ~/responsive-cocreation/scripts/capture.sh edge_01
   ```

   Use the same seed for the edge and the cloud run so both see the same
   digits. Add `1` as the second argument for a 10-trial dry run.

4. Pi (or cloud VM), when capture has finished:

   ```bash
   ~/rc-simulation/scripts/perception_side.sh stop
   ```

   This stops everything and prints the CPU summary of the run.

Start order matters: capture publishes as soon as anything listens on
`/sketch_image`, so perception (and the arm) must be up first. `capture.sh`
refuses to start when it cannot see them. `FORCE=1` skips that check.

## Where things end up

| What | Where |
|---|---|
| Latency/accuracy CSV, one per run | on the Pi or cloud VM, `~/dashboard_logs/<placement>_<date>-<time>.csv` |
| CPU samples | same folder, `cpu_<placement>_<date>-<time>.csv` |
| Capture's trial log (ground truth) | on the VM, `~/runs/<run-name>.csv` |

Copy the dashboard CSVs to your laptop to load them into the dashboard's
Compare tab:

```bash
scp nikko@<pi-ip>:dashboard_logs/edge_*.csv .
```

## Settings

Paths and names can be overridden with environment variables when the defaults
do not fit, for example `VENV=~/other-venv scripts/perception_side.sh edge`.
The variables are listed at the top of each script (`PERCEPTION_NODE`, `VENV`,
`CSV_DIR`, `PORT`, `WS`, `RVIZ=false` for no RViz, and so on).

## Working in the tmux windows

`tmux attach -t run` (or `sim`) shows the nodes' logs. `Ctrl-b n` switches
window, `Ctrl-b d` leaves it running in the background. Each window is a normal
shell, so you can `Ctrl-C` a node and run it again by hand.
