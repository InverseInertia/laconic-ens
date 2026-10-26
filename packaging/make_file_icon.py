"""Draws packaging/file-icon.png and file-icon.ico, the icon of a .lens file: a page with a
folded corner carrying the app icon (packaging/icon.png). Run it after changing icon.png."""
import os
from PIL import Image, ImageDraw

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = 4 * 512                                   # drawn large, then scaled down for smooth edges
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
u = S / 512
L, T, R, B, F = 76 * u, 16 * u, 436 * u, 496 * u, 110 * u   # page box and fold size
ink, page, fold = (23, 37, 61, 255), (250, 252, 255, 255), (203, 222, 245, 255)
w = int(12 * u)
d.polygon([(L, T), (R - F, T), (R, T + F), (R, B), (L, B)], fill=page, outline=ink, width=w)
d.polygon([(R - F, T), (R - F, T + F), (R, T + F)], fill=fold, outline=ink, width=w)
d.line([(R - F, T), (R, T + F)], fill=ink, width=w)
logo = Image.open(f"{root}/packaging/icon.png").convert("RGBA")
size = int(250 * u)
logo = logo.resize((size, size), Image.LANCZOS)
x, y = int((L + R) / 2 - size / 2), int(B - size - 40 * u)
d.rectangle([x - w // 2, y - w // 2, x + size + w // 2, y + size + w // 2], fill=ink)
img.alpha_composite(logo, (x, y))
# three text lines above the logo
for i in range(3):
    yy = T + (70 + 40 * i) * u
    d.rounded_rectangle([L + 50 * u, yy, R - (70 if i == 0 else 50) * u - (F if i == 0 else 0), yy + 16 * u],
                        radius=8 * u, fill=(58, 140, 255, 255))
out = img.resize((512, 512), Image.LANCZOS)
out.save(f"{root}/packaging/file-icon.png", optimize=True)
out.save(f"{root}/packaging/file-icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
