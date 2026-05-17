import io
import os
import urllib.request
import urllib.error

try:
    from fontTools.varLib.instancer import instantiateVariableFont, OverlapMode
    from fontTools.ttLib import TTFont
    HAS_INSTANCER = True
except ImportError:
    HAS_INSTANCER = False

OUTPUT_DIR = r"D:\PROJECTS\mirubrodigital\services\api\src\assets\fonts\posters"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE = "https://raw.githubusercontent.com/google/fonts/main/ofl"

FONT_SPECS = [
    # (family_dir, var_filename, output_prefix, weights)
    ("cinzel",              "Cinzel[wght].ttf",              "Cinzel",               [400, 700, 900]),
    ("montserrat",          "Montserrat[wght].ttf",          "Montserrat",           [400, 700, 900]),
    ("raleway",             "Raleway[wght].ttf",             "Raleway",              [400, 700, 900]),
    ("playfairdisplay",     "PlayfairDisplay[wght].ttf",     "PlayfairDisplay",      [400, 700, 900]),
    ("worksans",            "WorkSans[wght].ttf",            "WorkSans",             [400, 700, 900]),
    ("oswald",              "Oswald[wght].ttf",              "Oswald",               [400, 700]),
    ("cormorantgaramond",   "CormorantGaramond[wght].ttf",   "CormorantGaramond",    [400, 700]),
    ("librebaskerville",    "LibreBaskerville[wght].ttf",    "LibreBaskerville",     [400, 700]),
]

WEIGHT_NAMES = {400: "Regular", 700: "Bold", 900: "Black"}

def download_font(family_dir, filename):
    url = f"{BASE}/{family_dir}/{filename}"
    print(f"  Downloading {url} ...", end=" ", flush=True)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = resp.read()
        print(f"OK ({len(data)} bytes)")
        return io.BytesIO(data)
    except urllib.error.HTTPError as e:
        print(f"FAIL ({e.code})")
        return None

def instantiate_weight(font_buf, weight, output_prefix):
    if not HAS_INSTANCER:
        print("  fonttools instancer not available, skipping")
        return False
    weight_name = WEIGHT_NAMES.get(weight, str(weight))
    out_path = os.path.join(OUTPUT_DIR, f"{output_prefix}-{weight_name}.ttf")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 10000:
        print(f"  {output_prefix}-{weight_name}.ttf already exists, skipping")
        return True
    try:
        font_buf.seek(0)
        tt = TTFont(font_buf)
        # Check if it has a variable axis
        if "fvar" in tt:
            font_buf.seek(0)
            tt2 = TTFont(font_buf)
            instanced = instantiateVariableFont(tt2, {"wght": weight}, overlap=OverlapMode.REMOVE)
            instanced.save(out_path)
        else:
            # Not variable, just copy as-is at the closest weight
            font_buf.seek(0)
            tt.save(out_path)
        size = os.path.getsize(out_path)
        print(f"  Saved {output_prefix}-{weight_name}.ttf ({size} bytes)")
        return True
    except Exception as e:
        print(f"  ERROR instantiating {output_prefix}-{weight_name}: {e}")
        return False

ok = 0
fail = 0
for family_dir, var_filename, output_prefix, weights in FONT_SPECS:
    print(f"\n=== {output_prefix} ({family_dir}) ===")
    font_buf = download_font(family_dir, var_filename)
    if font_buf is None:
        # Try without variable suffix
        alt_name = var_filename.replace("[wght]", "").replace(".ttf", "-Regular.ttf")
        font_buf = download_font(family_dir, alt_name)
    if font_buf is None:
        print(f"  Could not download {var_filename}")
        fail += len(weights)
        continue
    for weight in weights:
        result = instantiate_weight(font_buf, weight, output_prefix)
        if result:
            ok += 1
        else:
            fail += 1

print(f"\n=== SUMMARY: {ok} OK, {fail} FAILED ===")
