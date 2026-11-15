# sfincstools

Command-line tools for inspecting and monitoring [SFINCS](https://sfincs.readthedocs.io) models.

## Installation

```bash
pip install -e .
```

## Tools

### `sfpgs` — check the progress of a SFINCS run

```bash
sfpgs [MODEL_DIR] [--watch SECONDS] [--stall MINUTES]
```

- `MODEL_DIR` – folder with `sfincs.inp` (default: current folder)
- `--watch` – refresh every SECONDS until the run ends (default: report once)
- `--stall` – warn if the log has not changed for this many minutes (default 10)

Reads `sfincs.log` / `sfincs_log.txt` (percent complete, remaining time, errors, summary)
and the last time stamp in `sfincs_map.nc` / `sfincs_his.nc`. Safe to run while SFINCS is running.

### `sfcfg` — display the configuration of a SFINCS model

```bash
sfcfg [MODEL_DIR] [--plot] [--save FILE.png]
```

- `MODEL_DIR` – folder with `sfincs.inp` (default: current folder)
- `--plot` – also show a map (bed level, mask, boundary, drainage, weirs, obs) and the forcing time series
- `--save` – write the figure to a file instead of opening a window

Reports `sfincs.inp` grouped by topic with derived values, the presence/size of every
referenced input file, and a short summary of each file's contents.

## Python usage

```python
from sfincstools import sfpgs, sfcfg

sfpgs.main(["path/to/model"])
sfcfg.main(["path/to/model", "--save", "model.png"])
```
