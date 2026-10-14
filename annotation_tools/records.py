from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class ObjectRecord:
    label: str
    bbox_xyxy: tuple[float, float, float, float]
    track_id: int | str | None = None
    attributes: dict = field(default_factory=dict)


@dataclass
class RoadObjectRecord(ObjectRecord):
    color: str = ''
    cutin: str = ''
    cutout: str = ''
    direction: str = ''


@dataclass
class EgoManeuverRecord(ObjectRecord):
    change_lane: str = ''
    turn: str = ''


@dataclass
class FrameRecord:
    clip_id: str
    frame_index: int
    image_path: Path
    width: int
    height: int
    objects: list[ObjectRecord]
    frame_level: dict
    raw: dict


class AnnotationSource(Protocol):
    def clips(self) -> list[str]: ...
    def frames(self, clip_id: str) -> list[FrameRecord]: ...


def xywh_to_xyxy(bbox):
    x, y, width, height = map(float, bbox)
    if width < 0 or height < 0:
        raise ValueError('Negative COCO bounding box size')
    return x, y, x + width, y + height


def corners_to_xyxy(coordinates):
    (x1, y1), (x2, y2) = coordinates
    if x2 < x1 or y2 < y1:
        raise ValueError('Reversed rectangle corners')
    return float(x1), float(y1), float(x2), float(y2)
