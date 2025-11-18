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

# --- โหลดการตั้งค่า Langflow จาก .env ---
# เราจะโหลดค่า Config ทั้งหมดไว้ที่นี่ เพื่อให้ handle_message สะอาดขึ้น
# และเป็นการเตรียมพร้อมสำหรับ Production Mode
LANGFLOW_API_URL = os.environ.get("LANGFLOW_API_URL") # เช่น http://localhost:7860/api/v1/run/
FLOW_ID = os.environ.get("FLOW_ID")               # เช่น 568fe4cc-f389...
LANGFLOW_API_KEY = os.environ.get("LANGFLOW_API_KEY")   # sk-....
# --- สิ้นสุดการตั้งค่าใหม่ ---

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
    # --- สิ้นสุด Logic Loading Animation ---

    # ตรวจสอบว่า Configs (ที่โหลดด้านบน) ครบถ้วนหรือไม่
    if not LANGFLOW_API_URL or not FLOW_ID or not LANGFLOW_API_KEY:
        print("!!! Error: LANGFLOW_API_URL, FLOW_ID, หรือ LANGFLOW_API_KEY ไม่ได้ตั้งค่าใน .env")
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text="Error: RAG (Langflow) ไม่ได้ตั้งค่าใน .env")
        )
        return

    # สร้าง URL ปลายทาง
    # (แทนที่ os.getenv('LANGFLOW_URL') เดิม)
    full_url = f"{LANGFLOW_API_URL}{FLOW_ID}"

    # กำหนด Headers: ใช้ X-Api-Key (สำหรับ Production Auth)
    # นี่คือการเปลี่ยนแปลงสำคัญเพื่อแก้ปัญหา 403 Forbidden
    # เราจะไม่ใช้ 'Authorization: Bearer' อีกต่อไป
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "X-Api-Key": LANGFLOW_API_KEY 
    }

    # สร้าง Payload: เปลี่ยนเป็น 'text'/'chat'
    # เราต้องการ 'json' output เพื่อให้ Python (ในข้อ 6) parse ได้ง่าย
    # (แทน 'chat'/'chat' เดิม)
    payload = {
        "input_value": user_question,   # <-- (แก้ไข) แก้ไขจาก user_query เป็น user_question
        "input_type": "chat",       
        "output_type": "chat",      # <-- (แก้ไข) เปลี่ยน "json" กลับเป็น "chat"
        "session_id": user_id 
    }

    try:
        # ยิง Request ไปยัง Langflow (ใช้ full_url ใหม่)
        print(f"-> Calling Langflow (Production Mode): {full_url}")
        print(f"-> Payload: {payload}")
        print(f"-> Using API Key: {LANGFLOW_API_KEY[:4]}...")

        response = requests.post(
            full_url, 
            headers=headers, 
            json=payload, 
            timeout=120
        )

        response.raise_for_status() 

        # อ่านคำตอบจาก JSON
        final_output = response.json()
        

        rag_answer = "ขออภัย ไม่พบคำตอบที่ชัดเจน" # (ค่าเริ่มต้น)
        
        # Logic การ Parse JSON ที่อัปเดตตาม RAW JSON
        try:
            # พยายามดึงคำตอบจาก Path ที่ 1 (สั้นที่สุดและเห็นใน Log)
            rag_answer = final_output['outputs'][0]['outputs'][0]['results']['message']['text']
            
        except (KeyError, IndexError, TypeError):
            try:
                # พยายามดึงคำตอบจาก Path ที่ 2 (Path เดิมจากขั้น 4.3)
                rag_answer = final_output['outputs'][0]['outputs'][0]['results']['message']['data']['text']
                
            except (KeyError, IndexError, TypeError):
                try:
                    # พยายามดึงคำตอบจาก Path ที่ 3 (Fallback)
                    rag_answer = final_output['outputs'][0]['outputs'][0]['outputs']['message']['message']
                
                except (KeyError, IndexError, TypeError) as e:
                    print(f"!!! JSON Parsing Error: ไม่พบ Path ที่ถูกต้องทั้งหมดหลังจากพยายาม 3 รูปแบบ: {e}")
                    # rag_answer จะยังคงเป็นค่าเริ่มต้น
            
        print(f"Langflow Answered: {rag_answer[:50]}...")

        # ส่งคำตอบ RAG (RAG Answer) กลับไปหาผู้ใช้
        # (เก็บไว้เหมือนเดิม)
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=rag_answer)
        )

    except requests.exceptions.HTTPError as e:
        # เพิ่มการจัดการ HTTP Error (เช่น 403/404)
        print(f"!!! Langflow HTTPError: {e.response.status_code}")
        print(f"!!! Response Body: {e.response.text[:200]}...")
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=f"Error: Langflow HTTP {e.response.status_code}. (ตรวจสอบ API Key/Flow ID)")
        )
    except requests.exceptions.RequestException as e:
        # (Connection error)
        print(f"!!! Langflow RequestException: {e}")
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=f"Error: ไม่สามารถเชื่อมต่อ RAG (Langflow) ได้\n({e})")
        )

    except LineBotApiError as e:
        print(f"!!! LineBotApiError (LINE_CHANNEL_ACCESS_TOKEN ผิด): {e}")
    
    except Exception as e:
        # (Error ทั่วไป)
        print(f"!!! An unexpected error occurred in handle_message (RAG): {e}")
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=f"Error: เกิดข้อผิดพลาดภายใน (handle_message)\n({e})")
        )