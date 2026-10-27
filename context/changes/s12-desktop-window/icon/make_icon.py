"""Draft of the cast-tv icon: an amber TV with the cast arcs, on a dark warm rounded square."""
import sys
from PIL import Image, ImageDraw

AMBER = (232, 163, 61, 255)          # --accent, #e8a33d
AMBER_SOFT = (246, 196, 120, 255)
BG_TOP = (44, 38, 32, 255)
BG_BOTTOM = (24, 21, 18, 255)


def draw(size=1024):
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    # a vertical gradient, masked by the rounded square
    grad = Image.new("RGBA", (s, s))
    gd = ImageDraw.Draw(grad)
    for y in range(s):
        t = y / (s - 1)
        gd.line([(0, y), (s, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=round(s * 0.225), fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    w = round(s * 0.062)                                   # stroke: heavy enough for 16 px
    # the screen
    x0, y0, x1, y1 = s * 0.16, s * 0.22, s * 0.84, s * 0.68
    d.rounded_rectangle([x0, y0, x1, y1], radius=round(s * 0.06), outline=AMBER, width=w)
    # the stand
    cx = s / 2
    d.rectangle([cx - w / 2, y1, cx + w / 2, s * 0.775], fill=AMBER)
    d.rounded_rectangle([s * 0.33, s * 0.755, s * 0.67, s * 0.755 + w], radius=w // 2, fill=AMBER)
    # the cast mark: a dot and two arcs from the screen's bottom-left corner
    ox, oy = x0 + s * 0.12, y1 - s * 0.10
    r = s * 0.045
    d.ellipse([ox - r, oy - r, ox + r, oy + r], fill=AMBER_SOFT)
    for k in (0.15, 0.255):
        R = s * k
        d.arc([ox - R, oy - R, ox + R, oy + R], start=270, end=360, fill=AMBER_SOFT, width=round(w * 0.8))
    return img


if __name__ == "__main__":
    out = sys.argv[1]
    big = draw(1024)
    big.resize((256, 256), Image.LANCZOS).save(out + "/icon.png")
    big.save(out + "/icon-1024.png")
    sizes = [16, 24, 32, 48, 64, 128, 256]
    big.save(out + "/cast-tv.ico", sizes=[(n, n) for n in sizes])
    # a preview: every size on the app's dark background and on a light one
    sheet = Image.new("RGBA", (40 + sum(n + 24 for n in sizes), 2 * 300), (255, 255, 255, 255))
    ImageDraw.Draw(sheet).rectangle([0, 0, sheet.width, 300], fill=(30, 30, 30, 255))
    x = 20
    for n in sizes:
        small = big.resize((n, n), Image.LANCZOS)
        for row in (0, 1):
            sheet.alpha_composite(small, (x, row * 300 + (300 - n) // 2))
        x += n + 24
    sheet.save(out + "/preview.png")
