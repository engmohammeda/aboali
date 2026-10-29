# دليل رفع المشروع على GitHub (للمالك)

## 1) عبر المتصفح (الأسهل لملف واحد)

1. افتح: `https://github.com/engmohammeda/abu-omar-ceramics`
2. اضغط **Add file → Create new file** أو **Upload files**.
3. للرفع المتعدد: اسحب الملفات ثم **Commit changes**.

## 2) عبر Git (من جهازك)

```bash
git clone https://github.com/engmohammeda/abu-omar-ceramics.git
cd abu-omar-ceramics

# عدّل/أضف ملفات
git add .
git commit -m "إضافة: وصف مختصر للتغيير"
git push origin main
```

## 3) تحديث ملف موجود من المتصفح

افتح الملف → أيقونة القلم ✏️ → عدّل → **Commit changes**.

## 4) قواعد التعامل مع المستودع

- **لا ترفع:** بيانات عملاء، أرقام هواتف خاصة، فواتير، صور شخصية بلا إذن.
- **لا ترفع:** صور موردين عليها علامة مائية.
- **ارفع:** نصوص، جداول، أصول بصرية من تصميمك.
- ملفات أكبر من 50MB تُرفع عبر Git LFS أو تُستبعد.

## 5) الرجوع لنسخة سابقة

- من GitHub: **Commits** → اختر الـ commit → **Browse files** → انسخ ما تحتاجه.
- من Git: `git log` ثم `git checkout <sha> -- path/to/file`.

## 6) كلمة على المفاتيح (Tokens)

- استخدم **Fine-grained token** مقيدًا بمستودع واحد فقط وبأقل صلاحية (Contents: Read/Write).
- لا تشارك المفتاح في محادثة أو ملف.
- ألغِ أي مفتاح شُكّ في ظهوره: Settings → Developer settings → Tokens → Revoke.
