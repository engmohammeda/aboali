# -*- coding: utf-8 -*-
"""بناء الغلاف (1500x500) وصورة الحساب (400x400) — أبو عمر للسيراميك والبورسلان"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import os

BASE = "/home/user/assets"
FDIR = f"{BASE}/fonts"
OUT  = f"{BASE}/out"
os.makedirs(OUT, exist_ok=True)

# ---------- الألوان: هوية «أبو عمر للسيراميك والبورسلان» (أسود أونيكس + ذهبي) ----------
ONYX    = (11, 9, 6)      # #0B0906
ONYX_D  = (6, 5, 3)
GOLD_HI = (251, 235, 199) # #FBEBC7
GOLD    = (234, 206, 165) # #EACEA5
GOLD_MD = (201, 170, 131) # #C9AA83
GOLD_DP = (184, 134, 80)  # #B88650
BRONZE  = (92, 72, 47)    # #5C482F
IVORY   = (246, 240, 230)

# أسماء متوافقة مع بقية السكربت
TERRA   = GOLD_DP
TERRA_D = BRONZE
NAVY    = ONYX
NAVY_D  = ONYX_D
SAND    = IVORY
SAND_L  = GOLD_HI
CHAR    = ONYX
WHITE   = (255, 255, 255)

def F(name, size):
    return ImageFont.truetype(f"{FDIR}/{name}", size)

def T(d, xy, txt, font, fill, anchor="ra", stroke=0, sfill=None):
    """رسم نص عربي من اليمين لليسار (anchor: ra = يمين-أعلى)"""
    d.text(xy, txt, font=font, fill=fill, anchor=anchor, direction="rtl",
           language="ar", stroke_width=stroke, stroke_fill=sfill)

def cover_crop(img, w, h):
    """قص لتغطية المقاس بدقة من المنتصف"""
    ir = img.width / img.height
    tr = w / h
    if ir > tr:
        nw = int(img.height * tr); nh = img.height
        x = (img.width - nw) // 2; box = (x, 0, x + nw, nh)
    else:
        nw = img.width; nh = int(img.width / tr)
        y = (img.height - nh) // 2; box = (0, y, nw, y + nh)
    return img.crop(box).resize((w, h), Image.LANCZOS)

# =====================================================================
# 1) الغلاف 1500 × 500
# =====================================================================
W, H = 1500, 500
cover = Image.new("RGB", (W, H), NAVY_D)

# --- منطقة الصور (يسار الغلاف) ---
IMG_W = 880
hero = cover_crop(Image.open(f"{BASE}/raw/hero-living.png").convert("RGB"), 600, H)
tex  = cover_crop(Image.open(f"{BASE}/raw/texture-stack.png").convert("RGB"), IMG_W-600, H)
cover.paste(hero, (0, 0))
cover.paste(tex, (600, 0))

# فاصل ذهبي رقيق بين الصورتين
d = ImageDraw.Draw(cover)
d.rectangle([598, 0, 601, H], fill=(255, 255, 255, 60))

# تدرّج دمج نحو اللوحة النصية (يمين الصور)
grad = Image.new("L", (IMG_W, 1), 0)
for x in range(IMG_W):
    v = 0 if x < IMG_W*0.55 else int(255 * ((x - IMG_W*0.55) / (IMG_W*0.45)) ** 1.6)
    grad.putpixel((x, 0), v)
grad = grad.resize((IMG_W, H))
overlay = Image.new("RGB", (IMG_W, H), NAVY_D)
cover.paste(overlay, (0, 0), grad)

# --- اللوحة النصية (يمين الغلاف) ---
PANEL_X = 880
panel = Image.new("RGB", (W - PANEL_X, H), NAVY)
pd = ImageDraw.Draw(panel)
# تدرّج رأسي داخل اللوحة
for y in range(H):
    t = y / H
    c = tuple(int(NAVY[i] + (NAVY_D[i] - NAVY[i]) * t) for i in range(3))
    pd.line([(0, y), (panel.width, y)], fill=c)
# زخرفة قوسية تراكوتا أسفل اللوحة
pd.ellipse([panel.width-330, H-190, panel.width+250, H+250], fill=TERRA_D)
# شريط تراكوتا رأسي على حافة اللوحة
pd.rectangle([0, 0, 9, H], fill=TERRA)
cover.paste(panel, (PANEL_X, 0))
d = ImageDraw.Draw(cover)

RX = W - 52          # محور اليمين داخل اللوحة
def gold_rule(y, w=110, x=RX):
    d.rectangle([x - w, y, x, y + 4], fill=GOLD)

# العنوان الرئيسي
T(d, (RX, 40), "أبو عمر", F("Tajawal-Black.ttf", 68), WHITE)
T(d, (RX, 118), "للسيراميك والبورسلان", F("Tajawal-Bold.ttf", 42), (245, 224, 205))

gold_rule(178, 130)

T(d, (RX, 200), "خبرة أكثر من 20 عامًا", F("Tajawal-Bold.ttf", 30), GOLD)
T(d, (RX, 244), "الرياض وضواحيها", F("Tajawal-Medium.ttf", 28), SAND)

# شارة الهاتف
ph_txt = "0566743293"
fph = F("Tajawal-Bold.ttf", 32)
tw = d.textlength(ph_txt, font=fph, direction="ltr")
pad = 54
bx1, by1 = RX, 300
bx0 = int(bx1 - tw - pad*2)
d.rounded_rectangle([bx0, by1, bx1, by1+58], radius=29, fill=TERRA, outline=GOLD, width=2)
# أيقونة هاتف صغيرة
cx = bx0 + 30
d.rounded_rectangle([cx-11, by1+17, cx+11, by1+41], radius=5, outline=WHITE, width=2)
d.ellipse([cx-3, by1+24, cx+3, by1+30], fill=WHITE)
d.text((bx0 + pad + 8, by1 + 27), ph_txt, font=fph, fill=WHITE, anchor="lm", direction="ltr")

T(d, (RX, 372), "توريد • تركيب • توصيل", F("Tajawal-Medium.ttf", 25), (222, 214, 202))

# شارة "من أعمالنا" على منطقة الصور (أعلى اليسار)
chip = "من أعمالنا"
fchip = F("Tajawal-Bold.ttf", 22)
cw = d.textlength(chip, font=fchip, direction="rtl")
d.rounded_rectangle([28, 28, 28 + cw + 48, 28 + 44], radius=22, fill=(0, 0, 0, 0))
chip_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
cd = ImageDraw.Draw(chip_layer)
cd.rounded_rectangle([28, 28, 28 + cw + 48, 72], radius=22, fill=(43, 43, 43, 185))
cover_rgba = cover.convert("RGBA")
cover_rgba.alpha_composite(chip_layer)
cover = cover_rgba.convert("RGB")
d = ImageDraw.Draw(cover)
T(d, (28 + cw + 34, 34), chip, fchip, WHITE)
# نقطة تراكوتا صغيرة
d.ellipse([36, 46, 48, 58], fill=TERRA)

cover.save(f"{OUT}/cover-1500x500.png", quality=95)
cover.save(f"{OUT}/cover-1500x500.jpg", quality=92)
print("cover saved")

# =====================================================================
# 2) صورة الحساب 400 × 400
# =====================================================================
S = 400
acc = Image.new("RGB", (S, S), NAVY)
ad = ImageDraw.Draw(acc)
for y in range(S):
    t = y / S
    c = tuple(int(NAVY_D[i] + (NAVY[i] - NAVY_D[i]) * t) for i in range(3))
    ad.line([(0, y), (S, y)], fill=c)

# نقشة بلاط خفيفة في الخلفية
for i in range(0, S+80, 80):
    ad.line([(i, 0), (i - 120, S)], fill=(255, 255, 255, 0) if False else (38, 88, 132), width=1)
    ad.line([(0, i), (S, i - 120)], fill=(38, 88, 132), width=1)

# قوس تراكوتا
ad.ellipse([-150, S-140, 190, S+160], fill=TERRA_D)

# إطار ذهبي مزدوج
ad.rounded_rectangle([12, 12, S-12, S-12], radius=18, outline=GOLD, width=3)
ad.rounded_rectangle([22, 22, S-22, S-22], radius=14, outline=(120, 100, 55), width=1)

CX = S // 2
ad.text((CX, 66), "أبو عمر", font=F("Tajawal-Black.ttf", 82), fill=WHITE,
        anchor="ma", direction="rtl", language="ar")
ad.rectangle([CX-70, 160, CX+70, 164], fill=GOLD)
ad.text((CX, 182), "للسيراميك والبورسلان", font=F("Tajawal-Bold.ttf", 27), fill=(245, 224, 205),
        anchor="ma", direction="rtl", language="ar")
ad.text((CX, 226), "خبرة أكثر من 20 عامًا", font=F("Tajawal-Bold.ttf", 23), fill=GOLD,
        anchor="ma", direction="rtl", language="ar")
ad.text((CX, 260), "الرياض وضواحيها", font=F("Tajawal-Medium.ttf", 22), fill=SAND,
        anchor="ma", direction="rtl", language="ar")

# الهاتف
fph2 = F("Tajawal-Bold.ttf", 26)
ph = "0566743293"
tw2 = ad.textlength(ph, font=fph2, direction="ltr")
bw2 = tw2 + 62
ad.rounded_rectangle([CX - bw2/2, 296, CX + bw2/2, 348], radius=26, fill=TERRA, outline=GOLD, width=2)
ad.text((CX + 12, 322), ph, font=fph2, fill=WHITE, anchor="mm", direction="ltr")
ad.rounded_rectangle([CX - bw2/2 + 16, 311, CX - bw2/2 + 34, 333], radius=4, outline=WHITE, width=2)

acc.save(f"{OUT}/account-400x400.png", quality=95)
acc.save(f"{OUT}/account-400x400.jpg", quality=92)
print("account saved")
