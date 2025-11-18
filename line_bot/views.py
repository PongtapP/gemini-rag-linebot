# Import (นำเข้า) เครื่องมือที่จำเป็นจาก Django และ LINE SDK
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

import requests
import os
import uuid
import json

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
            print("!!! InvalidSignatureError (Channel SECRET อาจจะผิด)")
            return HttpResponseForbidden()
        except Exception as e:
            # ถ้าเกิด Error อื่นๆ
            print(f"!!! Uncaught Exception in callback: {e}")
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
    ทำหน้าที่เชื่อมคำถาม (Question) ไปยัง RAG (Langflow)
    (เพิ่ม Logic สำหรับการแสดง Loading Animation ของ LINE)
    """
    user_question = event.message.text
    reply_token = event.reply_token
    user_id = event.source.user_id # ดึง user_id เพื่อใช้ในการส่ง Loading Request

    # เริ่มแสดง Loading Animation (จุดสามจุด) ทันทีที่ได้รับข้อความ
    # Logic นี้ถูกแยกออกมาเพื่อไม่ให้กระทบกับการเรียก Langflow
    LOADING_URL = "https://api.line.me/v2/bot/chat/loading/start"
    
    # Note: ใช้ line_bot_api.channel_access_token สำหรับ Authorization
    loading_headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {settings.LINE_CHANNEL_ACCESS_TOKEN}'
    }

    # Payload สำหรับ Loading: ใช้ user_id เป็น chatId และตั้งเวลา
    loading_payload = {
        "chatId": user_id,
        "loadingSeconds": 60 # 60 วินาที (ต้องเป็น multiples ของ 5)
    }

    try:
        requests.post(LOADING_URL, headers=loading_headers, json=loading_payload)
        print(f"[UI] Successfully started loading animation for user: {user_id}")
    except requests.exceptions.RequestException as e:
        # หากล้มเหลวในการแสดง Loading ให้พิมพ์ข้อผิดพลาดแล้วข้ามไป
        # เพื่อให้การทำงานหลัก (เรียก Langflow) ยังคงดำเนินต่อไปได้
        print(f"!!! [UI] Failed to start loading animation: {e}")
        pass

    # เตรียมข้อมูลและ Header สำหรับเรียก Langflow (RAG)
    langflow_url = os.getenv('LANGFLOW_URL')
    langflow_key = os.getenv('LANGFLOW_API_KEY')
    
    headers = {
        "Authorization": f"Bearer {langflow_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "output_type": "chat",
        "input_type": "chat",
        "input_value": user_question,
        # ใช้ user_id เป็น session_id เพื่อให้ Langflow สามารถจดจำ Session ได้
        "session_id": user_id 
    }

    try:
        print(f"Asking Langflow (URL: {langflow_url}): {user_question}")

        response = requests.post(langflow_url, json=payload, headers=headers, timeout=120)

        response.raise_for_status() 

        # ดึงคำตอบจาก JSON
        data = response.json()
        
        rag_answer = "Error: ไม่พบ 'outputs[0].outputs[0].results.message.data.text' ใน JSON"
        
        try:
            # (นี่คือ Path ที่ถูกแก้ไขล่าสุดตามการวิเคราะห์ของคุณ)
            rag_answer = data['outputs'][0]['outputs'][0]['results']['message']['data']['text']
        
        except (KeyError, IndexError, TypeError) as e:
            # (ถ้า Path พังระหว่างทาง)
            print(f"!!! JSON Parsing Error: ไม่พบ Path ที่ถูกต้อง (Correct Path): {e}")
            # (rag_answer จะยังคงเป็น Error: ไม่พบ...)
            
        print(f"Langflow Answered: {rag_answer[:50]}...")

        # ส่งคำตอบ RAG (RAG Answer) กลับไปหาผู้ใช้
        # การส่งข้อความตอบกลับด้วย reply_message จะยกเลิก Loading Animation อัตโนมัติ
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=rag_answer)
        )

    except requests.exceptions.RequestException as e:
        # (กรณี "ยิง" (Call) Langflow "ล้มเหลว" (Failed) (เช่น 403 Forbidden))
        print(f"!!! Langflow RequestException: {e}")
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=f"Error: ไม่สามารถเชื่อมต่อ RAG (Langflow) ได้\n({e})")
        )

    except LineBotApiError as e:
        print(f"!!! LineBotApiError (LINE_CHANNEL_ACCESS_TOKEN ผิด): {e}")
    
    except Exception as e:
        print(f"!!! An unexpected error occurred in handle_message (RAG): {e}")
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=f"Error: เกิดข้อผิดพลาดภายใน (handle_message)\n({e})")
        )