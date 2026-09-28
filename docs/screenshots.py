"""Capture screenshots of the running app (python app.py) with headless Chrome for the report/PPT."""
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.common.by import By

BASE = "http://localhost:5000"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
os.makedirs(OUT, exist_ok=True)

opts = webdriver.ChromeOptions()
opts.add_argument("--headless=new")
opts.add_argument("--window-size=1366,900")
opts.add_argument("--hide-scrollbars")
opts.add_argument("--force-device-scale-factor=1")
opts.add_experimental_option("prefs", {"credentials_enable_service": False, "profile.password_manager_enabled": False,
                                       "profile.password_manager_leak_detection": False})
d = webdriver.Chrome(options=opts)


def shot(name, path, wait=1.5, full=False, width=1366, height=900):
    d.set_window_size(width, height)
    d.get(BASE + path)
    time.sleep(wait)
    if full:
        h = d.execute_script("return document.documentElement.scrollHeight")
        d.set_window_size(width, min(h + 20, 3000))
        time.sleep(0.6)
    d.save_screenshot(os.path.join(OUT, name + ".png"))
    print("saved", name)


def login(user, pw):
    d.set_window_size(1366, 900)
    d.get(BASE + "/logout")
    d.delete_all_cookies()
    d.get(BASE + "/login")
    time.sleep(0.5)
    d.find_element(By.NAME, "username").send_keys(user)
    d.find_element(By.NAME, "password").send_keys(pw)
    d.execute_script("document.querySelector('main form').submit()")
    from selenium.webdriver.support.ui import WebDriverWait
    WebDriverWait(d, 30).until(lambda drv: "/login" not in drv.current_url)


creds = dict(a.split("=") for a in sys.argv[1:])   # farmer=user:pw officer=user:pw
shot("01_landing", "/lang/en", full=True)
fu, fp = creds["farmer"].split(":")
login(fu, fp)
shot("02_farmer_home", "/farmer", wait=3, full=True)
farm_link = d.find_element(By.CSS_SELECTOR, ".farm-card h3 a").get_attribute("href")
shot("03_farm_risk", farm_link.replace(BASE, ""), wait=3, full=True)
shot("04_diagnose", "/diagnose")
d.get(BASE + "/reports")
rep = d.execute_script("return [...document.querySelectorAll('a')].map(a=>a.href).filter(h=>h.includes('/report/'))")
shot("05_report", rep[0].replace(BASE, ""), wait=3, full=True)
d.get(BASE + "/lang/kn")
shot("06_report_kannada", rep[0].replace(BASE, ""), wait=2, full=True)
d.get(BASE + "/lang/ta")
shot("07_advisory_tamil", "/advisories/Tomato___Late_blight", full=True)
d.get(BASE + "/lang/en")
shot("08_mobile_home", "/farmer", wait=3, width=390, height=844, full=True)
ou, op = creds["officer"].split(":")
login(ou, op)
d.get(BASE + "/lang/en")
shot("09_officer_queue", "/officer", wait=2, full=True)
rid = d.execute_script("return [...document.querySelectorAll('a')].map(a=>a.href).filter(h=>h.includes('/officer/review/'))[0]")
shot("10_review", rid.replace(BASE, ""), wait=2, full=True)
shot("11_map", "/map", wait=6)
shot("12_dashboard", "/dashboard", wait=4, full=True)
shot("13_model", "/admin/model", wait=2, full=True)
shot("14_advisory_library", "/advisories", wait=1.5)
d.quit()
