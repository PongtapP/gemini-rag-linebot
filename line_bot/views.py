# Import necessary tools from Django and LINE SDK
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

# Connect API and Handler with Keys from settings.py
# Retrieve values from settings.py for security
line_bot_api = LineBotApi(settings.LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(settings.LINE_CHANNEL_SECRET)

# --- Load Langflow settings from .env ---
# We will load all Config values here to keep handle_message clean
# and to prepare for Production Mode
LANGFLOW_API_URL = os.environ.get("LANGFLOW_API_URL") # e.g., http://localhost:7860/api/v1/run/
FLOW_ID = os.environ.get("FLOW_ID")               # e.g., 568fe4cc-f389...
LANGFLOW_API_KEY = os.environ.get("LANGFLOW_API_KEY")   # sk-....
# --- End of new settings ---

# This function acts as the "gate" (Webhook Endpoint)
# @csrf_exempt: is an "exemption tag" that tells Django "not to check for a CSRF Token"
# because this request comes directly from the LINE Server, not from a web page
@csrf_exempt
def callback(request):
    """
    Handles the 'POST' request sent by the LINE Server (Webhook).
    """
    
    # Check that it's a POST request only
    if request.method == 'POST':
        # Get the "signature" from the header to verify that it's from LINE
        signature = request.headers['X-Line-Signature']
        
        # Get the "body" of the request
        body = request.body.decode('utf-8')

        try:
            # Let the 'handler' (from the SDK) validate the signature and
            # pass it on to the 'handle_message' function (or others we @add)
            handler.handle(body, signature)
        except InvalidSignatureError:
            # If the signature is invalid (someone else is trying to send a request)
            print("!!! InvalidSignatureError (Channel SECRET might be wrong)")
            return HttpResponseForbidden()
        except Exception as e:
            # If other errors occur
            print(f"!!! Uncaught Exception in callback: {e}")
            return HttpResponseBadRequest()
        
        # If successful, respond with "OK" (Status 200) to LINE
        return HttpResponse(status=200)
    else:
        # If not a POST (e.g., someone accesses through a browser)
        return HttpResponseBadRequest("Method Not Allowed")
    
# This function acts as the "Message Handler"
# @handler.add: "registers" this function with the 'handler'
# It says: "If there's a 'MessageEvent' that is a 'TextMessage', call this function"
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """
    Connects the question to the RAG (Langflow)
    (Adds logic for displaying LINE's loading animation)
    """
    user_question = event.message.text
    reply_token = event.reply_token
    user_id = event.source.user_id # Get user_id to send loading request

    # Start displaying the loading animation (three dots) as soon as the message is received
    # This logic is separated to not affect the Langflow call
    LOADING_URL = "https://api.line.me/v2/bot/chat/loading/start"
    
    # Note: Use line_bot_api.channel_access_token for Authorization
    loading_headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {settings.LINE_CHANNEL_ACCESS_TOKEN}'
    }

    # Payload for Loading: use user_id as chatId and set a timeout
    loading_payload = {
        "chatId": user_id,
        "loadingSeconds": 60 # 60 seconds (must be a multiple of 5)
    }

    try:
        requests.post(LOADING_URL, headers=loading_headers, json=loading_payload)
        print(f"[UI] Successfully started loading animation for user: {user_id}")
    except requests.exceptions.RequestException as e:
        # If loading fails, print the error and skip
        # so that the main process (calling Langflow) can continue
        print(f"!!! [UI] Failed to start loading animation: {e}")
        pass
    # --- End of Loading Animation Logic ---

    # Check if the configs (loaded above) are complete
    if not LANGFLOW_API_URL or not FLOW_ID or not LANGFLOW_API_KEY:
        print("!!! Error: LANGFLOW_API_URL, FLOW_ID, or LANGFLOW_API_KEY not set in .env")
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text="Error: RAG (Langflow) is not configured in .env")
        )
        return

    # Create the destination URL
    # (replaces the old os.getenv('LANGFLOW_URL'))
    full_url = f"{LANGFLOW_API_URL}{FLOW_ID}"

    # Set Headers: Use X-Api-Key (for Production Auth)
    # This is a key change to fix the 403 Forbidden error
    # We will no longer use 'Authorization: Bearer'
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "X-Api-Key": LANGFLOW_API_KEY 
    }

    # Create Payload: change to 'text'/'chat'
    # We want 'json' output to make it easy for Python (in step 6) to parse
    # (replaces the old 'chat'/'chat')
    payload = {
        "input_value": user_question,   # <-- (fix) changed from user_query to user_question
        "input_type": "chat",       
        "output_type": "chat",      # <-- (fix) changed "json" back to "chat"
        "session_id": user_id 
    }

    try:
        # Send a request to Langflow (using the new full_url)
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

        # Read the answer from JSON
        final_output = response.json()
        

        rag_answer = "Sorry, I couldn't find a clear answer." # (default value)
        
        # Updated JSON parsing logic based on RAW JSON
        try:
            # Try to get the answer from Path 1 (shortest and seen in logs)
            rag_answer = final_output['outputs'][0]['outputs'][0]['results']['message']['text']
            
        except (KeyError, IndexError, TypeError):
            try:
                # Try to get the answer from Path 2 (original path from step 4.3)
                rag_answer = final_output['outputs'][0]['outputs'][0]['results']['message']['data']['text']
                
            except (KeyError, IndexError, TypeError):
                try:
                    # Try to get the answer from Path 3 (Fallback)
                    rag_answer = final_output['outputs'][0]['outputs'][0]['outputs']['message']['message']
                
                except (KeyError, IndexError, TypeError) as e:
                    print(f"!!! JSON Parsing Error: Could not find the correct path after trying 3 patterns: {e}")
                    # rag_answer will remain the default value
            
        print(f"Langflow Answered: {rag_answer[:50]}...")

        # Send the RAG Answer back to the user
        # (keep as is)
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=rag_answer)
        )

    except requests.exceptions.HTTPError as e:
        # Add HTTP Error handling (e.g., 403/404)
        print(f"!!! Langflow HTTPError: {e.response.status_code}")
        print(f"!!! Response Body: {e.response.text[:200]}...")
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=f"Error: Langflow HTTP {e.response.status_code}. (Check API Key/Flow ID)")
        )
    except requests.exceptions.RequestException as e:
        # (Connection error)
        print(f"!!! Langflow RequestException: {e}")
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=f"Error: Could not connect to RAG (Langflow)\n({e})")
        )

    except LineBotApiError as e:
        print(f"!!! LineBotApiError (LINE_CHANNEL_ACCESS_TOKEN is wrong): {e}")
    
    except Exception as e:
        # (General error)
        print(f"!!! An unexpected error occurred in handle_message (RAG): {e}")
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=f"Error: An internal error occurred (handle_message)\n({e})")
        )