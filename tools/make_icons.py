"""Genera los iconos de la app (docs/icons)."""
from pathlib import Path
from PIL import Image, ImageDraw

S = 1024
img = Image.new("RGB", (S, S), "#0a6896")
d = ImageDraw.Draw(img)
white, slate = "#ffffff", "#163447"
# tres casas de la Ville Haute: tejados de pizarra, fachadas blancas
houses = [(170, 470, 300), (390, 360, 280), (590, 520, 260)]   # x, alero (y), ancho
for x, eave, w in houses:
    d.rectangle([x, eave, x + w, 820], fill=white)
    d.polygon([(x - 18, eave), (x + w / 2, eave - w * 0.55), (x + w + 18, eave)], fill=slate)
    # ventanas
    for row in range(2):
        for col in range(2):
            wx = x + w * (0.22 + col * 0.36)
            wy = eave + 60 + row * 120
            if wy + 70 < 800:
                d.rectangle([wx, wy, wx + w * 0.2, wy + 70], fill="#0a6896")
d.rectangle([120, 820, 904, 850], fill=white)
out = Path(__file__).resolve().parent.parent / "docs" / "icons"
out.mkdir(parents=True, exist_ok=True)
for name, size in [("icon-512.png", 512), ("icon-192.png", 192), ("apple-touch-icon.png", 180)]:
    img.resize((size, size), Image.LANCZOS).save(out / name, optimize=True)
print("ok")
