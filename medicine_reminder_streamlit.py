"""
Medicine Reminder Streamlit App
File: medicine_reminder_streamlit.py

Features:
- Add medicines with name, dose, times (multiple), start/end dates
- Stores schedule in a local JSON file (`med_data.json`)
- Background scheduler (APScheduler) triggers reminders
- TTS announcement produced using Amazon Polly (if AWS keys provided) OR gTTS fallback
- Plays reminder audio to the user via `st.audio` (generated mp3)
- Simple chat panel: uses OpenAI (if OPENAI_API_KEY provided) or fallback rule-based replies

How to use:
1. Put this file in a git repo.
2. Create `requirements.txt` with packages listed below (or let Streamlit install them).
3. (Optional) For best "Alexa-like" voice: provide AWS credentials as Streamlit secrets or environment variables:
   - AWS_ACCESS_KEY_ID
   - AWS_SECRET_ACCESS_KEY
   - AWS_REGION (e.g. us-east-1)
   When these are present the app will try Amazon Polly (neural voices).
4. (Optional) For AI chat: provide OPENAI_API_KEY as env var/secret.
5. Deploy on Streamlit Cloud (app.streamlit.io) or any host that supports Streamlit.

Notes / Limitations:
- Exact Alexa voice is proprietary and cannot be redistributed. The app supports Polly neural voices (close professional voices) if you provide AWS keys, otherwise gTTS produces a natural TTS but not Alexa voice.
- Server-side audio is generated and served to the client; automatic instantaneous browser autoplay depends on browser autoplay policies. The app will render audio widgets for you to press play if autoplay is blocked.

Requirements (put in requirements.txt):
streamlit
APScheduler
gTTS
boto3
openai
python-dotenv

"""

import streamlit as st
from datetime import datetime, date, time, timedelta
import json
import os
from uuid import uuid4
from typing import List, Dict, Any
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from gtts import gTTS
import tempfile
import threading
import time as time_mod

# Optional imports (only used if keys provided)
try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
    POLLY_AVAILABLE = True
except Exception:
    POLLY_AVAILABLE = False

# Optional OpenAI for chat
try:
    import openai
    OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False

DATA_FILE = "med_data.json"
AUDIO_DIR = "reminder_audio"
os.makedirs(AUDIO_DIR, exist_ok=True)

# --------------------- Utilities ---------------------
def load_data() -> Dict[str, Any]:
    if not os.path.exists(DATA_FILE):
        return {"medicines": [], "history": []}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data: Dict[str, Any]):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)

def synthesize_tts(text: str, filename: str) -> str:
    """
    Create an mp3 file with TTS. Prefer Amazon Polly (if creds & boto3 available and configured), else fallback to gTTS.
    Returns path to mp3 file.
    """
    aws_key = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
    aws_region = os.environ.get("AWS_REGION", "us-east-1")

    # Try Polly if possible and credentials provided
    if aws_key and aws_secret and POLLY_AVAILABLE:
        try:
            polly = boto3.client('polly',
                                 aws_access_key_id=aws_key,
                                 aws_secret_access_key=aws_secret,
                                 region_name=aws_region)
            # Choose a neural voice if available
            voice = 'Joanna'  # good neutral voice; change if you prefer
            resp = polly.synthesize_speech(Text=text, OutputFormat='mp3', VoiceId=voice)
            out_path = os.path.join(AUDIO_DIR, filename)
            with open(out_path, 'wb') as f:
                f.write(resp['AudioStream'].read())
            return out_path
        except (BotoCoreError, ClientError) as e:
            st.warning(f"Polly failed, falling back to gTTS: {e}")

    # Fallback to gTTS
    tts = gTTS(text=text, lang='en')
    out_path = os.path.join(AUDIO_DIR, filename)
    tts.save(out_path)
    return out_path

# --------------------- Scheduler ---------------------
scheduler = None
scheduler_lock = threading.Lock()

def start_scheduler_if_needed():
    global scheduler
    with scheduler_lock:
        if scheduler is None:
            scheduler = BackgroundScheduler()
            scheduler.start()

def clear_jobs():
    global scheduler
    with scheduler_lock:
        if scheduler:
            scheduler.remove_all_jobs()

def schedule_all_jobs():
    data = load_data()
    clear_jobs()
    start_scheduler_if_needed()
    for med in data.get("medicines", []):
        for t in med.get("times", []):
            # t format: HH:MM
            hour, minute = map(int, t.split(':'))
            # create a cron trigger daily between start and end date
            start_date = med.get('start_date')
            end_date = med.get('end_date')
            job_id = f"reminder-{med['id']}-{t}"

            # We'll schedule a daily job at hour:minute
            trigger = CronTrigger(hour=hour, minute=minute)
            # Job function
            scheduler.add_job(func=make_reminder_job(med), trigger=trigger, id=job_id, replace_existing=True)

def make_reminder_job(med):
    def job_func():
        # Called by BackgroundScheduler in server process
        now = datetime.now().isoformat()
        data = load_data()
        entry = {
            'id': str(uuid4()),
            'med_id': med['id'],
            'med_name': med['name'],
            'time': now,
            'message': f"Reminder: time to take your medicine {med['name']}. Dose: {med.get('dose','')}",
        }
        # create audio
        text = f"Hello. This is your medicine reminder. It's time to take {med['name']}. {med.get('dose','')}. Take it now and you will feel better."
        filename = f"reminder-{entry['id']}.mp3"
        try:
            mp3_path = synthesize_tts(text, filename)
            entry['audio'] = mp3_path
        except Exception as e:
            entry['audio'] = None
            entry['error'] = str(e)
        data.setdefault('history', []).append(entry)
        save_data(data)
    return job_func

# A tiny thread that reloads jobs occasionally so Streamlit UI changes pick up
def scheduler_watchdog():
    while True:
        try:
            schedule_all_jobs()
        except Exception:
            pass
        time_mod.sleep(60)

# Start watchdog in background
_watchdog_thread = threading.Thread(target=scheduler_watchdog, daemon=True)
_watchdog_thread.start()

# --------------------- Streamlit UI ---------------------
st.set_page_config(page_title="Medicine Reminder + Voice", layout='wide')
st.title("Medicine Reminder App — Voice + Chat")

col1, col2 = st.columns([2,1])

with col1:
    st.header("Add / Manage Medicines")
    with st.form("add_med_form"):
        name = st.text_input("Medicine name", value="Paracetamol")
        dose = st.text_input("Dose / Instructions", value="500 mg")
        times_input = st.text_input("Times (comma-separated, HH:MM)", value="09:00,21:00")
        start_d = st.date_input("Start date", value=date.today())
        end_d = st.date_input("End date", value=date.today() + timedelta(days=30))
        submitted = st.form_submit_button("Add / Update Medicine")
        if submitted:
            data = load_data()
            med_id = str(uuid4())
            times = [t.strip() for t in times_input.split(',') if t.strip()]
            med = {
                'id': med_id,
                'name': name,
                'dose': dose,
                'times': times,
                'start_date': str(start_d),
                'end_date': str(end_d)
            }
            data.setdefault('medicines', []).append(med)
            save_data(data)
            st.success(f"Saved {name}")
            schedule_all_jobs()

    st.markdown("---")
    st.subheader("Existing Medicines")
    data = load_data()
    for med in data.get('medicines', []):
        with st.expander(f"{med['name']} — {', '.join(med['times'])}"):
            st.write(f"Dose: {med.get('dose')}")
            st.write(f"Start: {med.get('start_date')} — End: {med.get('end_date')}")
            if st.button(f"Delete {med['name']}", key=f"del-{med['id']}"):
                data['medicines'] = [m for m in data['medicines'] if m['id'] != med['id']]
                save_data(data)
                st.experimental_rerun()

with col2:
    st.header("Scheduler Controls")
    if st.button("Start Scheduler"):
        start_scheduler_if_needed()
        schedule_all_jobs()
        st.success("Scheduler started — reminders will be generated at scheduled times (server time).")
    if st.button("Force Run Next Reminder Now"):
        # Simple demo run: run first med job immediately
        data = load_data()
        if data.get('medicines'):
            med = data['medicines'][0]
            job = make_reminder_job(med)
            job()
            st.success("Triggered one reminder now — check History section.")
        else:
            st.info("No medicines exist to trigger.")

    st.markdown("---")
    st.subheader("Recent Reminders / History")
    data = load_data()
    history = sorted(data.get('history', []), key=lambda x: x.get('time',''), reverse=True)
    for entry in history[:10]:
        st.write(f"**{entry['med_name']}** — {entry['time']}")
        st.write(entry.get('message',''))
        if entry.get('audio') and os.path.exists(entry['audio']):
            with open(entry['audio'], 'rb') as f:
                audio_bytes = f.read()
            st.audio(audio_bytes, format='audio/mp3')
        else:
            if entry.get('error'):
                st.write("Audio generation error:", entry['error'])

# --------------------- Chat Panel ---------------------
st.markdown("---")
st.header("Chat Assistant")

if 'chat_history' not in st.session_state:
    st.session_state['chat_history'] = []

with st.form("chat_form"):
    user_msg = st.text_input("Ask something (medicine-related or general)")
    send = st.form_submit_button("Send")
    if send and user_msg:
        response_text = None
        # If OpenAI key provided, use GPT for chat
        openai_key = os.environ.get('OPENAI_API_KEY')
        if openai_key and OPENAI_AVAILABLE:
            try:
                openai.api_key = openai_key
                resp = openai.ChatCompletion.create(model="gpt-4o-mini", messages=[
                    {"role":"system","content":"You are a helpful medical reminder assistant. Keep replies concise and friendly."},
                    {"role":"user","content":user_msg}
                ], max_tokens=200)
                response_text = resp['choices'][0]['message']['content']
            except Exception as e:
                response_text = f"OpenAI chat failed: {e}"
        else:
            # fallback simple reply
            if 'remind' in user_msg.lower():
                response_text = "I can help remind you — go to the Add Medicine panel to schedule reminders."
            else:
                response_text = "Sorry, I can't use the advanced chat (OpenAI key missing). I'm a simple assistant: add medicines or trigger reminders."

        st.session_state.chat_history.append((user_msg, response_text))

for q,a in st.session_state.chat_history[-10:]:
    st.markdown(f"**You:** {q}")
    st.markdown(f"**Assistant:** {a}")

# --------------------- Footer & Deployment Hints ---------------------
st.markdown("---")
st.subheader("Deployment / Next steps")
st.write("1) Add this file to a GitHub repository.\n2) Create requirements.txt with: streamlit, APScheduler, gTTS, boto3, openai, python-dotenv.\n3) On Streamlit Cloud, point to the repo and set Secrets: AWS keys (optional) and OPENAI_API_KEY (optional).\n4) Start the app.\n
Notes: For actual production-grade medication apps, consult medical/regulatory guidance. This app is a toy/demo to learn engineering techniques.")


