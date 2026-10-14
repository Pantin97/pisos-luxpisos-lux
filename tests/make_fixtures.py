"""Genera alertas de ejemplo con la misma estructura HTML que los emails reales
de Immotop (bloques table.realEstateBlock). Los datos son los de las alertas
recibidas entre septiembre y octubre de 2026 para la búsqueda de compra."""
from pathlib import Path

BLOCK = """
  <table width="100%" class="realEstateBlock" align="center"><tr><td align="center" valign="top">
    <table width="280" class="realEstateBlock__imageContainer" align="left"><tr><td>
      <a title="{title}" href="{url}"><img class="realEstateBlock__image" src="https://www.immotop.lu/img/common/listing_image_placeholder.png"></a>
    </td></tr></table>
    <table width="250" class="realEstateBlock__dataContainer" align="left"><tr valign="top"><td>
      <table width="100%">
        <tr><td class="realEstateBlock__title" align="left"><a title="{title}" href="{url}">﻿{title}﻿</a></td></tr>
        <tr><td class="realEstateBlock__subtitle" align="left">
          {zone}
        </td></tr>
        <tr><td align="left" class="realEstateBlock__price">
          € {price}
        </td></tr>
        <tr><td align="left" class="realEstateBlock__features">
          {features}
        </td></tr>
      </table>
    </td></tr></table>
  </td></tr></table>"""

PAGE = """<!DOCTYPE html><html><head><meta charset="UTF-8"></head><body>
<p class="bodyMail__text">Bonjour <b>Juan</b>, <br><b>{n} nouvelles annonces </b> pour vos recherches <b>Casas en venta en Luxemburgo</b></p>
{blocks}
<table class="searchRecap"><tr><td class="searchRecap__title">Votre recherche</td></tr></table>
</body></html>"""

LIMPERTSBERG = ("Appartement 2 chambres 9, 9a, Rue Josephine Jacquemart-jaans. L-1874, Luxembourg, Limpertsberg, Luxembourg",
                "Limpertsberg", "1 047 740", "77 m&sup2; | 2 chambres/pièces")

ALERTS = {
    "2026-09-07_immotop.html": [
        ("Appartement 2 chambres troisième étage, Kirchberg, Luxembourg", "Kirchberg", "920 000",
         "88 m&sup2; | 2 chambres/pièces | 1 salle de bain"),
    ],
    "2026-09-14_immotop.html": [
        LIMPERTSBERG,
        ("Appartement 2 chambres 22, Rue Joséphine Jacquemart-Jaans, Belair, Luxembourg", "Belair", "1 047 740",
         "77 m&sup2; | 2 chambres/pièces | 1 salle de bain"),
    ],
    "2026-09-15_immotop.html": [
        ("Appartement 2 chambres deuxième étage, Ville Haute, Luxembourg", "Ville Haute", "900 000",
         "68 m&sup2; | 2 chambres/pièces"),
        ("Appartement 2 chambres premier étage, Ville Haute, Luxembourg", "Ville Haute", "1 025 000",
         "80 m&sup2; | 2 chambres/pièces"),
    ],
    "2026-09-25_immotop.html": [LIMPERTSBERG],
    "2026-10-07_immotop.html": [LIMPERTSBERG],
}


def build(dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, (name, items) in enumerate(ALERTS.items()):
        blocks = "".join(
            BLOCK.format(title=t, zone=z, price=p, features=f, url=f"https://clicks.immotop.lu/f/a/fixture-{i}-{j}")
            for j, (t, z, p, f) in enumerate(items))
        path = dest / name
        path.write_text(PAGE.format(n=len(items), blocks=blocks), encoding="utf-8")
        paths.append(path)
    return paths


if __name__ == "__main__":
    for p in build(Path(__file__).parent / "fixtures"):
        print(p)
