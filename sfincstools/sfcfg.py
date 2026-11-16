"""
Display the configuration of a SFINCS model.

  sfcfg [MODEL_DIR] [--plot] [--save FILE.png]

  MODEL_DIR   folder with sfincs.inp (default: current folder)
  --plot      also show a map (bed level, mask, boundary, drainage, weirs, obs)
              and the forcing time series
  --save      write the figure to a file instead of opening a window

Reports
- sfincs.inp, grouped by topic, with derived values (grid extent, duration, ...)
- every referenced input file: present / missing, size
- a short summary of each file: active cells, boundary points, water-level
  forcing range, pumps/culverts, weirs, discharge points, NetCDF forcing
  (variables, time range, totals), subgrid table, infiltration
"""
import os, sys, argparse
from datetime import datetime, timedelta

import numpy as np

os.environ.setdefault('HDF5_USE_FILE_LOCKING', 'FALSE')

_trapz = getattr(np, 'trapezoid', None) or np.trapz   # np.trapz was renamed in NumPy 2.0

# --------------------------------------------------------------------------- #
# sfincs.inp keywords grouped by topic (anything not listed ends up in "Other")
GROUPS = [
    ('Grid', ['mmax', 'nmax', 'dx', 'dy', 'x0', 'y0', 'rotation', 'epsg', 'crsgeo',
              'latitude', 'qtrfile']),
    ('Time', ['tref', 'tstart', 'tstop', 'tspinup', 'dtmax', 'dtmin', 'dtout', 'dthisout',
              'dtmaxout', 'dtrstout', 'trstout', 'dtwnd', 't0out', 't1out']),
    ('Numerics', ['alpha', 'theta', 'huthresh', 'advection', 'viscosity', 'nuvisc',
                  'btfilter', 'stopdepth', 'baro', 'coriolis', 'slopelim', 'uvlim',
                  'nonh', 'wiggle_suppression', 'dtmin']),
    ('Physics', ['rgh_lev_land', 'manning', 'manning_land', 'manning_sea', 'zsini',
                 'rhoa', 'rhow', 'pavbnd', 'gapres', 'cdnrb', 'cdwnd', 'cdval',
                 'qinf', 'storecumprcp', 'utmzone']),
    ('Output', ['inputformat', 'outputformat', 'storevel', 'storevelmax', 'storetwet',
                'storehsubgrid', 'storeqdrain', 'storezvolume', 'storemeteo',
                'storemaxwind', 'storefw', 'storewavdir', 'outputtype_map', 'outputtype_his']),
]

# descriptions of the file keywords
FILEKEYS = {
    'depfile': 'bed level (regular grid)',
    'mskfile': 'active-cell mask',
    'indexfile': 'active-cell index',
    'sbgfile': 'subgrid tables',
    'manningfile': 'Manning roughness',
    'qinffile': 'constant infiltration',
    'scsfile': 'SCS curve number',
    'smaxfile': 'SCS max. storage',
    'sefffile': 'SCS effective storage',
    'f0file': 'Horton f0', 'fcfile': 'Horton fc', 'kdfile': 'Horton kd',
    'ksfile': 'Green-Ampt ks', 'psifile': 'Green-Ampt psi', 'sigmafile': 'Green-Ampt sigma',
    'bndfile': 'water-level boundary points',
    'bzsfile': 'water-level boundary time series',
    'bzifile': 'infragravity boundary time series',
    'bwvfile': 'wave boundary points',
    'srcfile': 'discharge points',
    'disfile': 'discharge time series',
    'drnfile': 'drainage structures (pumps / culverts)',
    'weirfile': 'weirs / levees',
    'thdfile': 'thin dams',
    'obsfile': 'observation points',
    'crsfile': 'cross sections',
    'precfile': 'precipitation time series (uniform)',
    'amprfile': 'precipitation (ascii grid)',
    'netamprfile': 'precipitation (NetCDF grid)',
    'netampfile': 'air pressure (NetCDF grid)',
    'netamuamvfile': 'wind (NetCDF grid)',
    'netbndbzsbzifile': 'water-level boundary (NetCDF)',
    'netsrcdisfile': 'discharges (NetCDF)',
    'spwfile': 'spiderweb (cyclone) wind',
    'wndfile': 'wind time series (uniform)',
    'amufile': 'wind u (ascii grid)', 'amvfile': 'wind v (ascii grid)',
    'ampfile': 'air pressure (ascii grid)',
    'rstfile': 'restart file',
    'inifile': 'initial water level',
    'ncinifile': 'initial conditions (NetCDF)',
    'wfpfile': 'wave forcing points', 'whifile': 'wave height', 'wtifile': 'wave period',
    'wstfile': 'wave set-up',
    'qtrfile': 'quadtree grid',
}

INT_KEYS = {'mmax', 'nmax', 'epsg', 'advection', 'viscosity', 'baro', 'pavbnd', 'crsgeo',
            'cdnrb', 'storecumprcp', 'rotation'}


# --------------------------------------------------------------------------- #
def read_inp(model_dir):
    inp = {}
    with open(os.path.join(model_dir, 'sfincs.inp')) as f:
        for line in f:
            line = line.split('!')[0]
            if '=' in line:
                k, v = line.split('=', 1)
                inp[k.strip().lower()] = v.strip()
    return inp


def fnum(inp, key, default=None):
    try:
        return float(inp[key].split()[0])
    except (KeyError, ValueError, IndexError):
        return default


def ptime(s):
    try:
        return datetime.strptime(s.strip(), '%Y%m%d %H%M%S')
    except Exception:
        return None


def human_size(n):
    for unit in ('B', 'kB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024


def human_dur(seconds):
    """3725 -> '1 h 2 min 5 s', 259200 -> '3 d'"""
    seconds = float(seconds)
    sign, s = ('-' if seconds < 0 else ''), abs(seconds)
    parts = []
    for unit, size in (('d', 86400), ('h', 3600), ('min', 60)):
        q, s = divmod(s, size)
        if q:
            parts.append(f'{int(q)} {unit}')
    if s or not parts:
        parts.append(f'{s:g} s')
    return sign + ' '.join(parts)


def human_time(t):
    return f'{t:%Y-%m-%d %H:%M:%S} ({t:%a})'


def header(title):
    print()
    print(title)
    print('-' * len(title))


def row(key, val, note=''):
    note = f'   # {note}' if note else ''
    print(f'  {key:<18} {val}{note}')


# --------------------------------------------------------------------------- #
# grid helpers
def grid_info(inp):
    mmax, nmax = int(fnum(inp, 'mmax', 0)), int(fnum(inp, 'nmax', 0))
    dx, dy = fnum(inp, 'dx', 0), fnum(inp, 'dy', 0)
    x0, y0 = fnum(inp, 'x0', 0), fnum(inp, 'y0', 0)
    rot = np.deg2rad(fnum(inp, 'rotation', 0))
    return mmax, nmax, dx, dy, x0, y0, rot


def cell_xy(inp, m, n):
    """cell-centre coordinates for 0-based column m and row n"""
    mmax, nmax, dx, dy, x0, y0, rot = grid_info(inp)
    xl, yl = (m + 0.5) * dx, (n + 0.5) * dy
    return x0 + xl * np.cos(rot) - yl * np.sin(rot), y0 + xl * np.sin(rot) + yl * np.cos(rot)


def grid_corners(inp):
    mmax, nmax, dx, dy, x0, y0, rot = grid_info(inp)
    L, W = mmax * dx, nmax * dy
    pts = np.array([[0, 0], [L, 0], [L, W], [0, W], [0, 0]], float)
    x = x0 + pts[:, 0] * np.cos(rot) - pts[:, 1] * np.sin(rot)
    y = y0 + pts[:, 0] * np.sin(rot) + pts[:, 1] * np.cos(rot)
    return x, y


def read_index(model_dir, inp):
    """0-based linear indices (column-major: n fastest) of the active cells, or None"""
    f = os.path.join(model_dir, inp.get('indexfile', 'sfincs.ind'))
    if not os.path.exists(f) or inp.get('inputformat', 'bin') != 'bin':
        return None
    raw = np.fromfile(f, dtype=np.int32)
    return raw[1:1 + raw[0]] - 1


def active_to_grid(inp, ind, values, fill=np.nan):
    """scatter values on active cells back to an (nmax, mmax) array"""
    mmax, nmax = grid_info(inp)[:2]
    a = np.full(mmax * nmax, fill, dtype=float)
    a[ind] = values
    return a.reshape(mmax, nmax).T


def read_active_bin(model_dir, inp, key, dtype):
    if key not in inp:
        return None
    f = os.path.join(model_dir, inp[key])
    if not os.path.exists(f):
        return None
    return np.fromfile(f, dtype=dtype)


# --------------------------------------------------------------------------- #
# readers for the ascii input files
def read_xy(path):
    pts = []
    with open(path) as f:
        for line in f:
            p = line.split()
            if len(p) >= 2:
                try:
                    pts.append((float(p[0]), float(p[1]), ' '.join(p[2:])))
                except ValueError:
                    pass
    return pts


def read_timeseries(path):
    a = np.loadtxt(path, ndmin=2)
    return a[:, 0], a[:, 1:]


def read_drn(path):
    rows = []
    with open(path) as f:
        for line in f:
            p = line.split()
            if len(p) >= 6:
                rows.append([float(v) for v in p[:6]])
    return np.array(rows).reshape(-1, 6)


def read_polylines(path, ncol_min=2):
    """tekal-style blocks: name / nrows ncols / rows"""
    lines, out = open(path).read().splitlines(), []
    i = 0
    while i < len(lines):
        name = lines[i].strip()
        if not name:
            i += 1
            continue
        nr, nc = (int(v) for v in lines[i + 1].split()[:2])
        data = np.array([[float(v) for v in lines[i + 2 + k].split()[:nc]] for k in range(nr)])
        out.append((name, data))
        i += 2 + nr
    return out


def nc_summary(path, tref=None):
    import netCDF4 as nc
    with nc.Dataset(path) as d:
        dims = ', '.join(f'{k}={len(v)}' for k, v in d.dimensions.items())
        print(f'      dims : {dims}')
        tinfo = None
        if 'time' in d.variables and len(d['time']) > 0:
            t = d['time']
            units = getattr(t, 'units', None)
            if units:
                try:
                    t0 = nc.num2date(t[0], units, only_use_cftime_datetimes=False)
                    t1 = nc.num2date(t[-1], units, only_use_cftime_datetimes=False)
                    dt = (t[1] - t[0]) if len(t) > 1 else 0
                    print(f'      time : {t0:%Y-%m-%d %H:%M} -> {t1:%Y-%m-%d %H:%M} '
                          f'({len(t)} steps, step {dt:g} {units.split()[0]})')
                    tinfo = (t0, t1)
                except Exception:
                    print(f'      time : {len(t)} steps ({units})')
        for name, v in d.variables.items():
            if name in d.dimensions or v.ndim == 0:
                continue
            units = getattr(v, 'units', '')
            line = f'      var  : {name}{list(v.dimensions)} {units}'.rstrip()
            if v.size <= 5e7 and np.issubdtype(v.dtype, np.number):
                a = np.asarray(v[:], dtype=float)
                if np.isfinite(a).any():
                    line += f'  min {np.nanmin(a):.4g}  mean {np.nanmean(a):.4g}  max {np.nanmax(a):.4g}'
            print(line)
        return tinfo


# --------------------------------------------------------------------------- #
TIME_LABELS = {
    'tref': 'reference time', 'tstart': 'start', 'tstop': 'stop',
    'tspinup': 'spin-up', 'dtmax': 'max. time step', 'dtmin': 'min. time step',
    'dtout': 'map output every', 'dthisout': 'his output every',
    'dtmaxout': 'max. map every', 'dtrstout': 'restart every', 'trstout': 'restart at',
    'dtwnd': 'meteo update every', 't0out': 'output from', 't1out': 'output until',
}


def show_time(inp, keys):
    """Time section in human-readable form; raw sfincs.inp value at the end of each line"""
    tr, t0, t1 = (ptime(inp.get(k, '')) for k in ('tref', 'tstart', 'tstop'))
    dur = (t1 - t0).total_seconds() if t0 and t1 else None

    def line(k, text):
        print(f'  {k:<10} {TIME_LABELS.get(k, ""):<20} {text:<44} [{inp[k]}]')

    for k in keys:
        if k in ('tref', 'tstart', 'tstop', 't0out', 't1out'):
            t = ptime(inp[k])
            if t is None:
                line(k, inp[k])
                continue
            text = human_time(t)
            if tr and k != 'tref':
                off = (t - tr).total_seconds()
                text += f'  = tref + {human_dur(off)}' if off else '  = tref'
            line(k, text)
            if k == 'tstop' and dur is not None:
                print(f'  {"":<10} {"-> run length":<20} {human_dur(dur)} ({dur / 3600:g} h)')
        elif k == 'trstout':
            v = fnum(inp, k, -999)
            line(k, 'off' if v < 0 else f'tref + {human_dur(v)}'
                 + (f'  = {human_time(tr + timedelta(seconds=v))}' if tr else ''))
        else:
            v = fnum(inp, k, 0)
            if v <= 0:
                line(k, 'off')
                continue
            text = human_dur(v)
            if dur and k in ('dtout', 'dthisout', 'dtmaxout', 'dtrstout'):
                n = int(dur // v) + (1 if k in ('dtout', 'dthisout') else 0)
                what = {'dtout': 'map frames', 'dthisout': 'his records',
                        'dtmaxout': 'max. map(s)', 'dtrstout': 'restart file(s)'}[k]
                text += f'  -> {n} {what}'
            line(k, text)


def show_inp(inp):
    used = set()
    for title, keys in GROUPS:
        present = [k for k in keys if k in inp and k not in used]
        if not present:
            continue
        header(title)
        if title == 'Time':
            show_time(inp, present)
            used.update(present)
            continue
        for k in present:
            used.add(k)
            note = ''
            if k == 'epsg':
                note = {'3826': 'TWD97 / TM2 zone 121', '4326': 'WGS 84', '3857': 'Web Mercator'}.get(inp[k], '')
            if k == 'advection':
                note = {'0': 'off', '1': '1D', '2': '2D'}.get(inp[k], '')
            if k == 'inputformat':
                note = 'binary msk/ind/dep' if inp[k] == 'bin' else 'ascii'
            if k == 'outputformat':
                note = {'net': 'NetCDF', 'bin': 'binary', 'asc': 'ascii'}.get(inp[k], '')
            row(k, inp[k], note)

        if title == 'Grid':
            mmax, nmax, dx, dy, x0, y0, rot = grid_info(inp)
            if mmax and nmax:
                xs, ys = grid_corners(inp)
                print(f'  {"-> cells":<18} {mmax} x {nmax} = {mmax * nmax:,}')
                print(f'  {"-> size":<18} {mmax * dx / 1000:.2f} km x {nmax * dy / 1000:.2f} km')
                print(f'  {"-> extent x":<18} {xs.min():.1f} .. {xs.max():.1f}')
                print(f'  {"-> extent y":<18} {ys.min():.1f} .. {ys.max():.1f}')

    other = [k for k in inp if k not in used and not k.endswith('file')]
    if other:
        header('Other')
        for k in other:
            row(k, inp[k])


def show_files(model_dir, inp):
    header('Input files')
    keys = [k for k in inp if k.endswith('file')]
    for k in keys:
        f = os.path.join(model_dir, inp[k])
        status = human_size(os.path.getsize(f)) if os.path.exists(f) else 'MISSING'
        print(f'  {k:<16} {inp[k]:<28} {status:>10}   {FILEKEYS.get(k, "")}')
    if not keys:
        print('  (none)')


def show_details(model_dir, inp, data):
    header('File contents')
    p = lambda k: os.path.join(model_dir, inp[k]) if k in inp and os.path.exists(os.path.join(model_dir, inp[k])) else None
    mmax, nmax = grid_info(inp)[:2]

    # mask / index
    ind = read_index(model_dir, inp)
    msk = read_active_bin(model_dir, inp, 'mskfile', np.int8)
    if ind is not None:
        data['ind'] = ind
        print(f'  active cells      : {len(ind):,} of {mmax * nmax:,} ({100 * len(ind) / (mmax * nmax):.1f} %)')
        if msk is not None and len(msk) == len(ind):
            data['msk'] = msk
            names = {1: 'active', 2: 'water-level bnd', 3: 'outflow bnd', 5: 'wave bnd'}
            u, c = np.unique(msk, return_counts=True)
            print('  mask values       : ' + ', '.join(f'{names.get(int(a), a)} ({a}) = {b:,}' for a, b in zip(u, c)))

    # subgrid
    if p('sbgfile'):
        try:
            import netCDF4 as nc
            with nc.Dataset(p('sbgfile')) as d:
                zmin = d['z_zmin'][:].astype(float)
                zmax = d['z_zmax'][:].astype(float)
                nl = len(d.dimensions['levels']) if 'levels' in d.dimensions else '?'
                print(f'  subgrid           : {len(zmin):,} cells, {nl} levels, '
                      f'zmin {np.nanmin(zmin):.2f} .. {np.nanmax(zmin):.2f} m, '
                      f'zmax {np.nanmin(zmax):.2f} .. {np.nanmax(zmax):.2f} m')
                data['zb'] = zmin
        except Exception as e:
            print(f'  subgrid           : could not read ({e})')
    elif p('depfile') and ind is not None:
        dep = np.fromfile(p('depfile'), dtype=np.float32)
        print(f'  bed level         : {np.nanmin(dep):.2f} .. {np.nanmax(dep):.2f} m')
        data['zb'] = dep

    # infiltration
    if p('qinffile'):
        q = np.fromfile(p('qinffile'), dtype=np.float32)
        print(f'  infiltration      : {q.min():.3g} .. {q.max():.3g} mm/h '
              f'(mean {q.mean():.3g}, {np.count_nonzero(q):,} cells > 0)')
    elif 'qinf' in inp:
        print(f'  infiltration      : uniform {inp["qinf"]} mm/h')

    # roughness
    if p('manningfile'):
        n = np.fromfile(p('manningfile'), dtype=np.float32)
        print(f'  manning           : {n.min():.3g} .. {n.max():.3g}')

    # boundary
    if p('bndfile'):
        bnd = read_xy(p('bndfile'))
        data['bnd'] = np.array([b[:2] for b in bnd])
        print(f'  boundary points   : {len(bnd)}')
    if p('bzsfile'):
        t, v = read_timeseries(p('bzsfile'))
        data['bzs'] = (t, v)
        print(f'  bzs time series   : {len(t)} times, t = {t[0]:g} .. {t[-1]:g} s, '
              f'{v.shape[1]} points, zs {v.min():.2f} .. {v.max():.2f} m')
        if 'bnd' in data and v.shape[1] != len(data['bnd']):
            print(f'  !! bzs has {v.shape[1]} columns but bnd has {len(data["bnd"])} points')

    # discharges
    if p('srcfile'):
        src = read_xy(p('srcfile'))
        data['src'] = np.array([s[:2] for s in src])
        print(f'  discharge points  : {len(src)}')
    if p('disfile'):
        t, v = read_timeseries(p('disfile'))
        data['dis'] = (t, v)
        print(f'  dis time series   : {len(t)} times, {v.shape[1]} points, '
              f'Q {v.min():.2f} .. {v.max():.2f} m3/s')

    # drainage structures
    if p('drnfile'):
        d = read_drn(p('drnfile'))
        data['drn'] = d
        kinds = {1: 'pump', 2: 'culvert', 3: 'check-valve culvert'}
        print(f'  drainage struct.  : {len(d)}')
        for typ in np.unique(d[:, 4]).astype(int):
            sel = d[d[:, 4] == typ]
            print(f'      {kinds.get(typ, f"type {typ}"):<10}: {len(sel):3d}, '
                  f'capacity {sel[:, 5].min():g} .. {sel[:, 5].max():g} m3/s, total {sel[:, 5].sum():g} m3/s')

    # weirs / thin dams
    for key, label in (('weirfile', 'weirs'), ('thdfile', 'thin dams')):
        if p(key):
            try:
                lines = read_polylines(p(key))
                data[key] = lines
                npts = sum(len(l[1]) for l in lines)
                length = sum(np.hypot(*np.diff(l[1][:, :2], axis=0).T).sum() for l in lines)
                msg = f'  {label:<18}: {len(lines)} polylines, {npts} points, {length / 1000:.2f} km'
                if key == 'weirfile' and lines and lines[0][1].shape[1] >= 3:
                    z = np.concatenate([l[1][:, 2] for l in lines])
                    msg += f', crest {z.min():.2f} .. {z.max():.2f} m'
                print(msg)
            except Exception as e:
                print(f'  {label:<18}: could not read ({e})')

    # observation points
    if p('obsfile'):
        obs = read_xy(p('obsfile'))
        data['obs'] = obs
        names = ', '.join(o[2].strip('"\'') or f'#{i + 1}' for i, o in enumerate(obs[:8]))
        print(f'  observation pts   : {len(obs)}  ({names}{" ..." if len(obs) > 8 else ""})')

    # uniform precipitation
    if p('precfile'):
        t, v = read_timeseries(p('precfile'))
        data['prec'] = (t, v[:, 0])
        total = _trapz(v[:, 0], t) / 3600
        print(f'  precipitation     : {len(t)} times, max {v.max():.2f} mm/h, total ~{total:.1f} mm')

    # NetCDF forcing
    t0, t1 = ptime(inp.get('tstart', '')), ptime(inp.get('tstop', ''))
    for key in [k for k in inp if k.startswith('net') and k.endswith('file')]:
        if p(key):
            print(f'  {key} ({inp[key]}):')
            try:
                tinfo = nc_summary(p(key))
                if tinfo and t0 and t1:
                    a, b = tinfo
                    a = datetime(a.year, a.month, a.day, a.hour, a.minute)
                    b = datetime(b.year, b.month, b.day, b.hour, b.minute)
                    if a > t0 or b < t1:
                        print(f'      !! forcing does not cover tstart..tstop ({t0} .. {t1})')
                if key == 'netamprfile':
                    data['netampr'] = p(key)
            except Exception as e:
                print(f'      could not read ({e})')


# --------------------------------------------------------------------------- #
def plot(model_dir, inp, data, save=None):
    import matplotlib.pyplot as plt

    series = [k for k in ('bzs', 'dis', 'prec', 'netampr') if k in data]
    fig = plt.figure(figsize=(14, 8))
    ax = fig.add_axes([0.05, 0.08, 0.55 if series else 0.9, 0.85])

    if 'ind' in data:
        ind = data['ind']
        if 'zb' in data and len(data['zb']) == len(ind):
            z = active_to_grid(inp, ind, data['zb'])
            label, cmap = 'bed level zmin (m)', 'terrain'
        else:
            z = active_to_grid(inp, ind, data.get('msk', np.ones(len(ind))))
            label, cmap = 'mask', 'viridis'
        mmax, nmax, dx, dy, x0, y0, rot = grid_info(inp)
        mm, nn = np.meshgrid(np.arange(mmax), np.arange(nmax))
        X, Y = cell_xy(inp, mm, nn)
        pc = ax.pcolormesh(X, Y, z, cmap=cmap, shading='nearest')
        fig.colorbar(pc, ax=ax, shrink=0.7, label=label)
        if 'msk' in data:
            bndcells = data['msk'] > 1
            if bndcells.any():
                n, m = ind[bndcells] % nmax, ind[bndcells] // nmax
                bx, by = cell_xy(inp, m, n)
                ax.plot(bx, by, 's', ms=1.5, color='tab:blue', label='mask bnd cells')

    xs, ys = grid_corners(inp)
    ax.plot(xs, ys, 'k-', lw=0.8, label='grid')
    if 'bnd' in data:
        ax.plot(*data['bnd'].T, 'o', color='navy', ms=5, label='bnd points')
    if 'src' in data:
        ax.plot(*data['src'].T, 'v', color='cyan', mec='k', ms=6, label='discharge')
    if 'drn' in data:
        d = data['drn']
        for r in d:
            ax.annotate('', xy=r[2:4], xytext=r[0:2],
                        arrowprops=dict(arrowstyle='->', color='red', lw=1.2))
        ax.plot(d[:, 0], d[:, 1], '.', color='red', ms=4, label='drainage (sink -> source)')
    for key, col, lab in (('weirfile', 'magenta', 'weir'), ('thdfile', 'k', 'thin dam')):
        for i, (name, a) in enumerate(data.get(key, [])):
            ax.plot(a[:, 0], a[:, 1], '-', color=col, lw=1.5, label=lab if i == 0 else None)
    for i, o in enumerate(data.get('obs', [])):
        ax.plot(o[0], o[1], '^', color='orange', mec='k', ms=7, label='obs' if i == 0 else None)
        ax.annotate(o[2].strip('"\''), (o[0], o[1]), fontsize=7, xytext=(3, 3), textcoords='offset points')

    ax.set_aspect('equal')
    ax.set_title(f'SFINCS model: {os.path.basename(os.path.abspath(model_dir))}  (EPSG:{inp.get("epsg", "?")})')
    ax.legend(loc='upper left', fontsize=8)
    ax.ticklabel_format(useOffset=False, style='plain')

    # forcing panels
    if series:
        h = 0.85 / len(series)
        tr = ptime(inp.get('tref', ''))
        t0, t1 = ptime(inp.get('tstart', '')), ptime(inp.get('tstop', ''))
        for i, k in enumerate(series):
            a = fig.add_axes([0.68, 0.08 + (len(series) - 1 - i) * h + 0.04, 0.3, h - 0.08])
            if k in ('bzs', 'dis', 'prec'):
                t, v = data[k]
                tt = [tr + timedelta(seconds=float(s)) for s in t] if tr else t
                a.plot(tt, v)
                a.set_ylabel({'bzs': 'zs (m)', 'dis': 'Q (m3/s)', 'prec': 'P (mm/h)'}[k])
            else:
                import netCDF4 as nc
                with nc.Dataset(data[k]) as d:
                    var = [v for v in d.variables if d[v].ndim == 3][0]
                    P = np.asarray(d[var][:], dtype=float)
                    tt = nc.num2date(d['time'][:], d['time'].units, only_use_cftime_datetimes=False)
                a.fill_between(tt, np.nanmean(P, axis=(1, 2)), step='post', alpha=0.5, label='mean')
                a.plot(tt, np.nanmax(P, axis=(1, 2)), drawstyle='steps-post', lw=0.8, label='max')
                a.set_ylabel(f'{var} (mm/h)')
                a.legend(fontsize=7)
            if t0 and t1:
                a.axvspan(t0, t1, color='grey', alpha=0.1)
            a.set_title(k, fontsize=9)
            a.tick_params(labelsize=7)
            for lab in a.get_xticklabels():
                lab.set_rotation(30)

    if save:
        fig.savefig(save, dpi=150)
        print(f'\nfigure written to {save}')
    else:
        plt.show()


# --------------------------------------------------------------------------- #
def build_parser():
    ap = argparse.ArgumentParser(prog='sfcfg', description='Display the configuration of a SFINCS model.')
    ap.add_argument('model_dir', nargs='?', default='.', help='folder with sfincs.inp (default: current folder)')
    ap.add_argument('--plot', action='store_true', help='show a map and forcing time series')
    ap.add_argument('--save', help='save the figure to this file (implies --plot)')
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)

    inp_path = os.path.join(args.model_dir, 'sfincs.inp')
    if not os.path.exists(inp_path):
        sys.exit(f'no sfincs.inp in {os.path.abspath(args.model_dir)}')

    inp = read_inp(args.model_dir)
    title = f'SFINCS model  {os.path.abspath(args.model_dir)}'
    print('=' * len(title))
    print(title)
    print('=' * len(title))

    show_inp(inp)
    show_files(args.model_dir, inp)
    data = {}
    show_details(args.model_dir, inp, data)

    if args.plot or args.save:
        plot(args.model_dir, inp, data, args.save)


if __name__ == '__main__':
    main()
