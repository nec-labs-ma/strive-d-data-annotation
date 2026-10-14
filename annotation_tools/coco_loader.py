"""Stream the COCO file into a reusable SQLite index; load one clip at a time."""
import hashlib
import json
import logging
import sqlite3
from pathlib import Path
from .naming import parse_frame_name
from .records import FrameRecord, ObjectRecord, xywh_to_xyxy
from .streaming import iter_sections

LOG = logging.getLogger(__name__)
INDEX_VERSION = 2


class CocoSource:
    def __init__(self, annotation_path, video_root, cache_dir='.cache/strive-d', flat=False):
        self.path = Path(annotation_path).resolve()
        self.video_root = Path(video_root)
        self.flat = flat
        cache = Path(cache_dir)
        cache.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(str(self.path).encode()).hexdigest()[:20]
        self.index_path = cache / f'coco-{digest}.sqlite'
        stat = self.path.stat()
        signature = f'{INDEX_VERSION}:{stat.st_size}:{stat.st_mtime_ns}'
        valid = False
        if self.index_path.exists():
            try:
                with sqlite3.connect(self.index_path) as con:
                    valid = con.execute('SELECT signature FROM metadata').fetchone() == (signature,)
            except sqlite3.DatabaseError:
                pass
        if not valid:
            self._build_index(signature)
        self.con = sqlite3.connect(self.index_path)
        self.categories = {row[0]: json.loads(row[1]) for row in self.con.execute('SELECT id, raw FROM categories')}
        counts = dict(self.con.execute('SELECT category_id, COUNT(*) FROM annotations GROUP BY category_id'))
        self.empty_categories = [v['name'] for k, v in self.categories.items() if not counts.get(k)]
        if self.empty_categories:
            LOG.warning('Declared categories with zero annotations: %s', ', '.join(self.empty_categories))

    def _build_index(self, signature):
        # No annotation JSON is held globally in memory. Atomic replacement
        # leaves the previous cache intact if parsing fails.
        import tempfile
        with tempfile.NamedTemporaryFile(dir=self.index_path.parent, suffix='.sqlite', delete=False) as temp:
            temp_path = Path(temp.name)
        try:
            con = sqlite3.connect(temp_path)
            try:
                con.executescript('''
                    CREATE TABLE metadata(signature TEXT);
                    CREATE TABLE categories(id INTEGER PRIMARY KEY, raw TEXT);
                    CREATE TABLE images(id INTEGER PRIMARY KEY, clip TEXT, frame INTEGER,
                        filename TEXT, raw TEXT);
                    CREATE TABLE annotations(id INTEGER PRIMARY KEY, image_id INTEGER,
                        category_id INTEGER, raw TEXT);
                ''')
                for section, item in iter_sections(self.path):
                    if section == 'categories':
                        con.execute('INSERT INTO categories VALUES (?, ?)', (item['id'], json.dumps(item)))
                    elif section == 'images':
                        parsed = parse_frame_name(item['file_name'])
                        con.execute('INSERT INTO images VALUES (?, ?, ?, ?, ?)',
                                    (item['id'], parsed['clip_id'], parsed['frame_index'], item['file_name'], json.dumps(item)))
                    elif section == 'annotations':
                        con.execute('INSERT INTO annotations VALUES (?, ?, ?, ?)',
                                    (item['id'], item['image_id'], item['category_id'], json.dumps(item)))
                if not con.execute('SELECT COUNT(*) FROM images').fetchone()[0]:
                    raise ValueError('COCO file contains no images')
                for column, table in [('image_id', 'images'), ('category_id', 'categories')]:
                    if con.execute(f'SELECT 1 FROM annotations a LEFT JOIN {table} b ON a.{column}=b.id WHERE b.id IS NULL LIMIT 1').fetchone():
                        raise ValueError(f'Annotation references unknown {column}')
                con.executescript('''
                    CREATE INDEX images_clip ON images(clip, frame);
                    CREATE INDEX annotations_image ON annotations(image_id);
                ''')
                con.execute('INSERT INTO metadata VALUES (?)', (signature,))
                con.commit()
            finally:
                con.close()
            temp_path.replace(self.index_path)
        finally:
            temp_path.unlink(missing_ok=True)

    def close(self):
        self.con.close()

    def clips(self):
        return [row[0] for row in self.con.execute('SELECT DISTINCT clip FROM images ORDER BY clip')]

    def frames(self, clip_id):
        rows = self.con.execute('SELECT id, frame, raw FROM images WHERE clip=? ORDER BY frame, filename, id', (clip_id,)).fetchall()
        if not rows:
            raise ValueError(f'Unknown clip: {clip_id}')
        records = []
        for image_id, frame_index, raw_image in rows:
            image = json.loads(raw_image)
            annotations = [json.loads(row[0]) for row in self.con.execute('SELECT raw FROM annotations WHERE image_id=? ORDER BY id', (image_id,))]
            objects, frame_level = [], {}
            for annotation in annotations:
                label = self.categories[annotation['category_id']]['name']
                attrs = annotation.get('attributes', {}).copy()
                obj = ObjectRecord(label, xywh_to_xyxy(annotation['bbox']), attrs.get('track_id'), attrs)
                objects.append(obj)
                if label in {'Road', 'Accident', 'Weather', 'Lighting'}:
                    frame_level.setdefault(label, []).append(attrs)
            path = self.video_root / image['file_name'] if self.flat else self.video_root / clip_id / image['file_name']
            records.append(FrameRecord(clip_id, frame_index if frame_index is not None else image_id,
                                       path, image['width'], image['height'], objects, frame_level,
                                       {'image': image, 'annotations': annotations}))
        missing = sum(not record.image_path.is_file() for record in records)
        if missing:
            LOG.warning('%s: %d/%d local frames missing', clip_id, missing, len(records))
        return records
