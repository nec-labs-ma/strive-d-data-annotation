import pytest
from annotation_tools.naming import parse_frame_name


@pytest.mark.parametrize('name,source,clip,frame,variant', [
    ('Crash-1500_001488_frame37.jpg', 'ccd_like', 'Crash-1500_001488', 37, None),
    ('Crash-1500_001488_frame37_1.jpg', 'ccd_like', 'Crash-1500_001488', 37, '1'),
    ('Normal_000500_frame5.jpg', 'ccd_like', 'Normal_000500', 5, None),
    ('training_negative_000827_frame15.jpg', 'ccd_like', 'training_negative_000827', 15, None),
    ('tmZqeKZ9uDg_009_effect_frame40.jpg', 'video_id_segment', 'tmZqeKZ9uDg_009_effect', 40, None),
    ('001928.jpg', 'numeric', 'unassigned_numeric', 1928, None),
    ('001999_1.jpg', 'numeric', 'unassigned_numeric', 1999, '1'),
    ('no-known-pattern.jpg', 'unknown', 'unassigned_unknown', None, None),
])
def test_families(name, source, clip, frame, variant):
    assert parse_frame_name(name) == dict(source=source, clip_id=clip, frame_index=frame, variant=variant)
