import json
import pytest
from annotation_tools.coco_loader import CocoSource
from annotation_tools.clip_loader import ClipSource
from annotation_tools.records import RoadObjectRecord, EgoManeuverRecord
from annotation_tools.streaming import iter_sections


def coco_fixture(tmp_path):
    path = tmp_path / 'annotations.json'
    data = {'images': [
        {'id': 1, 'file_name': 'Normal_000001_frame2.jpg', 'width': 100, 'height': 80},
        {'id': 2, 'file_name': 'Normal_000001_frame2_1.jpg', 'width': 100, 'height': 80}],
        'categories': [{'id': 1, 'name': 'Road'}, {'id': 2, 'name': 'Weather'}],
        'annotations': [{'id': 1, 'image_id': 1, 'category_id': 1, 'bbox': [10, 20, 30, 40],
                         'attributes': {'track_id': 9, 'Condition': 'Wet', 'Type': 'Green'}}]}
    path.write_text(json.dumps(data))
    return path


def test_coco_cache_raw_variants_and_flat(tmp_path):
    path = coco_fixture(tmp_path)
    source = CocoSource(path, tmp_path / 'frames', tmp_path / 'cache')
    records = source.frames('Normal_000001')
    assert len(records) == 2  # suffix variant is not silently deduplicated
    assert records[0].objects[0].bbox_xyxy == (10, 20, 40, 60)
    assert records[0].objects[0].attributes['Type'] == 'Green'
    assert records[0].frame_level['Road'][0]['Condition'] == 'Wet'
    assert source.empty_categories == ['Weather']
    stamp = source.index_path.stat().st_mtime_ns
    source.close()
    source = CocoSource(path, tmp_path, tmp_path / 'cache', flat=True)
    assert source.index_path.stat().st_mtime_ns == stamp
    assert source.frames('Normal_000001')[0].image_path == tmp_path / 'Normal_000001_frame2.jpg'
    source.close()
    data = json.loads(path.read_text())
    data['images'].append({'id': 3, 'file_name': 'Normal_000002_frame1.jpg', 'width': 80, 'height': 60})
    path.write_text(json.dumps(data))
    source = CocoSource(path, tmp_path, tmp_path / 'cache')
    assert source.clips() == ['Normal_000001', 'Normal_000002']
    source.close()


def clip_fixture(tmp_path):
    nested = tmp_path / 'annotations' / 'sample-clip' / 'sample-clip'
    nested.mkdir(parents=True)
    raw = {'frameId': 1, 'filePath': 'obsolete/prefix/sample-clip/0029_Camera.json',
           'isEffective': 1, 'info': {'width': 100, 'height': 80, 'depth': 3},
           'groupsProperties': [], 'qaMap': {}, 'dataList': [
               {'id': 1, 'label': 'car', 'shapeType': 'rectangle', 'coordinates': [[10, 20], [40, 60]],
                'properties': {'color': 'white', 'cutin': 'none', 'cutout': 'none', 'direction in terms of ego-car': 'left'}},
               {'id': 2, 'label': 'ego-vehicle', 'shapeType': 'rectangle', 'coordinates': [[0, 60], [90, 80]],
                'properties': {'Change Lane': 'none', 'Turn': 'none'}}]}
    for number in [31, 29]:
        raw['filePath'] = f'obsolete/prefix/sample-clip/{number:04d}_Camera.jpg'
        (nested / f'{number:04d}_Camera.json').write_text(json.dumps(raw))
    return tmp_path / 'annotations', nested


def test_clip_order_schema_and_tool_path(tmp_path):
    annotations, nested = clip_fixture(tmp_path)
    source = ClipSource(annotations, tmp_path / 'frames')
    records = source.frames('sample-clip')
    assert [r.frame_index for r in records] == [29, 31]
    assert records[0].raw['frameId'] == 1
    assert records[0].raw['groupsProperties'] == []
    assert records[0].image_path == tmp_path / 'frames/sample-clip/0029_Camera.jpg'
    assert isinstance(records[0].objects[0], RoadObjectRecord)
    assert isinstance(records[0].objects[1], EgoManeuverRecord)
    assert records[0].objects[0].bbox_xyxy == (10, 20, 40, 60)
    file = nested / '0029_Camera.json'
    raw = json.loads(file.read_text())
    raw['dataList'][0]['properties']['unexpected'] = True
    file.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match='unrecognized property schema'):
        source.frames('sample-clip')


def test_streaming_chunk_boundary_unicode_and_truncation(tmp_path):
    path = tmp_path / 'large.json'
    data = {'info': {'description': '汉字' * 40000}, 'images': [{'id': i} for i in range(2000)], 'annotations': []}
    path.write_text(json.dumps(data, ensure_ascii=False))
    values = list(iter_sections(path))
    assert values[0] == ('info', data['info'])
    assert [v for k, v in values if k == 'images'] == data['images']
    path.write_text('{"images": [{"id": 1}')
    with pytest.raises(ValueError):
        list(iter_sections(path))
