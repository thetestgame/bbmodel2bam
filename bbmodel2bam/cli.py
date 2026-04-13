"""CLI entry point for bbmodel2bam."""

import argparse
import os
import sys

from .version import __version__
from .converter import convert


def main():
    parser = argparse.ArgumentParser(
        description='Convert Blockbench .bbmodel files to Panda3D .bam files',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        '--version', action='version',
        version=f'%(prog)s {__version__}',
    )
    parser.add_argument('src', nargs='+', type=str, help='source .bbmodel file(s) or directory')
    parser.add_argument('dst', type=str, help='destination .bam file or directory')
    parser.add_argument(
        '-v', '--verbose', action='store_true',
        help='print extra information',
    )
    parser.add_argument(
        '--scale', type=float, default=1.0,
        help='uniform scale factor applied to all coordinates',
    )
    parser.add_argument(
        '--textures', choices=['embed', 'ref'], default='embed',
        help='how to handle textures: embed in BAM or save as ref files',
    )
    parser.add_argument(
        '--append-ext', action='store_true',
        help='append .bam extension instead of replacing (batch mode only)',
    )

    args = parser.parse_args()

    src = [os.path.abspath(i.strip('"')) for i in args.src]
    dst = os.path.abspath(args.dst.strip('"'))

    src_is_dir = len(src) == 1 and os.path.isdir(src[0])
    dst_is_dir = not os.path.splitext(dst)[1]
    if dst_is_dir and not dst.endswith(os.sep):
        dst += os.sep

    # Collect files to convert
    files = []
    if src_is_dir:
        for root, _, fnames in os.walk(src[0]):
            files += [os.path.join(root, f) for f in fnames if f.endswith('.bbmodel')]
    else:
        files = list(src)

    for f in files:
        if not os.path.exists(f):
            print(f'Source does not exist: {f}', file=sys.stderr)
            sys.exit(1)
        if not f.endswith('.bbmodel'):
            print(f'Source is not a .bbmodel file: {f}', file=sys.stderr)
            sys.exit(1)

    is_batch = len(files) > 1 or dst_is_dir

    if is_batch and not dst_is_dir:
        print('Destination must be a directory when converting multiple files',
              file=sys.stderr)
        sys.exit(1)

    try:
        for src_file in files:
            if is_batch:
                basename = os.path.basename(src_file)
                if args.append_ext:
                    out = os.path.join(dst, basename + '.bam')
                else:
                    out = os.path.join(dst, os.path.splitext(basename)[0] + '.bam')
            else:
                out = dst

            if args.verbose:
                print(f'Converting {src_file} -> {out}')

            convert(
                src_file, out,
                scale=args.scale,
                textures_mode=args.textures,
                verbose=args.verbose,
            )

        if args.verbose:
            print(f'Done. Converted {len(files)} file(s).')

    except Exception:
        import traceback
        print(traceback.format_exc(), file=sys.stderr)
        print('Failed to convert', file=sys.stderr)
        sys.exit(1)
