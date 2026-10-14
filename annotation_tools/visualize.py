"""Draw normalized boxes on user-supplied images; write an annotated MP4."""
import hashlib
import logging
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from .records import EgoManeuverRecord

LOG = logging.getLogger(__name__)
FRAME_LABELS = {'Road', 'Accident', 'Weather', 'Lighting', 'ego-vehicle'}
PALETTE = ['#ff9b54', '#68dfad', '#6cbaff', '#e5b3ff', '#ffd166', '#ff8ea1']


def label_color(label):
    # Normalize case only for grouping/color, preserve raw annotation text.
    index = int(hashlib.sha256(label.casefold().encode()).hexdigest()[:8], 16)
    return PALETTE[index % len(PALETTE)]


def attributes_text(attributes):
    return '; '.join(f'{k}: {v}' for k, v in attributes.items()
                     if v not in ('', None) and k not in {'rotation', 'keyframe', 'track_id'})


def _lines(text, draw, font, width):
    result, current = [], ''
    for word in text.split():
        candidate = f'{current} {word}'.strip()
        if current and draw.textlength(candidate, font=font) > width:
            result.append(current)
            current = word
        else:
            current = candidate
    return result + ([current] if current else [])


def render_frame(record, image=None):
    """Optional image allows synthetic QA without any source media."""
    if record.width <= 0 or record.height <= 0:
        raise ValueError('Annotation image dimensions must be positive')
    if image is None:
        with Image.open(record.image_path) as source:
            image = source.convert('RGB')
    else:
        image = image.convert('RGB').copy()
    width, height = image.size
    sx, sy = width / record.width, height / record.height
    if (width, height) != (record.width, record.height):
        LOG.warning('%s: image size differs from annotation (%sx%s vs %sx%s); scaling boxes',
                    record.image_path.name, width, height, record.width, record.height)
    try:
        font = ImageFont.load_default(size=max(12, round(width / 120)))
    except TypeError:  # Older Pillow fallback.
        font = ImageFont.load_default()
    probe = ImageDraw.Draw(image)
    header = [f'{record.clip_id} | frame {record.frame_index}']
    for label, values in record.frame_level.items():
        if isinstance(values, list):
            for attrs in values:
                text = attributes_text(attrs)
                if text:
                    header.extend(_lines(f'{label}: {text}', probe, font, width - 16))
        else:
            header.append(f'{label}: {values}')
    line_height = max(16, round(width / 120) + 5)
    strip = 12 + line_height * len(header)
    canvas = Image.new('RGB', (width, height + strip), '#171b24')
    canvas.paste(image, (0, strip))
    draw = ImageDraw.Draw(canvas)
    for i, line in enumerate(header):
        draw.text((8, 6 + i * line_height), line, fill='white', font=font)
    captions = []
    for obj in record.objects:
        x1, y1, x2, y2 = obj.bbox_xyxy
        if x1 < 0 or y1 < 0 or x2 > record.width or y2 > record.height:
            LOG.warning('%s: %s box %s outside annotation bounds %sx%s; clamping',
                        record.image_path.name, obj.label, obj.bbox_xyxy, record.width, record.height)
        x1, x2 = [max(0, min(width - 1, x * sx)) for x in (x1, x2)]
        y1, y2 = [strip + max(0, min(height - 1, y * sy)) for y in (y1, y2)]
        color = label_color(obj.label)
        if isinstance(obj, EgoManeuverRecord):
            # A dashed white outline distinguishes the maneuver annotation.
            color = '#ffffff'
            for start in range(int(x1), int(x2), 16):
                draw.line((start, y1, min(start + 8, x2), y1), fill=color, width=2)
                draw.line((start, y2, min(start + 8, x2), y2), fill=color, width=2)
            for start in range(int(y1), int(y2), 16):
                draw.line((x1, start, x1, min(start + 8, y2)), fill=color, width=2)
                draw.line((x2, start, x2, min(start + 8, y2)), fill=color, width=2)
        else:
            draw.rectangle((x1, y1, x2, y2), outline=color, width=2)
        title = obj.label + (f' #{obj.track_id}' if obj.track_id is not None else '')
        captions.append((obj, x1, y1, title, color))
    occupied = []
    for obj, x1, y1, title, color in captions:
        lines = [title]
        if obj.label not in FRAME_LABELS:
            names = {'Number of Signs': 'count', 'Number of Traffic-Lights': 'count',
                     'Status of Closest Traffic Lights': 'status', 'direction in terms of ego-car': 'side',
                     'cutin': 'in', 'cutout': 'out', 'color': 'color', 'Type': 'type'}
            compact = attributes_text({names.get(k, k): v for k, v in obj.attributes.items()})
            if compact:
                lines.extend(_lines(compact, draw, font, min(300, width - 12)))
        text_height = len(lines) * line_height + 4
        text_width = min(width - 8, max(draw.textlength(line, font=font) for line in lines) + 6)
        chosen = None
        # Separate crowded labels while keeping them close to their boxes.
        for step in range(max(1, height // (text_height + 4))):
            y = max(strip, min(y1 - text_height - step * (text_height + 4), strip + height - text_height))
            for offset in (0, -text_width, text_width, -2 * text_width, 2 * text_width):
                x = max(0, min(x1 + offset, width - text_width))
                rect = (x, y, x + text_width, y + text_height)
                if all(rect[2] + 4 <= r[0] or rect[0] >= r[2] + 4 or rect[3] + 4 <= r[1] or rect[1] >= r[3] + 4 for r in occupied):
                    chosen = rect
                    break
            if chosen:
                break
        if chosen is None:
            chosen = (0, strip, text_width, strip + text_height)
            LOG.warning('%s: crowded annotations; label overlap could not be avoided', record.image_path.name)
        occupied.append(chosen)
        x, y, right, bottom = chosen
        if abs(x - x1) > 5 or abs(bottom - y1) > 5:
            draw.line((x1, y1, max(x, min(x1, right)), bottom), fill=color, width=1)
        draw.rectangle(chosen, fill='#171b24')
        for i, line in enumerate(lines):
            draw.text((x + 3, y + 2 + i * line_height), line, fill=color, font=font)
    return canvas


def write_visualization(records, output_dir, fps=5):
    import cv2
    import numpy as np

    if fps <= 0:
        raise ValueError('fps must be positive')
    present = [r for r in records if r.image_path.is_file()]
    if not present:
        raise ValueError('No local images found for the selected frames')
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / f'{Path(present[0].clip_id).name}.mp4'
    writer = None
    try:
        for record in present:
            image = render_frame(record)
            image.thumbnail((1280, 800))
            if writer is None:
                # Pad to even dimensions for the encoder without distorting boxes.
                size = (image.width + image.width % 2, image.height + image.height % 2)
                writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), fps, size)
                if not writer.isOpened():
                    raise ValueError('OpenCV could not initialize the MP4 encoder')
            image.thumbnail(size)
            canvas = Image.new('RGB', size, '#171b24')
            canvas.paste(image, (0, 0))
            writer.write(cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR))
    finally:
        if writer is not None:
            writer.release()
    return path
