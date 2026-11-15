"""
sfincstools - command-line tools for SFINCS models.

  sfincstools -v / --version   show the package version
  sfincstools                  list the available tools
"""
import argparse

from sfincstools import __version__

TOOLS = (
    ('sfpgs', 'check the progress of a SFINCS run'),
    ('sfcfg', 'display the configuration of a SFINCS model'),
)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='sfincstools', description='Command-line tools for SFINCS models.')
    ap.add_argument('-v', '--version', action='version', version=f'%(prog)s {__version__}')
    ap.parse_args(argv)
    print(f'sfincstools {__version__}\n\navailable tools:')
    for name, desc in TOOLS:
        print(f'  {name:7s} {desc}')
    print("\nrun '<tool> -h' for help on a tool")


if __name__ == '__main__':
    main()
