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
    (อัพเดท)
    ทำหน้าที่เชื่อมคำถาม (Question) ไปยัง RAG (Langflow)
    (เวอร์ชันนี้ "แก้ไข Path สำหรับการ Parse JSON)
    """
    
    # (เดิม)
    user_question = event.message.text
    # (เดิม)
    reply_token = event.reply_token
    
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
        "session_id": str(uuid.uuid4()) 
    }

    try:
        # (เดิม)
        print(f"Asking Langflow (URL: {langflow_url}): {user_question}")

        # (เดิม)
        response = requests.post(langflow_url, json=payload, headers=headers, timeout=120)
        
        # (เดิม)
        response.raise_for_status() 

        # (อัพเดท)
        # 5. "ดึง" (Extract) "คำตอบ" (Answer) จาก JSON
        data = response.json()
        
        # (อัพเดท)
        # ================================================================
        # (เรา "จะ" (Will) "ลบ" (Remove) "โค้ด Debug" (Debug code) (ที่ "พิมพ์" (Prints) "JSON" (JSON) "ดิบ" (Raw)) "ทิ้ง" (Away) "ไป" (Away))
        # ================================================================

        # (อัพเดท)
        # (นี่คือ "Path" (Path) "ที่" (That) "ถูกต้อง" (Correct) (ที่ "อิง" (Based) "ตาม" (On) "Log" (Log) "ล่าสุด" (Latest) "จาก" (From) 17:58 น.))
        rag_answer = "Error: ไม่พบ 'results.message.data.text' ใน JSON" # (Error "ใหม่" (New) "ที่" (That) "ฉลาด" (Smarter) "ขึ้น" (Up))
        
        try:
            # (พยายาม (Try) "เจาะ" (Drill) "ลงไป" (Down) "ตาม" (To) "Path" (Path) "ที่" (That) "เรา" (We) "พบ" (Found))
            rag_answer = data['outputs'][0]['outputs'][0]['results']['message']['data']['text']
        
        except (KeyError, IndexError, TypeError) as e:
            # (ถ้า "Path" (Path) "พัง" (Breaks) "ระหว่าง" (Midway) "ทาง" (Way))
            print(f"!!! JSON Parsing Error: ไม่พบ Path ที่ถูกต้อง (Correct Path): {e}")
            # (rag_answer "จะ" (Will) "ยังคง" (Remain) "เป็น" (As) "Error: ไม่พบ...")

        # (เดิม)
        print(f"Langflow Answered: {rag_answer[:50]}...")

        # (เดิม)
        # 6. "ส่ง" (Send) "คำตอบ RAG" (RAG Answer) กลับไปหาผู้ใช้
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=rag_answer)
        )

    except requests.exceptions.RequestException as e:
        # (เดิม)
        # (กรณี "ยิง" (Call) Langflow "ล้มเหลว" (Failed) (เช่น 403 Forbidden))
        print(f"!!! Langflow RequestException: {e}")
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=f"Error: ไม่สามารถเชื่อมต่อ RAG (Langflow) ได้\n({e})")
        )

    except LineBotApiError as e:
        # (เดิม)
        print(f"!!! LineBotApiError (LINE_CHANNEL_ACCESS_TOKEN ผิด): {e}")
    
    except Exception as e:
        # (เดิม)
        print(f"!!! An unexpected error occurred in handle_message (RAG): {e}")
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=f"Error: เกิดข้อผิดพลาดภายใน (handle_message)\n({e})")
        )
    
    
    # # (ใหม่)
    # # ================================================================
    # # (นี่คือ "สวิตช์" (Toggle) "สำหรับ" (For) "ทดสอบ" (Testing) "Echo" (Echo))
    # if user_question.lower() == "test_echo":
    #     # (นี่คือ "โค้ด Echo" (Echo Code) "จาก" (From) "ขั้นที่ 3" (Step 3))
        
    #     print("--- (DEBUG) ECHO TEST REQUESTED ---")
        
    #     try:
    #         echo_answer = f"Echo: {user_question}"
            
    #         # (ยิง (Fire) "ตอบกลับ" (Reply) "ไป" (To) "LINE" (LINE))
    #         line_bot_api.reply_message(
    #             reply_token,
    #             TextSendMessage(text=echo_answer)
    #         )
            
    #         print("Echo test reply successful!")
        
    #     except LineBotApiError as e:
    #         # (ดักจับ (Catch) "กรณี" (Case) "ที่" (That) "ACCESS_TOKEN" (ACCESS_TOKEN) "ของ" (Of) "LINE" (LINE) "ผิด" (Wrong))
    #         print(f"!!! LineBotApiError (ECHO TEST FAILED - ACCESS_TOKEN อาจจะผิด): {e}")
        
    #     except Exception as e:
    #         print(f"!!! Unexpected error in ECHO TEST: {e}")

    # # (ใหม่)
    # # (ถ้า "ไม่ใช่" (NOT) "test_echo" (test_echo) ... "ให้" (Then) "ทำ" (Do) "RAG" (RAG) "ตามปกติ" (As normal))
    # else:
    #     # ================================================================
        
    #     # (อัพเดท)
    #     # --- (เริ่ม (Start) "RAG Bridge code v3 (Debug)") ---
        
    #     # (เดิม)
    #     # 1. ดึง "ที่อยู่" (URL) และ "Key" (Key) ของ Langflow (จาก .env)
    #     langflow_url = os.getenv('LANGFLOW_URL')
    #     langflow_key = os.getenv('LANGFLOW_API_KEY')

    #     # (เดิม)
    #     # 2. สร้าง "Headers" (Headers)
    #     headers = {
    #         "Authorization": f"Bearer {langflow_key}",
    #         "Content-Type": "application/json"
    #     }

    #     # (เดิม)
    #     # 3. สร้าง "Payload" (Payload)
    #     payload = {
    #         "output_type": "chat",
    #         "input_type": "chat",
    #         "input_value": user_question,
    #         "session_id": str(uuid.uuid4()) 
    #     }

    #     # (ใหม่)
    #     # 4. "ยิง" (Call) API ไป Langflow
    #     try:
    #         # (เดิม)
    #         print(f"Asking Langflow (URL: {langflow_url}): {user_question}")

    #         # (เดิม)
    #         response = requests.post(langflow_url, json=payload, headers=headers, timeout=120)
            
    #         # (เดิม)
    #         response.raise_for_status() 

    #         # (อัพเดท)
    #         # 5. "ดึง" (Extract) "คำตอบ" (Answer) จาก JSON
    #         data = response.json()
            
    #         # (ใหม่)
    #         # (พิมพ์ (Print) "JSON ดิบ" (Raw JSON) "ลงใน" (In) "Terminal 1" (Terminal 1))
    #         print("--- (DEBUG) FULL LANGFLOW RESPONSE (JSON) ---")
    #         print(json.dumps(data, indent=2, ensure_ascii=False)) 
    #         print("---------------------------------------------")
            
    #         # (เดิม)
    #         # (การ "คาดเดา" (Guessing) โครงสร้าง Output (Output structure))
    #         rag_answer = "Error: ไม่พบคำตอบใน JSON (Parsing failed)" 
            
    #         if 'outputs' in data and data['outputs']:
    #             first_output = data['outputs'][0]
    #             if 'outputs' in first_output and first_output['outputs']:
    #                 final_output = first_output['outputs'][0]
    #                 if 'results' in final_output and 'result' in final_output['results']:
    #                      rag_answer = final_output['results']['result'] 
    #                 elif 'text' in final_output:
    #                      rag_answer = final_output['text'] 

    #         # (เดิม)
    #         print(f"Langflow Answered: {rag_answer[:50]}...")

    #         # (เดิม)
    #         # 6. "ส่ง" (Send) "คำตอบ RAG" (RAG Answer) กลับไปหาผู้ใช้
    #         line_bot_api.reply_message(
    #             reply_token,
    #             TextSendMessage(text=rag_answer)
    #         )

    #     except requests.exceptions.RequestException as e:
    #         # (เดิม)
    #         # (กรณี "ยิง" (Call) Langflow "ล้มเหลว" (Failed) (เช่น 403 Forbidden))
    #         print(f"!!! Langflow RequestException: {e}")
    #         line_bot_api.reply_message(
    #             reply_token,
    #             TextSendMessage(text=f"Error: ไม่สามารถเชื่อมต่อ RAG (Langflow) ได้\n({e})")
    #         )

    #     except LineBotApiError as e:
    #         # (เดิม)
    #         print(f"!!! LineBotApiError (LINE_CHANNEL_ACCESS_TOKEN ผิด): {e}")
        
    #     except Exception as e:
    #         # (เดิม)
    #         print(f"!!! An unexpected error occurred in handle_message (RAG): {e}")
    #         line_bot_api.reply_message(
    #             reply_token,
    #             TextSendMessage(text=f"Error: เกิดข้อผิดพลาดภายใน (handle_message)\n({e})")
    #         )