import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import requests
import dropbox
from datetime import datetime, timedelta
import pytz

# Hent miljøvariabler fra GitHub Secrets
EMAIL_SENDER = os.getenv('EMAIL_SENDER')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
EMAIL_RECIPIENTS = [email.strip() for email in os.getenv('EMAIL_RECIPIENT', '').split(',')]
APP_KEY = os.getenv('APP_KEY')
APP_SECRET = os.getenv('APP_SECRET')
REFRESH_TOKEN = os.getenv('REFRESH_TOKEN')

def get_access_token():
    """Henter en ny access token fra Dropbox ved hjælp af refresh token."""
    url = "https://api.dropboxapi.com/oauth2/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN,
        "client_id": APP_KEY,
        "client_secret": APP_SECRET
    }
    
    response = requests.post(url, data=data)
    response.raise_for_status()
    return response.json()['access_token']

def download_db_from_dropbox(access_token):
    """Downloader databasefilen fra Dropbox ved hjælp af en access token."""
    dbx = dropbox.Dropbox(access_token)
    with open("products.db", "wb") as f:
        metadata, res = dbx.files_download(path="/products.db")
        f.write(res.content)
    print("Database downloaded from Dropbox")

def fetch_expiring_products():
    """Forespørger databasen om produkter, der udløber i dag eller inden for de næste 14 dage."""
    conn = sqlite3.connect("products.db")
    cursor = conn.cursor()

    today = datetime.now().strftime('%Y-%m-%d')
    in_14_days = (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')

    query = """
    SELECT 
        "Article Description Batch",
        "Expiry Date",
        "EAN Serial No",
        "Ship QTY",
        "PDF Source"
    FROM products 
    WHERE date(substr(`Expiry Date`, 7, 4) || '-' || substr(`Expiry Date`, 4, 2) || '-' || substr(`Expiry Date`, 1, 2)) 
    BETWEEN ? AND ?
    ORDER BY date(substr(`Expiry Date`, 7, 4) || '-' || substr(`Expiry Date`, 4, 2) || '-' || substr(`Expiry Date`, 1, 2))
    """
    cursor.execute(query, (today, in_14_days))
    products = cursor.fetchall()

    conn.close()
    return products

def generate_email_report(products):
    """Genererer en e-mailrapport baseret på produkterne."""
    if not products:
        return "<tr><td colspan='5'>Ingen produkter udløber indenfor de næste 14 dage.</td></tr>", ""

    email_body_today = ""
    email_body_14_days = ""

    # Dato i dag
    today_date = datetime.now().strftime('%d.%m.%Y')

    for product in products:
        article_description = product[0] if product[0] else "Ingen beskrivelse"
        expiry_date = product[1] if product[1] else "Ingen dato"
        ean_serial_no = product[2] if product[2] else "Ingen"
        ship_qty = product[3] if product[3] else "Ingen"
        pdf_source = product[4] if product[4] else "Ingen"
        
        row = f"""
        <tr>
            <td class="product-name">{article_description}</td>
            <td class="date">{expiry_date}</td>
            <td class="ean">{ean_serial_no}</td>
            <td class="qty">{ship_qty}</td>
            <td class="source">{pdf_source}</td>
        </tr>
        """

        if expiry_date == today_date:
            row = f"""
            <tr style="color: red; font-weight: bold;">
                <td class="product-name">{article_description}</td>
                <td class="date">{expiry_date}</td>
                <td class="ean">{ean_serial_no}</td>
                <td class="qty">{ship_qty}</td>
                <td class="source">{pdf_source}</td>
            </tr>
            """
            email_body_today += row
        else:
            email_body_14_days += row

    if email_body_today == "":
        email_body_today = "<tr><td colspan='5'>Ingen produkter udløber i dag.</td></tr>"

    return email_body_today, email_body_14_days

def send_email(subject, body_today, body_14_days):
    """Sender e-mailen til alle modtagere."""
    msg = MIMEMultipart("alternative")
    msg['From'] = EMAIL_SENDER
    msg['Subject'] = subject
    
    html = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                color: #333333;
            }}
            .container {{
                width: 80%;
                margin: 0 auto;
                padding: 20px;
                background-color: #f9f9f9;
                border: 1px solid #ddd;
                border-radius: 10px;
            }}
            h1 {{
                color: #4A90E2;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
                table-layout: fixed;
            }}
            th, td {{
                padding: 10px;
                border-bottom: 1px solid #ddd;
                text-align: left;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }}
            th {{
                background-color: #4A90E2;
                color: #ffffff;
            }}
            .product-name {{
                width: 35%;
            }}
            .date {{
                width: 15%;
            }}
            .ean {{
                width: 20%;
            }}
            .qty {{
                width: 15%;
            }}
            .source {{
                width: 15%;
            }}
            tr:hover {{
                background-color: #f5f5f5;
            }}
            .warning {{
                color: #ff6b6b;
                font-weight: bold;
            }}
            @media screen and (max-width: 768px) {{
                .container {{
                    width: 95%;
                    padding: 10px;
                }}
                th, td {{
                    padding: 5px;
                    font-size: 14px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Dagens Rapport: Udløbende Produkter</h1>

            <h2>Produkter Udløbende I Dag:</h2>
            <table>
                <tr>
                    <th class="product-name">Article Description</th>
                    <th class="date">Expiry Date</th>
                    <th class="ean">EAN Serial No</th>
                    <th class="qty">Ship QTY</th>
                    <th class="source">PDF Source</th>
                </tr>
                {body_today}
            </table>

            <h2>Produkter Udløbende Indenfor 14 Dage</h2>
            <p>Her er en liste over produkter, der udløber inden for de næste 14 dage:</p>
            <table>
                <tr>
                    <th class="product-name">Article Description</th>
                    <th class="date">Expiry Date</th>
                    <th class="ean">EAN Serial No</th>
                    <th class="qty">Ship QTY</th>
                    <th class="source">PDF Source</th>
                </tr>
                {body_14_days}
            </table>

            <p style="margin-top: 20px; font-size: 12px; color: #666;">
                Denne rapport er automatisk genereret. Ved spørgsmål kontakt venligst IT-support.
            </p>
        </div>
    </body>
    </html>
    """

    msg.attach(MIMEText(html, "html"))
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        
        # Send til hver modtager individuelt
        for recipient in EMAIL_RECIPIENTS:
            if recipient:  # Tjek at e-mailen ikke er tom
                msg_copy = MIMEMultipart("alternative")
                msg_copy['From'] = EMAIL_SENDER
                msg_copy['To'] = recipient
                msg_copy['Subject'] = subject
                msg_copy.attach(MIMEText(html, "html"))
                
                server.sendmail(EMAIL_SENDER, recipient, msg_copy.as_string())
                print(f"E-mail sendt succesfuldt til {recipient}")
        
        server.quit()
        print("Alle e-mails er sendt succesfuldt.")
    except Exception as e:
        print(f"Fejl ved afsendelse af e-mail: {e}")

if __name__ == "__main__":
    try:
        print("Starter daglig rapport proces...")
        access_token = get_access_token()
        print("Access token hentet fra Dropbox")
        
        download_db_from_dropbox(access_token)
        print("Database downloaded fra Dropbox")
        
        products = fetch_expiring_products()
        print(f"Fandt {len(products)} produkter der udløber snart")
        
        report_body_today, report_body_14_days = generate_email_report(products)
        print("E-mail rapport genereret")
        
        send_email("Dagens rapport: Udløbende Produkter", report_body_today, report_body_14_days)
        print("Process fuldført succesfult")
    except Exception as e:
        print(f"Kritisk fejl i hovedprocessen: {e}")
        # Her kunne tilføjes yderligere fejlhåndtering efter behov