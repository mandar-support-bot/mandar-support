# MANDAR SUPPORT - طريقة التشغيل (خطوة بخطوة)

## 1) شغّل الصلاحيات الخاصة في Discord Developer Portal
1. افتح https://discord.com/developers/applications واختار تطبيق MANDAR SUPPORT.
2. من القايمة شمال: **Bot**.
3. انزل لتحت عند **Privileged Gateway Intents** وفعّل:
   - **Server Members Intent**
   - **Message Content Intent**
4. اضغط **Save Changes**.

## 2) ادعُ البوت لسيرفرك
افتح لينك الدعوة اللي هيتبعتلك، اختار سيرفرك، Continue ثم Authorize.
(البوت محتاج الصلاحيات المكتوبة في اللينك: حذف الرسايل، تايم آوت للأعضاء، قراءة وكتابة الرسايل.)

## 3) ارفع ملفات البوت على GitHub
1. اعمل حساب مجاني على https://github.com (لو ماعندكش).
2. اعمل Repository جديد باسم `mandar-support` (Private عادي).
3. اضغط **Add file > Upload files** وارفع الملفات الخمسة:
   `bot.py` و `config.json` و `requirements.txt` و `runtime.txt` و `avatar.png`
4. اضغط **Commit changes**.

## 4) شغّل البوت على Render (مجاني، من غير كارت بنكي)
1. افتح https://render.com واعمل **Sign up with GitHub**.
2. من الداشبورد: **New > Web Service**.
3. اختار ريبو `mandar-support` واضغط **Connect**.
4. الإعدادات:
   - Name: `mandar-support`
   - Runtime: **Python 3**
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python bot.py`
   - Instance Type: **Free**
5. تحت عند **Environment Variables** ضيف:
   - KEY: `DISCORD_TOKEN`
   - VALUE: التوكن بتاع البوت (افتح Developer Portal > Bot > **Reset Token**، اعمل Copy للتوكن الجديد والصقه هنا)
6. اضغط **Deploy Web Service** واستنى دقيقتين.
7. لما تشوف في الـ Logs سطر فيه `MANDAR SUPPORT online as ...` يبقى البوت اشتغل ✅ وهيظهر Online في السيرفر.

## 5) خلّيه صاحي 24/7 (مهم)
Render المجاني بينام لو مفيش زيارات 15 دقيقة، فهنوقظه تلقائي:
1. افتح https://cron-job.org واعمل حساب مجاني.
2. اعمل Cronjob جديد: كل **10 دقائق**، والعنوان هو لينك خدمتك على Render (شكله `https://mandar-support.onrender.com`).
3. كده البوت يفضل شغال طول اليوم مجانا (750 ساعة مجانية في الشهر بتكفي خدمة واحدة 24/7).

## 6) تعديل ردود البوت بعدين
كل الردود والكلمات في ملف `config.json`: افتحه من GitHub > زرار القلم (Edit) > عدّل النص > Commit. Render هيعيد التشغيل لوحده.

## لو حاجة وقفت
افتح Render > الخدمة > Logs وابعتلي آخر سطور.
