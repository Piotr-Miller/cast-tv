"""Generate the tiny image fixtures the photo tests use, so no binaries are committed.

Run as a script to write them into a directory; import to get the bytes.
"""
from __future__ import annotations

import io
import sys

import pillow_heif
from PIL import Image

pillow_heif.register_heif_opener()


def _image(width, height):
    im = Image.new("RGB", (width, height), (40, 120, 200))
    for x in range(0, width, max(1, width // 8)):
        im.paste((220, 60, 60), (x, 0, x + max(1, width // 16), height // 2))
    return im


def jpeg(width=64, height=48, orientation=1, quality=85) -> bytes:
    im = _image(width, height)
    out = io.BytesIO()
    if orientation != 1:
        exif = Image.Exif()
        exif[0x0112] = orientation
        im.save(out, format="JPEG", quality=quality, exif=exif.tobytes())
    else:
        im.save(out, format="JPEG", quality=quality)
    return out.getvalue()


def png(width=64, height=48) -> bytes:
    out = io.BytesIO()
    _image(width, height).save(out, format="PNG")
    return out.getvalue()


def webp(width=64, height=48) -> bytes:
    out = io.BytesIO()
    _image(width, height).save(out, format="WEBP", quality=80)
    return out.getvalue()


def heic(width=64, height=48) -> bytes:
    out = io.BytesIO()
    _image(width, height).save(out, format="HEIF", quality=80)
    return out.getvalue()


def gif(width=16, height=16) -> bytes:
    out = io.BytesIO()
    _image(width, height).convert("P").save(out, format="GIF")
    return out.getvalue()


ALL = {"oriented.jpg": lambda: jpeg(orientation=6), "plain.jpg": jpeg, "plain.png": png,
       "plain.webp": webp, "plain.heic": heic, "plain.gif": gif}


def write_all(directory) -> dict:
    import os
    os.makedirs(directory, exist_ok=True)
    paths = {}
    for name, make in ALL.items():
        path = os.path.join(directory, name)
        with open(path, "wb") as fh:
            fh.write(make())
        paths[name] = path
    return paths


if __name__ == "__main__":
    for name, path in write_all(sys.argv[1] if len(sys.argv) > 1 else ".").items():
        print(path)
