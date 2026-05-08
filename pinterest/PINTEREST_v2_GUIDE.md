# NEXORA — Pinterest Pin Generator v2 (Site Crawler Edition)

## 🆕 الفرق بين v1 و v2

| الميزة | v1 (القديم) | v2 (الجديد) |
|---|---|---|
| **مصدر البيانات** | products.js محلي على جهازك | الموقع المنشور (sitemap.xml) |
| **رابط الـ pin** | يروح Amazon مباشرة | يروح NEXORA product page |
| **CTA على الصورة** | "Shop on Amazon →" | "Shop Now →" |
| **التحديث التلقائي** | لا — لازم تنزّل products.js | أيوه — يقرأ الموقع كل مرة |
| **حساسية للأخطاء** | يقف عند أي مشكلة | retry × 3 + يتخطى المنتج المعطل |

---

## 🚀 الاستخدام السريع

### ✅ الـ pins جاهزة بالفعل في `output_v2/upload/`

افتح الفولدر مباشرة وارفع الـ pins على Pinterest. مفيش حاجة لتشغيل أي سكريبت.

### 🔄 لو حبيت تعيد التوليد لاحقاً (لما تضيف منتجات جديدة)

```bash
# 1. تأكد إن Python 3.8+ مثبت + Pillow
pip install Pillow

# 2. شغّل الاسكريبت — يقرأ الموقع المنشور تلقائياً
python nexora_pinterest_v2.py

# 3. اختياري: جرّب على 3 منتجات بس
python nexora_pinterest_v2.py --limit 3

# 4. اختياري: غيّر الـ output path
python nexora_pinterest_v2.py --output ./my_pins

# 5. اختياري: غيّر الـ site
python nexora_pinterest_v2.py --site https://your-other-domain.com
```

---

## 📂 شكل المخرج

```
output_v2/
├── upload/                                      ⭐ ده اللي هتشتغل عليه
│   ├── account1_morning/                         (15 pin — الصبح 7-10 AM)
│   │   ├── tech/
│   │   │   ├── 01_voice-remote-control.../
│   │   │   │   ├── pin.png                       ← الصورة
│   │   │   │   ├── title.txt                     ← العنوان
│   │   │   │   ├── description.txt               ← الوصف بسطور
│   │   │   │   ├── link.txt                      ← https://nexora-shop-us.netlify.app/product/...
│   │   │   │   ├── board.txt                     ← اسم الـ board
│   │   │   │   └── info.txt                      ← كل التفاصيل في ملف واحد
│   │   │   └── 02_pack-of-2-remote-cover.../...
│   │   └── home/...
│   └── account2_night/                           (13 pin — بالليل 8-11 PM)
│       ├── beauty/...
│       └── pet/...
├── bulk_create_csv/                              (لو تحب تستخدم Pinterest Bulk Create)
│   ├── csv_account1_morning.csv                  (15 صف — Tech + Home)
│   └── csv_account2_night.csv                    (13 صف — Beauty + Pet)
└── (cache/ — أيقونات downloaded — تجاهلها)
```

---

## 🎨 4 ستايلات ممزوجة (مش spam في Pinterest)

| Style | الإحساس | الألوان |
|---|---|---|
| **Bold Dark** | Modern / Tech | خلفية داكنة + لون مميز للقسم |
| **Vibrant Gradient** | Lifestyle / Playful | متدرج لون القسم + كارد أبيض |
| **Minimalist Light** | Editorial / Clean | بيج + خط أسود كبير |
| **Luxe Gold** | Premium / Elegant | أسود + ذهبي |

كل قسم بياخد الـ 4 styles بالتدوير. كده Pinterest's algorithm يحب التنوع = reach أعلى.

---

## ⚡ مميزات v2

### 1. مقاومة الأخطاء (Robust)
- لو الـ network قطع → retry 3 مرات بتأخير 2s, 4s, 8s
- لو المنتج HTML غريب → يتخطاه (مش يقف الاسكريبت)
- رسائل خطأ واضحة لكل خطوة

### 2. يقرأ الموقع المنشور
- ينزّل sitemap.xml → يلاقي كل الـ /product/<slug>.html URLs
- يدخل كل صفحة يقرأ:
  - العنوان من `<h1>`
  - الصورة من Schema.org JSON-LD
  - السعر / السعر الأصلي / الخصم / التقييم / عدد المراجعات
  - القسم من Breadcrumb
- مفيش حاجة لـ scraping محلي

### 3. الرابط = NEXORA product page
- كل pin → product page على الموقع
- الزائر يقرأ التفاصيل في NEXORA → يضغط "Buy on Amazon" داخل الموقع
- ده بيعطي:
  - زيارات للموقع (= SEO authority)
  - Pinterest analytics لكل منتج
  - فرصة للزائر إنه يلف لمنتجات تانية
  - الموقع = "real brand" مش redirect link

---

## 🚀 Pinterest Setup خطوة بخطوة

### 🌅 Account 1 (Morning - 7-10 AM US)

1. افتح Chrome في وضع normal (مش incognito)
2. سجّل دخول الحساب الأول على https://pinterest.com
3. على البروفايل اضغط `+` → `Create Pin`
4. لكل فولدر في `account1_morning/`:
   1. اسحب `pin.png` لمساحة الصورة
   2. افتح `title.txt` → نسخ → الصق في "Title"
   3. افتح `description.txt` → نسخ → الصق في "Description"
   4. افتح `link.txt` → نسخ → الصق في "Destination URL"
   5. اختار الـ board من `board.txt`
   6. (اختياري) اختار "Schedule" واختار وقت بين 7-10 AM
   7. اضغط Publish

### 🌙 Account 2 (Night - 8-11 PM US)

1. **سجّل خروج من الحساب الأول** (مهم — Pinterest بيكتشف الحسابين لو متداخلين)
2. سجّل دخول الحساب الثاني
3. كرّر نفس الخطوات لكل فولدر في `account2_night/`
4. اختار وقت scheduling بين 8-11 PM

---

## 🧪 اختبار الاسكريبت قبل الـ deploy

```bash
# اختبر على 3 pins بس عشان تتأكد كل حاجة شغالة
python nexora_pinterest_v2.py --limit 3

# لو شغّال، احذف الـ output واشغّل الكامل
rm -rf output_v2/
python nexora_pinterest_v2.py
```

---

## 🔧 troubleshooting

### "ImportError: Could not import nexora_pinterest_generator"
- الاسكريبتين لازم يكونوا في **نفس الفولدر**.

### "No product URLs found in sitemap"
- اتأكد إن الموقع منشور على Netlify
- جرّب: `curl https://nexora-shop-us.netlify.app/sitemap.xml`
- لو مفيش حاجة، روح Netlify deploys واتأكد آخر deploy نجح

### "Pillow is required"
- شغّل: `pip install Pillow`

### الصور فاضية / مش بتنزّل
- ده أحياناً Amazon يحجب الصور — جرّب `--limit 5` الأول
- لو فضل المشكلة، الصور موجودة في cache فكل تشغيل تاني هيشتغل أسرع

---

## 📊 الإحصائيات بعد آخر تشغيل (May 2026)

- **28 pin** إجمالي (المنتجات الـ 28 اللي عاش فيها quality gate)
- **Account 1 Morning:** 15 pins (8 Tech + 7 Home)
- **Account 2 Night:** 13 pins (7 Beauty + 6 Pet)
- **توزيع الـ styles:** 8 Vibrant + 7 Bold + 7 Minimalist + 6 Luxe

---

## 🤖 تكامل مع Workflow المستقبلي

لو ضفت منتجات جديدة:
1. شغّل NEXORA Tool لإستخراج المنتجات
2. شغّل `nexora_site_builder.py` لتجديد الموقع
3. ادفع الـ ZIP لـ Netlify (drag & drop)
4. انتظر 30s
5. شغّل `nexora_pinterest_v2.py` → يقرأ الموقع المحدّث ويولّد pins جديدة

كده الـ pipeline بقى:
**NEXORA Scraper → Site Builder → Netlify Deploy → Pinterest v2 Generator**

كله ذاتي. مفيش شغل يدوي على المنتجات.
