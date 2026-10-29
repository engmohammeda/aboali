#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
add_footer.py — العلامة المائية (الاسم + رقم الهاتف) لهوية «أبو عمر للسيراميك والبورسلان»
==========================================================================================
الهوية: أسود أونيكس  #0B0906   +   ذهبي شامبانيا  #FBEBC7 / #C9AA83  +   برونز  #B88650

تضيف نصّين فقط لا غير: اسم النشاط + رقم الهاتف. لا شعارات ولا أسعار ولا نصوص أخرى.

المتطلبات:  pip install pillow

أمثلة
-----
python add_footer.py photo.jpg                       # الافتراضي: ذهبي فاخر + توهّج
python add_footer.py ./images --out ./ready          # مجلد كامل
python add_footer.py a.jpg --palette goldbar         # شريط ذهبي ونص أسود
python add_footer.py a.jpg --mode band --height .10  # شريط مستقل (لا يغطي الصورة)
python add_footer.py a.jpg --no-glow --palette onyx  # بلا توهّج
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
except ImportError:
    sys.exit("خطأ: مكتبة Pillow غير مثبّتة.  نفّذ:  pip install pillow")

# ═══════════════════════════════════════════════════════════════════════════
#  هوية «أبو عمر للسيراميك والبورسلان» — مستخرجة من الغلاف وصورة الحساب
# ═══════════════════════════════════════════════════════════════════════════
ONYX       = (11, 9, 6)        # #0B0906  أسود أونيكس (الخلفية الأساسية)
ONYX_SOFT  = (23, 18, 11)      # #17120B  أسود مائل للبني
GOLD_HI    = (251, 235, 199)   # #FBEBC7  ذهبي فاتح (هايلايت النيون)
GOLD       = (234, 206, 165)   # #EACEA5  ذهبي شامبانيا
GOLD_MID   = (201, 170, 131)   # #C9AA83  ذهبي متوسط
GOLD_DEEP  = (184, 134, 80)    # #B88650  برونز ذهبي
BRONZE     = (92, 72, 47)      # #5C482F  برونز غامق
IVORY      = (246, 240, 230)   # عاجي

DEFAULTS = {
    "name":  "أبو عمر للسيراميك والبورسلان",
    "phone": "0566743293",
    "font":  None,
    "palette": "gold",      # gold | goldbar | onyx | navy | terra | dark | light | sand
    "mode": "overlay",      # overlay | band
    "height": 0.12,
    "quality": 92,
    "suffix": "_ad",
    "min_height": 64,
    "name_ratio": 0.46,
    "phone_ratio": 0.40,
    "gap_ratio": 0.22,
    "margin_ratio": 0.035,
    "glow": True,
}

# لوحات الألوان: خلفية / لون الاسم / لون الرقم / لون الفاصل / الشفافية / توهّج
PALETTES = {
    # ── هوية المشروع (المعتمدة) ──
    "gold": {
        "bg": ONYX, "name": GOLD_HI, "phone": GOLD,
        "rule_from": BRONZE, "rule_to": GOLD_HI,
        "alpha": 238, "glow": True, "glow_color": GOLD_DEEP, "glow_alpha": 120,
    },
    "goldbar": {   # شريط ذهبي متدرّج ونص أسود — للصور الفاتحة
        "bg": GOLD_MID, "name": ONYX, "phone": ONYX,
        "rule_from": GOLD_HI, "rule_to": BRONZE,
        "alpha": 245, "glow": False, "glow_color": GOLD_HI, "glow_alpha": 60,
    },
    "onyx": {      # أسود صافٍ بلا توهّج — الأكثر رصانة
        "bg": ONYX, "name": IVORY, "phone": GOLD_MID,
        "rule_from": BRONZE, "rule_to": GOLD_DEEP,
        "alpha": 235, "glow": False, "glow_color": GOLD_DEEP, "glow_alpha": 90,
    },
    # ── لوحات بديلة ──
    "navy":  {"bg": (31, 78, 121),   "name": (255, 255, 255), "phone": (201, 162, 39),
              "rule_from": (180, 85, 45), "rule_to": (201, 162, 39), "alpha": 232,
              "glow": False, "glow_color": (0, 0, 0), "glow_alpha": 80},
    "terra": {"bg": (180, 85, 45),   "name": (255, 255, 255), "phone": (255, 226, 168),
              "rule_from": (239, 231, 218), "rule_to": (255, 226, 168), "alpha": 235,
              "glow": False, "glow_color": (0, 0, 0), "glow_alpha": 80},
    "dark":  {"bg": (43, 43, 43),    "name": (255, 255, 255), "phone": (201, 162, 39),
              "rule_from": (180, 85, 45), "rule_to": (201, 162, 39), "alpha": 225,
              "glow": False, "glow_color": (0, 0, 0), "glow_alpha": 80},
    "light": {"bg": (239, 231, 218), "name": (31, 78, 121),   "phone": (140, 62, 32),
              "rule_from": (201, 162, 39), "rule_to": (140, 62, 32), "alpha": 240,
              "glow": False, "glow_color": (255, 255, 255), "glow_alpha": 60},
    "sand":  {"bg": (248, 244, 238), "name": (43, 43, 43),    "phone": (180, 85, 45),
              "rule_from": (31, 78, 121), "rule_to": (180, 85, 45), "alpha": 245,
              "glow": False, "glow_color": (255, 255, 255), "glow_alpha": 60},
}

EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

FONT_CANDIDATES = [
    "Tajawal-Bold.ttf", "Tajawal-Black.ttf", "Tajawal-Medium.ttf",
    "../assets/fonts/Tajawal-Bold.ttf",
    "../01-اصول-الهوية/fonts/Tajawal-Bold.ttf",
    "/usr/share/fonts/truetype/tajawal/Tajawal-Bold.ttf",
    "Cairo-Bold.ttf", "NotoNaskhArabic-Bold.ttf", "NotoSansArabic-Bold.ttf",
    "Amiri-Bold.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf",
]


# ═══════════════════════════════════════════════════════════════════════════
#  أدوات مساعدة
# ═══════════════════════════════════════════════════════════════════════════
def find_font(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.exists():
            sys.exit(f"خطأ: ملف الخط غير موجود: {p}")
        return p
    here = Path(__file__).resolve().parent
    for cand in FONT_CANDIDATES:
        for base in (here, Path.cwd()):
            p = (base / cand).resolve()
            if p.exists():
                return p
    for root in ("/usr/share/fonts", "/usr/local/share/fonts",
                 str(Path.home() / ".fonts"), str(Path.home() / "Library/Fonts"),
                 "C:/Windows/Fonts"):
        rp = Path(root)
        if not rp.is_dir():
            continue
        for pat in ("*Tajawal*Bold*.ttf", "*Cairo*Bold*.ttf", "*Arabic*Bold*.ttf",
                    "*DejaVuSans*.ttf"):
            hits = sorted(rp.rglob(pat))
            if hits:
                return hits[0]
    sys.exit("خطأ: لم أجد خطًا عربيًا. مرّر المسار يدويًا:  --font /path/Tajawal-Bold.ttf")


def parse_hex(value: str) -> tuple[int, int, int]:
    v = value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6:
        raise argparse.ArgumentTypeError(f"لون HEX غير صالح: {value}")
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))


def hexof(c: tuple[int, int, int]) -> str:
    return "#%02X%02X%02X" % c


def gradient_image(w: int, h: int, c1: tuple[int, int, int], c2: tuple[int, int, int]) -> Image.Image:
    """تدرّج أفقي سريع (يُبنى بعرض 256 ثم يُمدّ)."""
    strip = Image.new("RGB", (256, 1))
    px = strip.load()
    for x in range(256):
        t = x / 255
        px[x, 0] = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
    return strip.resize((max(1, w), max(1, h)), Image.BILINEAR)


def load_image(path: Path) -> Image.Image:
    img = Image.open(path)
    img.load()
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
    else:
        img = img.convert("RGB")
    return img


# ═══════════════════════════════════════════════════════════════════════════
#  التخطيط وأحجام الخطوط
# ═══════════════════════════════════════════════════════════════════════════
def fit_single(draw, text, max_w: int, font_path: Path, size: int,
               rtl: bool = False, min_size: int = 12) -> ImageFont.FreeTypeFont:
    kw = {"direction": "rtl", "language": "ar"} if rtl else {"direction": "ltr"}
    f = ImageFont.truetype(str(font_path), size)
    for _ in range(80):
        if draw.textlength(text, font=f, **kw) <= max_w or f.size <= min_size:
            return f
        size = int(size * 0.95)
        f = ImageFont.truetype(str(font_path), max(1, size))
    return f


def plan_layout(draw, name: str, phone: str, bar_h: int, box_w: int, font_path: Path,
                name_ratio: float, phone_ratio: float, gap_ratio: float):
    """row = صف واحد | stack = صفّان (للأسماء الطويلة)."""
    base_name = max(12, int(bar_h * name_ratio))
    base_phone = max(12, int(bar_h * phone_ratio))
    f_n0 = ImageFont.truetype(str(font_path), base_name)
    f_p0 = ImageFont.truetype(str(font_path), base_phone)
    w_n0 = draw.textlength(name, font=f_n0, direction="rtl", language="ar")
    w_p0 = draw.textlength(phone, font=f_p0, direction="ltr")
    gap0 = int(max(w_n0, w_p0) * gap_ratio)

    if w_n0 + w_p0 + gap0 <= box_w:
        return ("row", f_n0, f_p0, gap0)

    scale = 0.88
    while scale >= 0.72:
        ns, ps = max(12, int(base_name * scale)), max(12, int(base_phone * scale))
        f_n, f_p = ImageFont.truetype(str(font_path), ns), ImageFont.truetype(str(font_path), ps)
        w_n = draw.textlength(name, font=f_n, direction="rtl", language="ar")
        w_p = draw.textlength(phone, font=f_p, direction="ltr")
        if w_n + w_p + int(max(w_n, w_p) * gap_ratio) <= box_w:
            return ("row", f_n, f_p, int(max(w_n, w_p) * gap_ratio))
        scale -= 0.04

    f_n = fit_single(draw, name, box_w, font_path, max(12, int(bar_h * 0.46)), rtl=True)
    f_p = fit_single(draw, phone, box_w, font_path, max(12, int(bar_h * 0.38)))
    while f_n.size + f_p.size + 10 > bar_h * 0.92 and min(f_n.size, f_p.size) > 12:
        f_n = ImageFont.truetype(str(font_path), max(12, int(f_n.size * 0.92)))
        f_p = ImageFont.truetype(str(font_path), max(12, int(f_p.size * 0.92)))
    return ("stack", f_n, f_p, 0)


# ═══════════════════════════════════════════════════════════════════════════
#  الرسم
# ═══════════════════════════════════════════════════════════════════════════
def render(img: Image.Image, cfg: dict, font_path: Path, pal: dict,
           bg_override=None) -> tuple[Image.Image, dict]:
    w, h = img.size
    bar_h = max(cfg["min_height"], int(h * cfg["height"]))
    bar_h = min(bar_h, max(cfg["min_height"], int(h * 0.35)))
    margin = max(12, int(w * cfg["margin_ratio"]))
    box_w = w - margin * 2

    bg = bg_override or pal["bg"]
    is_rgba = img.mode == "RGBA"

    # ── تهيئة اللوحة ──
    if cfg["mode"] == "band":
        canvas = Image.new("RGBA", (w, h + bar_h), (0, 0, 0, 0))
        canvas.paste(img.convert("RGBA"), (0, 0))
        top, text_mid = h, h + bar_h // 2
    else:
        canvas = img.convert("RGBA")
        top, text_mid = h - bar_h, h - bar_h // 2

    bar = Image.new("RGBA", (w, bar_h), bg + (255,))
    # إضاءة خفيفة أعلى الشريط وأسفله (يعطي إحساس النيون الذهبي في الهوية)
    shade = Image.new("RGBA", (w, bar_h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for y in range(bar_h):
        t = abs(y - bar_h / 2) / (bar_h / 2)
        a = int(26 * t * t)
        if a:
            sd.line([(0, y), (w, y)], fill=(0, 0, 0, a))
    bar = Image.alpha_composite(bar, shade)

    # الفاصل الذهبي المتدرّج أعلى الشريط
    rule_h = max(2, bar_h // 34)
    rule = gradient_image(w, rule_h, pal["rule_from"], pal["rule_to"]).convert("RGBA")
    bar.paste(rule, (0, 0))

    if cfg["mode"] == "overlay":
        # تدرّج تمهيدي فوق الصورة قبل الشريط
        fade = max(10, bar_h // 2)
        fo = Image.new("RGBA", (w, fade), (0, 0, 0, 0))
        fd = ImageDraw.Draw(fo)
        for y in range(fade):
            fd.line([(0, y), (w, y)], fill=bg + (int(pal["alpha"] * (y / fade) ** 1.7),))
        canvas.alpha_composite(fo, (0, top - fade))

    bar.putalpha(pal["alpha"])
    canvas.alpha_composite(bar, (0, top))
    draw = ImageDraw.Draw(canvas)

    layout, f_name, f_phone, gap = plan_layout(
        draw, cfg["name"], cfg["phone"], bar_h, box_w, font_path,
        cfg["name_ratio"], cfg["phone_ratio"], cfg["gap_ratio"]
    )

    # ── تحديد مواضع النص ──
    if layout == "row":
        name_xy = (w - margin, text_mid, "rm")
        phone_xy = (margin, text_mid, "lm")
    else:
        h_name = f_name.getbbox(cfg["name"], direction="rtl", language="ar")[3]
        h_phone = f_phone.size
        gap_v = max(4, int(bar_h * 0.06))
        y0 = text_mid - (h_name + h_phone + gap_v) // 2
        name_xy = (w // 2, y0, "ma")
        phone_xy = (w // 2, y0 + h_name + gap_v, "ma")

    # ── التوهّج الذهبي (اختياري) ──
    if cfg["glow"] and pal.get("glow"):
        glow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow_layer)
        gd.text((name_xy[0], name_xy[1]), cfg["name"], font=f_name,
                fill=pal["glow_color"] + (255,), anchor=name_xy[2],
                direction="rtl", language="ar")
        gd.text((phone_xy[0], phone_xy[1]), cfg["phone"], font=f_phone,
                fill=pal["glow_color"] + (255,), anchor=phone_xy[2], direction="ltr")
        radius = max(2, int(f_name.size * 0.16))
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius))
        alpha = glow_layer.getchannel("A").point(lambda a: int(a * pal["glow_alpha"] / 255))
        glow_layer.putalpha(alpha)
        canvas.alpha_composite(glow_layer)
        draw = ImageDraw.Draw(canvas)

    # ── النص الحاد ──
    draw.text((name_xy[0], name_xy[1]), cfg["name"], font=f_name,
              fill=pal["name"], anchor=name_xy[2], direction="rtl", language="ar")
    draw.text((phone_xy[0], phone_xy[1]), cfg["phone"], font=f_phone,
              fill=pal["phone"], anchor=phone_xy[2], direction="ltr")

    canvas = canvas.convert("RGBA") if is_rgba else canvas.convert("RGB")
    return canvas, {"layout": layout, "bar_h": bar_h, "font": f_name.size}


# ═══════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════
def output_path(src: Path, out_dir: Path | None, suffix: str, force_fmt: str | None) -> Path:
    ext = src.suffix.lower()
    if force_fmt:
        ext = "." + force_fmt.lstrip(".").lower()
    elif ext == ".jpeg":
        ext = ".jpg"
    d = out_dir if out_dir else src.parent
    d.mkdir(parents=True, exist_ok=True)
    return d / (src.stem + suffix + ext)


def collect_inputs(args_inputs: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in args_inputs:
        p = Path(raw).expanduser()
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix.lower() in EXTS and not f.stem.endswith("_ad"):
                    files.append(f)
        elif p.is_file():
            files.append(p)
        else:
            print(f"⚠️  تم تجاهل مسار غير موجود: {raw}", file=sys.stderr)
    seen, unique = set(), []
    for f in files:
        k = f.resolve()
        if k not in seen:
            seen.add(k)
            unique.append(f)
    return unique


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="العلامة المائية لهوية أبو عمر للسيراميك والبورسلان (الاسم + رقم الهاتف فقط).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""أمثلة:
  python add_footer.py photo.jpg
  python add_footer.py ./images --out ./ready --palette gold
  python add_footer.py *.jpg --mode band --height 0.10 --no-glow
""")
    p.add_argument("inputs", nargs="+", help="ملف صورة أو مجلد (يمكن تمرير عدة مسارات)")
    p.add_argument("--name", default=DEFAULTS["name"], help="اسم النشاط")
    p.add_argument("--phone", default=DEFAULTS["phone"], help="رقم الهاتف")
    p.add_argument("--out", default=None, help="مجلد الإخراج")
    p.add_argument("--font", default=DEFAULTS["font"], help="مسار ملف الخط .ttf")
    p.add_argument("--palette", default=DEFAULTS["palette"], choices=sorted(PALETTES),
                   help="لوحة الألوان (افتراضي: %(default)s)")
    p.add_argument("--mode", default=DEFAULTS["mode"], choices=["overlay", "band"],
                   help="overlay = فوق الصورة | band = يمدّ الصورة")
    p.add_argument("--bg", default=None, help='لون الخلفية HEX مثل "#0B0906"')
    p.add_argument("--height", type=float, default=DEFAULTS["height"],
                   help="ارتفاع الشريط كنسبة من ارتفاع الصورة")
    p.add_argument("--quality", type=int, default=DEFAULTS["quality"], help="جودة JPG")
    p.add_argument("--suffix", default=DEFAULTS["suffix"], help="لاحقة اسم الملف الناتج")
    p.add_argument("--format", default=None, choices=["jpg", "png", "webp"], help="صيغة الإخراج")
    p.add_argument("--glow", dest="glow", action="store_true", default=DEFAULTS["glow"],
                   help="تفعيل التوهّج الذهبي (افتراضي للهوية)")
    p.add_argument("--no-glow", dest="glow", action="store_false", help="إيقاف التوهّج")
    p.add_argument("--dry-run", action="store_true", help="تجربة بلا حفظ")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    font_path = find_font(args.font)
    pal = dict(PALETTES[args.palette])
    bg_override = parse_hex(args.bg) if args.bg else None

    cfg = {
        "name": args.name.strip(), "phone": args.phone.strip(), "mode": args.mode,
        "height": args.height, "quality": max(1, min(100, args.quality)),
        "name_ratio": DEFAULTS["name_ratio"], "phone_ratio": DEFAULTS["phone_ratio"],
        "gap_ratio": DEFAULTS["gap_ratio"], "margin_ratio": DEFAULTS["margin_ratio"],
        "min_height": DEFAULTS["min_height"], "glow": args.glow,
    }

    files = collect_inputs(args.inputs)
    if not files:
        print("⚠️  لا توجد صور للمعالجة.", file=sys.stderr)
        return 1

    out_dir = Path(args.out).expanduser() if args.out else None

    print("═" * 64)
    print("  🏷️  العلامة المائية — أبو عمر للسيراميك والبورسلان")
    print("═" * 64)
    print(f"  الاسم    : {cfg['name']}")
    print(f"  الهاتف   : {cfg['phone']}")
    print(f"  الخط      : {font_path.name}")
    print(f"  اللوحة   : {args.palette}  (خلفية {hexof(bg_override or pal['bg'])}"
          f" | اسم {hexof(pal['name'])} | رقم {hexof(pal['phone'])})")
    print(f"  النمط    : {cfg['mode']}  |  توهّج: {'نعم' if cfg['glow'] else 'لا'}")
    print(f"  الصور    : {len(files)}" + ("   ⚠️ وضع التجربة" if args.dry_run else ""))
    print("─" * 64)

    ok, failed = 0, []
    for i, src in enumerate(files, 1):
        try:
            img = load_image(src)
            result, rep = render(img, cfg, font_path, pal, bg_override)
            line = (f"  [{i:>2}/{len(files)}] {src.name[:36]:<36} "
                    f"{img.size[0]}×{img.size[1]} → شريط {rep['bar_h']}px "
                    f"({rep['layout']}, خط {rep['font']})")
            if not args.dry_run:
                dst = output_path(src, out_dir, args.suffix, args.format)
                ext = dst.suffix.lower()
                if ext in (".jpg", ".jpeg"):
                    result.convert("RGB").save(dst, quality=cfg["quality"],
                                               subsampling=0, optimize=True, progressive=True)
                elif ext == ".webp":
                    result.save(dst, quality=cfg["quality"], method=6)
                else:
                    result.save(dst, optimize=True)
                line += f"\n            ↳ {dst}"
            print(line)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            failed.append((src, exc))
            print(f"  [{i:>2}/{len(files)}] ❌ {src.name}: {exc}")

    print("─" * 64)
    print(f"  ✅ تم: {ok}" + (f"   |   ❌ فشل: {len(failed)}" if failed else ""))
    if out_dir and not args.dry_run:
        print(f"  📁 الإخراج: {out_dir.resolve()}")
    print("═" * 64)
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
