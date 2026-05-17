# Poster Fonts — Google Fonts (SIL Open Font License)

These TTF files are used by ReportLab to render custom typography in QR poster PDFs.
They are registered at runtime via `pdfmetrics.registerFont(TTFont(...))` in `qr_posters.py`.

All fonts are sourced from [Google Fonts](https://fonts.google.com/) and are licensed under the
**SIL Open Font License 1.1** (OFL-1.1), which permits use in commercial applications and embedding
in documents (including PDFs).  Full license text: https://scripts.sil.org/OFL

Static weight TTF files were generated from Google Fonts variable fonts using
[fonttools](https://github.com/fonttools/fonttools) `varLib.instancer`.

---

## Font Index

| File | Family | Weight | CSS Weight | Source |
|------|--------|--------|------------|--------|
| Cinzel-Regular.ttf | Cinzel | Regular | 400 | https://fonts.google.com/specimen/Cinzel |
| Cinzel-Bold.ttf | Cinzel | Bold | 700 | https://fonts.google.com/specimen/Cinzel |
| Cinzel-Black.ttf | Cinzel | Black | 900 | https://fonts.google.com/specimen/Cinzel |
| Montserrat-Regular.ttf | Montserrat | Regular | 400 | https://fonts.google.com/specimen/Montserrat |
| Montserrat-Bold.ttf | Montserrat | Bold | 700 | https://fonts.google.com/specimen/Montserrat |
| Montserrat-Black.ttf | Montserrat | Black | 900 | https://fonts.google.com/specimen/Montserrat |
| Poppins-Regular.ttf | Poppins | Regular | 400 | https://fonts.google.com/specimen/Poppins |
| Poppins-Bold.ttf | Poppins | Bold | 700 | https://fonts.google.com/specimen/Poppins |
| Poppins-Black.ttf | Poppins | Black | 900 | https://fonts.google.com/specimen/Poppins |
| Raleway-Regular.ttf | Raleway | Regular | 400 | https://fonts.google.com/specimen/Raleway |
| Raleway-Bold.ttf | Raleway | Bold | 700 | https://fonts.google.com/specimen/Raleway |
| Raleway-Black.ttf | Raleway | Black | 900 | https://fonts.google.com/specimen/Raleway |
| PlayfairDisplay-Regular.ttf | Playfair Display | Regular | 400 | https://fonts.google.com/specimen/Playfair+Display |
| PlayfairDisplay-Bold.ttf | Playfair Display | Bold | 700 | https://fonts.google.com/specimen/Playfair+Display |
| PlayfairDisplay-Black.ttf | Playfair Display | Black | 900 | https://fonts.google.com/specimen/Playfair+Display |
| WorkSans-Regular.ttf | Work Sans | Regular | 400 | https://fonts.google.com/specimen/Work+Sans |
| WorkSans-Bold.ttf | Work Sans | Bold | 700 | https://fonts.google.com/specimen/Work+Sans |
| WorkSans-Black.ttf | Work Sans | Black | 900 | https://fonts.google.com/specimen/Work+Sans |
| Lato-Regular.ttf | Lato | Regular | 400 | https://fonts.google.com/specimen/Lato |
| Lato-Bold.ttf | Lato | Bold | 700 | https://fonts.google.com/specimen/Lato |
| Lato-Black.ttf | Lato | Black | 900 | https://fonts.google.com/specimen/Lato |
| Oswald-Regular.ttf | Oswald | Regular | 400 | https://fonts.google.com/specimen/Oswald |
| Oswald-Bold.ttf | Oswald | Bold | 700 | https://fonts.google.com/specimen/Oswald |
| CormorantGaramond-Regular.ttf | Cormorant Garamond | Regular | 400 | https://fonts.google.com/specimen/Cormorant+Garamond |
| CormorantGaramond-Bold.ttf | Cormorant Garamond | Bold | 700 | https://fonts.google.com/specimen/Cormorant+Garamond |
| LibreBaskerville-Regular.ttf | Libre Baskerville | Regular | 400 | https://fonts.google.com/specimen/Libre+Baskerville |
| LibreBaskerville-Bold.ttf | Libre Baskerville | Bold | 700 | https://fonts.google.com/specimen/Libre+Baskerville |

**Note:** Oswald, Cormorant Garamond, and Libre Baskerville do not include a Black (900) weight.
Requests for those families at `font_weight='black'` automatically normalize to `bold` in `resolve_poster_font()`.

---

## Regenerating Fonts

If fonts need to be re-generated (e.g. to update to a newer version), run:

```bash
pip install fonttools skia-pathops requests
python generate_fonts.py   # from repo root
```
