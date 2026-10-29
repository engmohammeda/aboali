#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
add_footer.py — أداة إضافة الاسم ورقم الهاتف أسفل صور الإعلانات
=================================================================
تضيف نصّين فقط لا غير:  اسم النشاط  +  رقم الهاتف.
لا شعارات، لا أسعار، لا أي نصوص إضافية.

المتطلبات:  pip install pillow

أمثلة الاستخدام
---------------
# صورة واحدة
python add_footer.py photo.jpg

# مجلد كامل (كل الصور بداخله)
python add_footer.py ./ad-images --out ./ready

# مجموعة ملفات + ألوان مخصصة
python add_footer.py a.jpg b.jpg c.png --palette terra --height 0.13

# شريط يمدّ الصورة للأسفل بدل التغطية عليها
python add_footer.py ./ad-images --mode band --bg "#1F4E79"

# تجربة بدون حفظ (لمعرفة إن كان النص سيتسع)
python add_footer.py photo.jpg --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:
    sys.exit("خطأ: مكتبة Pillow غير مثبّتة.  نفّذ:  pip install pillow")

# ----------------------------------------------------------------------------
# الإعدادات الافتراضية — عدّلها مرة واحدة هنا إن أردت
# ----------------------------------------------------------------------------
DEFAULTS = {
    "name":  "أبو عمر للسيراميك والبورسلان",
    "phone": "0566743293",
    "font":  None,            # None = يبحث تلقائيًا عن Tajawal ثم Cairo ثم خط النظام
    "palette": "navy",        # navy | terra | dark | light | sand
    "mode": "overlay",        # overlay = شريط فوق الصورة | band = شريط يمدّ الصورة
    "height": 0.12,           # نسبة ارتفاع الشريط من ارتفاع الصورة
    "quality": 92,            # جودة JPG
    "suffix": "_ad",          # لاحقة اسم الملف الناتج
    "min_height": 64,         # أقل ارتفاع شريط بالبكسل
    "name_ratio": 0.46,       # حجم خط الاسم = ارتفاع الشريط × هذه النسبة
    "phone_ratio": 0.40,
    "gap_ratio": 0.22,        # المسافة بين الاسم والرقم
    "margin_ratio": 0.035,    # الهامش الجانبي
}

PALETTES = {
    #            خلفية الشريط            لون الاسم        لون الرقم     الفاصل
    "navy":  {"bg": (31, 78, 121),   "name": (255, 255, 255), "phone": (201, 162, 39), "rule": (180, 85, 45),  "alpha": 232},
    "terra": {"bg": (180, 85, 45),   "name": (255, 255, 255), "phone": (255, 226, 168), "rule": (239, 231, 218), "alpha": 235},
    "dark":  {"bg": (43, 43, 43),    "name": (255, 255, 255), "phone": (201, 162, 39), "rule": (180, 85, 45),  "alpha": 225},
    "light": {"bg": (239, 231, 218), "name": (31, 78, 121),   "phone": (140, 62, 32),  "rule": (201, 162, 39), "alpha": 240},
    "sand":  {"bg": (248, 244, 238), "name": (43, 43, 43),    "phone": (180, 85, 45),  "rule": (31, 78, 121),  "alpha": 245},
}

EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

FONT_CANDIDATES = [
    # مسارات شائعة لخط Tajawal (خط الهوية المعتمد)
    "Tajawal-Bold.ttf", "Tajawal-Black.ttf", "Tajawal-Medium.ttf",
    "../assets/fonts/Tajawal-Bold.ttf",
    "../01-اصول-الهوية/fonts/Tajawal-Bold.ttf",
    "/usr/share/fonts/truetype/tajawal/Tajawal-Bold.ttf",
    # بدائل عربية
    "Cairo-Bold.ttf", "NotoNaskhArabic-Bold.ttf", "NotoSansArabic-Bold.ttf",
    "Amiri-Bold.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf",
]


# ----------------------------------------------------------------------------
# أدوات مساعدة
# ----------------------------------------------------------------------------
def find_font(explicit: str | None) -> Path:
    """تحديد ملف الخط: الممرّر صراحةً، ثم مسارات البحث، ثم خط النظام."""
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

    # بحث سريع في مجلدات الخطوط
    for root in ("/usr/share/fonts", "/usr/local/share/fonts", str(Path.home() / ".fonts"),
                 str(Path.home() / "Library/Fonts"), "C:/Windows/Fonts"):
        rp = Path(root)
        if not rp.is_dir():
            continue
        for pat in ("*Tajawal*Bold*.ttf", "*Cairo*Bold*.ttf", "*Arabic*Bold*.ttf", "*DejaVuSans*.ttf"):
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


def load_image(path: Path) -> Image.Image:
    """فتح الصورة + تصحيح اتجاه EXIF + تحويل لوضع آمن للرسم."""
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


def fit_single(draw, text, max_w: int, font_path: Path, size: int,
               rtl: bool = False, min_size: int = 12) -> ImageFont.FreeTypeFont:
    """تصغير خط نص واحد حتى يدخل في العرض المتاح."""
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
    """
    تحديد التخطيط وأحجام الخطوط:
      row   = الاسم يمينًا والرقم يسارًا في صف واحد
      stack = الاسم في سطر والرقم في سطر تحته (للأسماء الطويلة أو الصور الضيقة)
    الحد الأدنى المقبول للتصغير في وضع الصف هو 72% من الحجم الأساسي،
    فإن لم يتّسع ننتقل إلى وضع الصفّين بدل تصغير غير مقروء.
    """
    base_name = max(12, int(bar_h * name_ratio))
    base_phone = max(12, int(bar_h * phone_ratio))
    w_name0 = draw.textlength(name, font=ImageFont.truetype(str(font_path), base_name),
                              direction="rtl", language="ar")
    w_phone0 = draw.textlength(phone, font=ImageFont.truetype(str(font_path), base_phone),
                               direction="ltr")
    gap0 = int(max(w_name0, w_phone0) * gap_ratio)

    # 1) صف واحد بالحجم الأساسي
    if w_name0 + w_phone0 + gap0 <= box_w:
        return ("row", ImageFont.truetype(str(font_path), base_name),
                ImageFont.truetype(str(font_path), base_phone), gap0)

    # 2) صف واحد بتصغير محدود (حتى 72%)
    scale = 0.88
    while scale >= 0.72:
        ns, ps = max(12, int(base_name * scale)), max(12, int(base_phone * scale))
        f_n, f_p = ImageFont.truetype(str(font_path), ns), ImageFont.truetype(str(font_path), ps)
        w_n = draw.textlength(name, font=f_n, direction="rtl", language="ar")
        w_p = draw.textlength(phone, font=f_p, direction="ltr")
        if w_n + w_p + int(max(w_n, w_p) * gap_ratio) <= box_w:
            return ("row", f_n, f_p, int(max(w_n, w_p) * gap_ratio))
        scale -= 0.04

    # 3) صفّان: كل نص يأخذ عرض الصورة كاملًا
    f_n = fit_single(draw, name, box_w, font_path, max(12, int(bar_h * 0.46)), rtl=True)
    f_p = fit_single(draw, phone, box_w, font_path, max(12, int(bar_h * 0.38)))
    # ضمان عدم تجاوز ارتفاع الشريط (سطران + فراغ)
    while f_n.size + f_p.size + 10 > bar_h * 0.92 and min(f_n.size, f_p.size) > 12:
        f_n = ImageFont.truetype(str(font_path), max(12, int(f_n.size * 0.92)))
        f_p = ImageFont.truetype(str(font_path), max(12, int(f_p.size * 0.92)))
    return ("stack", f_n, f_p, 0)


def render(img: Image.Image, cfg: dict, font_path: Path, pal: dict,
           bg_override=None) -> tuple[Image.Image, dict]:
    """رسم الشريط وإرجاع الصورة الناتجة + تقرير."""
    w, h = img.size
    bar_h = max(cfg["min_height"], int(h * cfg["height"]))
    # لا يتجاوز الشريط 35% من الصورة (منعًا لطمس الإعلان)
    bar_h = min(bar_h, max(cfg["min_height"], int(h * 0.35)))

    margin = max(12, int(w * cfg["margin_ratio"]))
    box_w = w - margin * 2

    bg = bg_override or pal["bg"]
    is_rgba = img.mode == "RGBA"

    if cfg["mode"] == "band":
        # تمديد الصورة: الشريط أسفل الصورة بلا تغطية أي جزء منها
        canvas = Image.new("RGBA" if is_rgba else "RGB", (w, h + bar_h),
                           (0, 0, 0, 0) if is_rgba else bg)
        canvas.paste(img, (0, 0))
        draw = ImageDraw.Draw(canvas)
        top = h
        draw.rectangle([0, top, w, h + bar_h], fill=bg)
        # خط تمييز رقيق أعلى الشريط
        draw.rectangle([0, top, w, top + max(2, bar_h // 40)], fill=pal["rule"])
        text_mid = top + bar_h // 2
    else:
        # تراكب: الشريط فوق الجزء السفلي من الصورة
        canvas = img.copy()
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        top = h - bar_h
        # تدرّج ناعم أعلى الشريط لتحسين قراءة النص
        fade = max(8, bar_h // 3)
        for i in range(fade):
            a = int(pal["alpha"] * (i / fade) ** 1.5)
            od.rectangle([0, top - fade + i, w, top - fade + i + 1], fill=bg + (a,))
        od.rectangle([0, top, w, h], fill=bg + (pal["alpha"],))
        od.rectangle([0, top, w, top + max(2, bar_h // 40)], fill=pal["rule"] + (255,))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay)
        text_mid = top + bar_h // 2

    draw = ImageDraw.Draw(canvas)
    layout, f_name, f_phone, gap = plan_layout(
        draw, cfg["name"], cfg["phone"], bar_h, box_w, font_path,
        cfg["name_ratio"], cfg["phone_ratio"], cfg["gap_ratio"]
    )

    right, left = w - margin, margin

    if layout == "row":
        # الاسم يمينًا (اتجاه RTL) والرقم يسارًا
        draw.text((right, text_mid), cfg["name"], font=f_name, fill=pal["name"],
                  anchor="rm", direction="rtl", language="ar")
        draw.text((left, text_mid), cfg["phone"], font=f_phone, fill=pal["phone"],
                  anchor="lm", direction="ltr")
    else:
        # صفّان: الاسم أعلى والرقم تحته، كلاهما في الوسط
        h_name = f_name.getbbox(cfg["name"], direction="rtl", language="ar")[3]
        h_phone = f_phone.size
        gap_v = max(4, int(bar_h * 0.06))
        total = h_name + h_phone + gap_v
        y0 = text_mid - total // 2
        draw.text((w // 2, y0), cfg["name"], font=f_name, fill=pal["name"],
                  anchor="ma", direction="rtl", language="ar")
        draw.text((w // 2, y0 + h_name + gap_v), cfg["phone"], font=f_phone,
                  fill=pal["phone"], anchor="ma", direction="ltr")

    if cfg["mode"] == "band" and not is_rgba:
        canvas = canvas.convert("RGB")
    elif is_rgba:
        canvas = canvas.convert("RGBA")

    report = {"layout": layout, "bar_h": bar_h, "font": f_name.size}
    return canvas, report


def output_path(src: Path, out_dir: Path | None, suffix: str, force_fmt: str | None) -> Path:
    stem = src.stem + suffix
    ext = src.suffix.lower()
    if force_fmt:
        ext = "." + force_fmt.lstrip(".").lower()
    elif ext == ".jpeg":
        ext = ".jpg"
    target_dir = out_dir if out_dir else src.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / (stem + ext)


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
    # إزالة التكرار مع الحفاظ على الترتيب
    seen, unique = set(), []
    for f in files:
        k = f.resolve()
        if k not in seen:
            seen.add(k)
            unique.append(f)
    return unique


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="إضافة الاسم ورقم الهاتف أسفل صور الإعلانات (نصّان فقط، بلا أي إضافات).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""أمثلة:
  python add_footer.py photo.jpg
  python add_footer.py ./ad-images --out ./ready --palette terra
  python add_footer.py *.jpg --mode band --bg "#1F4E79"
""",
    )
    p.add_argument("inputs", nargs="+", help="ملف صورة أو مجلد (يمكن تمرير عدة مسارات)")
    p.add_argument("--name", default=DEFAULTS["name"], help="اسم النشاط (الافتراضي: %(default)s)")
    p.add_argument("--phone", default=DEFAULTS["phone"], help="رقم الهاتف (الافتراضي: %(default)s)")
    p.add_argument("--out", default=None, help="مجلد الإخراج (افتراضي: بجانب الصورة الأصلية)")
    p.add_argument("--font", default=DEFAULTS["font"], help="مسار ملف الخط .ttf")
    p.add_argument("--palette", default=DEFAULTS["palette"], choices=sorted(PALETTES),
                   help="لوحة الألوان (افتراضي: %(default)s)")
    p.add_argument("--mode", default=DEFAULTS["mode"], choices=["overlay", "band"],
                   help="overlay = شريط فوق الصورة | band = شريط يمدّ الصورة (افتراضي: %(default)s)")
    p.add_argument("--bg", default=None, help='لون خلفية الشريط HEX مثل "#1F4E79" (يتجاوز --palette)')
    p.add_argument("--height", type=float, default=DEFAULTS["height"],
                   help="ارتفاع الشريط كنسبة من ارتفاع الصورة (افتراضي: %(default)s)")
    p.add_argument("--quality", type=int, default=DEFAULTS["quality"], help="جودة JPG 1-100")
    p.add_argument("--suffix", default=DEFAULTS["suffix"], help="لاحقة اسم الملف الناتج")
    p.add_argument("--format", default=None, choices=["jpg", "png", "webp"],
                   help="تحويل صيغة الإخراج")
    p.add_argument("--dry-run", action="store_true", help="عدم حفظ أي ملف — عرض التقرير فقط")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    font_path = find_font(args.font)
    palette = dict(PALETTES[args.palette])
    bg_override = parse_hex(args.bg) if args.bg else None

    cfg = {
        "name": args.name.strip(),
        "phone": args.phone.strip(),
        "mode": args.mode,
        "height": args.height,
        "quality": max(1, min(100, args.quality)),
        "name_ratio": DEFAULTS["name_ratio"],
        "phone_ratio": DEFAULTS["phone_ratio"],
        "gap_ratio": DEFAULTS["gap_ratio"],
        "margin_ratio": DEFAULTS["margin_ratio"],
        "min_height": DEFAULTS["min_height"],
    }

    files = collect_inputs(args.inputs)
    if not files:
        print("⚠️  لا توجد صور للمعالجة.", file=sys.stderr)
        return 1

    out_dir = Path(args.out).expanduser() if args.out else None

    print("═" * 62)
    print("  إضافة الاسم ورقم الهاتف أسفل صور الإعلانات")
    print("═" * 62)
    print(f"  الاسم       : {cfg['name']}")
    print(f"  الهاتف      : {cfg['phone']}")
    print(f"  الخط         : {font_path.name}")
    print(f"  النمط        : {cfg['mode']}  |  اللوحة: {args.palette}"
          + (f"  |  خلفية: {args.bg}" if args.bg else ""))
    print(f"  عدد الصور    : {len(files)}")
    if args.dry_run:
        print("  ⚠️  وضع التجربة: لن يُحفظ أي ملف")
    print("─" * 62)

    ok, failed = 0, []
    for i, src in enumerate(files, 1):
        try:
            img = load_image(src)
            result, rep = render(img, cfg, font_path, palette, bg_override)
            line = (f"  [{i:>2}/{len(files)}] {src.name[:34]:<34} "
                    f"{img.size[0]}×{img.size[1]} → شريط {rep['bar_h']}px "
                    f"({rep['layout']}, خط {rep['font']})")
            if not args.dry_run:
                dst = output_path(src, out_dir, args.suffix, args.format)
                if dst.suffix.lower() in (".jpg", ".jpeg"):
                    result.convert("RGB").save(dst, quality=cfg["quality"], optimize=True, progressive=True)
                elif dst.suffix.lower() == ".webp":
                    result.save(dst, quality=cfg["quality"], method=6)
                else:
                    result.save(dst, optimize=True)
                line += f"\n            ↳ {dst}"
            print(line)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            failed.append((src, exc))
            print(f"  [{i:>2}/{len(files)}] ❌ {src.name}: {exc}")

    print("─" * 62)
    print(f"  ✅ تم بنجاح: {ok}" + (f"   |   ❌ فشل: {len(failed)}" if failed else ""))
    if out_dir and not args.dry_run:
        print(f"  📁 الإخراج: {out_dir.resolve()}")
    print("═" * 62)
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
