"""
Build a sfincs.inp in a desktop (tkinter) GUI.

  sfgen [SOURCE] [--out-dir DIR]

  SOURCE     .xlsx (one sheet per group) or .inp to load at start, or a model folder
             (its sfincs.inp is loaded). Default: inp_prep.xlsx in the current folder
             if it exists, else the built-in defaults.
  --out-dir  output folder for the generated .inp / .bat (default: the folder of an
             .inp SOURCE, else the current folder)

Each tab is one parameter group (= one sheet of the .xlsx when saved as Excel).
  * On checkbox: checked -> 'key = value' is written; unchecked -> the line is left out
    (or written as '#key = value' when 'Write disabled lines as #comments' is ticked;
    SFINCS ignores such lines because the keyword no longer matches).
  * The description column is for the GUI / xlsx only - sfincs.inp has no comments.
  * Load reads an .xlsx (one sheet per group) or an existing sfincs.inp ('Load .inp...').
    Keywords of a loaded .inp are sorted into the matching tab; unknown ones go to 'other'.
  * Time tab: tref / tstart / tstop as 'yyyymmdd HHMMSS'. Preview/Generate checks them,
    prints the simulation length and, when 'dtmaxout = full run' is ticked, sets
    dtmaxout = tstop - tstart.
  * Generate writes <name>.inp (default sfincs.inp) and optionally run_<name>.bat.
    SFINCS always reads 'sfincs.inp' from the working folder, so for any other name the
    .bat first copies <name>.inp -> sfincs.inp.
  * Generate warns about *file entries that do not exist in the output folder, about keywords
    active twice (incl. aliases such as dtout/dtmapout, precipfile/prcfile) and about
    keywords SFINCS does not read (dtmin, storeqdrain).
  * Keyword list = all keywords read by sfincs_input.f90 (Deltares/SFINCS main, checked 2026-11).
"""
import os
import sys
import argparse
import contextlib
import io
from collections import OrderedDict
from datetime import datetime

import pandas as pd

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

DEFAULT_XLSX = 'inp_prep.xlsx'          # auto-loaded at start if it exists
DEFAULT_NAME = 'sfincs'                 # -> sfincs.inp
EXE_DEFAULT = r'C:\SFINCS\sfincs.exe'
KEY_WIDTH = 20                          # column width of the keyword in sfincs.inp
TFMT = '%Y%m%d %H%M%S'

# ---------------------------------------------------------------------------
#  Built-in defaults: group -> [on, keyword, value, description]
#  Active rows  = SFINCS_Gaemi2024_false_time/sfincs.inp.
#  Inactive rows = every other keyword read by SFINCS (sfincs_input.f90, Deltares/SFINCS
#  main branch, checked 2026-11), value = SFINCS default. Older executables ignore
#  keywords they do not know.
# ---------------------------------------------------------------------------
DEFAULTS = OrderedDict([
    ('info', [
        ['SFINCS input generated with sfincsGen', '', ''],
    ]),
    ('domain', [
        [True,  'mmax',      '583',        'Number of grid cells in x (m) direction'],
        [True,  'nmax',      '648',        'Number of grid cells in y (n) direction'],
        [True,  'dx',        '20.0',       'Grid size in x (m)'],
        [True,  'dy',        '20.0',       'Grid size in y (m)'],
        [True,  'x0',        '172937.5',   'x of grid origin (lower-left corner)'],
        [True,  'y0',        '2498797.5',  'y of grid origin (lower-left corner)'],
        [True,  'rotation',  '0',          'Grid rotation (deg, anti-clockwise from east)'],
        [True,  'epsg',      '3826',       'EPSG code of the model CRS (3826 = TWD97 / TM2)'],
        [True,  'latitude',  '0.0',        'Latitude for Coriolis in a projected CRS (deg)'],
        [True,  'crsgeo',    '0',          '1: geographic (spherical) coordinates, 0: projected'],
        [False, 'utmzone',   'nil',        'UTM zone (e.g. 51N) for spiderweb lat/lon conversion'],
        [False, 'global_model', '0',       '1: global model (alias global)'],
    ]),
    ('time', [
        [True,  'tref',      '20000101 000000', 'Reference time (yyyymmdd HHMMSS); = tstart if omitted'],
        [True,  'tstart',    '20000101 000000', 'Start time (yyyymmdd HHMMSS)'],
        [True,  'tstop',     '20000102 120000', 'Stop time (yyyymmdd HHMMSS)'],
        [True,  'tspinup',   '0.0',        'Spin-up time for boundary conditions (s)'],
        [False, 'spinup_meteo', '0',       '1: apply spin-up also to meteo forcing'],
        [True,  'dtmax',     '60.0',       'Maximum internal time step (s)'],
    ]),
    ('numerics', [
        [True,  'alpha',     '0.5',        'CFL time-step reduction factor'],
        [True,  'theta',     '1.0',        'Momentum smoothing factor (1.0 = no smoothing)'],
        [True,  'huthresh',  '0.01',       'Threshold water depth for flux (m); default 0.05'],
        [False, 'hmin_cfl',  '0.1',        'Min. depth used for the CFL time step (m)'],
        [True,  'advection', '1',          '1/0 Advection on/off (0 = SFINCS-LIE)'],
        [False, 'advection_scheme', 'upw1', 'upw1 or original'],
        [False, 'advection_mask', '1',     '1/0 use advection mask'],
        [False, 'advlim',    '1.0',        'Limit on advective acceleration (m/s2)'],
        [True,  'viscosity', '1',          '1/0 Viscosity on/off'],
        [False, 'nuvisc',    '0.01',       'Viscosity coefficient per m grid size'],
        [False, 'nuviscfac', '100.0',      'Viscosity factor at refinement transitions'],
        [False, 'friction2d', '1',         '1/0 2D component in friction term'],
        [False, 'coriolis',  '1',          '1/0 Coriolis term'],
        [True,  'btfilter',  '60.0',       'Boundary mean-velocity filter time (s)'],
        [False, 'btrelax',   '3600.0',     'Boundary mean-velocity relaxation time (s)'],
        [False, 'structure_relax', '10.0', 'Relaxation time for structure discharges (s)'],
        [False, 'wiggle_suppression', '1', '1/0 wiggle limiter (subgrid only)'],
        [False, 'wiggle_factor', '0.1',    'Wiggle limiter strength'],
        [False, 'wiggle_threshold', '0.1', 'Wiggle acceleration-difference threshold (m/s2)'],
        [False, 'uvlim',     '10.0',       'Limit on flux velocity (m/s)'],
        [False, 'uvmax',     '1000.0',     'Max flux velocity for min. time step (m/s); replaces stopdepth'],
        [True,  'stopdepth', '100.0',      'LEGACY - removed in newer SFINCS (replaced by uvmax); ignored there'],
        [False, 'slopelim',  '9999.9',     'Slope limiter on dz/dx (9999.9 = off)'],
        [False, 'huvmin',    '0.0',        'Min. depth for velocity calculation (m)'],
        [False, 'h73table',  '0',          '1: lookup table for the h^(7/3) term'],
        [False, 'bndtype',   '1',          'Boundary type of sfincs.bzs (1 = water level)'],
        [False, 'nonh',      '0',          '1/0 Non-hydrostatic on/off'],
        [False, 'nh_fnudge', '0.9',        'Non-hydrostatic nudging factor'],
        [False, 'nh_tstop',  '-999.0',     'Non-hydrostatic stop time (s)'],
        [False, 'nh_tol',    '0.001',      'Non-hydrostatic solver tolerance'],
        [False, 'nh_itermax', '100',       'Non-hydrostatic max. iterations'],
        [False, 'bathtub',   '0',          '1: bathtub mode'],
        [False, 'bathtub_fachs', '0.2',    'Bathtub factor'],
        [False, 'bathtub_dt', '-999.0',    'Bathtub time step (s)'],
        [False, 'dtoutfixed', '1',         '1: fixed output times'],
    ]),
    ('physics', [
        [True,  'zsini',     '0.0',        'Initial water level (m)'],
        [False, 'manning',   '0.04',       'Uniform Manning n (if no manningfile / subgrid)'],
        [True,  'rgh_lev_land', '0.0',     'Level separating land / sea roughness (m)'],
        [False, 'manning_land', '0.04',    'Manning n above rgh_lev_land (default -999 = unused)'],
        [False, 'manning_sea', '0.02',     'Manning n below rgh_lev_land (default -999 = unused)'],
        [True,  'rhoa',      '1.25',       'Air density (kg/m3)'],
        [True,  'rhow',      '1024.0',     'Water density (kg/m3)'],
        [True,  'baro',      '1',          '1/0 Atmospheric pressure gradient on/off'],
        [True,  'pavbnd',    '0',          'Average boundary pressure for inverse barometer (Pa, 0 = off)'],
        [True,  'gapres',    '101200.0',   'Background atmospheric pressure (Pa)'],
        [True,  'cdnrb',     '3',          'Number of wind-drag breakpoints (0 = built-in defaults)'],
        [True,  'cdwnd',     '0.0 28.0 50.0', 'Wind speeds of the drag breakpoints (m/s)'],
        [True,  'cdval',     '0.001 0.0025 0.0015', 'Drag coefficients at the breakpoints'],
        [False, 'amprblock', '1',          '1: rain value held as block over its interval, 0: linear'],
        [False, 'factor_wind', '1.0',      'Multiplier on all wind input'],
        [False, 'factor_pres', '1.0',      'Multiplier on pressure deficit'],
        [False, 'factor_prcp', '1.0',      'Multiplier on all precipitation'],
        [False, 'factor_spw_size', '1.0',  'Multiplier on spiderweb radius'],
        [False, 'spwmergefrac', '0.5',     'Spiderweb merge fraction of radius'],
        [False, 'usespwprecip', '1',       '1/0 use spiderweb precipitation'],
        [False, 'radstr',    '0',          '1: radiation stress'],
        [False, 'rugdepth',  '0.05',       'Depth threshold for run-up gauges (m)'],
        [False, 'wave_enhanced_roughness', '0', '1: wave-enhanced roughness'],
        [False, 'waveage',   '-999.0',     'Wave age'],
    ]),
    ('grid files', [
        [True,  'inputformat', 'bin',      'bin or asc'],
        [False, 'qtrfile',   'sfincs.nc',  'Quadtree grid file (quadtree models)'],
        [True,  'mskfile',   'sfincs.msk', 'Mask file (0 inactive, 1 active, 2 water-level bnd, 3 outflow)'],
        [True,  'indexfile', 'sfincs.ind', 'Index file of active cells (binary input)'],
        [False, 'depfile',   'sfincs.dep', 'Bed level file (if no subgrid)'],
        [True,  'sbgfile',   'sfincs_subgrid.nc', 'Subgrid tables (NetCDF needs SFINCS >= v2.1.1)'],
        [False, 'manningfile', 'sfincs.man', 'Spatially varying Manning n'],
        [False, 'inifile',   'sfincs.ini', 'Initial water level file'],
        [False, 'rstfile',   'sfincs.rst', 'Restart file'],
        [False, 'cstfile',   'sfincs.cst', 'Coastline file'],
        [False, 'volfile',   'sfincs.vol', 'Green-infrastructure storage volume'],
        [False, 'z0lfile',   'sfincs.z0l', 'Roughness length file'],
    ]),
    ('structures', [
        [True,  'weirfile',  'sfincs.weir', 'Weirs / levees (polyline with crest heights)'],
        [False, 'thdfile',   'sfincs.thd', 'Thin dams'],
        [True,  'drnfile',   'sfincs.drn', 'Drainage structures / pumps (legacy asc or TOML)'],
        [False, 'dkbfile',   'sfincs.dkb', 'Dike breach definitions (TOML)'],
        [False, 'urbfile',   'sfincs.urb', 'Urban drainage zones (TOML)'],
    ]),
    ('infiltration', [
        [False, 'qinf',      '0.0',        'Uniform constant infiltration rate (mm/h)'],
        [False, 'qinf_zmin', '0.0',        'Min. elevation where qinf applies (m)'],
        [True,  'qinffile',  'sfincs_quarter.qinf', 'Spatially varying constant infiltration (mm/h, legacy)'],
        [False, 'inffile',   'sfincs_inf.nc', 'NetCDF infiltration input (newer method; alias infiltrationfile)'],
        [False, 'inftype',   'none',       'Infiltration method read from inffile (alias infiltrationtype)'],
        [False, 'scsfile',   'sfincs.scs', 'Curve Number: S max file (legacy)'],
        [False, 'sfacinf',   '0.2',        'Curve Number initial abstraction factor'],
        [False, 'smaxfile',  'sfincs.smax', 'Curve Number with recovery: Smax (legacy)'],
        [False, 'sefffile',  'sfincs.seff', 'Curve Number with recovery: Seff (legacy)'],
        [False, 'ksfile',    'sfincs.ks',  'Saturated hydraulic conductivity (legacy)'],
        [False, 'psifile',   'sfincs.psi', 'Green-Ampt: suction head (legacy)'],
        [False, 'sigmafile', 'sfincs.sigma', 'Green-Ampt: max moisture deficit (legacy)'],
        [False, 'f0file',    'sfincs.f0',  'Horton: max infiltration (legacy)'],
        [False, 'fcfile',    'sfincs.fc',  'Horton: min infiltration (legacy)'],
        [False, 'kdfile',    'sfincs.kd',  'Horton: decay constant (legacy)'],
        [False, 'horton_kr_kd', '10.0',    'Horton recovery / decay ratio'],
    ]),
    ('forcing', [
        [True,  'bndfile',   'sfincs.bnd', 'Water-level boundary points'],
        [True,  'bzsfile',   'sfincs.bzs', 'Water-level time series at the boundary points'],
        [False, 'bzifile',   'sfincs.bzi', 'Infragravity / incoming wave series'],
        [False, 'bcafile',   'sfincs.bca', 'Tidal components at the boundary points'],
        [False, 'use_bcafile', '1',        '1/0 use bcafile'],
        [False, 'bdrfile',   'sfincs.bdr', 'Boundary (downstream river) file'],
        [False, 'netbndbzsbzifile', 'sfincs_netbndbzsbzifile.nc', 'Boundary points + series as NetCDF'],
        [False, 'srcfile',   'sfincs.src', 'Discharge source points'],
        [False, 'disfile',   'sfincs.dis', 'Discharge time series at the source points'],
        [False, 'netsrcdisfile', 'sfincs_netsrcdisfile.nc', 'Sources + discharges as NetCDF'],
        [False, 'prcfile',   'sfincs.prcp', 'Uniform rainfall time series, mm/h (alias precipfile, prcpfile)'],
        [True,  'netamprfile', 'sfincs_precip_kemi.nc', 'Spatially varying rainfall, NetCDF (mm/h)'],
        [False, 'amprfile',  'sfincs.ampr', 'Spatially varying rainfall, Delft3D meteo (mm/h)'],
        [False, 'wndfile',   'sfincs.wnd', 'Uniform wind time series'],
        [False, 'amufile',   'sfincs.amu', 'Wind u, Delft3D meteo'],
        [False, 'amvfile',   'sfincs.amv', 'Wind v, Delft3D meteo'],
        [False, 'ampfile',   'sfincs.amp', 'Air pressure, Delft3D meteo'],
        [False, 'netamuamvfile', 'sfincs_netamuamv.nc', 'Spatially varying wind u/v, NetCDF'],
        [False, 'netampfile', 'sfincs_netamp.nc', 'Spatially varying air pressure, NetCDF'],
        [False, 'spwfile',   'sfincs.spw', 'Spiderweb (tropical cyclone) file'],
        [False, 'netspwfile', 'sfincs_spw.nc', 'Spiderweb file, NetCDF'],
        [True,  'dtwnd',     '1800.0',     'Update interval of spatial meteo forcing (s)'],
    ]),
    ('output', [
        [True,  'outputformat', 'net',     'net (NetCDF) / bin / asc'],
        [False, 'outputtype_map', 'net',   'Map output format (default = outputformat)'],
        [False, 'outputtype_his', 'net',   'His output format (default = outputformat)'],
        [False, 'nc_deflate_level', '2',   'NetCDF compression level'],
        [False, 't0out',     '-999.0',     'Start of output window (s after tref; -999 = tstart)'],
        [False, 't1out',     '-999.0',     'End of output window (s after tref; -999 = tstop)'],
        [True,  'dtout',     '3600',       'Map output interval (s) (alias of dtmapout)'],
        [True,  'dthisout',  '3600',       'His (observation) output interval (s)'],
        [True,  'dtmaxout',  '129600.0',   'Interval of max-value maps (s); = tstop-tstart for one map'],
        [True,  'dtrstout',  '0.0',        'Restart output interval (s), 0 = none'],
        [True,  'trstout',   '-999.0',     'Time of a single restart output (s), -999 = none'],
        [False, 'obsfile',   'sfincs.obs', 'Observation points'],
        [False, 'crsfile',   'sfincs.crs', 'Cross sections (discharge output)'],
        [False, 'rugfile',   'sfincs.rug', 'Run-up gauges'],
        [True,  'storecumprcp', '1',       '1/0 Store cumulative rainfall'],
        [False, 'storevelmax', '1',        '1/0 Store max velocity'],
        [False, 'storefluxmax', '1',       '1/0 Store max flux'],
        [False, 'storevel',  '1',          '1/0 Store velocities in map file'],
        [False, 'storetwet', '1',          '1/0 Store time a cell was wet'],
        [False, 'twet_threshold', '0.01',  'Depth threshold for twet (m)'],
        [False, 'storetzsmax', '1',        '1/0 Store time of max water level'],
        [False, 'storehsubgrid', '1',      '1/0 Store subgrid hmax estimate'],
        [False, 'storehmean', '1',         '1/0 Store mean subgrid depth'],
        [False, 'storezvolume', '1',       '1/0 Store subgrid water volumes'],
        [False, 'storezvolmax', '1',       '1/0 Store max subgrid volume (default 1)'],
        [False, 'storestoragevolume', '1', '1/0 Store green-infrastructure storage volumes'],
        [False, 'storemeteo', '1',         '1/0 Store meteo forcing in map file'],
        [False, 'storemaxwind', '1',       '1/0 Store max wind speed'],
        [False, 'storefw',   '1',          '1/0 Store SnapWave wave forces'],
        [False, 'storewavdir', '1',        '1/0 Store SnapWave wave direction'],
        [False, 'store_dynamic_bed_level', '1', '1/0 Store dynamic bed level'],
        [False, 'store_river_discharge', '1', '1/0 Store per-source discharge in his'],
        [False, 'store_urban_drainage_discharge', '1', '1/0 Store per-zone outfall discharge in his'],
        [False, 'store_cumulative_urban_drainage', '1', '1/0 Store cumulative urban drainage'],
        [False, 'store_tsunami_arrival_time', '1', '1/0 Store tsunami arrival time'],
        [False, 'tsunami_arrival_threshold', '0.01', 'Threshold for tsunami arrival (m)'],
        [False, 'output_on_quadtree_mesh', '0', '1: map output on quadtree mesh'],
        [False, 'timestep_analysis', '1',  '1/0 Write time-step limiter variables'],
        [False, 'writeruntime', '1',       '1/0 Write runtimes.txt'],
        [False, 'debug',     '0',          '1: write output every time step'],
        [False, 'percentage_done', '5',    'Progress reporting interval (%)'],
    ]),
    ('waves', [
        [False, 'snapwave',  '0',          '1: SnapWave on'],
        [False, 'dtwave',    '3600.0',     'Wave update interval (s)'],
        [False, 'snapwave_wind', '0',      '1: SnapWave wind growth'],
        [False, 'snapwave_waveforces_ratio', '1.0', 'Wave-force ratio'],
        [False, 'snapwave_vegetation', '0', '1: SnapWave vegetation'],
        [False, 'snapwave_use_nearest', '1', '1: nearest-point coupling'],
        [False, 'vegetation', '0',         '1: vegetation on'],
        [False, 'vegfile',   'sfincs.veg', 'Vegetation file'],
        [False, 'vegtype',   'none',       'Vegetation type TOML'],
        [False, 'wavemaker_wvmfile', 'sfincs.wvm', 'Wave maker locations'],
        [False, 'wavemaker_timeseries_wvmfile', 'none', 'Wave maker time series'],
        [False, 'wavemaker_wfpfile', 'sfincs.wfp', 'Wave maker forcing points'],
        [False, 'wavemaker_whifile', 'sfincs.whi', 'Wave maker wave heights'],
        [False, 'wavemaker_wtifile', 'sfincs.wti', 'Wave maker wave periods'],
        [False, 'wavemaker_wstfile', 'sfincs.wst', 'Wave maker setup'],
        [False, 'wavemaker_filter_time', '600.0', 'Wave maker filter time (s)'],
        [False, 'wavemaker_filter_fred', '0.99', 'Wave maker filter factor'],
        [False, 'wavemaker_signal', 'spectrum', 'spectrum / ...'],
        [False, 'wavemaker_hmin', '0.1',   'Min. depth at wave maker (m)'],
        [False, 'wavemaker_nfreqs_inc', '100', 'Incident-band frequencies'],
        [False, 'wavemaker_freqmin_inc', '0.04', 'Incident-band min. freq (Hz)'],
        [False, 'wavemaker_freqmax_inc', '1.0', 'Incident-band max. freq (Hz)'],
        [False, 'wavemaker_nfreqs_ig', '100', 'IG-band frequencies'],
        [False, 'wavemaker_freqmin_ig', '0.0', 'IG-band min. freq (Hz)'],
        [False, 'wavemaker_freqmax_ig', '0.1', 'IG-band max. freq (Hz)'],
        [False, 'wavemaker_tinc2ig', '-1.0', 'Tinc to IG ratio'],
        [False, 'wavemaker_surfslope', '-1.0', 'Surf slope'],
        [False, 'wavemaker_hm0_ig_factor', '1.0', 'Hm0 IG factor'],
        [False, 'wavemaker_hm0_inc_factor', '1.0', 'Hm0 incident factor'],
        [False, 'wavemaker_gammax', '1.0', 'Max. breaker index'],
        [False, 'wavemaker_tpmin', '1.0',  'Min. peak period (s)'],
        [False, 'wavemaker_hig', '1',      '1: IG waves'],
        [False, 'wavemaker_hinc', '0',     '1: incident waves'],
    ]),
    ('other', [
    ]),
])
PAR_LIST = list(DEFAULTS.keys())

# alias -> keyword used in this GUI (so a loaded .inp lands on the right row, and duplicates are caught)
ALIASES = {
    'dtmapout': 'dtout', 'precipfile': 'prcfile', 'prcpfile': 'prcfile', 'amrfile': 'amprfile',
    'ampr_block': 'amprblock', 'seffile': 'sefffile', 'global': 'global_model',
    'infiltrationfile': 'inffile', 'infiltration_file': 'inffile',
    'infiltrationtype': 'inftype', 'infiltration_type': 'inftype',
    'regular_output_on_mesh': 'output_on_quadtree_mesh', 'vegetationfile': 'vegfile',
    'vegetationtype_toml': 'vegtype',
    'snapwave_waveforces_factor': 'snapwave_waveforces_ratio', 'waveforces_ratio': 'snapwave_waveforces_ratio',
    'wvmfile': 'wavemaker_wvmfile', 'wfpfile': 'wavemaker_wfpfile', 'whifile': 'wavemaker_whifile',
    'wtifile': 'wavemaker_wtifile', 'wstfile': 'wavemaker_wstfile', 'wmtfilter': 'wavemaker_filter_time',
    'wmfred': 'wavemaker_filter_fred', 'wmsignal': 'wavemaker_signal', 'wmhmin': 'wavemaker_hmin',
    'nfreqsinc': 'wavemaker_nfreqs_inc', 'freqmininc': 'wavemaker_freqmin_inc',
    'freqmaxinc': 'wavemaker_freqmax_inc', 'nfreqsig': 'wavemaker_nfreqs_ig',
    'freqminig': 'wavemaker_freqmin_ig', 'freqmaxig': 'wavemaker_freqmax_ig',
}
# keywords that are NOT valid sfincs.inp input (warned about on Generate)
NOT_READ = {'dtmin': 'computed by SFINCS, not read', 'storeqdrain': 'not a SFINCS keyword',
            'nuviscdim': 'deprecated, no longer used'}

# keyword (lower) -> group, used when sorting a loaded sfincs.inp into tabs
KEY_GROUP = {r[1].lower(): g for g, rows in DEFAULTS.items() if g != 'info' for r in rows}
KEY_DESC = {r[1].lower(): r[3] for g, rows in DEFAULTS.items() if g != 'info' for r in rows}


def _clean(x):
    if x is None:
        return ''
    try:
        if pd.isna(x):
            return ''
    except (TypeError, ValueError):
        pass
    return str(x)


def _copy(data):
    return OrderedDict((g, [list(r) for r in rows]) for g, rows in data.items())


# ---------------------------------------------------------------------------
#  read / write
# ---------------------------------------------------------------------------
def parse_inp(text):
    """Parse sfincs.inp text into the group/rows structure.
    Known keywords go to their tab (in DEFAULTS order), unknown ones to 'other'.
    Keywords from DEFAULTS that are not in the file are kept, switched off."""
    found = OrderedDict()                     # key_lower -> [on, key, val]
    info = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        on = not s.startswith('#')
        body = s.lstrip('#').strip()
        if '=' not in body:
            if not on and body:
                info.append([body, '', ''])     # free comment -> header
            continue
        key, val = body.split('=', 1)
        key, val = key.strip(), val.strip()
        if not key or ' ' in key:
            if not on:
                info.append([body, '', ''])
            continue
        kl = ALIASES.get(key.lower(), key.lower())
        if kl in found and found[kl][0] and not on:
            continue                            # active line wins over a commented duplicate
        found[kl] = [on, key, val]

    data = OrderedDict()
    data['info'] = info or [['', '', '']]
    for g, rows in DEFAULTS.items():
        if g == 'info':
            continue
        out = []
        for _, key, val, com in rows:
            kl = key.lower()
            if kl in found:
                on, k, v = found.pop(kl)
                out.append([on, k, v, com])
            else:
                out.append([False, key, val, com])
        data[g] = out
    for kl, (on, k, v) in found.items():        # unknown keywords
        data['other'].append([on, k, v, ''])
    return data


def read_inp(path):
    for enc in ('utf-8-sig', 'cp950', 'latin-1'):
        try:
            with open(path, encoding=enc) as f:
                return parse_inp(f.read())
        except UnicodeDecodeError:
            continue


def read_xlsx(path):
    """One sheet per group, first row = header (same layout as mdu_prep.xlsx)."""
    xf = pd.ExcelFile(path)
    data = OrderedDict()
    for sht in xf.sheet_names:
        df = pd.read_excel(xf, sheet_name=sht, index_col=None, dtype=object)
        rows = []
        for r in df.itertuples(index=False):
            r = list(r) + [None] * 4
            if sht == 'info':
                rows.append([_clean(x).strip() for x in r[:3]])
            else:
                try:
                    on = float(r[0]) == 1
                except (TypeError, ValueError):
                    on = False
                rows.append([on, _clean(r[1]).strip(), _clean(r[2]).strip(), _clean(r[3]).strip()])
        data[sht] = rows
    return data


def write_xlsx(data, path):
    with pd.ExcelWriter(path, engine='openpyxl') as xw:
        for g, rows in data.items():
            if g == 'info':
                df = pd.DataFrame(rows, columns=['col1', 'col2', 'col3'])
            else:
                df = pd.DataFrame([[1 if on else 0, k, v, c] for on, k, v, c in rows],
                                  columns=['use', 'parameter', 'value', 'description'])
            df.to_excel(xw, sheet_name=g[:31], index=False)


def check_groups(names):
    names = set(names)
    extra = names.difference(PAR_LIST)
    missing = set(PAR_LIST).difference(names)
    if not extra and not missing:
        print('The number of parameter groups is correct.')
    if extra:
        print('Extra parameter group(s) {0} - written as well.'.format(sorted(extra)))
    if missing:
        print('Parameter group(s) {0} missing in the input.'.format(sorted(missing)))


def to_inp_text(data, write_disabled=False, write_info=False):
    """'key = value' lines, keyword padded to KEY_WIDTH (same look as hydromt_sfincs)."""
    lines, seen = [], {}
    if write_info:
        for r in data.get('info', []):
            txt = ' '.join(str(x).strip() for x in r if str(x).strip())
            if txt:
                lines.append('# ' + txt)
    for g, rows in data.items():
        if g == 'info':
            continue
        for on, key, val, _com in rows:
            key = str(key).strip()
            if not key:
                continue
            if not on and not write_disabled:
                continue
            if on and key.lower() in NOT_READ:
                print('WARNING: "{0}" - {1}.'.format(key, NOT_READ[key.lower()]))
            if on:
                key_c = ALIASES.get(key.lower(), key.lower())
                if key_c in seen:
                    print('WARNING: keyword "{0}" active twice (tabs {1} and {2}); SFINCS uses the first.'
                          .format(key, seen[key_c], g))
                seen.setdefault(key_c, g)
            prefix = '' if on else '#'
            lines.append('{0}{1:{w}s} = {2}'.format(prefix, key, str(val).strip(), w=KEY_WIDTH))
    return '\n'.join(lines) + '\n'


def bat_text(inp_name, exe):
    s = ['@echo off',
         'REM generated by sfincsGen',
         'cd /d "%~dp0"']
    if inp_name.lower() != 'sfincs.inp':
        s.append('REM SFINCS always reads sfincs.inp -> copy this variant first')
        s.append('copy /Y "{0}" sfincs.inp'.format(inp_name))
    s += ['set SFINCS_EXE={0}'.format(exe), '"%SFINCS_EXE%"', 'pause']
    return '\r\n'.join(s) + '\r\n'


def name_from_path(path):
    """inp_prep.xlsx -> 'prep', sfincs_half.inp -> 'sfincs_half'."""
    base = os.path.splitext(os.path.basename(path))[0]
    return base[4:] if base.lower().startswith('inp_') else base


# ---------------------------------------------------------------------------
#  checks on the time tab
# ---------------------------------------------------------------------------
def _rows_by_key(data):
    out = {}
    for g, rows in data.items():
        if g == 'info':
            continue
        for r in rows:
            k = str(r[1]).strip().lower()
            k = ALIASES.get(k, k)
            if k and r[0] and k not in out:
                out[k] = r
    return out


def _parse_t(s):
    s = ' '.join(str(s).split())
    try:
        return datetime.strptime(s, TFMT)
    except ValueError:
        raise ValueError('"%s" is not yyyymmdd HHMMSS' % s)


def check_time(data, full_run_dtmaxout=False):
    """Validate tref/tstart/tstop, print run length; optionally dtmaxout = tstop - tstart.
    Returns True if dtmaxout was changed. Raises ValueError on bad input."""
    rk = _rows_by_key(data)
    for k in ('tstart', 'tstop'):
        if k not in rk:
            raise ValueError('[time] %s missing or switched off' % k)
    t0, t1 = (_parse_t(rk[k][2]) for k in ('tstart', 'tstop'))
    rk['tstart'][2], rk['tstop'][2] = t0.strftime(TFMT), t1.strftime(TFMT)
    if 'tref' in rk:
        tref = _parse_t(rk['tref'][2])
        rk['tref'][2] = tref.strftime(TFMT)
    else:
        tref = t0
        print('NOTE: tref not set -> SFINCS uses tref = tstart.')
    if t1 <= t0:
        raise ValueError('tstop (%s) must be after tstart (%s)' % (t1, t0))
    if t0 < tref:
        print('WARNING: tstart is before tref.')
    dur = (t1 - t0).total_seconds()
    print('Run: {0} -> {1}  = {2:g} s ({3:g} h), tstart - tref = {4:g} s'.format(
        t0, t1, dur, dur / 3600., (t0 - tref).total_seconds()))

    for k in ('dtout', 'dthisout', 'dtmaxout'):
        if k in rk and rk[k][0]:
            try:
                v = float(rk[k][2])
            except ValueError:
                print('WARNING: %s = "%s" is not a number' % (k, rk[k][2]))
                continue
            if v > dur:
                print('NOTE: %s = %g s > run length %g s' % (k, v, dur))

    changed = False
    if full_run_dtmaxout:
        new = '%.1f' % dur
        row = next((r for g, rows in data.items() if g != 'info' for r in rows
                    if str(r[1]).strip().lower() == 'dtmaxout'), None)
        if row is not None:
            changed = row[2] != new or not row[0]
            row[0], row[2] = True, new
        else:
            data.setdefault('output', []).append([True, 'dtmaxout', new, KEY_DESC.get('dtmaxout', '')])
            changed = True
        print('dtmaxout = %s (tstop - tstart)' % new)
    return changed


def check_files(data, folder):
    """Warn about active *file entries that are not present in the output folder."""
    n_bad = 0
    for g, rows in data.items():
        if g == 'info':
            continue
        for on, key, val, _ in rows:
            if on and str(key).strip().lower().endswith('file') and str(val).strip():
                p = os.path.join(folder, str(val).strip())
                if not os.path.exists(p):
                    print('WARNING: {0} = {1} not found in {2}'.format(key, val, os.path.abspath(folder)))
                    n_bad += 1
    if not n_bad:
        print('All referenced files exist.')


# =====================================================================
#  tkinter GUI
# =====================================================================
class ScrollFrame(ttk.Frame):
    """Frame with vertical + horizontal scrollbars; put widgets in .inner."""

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        hsb = ttk.Scrollbar(self, orient='horizontal', command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.inner = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.inner, anchor='nw')
        self.inner.bind('<Configure>', self._update_region)
        self.canvas.bind('<Configure>', self._update_region)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.canvas.bind('<Enter>', lambda e: self.canvas.bind_all('<MouseWheel>', self._wheel))
        self.canvas.bind('<Leave>', lambda e: self.canvas.unbind_all('<MouseWheel>'))

    def _update_region(self, _=None):
        w = max(self.inner.winfo_reqwidth(), self.canvas.winfo_width())
        h = max(self.inner.winfo_reqheight(), self.canvas.winfo_height())
        self.canvas.configure(scrollregion=(0, 0, w, h))
        if self.inner.winfo_reqheight() <= self.canvas.winfo_height():
            self.canvas.yview_moveto(0)
        if self.inner.winfo_reqwidth() <= self.canvas.winfo_width():
            self.canvas.xview_moveto(0)

    def _wheel(self, e):
        if self.inner.winfo_reqheight() <= self.canvas.winfo_height():
            return
        self.canvas.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), 'units')


class InpGuiTk:
    W_KEY, W_VAL, W_COM = 22, 40, 70
    W_INFO = [70, 25, 30]

    def __init__(self, notebook, out_dir_var):
        self.nb = notebook
        self.out_dir = out_dir_var
        self.rows = OrderedDict()

    def _browse_file(self, var):
        start = self.out_dir.get().strip() or '.'
        p = filedialog.askopenfilename(initialdir=start)
        if p:
            try:
                rel = os.path.relpath(p, os.path.abspath(start))
            except ValueError:                  # other drive on Windows
                rel = p
            var.set(rel.replace('\\', '/'))

    def _row(self, parent, group, vals, r):
        if group == 'info':
            vals = (list(vals) + ['', '', ''])[:3]
            vs = [tk.StringVar(value=str(v)) for v in vals]
            for c, (v, wd) in enumerate(zip(vs, self.W_INFO)):
                ttk.Entry(parent, textvariable=v, width=wd).grid(row=r, column=c, sticky='ew', padx=1, pady=1)
            return vs
        on, key, val, com = (list(vals) + ['', '', '', ''])[:4]
        vs = [tk.BooleanVar(value=bool(on)), tk.StringVar(value=str(key)),
              tk.StringVar(value=str(val)), tk.StringVar(value=str(com))]
        ttk.Checkbutton(parent, variable=vs[0]).grid(row=r, column=0, padx=(4, 2))
        ttk.Entry(parent, textvariable=vs[1], width=self.W_KEY).grid(row=r, column=1, sticky='ew', padx=1, pady=1)
        ttk.Entry(parent, textvariable=vs[2], width=self.W_VAL).grid(row=r, column=2, sticky='ew', padx=1, pady=1)
        if str(key).strip().lower().endswith('file'):
            ttk.Button(parent, text='...', width=3,
                       command=lambda v=vs[2]: self._browse_file(v)).grid(row=r, column=3, padx=1)
        ttk.Entry(parent, textvariable=vs[3], width=self.W_COM).grid(row=r, column=4, sticky='ew', padx=1, pady=1)
        return vs

    def _page(self, group, rows):
        page = ttk.Frame(self.nb)
        sf = ScrollFrame(page)
        sf.pack(fill='both', expand=True)
        body = sf.inner
        if group == 'info':
            ttk.Label(body, text="Notes; written as '# ...' at the top only if 'Write info header' is ticked",
                      font=('', 9, 'italic')).grid(row=0, column=0, columnspan=3, sticky='w', pady=(4, 2))
        else:
            for c, t in ((0, 'On'), (1, 'Keyword'), (2, 'Value'), (4, 'Description (not written)')):
                ttk.Label(body, text=t, font=('', 9, 'bold')).grid(row=0, column=c, sticky='w', pady=(4, 2))
        self.rows[group] = [self._row(body, group, r, i + 1) for i, r in enumerate(rows)]

        def _add():
            new = ['', '', ''] if group == 'info' else [True, '', '', '']
            self.rows[group].append(self._row(body, group, new, len(self.rows[group]) + 1))
            btn.grid_configure(row=len(self.rows[group]) + 1)
            sf.canvas.update_idletasks()
            sf.canvas.yview_moveto(1.0)

        btn = ttk.Button(body, text='+ add row', command=_add)
        btn.grid(row=len(rows) + 1, column=0, columnspan=2, sticky='w', pady=4)
        return page

    def set_data(self, data, keep_tab=False):
        idx = self.nb.index('current') if (keep_tab and self.nb.tabs()) else 0
        for t in self.nb.tabs():
            self.nb.forget(t)
        self.rows = OrderedDict()
        for g, rows in data.items():
            self.nb.add(self._page(g, rows), text=g)
        if self.nb.tabs():
            self.nb.select(min(idx, len(self.nb.tabs()) - 1))

    def get_data(self):
        return OrderedDict((g, [[v.get() for v in r] for r in rows])
                           for g, rows in self.rows.items())


class App(tk.Tk):
    def __init__(self, source=None, out_dir=None):
        super().__init__()
        self.title('SFINCS - sfincs.inp builder')
        self.geometry('1250x820')
        pad = dict(padx=4, pady=2)

        # ---- top: load / save ----
        top = ttk.Frame(self)
        top.pack(fill='x', **pad)
        self.src_path = tk.StringVar(value=source or DEFAULT_XLSX)
        self.save_path = tk.StringVar(value='inp_custom.xlsx')
        ttk.Label(top, text='Load from').grid(row=0, column=0, sticky='w')
        ttk.Entry(top, textvariable=self.src_path, width=70).grid(row=0, column=1, sticky='ew', **pad)
        ttk.Button(top, text='...', width=3, command=self.browse_src).grid(row=0, column=2)
        ttk.Button(top, text='Load', command=self.on_load).grid(row=0, column=3, **pad)
        ttk.Button(top, text='Load .inp...', command=self.on_load_inp).grid(row=0, column=4, **pad)
        ttk.Button(top, text='Built-in defaults', command=self.on_reset).grid(row=0, column=5, **pad)
        ttk.Label(top, text='Save as').grid(row=1, column=0, sticky='w')
        ttk.Entry(top, textvariable=self.save_path, width=70).grid(row=1, column=1, sticky='ew', **pad)
        ttk.Button(top, text='...', width=3, command=self.browse_save).grid(row=1, column=2)
        ttk.Button(top, text='Save xlsx', command=self.on_save).grid(row=1, column=3, **pad)
        top.columnconfigure(1, weight=1)

        # ---- output vars (needed by the tabs' file browsers) ----
        self.out_dir = tk.StringVar(value=out_dir or '.')
        self.out_name = tk.StringVar(value=DEFAULT_NAME)
        self.exe = tk.StringVar(value=EXE_DEFAULT)
        self.write_bat = tk.BooleanVar(value=True)
        self.write_disabled = tk.BooleanVar(value=False)
        self.write_info = tk.BooleanVar(value=False)
        self.full_dtmax = tk.BooleanVar(value=True)

        # ---- middle: tabs ----
        pw = ttk.PanedWindow(self, orient='vertical')
        pw.pack(fill='both', expand=True, **pad)
        nb = ttk.Notebook(pw)
        self.gui = InpGuiTk(nb, self.out_dir)
        pw.add(nb, weight=4)

        # ---- output options + log ----
        bottom = ttk.Frame(pw)
        pw.add(bottom, weight=1)
        opt = ttk.LabelFrame(bottom, text='Output')
        opt.pack(fill='x')
        ttk.Label(opt, text='Output dir').grid(row=0, column=0, sticky='w', **pad)
        ttk.Entry(opt, textvariable=self.out_dir, width=55).grid(row=0, column=1, sticky='ew', **pad)
        ttk.Button(opt, text='...', width=3, command=self.browse_dir).grid(row=0, column=2)
        ttk.Label(opt, text='INP name').grid(row=0, column=3, sticky='w', **pad)
        ttk.Entry(opt, textvariable=self.out_name, width=30).grid(row=0, column=4, sticky='w', **pad)
        ttk.Label(opt, text='(.inp added)').grid(row=0, column=5, sticky='w')
        ttk.Label(opt, text='Executable').grid(row=1, column=0, sticky='w', **pad)
        ttk.Entry(opt, textvariable=self.exe, width=55).grid(row=1, column=1, sticky='ew', **pad)
        ttk.Button(opt, text='...', width=3, command=self.browse_exe).grid(row=1, column=2)
        ttk.Checkbutton(opt, text='Also write run_<name>.bat', variable=self.write_bat).grid(
            row=1, column=3, columnspan=3, sticky='w', **pad)
        chk = ttk.Frame(opt)
        chk.grid(row=2, column=0, columnspan=6, sticky='w', **pad)
        ttk.Checkbutton(chk, text='dtmaxout = full run (tstop - tstart)',
                        variable=self.full_dtmax).pack(side='left', padx=(0, 12))
        ttk.Checkbutton(chk, text='Write disabled lines as #comments',
                        variable=self.write_disabled).pack(side='left', padx=(0, 12))
        ttk.Checkbutton(chk, text='Write info header', variable=self.write_info).pack(side='left')
        btns = ttk.Frame(opt)
        btns.grid(row=3, column=0, columnspan=6, sticky='w', **pad)
        ttk.Button(btns, text='Preview', command=self.on_preview).pack(side='left', padx=(0, 6))
        ttk.Button(btns, text='Check files', command=self.on_check_files).pack(side='left', padx=(0, 6))
        ttk.Button(btns, text='Generate .inp', command=self.on_generate).pack(side='left')
        opt.columnconfigure(1, weight=1)

        self.log = ScrolledText(bottom, height=10, font=('Consolas', 9), wrap='none')
        self.log.pack(fill='both', expand=True, pady=(4, 0))

        # ---- initial values ----
        if source:
            self.on_load()
            if self.gui.rows:                   # loaded
                if out_dir:
                    self.out_dir.set(out_dir)
                return
        with self.logging(clear=not source):
            if not source and os.path.exists(DEFAULT_XLSX):
                try:
                    data, name = read_xlsx(DEFAULT_XLSX), name_from_path(DEFAULT_XLSX)
                    print('Loaded defaults from ' + os.path.abspath(DEFAULT_XLSX))
                except Exception as e:
                    print('Could not read', DEFAULT_XLSX, '->', e, '- using built-in defaults.')
                    data, name = _copy(DEFAULTS), DEFAULT_NAME
            elif source:
                data, name = _copy(DEFAULTS), DEFAULT_NAME
                print('Using built-in defaults.')
            else:
                data, name = _copy(DEFAULTS), DEFAULT_NAME
                print(DEFAULT_XLSX + ' not found - using built-in defaults.')
            self.gui.set_data(data)
            self.out_name.set(name)
            check_groups(self.gui.rows.keys())

    @contextlib.contextmanager
    def logging(self, clear=True):
        if clear:
            self.log.delete('1.0', 'end')
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                yield
        except Exception as e:
            buf.write('ERROR: %s\n' % e)
        finally:
            self.log.insert('end', buf.getvalue())
            self.log.see('end' if not clear else '1.0')

    # ---- dialogs ----
    def browse_src(self):
        p = filedialog.askopenfilename(filetypes=[('xlsx / inp', ('*.xlsx', '*.inp')), ('Excel', '*.xlsx'),
                                                  ('SFINCS inp', '*.inp'), ('All files', '*.*')])
        if p:
            self.src_path.set(p)

    def browse_save(self):
        p = filedialog.asksaveasfilename(defaultextension='.xlsx', filetypes=[('Excel', '*.xlsx')])
        if p:
            self.save_path.set(p)

    def browse_dir(self):
        p = filedialog.askdirectory()
        if p:
            self.out_dir.set(p)

    def browse_exe(self):
        p = filedialog.askopenfilename(filetypes=[('Executable', '*.exe'), ('All files', '*.*')])
        if p:
            self.exe.set(p)

    # ---- actions ----
    def on_load(self):
        with self.logging():
            p = self.src_path.get().strip()
            try:
                data = read_inp(p) if not p.lower().endswith(('.xlsx', '.xlsm', '.xls')) else read_xlsx(p)
            except Exception as e:
                print('Could not load', p, '->', e)
                return
            self.gui.set_data(data)
            self.out_name.set(name_from_path(p))
            if not p.lower().endswith(('.xlsx', '.xlsm', '.xls')):
                self.out_dir.set(os.path.dirname(os.path.abspath(p)))
            print('Loaded', os.path.abspath(p))
            if data.get('other'):
                print('Unknown keywords put in tab "other":', ', '.join(r[1] for r in data['other']))
            check_groups(data.keys())

    def on_load_inp(self):
        p = filedialog.askopenfilename(title='Load sfincs.inp',
                                       filetypes=[('SFINCS inp', '*.inp'), ('All files', '*.*')])
        if p:
            self.src_path.set(p)
            self.on_load()

    def on_reset(self):
        with self.logging():
            self.gui.set_data(_copy(DEFAULTS))
            self.out_name.set(DEFAULT_NAME)
            print('Reset to built-in defaults.')

    def on_save(self):
        with self.logging():
            p = self.save_path.get().strip()
            try:
                write_xlsx(self.gui.get_data(), p)
                print('Saved', os.path.abspath(p))
            except Exception as e:
                print('Could not save ->', e)

    def _prepare(self):
        """Read tabs, run time checks; returns data (tabs refreshed if values changed)."""
        data = self.gui.get_data()
        check_time(data, self.full_dtmax.get())
        self.gui.set_data(data, keep_tab=True)
        return data

    def on_preview(self):
        with self.logging():
            try:
                data = self._prepare()
            except ValueError as e:
                print('WARNING: time check failed ->', e)
                data = self.gui.get_data()
            print('-' * 60)
            print(to_inp_text(data, self.write_disabled.get(), self.write_info.get()))

    def on_check_files(self):
        with self.logging():
            check_files(self.gui.get_data(), self.out_dir.get().strip() or '.')

    def on_generate(self):
        with self.logging():
            name = self.out_name.get().strip() or DEFAULT_NAME
            if name.lower().endswith('.inp'):
                name = name[:-4]
            d = self.out_dir.get().strip() or '.'
            try:
                data = self._prepare()
            except ValueError as e:
                print('ERROR:', e)
                print('Nothing written. Fix the [time] tab and try again.')
                messagebox.showerror('sfincsGen', 'Time check failed:\n%s' % e)
                return
            os.makedirs(d, exist_ok=True)
            inp_file = os.path.join(d, name + '.inp')
            if os.path.exists(inp_file) and not messagebox.askyesno(
                    'sfincsGen', '%s exists.\nOverwrite?' % os.path.abspath(inp_file)):
                print('Cancelled - nothing written.')
                return
            with open(inp_file, 'wt', encoding='utf-8', newline='\n') as f:
                f.write(to_inp_text(data, self.write_disabled.get(), self.write_info.get()))
            print('Writing input file done ->', os.path.abspath(inp_file))
            if self.write_bat.get():
                bat_file = os.path.join(d, 'run.bat' if name.lower() == 'sfincs' else 'run_' + name + '.bat')
                if os.path.exists(bat_file) and not messagebox.askyesno(
                        'sfincsGen', '%s exists.\nOverwrite?' % os.path.abspath(bat_file)):
                    print('Run script kept as is.')
                    check_files(data, d)
                    return
                with open(bat_file, 'wt', encoding='utf-8', newline='') as f:
                    f.write(bat_text(name + '.inp', self.exe.get().strip()))
                print('Run script ->', os.path.abspath(bat_file))
            check_files(data, d)


def build_parser():
    ap = argparse.ArgumentParser(prog='sfgen', description='Build a sfincs.inp in a desktop (tkinter) GUI.')
    ap.add_argument('source', nargs='?',
                    help='.xlsx or .inp to load at start, or a model folder with sfincs.inp '
                         '(default: %s in the current folder, else built-in defaults)' % DEFAULT_XLSX)
    ap.add_argument('--out-dir', metavar='DIR',
                    help='output folder for the .inp / .bat (default: folder of an .inp source, else current folder)')
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    source = args.source
    if source and os.path.isdir(source):
        source = os.path.join(source, 'sfincs.inp')
    if source and not os.path.exists(source):
        sys.exit('not found: %s' % source)
    App(source, args.out_dir).mainloop()


if __name__ == '__main__':
    main()
