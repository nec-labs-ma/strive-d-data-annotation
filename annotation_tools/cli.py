import argparse
import json
import logging
from pathlib import Path
from .clip_loader import ClipSource
from .coco_loader import CocoSource


def read_config(path):
    path = Path(path).resolve()
    with path.open() as handle:
        values = json.load(handle)
    for key in ('video_root', 'coco_annotations', 'clip_annotations', 'cache_dir'):
        if key in values and values[key]:
            candidate = Path(values[key]).expanduser()
            values[key] = candidate if candidate.is_absolute() else (path.parent / candidate).resolve()
    return values


def make_source(config, source, flat=False):
    if source == 'coco':
        return CocoSource(config['coco_annotations'], config['video_root'], config.get('cache_dir', '.cache/strive-d'), flat)
    return ClipSource(config['clip_annotations'], config['video_root'])


def main(argv=None):
    parser = argparse.ArgumentParser(description='Load and view separately distributed annotations offline')
    parser.add_argument('--config', default='paths.json')
    parser.add_argument('--source', choices=['coco', 'clip'], required=True)
    parser.add_argument('--clip', help='Clip ID to visualize')
    parser.add_argument('--list-clips', action='store_true')
    parser.add_argument('--flat', action='store_true', help='COCO only: frames directly under video_root')
    parser.add_argument('--out', default='out')
    parser.add_argument('--frames', help='Inclusive frame range, e.g. 0029:0100')
    parser.add_argument('--fps', type=float, default=5)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
    source = None
    try:
        if args.flat and args.source != 'coco':
            raise ValueError('--flat applies only to the COCO source')
        config = read_config(args.config)
        source = make_source(config, args.source, args.flat)
        if args.list_clips:
            print('\n'.join(source.clips()))
        else:
            if not args.clip:
                raise ValueError('--clip is required unless using --list-clips')
            from .visualize import write_visualization
            records = source.frames(args.clip)
            if args.frames:
                parts = args.frames.split(':')
                if len(parts) != 2:
                    raise ValueError('--frames must be START:END')
                start, end = map(int, parts)
                if start > end:
                    raise ValueError('--frames start must be <= end')
                records = [r for r in records if start <= r.frame_index <= end]
            if not records:
                raise ValueError('No annotations match the selected frame range')
            print(write_visualization(records, args.out, args.fps))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))
    finally:
        if isinstance(source, CocoSource):
            source.close()


if __name__ == '__main__':
    main()
