#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
benchmark_haraj.py — قياس فعلي: هل الأداة تنقذ الجودة بعد ضغط حراج؟
====================================================================
السؤال: بعد أن يرفع حراج الصورة ويعيد ترميزها، أيّهما أفضل؟
   (أ) صورة رُفعت كما هي (الطريقة العادية)
   (ب) صورة مرّت على haraj_optimizer ثم رُفعت

الطريقة:
  1. نأخذ الصورة الأصلية = "الحقيقة" (ground truth).
  2. المسار العادي  : الأصل ← ضغط حراج المحاكى.
  3. المسار المحسّن : الأصل ← haraj_optimizer ← ضغط حراج المحاكى.
  4. نقيس الاثنين مقابل الأصل: PSNR / SSIM / الحدة.

ضغط حراج المحاكى (محاكاة متحفظة لأسوأ حالة):
  تصغير لأقصى 1080px + إعادة ترميز JPEG بجودة 72–80 + 4:2:0

الاستخدام:
  python tools/benchmark_haraj.py photo.jpg
  python tools/benchmark_haraj.py ./raw --out ./bench --quality 75
"""

from __future__ import annotations

import argparse
import io
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import haraj_optimizer as ho  # noqa: E402
import add_footer as af  # noqa: E402
find_font = af.find_font


def haraj_simulate(img: Image.Image, max_side: int, quality: int,
                   subsampling: int = 2) -> Image.Image:
    """محاكاة إعادة ترميز حراج: تصغير + JPEG منخفض الجودة + تقليل عيّنات الألوان."""
    w, h = img.size
    longest = max(w, h)
    if longest > max_side:
        f = max_side / longest
        img = img.resize((round(w * f), round(h * f)), Image.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality,
                            subsampling=subsampling, optimize=True)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def metrics(truth: Image.Image, test: Image.Image) -> dict:
    return {
        "psnr": ho.psnr(truth, test),
        "ssim": ho.ssim(truth, test),
        "sharp": ho.sharpness_score(test),
        "kb": 0.0,
        "size": test.size,
    }


def params_zoom(a: Image.Image) -> int:
    """تكبير معقول يُبقي صورة المقارنة واضحة وغير مكبّرة أكثر من اللازم."""
    return 2 if max(a.size) > 500 else 3


def side_by_side(a: Image.Image, b: Image.Image, label_a: str, label_b: str,
                 font_path: Path, crop: bool = True, out: Path | None = None) -> Image.Image:
    """صورة مقارنة: تكبير منطقة واحدة في الصورتين جنبًا إلى جنب."""
    w, h = a.size
    if crop:
        # منطقة مركزية بتكبير 3× لإظهار فقدان التفاصيل
        cw, chh = w // 3, h // 3
        box = (w // 2 - cw // 2, h // 2 - chh // 2, w // 2 + cw // 2, h // 2 + chh // 2)
        a, b = a.crop(box), b.crop(box)
        zoom = params_zoom(a)
        a = a.resize((a.width * zoom, a.height * zoom), Image.NEAREST)
        b = b.resize((b.width * zoom, b.height * zoom), Image.NEAREST)

    gap, header = 18, 100
    cw, chh = a.size
    canvas = Image.new("RGB", (cw * 2 + gap * 3, chh + header + gap * 2), (18, 18, 18))
    canvas.paste(a, (gap, header + gap))
    canvas.paste(b, (gap * 2 + cw, header + gap))
    d = ImageDraw.Draw(canvas)

    # ⚠️ ملاحظة تقنية: رسم نصَّين عربيَّين (RTL + language="ar") على نفس ImageDraw
    # يُفسد تشكيل الحروف في Pillow/libraqm. الحل: كل تسمية تُرسم على طبقة مستقلة ثم تُلصق.
    def draw_label(text: str, center_x: int, font, color) -> None:
        layer = Image.new("RGBA", (cw, header), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.text((cw // 2, header // 2), text, font=font, fill=color + (255,),
                anchor="mm", direction="rtl", language="ar")
        canvas.paste(layer, (center_x - cw // 2, 0), layer)

    # حجم خط يتّسع داخل عرض كل لوحة (يمنع تراكب التسميتين)
    def fit(text: str, max_w: int) -> ImageFont.FreeTypeFont:
        size = min(46, chh // 8 + 20)
        f = ImageFont.truetype(str(font_path), size)
        while d.textlength(text, font=f, direction="rtl", language="ar") > max_w and size > 11:
            size -= 1
            f = ImageFont.truetype(str(font_path), size)
        return f

    fa, fb = fit(label_a, cw - 12), fit(label_b, cw - 12)
    draw_label(label_a, gap + cw // 2, fa, (205, 205, 205))
    draw_label(label_b, gap * 2 + cw + cw // 2, fb, (234, 206, 165))
    d.line([(gap * 2 + cw - gap // 2, header), (gap * 2 + cw - gap // 2, canvas.height)],
           fill=(80, 60, 30), width=2)
    if out:
        canvas.save(out, quality=95)
    return canvas


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="قياس أثر ضغط حراج على الصورة قبل/بعد الأداة")
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--out", default="bench", help="مجلد المقارنات")
    ap.add_argument("--haraj-max-side", type=int, default=1080, help="أقصى ضلع يفرضه حراج (محاكاة)")
    ap.add_argument("--quality", type=int, default=75, help="جودة حراج المحاكاة")
    ap.add_argument("--preset", default="max", help="إعداد الأداة المستخدم في المسار المحسّن")
    ap.add_argument("--max-kb", type=float, default=0, help="0 = بلا حد حجم")
    args = ap.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    font = find_font(None)

    files = ho.collect(args.inputs, argparse.Namespace(suffix="_haraj", recursive=True))
    if not files:
        print("لا صور.")
        return 1

    preset = dict(ho.PRESETS[args.preset])
    rows = []

    print("═" * 78)
    print(f"  🔬 محاكاة ضغط حراج: أقصى ضلع {args.haraj_max_side}px • جودة {args.quality} • 4:2:0")
    print("═" * 78)

    for i, src in enumerate(files, 1):
        img, _ = ho.load_source(src)
        w0, h0 = img.size

        # مسار (أ): الرفع العادي
        naive = haraj_simulate(img, args.haraj_max_side, args.quality)

        # مسار (ب): بعد الأداة
        resized, factor = ho.resize_smart(img, preset["max_side"], preset["min_side"], False)
        sharpened, _ = ho.adaptive_sharpen(resized, preset["sharpen"], factor)
        data, q = ho.encode_with_budget(sharpened, preset, args.max_kb,
                                        preset["subsampling"], preset["progressive"], None)
        prepared = Image.open(io.BytesIO(data)).convert("RGB")
        optimized = haraj_simulate(prepared, args.haraj_max_side, args.quality)

        # الحقيقة = الأصل بمقاس المقارنة
        truth = img.resize(optimized.size, Image.LANCZOS)

        m_naive = metrics(truth, naive)
        m_opt = metrics(truth, optimized)

        rows.append((src.name, w0, h0, m_naive, m_opt))

        gap_psnr = m_opt["psnr"] - m_naive["psnr"]
        gap_ssim = (m_opt["ssim"] - m_naive["ssim"]) * 100
        gap_sharp = 100 * (m_opt["sharp"] - m_naive["sharp"]) / max(1e-9, m_naive["sharp"])

        print(f"\n  [{i}/{len(files)}] {src.name}  ({w0}×{h0})")
        print(f"        {'المقياس':<12}{'رفع عادي':>14}{'بعد الأداة':>14}{'الفرق':>14}")
        print(f"        {'─'*54}")
        print(f"        {'PSNR':<12}{m_naive['psnr']:>11.2f} dB{m_opt['psnr']:>11.2f} dB{gap_psnr:>+11.2f} dB")
        print(f"        {'SSIM':<12}{m_naive['ssim']:>14.4f}{m_opt['ssim']:>14.4f}{gap_ssim:>+13.2f}%")
        print(f"        {'الحدّة':<12}{m_naive['sharp']:>14.1f}{m_opt['sharp']:>14.1f}{gap_sharp:>+13.1f}%")

        comp = out_dir / f"{src.stem}_compare.jpg"
        side_by_side(naive, optimized, "رفع عادي — بعد ضغط حراج", "بعد الأداة — بعد ضغط حراج",
                     font, crop=True, out=comp)
        print(f"        🖼️  مقارنة مُكبّرة 3×: {comp}")

    # ملخص
    if rows:
        avg_n = sum(r[3]["psnr"] for r in rows) / len(rows)
        avg_o = sum(r[4]["psnr"] for r in rows) / len(rows)
        avg_sn = sum(r[3]["ssim"] for r in rows) / len(rows)
        avg_so = sum(r[4]["ssim"] for r in rows) / len(rows)
        avg_hn = sum(r[3]["sharp"] for r in rows) / len(rows)
        avg_ho = sum(r[4]["sharp"] for r in rows) / len(rows)
        print("\n" + "═" * 78)
        print("  📊 الملخص")
        print("─" * 78)
        print(f"  متوسط PSNR : {avg_n:6.2f} dB  →  {avg_o:6.2f} dB   ({avg_o-avg_n:+.2f} dB)")
        print(f"  متوسط SSIM : {avg_sn:6.4f}    →  {avg_so:6.4f}     ({(avg_so-avg_sn)*100:+.2f}%)")
        print(f"  متوسط الحدّة: {avg_hn:6.1f}      →  {avg_ho:6.1f}       "
              f"({100*(avg_ho-avg_hn)/max(1e-9,avg_hn):+.1f}%)")
        print("═" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
