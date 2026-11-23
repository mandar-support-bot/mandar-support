# MANDAR SUPPORT - طريقة التشغيل (خطوة بخطوة)

ملفات البوت جاهزة على GitHub، مش محتاج تعمل حساب GitHub ولا ترفع أي حاجة.
كله هياخد حوالي 10 دقايق.

## 1) افتح حساب Render (مجاني، من غير كارت بنكي)
1. افتح https://render.com واضغط **Get Started**.
2. سجّل بإيميلك وباسورد (مش محتاج GitHub ولا بطاقة بنكية).

## 2) اعمل خدمة البوت
1. من الداشبورد اضغط **New > Web Service**.
2. اختار **Public Git repository** والصق اللينك ده:
   `https://github.com/mandar-support-bot/mandar-support`
   واضغط Continue.
3. املى الإعدادات:
   - Name: `mandar-support`
   - Runtime: **Python 3**
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python bot.py`
   - Instance Type: **Free**
4. تحت عند **Environment Variables** دوس **Add Environment Variable**:
   - KEY: `DISCORD_TOKEN`
   - VALUE: التوكن بتاع البوت: افتح https://discord.com/developers/applications > تطبيق MANDAR SUPPORT > Bot > **Reset Token** > اعمل Copy للتوكن الجديد والصقه هنا.
5. اضغط **Deploy Web Service** واستنى دقيقتين.
6. لما تشوف في الـ Logs سطر فيه `MANDAR SUPPORT online as ...` يبقى تمام ✅ والبوت هيظهر Online في السيرفر.

## 3) خلّيه صاحي 24/7 (مهم)
Render المجاني بينام لو مفيش زيارات 15 دقيقة، فهنوقظه تلقائي:
1. افتح https://cron-job.org واعمل حساب مجاني.
2. اعمل Cronjob جديد: كل **10 دقائق**، والعنوان هو لينك خدمتك على Render (شكله `https://mandar-support.onrender.com` — هتلاقيه فوق في صفحة الخدمة).
3. كده البوت يفضل شغال طول اليوم مجانا.

## 4) تعديل ردود البوت بعدين
قولّي على التعديل اللي عايزه (أي رد، كلمات، رولز معفية) وأنا هعدّله في GitHub.
بعدها: افتح Render > خدمة mandar-support > **Manual Deploy > Deploy latest commit** عشان التعديل يتطبق.

## حساب GitHub بتاعك
الريبو متستضاف على حساب GitHub اتعمل بإيميلك (اسم المستخدم: mandar-support-bot).
الباسورد محفوظ عندنا في الخزنة، وتقدر تعمل Reset للباسورد من إيميلك في أي وقت.

## لو حاجة وقفت
افتح Render > الخدمة > Logs وابعتلي آخر سطور.
