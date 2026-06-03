from playwright.sync_api import sync_playwright
import json
import os
import tkinter as tk
import time
import random
import eel
import re  # ⚡ Added Regex import for the Course Extractor

from paths import CONFIG_FILE, COOKIE_FILE, CHROME_DATA_DIR # Make sure to import it!


def run_moodle_spider(force_refresh=False):
    if os.path.exists(CONFIG_FILE):
        # ⚡ THE FIX: Explicitly forcing UTF-8 so Hebrew doesn't crash Windows
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            email = config.get("email", "")
            password = config.get("password", "")
    else: return None
    if not email or not password: return None

    if force_refresh and os.path.exists(COOKIE_FILE): os.remove(COOKIE_FILE)

    with sync_playwright() as p:
        print("\n🚀 Launching Moodle Spider Engine...")
        std_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        context = p.chromium.launch_persistent_context(
        user_data_dir=CHROME_DATA_DIR,
        headless=True,
        user_agent=std_user_agent
    )
        if os.path.exists(COOKIE_FILE):
            with open(COOKIE_FILE, 'r', encoding="utf-8") as f: context.add_cookies(json.load(f))
        page = context.new_page()
        all_tasks = []

        print("📡 Connecting to Moodle Dashboard...")
        try: page.goto("https://moodle25.technion.ac.il/my/", wait_until="domcontentloaded", timeout=20000)
        except: pass 

        if "/my/" not in page.url:
            print("🚪 Session expired. Launching 2FA Microsoft Window...")
            browser.close()
            root = tk.Tk(); root.withdraw()
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight(); root.destroy()
            pw, ph = 600, 800
            auth_browser = p.chromium.launch(headless=False, args=[f'--window-size={pw},{ph}', f'--window-position={int((sw-pw)/2)},{int((sh-ph)/2)}'])
            auth_context = auth_browser.new_context(user_agent=std_user_agent)
            auth_page = auth_context.new_page()
            
            try:
                auth_page.goto("https://moodle25.technion.ac.il/login/index.php")
                if not auth_page.locator('input[type="email"]').is_visible(timeout=3000):
                    sso = auth_page.locator("a:has-text('Technion account'), a:has-text('חשבון הטכניון'), a:has-text('Sign in'), a[href*='openid']").first
                    if sso.is_visible(timeout=3000): sso.click(); auth_page.wait_for_selector('input[type="email"]', timeout=10000)

                if auth_page.locator('input[type="email"]').is_visible(timeout=5000):
                    auth_page.fill('input[type="email"]', email)
                    auth_page.click('input[type="submit"]')
                    try:
                        auth_page.wait_for_selector('input[type="password"]', timeout=4000)
                        auth_page.fill('input[type="password"]', password) 
                        auth_page.click('input[type="submit"]')
                    except: pass

                print("⏳ Waiting for 2FA Phone Approval...")
                timeout_counter = 0
                while timeout_counter < 120:
                    if "moodle25.technion.ac.il" in auth_page.url and "login" not in auth_page.url: break
                    auth_page.wait_for_timeout(1000); timeout_counter += 1
                
                if timeout_counter >= 120: raise Exception("Timeout")
                auth_page.wait_for_timeout(2000)
                with open(COOKIE_FILE, 'w', encoding="utf-8") as f: json.dump(auth_context.cookies(), f)
            except Exception as e:
                try: auth_browser.close()
                except: pass
                return None
                
            auth_browser.close(); time.sleep(2) 

            browser = p.chromium.launch(headless=True) 
            context = browser.new_context(user_agent=std_user_agent)
            with open(COOKIE_FILE, 'r', encoding="utf-8") as f: context.add_cookies(json.load(f))
            page = context.new_page()
            try: page.goto("https://moodle25.technion.ac.il/my/", wait_until="domcontentloaded", timeout=20000)
            except: pass

        try:
            c_tab = page.locator("a:has-text('הקורסים שלי')").first
            if c_tab.is_visible(timeout=3000): c_tab.click()
        except: pass
        try: page.wait_for_selector("a[href*='course/view.php?id=']", timeout=15000); page.wait_for_timeout(2000) 
        except: pass

        course_links = page.locator("a[href*='course/view.php?id=']").all()
        course_urls = list(set([link.get_attribute("href") for link in course_links if link.get_attribute("href")]))
        
        global_course_map = {} 
        
        print(f"🕸️ Sweeping {len(course_urls)} courses for assignments...")
        for url in course_urls:
            time.sleep(random.uniform(0.5, 1.2))
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                try: course_name = page.locator("h1").first.inner_text().strip()
                except: course_name = "Unknown Course"
                if any(w in course_name for w in ["חינוך גופני", "הטרדה מינית", "הדרכה"]): continue

                match = re.search(r'(\d{5,8})', course_name)
                if match:
                    extracted_id = match.group(1)
                    global_course_map[extracted_id] = {"name": course_name, "url": url}

                print(f"   🔍 Checking: {course_name}")
                p_links = page.locator("a:has-text('HW'), a:has-text('WebWork'), a:has-text('webwork'), a:has-text('ווברק'), a:has-text('מערכת תרגילי בית')").all()
                valid_link = next((l for l in p_links if "mod/page" not in (l.get_attribute("href") or "") and "mod/forum" not in (l.get_attribute("href") or "")), None)
                if not valid_link: continue 

                valid_link.click(force=True)
                try: ww_page = context.wait_for_event("page", timeout=5000)
                except: ww_page = page

                ww_page.wait_for_selector("table.problem_set_table, li.list-group-item", timeout=8000)
                if ww_page.locator("li.list-group-item").count() > 0:
                    for row in ww_page.locator("li.list-group-item").all():
                        name_loc = row.locator("a.fw-bold")
                        if name_loc.count() > 0 and row.get_attribute("data-set-status") == "open":
                            details = row.locator("div.font-sm").first.inner_text().strip() 
                            due_date = details.split("Due")[-1].strip(' .') if "Due" in details else details
                            all_tasks.append({"course": course_name, "name": name_loc.first.inner_text().strip(), "due_date": due_date, "link": name_loc.first.get_attribute("href") or ww_page.url, "course_url": url})
                elif ww_page.locator("table.problem_set_table").count() > 0:
                    for row in ww_page.locator("table.problem_set_table tr").all()[1:]:
                        cols = row.locator("td").all()
                        if len(cols) >= 3 and cols[1].inner_text().strip().lower() == "open":
                            a_tag = cols[0].locator("a").first
                            all_tasks.append({"course": course_name, "name": cols[0].inner_text().strip(), "due_date": cols[2].inner_text().strip(), "link": a_tag.get_attribute("href") if a_tag else ww_page.url, "course_url": url})
                
                if ww_page != page: ww_page.close() 
            except Exception:
                try: [p.close() for p in context.pages if p != page]
                except: pass
                continue

        browser.close()
        print("✅ Sync Complete!")
        return {"tasks": all_tasks, "course_meta": global_course_map}


def run_exam_harvester():
    if not os.path.exists(COOKIE_FILE): return -1
    
    def send_update(msg, pct, eta):
        try: eel.update_harvest_progress(msg, int(pct), eta)()
        except: pass

    with sync_playwright() as p:
        send_update("Initializing Web Driver...", 5, "Calculating...")
        std_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        browser = p.chromium.launch(headless=True) 
        context = browser.new_context(user_agent=std_user_agent) 
        # ⚡ Added UTF-8 here as well just to be safe
        with open(COOKIE_FILE, 'r', encoding="utf-8") as f: context.add_cookies(json.load(f))
            
        page = context.new_page()
        try: page.goto("https://moodle25.technion.ac.il/my/", wait_until="domcontentloaded", timeout=20000)
        except: pass
        if "/my/" not in page.url: browser.close(); return -1

        send_update("Sweeping Moodle Dashboard...", 10, "Calculating...")
        try:
            c_tab = page.locator("a:has-text('הקורסים שלי')").first
            if c_tab.is_visible(timeout=3000): c_tab.click()
        except: pass
        try: page.wait_for_selector("a[href*='course/view.php?id=']", timeout=10000); page.wait_for_timeout(2000) 
        except: pass

        course_links = page.locator("a[href*='course/view.php?id=']").all()
        course_urls = list(set([link.get_attribute("href") for link in course_links if link.get_attribute("href")]))
        downloaded_count = 0
        total_courses = len(course_urls)
        
        for idx, url in enumerate(course_urls):
            pct = 10 + ((idx / total_courses) * 90)
            eta_mins = (total_courses - idx) * 2 
            eta_str = f"~{eta_mins} mins remaining"
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                try: course_name = page.locator("h1").first.inner_text().strip()
                except: continue
                safe_course = "".join([c for c in course_name if c.isalnum() or c.isspace() or c == '-']).strip()
                if not safe_course: safe_course = f"Course_{idx}"
                
                send_update(f"Scanning: {safe_course}", pct, eta_str)
                course_dir = os.path.join(os.getcwd(), "web", "vault", safe_course)
                
                sections = page.locator("li.section.main, section.course-section").all()
                if not sections: sections = [page] 
                
                for sec in sections:
                    if sec == page:
                        safe_sec = "General"
                    else:
                        try: sec_name = sec.locator("h3, h4").first.inner_text().strip()
                        except: sec_name = "General"
                        safe_sec = "".join([c for c in sec_name if c.isalnum() or c.isspace() or c in '-_()']).strip()
                        if not safe_sec: safe_sec = "General"
                    
                    sec_dir = os.path.join(course_dir, safe_sec)

                    resources = sec.locator("a[href*='mod/resource/view.php']").all()
                    for res in resources:
                        try:
                            href = res.get_attribute("href")
                            text = res.inner_text().strip()
                            safe_file = "".join([c for c in text if c.isalnum() or c.isspace() or c in '-_()']).strip()
                            if not safe_file: safe_file = f"File_{random.randint(1000,9999)}"
                            
                            resp = page.context.request.get(href)
                            ctype = resp.headers.get("content-type", "").lower()
                            if resp.ok and "text/html" not in ctype:
                                ext = ".pdf"
                                if "word" in ctype or "document" in ctype: ext = ".docx"
                                elif "powerpoint" in ctype or "presentation" in ctype: ext = ".pptx"
                                elif "zip" in ctype or "archive" in ctype: ext = ".zip"
                                file_path = os.path.join(sec_dir, safe_file + ext)
                                if not os.path.exists(file_path):
                                    os.makedirs(sec_dir, exist_ok=True)
                                    with open(file_path, "wb") as f: f.write(resp.body())
                                    downloaded_count += 1
                            elif resp.ok and "text/html" in ctype:
                                sub_page = context.new_page()
                                try:
                                    sub_page.goto(href, wait_until="domcontentloaded", timeout=8000)
                                    real_link = sub_page.locator("div.resourceworkaround a, object[type='application/pdf']").first
                                    if real_link.count() > 0:
                                        real_href = real_link.get_attribute("href") if real_link.evaluate("el => el.tagName").lower() == "a" else real_link.get_attribute("data")
                                        if real_href:
                                            file_resp = page.context.request.get(real_href)
                                            if file_resp.ok:
                                                file_path = os.path.join(sec_dir, safe_file + ".pdf")
                                                if not os.path.exists(file_path):
                                                    os.makedirs(sec_dir, exist_ok=True)
                                                    with open(file_path, "wb") as f: f.write(file_resp.body())
                                                    downloaded_count += 1
                                except: pass
                                finally: sub_page.close()
                        except: pass

                    moodle_folders = sec.locator("a[href*='mod/folder/view.php']").all()
                    folder_urls = list(set([f.get_attribute("href") for f in moodle_folders]))
                    
                    for f_url in folder_urls:
                        sub_page = context.new_page()
                        try:
                            sub_page.goto(f_url, wait_until="domcontentloaded", timeout=10000)
                            try: folder_name = sub_page.locator("h2").first.inner_text().strip()
                            except: folder_name = f"Folder_{random.randint(100,999)}"
                            safe_folder = "".join([c for c in folder_name if c.isalnum() or c.isspace() or c in '-_()']).strip()
                            
                            folder_dir = os.path.join(sec_dir, safe_folder)
                            files = sub_page.locator("a[href*='pluginfile.php']").all()
                            for fl in files:
                                fl_href = fl.get_attribute("href")
                                fl_text = fl.inner_text().strip()
                                safe_file = "".join([c for c in fl_text if c.isalnum() or c.isspace() or c in '-_().']).strip()
                                if not safe_file: safe_file = f"File_{random.randint(1000,9999)}.pdf"
                                if "." not in safe_file: safe_file += ".pdf"
                                
                                if "?forcedownload=1" not in fl_href: fl_href += "?forcedownload=1"
                                
                                file_path = os.path.join(folder_dir, safe_file)
                                if not os.path.exists(file_path):
                                    os.makedirs(folder_dir, exist_ok=True)
                                    file_resp = sub_page.context.request.get(fl_href)
                                    if file_resp.ok:
                                        with open(file_path, "wb") as f: f.write(file_resp.body())
                                        downloaded_count += 1
                        except: pass
                        finally: sub_page.close()
                        
            except Exception: continue

        send_update("Finalizing files...", 100, "Done!")
        browser.close()
        return downloaded_count