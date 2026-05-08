# 🤖 NEXORA — Pinterest Automation Setup Guide
## دليل ربط Make.com بحسابات Pinterest

> **الفكرة الكبيرة:** Make.com يقرأ Google Sheet كل ساعة → كل صف فيه pin جاهز للنشر → يعمل router للحساب الصح → ينشر تلقائي → يحدّث الـ status في الـ sheet.
>
> **مفيش API tokens** — كل اتصال = login عادي بالـ email + password عبر OAuth popup من Pinterest نفسه.

---

## 📋 ما تحتاجه قبل البدء

| العنصر | المصدر | التكلفة |
|---|---|---|
| 2 × Pinterest Business Account | [pinterest.com/business](https://pinterest.com/business) | مجاني |
| 1 × Google Account | حسابك العادي | مجاني |
| 1 × Make.com account | [make.com](https://www.make.com/en/register) | مجاني (1K ops/شهر) |
| 1 × ImgBB API key | [api.imgbb.com](https://api.imgbb.com/) | مجاني unlimited |
| Python 3.8+ على جهازك | [python.org](https://python.org) | مجاني |

⏱ **الوقت الكلي للـ setup:** 30-45 دقيقة (مرة واحدة فقط)

---

## 🔧 المرحلة 1 — Python Pipeline (5 دقايق)

### الخطوة 1.1 — احصل على ImgBB API Key

1. اذهب إلى https://api.imgbb.com/
2. اضغط **"Get API key"** → سجّل دخول بـ Google
3. انسخ الـ API Key (سطر طويل)

### الخطوة 1.2 — شغّل الـ Pipeline

```bash
cd /path/to/nexora-pinterest-v2

# اختياري: حفظ الـ key كـ env variable
export IMGBB_API_KEY="paste_your_key_here"

# تشغيل الـ pipeline
python3 build_make_sheet.py
```

**النتيجة:**
```
================================================================
 NEXORA → Make.com Sheet Builder
================================================================
✓ Found 28 pin folders
✓ Hot 6 detection: 6 URLs flagged

  [01/28] Uploading tech-01 (pin.png) ... ✓
  [02/28] Uploading tech-02 (pin.png) ... ✓
  ...
  [28/28] Uploading pet-13 (pin.png) ... ✓

 ✓ CSV written: output_v2/make_sheet.csv
   28 rows × 20 columns
```

**أهم ملفين هتجدهم:**
- `output_v2/make_sheet.csv` ← هترفعه على Google Sheets في الخطوة الجاية
- `output_v2/make_sheet_uploads.json` ← cache (متمسحوش — لو شغّلت الـ pipeline تاني، هيعرف الصور المرفوعة قبل كده ومايرفعهاش تاني)

> 💡 **لو الإنترنت بطئ** أو وقع فجأة، شغّل الأمر تاني — هيكمّل من فين وقف بفضل الـ cache.

---

## 📊 المرحلة 2 — Google Sheets Setup (5 دقايق)

### الخطوة 2.1 — اعمل sheet جديد

1. اذهب إلى [sheets.google.com](https://sheets.google.com)
2. اضغط **"Blank"** لعمل sheet جديد
3. سمّيه: **NEXORA Pinterest Automation**

### الخطوة 2.2 — استورد الـ CSV

1. **File → Import**
2. اختر **Upload** → ارفع `output_v2/make_sheet.csv`
3. في الـ dialog:
   - **Import location:** "Replace current sheet"
   - **Separator type:** "Detect automatically"
   - **Convert text to numbers/dates:** "Yes"
4. اضغط **"Import data"**

### الخطوة 2.3 — احفظ Sheet ID

افتح الـ sheet وانظر لـ URL في المتصفح:

```
https://docs.google.com/spreadsheets/d/1aBcDeFgHiJkLmNoPqRsTuVwXyZ/edit#gid=0
                                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                       ده الـ Sheet ID — انسخه واحفظه
```

### الخطوة 2.4 — تحقق من الأعمدة

تأكد إن الـ sheet عنده الأعمدة دي بالترتيب ده **بالظبط** (مهم لـ Make.com):

| العمود | الاسم | المثال |
|---|---|---|
| A | id | tech-01 |
| B | account_key | account1_morning |
| C | category | tech |
| D | style | luxe |
| E | is_hot | TRUE |
| F | image_url | https://i.ibb.co/xxx/pin.png |
| G | image_thumb_url | https://i.ibb.co/xxx/pin-thumb.png |
| H | title | Smart Tech Find: ... |
| I | description | ✨ ... 💰 Now $17.77 ... |
| J | destination_url | https://nexora-shop-us.netlify.app/product/... |
| K | board_name | Smart Tech Finds |
| L | publish_at | 2026-05-07 11:00:00 |
| M | status | ready |
| N | posted_pinterest_at | (فارغ) |
| O | pinterest_pin_id | (فارغ) |
| P | posted_facebook_at | (فارغ) |
| Q | posted_instagram_at | (فارغ) |
| R | posted_youtube_at | (فارغ) |
| S | video_url | (فارغ) |
| T | notes | (فارغ) |

> 💡 **عدّل في الـ sheet براحتك:** ممكن تغيّر `publish_at` لو حابب توقيت تاني، أو تخلي بعض الـ rows `status=ready` والباقي `status=draft` لو مش عايزها كلها تتنشر دلوقتي.

---

## 🎨 المرحلة 3 — Pinterest Boards Setup (10 دقايق)

⚠️ **مهم:** قبل ما تربط Make.com، لازم البـ boards دي تكون موجودة في حساباتك على Pinterest.

### الحساب 1 (Morning) — احتاج Boards دي:
| Category | Board Name |
|---|---|
| Tech | **Smart Tech Finds** |
| Home | **Home & Kitchen Inspiration** |

### الحساب 2 (Night) — احتاج Boards دي:
| Category | Board Name |
|---|---|
| Beauty | **Self-Care & Beauty** |
| Pet | **Pet Parents Picks** |

### الخطوات:

**على كل حساب Pinterest:**
1. سجّل دخول
2. اضغط **"Create board"**
3. حط الاسم بالضبط زي الجدول فوق
4. اختار **"Public"** (مش Secret)
5. كرّر للـ board التاني

> 💡 لو الـ boards عندك أصلاً بأسماء تانية، لازم **تغيّر الـ `board_name` في الـ sheet** عشان يطابق أسماء الـ boards بتاعتك.

---

## ⚙️ المرحلة 4 — Make.com Setup (15-20 دقيقة)

### الخطوة 4.1 — اعمل حساب Make.com

1. اذهب إلى [make.com/en/register](https://www.make.com/en/register)
2. سجّل بـ Google (أسهل)
3. اختر **"Free plan"** للبداية
4. لما يدخّلك للـ Dashboard، اضغط **"Scenarios"** من القائمة الجانبية

### الخطوة 4.2 — استورد الـ Blueprint

1. اضغط **"Create a new scenario"**
2. في الـ canvas الفارغ، اضغط على ⋯ (3 نقاط) في الأسفل
3. اختر **"Import Blueprint"**
4. ارفع الملف: **`make_blueprints/blueprint_pinterest_auto_poster.json`**
5. هتلاقي الـ scenario كاملة بـ 6 modules:

```
[Search Sheet Rows] → [Router] ─┬─→ [Pinterest Acc1] → [Update Sheet]
                                └─→ [Pinterest Acc2] → [Update Sheet]
```

### الخطوة 4.3 — ربط Google Sheets

1. اضغط على module **"Search Rows"** (الأولاني)
2. هيظهر علامة ⚠ على الـ Connection (لأن الـ blueprint عنده placeholder)
3. اضغط **"Add"** بجنب Connection
4. اختر **"Sign in with Google"** → اعمل login
5. اضغط **"Allow"** على كل الصلاحيات (Make يحتاج read/write على Sheets)
6. في حقل **Spreadsheet** → اختر **"Select from a list"** → اختار `NEXORA Pinterest Automation`
7. في حقل **Sheet name** → اختار `Sheet1`
8. خلّي **"Range"** فاضي (Make هيقرأ كل الـ sheet)
9. **"Includes headers?"** → Yes
10. اضغط **"OK"**

### الخطوة 4.4 — ربط Pinterest Account 1

1. اضغط على module **"Create a Pin"** (الفرع العلوي — تحت Account 1)
2. علامة ⚠ على الـ Connection
3. اضغط **"Add"** بجنب Connection
4. سمّي الـ connection: **`NEXORA - Pinterest Account 1`**
5. اضغط **"Save"**
6. هيفتح popup من Pinterest:
   - حط email + password بتاع **الحساب الأول** (Morning)
   - اضغط **"Allow"** لكل الصلاحيات (Make يحتاج Write/Read على pins + boards)
7. لما الـ popup يقفل، ارجع لـ Make
8. في حقل **Board** → هتلاقي dropdown فيه كل الـ boards بتاعت الحساب
9. **خد بالك:** الـ blueprint بيحدد الـ board من الـ sheet (`{{1.board_name}}`)، فممكن تخلّي الحقل ده بهذا التعبير، أو تختار board ثابت يدوي
10. باقي الحقول (Title, Description, Image URL, Destination Link) معبّاية تلقائياً من الـ sheet — متغيرش حاجة فيها
11. اضغط **"OK"**

### الخطوة 4.5 — ربط Pinterest Account 2

نفس الخطوات 4.4 بالضبط، بس:
- الـ module: **"Create a Pin"** (الفرع السفلي — تحت Account 2)
- اعمل **connection جديدة** اسمها: **`NEXORA - Pinterest Account 2`**
- استخدم email + password بتاع **الحساب الثاني** (Night)

> ⚠️ **مهم:** لازم تكون 2 connections منفصلين. متستخدمش connection الحساب 1 للحساب 2.

### الخطوة 4.6 — ربط Update Sheet (× 2)

في الـ blueprint عندك module اسمه **"Update a Row"** بعد كل Pinterest module. بيحدّث الـ sheet بالـ status الجديد:

1. اضغط على module **"Update a Row"** (تحت Account 1)
2. لو الـ Connection مش موجود، اضغط **Add** واستخدم نفس Google connection اللي عملته في 4.3
3. في **Spreadsheet** → اختار `NEXORA Pinterest Automation`
4. في **Row number** → خلّيها معبّاية بـ `{{1.__ROW_NUMBER__}}` (تلقائي)
5. اضغط **"OK"**
6. كرّر نفس الخطوات للـ "Update a Row" الثاني (تحت Account 2)

### الخطوة 4.7 — اختبار سريع (Run once)

1. تأكد إن الـ sheet عنده على الأقل **1 row بـ status=ready** و publish_at زمنه عدّى
2. في الـ scenario، اضغط على **"Run once"** (الزرار الأرجواني تحت)
3. شوف بصرياً:
   - module 1 (Search Rows) → بيرجّع row(s) من الـ sheet
   - module 2 (Router) → بياخد كل row ويوزّع
   - module 3/5 (Pinterest) → بيعمل pin
   - module 4/6 (Update Row) → بيحدّث الـ sheet → `status=posted`
4. افتح Pinterest في tab تاني → هتلاقي الـ pin اتنشر
5. ارجع للـ sheet → الـ row `status` بقى "posted" + `posted_pinterest_at` معبّى

### الخطوة 4.8 — شغّل الـ Schedule

1. لما الاختبار ينجح، ارجع للـ scenario
2. اضغط على الـ ⏰ scheduling icon (تحت يسار الكنفاس)
3. اختار **"At regular intervals"** → كل **60 دقيقة** (موصى)
4. ⚠️ **متعملش أقل من 30 دقيقة** — Pinterest بيحس spam
5. شغّل الـ toggle للـ **"Activate"** فوق على اليمين

✅ **الـ system شغّال دلوقتي تلقائياً!** كل ساعة Make هيشيك على الـ sheet ويعمل الـ pins اللي زمنها عدّى.

---

## 📈 إزاي تتابع وتدير النظام

### إضافة pins جديدة:

```bash
# على الـ site:
1. ضيف منتجات جديدة على NEXORA tool
2. رفع site جديد على Netlify

# على جهازك:
3. python nexora_pinterest_v2.py --refresh    # pins للجديد بس
4. python build_make_sheet.py                  # يضيف الـ rows الجديدة على CSV
5. ارفع الـ CSV الجديد على Google Sheets:
   File → Import → Replace current sheet (أو append rows جديدة)
6. Make.com هيلتقطها تلقائياً في الـ run الجاي
```

### تعديل الـ schedule:

في الـ sheet، عمود `publish_at`:
- **فاضي** = ينشر في أقرب فرصة (في next run)
- **`2026-05-07 14:00:00`** = ينتظر للوقت ده
- ممكن تعدّل أي time في أي وقت — Make.com يقرأ القيمة الجديدة في الـ run الجاي

### إيقاف pin معين:

غيّر الـ `status` من `ready` لـ `paused` أو `draft` — Make.com مش هيلمسه.

### معرفة الفشل:

لو Make.com فشل ينشر pin:
- الـ `status` يبقى `error`
- الـ `notes` يحتوي رسالة الخطأ
- في Make.com → Scenario → History → اشوف الـ logs

---

## 🔒 حدود مهمة لازم تعرفها

### Pinterest:
- **Daily Limit:** ~25 pin/يوم لكل حساب (مش 100 زي ما الـ docs بتقول — في الواقع، أكتر من 25 بيؤدي إلى shadow ban)
- **Rate Limit:** 1 pin كل 30 دقيقة على الأقل
- **التوصية:** 8-12 pin/يوم لكل حساب، بفاصل 60 دقيقة (موصى schedule)

### Make.com Free Plan:
- **1,000 operations/شهر** — كل pin عملية
- 28 pin × ~4 ops = 112 ops لكل full run = **~9 full runs/شهر**
- لو هتنشر 28 pin أسبوعياً، الـ Free plan كافي
- **الترقية:** Core Plan **$9/شهر** = 10K ops (يكفي 89 full runs)

### ImgBB:
- مفيش حدود على عدد الصور
- بس الصورة الواحدة لازم ≤ 32 MB
- pin.png عندك ~600 KB بس، فمفيش مشكلة

---

## 🐛 حل المشاكل الشائعة

### "Connection failed" على Pinterest
- **السبب:** الحساب Personal مش Business
- **الحل:** [pinterest.com/business/convert](https://www.pinterest.com/business/convert/) (دقيقة واحدة)

### "Image URL not accessible"
- **السبب:** ImgBB رفض الصورة (نادر) أو الـ URL منتهي صلاحيته
- **الحل:** شغّل `python build_make_sheet.py --refresh` لإعادة رفع الصور

### "Board not found"
- **السبب:** اسم الـ board في الـ sheet ≠ اسم الـ board في Pinterest
- **الحل:** عدّل عمود `board_name` في الـ sheet ليطابق الاسم الفعلي

### "Rate limit exceeded"
- **السبب:** Pinterest حسّ بـ spam (أكتر من 1 pin / 30 دقيقة)
- **الحل:** زوّد الـ schedule في Make.com لـ 90 دقيقة، وقلّل عدد الـ pins بـ status=ready

### Make.com يبعت زي operations كتير
- **السبب:** الـ scenario بتاخد كل rows في الـ sheet مع كل run
- **الحل:** تأكد إن الفلتر `status=ready` شغّال — الـ rows اللي اتنشرت قبل كده بقت `status=posted`

---

## 🚀 الخطوة الجاية بعد ما Pinterest يستقر

لما الـ Pinterest automation تشتغل لمدة أسبوع بدون مشاكل، هنضيف:

1. **Phase 7C — Facebook + Instagram** (نفس النظام تماماً، blueprint جديد)
2. **Phase 7D — YouTube Shorts** (يحتاج فيديوهات تعملها بـ CapCut/Canva)
3. **Phase 7E — TikTok** (عبر Buffer + Zapier — ميدل لاير)

كل blueprint هيكون نفس الـ pattern:
- **Read sheet** → **Router** → **Post on platform** → **Update sheet**

---

## 📞 لو احتجت مساعدة

- Make.com Community: [community.make.com](https://community.make.com)
- Pinterest Help: [help.pinterest.com](https://help.pinterest.com)
- ImgBB Status: [status.imgbb.com](https://status.imgbb.com)

---

**🎉 مبروك! النظام دلوقتي يعمل pins تلقائياً 24/7 بدون تدخّل منك.**
