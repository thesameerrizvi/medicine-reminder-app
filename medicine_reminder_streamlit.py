"""
Medicine Reminder Streamlit App - FINAL

Features:
- Add medicines with name, dose, times, start/end dates
- Alexa-like voice using Amazon Polly (fallback gTTS)
- Background scheduler triggers reminders
- Reminder audio available in app
- Chat assistant with OpenAI GPT or fallback responses

Instructions:
- Copy this file `medicine_reminder_streamlit.py` to your GitHub repo
- Create `requirements.txt`:
  streamlit
  APScheduler
  gTTS
  boto3
  openai
  python-dotenv
- Deploy on Streamlit Cloud, set secrets for AWS Polly and OpenAI if available
- App URL will be generated automatically
"""

import streamlit as st
from datetime import datetime, date, timedelta
import json, os, threading, time as time_mod
from uuid import uuid4
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from gtts import gTTS
try: import boto3
except: boto3 = None
try: import openai
except: openai = None

DATA_FILE = "med_data.json"
AUDIO_DIR = "reminder_audio"
os.makedirs(AUDIO_DIR, exist_ok=True)

# ----------------- Utilities -----------------

def load_data():
    if not os.path.exists(DATA_FILE): return {"medicines": [], "history": []}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)

def synthesize_tts(text, filename):
    # Try Amazon Polly if keys & boto3 available
    aws_key = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
    aws_region = os.environ.get("AWS_REGION", "us-east-1")
    if aws_key and aws_secret and boto3:
        try:
            polly = boto3.client('polly', aws_access_key_id=aws_key, aws_secret_access_key=aws_secret, region_name=aws_region)
            voice = 'Joanna'  # Change to your preferred Polly voice
            resp = polly.synthesize_speech(Text=text, OutputFormat='mp3', VoiceId=voice)
            out_path = os.path.join(AUDIO_DIR, filename)
            with open(out_path, 'wb') as f:
                f.write(resp['AudioStream'].read())
            return out_path
        except Exception as e:
            st.warning(f"Polly failed, using gTTS fallback: {e}")
    # gTTS fallback
    tts = gTTS(text=text, lang='en')
    out_path = os.path.join(AUDIO_DIR, filename)
    tts.save(out_path)
    return out_path

# ----------------- Scheduler -----------------
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
        if scheduler: scheduler.remove_all_jobs()

def schedule_all_jobs():
    data = load_data()
    clear_jobs()
    start_scheduler_if_needed()
    for med in data.get("medicines", []):
        for t in med.get("times", []):
            hour, minute = map(int, t.split(':'))
            job_id = f"reminder-{med['id']}-{t}"
            scheduler.add_job(func=make_reminder_job(med), trigger=CronTrigger(hour=hour, minute=minute), id=job_id, replace_existing=True)

def make_reminder_job(med):
    def job_func():
        now = datetime.now().isoformat()
        data = load_data()
        entry = {
            'id': str(uuid4()),
            'med_id': med['id'],
            'med_name': med['name'],
            'time': now,
            'message': f"Reminder: time to take your medicine {med['name']}. Dose: {med.get('dose','')}",
        }
        text = f"Hello. This is your medicine reminder. It's time to take {med['name']}. {med.get('dose','')}. Take it now and you will feel better."
        filename = f"reminder-{entry['id']}.mp3"
        try: entry['audio'] = synthesize_tts(text, filename)
        except Exception as e: entry['audio'] = None; entry['error'] = str(e)
        data.setdefault('history', []).append(entry)
        save_data(data)
    return job_func

def scheduler_watchdog():
    while True:
        try: schedule_all_jobs()
        except: pass
        time_mod.sleep(60)
_thread = threading.Thread(target=scheduler_watchdog, daemon=True)
_thread.start()

# ----------------- Streamlit UI -----------------
st.set_page_config(page_title="Medicine Reminder + Voice", layout='wide')
st.title("Medicine Reminder App — Voice + Chat")

col1, col2 = st.columns([2,1])

with col1:
    st.header("Add / Manage Medicines")
    with st.form("add_med_form"):
        # --- Change defaults here if you want ---
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
            med = {'id': med_id,'name': name,'dose': dose,'times': times,'start_date': str(start_d),'end_date': str(end_d)}
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
    if st.button("Start Scheduler"): start_scheduler_if_needed(); schedule_all_jobs(); st.success("Scheduler started")
    if st.button("Force Run Next Reminder Now"):
        data = load_data()
        if data.get('medicines'):
            make_reminder_job(data['medicines'][0])()  # trigger one reminder
            st.success("Triggered one reminder now")
        else: st.info("No medicines exist to trigger.")

    st.markdown("---")
    st.subheader("Recent Reminders / History")
    history = sorted(data.get('history', []), key=lambda x: x.get('time',''), reverse=True)
    for entry in history[:10]:
        st.write(f"**{entry['med_name']}** — {entry['time']}")
        st.write(entry.get('message',''))
        if entry.get('audio') and os.path.exists(entry['audio']):
            with open(entry['audio'], 'rb') as f: st.audio(f.read(), format='audio/mp3')
        elif entry.get('error'): st.write("Audio generation error:", entry['error'])

st.markdown("---")
st.header("Chat Assistant")
if 'chat_history' not in st.session_state: st.session_state['chat_history'] = []
with st.form("chat_form"):
    user_msg = st.text_input("Ask something")
    send = st.form_submit_button("Send")
    if send and user_msg:
        response_text = None
        openai_key = os.environ.get('OPENAI_API_KEY')
        if openai_key and openai:
            try:
                openai.api_key = openai_key
                resp = openai.ChatCompletion.create(model="gpt-4o-mini", messages=[
                    {"role":"system","content":"You are a helpful medical reminder assistant. Keep replies concise and friendly."},
                    {"role":"user","content":user_msg}
                ], max_tokens=200)
                response_text = resp['choices'][0]['message']['content']
            except Exception as e: response_text = f"OpenAI chat failed: {e}"
        else:
            response_text = "Fallback reply: Add medicines to schedule reminders."
        st.session_state.chat_history.append((user_msg, response_text))

for q,a in st.session_state.chat_history[-10:]:
    st.markdown(f"**You:** {q}")
    st.markdown(f"**Assistant:** {a}")

st.markdown("---")
st.subheader("Deployment Notes")
st.write("Upload this file + requirements.txt to GitHub, deploy on Streamlit Cloud. Add AWS & OpenAI secrets for voice/chat features.")
