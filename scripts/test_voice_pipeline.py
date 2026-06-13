import requests
import json
import time
import sys

BASE_URL = "http://localhost:8000"

def print_banner(title):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def test_realtime_session_flow():
    print_banner("1. Testing Real-time Voice Session Flow")
    
    # --- A. Start Session ---
    start_url = f"{BASE_URL}/api/voice/session/start"
    start_payload = {"mode": "realtime"}
    print(f"\n[A] Starting Voice Session via POST {start_url}...")
    
    # Equivalent curls
    escaped_start = json.dumps(start_payload).replace('"', '\\"')
    print("\n  Equivalent Command Line:")
    print(f"    bash/cmd: curl -X POST -H \"Content-Type: application/json\" -d \"{escaped_start}\" {start_url}")
    print(f"    PowerShell: Invoke-RestMethod -Uri \"{start_url}\" -Method Post -ContentType \"application/json\" -Body \"{escaped_start}\"")
    
    response = requests.post(start_url, json=start_payload)
    print(f"\n  Response Code: {response.status_code}")
    if response.status_code != 200:
        print(f"  Error: {response.text}")
        return None
        
    start_data = response.json()
    session_id = start_data.get("session_id")
    print(f"  Session ID: {session_id}")
    print(f"  Greeting: {start_data.get('greeting_text')}")
    print(f"  Greeting Audio B64 Present: {start_data.get('greeting_audio_b64') is not None}")
    
    # --- B. Send Reply Turn 1 (Paris Request) ---
    reply_url = f"{BASE_URL}/api/voice/session/reply"
    reply_payload_1 = {
        "session_id": session_id,
        "transcript": "Plan a 5-day trip to Paris for a couple with a $3000 budget, love museums and romantic dining, hate crowds",
        "mode": "realtime"
    }
    print_banner("2. Sending Turn 1: Paris Trip Request")
    print(f"Posting to {reply_url}...")
    
    # Equivalent curls
    escaped_reply_1 = json.dumps(reply_payload_1).replace('"', '\\"')
    print("\n  Equivalent Command Line:")
    print(f"    bash/cmd: curl -X POST -H \"Content-Type: application/json\" -d \"{escaped_reply_1}\" {reply_url}")
    
    response = requests.post(reply_url, json=reply_payload_1)
    print(f"\n  Response Code: {response.status_code}")
    if response.status_code != 200:
        print(f"  Error: {response.text}")
        return None
        
    reply_data_1 = response.json()
    print(f"  Status: {reply_data_1.get('status')}")
    print(f"  Question: {reply_data_1.get('question')}")
    print(f"  Question Audio B64 Present: {reply_data_1.get('question_audio_b64') is not None}")
    
    # --- C. Send Reply Turn 2 (Start Date) ---
    reply_payload_2 = {
        "session_id": session_id,
        "transcript": "We want to travel starting June 15, 2026.",
        "mode": "realtime"
    }
    print_banner("3. Sending Turn 2: Providing Start Date")
    print(f"Posting to {reply_url}...")
    
    # Equivalent curls
    escaped_reply_2 = json.dumps(reply_payload_2).replace('"', '\\"')
    print("\n  Equivalent Command Line:")
    print(f"    bash/cmd: curl -X POST -H \"Content-Type: application/json\" -d \"{escaped_reply_2}\" {reply_url}")
    
    response = requests.post(reply_url, json=reply_payload_2)
    print(f"\n  Response Code: {response.status_code}")
    if response.status_code != 200:
        print(f"  Error: {response.text}")
        return None
        
    reply_data_2 = response.json()
    print(f"  Status: {reply_data_2.get('status')}")
    if reply_data_2.get('status') != "ready":
        print("  Error: Session not promoted to 'ready'!")
        return None
        
    print("  [SUCCESS] Session is READY. Proceeding to plan stream...")
    
    # --- D. Stream Planning Itinerary (SSE) ---
    plan_url = f"{BASE_URL}/api/voice/session/{session_id}/plan"
    print_banner("4. Streaming Planning Events (SSE)")
    print(f"Connecting to GET {plan_url}...")
    
    print("\n  Equivalent Command Line:")
    print(f"    bash/cmd: curl -N {plan_url}")
    print(f"    PowerShell: Invoke-WebRequest -Uri \"{plan_url}\" -OutVariable resp; $resp.Content")
    
    t0 = time.time()
    try:
        response = requests.get(plan_url, stream=True, timeout=600)
        print(f"\n  Response Status: {response.status_code}")
        
        current_event = None
        for line in response.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8").strip()
            if line_str.startswith("event:"):
                current_event = line_str.split(":", 1)[1].strip()
            elif line_str.startswith("data:"):
                data_str = line_str.split(":", 1)[1].strip()
                print(f"\n  >>> SSE Event: [{current_event}]")
                try:
                    payload = json.loads(data_str)
                    if current_event in ("agent_start", "agent_done", "error"):
                        print(json.dumps(payload, indent=4))
                    elif current_event == "plan_complete":
                        print("  [plan_complete] Trip Itinerary Generated Successfully!")
                        print(f"  Trip ID: {payload.get('trip_id')}")
                        print(f"  Pipeline Status: {payload.get('pipeline_status')}")
                        print(f"  Validation Status: {payload.get('validation_status')}")
                        print(f"  Itinerary Days Count: {len(payload.get('itinerary', {}).get('days', []))}")
                        print(f"  Estimated Cost: {payload.get('budget_breakdown', {}).get('total_estimated_cost')} {payload.get('budget_breakdown', {}).get('currency')}")
                        print(f"  Errors: {payload.get('errors')}")
                        print("\n  === Full plan_complete JSON Payload ===")
                        print(json.dumps(payload, indent=2))
                    elif current_event == "voice_summary":
                        print("  [voice_summary] Voice TTS Summary Generated!")
                        print(f"  Text: {payload.get('text')}")
                        print(f"  Audio Format: {payload.get('audio_format')}")
                        print(f"  Audio Base64 Present: {payload.get('audio_b64') is not None}")
                except Exception as e:
                    print(f"  Raw data: {data_str} (error parsing: {e})")
        elapsed = time.time() - t0
        print(f"\n  SSE stream closed in {elapsed:.2f} seconds.")
    except Exception as exc:
        print(f"\n  SSE stream failed: {exc}")

def test_confirm_flow():
    print_banner("5. Testing Edit-Before-Submit Flow (/api/voice/confirm)")
    confirm_url = f"{BASE_URL}/api/voice/confirm"
    confirm_payload = {
        "transcript": "Plan a 5-day trip to Paris for a couple with a $3000 budget, love museums and romantic dining, hate crowds. Start date is June 15, 2026.",
        "session_id": "paris-confirm-test-session",
        "user_id": "paris-confirm-test-user"
    }
    
    print(f"Posting to {confirm_url}...")
    escaped_confirm = json.dumps(confirm_payload).replace('"', '\\"')
    print("\n  Equivalent Command Line:")
    print(f"    bash/cmd: curl -X POST -H \"Content-Type: application/json\" -d \"{escaped_confirm}\" {confirm_url}")
    
    t0 = time.time()
    try:
        response = requests.post(confirm_url, json=confirm_payload, timeout=600)
        elapsed = time.time() - t0
        print(f"\n  Response received in {elapsed:.2f} seconds.")
        print(f"  Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("\n  === Confirm Response Summary ===")
            print(f"  Trip ID: {data.get('trip_id')}")
            print(f"  Pipeline Status: {data.get('pipeline_status')}")
            print(f"  Validation Status: {data.get('validation_status')}")
            print(f"  Has Itinerary: {data.get('itinerary') is not None}")
            print(f"  Has Budget Breakdown: {data.get('budget_breakdown') is not None}")
            print(f"  Voice Summary Text: {data.get('voice_summary')}")
            print(f"  Voice Summary Audio Format: {data.get('voice_summary_audio_format')}")
            print(f"  Voice Summary Audio B64 Present: {data.get('voice_summary_audio_b64') is not None}")
            print(f"  Errors: {data.get('errors')}")
            print("\n  === Full Confirm Response JSON ===")
            print(json.dumps(data, indent=2))
        else:
            print(f"  Error Response Body:\n{response.text}")
    except Exception as exc:
        print(f"  Confirm request failed: {exc}")

if __name__ == "__main__":
    test_realtime_session_flow()
    test_confirm_flow()
