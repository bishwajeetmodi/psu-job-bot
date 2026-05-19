import requests
from bs4 import BeautifulSoup
import re
import sqlite3
import pdfplumber
from urllib.parse import urljoin
from datetime import datetime
import os

# =====================================================
# 🤖 TELEGRAM CONFIG
# =====================================================

BOT_TOKEN = "8929362509:AAES5eVT4zFeasfITxEI5MwDsKZDpbafI10"
CHAT_ID = "898809138"

DB_NAME = "psu_jobs.db"

# =====================================================
# 🏢 PSU CAREER PAGES
# =====================================================

CAREER_PAGES = {
    "Coal India": "https://www.coalindia.in/career-cil/",
    "ONGC": "https://ongcindia.com/web/eng/career",
    "NTPC": "https://careers.ntpc.co.in/recruitment/",
    "IOCL": "https://iocl.com/latest-job-opening",
    "GAIL": "https://gailonline.com/CRCurrentOpening.html",
    "BHEL": "https://careers.bhel.in/",
    "BEL": "https://bel-india.in/",
    "RITES": "https://rites.com/",
    "NFL": "https://nationalfertilizers.com/",
    "NALCO": "https://nalcoindia.com/",
    "AAI": "https://www.aai.aero/",
    "NBCC": "https://www.nbccindia.in/",
    "ECIL": "https://www.ecil.co.in/",
    "IRCON": "https://www.ircon.org/",
    "NHPC": "https://www.nhpcindia.com/"
}

# =====================================================
# 🎯 FILTERS
# =====================================================

KEYWORDS = [
    "recruitment",
    "vacancy",
    "advertisement",
    "notification",
    "apply",
    "career",
    "walk-in",
    "executive trainee",
    "management trainee",
    "officer",
    "job opening"
]

BLOCKED = [
    "policy",
    "tender",
    "circular",
    "manual",
    "holiday",
    "csr",
    "annual report",
    "purchase",
    "finance",
    "corrigendum"
]

# =====================================================
# 🗄 DATABASE + AUTO MIGRATION
# =====================================================

def init_db():

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        link TEXT PRIMARY KEY,
        company TEXT,
        title TEXT,
        ad_date TEXT,
        last_date TEXT,
        pdf_text TEXT,
        timestamp TEXT
    )
    """)

    cursor.execute("PRAGMA table_info(jobs)")
    columns = [col[1] for col in cursor.fetchall()]

    if "timestamp" not in columns:
        try:
            cursor.execute(
                "ALTER TABLE jobs ADD COLUMN timestamp TEXT"
            )
        except:
            pass

    conn.commit()

    return conn, cursor


conn, cursor = init_db()

# =====================================================
# 📩 TELEGRAM MESSAGE
# =====================================================

def send_message(text):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    try:
        requests.post(url, data=payload, timeout=20)

    except Exception as e:
        print("Telegram Error:", e)

# =====================================================
# 🚫 RECRUITMENT FILTER
# =====================================================

def is_recruitment(text):

    text = text.lower()

    if any(word in text for word in BLOCKED):
        return False

    return any(word in text for word in KEYWORDS)

# =====================================================
# 📅 DATE EXTRACTION
# =====================================================

def extract_date(text):

    patterns = [

        r"\d{2}/\d{2}/\d{4}",
        r"\d{2}-\d{2}-\d{4}",
        r"\d{1,2}\s+[A-Za-z]+\s+\d{4}"

    ]

    for pattern in patterns:

        match = re.search(pattern, text)

        if match:
            return match.group()

    return "Not Found"

# =====================================================
# 📄 PDF DOWNLOAD
# =====================================================

def download_pdf(url):

    try:

        response = requests.get(url, timeout=20)

        file_path = "temp.pdf"

        with open(file_path, "wb") as f:
            f.write(response.content)

        return file_path

    except Exception as e:

        print("PDF Download Error:", e)

        return None

# =====================================================
# 📄 READ PDF
# =====================================================

def read_pdf(path):

    text = ""

    try:

        with pdfplumber.open(path) as pdf:

            for page in pdf.pages:

                page_text = page.extract_text()

                if page_text:
                    text += page_text + "\n"

    except Exception as e:

        print("PDF Read Error:", e)

    return text

# =====================================================
# 🧾 DATABASE CHECK
# =====================================================

def exists(link):

    cursor.execute(
        "SELECT 1 FROM jobs WHERE link=?",
        (link,)
    )

    return cursor.fetchone() is not None

# =====================================================
# 💾 SAVE JOB
# =====================================================

def save(job):

    cursor.execute("""

    INSERT OR IGNORE INTO jobs
    (link, company, title, ad_date,
     last_date, pdf_text, timestamp)

    VALUES (?, ?, ?, ?, ?, ?, ?)

    """, (

        job["link"],
        job["company"],
        job["title"],
        job["ad_date"],
        job["last_date"],
        job.get("pdf_text", ""),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ))

    conn.commit()

# =====================================================
# 🌐 SCRAPER
# =====================================================

def scrape(company, url):

    jobs = []

    try:

        response = requests.get(url, timeout=20)

        soup = BeautifulSoup(response.text, "lxml")

        links = soup.find_all("a", href=True)

        print(f"{company}: {len(links)} links found")

        for a in links:

            title = a.get_text(" ", strip=True)

            if len(title) < 5:
                continue

            link = urljoin(url, a["href"])

            parent_text = a.parent.get_text(
                " ",
                strip=True
            )

            jobs.append({

                "company": company,
                "title": title,
                "link": link,
                "ad_date": extract_date(parent_text),
                "last_date": "Not Found"

            })

    except Exception as e:

        print(f"Scraping Error ({company}):", e)

    return jobs

# =====================================================
# 🚀 MAIN BOT
# =====================================================

def run_bot():

    print("\n🚀 PSU Recruitment Bot Started\n")

    total_alerts = 0

    for company, url in CAREER_PAGES.items():

        print(f"🔍 Scraping {company}...")

        jobs = scrape(company, url)

        for job in jobs:

            text = job["title"] + " " + job["link"]

            # recruitment filter
            if not is_recruitment(text):
                continue

            # duplicate filter
            if exists(job["link"]):
                continue

            # PDF Parsing
            job["pdf_text"] = ""

            if job["link"].lower().endswith(".pdf"):

                print("📄 PDF Found")

                pdf_file = download_pdf(job["link"])

                if pdf_file:

                    pdf_text = read_pdf(pdf_file)

                    job["pdf_text"] = pdf_text[:5000]

            # save to DB
            save(job)

            # telegram message
            message = f"""
🏢 <b>PSU Recruitment Alert</b>

🏭 <b>Company:</b>
{job['company']}

📌 <b>Title:</b>
{job['title']}

📅 <b>Advertisement Date:</b>
{job['ad_date']}

🔗 <b>Link:</b>
{job['link']}
"""

            send_message(message)

            total_alerts += 1

            print("✅ Alert Sent")

    print(f"\n📩 Total Alerts Sent: {total_alerts}")

# =====================================================
# ▶ ENTRY POINT
# =====================================================

if __name__ == "__main__":
    run_bot()
