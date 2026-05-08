# 📌 NEXORA Pinterest — Two Accounts Strategy

> دليل التوزيع الذكي على حسابين Pinterest Business (Morning + Night).
> Smart distribution across two Pinterest Business accounts.

---

## 🎯 ليه حسابين؟ | Why two accounts?

**عشان تتجنّب duplicate detection من Pinterest:**
- كل pin بيتنشر **مرة واحدة بس** على حساب واحد بس
- كل حساب له **niche** مختلف → Pinterest's algorithm يفهم audience أكتر
- Posting times مختلفة → reach أوسع جغرافياً
- Backup: لو حساب اتعطل، التاني سليم

---

## 📊 توزيع الحسابين

### 🌅 Account 1 — Morning Curator (نشر صباحي)
- **15 pins** | Tech (8) + Home (7)
- **CSV file:** `csv_account1_morning.csv`
- **Folders:** `pins/tech/` + `pins/home/`
- **Best posting time:** 7-10 AM US Eastern (US wakes up)
- **Profile name suggestion:** "NEXORA — Smart Tech & Home"
- **Bio suggestion:**
  > Curated Amazon finds for tech-savvy homes. Verified picks updated weekly. Editor-tested gadgets and home essentials.

### 🌙 Account 2 — Night Specialist (نشر مسائي)
- **15 pins** | Beauty (8) + Pet (7)
- **CSV file:** `csv_account2_night.csv`
- **Folders:** `pins/beauty/` + `pins/pet/`
- **Best posting time:** 8-11 PM US Eastern (peak Pinterest engagement)
- **Profile name suggestion:** "NEXORA — Beauty & Pet Picks"
- **Bio suggestion:**
  > Beauty essentials and pet must-haves, handpicked from Amazon. Daily inspiration for self-care and pet parents.

---

## 🪄 خطوات الإعداد لكل حساب

### Step 1: إنشاء الحساب
- روح: https://business.pinterest.com
- اضغط "Create a free business account"
- استخدم إيميل مختلف لكل حساب (لو معندكش، استخدم `karemali11+morning@gmail.com` و `karemali11+night@gmail.com` — Gmail بيقبل الـ `+` aliases)

### Step 2: Profile Setup
- اسم البروفايل: زي اللي فوق
- البايو: زي اللي فوق
- Website: `https://nexora-shop-us.netlify.app` (نفس الموقع للحسابين — مفيش مشكلة)
- Profile picture: استخدم لوجو NEXORA

### Step 3: Claim Website (للحسابين)
1. Settings → Claimed accounts → Claim website
2. يديك meta tag → ابعتهولي
3. أضيفه في `index.html` → ZIP → ترفعه على Netlify
4. Pinterest verifies ✓

⚠️ **مهم:** الموقع يقدر يكون مربوط بحسابين Business، Pinterest بيسمح بكده.

### Step 4: Create Boards (لكل حساب board مختلفة)

**Account 1:**
| Board | Description |
|---|---|
| **Smart Tech Finds** | Curated Amazon tech gadgets, smart home devices, and electronics. Editor-tested weekly. |
| **Home & Kitchen Inspiration** | Beautiful and practical home essentials, kitchen tools, and decor ideas — handpicked. |

**Account 2:**
| Board | Description |
|---|---|
| **Beauty & Self-Care Picks** | Tested beauty products, skincare gems, and self-care essentials. Editor-approved finds. |
| **Pet Lovers Essentials** | Toys, food, grooming tools, and innovative gear for cats and dogs. |

⚠️ **مهم:** أسماء الـ boards لازم تكون نفسها زي اللي في الـ CSV — Pinterest Bulk Create يربط الـ pins بالـ boards عبر الاسم.

### Step 5: رفع الـ pins (Bulk Create)

#### للحساب 1 (Morning):
1. سجل دخول للحساب الأول
2. روح: https://business.pinterest.com/bulk-create
3. اضغط "Upload images" → اختار الـ 15 PNG من `pins/tech/` + `pins/home/`
4. اضغط "Upload CSV" → اختار `csv_account1_morning.csv`
5. اختار "Schedule pins" → "Spread evenly across 14 days" → اختار التوقيت 7-10 AM
6. Publish ✅

#### للحساب 2 (Night):
1. **سجل خروج من الحساب 1** (مهم! عشان Pinterest يميّز الحسابين)
2. سجل دخول للحساب الثاني
3. نفس الخطوات بس استخدم: PNG من `pins/beauty/` + `pins/pet/` + `csv_account2_night.csv`
4. اختار التوقيت 8-11 PM
5. Publish ✅

---

## 🚫 احذر — أمور تتجنّبها

### ❌ ما تعملش:
1. **رفع نفس الـ pin على الحسابين** → Pinterest يكتشف ويعاقب
2. **استخدام نفس الـ description بالظبط** → نفس المشكلة
3. **تسجيل دخول بنفس الـ IP لكلا الحسابين في نفس الوقت** → ممكن Pinterest يعتبر sock puppet
4. **Cross-pinning بين الحسابين بكثرة** → خطر آخر
5. **متابعة الحساب الأول من الثاني** → علامة احمر

### ✅ تأكد من:
1. كل pin في حساب واحد بس
2. الـ boards أسماءها مختلفة بين الحسابين
3. الـ posting times مختلفة (صباح vs مساء)
4. لو ممكن، استخدم browsers مختلفة (Chrome للحساب 1، Firefox للحساب 2)
5. أو في Chrome، استخدم Profiles مختلفة

---

## 📈 KPI متوقع للأسبوع الأول

| Metric | Account 1 | Account 2 |
|---|---|---|
| Impressions | 200-500 | 250-600 (Beauty/Pet أكتر engagement على Pinterest) |
| Saves | 10-30 | 15-40 |
| Outbound clicks | 2-8 | 3-10 |

بعد شهر، الحساب 2 (Beauty/Pet) عادة بيتفوق لأن Pinterest's audience نسائي ٧٠٪.

---

## 🆘 لو حصل مشكلة

| المشكلة | الحل |
|---|---|
| Pinterest يقول "duplicate content" | تأكد إن الـ pin مش موجود في حساب تاني. لو موجود، احذفه من واحد. |
| Account suspended | تواصل Pinterest support وأكد إنك business واحد بحسابين منفصلين |
| Reach منخفض جداً | جرّب تغيّر titles/descriptions، Pinterest يحب التنوع |

---

## 📞 Support

أي مشكلة في الإعداد، ابعتلي screenshot.

**Email:** karemali11@gmail.com  
**Site:** https://nexora-shop-us.netlify.app

---

Made with ❤️ for NEXORA — Smart Finds. Better Life.
