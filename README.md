# Medicine Reminder App (Streamlit)

A simple **Medicine Reminder Web App** built with **Streamlit**.  
Features:
- Add medicines with dose, start/end date, and multiple reminder times
- Voice reminders (using Amazon Polly if AWS keys provided, else Google TTS)
- Reminder history with audio playback
- Chat assistant (uses OpenAI GPT if API key provided, else fallback replies)

---

## 🚀 Live Demo
👉 [Streamlit App Link](https://share.streamlit.io/)  
*(This will appear once you deploy your app on Streamlit Cloud)*

---

## 🛠️ How It Works
1. Add a medicine name, dose, and reminder times (e.g., `09:00, 21:00`).
2. Scheduler runs in the background and generates reminders at the correct times.
3. Each reminder creates an **audio file** that you can play inside the app.
4. Chat panel lets you ask questions (AI-powered if you add `OPENAI_API_KEY`).

---

## 📂 Project Structure
