# 📌 NEXORA Pinterest Setup Guide

> دليل كامل لرفع 30 pin على Pinterest وتفعيل Auto-Scheduling — بالعربي + English.
> Complete guide to uploading 30 pins to Pinterest and enabling auto-scheduling.

---

## 🎯 المحتوى | Contents

1. [إنشاء حساب Pinterest Business (مجاني)](#1-pinterest-business-account)
2. [تأكيد ملكية الموقع (claim website)](#2-claim-your-website)
3. [إنشاء الـ Boards (4 boards بأسماء موحّدة)](#3-create-boards)
4. [رفع الـ pins (Bulk Create + Scheduler)](#4-upload-pins)
5. [تفعيل Pinterest Analytics](#5-analytics)
6. [Tips للنجاح على Pinterest](#6-tips)

---

## 1) Pinterest Business Account
### إنشاء حساب Pinterest Business (مجاني — 5 دقائق)

### 🇸🇦 بالعربي:

1. روح على: **https://business.pinterest.com**
2. اضغط **"Create a free business account"** (مجاني تماماً)
3. سجّل بإيميلك: `karemali11@gmail.com`
4. كلمة سر قوية
5. اختار **"Create new account"** (مش "Convert existing")
6. اسم العمل: **NEXORA**
7. الرابط: `https://nexora-shop-us.netlify.app`
8. الدولة: اختار حسب موقعك (مفيش تأثير على الزوار الأمريكان)
9. اللغة: **English** (مهم — جمهورك أمريكي)
10. الفئة: **"Online retail"** أو **"Affiliate marketing"**
11. اضغط **"Next"** → **"Continue without creating an ad"** (مش هتعمل إعلانات دفع)

✅ **انتهيت — حسابك جاهز.**

### 🇬🇧 English:

1. Visit: **https://business.pinterest.com**
2. Click **"Create a free business account"**
3. Email: your account email
4. Strong password
5. Choose **"Create new account"** (not convert)
6. Business name: **NEXORA**
7. Website: `https://nexora-shop-us.netlify.app`
8. Country: your country
9. Language: **English** (audience is US-based)
10. Category: **"Online retail"** or **"Affiliate marketing"**
11. Click **"Next"** → **"Continue without creating an ad"**

---

## 2) Claim Your Website
### تأكيد ملكية الموقع (مهم لـ SEO + Verified Badge)

### 🇸🇦 بالعربي:

1. من الـ profile menu (يمين فوق)، اضغط **Settings** ⚙️
2. اختار **"Claimed accounts"** من القائمة الجانبية
3. تحت **"Websites"**، اضغط **"Claim"**
4. حط الرابط: `https://nexora-shop-us.netlify.app`
5. اختار طريقة التحقق: **"Add HTML tag"**
6. هتظهر `<meta name="p:domain_verify" content="XXXXXX" />`
7. **انسخ الـ tag** وابعتهولي أنا → هضيفه في `index.html` وأبعتلك ZIP محدّث
8. ترجع لـ Pinterest → **"Verify"** → ✅

### Why claim?
- Verified badge ✓ next to your name
- Pinterest Analytics بيشمل بيانات موقعك
- زوار أكتر بسبب الـ trust signal

---

## 3) Create Boards
### إنشاء 4 Boards (بنفس الأسماء المستخدمة في CSV)

### 🇸🇦 من الـ Profile:

1. اضغط زرار **"+"** فوق على اليمين → **"Board"**
2. أنشئ الـ 4 boards دول **بالظبط بنفس الأسماء**:

| Board Name | Description (نص جاهز للنسخ) |
|---|---|
| **Smart Tech Finds** | Curated Amazon tech gadgets, smart home devices, and electronics that make life easier. Updated weekly with deals. |
| **Home & Kitchen Inspiration** | Beautiful and practical home essentials, kitchen tools, and decor ideas — handpicked from Amazon's bestsellers. |
| **Beauty & Self-Care Picks** | Tested beauty products, skincare gems, and self-care essentials. Editor-approved Amazon finds for every routine. |
| **Pet Lovers Essentials** | Toys, food, grooming tools, and innovative gear for cats and dogs. Pet parents' favorite Amazon picks. |

### ⚠️ مهم:
**الأسماء لازم تكون نفسها** عشان Pinterest Bulk Create يربط كل pin بالـ board الصح تلقائياً.

---

## 4) Upload Pins
### رفع الـ 30 pin (Bulk Create + Scheduler)

### Option A: Bulk Upload عبر Pinterest Business Hub ⭐ (الأسرع)

1. روح على: **https://business.pinterest.com/bulk-create**
2. اضغط **"Create pins"** → اختار **"Use Bulk Create"**
3. **رفع الصور:**
   - اضغط **"Upload images"**
   - اختار كل الـ 30 PNG من المجلد `pins/` (تقدر تختار من كذا فولدر — Ctrl+A داخل كل فولدر)
   - استنى الرفع يخلص (1-2 دقيقة)
4. **رفع الـ CSV:**
   - اضغط **"Upload CSV"**
   - اختار `nexora_pins.csv`
   - Pinterest هيقرأ الـ CSV ويربط كل image بالـ row الخاص بيه (عبر اسم الملف)
5. **Pin scheduling:**
   - اختار **"Schedule pins"**
   - الـ default 3-5 pins per day على مدى أسبوعين (مثالي — مش spam)
   - اختار **"Spread evenly across 14 days"**
6. اضغط **"Publish"** — ✅ 

### Option B: لو Bulk Create مش متاح في حسابك

1. روح على Profile → اضغط **"+"** → **"Pin"**
2. ارفع الصورة الأولى من فولدر `pins/tech/01_*.png`
3. افتح `nexora_pins.csv` في Excel → اعمل copy للـ row الأولى
4. الصق:
   - **Title** (الخانة الأولى)
   - **Pin description** (الخانة الثانية)
   - **Destination link** (الخانة الثالثة)
   - **Board** اختار "Smart Tech Finds"
5. اضغط **"Publish"**
6. كرّر للباقي (30 pin × ~ دقيقة = 30 دقيقة)

> **💡 Tip:** Schedule pins for different times (morning, afternoon, evening US time) for max reach.

---

## 5) Analytics
### تفعيل Pinterest Analytics

1. من الـ Business Hub، اضغط **"Analytics"**
2. أول مرة Pinterest هيجمع البيانات بعد 24 ساعة من نشر أول pin
3. ابعد أسبوع، اطلع على:
   - **Impressions** (كم حد شاف الـ pins)
   - **Outbound clicks** (كم حد ضغط على الموقع)
   - **Saves** (Pinterest الـ "like" — مهم لـ algorithm)

---

## 6) Tips
### 🔥 نصائح أساسية لنجاح Pinterest:

### ⏱ التوقيت المثالي للنشر (US time):
- **Best:** Saturday 8-11 PM (peak engagement)
- **Good:** Mon-Fri 7-9 PM
- **OK:** أوقات الأكل (12-1 PM, 5-7 PM)

### 📊 ايه اللي بيرفع reach:
1. **Repin يومياً:** اعمل save لـ pins في boards تانية متعلقة (cross-pollination)
2. **Engagement الأول 30 دقيقة:** أرسل Pinterest link لأصحابك يـ save
3. **Hashtags:** Pinterest قلل أهمية hashtags لكن لسه بيساعد في discovery
4. **Keywords في الـ description:** اللي بيجيب Search traffic
5. **Fresh pins يومياً:** Pinterest يعشق المحتوى الجديد — حاول كل أسبوع تضيف 5-10 pins جديدة

### 🚫 تجنّب:
- نشر نفس الـ pin في نفس البورد مرتين
- Spam comments / DMs
- Stock images عامة (Pinterest بيكشفها)
- Click-bait titles

### 🎯 KPI للأسبوع الأول:
- **20-50 impressions/pin** = طبيعي (warm-up)
- **بعد أسبوعين:** ابدأ تشوف الـ pins المتميزة (high engagement)
- **بعد شهر:** اعمل scale للـ pins اللي شغّالة

---

## 📅 Timeline متوقع

| الأسبوع | المتوقع |
|---|---|
| 1-2 | Pinterest يبدأ في "indexing" الـ pins. Reach منخفض. |
| 3-4 | الـ pins القوية تبدأ تاخد موجة (impressions, saves). |
| 1-2 شهور | الـ pins الـ "evergreen" تبدأ تجيب outbound clicks ثابتة. |
| 3-6 شهور | Pinterest = أكبر مصدر traffic للموقع (إن شاء الله). |

---

## 🆘 لو واجهتك مشكلة

1. **Pinterest رفض الـ pin بسبب affiliate link:**  
   → Pinterest يدعم Amazon affiliate links 100%، لكن أحياناً بيعيد فحصها بعد الرفع. لو ظهرت رسالة، اعمل reach out لـ Pinterest support وابعتهم نسخة من Amazon Associates ID.

2. **CSV upload failed:**  
   → افتح الـ CSV في Excel, save as "CSV UTF-8" (مش "CSV (Comma Delimited)")

3. **Image quality warning:**  
   → كل الـ pins 1000×1500px (الأمثل). لو ظهر warning، تجاهله.

4. **Affiliate disclosure:**  
   → الـ pin descriptions بتاعتنا فيها سطر "As an Amazon Associate, NEXORA earns from qualifying purchases" → كده انت متوافق مع FTC + Pinterest policies.

---

## 📞 Support

أي مشكلة في الرفع أو في الـ Pinterest dashboard، ابعتلي screenshot وأنا هحلهالك.

**Email:** karemali11@gmail.com  
**Site:** https://nexora-shop-us.netlify.app

---

Made with ❤️ for NEXORA — Smart Finds. Better Life.
