import logging
from PIL import Image
import pytest
from annotation_tools.records import ObjectRecord, FrameRecord, xywh_to_xyxy, corners_to_xyxy
from annotation_tools.visualize import render_frame, label_color


def test_two_box_conventions():
    assert xywh_to_xyxy([318, 175.72, 46.75, 19.48]) == pytest.approx((318, 175.72, 364.75, 195.2))
    assert corners_to_xyxy([[852, 529], [942, 628]]) == (852, 529, 942, 628)
    with pytest.raises(ValueError):
        xywh_to_xyxy([0, 0, -2, 3])


def test_render_clamps_to_annotation_bounds_and_scales(tmp_path, caplog):
    frame = FrameRecord('sample', 1, tmp_path / 'frame.jpg', 100, 80,
                        [ObjectRecord('car', (-5, 20, 110, 75), 7)], {}, {})
    with caplog.at_level(logging.WARNING):
        rendered = render_frame(frame, Image.new('RGB', (200, 160), 'black'))
    assert 'clamping' in caplog.text
    assert 'scaling boxes' in caplog.text
    from PIL import ImageColor
    assert rendered.getpixel((199, 160)) == ImageColor.getrgb(label_color('car'))
    assert label_color('CAR') == label_color('car')
