# Import (นำเข้า) เครื่องมือที่จำเป็นจาก Django และ LINE SDK
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# เชื่อมต่อ API และ Handler กับ Keys (Placeholders) จาก settings.py
# ดึงค่าจาก settings.py เพื่อความปลอดภัย
line_bot_api = LineBotApi(settings.LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(settings.LINE_CHANNEL_SECRET)

# ฟังก์ชันนี้ทำหน้าที่เป็น "ประตู" (Webhook Endpoint)
# @csrf_exempt: คือ "ป้ายยกเว้น" ที่บอก Django ว่า "ไม่ต้องตรวจสอบ CSRF Token"
# เพราะ Request นี้มาจาก LINE Server โดยตรง ไม่ได้มาจากหน้าเว็บ
@csrf_exempt
def callback(request):
    """
    ทำหน้าที่รับ 'POST' request ที่ LINE Server ยิงมา (Webhook)
    """
    
    # ตรวจสอบว่าเป็นการส่งแบบ POST เท่านั้น
    if request.method == 'POST':
        # ดึง "ลายเซ็น" (Signature) จาก Header เพื่อยืนยันว่าเป็น LINE จริงๆ
        signature = request.headers['X-Line-Signature']
        
        # ดึง "เนื้อหา" (Body) ของ Request
        body = request.body.decode('utf-8')

        try:
            # ให้ 'handler' (จาก SDK) ตรวจสอบลายเซ็น และ
            # ส่งต่อไปให้ฟังก์ชัน 'handle_message' (หรือตัวอื่นๆ ที่เรา @add ไว้)
            handler.handle(body, signature)
        except InvalidSignatureError:
            # ถ้าลายเซ็นไม่ถูกต้อง (คนอื่นพยายามยิงมา)
            return HttpResponseForbidden()
        except Exception as e:
            # ถ้าเกิด Error อื่นๆ
            return HttpResponseBadRequest()
        
        # ถ้าสำเร็จ ให้ตอบ "OK" (Status 200) กลับไปให้ LINE
        return HttpResponse(status=200)
    else:
        # ถ้าไม่ใช่ POST (เช่น มีคนเข้าผ่าน Browser)
        return HttpResponseBadRequest("Method Not Allowed")
    
# ฟังก์ชันนี้ทำหน้าที่ "จัดการข้อความ" (Message Handler)
# @handler.add: คือการ "ลงทะเบียน" ฟังก์ชันนี้กับ 'handler'
# บอกว่า: "ถ้ามีเหตุการณ์ 'MessageEvent' ที่เป็น 'TextMessage' (ข้อความตัวอักษร) ให้เรียกฟังก์ชันนี้"
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """
    ทำหน้าที่ประมวลผลเมื่อได้รับ "ข้อความ" (TextMessage) จากผู้ใช้
    (นี่คือ "Bridge" ที่จะเชื่อมไป RAG ในอนาคต)
    """
    
    # ดึงข้อความที่ผู้ใช้พิมพ์มา
    user_question = event.message.text
    
    # ดึง "ตั๋ว" สำหรับการตอบกลับ (Reply Token)
    reply_token = event.reply_token
    
    # --- (ส่วนทดสอบ Echo) ---
    # ในอนาคต เราจะเปลี่ยนบรรทัดนี้เป็นการ "เรียก Langflow" (RAG)
    echo_answer = f"Echo: {user_question}"
    
    # สั่งให้ API ตอบกลับข้อความ Echo นี้ไปหาผู้ใช้
    line_bot_api.reply_message(
        reply_token,
        TextSendMessage(text=echo_answer)
    )