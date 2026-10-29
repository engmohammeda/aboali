#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
haraj_optimizer.py — محسّن صور حراج الاحترافي
==============================================
المشكلة: حراج يعيد ضغط كل صورة ترفعها ويصغّرها، فتخرج ناعمة/مشوّشة/باهتة.
الحل: لا نرفع الصورة "كما هي"، بل نُهيّئها لتنجو من ضغط حراج:

  1. تصحيح اتجاه EXIF (صور الجوال) — يمنع الصور المقلوبة.
  2. تحويل كل ملفات الألوان إلى sRGB — يمنع تغيّر الألوان بعد الرفع.
  3. تصغير ذكي بـ LANCZOS فقط (لا تكبير أبدًا) إلى المقاس المستهدف.
  4. إعادة الحدة بشكل تكيّفي (UnsharpMask) بمقدار يتناسب مع نسبة التصغير،
     لتعويض التنعيم الذي سيحدثه ضغط حراج.
  5. ترميز JPEG بأعلى جودة ممكنة: 4:4:4 (بدون تقليل عيّنات الألوان)
     + progressive + optimize — أهم إعداد للحفاظ على التفاصيل والألوان.
  6. ضبط الجودة تلقائيًا (بحث تكراري) للوصول إلى الحجم المسموح بلا فقدان ظاهر.
  7. قياس جودة فعلي: PSNR + SSIM + درجة الحدة قبل/بعد، لتعرف بالأرقام ما حدث.
  8. (اختياري) إضافة العلامة المائية: الاسم + رقم الهاتف بهوية المشروع.

المتطلبات:  pip install pillow          (numpy اختيارية — لتحسين القياسات)
الاستخدام السريع:
    python haraj_optimizer.py photo.jpg
    python haraj_optimizer.py ./raw --out ./جاهزة-للحراج
    python haraj_optimizer.py ./raw --preset max --footer
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps, ImageStat
    try:
        from PIL import ImageCms
    except ImportError:  # pragma: no cover
        ImageCms = None
except ImportError:
    sys.exit("❌ مكتبة Pillow غير مثبّتة.  شغّل:  pip install pillow")

try:
    import numpy as np
except ImportError:
    np = None

# اختياري: دعم HEIC/HEIF (صور الآيفون)
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_OK = True
except ImportError:
    HEIF_OK = False

# ═══════════════════════════════════════════════════════════════════════════
#  الإعدادات الجاهزة (Presets)
# ═══════════════════════════════════════════════════════════════════════════
PRESETS = {
    # الافتراضي: أفضل توازن جودة/حجم لحراج
    "haraj": dict(max_side=2048, min_side=1000, quality=92, min_quality=82,
                  max_kb=2048, sharpen=0.35, subsampling=0, progressive=True),
    # أقصى جودة: للصور التي تحمل تفاصيل مهمة (ملمس بلاط، أنماط، نقوش)
    "max":   dict(max_side=2560, min_side=1200, quality=95, min_quality=88,
                  max_kb=4096, sharpen=0.50, subsampling=0, progressive=True),
    # متوازن: حجم أصغر مع جودة ممتازة
    "balanced": dict(max_side=1800, min_side=900, quality=90, min_quality=80,
                     max_kb=1024, sharpen=0.30, subsampling=0, progressive=True),
    # خفيف: لمن عنده صور كثيرة أو اتصال بطيء
    "lite":  dict(max_side=1400, min_side=800, quality=86, min_quality=76,
                  max_kb=512, sharpen=0.25, subsampling=0, progressive=True),
    # آمن: بلا أي حدّة — أعلى أمانة ممكنة للأصل (الأفضل للصور ذات النقوش الدقيقة)
    "safe":  dict(max_side=2048, min_side=1000, quality=94, min_quality=85,
                  max_kb=3072, sharpen=0.0, subsampling=0, progressive=True),
}

EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
if HEIF_OK:
    EXTS |= {".heic", ".heif"}

TMP_SUFFIX = "_haraj_tmp"


# ═══════════════════════════════════════════════════════════════════════════
#  المرافق
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class Report:
    src: str
    dst: str = ""
    orig_w: int = 0
    orig_h: int = 0
    out_w: int = 0
    out_h: int = 0
    orig_kb: float = 0.0
    out_kb: float = 0.0
    quality: int = 0
    scale: float = 1.0
    sharpen: float = 0.0
    psnr: float = 0.0
    ssim: float = 0.0
    sharpness_before: float = 0.0
    sharpness_after: float = 0.0
    footer: bool = False
    seconds: float = 0.0
    status: str = "ok"
    note: str = ""

    @property
    def sharp_gain(self) -> float:
        if self.sharpness_before <= 0:
            return 0.0
        return 100.0 * (self.sharpness_after - self.sharpness_before) / self.sharpness_before


def human_kb(kb: float) -> str:
    return f"{kb/1024:.2f} MB" if kb >= 1024 else f"{kb:.0f} KB"


def flatten_to_rgb(img: Image.Image, bg=(255, 255, 255)) -> Image.Image:
    """تسطيح الشفافية على خلفية، مع الحفاظ على أي قناة شفافية متدرّجة."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        canvas = Image.new("RGB", img.size, bg)
        canvas.paste(img, mask=img.getchannel("A"))
        return canvas
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def to_srgb(img: Image.Image, icc: bytes | None, warnings: list[str]) -> Image.Image:
    """تحويل ملف الألوان إلى sRGB — يمنع انقلاب/بهتان الألوان بعد الرفع."""
    if not icc or ImageCms is None:
        return img
    try:
        src_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        src_name = (ImageCms.getProfileDescription(src_profile) or "").strip()
        if "srgb" in src_name.lower():
            return img
        dst_profile = ImageCms.createProfile("sRGB")
        return ImageCms.profileToProfile(img, src_profile, dst_profile, outputMode="RGB")
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"تعذّر تحويل ملف الألوان ({exc}) — تم الافتراض أنه sRGB")
        return img


def load_source(path: Path) -> tuple[Image.Image, list[str]]:
    warnings: list[str] = []
    img = Image.open(path)
    img.load()
    icc = img.info.get("icc_profile")

    try:
        rotated = ImageOps.exif_transpose(img)
        if rotated is not None:
            if rotated.size != img.size:
                warnings.append("تم تصحيح اتجاه EXIF")
            img = rotated
    except Exception:
        pass

    img = to_srgb(img, icc, warnings)
    img = flatten_to_rgb(img)
    return img, warnings


def resize_smart(img: Image.Image, max_side: int, min_side: int,
                 allow_upscale: bool) -> tuple[Image.Image, float]:
    """تصغير فقط (أو تكبير محدود إن سُمح). يعيد الصورة + نسبة التغيير."""
    w, h = img.size
    longest = max(w, h)
    factor = 1.0

    if longest > max_side:
        factor = max_side / longest
    elif longest < min_side and allow_upscale:
        factor = min(min_side / longest, 2.0)   # تكبير لا يتجاوز الضعف

    if abs(factor - 1.0) < 0.005:
        return img, 1.0

    new_size = (max(1, round(w * factor)), max(1, round(h * factor)))
    # LANCZOS = أفضل مرشّح للتصغير (يحفظ التفاصيل والحدّة)
    return img.resize(new_size, Image.LANCZOS), factor


def apply_sharpen(img: Image.Image, amount: float) -> Image.Image:
    """تطبيق UnsharpMask بمقدار محدد (0 = بلا تغيير)."""
    if amount <= 0:
        return img
    radius = 1.0 if img.size[0] >= 1200 else 0.8
    threshold = 2 if img.size[0] >= 1200 else 3
    return img.filter(ImageFilter.UnsharpMask(radius=radius,
                                              percent=int(amount * 100),
                                              threshold=threshold))


def adaptive_sharpen(img: Image.Image, base: float, factor: float) -> tuple[Image.Image, float]:
    """
    حدّة تكيّفية: كلما صغّرنا أكثر، زدنا الحدّة قليلًا لتعويض التنعيم.
    UnsharpMask أفضل من ImageEnhance.Sharpness لأنه يعمل على الترددات الدقيقة.
    """
    if base <= 0:
        return img, 0.0
    boost = 1.0 + max(0.0, (1.0 - factor)) * 0.9     # تصغير 50% → +45%
    amount = min(2.0, base * boost)
    radius = 1.0 if img.size[0] >= 1200 else 0.8
    threshold = 2 if img.size[0] >= 1200 else 3       # لا تُحدّد الضوضاء في المساحات الهادئة
    out = img.filter(ImageFilter.UnsharpMask(radius=radius, percent=int(amount * 100),
                                             threshold=threshold))
    return out, amount


def encode_jpeg(img: Image.Image, quality: int, subsampling: int,
                progressive: bool, icc: bytes | None = None) -> bytes:
    buf = io.BytesIO()
    kw = dict(format="JPEG", quality=quality, subsampling=subsampling,
              optimize=True, progressive=progressive)
    if icc:
        kw["icc_profile"] = icc
    img.save(buf, **kw)
    return buf.getvalue()


def encode_with_budget(img: Image.Image, preset: dict, max_kb: float,
                       subsampling: int, progressive: bool,
                       icc: bytes | None) -> tuple[bytes, int]:
    """
    بحث تكراري عن أعلى جودة تحقّق شرط الحجم.
    لا نهبط تحت min_quality مهما كان الحجم — الجودة أولًا.
    """
    q_hi = preset["quality"]
    q_lo = preset["min_quality"]
    limit = max_kb * 1024

    data = encode_jpeg(img, q_hi, subsampling, progressive, icc)
    if len(data) <= limit or max_kb <= 0:
        return data, q_hi

    best_data, best_q = data, q_hi
    lo, hi = q_lo, q_hi - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = encode_jpeg(img, mid, subsampling, progressive, icc)
        if len(cand) <= limit:
            best_data, best_q = cand, mid
            lo = mid + 1
        else:
            hi = mid - 1

    if len(best_data) > limit:
        # حتى أدنى جودة مقبولة تجاوزت الحجم → نُصغّر الأبعاد بدل إتلاف الجودة
        return best_data, best_q
    return best_data, best_q


def _gray(img: Image.Image) -> Image.Image:
    return img.convert("L")


def sharpness_score(img: Image.Image) -> float:
    """مقياس الحدة: تباين حواف لابلاسيان (أعلى = أوضح)."""
    g = _gray(img)
    lap = g.filter(ImageFilter.Kernel((3, 3), (0, -1, 0, -1, 4, -1, 0, -1, 0), scale=1))
    return float(ImageStat.Stat(lap).stddev[0])


def psnr(a: Image.Image, b: Image.Image) -> float:
    """PSNR بين صورتين بنفس المقاس (أعلى = فرق أقل)."""
    if a.size != b.size:
        b = b.resize(a.size, Image.LANCZOS)
    from PIL import ImageChops
    diff = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
    stat = ImageStat.Stat(diff)
    mse = sum(s ** 2 for s in stat.rms) / len(stat.rms)
    if mse <= 1e-12:
        return 99.0
    return 20 * math.log10(255.0 / math.sqrt(mse))


def ssim(a: Image.Image, b: Image.Image) -> float:
    """SSIM تقريبي (نافذة 8×8) — مطابق للإدراك البشري أكثر من PSNR."""
    if np is None:
        return 0.0
    if a.size != b.size:
        b = b.resize(a.size, Image.LANCZOS)
    A = np.asarray(_gray(a), dtype=np.float64)
    B = np.asarray(_gray(b), dtype=np.float64)
    C1, C2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    win = 8
    h, w = A.shape
    h, w = (h // win) * win, (w // win) * win
    if h == 0 or w == 0:
        return 0.0
    A, B = A[:h, :w], B[:h, :w]
    A = A.reshape(h // win, win, w // win, win).swapaxes(1, 2)
    B = B.reshape(h // win, win, w // win, win).swapaxes(1, 2)
    muA, muB = A.mean(axis=(2, 3)), B.mean(axis=(2, 3))
    varA, varB = A.var(axis=(2, 3)), B.var(axis=(2, 3))
    cov = ((A - muA[..., None, None]) * (B - muB[..., None, None])).mean(axis=(2, 3))
    num = (2 * muA * muB + C1) * (2 * cov + C2)
    den = (muA ** 2 + muB ** 2 + C1) * (varA + varB + C2)
    return float(np.mean(num / den))


# ═══════════════════════════════════════════════════════════════════════════
#  المعالجة
# ═══════════════════════════════════════════════════════════════════════════
def process_one(src: Path, out_dir: Path | None, preset: dict, args) -> Report:
    t0 = time.perf_counter()
    rep = Report(src=str(src))

    img, warns = load_source(src)
    rep.orig_w, rep.orig_h = img.size
    rep.orig_kb = src.stat().st_size / 1024
    if warns:
        rep.note = "؛ ".join(warns)

    # 1) القياسات قبل الترميز (على الصورة بعد التصغير والحدّة)
    max_side = args.target_side if getattr(args, "target_side", None) else preset["max_side"]
    resized, factor = resize_smart(img, max_side, preset["min_side"],
                                   args.allow_upscale)
    rep.scale = factor
    rep.sharpness_before = sharpness_score(resized)

    sharpened, amount = adaptive_sharpen(resized, preset["sharpen"], factor)

    # 🛡️ حارس الجودة: الحدّة التي تُبعد الصورة عن أصلها أكثر من اللازم تُقلَّل تلقائيًا.
    # السبب (مُثبت بالتجربة): الحدّة الزائدة تُنتج هالات وضجيجًا يعظّمه ضغط حراج.
    guard_used = False
    if amount > 0 and args.quality_guard:
        limit = args.guard_psnr
        for _ in range(6):
            if psnr(resized, sharpened) >= limit:
                break
            amount *= 0.65
            sharpened = apply_sharpen(resized, amount)
            guard_used = True
        if guard_used:
            rep.note = ((rep.note + "؛ ") if rep.note else "") + \
                f"حارس الجودة خفّض الحدّة إلى {amount:.2f} (حفاظًا على التفاصيل)"

    rep.sharpen = round(amount, 2)
    rep.sharpness_after = sharpness_score(sharpened)

    target = sharpened

    # 2) العلامة المائية (اختيارية)
    if args.footer:
        try:
            import add_footer as af
            pal = dict(af.PALETTES[args.footer_palette])
            cfg = {
                "name": args.name, "phone": args.phone,
                "mode": args.footer_mode, "height": args.footer_height,
                "quality": preset["quality"],
                "name_ratio": af.DEFAULTS["name_ratio"],
                "phone_ratio": af.DEFAULTS["phone_ratio"],
                "gap_ratio": af.DEFAULTS["gap_ratio"],
                "margin_ratio": af.DEFAULTS["margin_ratio"],
                "min_height": af.DEFAULTS["min_height"],
                "glow": not args.no_glow,
            }
            target, _ = af.render(target, cfg, af.find_font(None), pal)
            rep.footer = True
        except Exception as exc:  # noqa: BLE001
            rep.note = (rep.note + "؛ " if rep.note else "") + f"تعذّرت العلامة المائية: {exc}"

    # 3) الترميز مع ميزانية الحجم
    max_kb = args.max_kb if args.max_kb is not None else preset["max_kb"]
    icc = None
    if not args.strip_icc:
        try:
            icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        except Exception:
            icc = None
    data, used_q = encode_with_budget(target, preset, max_kb,
                                      preset["subsampling"], preset["progressive"], icc)

    # 4) لو تجاوزنا السقف رغم أدنى جودة → تصغير إضافي (أفضل من إتلاف الجودة)
    if max_kb > 0 and len(data) > max_kb * 1024 and not args.no_shrink_for_size:
        for _ in range(4):
            new_side = int(max(target.size) * 0.9)
            if new_side < preset["min_side"] * 0.8:
                break
            target = target.resize((max(1, int(target.size[0] * 0.9)),
                                    max(1, int(target.size[1] * 0.9))), Image.LANCZOS)
            data, used_q = encode_with_budget(target, preset, max_kb,
                                              preset["subsampling"],
                                              preset["progressive"], icc)
            if len(data) <= max_kb * 1024:
                rep.note = (rep.note + "؛ " if rep.note else "") + "تم تصغير إضافي للوصول للحجم"
                break

    # 5) قياس الجودة الفعلي بعد فك الترميز
    try:
        decoded = Image.open(io.BytesIO(data)).convert("RGB")
        rep.psnr = psnr(target, decoded)
        rep.ssim = ssim(target, decoded)
        rep.sharpness_after = sharpness_score(decoded)   # الحدة الفعلية المسلَّمة
    except Exception:
        pass

    rep.quality = used_q
    rep.out_w, rep.out_h = target.size
    rep.out_kb = len(data) / 1024

    dst = ""
    if not args.dry_run:
        if out_dir:
            od = out_dir
        elif args.in_place:
            od = src.parent
        else:
            od = src.parent / "جاهزة-للحراج"
        od.mkdir(parents=True, exist_ok=True)
        base = src.stem
        if base.endswith(args.suffix):
            base = base[: -len(args.suffix)]
        name = base + args.suffix + ".jpg"
        p = od / name
        n = 1
        while p.exists() and not args.overwrite:
            p = od / f"{base}{args.suffix}_{n}.jpg"
            n += 1
        p.write_bytes(data)
        dst = str(p)
    rep.dst = dst
    rep.seconds = round(time.perf_counter() - t0, 2)

    # ما يُرفع لاحقًا هو G:\...\جاهزة-للحراج — يمنع المعالجة المزدوجة تلقائيًا
    return rep


def collect(paths: list[str], args) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if not f.is_file() or f.suffix.lower() not in EXTS:
                    continue
                if not args.recursive and f.parent != p:
                    continue
                if f.stem.endswith(args.suffix) or f.stem.endswith(TMP_SUFFIX):
                    continue
                if "جاهزة-للحراج" in f.parts:
                    continue
                files.append(f)
        elif p.is_file():
            files.append(p)
        else:
            print(f"⚠️  تم تجاهل مسار غير موجود: {raw}", file=sys.stderr)
    seen, uniq = set(), []
    for f in files:
        k = f.resolve()
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    return uniq


def print_report(rep: Report, idx: int, total: int) -> None:
    ratio = rep.out_kb / rep.orig_kb * 100 if rep.orig_kb else 0
    print(f"  [{idx:>2}/{total}] {Path(rep.src).name[:34]:<34}")
    print(f"        📐 {rep.orig_w}×{rep.orig_h} → {rep.out_w}×{rep.out_h}"
          f"   (مقياس {rep.scale:.2f}×)")
    print(f"        📦 {human_kb(rep.orig_kb)} → {human_kb(rep.out_kb)}"
          f"   ({ratio:.0f}% من الأصل)   جودة {rep.quality}")
    metrics = f"        🔬 PSNR {rep.psnr:.1f} dB"
    if rep.ssim:
        metrics += f"  •  SSIM {rep.ssim:.4f}"
    metrics += f"  •  الحدّة {rep.sharp_gain:+.0f}% (مقدار {rep.sharpen})"
    print(metrics)
    if rep.footer:
        print("        🏷️  علامة مائية: نعم")
    if rep.note:
        print(f"        ℹ️  {rep.note}")
    if rep.dst:
        print(f"        ↳ {rep.dst}")
    print(f"        ⏱️  {rep.seconds}s")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="haraj_optimizer.py",
        description="تحضير الصور لحراج بأعلى جودة ممكنة (sRGB + 4:4:4 + حدّة تكيّفية + ميزانية حجم).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""الإعدادات الجاهزة:
  haraj     الأفضل عمومًا: أقصى ضلع 2048، جودة 92، حدّة 1.0   (افتراضي)
  max       أقصى تفاصيل: 2560، جودة 95، حدّة 1.15
  balanced  توازن الحجم: 1800، جودة 90
  lite      خفيف: 1400، جودة 86

أمثلة:
  python haraj_optimizer.py photo.jpg
  python haraj_optimizer.py ./raw --preset max --out ./جاهزة-للحراج
  python haraj_optimizer.py ./raw --footer                      # مع الاسم والرقم
  python haraj_optimizer.py ./raw --preset balanced --max-kb 900
""")
    p.add_argument("inputs", nargs="+", help="ملف/مجلد صور (يمكن تمرير عدة)")
    p.add_argument("--preset", default="haraj", choices=sorted(PRESETS), help="الإعداد الجاهز")
    p.add_argument("--out", default=None, help="مجلد الإخراج (افتراضي: جاهزة-للحراج)")
    p.add_argument("--in-place", action="store_true", help="الحفظ بجانب الصورة الأصلية")
    p.add_argument("--max-side", type=int, default=None, help="أقصى ضلع بالبكسل (يتجاوز الإعداد)")
    p.add_argument("--min-side", type=int, default=None, help="أقل ضلع مسموح")
    p.add_argument("--quality", type=int, default=None, help="جودة JPEG (يتجاوز الإعداد)")
    p.add_argument("--min-quality", type=int, default=None, help="أدنى جودة مسموحة")
    p.add_argument("--max-kb", type=float, default=None, help="حد الحجم بالكيلوبايت (0 = بلا حد)")
    p.add_argument("--sharpen", type=float, default=None, help="مقدار الحدّة (0 = بلا حدّة)")
    p.add_argument("--allow-upscale", action="store_true",
                   help="السماح بتكبير الصور الصغيرة حتى min-side (افتراضيًا لا)")
    p.add_argument("--no-shrink-for-size", action="store_true",
                   help="منع التصغير الإضافي عند تجاوز الحجم")
    p.add_argument("--strip-icc", action="store_true", help="إزالة ملف الألوان من الملف الناتج")
    p.add_argument("--quality-guard", dest="quality_guard", action="store_true", default=True,
                   help="حارس الجودة: يقلّل الحدّة تلقائيًا إن أضرّت بالتفاصيل (افتراضي: مفعّل)")
    p.add_argument("--no-quality-guard", dest="quality_guard", action="store_false",
                   help="إيقاف حارس الجودة")
    p.add_argument("--guard-psnr", type=float, default=41.0,
                   help="عتبة أمانة الحدّة بالـ PSNR مقابل الصورة غير الحادة (افتراضي 41 dB)")
    p.add_argument("--target-side", type=int, default=None,
                   help="تصغير مسبق إلى هذا الضلع لنتحكّم نحن بإعادة العيّنات بدل المنصة (مثال: 1080)")
    p.add_argument("--recursive", action="store_true", default=True, help="البحث في المجلدات الفرعية")
    p.add_argument("--no-recursive", dest="recursive", action="store_false")
    p.add_argument("--suffix", default="_haraj", help="لاحقة الملفات الناتجة")
    p.add_argument("--overwrite", action="store_true", help="الكتابة فوق الملفات الموجودة")
    p.add_argument("--jobs", type=int, default=1, help="عدد العمليات المتوازية")
    p.add_argument("--report", default=None, help="حفظ تقرير CSV في هذا المسار")
    p.add_argument("--json", default=None, help="حفظ تقرير JSON في هذا المسار")
    p.add_argument("--dry-run", action="store_true", help="بلا حفظ")
    # خيارات العلامة المائية
    p.add_argument("--footer", action="store_true", help="إضافة الاسم ورقم الهاتف (هوية المشروع)")
    p.add_argument("--footer-palette", default="gold", help="لوحة العلامة المائية (gold/goldbar/onyx…)")
    p.add_argument("--footer-mode", default="overlay", choices=["overlay", "band"])
    p.add_argument("--footer-height", type=float, default=0.12)
    p.add_argument("--no-glow", action="store_true", help="إيقاف توهّج العلامة المائية")
    p.add_argument("--name", default="أبو عمر للسيراميك والبورسلان")
    p.add_argument("--phone", default="0566743293")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    preset = dict(PRESETS[args.preset])
    for key, arg in (("max_side", "max_side"), ("min_side", "min_side"),
                     ("quality", "quality"), ("min_quality", "min_quality"),
                     ("sharpen", "sharpen")):
        val = getattr(args, key, None)
        if val is not None:
            preset[arg] = val
    if preset["min_quality"] > preset["quality"]:
        preset["min_quality"] = preset["quality"]

    files = collect(args.inputs, args)
    if not files:
        print("⚠️  لم يتم العثور على صور.", file=sys.stderr)
        return 1

    out_dir = Path(args.out).expanduser() if args.out else None

    print("═" * 66)
    print("  🖼️  محسّن صور حراج — بأعلى جودة ممكنة")
    print("═" * 66)
    print(f"  الإعداد   : {args.preset}   (أقصى ضلع {preset['max_side']} • جودة "
          f"{preset['quality']}→{preset['min_quality']} • حدّة {preset['sharpen']})")
    print(f"  اللون      : sRGB  |  العيّنات: 4:4:4 (بلا تقليل)  |  "
          f"{'Progressive' if preset['progressive'] else 'Baseline'}")
    print(f"  الحجم      : حد {args.max_kb if args.max_kb is not None else preset['max_kb']} KB"
          + (f"  |  مقاس مستهدف {args.target_side}px" if args.target_side else ""))
    print(f"  حارس الجودة: {'مفعّل' if args.quality_guard else 'متوقف'}"
          f" (عتبة {args.guard_psnr:.0f} dB)")
    print(f"  العلامة    : {'نعم — ' + args.footer_palette if args.footer else 'لا'}")
    print(f"  الصور      : {len(files)}" + ("   ⚠️ وضع التجربة (بلا حفظ)" if args.dry_run else ""))
    if np is None:
        print("  ℹ️  numpy غير مثبتة — SSIM سيكون 0 (الباقي يعمل).  pip install numpy")
    if not HEIF_OK:
        print("  ℹ️  صور HEIC غير مدعومة.  pip install pillow-heif")
    print("─" * 66)

    reports: list[Report] = []
    t0 = time.perf_counter()

    if args.jobs > 1 and len(files) > 1:
        with ThreadPoolExecutor(max_workers=args.jobs) as ex:
            futures = [ex.submit(process_one, f, out_dir, preset, args) for f in files]
            for i, fut in enumerate(futures, 1):
                try:
                    rep = fut.result()
                except Exception as exc:  # noqa: BLE001
                    print(f"  [{i:>2}/{len(files)}] ❌ {exc}")
                    continue
                reports.append(rep)
                print_report(rep, i, len(files))
    else:
        for i, f in enumerate(files, 1):
            try:
                rep = process_one(f, out_dir, preset, args)
            except Exception as exc:  # noqa: BLE001
                print(f"  [{i:>2}/{len(files)}] ❌ {f.name}: {exc}")
                continue
            reports.append(rep)
            print_report(rep, i, len(files))

    elapsed = time.perf_counter() - t0
    ok = sum(1 for r in reports if r.status == "ok")
    print("─" * 66)
    if reports:
        tot_in = sum(r.orig_kb for r in reports)
        tot_out = sum(r.out_kb for r in reports)
        avg_psnr = sum(r.psnr for r in reports) / len(reports)
        avg_ssim = sum(r.ssim for r in reports) / len(reports) if np else 0
        gains = [r.sharp_gain for r in reports if r.sharpness_before > 0]
        print(f"  ✅ تم: {ok}/{len(files)}   |   ⏱️  {elapsed:.1f}s")
        print(f"  📦 الإجمالي: {human_kb(tot_in)} → {human_kb(tot_out)}"
              f"   ({tot_out / tot_in * 100:.0f}%)")
        print(f"  🔬 متوسط PSNR {avg_psnr:.1f} dB"
              + (f"  •  SSIM {avg_ssim:.4f}" if np else "")
              + (f"  •  تحسّن الحدّة {sum(gains)/len(gains):+.0f}%" if gains else ""))
        if out_dir and not args.dry_run:
            print(f"  📁 الإخراج: {out_dir.resolve()}")
        elif not args.dry_run:
            print("  📁 الإخراج: جاهزة-للحراج (بجانب كل صورة)")
    print("═" * 66)

    # التقارير
    if args.report and reports:
        rp = Path(args.report)
        rp.parent.mkdir(parents=True, exist_ok=True)
        with rp.open("w", newline="", encoding="utf-8-sig") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(asdict(reports[0]).keys()))
            wr.writeheader()
            for r in reports:
                wr.writerow(asdict(r))
        print(f"  📄 تقرير CSV: {rp}")

    if args.json and reports:
        jp = Path(args.json)
        jp.parent.mkdir(parents=True, exist_ok=True)
        payload = [dict(asdict(r), sharp_gain=round(r.sharp_gain, 1)) for r in reports]
        jp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  📄 تقرير JSON: {jp}")

    return 0 if ok == len(files) else 2


if __name__ == "__main__":
    raise SystemExit(main())
