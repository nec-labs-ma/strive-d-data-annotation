"""Replaceable, inferred filename grouping; these are not verified dataset IDs."""
import re
from pathlib import Path

FAMILIES = [
    ('ccd_like', re.compile(r'^(?P<clip>Crash-\d+_\d+)_frame(?P<frame>\d+)(?:_(?P<variant>\d+))?\.(?:jpg|png)$', re.I)),
    ('ccd_like', re.compile(r'^(?P<clip>Normal_\d+)_frame(?P<frame>\d+)(?:_(?P<variant>\d+))?\.(?:jpg|png)$', re.I)),
    ('ccd_like', re.compile(r'^(?P<clip>training_negative_\d+)_frame(?P<frame>\d+)(?:_(?P<variant>\d+))?\.(?:jpg|png)$', re.I)),
    ('video_id_segment', re.compile(r'^(?P<clip>[A-Za-z0-9_-]{11}_\d+_(?:cause|effect))_frame(?P<frame>\d+)(?:_(?P<variant>\d+))?\.(?:jpg|png)$', re.I)),
    ('numeric', re.compile(r'^(?P<frame>\d+)(?:_(?P<variant>\d+))?\.(?:jpg|png)$', re.I)),
]


def parse_frame_name(file_name):
    name = Path(file_name).name
    for source, pattern in FAMILIES:
        match = pattern.fullmatch(name)
        if match:
            parts = match.groupdict()
            # Bare numbers contain no clip identity. Keep them in a visibly
            # unassigned group, never assert they belong to one real video.
            return dict(source=source, clip_id=parts.get('clip') or 'unassigned_numeric',
                        frame_index=int(parts['frame']), variant=parts.get('variant'))
    return dict(source='unknown', clip_id='unassigned_unknown', frame_index=None, variant=None)
