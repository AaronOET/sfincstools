# Changelog

## 0.1.2

- **sfincstools**: `-h` / `--help` now lists the tools with a short description.
- **sfpgs**, **sfcfg**: `-h` now explains `MODEL_DIR` (folder with `sfincs.inp`, default: current folder). New Python API: `build_parser()` returns the tool's argument parser.

## 0.1.1

- Added the **sfincstools** command (also `python -m sfincstools`): `-v` / `--version` prints the package version; with no arguments it lists the available tools.

## 0.1.0

- First release of the `sfincstools` package, with two command-line tools:
- Added **sfpgs** (from `prototype/check_sfincs_progress.py`): checks the progress of a SFINCS run. Reads `sfincs.log` / `sfincs_log.txt` (percent complete, SFINCS's remaining-time estimate, errors, warnings, final summary) and the last time stamp in `sfincs_map.nc` / `sfincs_his.nc`, so the model time reached is shown too. Safe to run while SFINCS is running (output files are opened read-only, a locked file is skipped). `--watch SECONDS` refreshes until the run finishes or fails; `--stall MINUTES` (default 10) flags a run whose log has not changed for that long. Python API: `main(argv)`, `report()`, `read_log()`, `read_inp()`.
- Added **sfcfg** (from `prototype/show_sfincs_config.py`): displays the configuration of a SFINCS model. Lists `sfincs.inp` grouped by topic (Grid, Time, Numerics, Physics, Output, Other) with derived values (cells, grid size and extent, run length, number of map / his frames), every referenced input file (present / missing, size), and a summary of each file: active cells and mask values, subgrid table, bed level, infiltration, Manning, boundary points and `bzs` range, discharge points and `dis` range, drainage structures per type, weirs / thin dams, observation points, uniform precipitation total, and NetCDF forcing (dimensions, time range, variable min / mean / max, with a warning when it does not cover `tstart` .. `tstop`). `--plot` shows a map (bed level or mask, boundary, discharges, drainage, weirs, obs) with the forcing time series; `--save FILE.png` writes it to a file. Unlike the prototype, the precipitation total also works with NumPy 2 (`np.trapezoid`). Python API: `main(argv)`, `read_inp()`, `show_inp()`, `show_files()`, `show_details()`, `plot()`.
