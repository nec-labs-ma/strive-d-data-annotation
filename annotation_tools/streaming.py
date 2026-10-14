"""Incrementally decode a top-level JSON object and its array items."""
import json


def iter_sections(path):
    decoder = json.JSONDecoder()
    with open(path, encoding='utf-8') as handle:
        buf, pos, eof = '', 0, False

        def fill():
            nonlocal buf, pos, eof
            chunk = handle.read(65536)
            buf = buf[pos:] + chunk
            pos = 0
            eof = not chunk

        def peek():
            nonlocal pos
            while True:
                while pos < len(buf) and buf[pos].isspace():
                    pos += 1
                if pos < len(buf):
                    return buf[pos]
                if eof:
                    return ''
                fill()

        def expect(char):
            nonlocal pos
            if peek() != char:
                raise ValueError(f'Expected {char!r} in annotation JSON')
            pos += 1

        def value():
            nonlocal pos
            peek()
            while True:
                try:
                    result, end = decoder.raw_decode(buf, pos)
                    # A primitive at a chunk boundary may be incomplete.
                    if end == len(buf) and not eof:
                        fill()
                        continue
                    pos = end
                    return result
                except json.JSONDecodeError:
                    if eof:
                        raise
                    fill()

        expect('{')
        if peek() != '}':
            while True:
                key = value()
                if not isinstance(key, str):
                    raise ValueError('Top-level JSON key must be a string')
                expect(':')
                if peek() == '[':
                    expect('[')
                    if peek() != ']':
                        while True:
                            yield key, value()
                            if peek() != ',':
                                break
                            expect(',')
                    expect(']')
                else:
                    yield key, value()
                if peek() != ',':
                    break
                expect(',')
        expect('}')
        if peek():
            raise ValueError('Unexpected content after annotation JSON')
