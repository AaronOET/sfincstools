"""
Check the progress of a SFINCS run.

  sfpgs [MODEL_DIR] [--watch SECONDS] [--stall MINUTES]

  MODEL_DIR   folder with sfincs.inp (default: current folder)
  --watch     refresh every SECONDS until the run ends (default: report once)
  --stall     warn if the log has not changed for this many minutes (default 10)

Reads
- sfincs.log (or sfincs_log.txt): "xx% complete, yy s remaining", errors, final summary
- sfincs_map.nc / sfincs_his.nc : last output time, so you also see the model time reached
Works while SFINCS is running (the output files are opened read-only; a locked file is simply skipped).
"""
import os, re, sys, time, argparse
from datetime import datetime, timedelta

os.environ.setdefault('HDF5_USE_FILE_LOCKING', 'FALSE')   # allow reading NetCDF files that SFINCS has open

LOGS = ('sfincs.log', 'sfincs_log.txt')


def read_inp(model_dir):
    inp = {}
    with open(os.path.join(model_dir, 'sfincs.inp')) as f:
        for line in f:
            if '=' in line:
                k, v = line.split('=', 1)
                inp[k.strip().lower()] = v.strip()
    return inp


def parse_time(s):
    return datetime.strptime(s.strip(), '%Y%m%d %H%M%S')


def last_output_time(path):
    """last time stamp in a SFINCS NetCDF output file (None if missing / locked)"""
    if not os.path.exists(path):
        return None, 0
    try:
        import netCDF4 as nc
        with nc.Dataset(path) as d:
            t = d['time']
            if len(t) == 0:
                return None, 0
            last = nc.num2date(t[-1], t.units, only_use_cftime_datetimes=False)
            return datetime(last.year, last.month, last.day, last.hour, last.minute, last.second), len(t)
    except Exception:
        return None, 0


def read_log(model_dir):
    """newest log file -> dict with percent, remaining, status, messages"""
    logs = [os.path.join(model_dir, f) for f in LOGS if os.path.exists(os.path.join(model_dir, f))]
    if not logs:
        return None
    log = max(logs, key=os.path.getmtime)
    with open(log, errors='ignore') as f:
        txt = f.read()
    r = dict(file=log, mtime=datetime.fromtimestamp(os.path.getmtime(log)), percent=None, remaining=None,
             status='starting', errors=[], warnings=[], summary={})
    prog = re.findall(r'(\d+)%\s*complete,\s*([\d.]+|-)\s*s remaining', txt)
    if prog:
        r['percent'] = int(prog[-1][0])
        r['remaining'] = None if prog[-1][1] == '-' else float(prog[-1][1])
        r['status'] = 'running'
    r['errors'] = [l.strip() for l in txt.splitlines() if re.match(r'\s*error', l, re.I)]
    r['warnings'] = sorted({l.strip() for l in txt.splitlines() if re.match(r'\s*warning', l, re.I)})
    if 'Simulation finished' in txt or 'Closing off SFINCS' in txt:
        r['status'] = 'finished'
        for key, pat in (('total time', r'Total time\s*:\s*([\d.]+)'), ('average time step', r'Average time step \(s\)\s*:\s*([\d.]+)')):
            m = re.search(pat, txt)
            if m: r['summary'][key] = float(m.group(1))
    if r['errors'] or re.search(r'has stopped|unstable|simulation stopped', txt, re.I):
        r['status'] = 'error'
    return r


def bar(frac, width=40):
    frac = min(max(frac, 0.0), 1.0)
    n = int(round(frac * width))
    return '[' + '#' * n + '-' * (width - n) + f'] {frac * 100:5.1f}%'


def report(model_dir, stall_min):
    inp = read_inp(model_dir)
    tstart, tstop = parse_time(inp['tstart']), parse_time(inp['tstop'])
    total = (tstop - tstart).total_seconds()
    log = read_log(model_dir)
    t_map, n_map = last_output_time(os.path.join(model_dir, 'sfincs_map.nc'))
    t_his, n_his = last_output_time(os.path.join(model_dir, 'sfincs_his.nc'))
    t_out = max([t for t in (t_map, t_his) if t is not None], default=None)

    print(f'\n=== {os.path.abspath(model_dir)}   ({datetime.now():%Y-%m-%d %H:%M:%S})')
    print(f'model period : {tstart} -> {tstop}  ({total / 3600:.1f} h)')
    if log is None:
        print('status       : not started (no sfincs.log / sfincs_log.txt)')
        return 'not started'

    status = log['status']
    idle = datetime.now() - log['mtime']
    if status in ('running', 'starting') and idle > timedelta(minutes=stall_min):
        status = f'stalled? (log unchanged for {idle.total_seconds() / 60:.0f} min)'
    print(f'status       : {status}   [{os.path.basename(log["file"])}, updated {log["mtime"]:%H:%M:%S}]')

    if log['status'] == 'finished':
        print(f'progress     : {bar(1.0)}')
        for k, v in log['summary'].items():
            print(f'{k:<13}: {v:g} s')
    elif log['percent'] is not None:
        rem = '' if log['remaining'] is None else f', ~{timedelta(seconds=round(log["remaining"]))} remaining (SFINCS estimate)'
        print(f'progress     : {bar(log["percent"] / 100)}{rem}')
    if t_out is not None:
        frac = (t_out - tstart).total_seconds() / total if total > 0 else 0
        print(f'model time   : {t_out}  ({(t_out - tstart).total_seconds() / 3600:.1f} of {total / 3600:.1f} h, '
              f'{frac * 100:.0f}%; map steps {n_map}, his steps {n_his})')
    for e in log['errors'][:5]:
        print(f'ERROR        : {e}')
    for w in log['warnings'][:5]:
        print(f'warning      : {w}')
    if len(log['warnings']) > 5:
        print(f'               ... {len(log["warnings"]) - 5} more warnings in the log')
    return log['status']


def main(argv=None):
    ap = argparse.ArgumentParser(prog='sfpgs', description='Check the progress of a SFINCS run')
    ap.add_argument('model_dir', nargs='?', default='.')
    ap.add_argument('--watch', type=float, default=0, help='refresh interval in seconds (0 = once)')
    ap.add_argument('--stall', type=float, default=10, help='minutes without log updates before warning')
    a = ap.parse_args(argv)
    if not os.path.exists(os.path.join(a.model_dir, 'sfincs.inp')):
        sys.exit(f'no sfincs.inp in {a.model_dir}')
    while True:
        status = report(a.model_dir, a.stall)
        if not a.watch or status in ('finished', 'error'):
            break
        try:
            time.sleep(a.watch)
        except KeyboardInterrupt:
            break


if __name__ == '__main__':
    main()
