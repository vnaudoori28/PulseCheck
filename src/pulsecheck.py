import os
import json
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date

# ── Config ────────────────────────────────────────────────────────────────────

MONDAY_API_TOKEN   = os.environ["MONDAY_API_TOKEN"]
TRACKER_BOARD_ID   = os.environ["TRACKER_BOARD_ID"]
SMTP_HOST          = os.environ["SMTP_HOST"]          # e.g. smtp.zoho.com
SMTP_PORT          = int(os.environ.get("SMTP_PORT", 465))
SMTP_USER          = os.environ["SMTP_USER"]          # sender address
SMTP_PASSWORD      = os.environ["SMTP_PASSWORD"]

PULSECHECK_DAILY_LINK      = "https://survey.zoho.com/zs/QsBhQd"
PULSECHECK_ESCALATION_LINK = "https://survey.zoho.com/zs/3CBhu8"

# Monday full name → email (must match exact text from Logistics/Buddy column)
MEMBER_EMAILS = {
    "Varalakshmi Naudoori": "lakshmi@authentica.com",
    # "Siddhanth Waghmare":  "sid@authentica.com",
    # "Aakash Korandla":     "aakash@authentica.com",
    # "Bhavana ???":         "bhavana@authentica.com",
    # "Debolina ???":        "debolina@authentica.com",
    # "Komal ???":           "komal@authentica.com",
    # "Vedanth Maheshwari":  "vedanth@authentica.com",
}

ESCALATION_RECIPIENTS = [
    "lakshmi@authentica.com",
    # "ravi@authentica.com",
    # "sid@authentica.com",
    # "vedanth@authentica.com",
]

PEOPLE_COLUMN_ID = "multiple_person_mkqnz36m"

# ── Monday.com ────────────────────────────────────────────────────────────────

def fetch_assignments():
    """Returns { display_name: [program_name, ...] } for all active board items."""
    query = """
    query ($board_id: ID!) {
      boards(ids: [$board_id]) {
        items_page(limit: 200) {
          items {
            name
            column_values(ids: ["multiple_person_mkqnz36m"]) {
              ... on PeopleValue {
                persons_and_teams {
                  id
                  kind
                }
              }
              text
            }
          }
        }
      }
    }
    """
    headers = {
        "Authorization": MONDAY_API_TOKEN,
        "Content-Type": "application/json",
        "API-Version": "2024-01"
    }
    resp = requests.post(
        "https://api.monday.com/v2",
        headers=headers,
        json={"query": query, "variables": {"board_id": TRACKER_BOARD_ID}},
        timeout=30
    )
    resp.raise_for_status()
    data = resp.json()

    assignments = {}  # { "Lakshmi": ["Program A", "Program B"] }

    items = data["data"]["boards"][0]["items_page"]["items"]
    for item in items:
        program_name = item["name"]
        col = item["column_values"][0] if item["column_values"] else None
        if not col:
            continue
        text = col.get("text", "") or ""
        if not text.strip():
            continue
        # text is comma-separated display names e.g. "Lakshmi, Aakash"
        for raw_name in text.split(","):
            name = raw_name.strip()
            if name:
                assignments.setdefault(name, []).append(program_name)

    return assignments

# ── Email ─────────────────────────────────────────────────────────────────────

def send_email(to_addresses, subject, html_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_USER
    msg["To"]      = ", ".join(to_addresses)
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, to_addresses, msg.as_string())
    print(f"  ✓ Sent to {', '.join(to_addresses)}")

# ── Email Templates ───────────────────────────────────────────────────────────

def team_email_body(name, programs, survey_link, today):
    program_rows = "".join(
        f"<li style='margin:4px 0;'>{p}</li>" for p in programs
    )
    return f"""
    <div style="font-family:Arial,sans-serif;font-size:14px;color:#333;max-width:600px;">
      <h2 style="color:#2c5f8a;">🟢 PulseCheck Daily — {today}</h2>
      <p>Hi {name},</p>
      <p>Time for your daily program status check-in. You are currently assigned to the following programs:</p>
      <ul style="background:#f5f7fa;padding:12px 24px;border-radius:6px;">
        {program_rows}
      </ul>
      <p>Please submit <strong>one entry per program</strong> using the form below.
         Copy the program name from the list above and paste it into the form.</p>
      <p style="margin:24px 0;">
        <a href="{survey_link}"
           style="background:#2c5f8a;color:#fff;padding:10px 20px;border-radius:4px;text-decoration:none;font-weight:bold;">
          Open PulseCheck Daily →
        </a>
      </p>
      <p style="color:#888;font-size:12px;">
        If a program is Red or Amber, please add remarks in the Remarks field.<br>
        Takes less than 2 minutes. Thank you!
      </p>
    </div>
    """

def manager_email_body(survey_link, today):
    return f"""
    <div style="font-family:Arial,sans-serif;font-size:14px;color:#333;max-width:600px;">
      <h2 style="color:#8a2c2c;">🔴 PulseCheck Escalation Log — {today}</h2>
      <p>Hi,</p>
      <p>Use the form below to log any escalations raised today against programs or team members.</p>
      <p>Submit <strong>one entry per escalation</strong>.</p>
      <p style="margin:24px 0;">
        <a href="{survey_link}"
           style="background:#8a2c2c;color:#fff;padding:10px 20px;border-radius:4px;text-decoration:none;font-weight:bold;">
          Open Escalation Log →
        </a>
      </p>
      <p style="color:#888;font-size:12px;">
        <strong>Severity guide:</strong><br>
        🔴 <strong>High</strong> — Program delivery at risk; client informed or likely to escalate.<br>
        🟡 <strong>Medium</strong> — Internal blocker needing resolution within 2–3 days.<br>
        🟢 <strong>Low</strong> — Minor issue being tracked, no immediate delivery risk.
      </p>
    </div>
    """

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    today = date.today().strftime("%d %b %Y")
    print(f"\n📋 PulseCheck Dispatch — {today}\n")

    # 1. Pull assignments from Monday
    print("Fetching assignments from Monday.com...")
    assignments = fetch_assignments()
    print(f"  Found assignments for: {', '.join(assignments.keys()) or 'nobody'}\n")

    # 2. Send team member emails
    print("Sending PulseCheck Daily emails...")
    for name, email in MEMBER_EMAILS.items():
        programs = assignments.get(name, [])
        if not programs:
            print(f"  ⚠ No programs found for {name} — skipping")
            continue
        first_name = name.split()[0]
        body = team_email_body(first_name, programs, PULSECHECK_DAILY_LINK, today)
        send_email([email], f"PulseCheck Daily — {today}", body)

    # 3. Send manager escalation email
    print("\nSending Escalation Log email...")
    body = manager_email_body(PULSECHECK_ESCALATION_LINK, today)
    send_email(ESCALATION_RECIPIENTS, f"PulseCheck Escalation Log — {today}", body)

    print("\n✅ PulseCheck dispatch complete.")

if __name__ == "__main__":
    main()
