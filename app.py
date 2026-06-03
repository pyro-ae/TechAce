import eel
import pandas as pd
import os
import requests
from icalendar import Calendar
from datetime import datetime, timedelta
import pytz
import json
import tkinter as tk
from tkinter import filedialog
import re
import google.generativeai as genai
import time
import math
import webbrowser
import shutil
import pygetwindow as gw
from PIL import Image, ImageTk, ImageGrab
from moodle_ww_scraper import run_moodle_spider, run_exam_harvester
import PyPDF2  
import random
import subprocess
import sys
import requests

from paths import CONFIG_FILE, COOKIE_FILE

@eel.expose
def check_for_updates():
    # You'll need to host a simple version.txt on GitHub
    current_ver = "1.0.0"
    try:
        remote_ver = requests.get("https://raw.githubusercontent.com/YOUR_USER/YOUR_REPO/main/version.txt").text.strip()
        if remote_ver > current_ver:
            return {"available": True, "url": "https://github.com/YOUR_USER/YOUR_REPO/releases/latest/download/TechAce.exe"}
    except: pass
    return {"available": False}

@eel.expose
def apply_update(download_url):
    # 1. Download the new version to a temp file
    new_exe = "TechAce_New.exe"
    r = requests.get(download_url, stream=True)
    with open(new_exe, 'wb') as f:
        f.write(r.content)
    
    # 2. Write the "Agent" (The .bat file)
    # This script waits, swaps, and restarts
    bat_content = f"""
    @echo off
    timeout /t 3 /nobreak >nul
    del "TechAce.exe"
    ren "{new_exe}" "TechAce.exe"
    start TechAce.exe
    del "%~f0"
    """
    with open("update.bat", "w") as f:
        f.write(bat_content)
    
    # 3. Launch the agent and exit
    subprocess.Popen("update.bat", shell=True)
    os._exit(0) # Immediate force-kill of the app

CONFIG_FILE = "techace_config.json"
df_current = None 

# --- AI EXAM TEXT CACHE LOCKS ---
_CACHED_EXAM_PATH = None
_CACHED_EXAM_TEXT = ""


def load_config():
    default_config = {
        "moodle_url": "", "cheesefork_url": "", "email": "", "password": "",
        "gemini_api_key": "AIzaSyBpd2EXo3G3XrTQR_BxP2sLVJRPmAgmAMM", "transit_key": "", "wallpaper": "",
        "bg_color": "#000000", "card_bg": "#070c1a", "accent_color": "#5c85ff", 
        "font_family": "'Inter', sans-serif", "dimmer_opacity": 0.3, 
        "card_opacity": 0.85, "browser_mode": "in_app",
        "campaigns": [],
        "webwork_tasks": [],
        "completed_tasks": [],
        "course_map": {}
    }
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            try:
                user_config = json.load(f)
                default_config.update(user_config)
            except:
                pass
    return default_config

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

def clean_course_name(raw_str):
    if not raw_str: return "General"
    raw_str = str(raw_str).strip()
    
    if re.fullmatch(r'\d+', raw_str): return raw_str
        
    parts = [p.strip() for p in raw_str.split('-')]
    unwanted = ["אביב", "spring", "סמסטר", "semester", "קיץ", "חורף"]
    
    filtered = []
    for part in parts:
        if not part: continue
        if part.isdigit(): continue 
        if any(w in part.lower() for w in unwanted): continue
        filtered.append(part)
        
    if filtered:
        clean_name = " - ".join(filtered)
        clean_name = re.sub(r'\b\d{5,8}\b', '', clean_name).strip(' -')
        if clean_name: return clean_name
            
    match = re.search(r'\b(\d{5,8})\b', raw_str)
    if match: return match.group(1)
        
    return "General"

@eel.expose
def open_system_browser(url_or_path):
    if not url_or_path.startswith("http"):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        url_or_path = os.path.join(base_dir, "web", url_or_path.replace("/", os.sep))
    webbrowser.open(url_or_path)

@eel.expose
def pick_wallpaper():
    root = tk.Tk(); root.attributes("-topmost", True); root.withdraw()
    filepath = filedialog.askopenfilename(title="Select Wallpaper", filetypes=[("Image Files", "*.png *.jpg *.jpeg *.gif")])
    root.destroy()
    if filepath:
        wall_dir = os.path.join("web", "wallpapers")
        os.makedirs(wall_dir, exist_ok=True)
        dest_path = os.path.join(wall_dir, "custom_bg.png")
        shutil.copy(filepath, dest_path)
        return f"wallpapers/custom_bg.png?t={int(time.time())}" 
    return ""

@eel.expose
def ask_techace_tutor(user_message, active_exam_path=None, msg_id="default"):
    global _CACHED_EXAM_PATH, _CACHED_EXAM_TEXT
    
    config = load_config()
    api_key = config.get("gemini_api_key", "")
    if not api_key: 
        eel.updateChatStream(msg_id, "⚠️ **Connection Error:** Please paste your Gemini API Key in Settings!", True)()
        return
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-3.5-flash')
        
        context_block = ""
        if active_exam_path:
            normalized_path = active_exam_path.replace("\\", "/").lstrip("/")
            if _CACHED_EXAM_PATH == normalized_path:
                exam_text = _CACHED_EXAM_TEXT
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                pdf_full_path = os.path.join(base_dir, "web", *normalized_path.split("/"))
                exam_text = ""
                if os.path.exists(pdf_full_path):
                    try:
                        print(f"📄 Cache Miss: Extracting text from new exam PDF...")
                        with open(pdf_full_path, "rb") as f:
                            reader = PyPDF2.PdfReader(f)
                            for page in reader.pages:
                                extracted = page.extract_text()
                                if extracted:
                                    exam_text += extracted + "\n"
                        _CACHED_EXAM_PATH = normalized_path
                        _CACHED_EXAM_TEXT = exam_text
                    except Exception as e:
                        print(f"Failed to read PDF for AI: {e}")

            if exam_text:
                context_block = f"\n\n--- SECRET SYSTEM CONTEXT ---\nThe user is currently viewing this exam. Use this text to assist them:\n{exam_text[:8000]}\n-----------------------------------\n"

        anti_yap = "\n\n(System Override: Be concise. Provide step-by-step solutions immediately. CRITICAL: Use LaTeX formatting for math. Use $$...$$ for block equations and $...$ for inline math. Do NOT use parentheses or brackets for delimiters. Respond in the user's language.)"
        full_prompt = user_message + context_block + anti_yap
        
        print(f"🧠 Streaming {len(full_prompt)} chars to Gemini...")
        
        response = model.generate_content(full_prompt, stream=True)
        for chunk in response:
            if chunk.text:
                eel.updateChatStream(msg_id, chunk.text, False)()
                
        print("✅ Stream complete!")
        eel.updateChatStream(msg_id, "", True)() 
        
    except Exception as e:
        eel.updateChatStream(msg_id, f"❌ **System Failure:** {str(e)}", True)()

@eel.expose
def generate_mock_exam_json(course_name, language="en", difficulty="medium", num_questions=5):
    config = load_config()
    api_key = config.get("gemini_api_key", "")
    if not api_key: 
        return {"error": "No Gemini API Key found in Settings!"}
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-3.5-flash')
        
        lang_instruction = "Hebrew" if language == "he" else "English"
        
        prompt = f"Create a university-level {num_questions}-question multiple choice test for a course called '{course_name}'. The difficulty level should be '{difficulty}'. Write the questions and options entirely in {lang_instruction}. CRITICAL: Use strict LaTeX formatting for all math, variables, and equations (use $$ for block equations, $ for inline math). Respond ONLY with a raw, valid JSON array of objects. Example Schema: [{{\"q\": \"Question text?\", \"options\": [\"A\", \"B\", \"C\", \"D\"], \"answer\": 0}}]. Do NOT include markdown blocks like ```json."
        
        response = model.generate_content(prompt)
        raw_text = response.text
        
        # ⚡ ROBUST EXTRACTION: Use Regex to grab only the array from [ to ]
        match = re.search(r'\[.*\]', raw_text, re.DOTALL)
        if match:
            clean_text = match.group(0)
        else:
            clean_text = raw_text.replace("```json", "").replace("```", "").strip()
            
        return json.loads(clean_text)
    except Exception as e:
        return {"error": f"Failed to parse AI output. Try generating fewer questions at once! Detail: {str(e)}"}

import os # Make sure this is at the top of your app.py if it isn't already!

@eel.expose
def forge_schedule_from_syllabi(phases, days_off):
    root = tk.Tk(); root.attributes("-topmost", True); root.withdraw()
    filepaths = filedialog.askopenfilenames(title="Select Syllabi/Guidelines (PDF)", filetypes=[("PDF Files", "*.pdf")])
    root.destroy()
    
    if not filepaths:
        return {"success": False, "error": "No files selected."}
        
    config = load_config()
    api_key = config.get("gemini_api_key", "")
    if not api_key:
        return {"success": False, "error": "Gemini API Key missing!"}

    try:
        combined_text = ""
        for path in filepaths:
            with open(path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    ext = page.extract_text()
                    if ext: combined_text += ext + "\n"

        days_off_str = ", ".join(days_off) if days_off else "None"
        phases_str = json.dumps(phases, indent=2)
        
        # ⚡ CSV ADAPTATION: Find the maximum amount of blocks required across all phases
        max_blocks = max([len(p['blocks']) for p in phases]) if phases else 3
        block_keys = [f"Block {i+1}" for i in range(max_blocks)]
            
        json_schema_example = f'{{"Date": "YYYY-MM-DD", "Location": "Phase Location", '
        json_schema_example += ", ".join([f'"{k}": "[00:00 - 00:00 Name] Task"' for k in block_keys])
        json_schema_example += "}"

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-3.5-flash')

        prompt = f"""
        You are a Master Academic & Routine Planner. 
        I have provided text from my syllabuses/course guidelines below. 
        
        I have organized my timeline into different PHASES. Each phase has its own specific date range, location, and daily time blocks.
        PHASES DEFINITION:
        {phases_str}
        
        CRITICAL RULES:
        1. REST DAYS: My designated rest days are: {days_off_str}. On these days, MUST NOT schedule academic tasks. Fill EVERY block with "SYSTEM OFFLINE".
        2. Generate a continuous schedule covering every single date from the start date of the first phase to the end date of the last phase.
        3. For each date, determine which phase it belongs to, and use ONLY the time blocks defined for that specific phase.
        4. In the JSON, use generic keys: "Block 1", "Block 2", up to "Block {max_blocks}".
        5. Inside each block's text value, you MUST prefix the task with the time and block name. Example: "[05:30 - 08:30 Heavy Vanguard] Study Calculus".
        6. If a phase has fewer blocks than {max_blocks}, set the value of the extra blocks to "N/A".
        
        OUTPUT FORMAT:
        Output ONLY a valid JSON array of objects. Do not use markdown blocks like ```json.
        Schema format requirement (You MUST use these exact keys):
        [
            {json_schema_example}
        ]
        
        SYLLABUS TEXT:
        {combined_text[:30000]}
        """

        response = model.generate_content(prompt)
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        
        match = re.search(r'\[.*\]', clean_text, re.DOTALL)
        if match: clean_text = match.group(0)

        schedule_data = json.loads(clean_text)
        df = pd.DataFrame(schedule_data)
        
        save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_schedules")
        os.makedirs(save_dir, exist_ok=True)
        
        safe_start = phases[0]['start_date'].replace("-", "")
        safe_end = phases[-1]['end_date'].replace("-", "")
        clean_name = f"Timeline_{safe_start}_to_{safe_end}.csv"
        
        save_path = os.path.join(save_dir, clean_name)
        df.to_csv(save_path, index=False)
        
        if "campaigns" not in config: config["campaigns"] = []
        if save_path not in config["campaigns"]:
            config["campaigns"].append(save_path)
            save_config(config)

        return {"success": True, "filepath": save_path}

    except Exception as e:
        return {"success": False, "error": f"AI Parsing Error: {str(e)}"}

@eel.expose
def solve_from_clipboard(user_prompt, msg_id="default"):
    config = load_config()
    api_key = config.get("gemini_api_key", "")
    if not api_key: 
        eel.updateChatStream(msg_id, "⚠️ **Connection Error:** Please paste your Gemini API Key in Settings!", True)()
        return

    try:
        img = ImageGrab.grabclipboard()
        if img is None:
            eel.updateChatStream(msg_id, "⚠️ **No image detected!** Press `Win + Shift + S` to snip a specific question, then try again.", True)()
            return

        if img.mode != 'RGB':
            img = img.convert('RGB')

        img.thumbnail((1024, 1024)) 

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-3.5-flash') 

        anti_yap = "\n\n(System Override: Be concise. Provide step-by-step solutions immediately. CRITICAL: Use LaTeX formatting for math. Use $$...$$ for block equations and $...$ for inline math. Do NOT use parentheses or brackets for delimiters. Respond in the user's language.)"
        final_prompt = user_prompt + anti_yap
        
        print("📸 Uploading compressed image to Vision AI (Streaming)...")
        response = model.generate_content([final_prompt, img], stream=True)
        
        for chunk in response:
            if chunk.text:
                eel.updateChatStream(msg_id, chunk.text, False)()
                
        print("✅ Vision stream complete!")
        eel.updateChatStream(msg_id, "", True)()
        
    except Exception as e:
        eel.updateChatStream(msg_id, f"❌ **Vision System Failure:** {str(e)}", True)()

@eel.expose
def trigger_import_grades_csv():
    root = tk.Tk()
    root.attributes("-topmost", True)
    root.withdraw()
    filepath = filedialog.askopenfilename(title="Select Technion Grades CSV", filetypes=[("CSV Files", "*.csv")])
    root.destroy()
    
    if not filepath:
        return {"success": False, "error": "No file selected"}
        
    try:
        try:
            df = pd.read_csv(filepath, encoding='utf-8-sig')
        except:
            df = pd.read_csv(filepath, encoding='cp1255')
            
        grade_col = next((c for c in df.columns if 'grade' in c.lower() or 'ציון' in c), None)
        credits_col = next((c for c in df.columns if 'credit' in c.lower() or 'point' in c.lower() or 'נק' in c), None)
        course_col = next((c for c in df.columns if 'course' in c.lower() or 'מקצוע' in c), None)
        
        if not grade_col or not credits_col:
            return {"success": False, "error": "Could not automatically find 'Grade' (ציון) or 'Credits' (נקודות) columns in the CSV."}
            
        courses_data = []
        total_points = 0.0
        total_weighted = 0.0
        
        for _, row in df.iterrows():
            grade_val = row[grade_col]
            credit_val = row[credits_col]
            course_name = row[course_col] if course_col else "Unknown Course"
            
            try:
                g = float(str(grade_val).strip())
                c = float(str(credit_val).strip())
                if g > 0 and c > 0: 
                    courses_data.append({"name": str(course_name), "grade": g, "credits": c})
                    total_points += c
                    total_weighted += (g * c)
            except ValueError:
                continue
                
        gpa = (total_weighted / total_points) if total_points > 0 else 0.0
        
        return {
            "success": True,
            "gpa": round(gpa, 2),
            "total_credits": round(total_points, 1),
            "courses": courses_data
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def get_initial_data():
    config = load_config()
    campaigns = [os.path.basename(p) for p in config.get("campaigns", [])]
    return {"campaigns": campaigns, "full_paths": config.get("campaigns", [])}

@eel.expose
def trigger_import_csv():
    root = tk.Tk(); root.attributes("-topmost", True); root.withdraw()
    filepath = filedialog.askopenfilename(title="Select Schedule CSV", filetypes=[("CSV Files", "*.csv")])
    root.destroy()
    if filepath:
        config = load_config()
        if filepath not in config.get("campaigns", []):
            if "campaigns" not in config:
                config["campaigns"] = []
            config["campaigns"].append(filepath)
            save_config(config)
        return {"success": True, "filepath": filepath, "filename": os.path.basename(filepath)}
    return {"success": False}

@eel.expose
def load_csv_file(filepath):
    global df_current
    if not os.path.exists(filepath): return {"error": "File not found"}
    try:
        df_current = pd.read_csv(filepath)
        if 'Date' not in df_current.columns or 'Location' not in df_current.columns:
            return {"error": "Invalid Format"}
        return {"success": True, "dates": df_current['Date'].tolist()}
    except Exception as e:
        return {"error": str(e)}

@eel.expose
def get_dashboard_for_date(selected_date):
    global df_current
    if df_current is None or df_current.empty: return {"error": "No CSV loaded"}
    day_data = df_current[df_current['Date'] == selected_date].iloc[0]
    blocks = []
    for block_name in df_current.columns[2:]:
        target = str(day_data[block_name])
        clean_name = re.sub(r'".*?"', '', block_name).strip()
        status = "active"
        if "SYSTEM OFFLINE" in target or "LIGHT REVIEW" in target: status = "offline"
        elif "FLIGHT" in target: status = "flight"
        blocks.append({"name": clean_name, "target": target, "status": status})
    return {"location": str(day_data['Location']), "blocks": blocks}

@eel.expose
def get_saved_radar_data():
    config = load_config()
    israel_tz = pytz.timezone('Asia/Jerusalem')
    now = datetime.now(israel_tz)
    
    active_ww = config.get("webwork_tasks", [])
    def parse_ww_date(date_str):
        try:
            clean_str = date_str.replace("@", "").strip()
            if ":" in clean_str: return datetime.strptime(clean_str, "%d.%m.%Y %H:%M")
            else: return datetime.strptime(clean_str, "%d.%m.%Y")
        except: return datetime.max
    active_ww.sort(key=lambda x: parse_ww_date(x.get("date", "")))

    for w in active_ww:
        w['course'] = clean_course_name(w.get("course", ""))
        dt = parse_ww_date(w.get("date", ""))
        if dt != datetime.max:
            dt = israel_tz.localize(dt) if dt.tzinfo is None else dt.astimezone(israel_tz)
            w['is_urgent'] = (dt - now).total_seconds() <= 259200
        else:
            w['is_urgent'] = False

    completed_list = config.get("completed_tasks", [])
    m_url = config.get("moodle_url", "")
    c_url = config.get("cheesefork_url", "").replace("webcal://", "https://")
    urls = [u for u in [m_url, c_url] if u and "http" in u]

    m_temp, e_temp, archived = [], [], []
    feed_error = False 

    if urls:
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            noise = ['זום', 'הרצא', 'תרגול', 'שיעור', 'zoom', 'lecture', 'tutorial', 'מפגש', 'קבלה']
            cmap = config.get("course_map", {})
            url_map = config.get("course_url_map", {}) 
            
            for url in urls:
                try:
                    res = requests.get(url, headers=headers, timeout=10)
                    res.raise_for_status()
                    cal = Calendar.from_ical(res.content)
                    for component in cal.walk():
                        if component.name == "VEVENT":
                            summary = str(component.get('summary'))
                            if any(n in summary.lower() for n in noise): continue
                            
                            is_exam = any(ex in summary.lower() for ex in ['מבחן', 'מועד', 'exam', 'בחינה'])
                            
                            extracted_num = None
                            categories = component.get('categories')
                            cat_str = categories.to_ical().decode('utf-8') if categories and hasattr(categories, 'to_ical') else ""
                            
                            match_cat = re.search(r'(\d{5,8})', cat_str)
                            match_sum = re.search(r'(\d{5,8})', summary)
                            
                            if match_cat: extracted_num = match_cat.group(1)
                            elif match_sum: extracted_num = match_sum.group(1)
                            
                            c_tag = cmap.get(extracted_num, extracted_num) if extracted_num else "General"
                            course_url = url_map.get(extracted_num, "https://moodle25.technion.ac.il/my/") if extracted_num else "https://moodle25.technion.ac.il/my/"

                            if is_exam:
                                parts = re.split(r'\s*[-–—]\s*', summary, maxsplit=1)
                                if len(parts) == 2:
                                    if "מועד" in parts[0] or "exam" in parts[0].lower() or "בחינה" in parts[0].lower():
                                        task_id = parts[0].strip()
                                        if c_tag == "General": c_tag = parts[1].strip()
                                    elif "מועד" in parts[1] or "exam" in parts[1].lower() or "בחינה" in parts[1].lower():
                                        task_id = parts[1].strip()
                                        if c_tag == "General": c_tag = parts[0].strip()
                                    else:
                                        task_id = summary
                                else:
                                    task_id = summary
                            else:
                                task_id = re.sub(r'\[\d{5,8}\]\s*-?\s*', '', summary)
                                task_id = task_id.replace("תאריך הגשה ", "").replace("יש להגיש את ", "").replace("'", "")
                                task_id = re.sub(r'-\s*להגשה.*', '', task_id).strip()

                            c_tag = clean_course_name(c_tag)
                                
                            dtstart = component.get('dtstart').dt
                            if type(dtstart) is not datetime: dtstart = datetime.combine(dtstart, datetime.min.time())
                            if dtstart.tzinfo is None: dtstart = israel_tz.localize(dtstart)
                            else: dtstart = dtstart.astimezone(israel_tz)
                            
                            if task_id in completed_list: 
                                archived.append(task_id)
                                continue
                            
                            event_url_obj = component.get('url')
                            event_url = str(event_url_obj) if event_url_obj else course_url
                            is_urgent = (dtstart - now).total_seconds() <= 259200
                            
                            if is_exam and now <= dtstart <= now + timedelta(days=365): 
                                e_temp.append((dtstart, {'task': task_id, 'course': c_tag, 'date': dtstart.strftime('%b %d'), 'is_urgent': is_urgent, 'link': event_url, 'course_url': course_url}))
                            elif not is_exam and now <= dtstart <= now + timedelta(days=14): 
                                m_temp.append((dtstart, {'task': task_id, 'course': c_tag, 'date': dtstart.strftime('%b %d, %H:%M'), 'is_urgent': is_urgent, 'link': event_url, 'course_url': course_url}))
                except Exception: 
                    feed_error = True
        except Exception: 
            feed_error = True

    m_temp.sort(key=lambda x: x[0])
    e_temp.sort(key=lambda x: x[0])
    return {
        "moodle": [x[1] for x in m_temp], "exams": [x[1] for x in e_temp], 
        "webwork": active_ww, "archived": archived, "error": feed_error
    }


@eel.expose
def sync_threat_radar():
    config = load_config()
    cmap = config.get("course_map", {})
    url_map = config.get("course_url_map", {})
    formatted_tasks = []
    
    if config.get("email") and config.get("password"):
        try:
            print("🕸️ Firing Moodle Spider Engine...")
            spider_data = run_moodle_spider(force_refresh=False)
            
            if spider_data is not None:
                new_tasks = spider_data.get("tasks", [])
                course_meta = spider_data.get("course_meta", {})
                
                for cid, meta in course_meta.items():
                    clean_n = clean_course_name(meta["name"])
                    if clean_n and clean_n != cid:
                        cmap[cid] = clean_n
                    url_map[cid] = meta["url"]
                
                for t in new_tasks:
                    raw_course = str(t.get("course", "") or t.get("course_name", "General"))
                    clean_name = clean_course_name(raw_course)
                    
                    raw_link = str(t.get("link", ""))
                    if raw_link.startswith("/"):
                        if "webwork" in raw_link.lower() or "webwork" in raw_course.lower():
                            raw_link = "https://webwork.technion.ac.il" + raw_link
                        else:
                            raw_link = "https://moodle25.technion.ac.il" + raw_link
                    
                    formatted_tasks.append({
                        "course": clean_name,
                        "name": str(t.get("name", "Unknown Task")),
                        "date": str(t.get("due_date", "Unknown")),
                        "link": raw_link,
                        "course_url": str(t.get("course_url", "")) 
                    })
                
                config["course_map"] = cmap 
                config["course_url_map"] = url_map
                config["webwork_tasks"] = formatted_tasks
                save_config(config)
                
        except Exception as e:
            print(f"Spider Error: {e}")
    else:
        print("⚠️ Spider Aborted: No Email/Password found in config!")
            
    return get_saved_radar_data()

@eel.expose
def harvest_moodle_exams():
    try:
        print("🕸️ Firing Dedicated Exam Harvester Engine...")
        download_count = run_exam_harvester()
        return download_count
    except Exception as e:
        print(f"Harvester Error: {e}")
        return -1

@eel.expose
def archive_tasks(task_names):
    config = load_config()
    for task in task_names:
        if task not in config.get("completed_tasks", []): 
            if "completed_tasks" not in config:
                config["completed_tasks"] = []
            config["completed_tasks"].append(task)
    save_config(config)

@eel.expose
def remove_webwork(task_names_to_keep):
    config = load_config()
    config["webwork_tasks"] = [w for w in config.get("webwork_tasks", []) if w['name'] in task_names_to_keep]
    save_config(config)

@eel.expose
def get_settings():
    config = load_config()
    return {
        "moodle_url": config.get("moodle_url", ""), "cheesefork_url": config.get("cheesefork_url", ""),
        "email": config.get("email", ""), "password": config.get("password", ""),
        "gemini_api_key": config.get("gemini_api_key", ""), "transit_key": config.get("transit_key", ""), 
        "wallpaper": config.get("wallpaper", ""),
        "bg_color": config.get("bg_color", "#000000"), "card_bg": config.get("card_bg", "#070c1a"),
        "accent_color": config.get("accent_color", "#5c85ff"), "font_family": config.get("font_family", "'Inter', sans-serif"),
        "dimmer_opacity": config.get("dimmer_opacity", 0.3), "card_opacity": config.get("card_opacity", 0.85),
        "browser_mode": config.get("browser_mode", "in_app")
    }

@eel.expose
def save_settings(config_dict):
    try:
        existing_config = load_config() 
        existing_config.update(config_dict) 
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(existing_config, f, indent=4)
        return True
    except Exception as e:
        print(f"❌ Error saving settings: {e}")
        return False

@eel.expose
def build_vault_tree(dir_path):
    tree = []
    try:
        for item in sorted(os.listdir(dir_path)):
            item_path = os.path.join(dir_path, item)
            if os.path.isdir(item_path):
                children = build_vault_tree(item_path)
                tree.append({"name": item, "type": "folder", "children": children})
            else:
                ext = item.rsplit('.', 1)[-1].lower() if '.' in item else ''
                clean = item.rsplit('.', 1)[0] if '.' in item else item
                base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
                web_path = os.path.relpath(item_path, base_dir).replace("\\", "/")
                tree.append({"name": clean, "type": "file", "ext": ext, "path": web_path, "filename": item})
    except: pass
    return tree

@eel.expose
def get_local_exams():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    vault_dir = os.path.join(base_dir, "web", "vault")
    if not os.path.exists(vault_dir): 
        os.makedirs(vault_dir)
        return []
    return build_vault_tree(vault_dir)

print("Starting TechAce V7 P2P System...")

root = tk.Tk()
root.attributes("-topmost", True)
root.attributes("-fullscreen", True)
root.config(bg='#05030a')
sw = root.winfo_screenwidth()
sh = root.winfo_screenheight()
lbl = tk.Label(root, bg='#05030a', borderwidth=0, highlightthickness=0)
lbl.place(relx=0.5, rely=0.5, anchor=tk.CENTER) 

@eel.expose
def search_campus_logistics(query):
    config = load_config()
    api_key = config.get("gemini_api_key", "")
    
    if not api_key:
        return {"error": "Please add your Gemini API Key in Settings to use the Campus Explorer!"}
        
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-3.5-flash')
        
        system_prompt = (
            f"You are the Technion Campus Logistics Assistant. The user is asking: '{query}'. "
            "Provide a highly detailed, helpful response. If they are asking about a food place, "
            "include its typical operating status, current or common menu items, contact details, "
            "and helpful tips. If they are asking about transit, act like a mini-Moovit and list "
            "the primary bus lines (like 11, 17, 19, 31, 76), their destinations from campus, and "
            "which stop to use (Main Gate, ASAT Student Union, or Mizrah Dorms). "
            "Format your entire response in clean, beautiful Markdown with bullet points."
        )
        
        response = model.generate_content(system_prompt)
        return {"markdown": response.text}
    except Exception as e:
        return {"error": f"AI Search failed: {str(e)}"}

eel.init('web')

# ⚡ Give Chrome an EXACT, absolute path so it never panics and crashes
chrome_data_path = os.path.abspath("techace_chrome_data")

chrome_flags = [
    '--ignore-gpu-blocklist', 
    '--enable-gpu-rasterization', 
    '--background-color=#05030a', 
    '--autoplay-policy=no-user-gesture-required',
    '--start-fullscreen',
    f'--user-data-dir={chrome_data_path}'  # ⚡ Uses the absolute path
]

# ⚡ SET PORT TO 8000: Chrome will now remember your permissions permanently!
eel.start('index.html', port=8000, cmdline_args=chrome_flags, block=False)

try:
    img_path = os.path.join("web", "penguin.png")
    img_orig = Image.open(img_path).convert("RGBA")
    
    ratio = 300 / img_orig.width
    base_w, base_h = int(img_orig.width * ratio), int(img_orig.height * ratio)
    img_base = img_orig.resize((base_w, base_h), Image.Resampling.LANCZOS)
    
    for i in range(90):
        scale = 1.0 + (0.05 * math.sin((math.pi * i) / 30)) 
        new_w, new_h = int(base_w * scale), int(base_h * scale)
        
        img_resized = img_base.resize((new_w, new_h), Image.Resampling.BILINEAR)
        tk_img = ImageTk.PhotoImage(img_resized)
        lbl.config(image=tk_img)
        lbl.image = tk_img 
        root.update()
        eel.sleep(0.016)

    target_h = 45 
    target_w = int(img_orig.width * (45 / img_orig.height))
    frames = 12 
    
    for i in range(frames):
        progress = i / float(frames)
        ease = progress * progress * progress 
        
        current_w = int(base_w - (base_w - target_w) * ease)
        current_h = int(base_h - (base_h - target_h) * ease)
        current_rely = 0.5 - (0.45 * ease) 
        
        img_resized = img_base.resize((current_w, current_h), Image.Resampling.BILINEAR)
        tk_img = ImageTk.PhotoImage(img_resized)
        lbl.config(image=tk_img)
        lbl.image = tk_img
        lbl.place(relx=0.5, rely=current_rely, anchor=tk.CENTER)
        root.update()
        eel.sleep(0.01)

    for i in range(10, -1, -2):
        root.attributes("-alpha", i / 10.0)
        root.update()
        eel.sleep(0.01)

except Exception as e:
    print(f"Splash error: {e}")

root.destroy()

while True:
    eel.sleep(1.0)