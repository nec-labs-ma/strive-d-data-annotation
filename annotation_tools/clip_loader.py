"""Custom per-frame annotations. Stored tool paths are never used as local paths."""
import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from .records import FrameRecord, RoadObjectRecord, EgoManeuverRecord, corners_to_xyxy

LOG = logging.getLogger(__name__)
FRAME_NAME = re.compile(r'^(\d+)_.*\.json$', re.I)
ROAD_KEYS = {'color', 'cutin', 'cutout', 'direction in terms of ego-car'}
EGO_KEYS = {'Change Lane', 'Turn'}


class ClipSource:
    def __init__(self, annotation_path, video_root):
        self.root = Path(annotation_path)
        self.video_root = Path(video_root)
        if not self.root.exists():
            raise FileNotFoundError(self.root)
        self._files = defaultdict(list)
        for path in sorted(self.root.rglob('*.json')):
            match = FRAME_NAME.fullmatch(path.name)
            if match:
                # The immediate parent is the clip, regardless of outer nesting.
                self._files[path.parent.name].append((int(match[1]), path))
        if not self._files:
            raise ValueError('No numeric-prefix per-frame annotation files found')
        for clip, entries in self._files.items():
            if len({n for n, _ in entries}) != len(entries):
                raise ValueError(f'{clip}: duplicate frame numbers (possibly colliding clip directories)')
            entries.sort()

    def clips(self):
        return sorted(self._files)

    def frames(self, clip_id):
        if clip_id not in self._files:
            raise ValueError(f'Unknown clip: {clip_id}')
        records = []
        for number, path in self._files[clip_id]:
            raw = json.loads(path.read_text())
            objects, maneuvers = [], []
            for entry in raw['dataList']:
                if entry['shapeType'] != 'rectangle':
                    raise ValueError(f'{path.name}: unsupported shapeType {entry["shapeType"]!r}')
                attrs = entry['properties'].copy()
                common = dict(label=entry['label'], bbox_xyxy=corners_to_xyxy(entry['coordinates']),
                              track_id=entry['id'], attributes=attrs)
                if entry['label'] == 'ego-vehicle' and set(attrs) == EGO_KEYS:
                    ego = EgoManeuverRecord(**common, change_lane=attrs['Change Lane'], turn=attrs['Turn'])
                    objects.append(ego)
                    maneuvers.append(attrs)
                elif entry['label'] != 'ego-vehicle' and set(attrs) == ROAD_KEYS:
                    objects.append(RoadObjectRecord(**common, color=attrs['color'], cutin=attrs['cutin'],
                                                    cutout=attrs['cutout'], direction=attrs['direction in terms of ego-car']))
                else:
                    raise ValueError(f'{path.name}: unrecognized property schema for {entry["label"]!r}: {sorted(attrs)}')
            basename = Path(raw['filePath'].replace('\\', '/')).name
            records.append(FrameRecord(clip_id, number, self.video_root / clip_id / basename,
                                       raw['info']['width'], raw['info']['height'], objects,
                                       {'ego-vehicle': maneuvers, 'isEffective': raw['isEffective']}, raw))
        missing = sum(not record.image_path.is_file() for record in records)
        if missing:
            LOG.warning('%s: %d/%d local frames missing', clip_id, missing, len(records))
        return records
