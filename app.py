from flask import Flask, render_template, request, redirect, url_for, jsonify, session, make_response, abort
from flask import send_from_directory
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user
from pymongo import MongoClient
from werkzeug.utils import secure_filename
from bson.objectid import ObjectId
import pytesseract, os, re, json, io
from PIL import Image
from datetime import datetime
import traceback
import shutil
from functools import wraps
from reportlab.pdfgen import canvas as _pdf_canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from flask_cors import CORS
import requests
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import Firestore utilities
from firestore_utils import db, UPDATES_COLLECTION, FAQ_COLLECTION

# Application Configuration
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv('SECRET_KEY', 'dev-secret-key'),  # Change this to a random secret key in production
    UPLOAD_FOLDER='uploads',
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB max file size
)

# Initialize extensions
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
CORS(app)

# LLM Configuration
LLM_API_ENDPOINT = os.getenv('LLM_API_ENDPOINT', 'https://api.openai.com/v1/chat/completions')
LLM_API_KEY = os.getenv('NVIDIA_API_KEY') or os.getenv('OPENAI_API_KEY')
LLM_MODEL = os.getenv('LLM_MODEL', 'gpt-3.5-turbo')

# LLM Context Management
def get_user_context(email: str) -> List[Dict[str, str]]:
    """Get conversation context for the user"""
    try:
        # Get last 5 messages from chat history
        chat_history = list(chats_col.find(
            {"user": email},
            {"_id": 0, "role": 1, "content": "$text", "date": 1}
        ).sort("date", -1).limit(10))
        
        # Convert to LLM message format and reverse to maintain order
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in reversed(chat_history)
        ]
    except Exception as e:
        print(f"Error fetching chat history: {e}")
        return []

def get_financial_context(email: str) -> Dict[str, Any]:
    """Get financial context for the user"""
    try:
        # Get recent expenses summary
        pipeline = [
            {"$match": {"user": email}},
            {"$sort": {"date": -1}},
            {"$limit": 30},  # Last 30 transactions
            {"$group": {
                "_id": "$category",
                "total": {"$sum": "$amount"},
                "count": {"$sum": 1},
                "last_date": {"$first": "$date"}
            }},
            {"$sort": {"total": -1}}
        ]
        expenses = list(expenses_col.aggregate(pipeline))
        
        # Get budget if set
        settings = _get_user_settings(email)
        
        return {
            "recent_expenses": expenses[:5],  # Top 5 categories
            "total_spent": sum(e["total"] for e in expenses),
            "monthly_budget": settings.get("monthly_budget"),
            "savings_goal": settings.get("savings_goal")
        }
    except Exception as e:
        print(f"Error fetching financial context: {e}")
        return {}

def generate_llm_response(user_message: str, user_email: str) -> str:
    """Generate a response using the LLM"""
    if not LLM_API_KEY:
        return "LLM integration is not configured. Please set the OPENAI_API_KEY environment variable."
    
    # Get conversation and financial context
    conversation = get_user_context(user_email)
    financial_context = get_financial_context(user_email)
    
    # Prepare system message with financial context
    system_message = {
        "role": "system",
        "content": f"""You are a helpful financial advisor AI assistant. Your goal is to help users manage their expenses, save money, and make better financial decisions.
        
        User's Financial Context:
        - Top Spending Categories: {', '.join([f"{e['_id']} (${e['total']:.2f})" for e in financial_context.get('recent_expenses', [])])}
        - Total Monthly Spend: ${financial_context.get('total_spent', 0):.2f}
        - Monthly Budget: ${financial_context.get('monthly_budget', 'Not set')}
        - Savings Goal: ${financial_context.get('savings_goal', 'Not set')}
        
        Guidelines:
        1. Be concise and specific in your responses
        2. Provide actionable advice
        3. Reference the user's spending patterns when relevant
        4. Suggest specific budget adjustments
        5. Be encouraging and non-judgmental
        """
    }
    
    # Prepare messages for the API
    messages = [system_message] + conversation + [{"role": "user", "content": user_message}]
    
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_API_KEY}"
        }
        
        payload = {
            "model": LLM_MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 500
        }
        
        response = requests.post(
            LLM_API_ENDPOINT,
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            print(f"LLM API Error: {response.status_code} - {response.text}")
            return "I'm having trouble connecting to the AI assistant. Please try again later."
            
    except Exception as e:
        print(f"Error calling LLM API: {e}")
        return "I'm sorry, I encountered an error while processing your request. Please try again."


# Tesseract OCR configuration
tess_cmd = os.getenv('TESSERACT_CMD', '/opt/homebrew/bin/tesseract')
pytesseract.pytesseract.tesseract_cmd = tess_cmd
_tess_found = shutil.which('tesseract')
if _tess_env:
    pytesseract.pytesseract.tesseract_cmd = _tess_env
elif _tess_found:
    pytesseract.pytesseract.tesseract_cmd = _tess_found


app = Flask(__name__)
app.secret_key = "super_secret_key"

# Configure CORS
CORS(app, 
     resources={
         r"/api/*": {
             "origins": ["http://localhost:5000", "http://127.0.0.1:5000"],
             "supports_credentials": True,
             "allow_headers": ["Content-Type", "Authorization"],
             "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
         }
     })

bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# Make sure uploads folder exists
os.makedirs('uploads', exist_ok=True)

# Database connection
mongo_uri = os.getenv('MONGO_URI')
if not mongo_uri:
    raise ValueError("No MONGO_URI environment variable set. Please check your .env file.")

client = MongoClient(mongo_uri)
db = client[os.getenv('MONGO_DB_NAME', 'ai_expenses')]

# Collections
users_col = db["users"]
expenses_col = db["expenses"]
chats_col = db["chats"]
notifications_col = db["notifications"]
faq_col = db["faqs"]
updates_col = db["updates"]

class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data["_id"])
        self.email = user_data.get("email")
        self.username = user_data.get("username") or (self.email.split('@')[0] if self.email else None)
        self.is_admin = user_data.get("is_admin", False)

@login_manager.user_loader
def load_user(user_id):
    try:
        u = users_col.find_one({"_id": ObjectId(user_id)})
        return User(u) if u else None
    except Exception:
        return None


def categorize_expense(text):
    text = text.lower()
    categories = {
        "Food": ["food", "restaurant", "burger", "pizza", "hotel", "meal", "snack", "biryani"],
        "Travel": ["uber", "ola", "train", "flight", "bus", "taxi", "petrol", "fuel"],
        "Entertainment": ["movie", "cinema", "netflix", "prime", "game", "music"],
        "Bills": ["electricity", "water", "mobile", "internet", "wifi"],
        "Shopping": ["amazon", "flipkart", "mall", "clothes", "store"],
        "Health": ["pharmacy", "hospital", "doctor", "medical"],
    }
    for cat, words in categories.items():
        if any(w in text for w in words):
            return cat
    return "Misc"

def assess_expense(category, amount, text):
    text_l = (text or "").lower()
    wanted = True
    reason = ""
    tips = []

    if category in ("Bills", "Health", "Travel"):
        wanted = True
        reason = f"{category} is generally a necessary expense."
        if category == "Bills":
            tips.append("Review recurring plans to eliminate unused subscriptions.")
        if category == "Health":
            tips.append("Compare pharmacies or use generics to reduce costs.")
    elif category in ("Entertainment", "Shopping"):
        wanted = False
        reason = f"{category} is usually discretionary."
        tips.append("Set a monthly cap for discretionary categories.")
        tips.append("Delay non-urgent purchases by 24 hours to curb impulse buys.")
    elif category == "Food":
        if any(k in text_l for k in ["restaurant", "hotel", "pizza", "burger", "biryani"]):
            wanted = False
            reason = "Eating out is discretionary compared to groceries."
            tips.append("Meal plan and cook at home more often.")
        else:
            wanted = True
            reason = "Groceries are generally necessary."
    else:
        wanted = amount < 500
        reason = "Small purchases may be okay; larger ones may be avoidable."

    if amount >= 2000 and category in ("Entertainment", "Shopping"):
        tips.append("High spend detected. Consider reducing frequency or finding cheaper alternatives.")
    if amount >= 5000:
        tips.append("Set aside an emergency buffer before large discretionary spends.")

    assessment = "Wanted" if wanted else "Unwanted"
    return assessment, reason, tips

def extract_total_amount(text: str) -> float:
    try:
        lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        keyword_patterns = [
            r"grand\s*total",
            r"total\s*amount",
            r"amount\s*payable",
            r"net\s*total",
            r"balance\s*due",
            r"total$",
            r"total\s*:"
        ]
        amount_pattern = r"(?:(?:₹|rs\.?)[\s:]*)?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)"

        def to_float(s: str):
            try:
                return float(s.replace(',', ''))
            except Exception:
                return None

        for ln in reversed(lines):
            low = ln.lower()
            if any(re.search(k, low, re.IGNORECASE) for k in keyword_patterns):
                m = re.search(amount_pattern, ln, re.IGNORECASE)
                if m:
                    val = to_float(m.group(1))
                    if val is not None:
                        return val

        currency_amounts = list(re.finditer(r"(?:₹|rs\.?)[\s:]*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)", text, re.IGNORECASE))
        if currency_amounts:
            val = to_float(currency_amounts[-1].group(1))
            if val is not None:
                return val

        candidates = []
        for m in re.finditer(r"[0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?", text):
            s = m.group(0)
            if len(re.sub(r"[^0-9]", "", s)) >= 10 and (',' not in s and '.' not in s):
                continue
            val = to_float(s)
            if val is None:
                continue
            if 1 <= val <= 1_000_000:
                candidates.append(val)
        if candidates:
            return max(candidates)

        return 0.0
    except Exception:
        return 0.0

def _parse_doc_date(s: str) -> datetime:
    try:
        return datetime.strptime(str(s), "%Y-%m-%d %H:%M")
    except Exception:
        return datetime.now()

def _month_bounds(dt: datetime):
    start = datetime(dt.year, dt.month, 1)
    if dt.month == 12:
        end = datetime(dt.year + 1, 1, 1)
    else:
        end = datetime(dt.year, dt.month + 1, 1)
    return start, end

TIP_BANK = {
    "Food": [
        "Plan meals and batch-cook twice a week.",
        "Buy staples in bulk and prefer store brands.",
        "Limit eating out to pre-planned occasions."
    ],
    "Travel": [
        "Bundle errands and carpool when possible.",
        "Use public transport for 1–2 trips per week.",
        "Track fuel efficiency and maintain tyre pressure."
    ],
    "Entertainment": [
        "Set a monthly cap and pre-schedule low-cost activities.",
        "Share subscriptions or rotate platforms.",
        "Use free community events."
    ],
    "Bills": [
        "Audit subscriptions; cancel unused plans.",
        "Negotiate internet/mobile plans annually.",
        "Use auto-pay to avoid late fees."
    ],
    "Shopping": [
        "Apply the 24-hour rule for non-essentials.",
        "Remove saved cards to reduce impulse buys.",
        "Compare across stores and wait for sales."
    ],
    "Health": [
        "Use generics and compare pharmacy prices.",
        "Schedule annual preventive checkups.",
        "Use HSAs/insurance to lower out-of-pocket."
    ],
}

TAX_TIPS_INDIA = [
    "Use Section 80C (₹1.5L): ELSS, PPF, EPF, SSY, life insurance premiums.",
    "Extra NPS under 80CCD(1B) (₹50k) in addition to 80C.",
    "80D: Health insurance premiums (self/family/parents) and preventive checkups.",
    "HRA exemption if paying rent (keep rent receipts, PAN of landlord if >₹1L/year).",
    "Home loan: 24(b) interest up to ₹2L; principal under 80C; consider 80EE/80EEA where eligible.",
    "80TTA/80TTB: Savings interest deduction (₹10k/₹50k for seniors).",
    "80G: Donations to approved institutions (retain receipts/Form 10BE).",
    "LTA: Claim for domestic travel as per employer policy with proofs.",
    "80E: Education loan interest deduction (no upper cap; max 8 years).",
    "Choose regime wisely: Old (deductions) vs New (lower rates, fewer deductions)."
]

def _get_user_settings(email: str) -> dict:
    try:
        u = users_col.find_one({"email": email}) or {}
        return u.get("settings") or {}
    except Exception:
        return {}

def _save_user_settings(email: str, settings: dict):
    try:
        users_col.update_one({"email": email}, {"$set": {"settings": settings}}, upsert=False)
    except Exception:
        pass

def _last_30d_totals(email: str):
    try:
        return list(expenses_col.aggregate([
            {"$match": {"user": email}},
            {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}}
        ]))
    except Exception:
        return []

def _sum_for_category(grouped, cat: str) -> float:
    for x in grouped:
        if str(x.get("_id")) == cat:
            try:
                return float(x.get("total") or 0)
            except Exception:
                return 0.0
    return 0.0

@app.route('/')
def home():
    # Show marketing landing page for guests; redirect logged-in users to dashboard
    try:
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
    except Exception:
        pass
    return render_template('landing.html')

@app.route('/logo.png')
def logo_asset():
    try:
        return send_from_directory('.', 'logo.png')
    except Exception:
        return ('', 404)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Handle both form data and JSON requests
        if request.is_json:
            data = request.get_json()
            email = data.get('email')
            password = data.get('password')
        else:
            email = request.form.get('email')
            password = request.form.get('password')
            
        if not email or not password:
            if request.is_json:
                return jsonify({"error": "Email and password are required"}), 400
            return render_template('login.html', error="Email and password are required")
            
        user = users_col.find_one({'email': email})
        if user and bcrypt.check_password_hash(user['password'], password):
            login_user(User(user))
            print(f"✅ Login success for {email}")
            if request.is_json:
                return jsonify({"message": "Login successful"}), 200
            return redirect(url_for('dashboard'))
            
        if request.is_json:
            return jsonify({"error": "Invalid credentials"}), 401
        return render_template('login.html', error="Invalid credentials.")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')
        
    # Handle POST request
    email = request.form.get('email')
    if not email:
        return render_template('register.html', error="Email is required.")
        
    username = (request.form.get('username') or '').strip()
    password = request.form.get('password')
    
    if not password:
        return render_template('register.html', error="Password is required.")
        
    if users_col.find_one({'email': email}):
        return render_template('register.html', error="User already exists.")

    # First user is always an admin
    is_first_user = users_col.count_documents({}) == 0
    users_col.insert_one({
        'email': email, 
        'password': bcrypt.generate_password_hash(password).decode('utf-8'),
        'username': username or email.split('@')[0],
        'is_admin': is_first_user,
        'created_at': datetime.utcnow()
    })
    return redirect(url_for('login', msg="Registration successful! Please login."))

@app.route('/dashboard')
@login_required
def dashboard():
    print(f"📊 Dashboard opened for {current_user.email}")
    display_name = getattr(current_user, 'username', None) or current_user.email
    return render_template('index.html', user=display_name)

@app.route('/analysis')
@login_required
def analysis_page():
    try:
        display_name = getattr(current_user, 'username', None) or current_user.email
        return render_template('analysis.html', user=display_name)
    except Exception:
        return render_template('analysis.html', user='')

@app.route('/api/summary')
@login_required
def api_summary():
    try:
        now = datetime.now()
        start, end = _month_bounds(now)

        # Fetch user expenses and filter by current month
        cursor = expenses_col.find({"user": current_user.email})
        expenses = []
        for x in cursor:
            try:
                d = _parse_doc_date(x.get('date'))
            except Exception:
                d = now
            if start <= d < end:
                expenses.append({
                    'date': d,
                    'category': x.get('category') or 'Misc',
                    'amount': float(x.get('amount') or 0),
                    'filename': x.get('filename')
                })

        total_spend = sum(e['amount'] for e in expenses)
        # Top categories
        cat_tot = {}
        for e in expenses:
            cat_tot[e['category']] = cat_tot.get(e['category'], 0.0) + float(e['amount'] or 0)
        top = sorted([{ 'category': k, 'total': v } for k, v in cat_tot.items()], key=lambda x: -x['total'])[:3]

        # Budget
        settings = _get_user_settings(current_user.email)
        budget = float(settings.get('monthly_budget') or 0)
        net_balance = (budget - total_spend) if budget else None
        pct = (total_spend / budget * 100.0) if budget else None

        # Recent activity
        recent = sorted(expenses, key=lambda x: x['date'], reverse=True)[:10]
        recent = [{
            'date': r['date'].strftime('%Y-%m-%d %H:%M'),
            'category': r['category'],
            'amount': r['amount'],
            'filename': r.get('filename')
        } for r in recent]

        return jsonify({
            'period': {
                'start': start.strftime('%Y-%m-%d'),
                'end': (end).strftime('%Y-%m-%d')
            },
            'total_spend': total_spend,
            'top_categories': top,
            'budget': {'amount': budget, 'percent_used': pct},
            'net_balance': net_balance,
            'recent': recent
        })
    except Exception:
        print('❌ api_summary error:', traceback.format_exc())
        return jsonify({'error': 'Unable to compute summary'}), 500

@app.route('/api/analysis')
@login_required
def api_analysis():
    try:
        # Parse range
        q_start = request.args.get('start')
        q_end = request.args.get('end')
        now = datetime.now()
        if q_start and q_end:
            try:
                start = datetime.strptime(q_start, '%Y-%m-%d')
                end = datetime.strptime(q_end, '%Y-%m-%d')
            except Exception:
                start, end = _month_bounds(now)
        else:
            start, end = _month_bounds(now)

        # Load all for user and filter by date
        items = []
        for x in expenses_col.find({"user": current_user.email}):
            d = _parse_doc_date(x.get('date'))
            if start <= d < end:
                items.append({
                    'date': d,
                    'merchant': (x.get('text') or '').split('\n', 1)[0][:40],
                    'category': x.get('category') or 'Misc',
                    'amount': float(x.get('amount') or 0)
                })

        # By day
        by_day = {}
        for e in items:
            k = e['date'].strftime('%Y-%m-%d')
            by_day[k] = by_day.get(k, 0.0) + e['amount']
        trend = [{'date': k, 'total': by_day[k]} for k in sorted(by_day.keys())]

        # By category
        by_cat = {}
        for e in items:
            by_cat[e['category']] = by_cat.get(e['category'], 0.0) + e['amount']
        cat_breakdown = [{'category': k, 'total': v} for k, v in sorted(by_cat.items(), key=lambda x: -x[1])]

        # AI-ish insights (heuristics)
        insights = []
        if cat_breakdown:
            vals = [c['total'] for c in cat_breakdown]
            avg = sum(vals) / len(vals)
            top = cat_breakdown[0]
            if avg and top['total'] > avg * 1.25:
                insights.append(f"Spending {((top['total']/avg)-1)*100:.0f}% above category average in {top['category']} this period.")
        # Forecast vs budget
        settings = _get_user_settings(current_user.email)
        budget = float(settings.get('monthly_budget') or 0)
        if budget:
            days = max((end - start).days, 1)
            spent = sum(e['amount'] for e in items)
            today_index = max((min(now, end) - start).days, 1)
            daily = spent / max(today_index, 1)
            forecast = daily * days
            if forecast > budget:
                insights.append(f"At this rate, you may exceed your budget by ₹{forecast - budget:.0f}.")

        table = [{
            'date': e['date'].strftime('%Y-%m-%d'),
            'merchant': e['merchant'],
            'category': e['category'],
            'amount': e['amount']
        } for e in sorted(items, key=lambda x: x['date'], reverse=True)]

        return jsonify({
            'range': { 'start': start.strftime('%Y-%m-%d'), 'end': end.strftime('%Y-%m-%d') },
            'trend': trend,
            'by_category': cat_breakdown,
            'table': table,
            'insights': insights
        })
    except Exception:
        print('❌ api_analysis error:', traceback.format_exc())
        return jsonify({'error': 'Unable to compute analysis'}), 500

@app.route('/upload', methods=['POST'])
@login_required
def upload_receipt():
    print("🟢 /upload route triggered")

    # Check if the post request has the file part
    if 'file' not in request.files:
        print("❌ No file part in request")
        return jsonify({'success': False, 'error': 'No file part in request'}), 400

    file = request.files['file']
    
    # If user does not select file, browser also submit an empty part without filename
    if file.filename == '':
        print("❌ No selected file")
        return jsonify({'success': False, 'error': 'No selected file'}), 400

    # Validate file type
    filename = secure_filename(file.filename)
    file_ext = os.path.splitext(filename)[1].lower()
    
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.pdf'}
    if file_ext not in allowed_extensions:
        return jsonify({
            'success': False,
            'error': f'Unsupported file type. Please upload: {", ".join(allowed_extensions)}'
        }), 400

    # Create uploads directory if it doesn't exist
    upload_dir = 'uploads'
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)

    # Save the uploaded file
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)
    print(f"📁 File saved to: {filepath}")

    try:
        text = ""
        if file_ext == '.pdf':
            # Process PDF file
            try:
                from pdf2image import convert_from_path
                import tempfile
                
                print("📄 Processing PDF file...")
                with tempfile.TemporaryDirectory() as temp_dir:
                    # Convert PDF to images
                    images = convert_from_path(
                        filepath,
                        output_folder=temp_dir,
                        fmt='jpeg',
                        thread_count=4
                    )
                    
                    # Process each page
                    for i, image in enumerate(images):
                        # Save page as image
                        img_path = os.path.join(temp_dir, f'page_{i+1}.jpg')
                        image.save(img_path, 'JPEG', quality=90)
                        # Extract text from each page
                        page_text = pytesseract.image_to_string(Image.open(img_path))
                        text += f"--- Page {i+1} ---\n{page_text}\n\n"
                        
                    print(f"✅ Processed {len(images)} pages from PDF")
                    
            except Exception as e:
                print(f"❌ PDF processing error: {str(e)}")
                return jsonify({
                    'success': False,
                    'error': f'Failed to process PDF: {str(e)}'
                }), 500
        else:
            # Process image file
            try:
                print("🖼️ Processing image file...")
                text = pytesseract.image_to_string(Image.open(filepath))
            except Exception as e:
                print(f"❌ Image processing error: {str(e)}")
                return jsonify({
                    'success': False,
                    'error': f'Failed to process image: {str(e)}'
                }), 500

        print(f"📝 Extracted text length: {len(text)} characters")
        if text.strip():
            print("📄 Sample extracted text:", text[:200] + "...")
        else:
            print("⚠️ No text was extracted from the file")

        # Process the extracted text
        try:
            amount = extract_total_amount(text)
            category = categorize_expense(text)
            assessment, reason, tips = assess_expense(category, amount, text)
            print(f"✅ Processed - Category: {category}, Amount: {amount}, Assessment: {assessment}")
        except Exception as e:
            print(f"❌ Error processing extracted text: {traceback.format_exc()}")
            return jsonify({
                'success': False,
                'error': f'Failed to process receipt data: {str(e)}'
            }), 500

        # Save to database
        doc = {
            'user': current_user.email,
            'filename': filename,
            'filetype': 'pdf' if file_ext == '.pdf' else 'image',
            'category': category,
            'amount': amount,
            'text': text,
            'date': datetime.now().strftime("%Y-%m-%d %H:%M"),
            'uploaded_at': datetime.now(),
            'file_size': os.path.getsize(filepath),
            'mimetype': file.content_type
        }
        
        try:
            result = expenses_col.insert_one(doc)
            if not result.inserted_id:
                raise Exception("Database insertion failed")
            print(f"💾 Saved to database with ID: {result.inserted_id}")
        except Exception as e:
            print(f"❌ Database error: {str(e)}")
            return jsonify({
                'success': False,
                'error': 'Failed to save to database'
            }), 500

        # Get updated category totals
        try:
            pipeline = [
                {"$match": {"user": current_user.email}},
                {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}},
                {"$sort": {"total": -1}}
            ]
            grouped = list(expenses_col.aggregate(pipeline))
            print(f"📊 Updated category totals: {grouped}")
        except Exception as e:
            print(f"⚠️ Could not get updated totals: {str(e)}")
            grouped = []

        # Save last receipt context in session for interactive Q&A
        try:
            session['last_receipt'] = {
                'category': category,
                'amount': float(amount or 0),
                'assessment': assessment,
                'reason': reason,
                'tips': tips,
                'filename': filename
            }
            print("💾 Saved receipt context to session")
        except Exception as e:
            print(f"⚠️ Could not save to session: {str(e)}")

        return jsonify({
            'success': True,
            'message': 'Receipt processed successfully',
            'data': {
                'category': category,
                'amount': amount,
                'filename': filename,
                'filetype': 'pdf' if file_ext == '.pdf' else 'image',
                'extracted_text': text[:500] + ('...' if len(text) > 500 else '')
            },
            'totals': grouped,
            'assessment': {
                'category': category,
                'amount': amount,
                'label': assessment,
                'reason': reason,
                'tips': tips or "No specific tips available for this category."
            }
        })

    except Exception as e:
        print(f"❌ Unexpected error: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': f'An unexpected error occurred: {str(e)}'
        }), 500
    finally:
        # Clean up the uploaded file
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                print(f"🧹 Cleaned up file: {filepath}")
        except Exception as e:
            print(f"⚠️ Could not clean up file {filepath}: {str(e)}")
            

@app.route('/expenses/add', methods=['POST'])
@login_required
def add_expense_manual():
    try:
        payload = request.get_json(silent=True) or {}
        category = (payload.get('category') or 'Misc').strip() or 'Misc'
        amount = float(payload.get('amount') or 0)
        merchant = (payload.get('merchant') or '').strip()
        note = (payload.get('note') or '').strip()
        
        # Handle date formatting
        date_input = payload.get('date')
        if date_input:
            if 'T' in date_input:  # Handle datetime-local input format
                date_str = date_input.replace('T', ' ')
            else:
                date_str = date_input
        else:
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        date_str = date_str.strip()

        # For analysis helpers, build a simple text blob
        text_blob = "\n".join(filter(None, [merchant, note, f"Category: {category}"]))
        assessment, reason, tips = assess_expense(category, amount, text_blob)

        doc = {
            'user': current_user.email,
            'filename': None,
            'category': category,
            'amount': amount,
            'text': text_blob,
            'date': date_str,
            'merchant': merchant,
            'note': note,
            'created_at': datetime.now()
        }
        
        # Insert the document and get the inserted ID
        result = expenses_col.insert_one(doc)
        
        if not result.inserted_id:
            raise Exception("Failed to insert expense")

        # Get updated category totals
        pipeline = [
            {"$match": {"user": current_user.email}},
            {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}}
        ]
        grouped = list(expenses_col.aggregate(pipeline))

        return jsonify({
            'success': True,
            'message': 'Expense added successfully',
            'data': grouped,
            'assessment': {
                'label': assessment,
                'reason': reason,
                'category': category,
                'amount': amount,
                'tips': TIP_BANK.get(category, tips)
            }
        })
    except Exception as e:
        print('❌ add_expense_manual error:', str(e))
        return jsonify({
            'success': False,
            'error': str(e) or 'Failed to add expense'
        }), 500

@app.route('/expenses/summary')
@login_required
def get_expense_summary():
    try:
        pipeline = [
            {"$match": {"user": current_user.email}},
            {"$group": {
                "_id": "$category",
                "total": {"$sum": "$amount"}
            }},
            {"$sort": {"total": -1}}
        ]
        result = list(expenses_col.aggregate(pipeline))
        
        return jsonify({
            'success': True,
            'categories': [item['_id'] for item in result],
            'totals': [item['total'] for item in result]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/advice', methods=['POST'])
@login_required
def advice():
    try:
        payload = request.get_json(silent=True) or {}
        msg_raw = payload.get('message') or ''
        msg = msg_raw.lower()
        budget = float(payload.get('budget') or 0) if payload.get('budget') else None

        # Get user's financial context
        settings = _get_user_settings(current_user.email)
        grouped = list(expenses_col.aggregate([
            {"$match": {"user": current_user.email}},
            {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}},
            {"$sort": {"total": -1}}
        ]))
        top_cat_doc = grouped[0] if grouped else None
        top_cat = top_cat_doc["_id"] if top_cat_doc else None

        # Check for specific intents that should use rule-based responses
        use_llm = True
        reply = None
        
        # Rule-based responses for specific intents
        import re as _re
        
        # Budget setting
        m_budget = _re.search(r"(set|update)\s+(?:my\s+)?budget\s+(?:to\s+)?(?:₹|rs\.?\s*)?(\d+(?:,\d{3})*)", msg, _re.IGNORECASE)
        if m_budget:
            val = float(m_budget.group(2).replace(',', ''))
            reply = f"Noted your target of ₹{val:.0f}. To update your budget, use the Set Budget button above."
            use_llm = False
        
        # Tax-related queries
        elif any(term in msg for term in ["tax", "80c", "income tax", "hra", "nps"]):
            lines = ["India tax‑saving checklist:"]
            for t in TAX_TIPS_INDIA[:8]:
                lines.append(f"- {t}")
            regime_hint = "If you use the Old Regime, these deductions apply; the New Regime has lower rates but fewer deductions."
            lines.append(f"- {regime_hint}")
            lines.append("Would you like me to draft a sample plan across 80C/80D/NPS based on your budget?")
            reply = "\n".join(lines)
            use_llm = False
        
        # Last receipt details
        elif "receipt" in msg or "bill" in msg:
            last = expenses_col.find_one({"user": current_user.email}, sort=[("_id", -1)])
            if last:
                a_lbl, a_reason, a_tips = assess_expense(last.get('category'), float(last.get('amount') or 0), last.get('text') or '')
                bullets = "\n".join([f"- {t}" for t in (a_tips or [])[:3]])
                reply = "\n".join([
                    f"Last receipt: {last.get('category')} · ₹{float(last.get('amount') or 0):.0f} — {a_lbl}.",
                    a_reason or "",
                    bullets or ""
                ]).strip()
                use_llm = False

        # If no rule-based response, use LLM
        if use_llm and reply is None:
            try:
                # Generate response using LLM
                reply = generate_llm_response(msg_raw, current_user.email)
                
                # If LLM fails, fall back to basic response
                if not reply or "error" in reply.lower() or "trouble" in reply.lower():
                    reply = "I'm here to help with your finances. You can ask me about your spending, set budgets, or get savings tips."
            except Exception as e:
                print(f"LLM generation error: {e}")
                reply = "I'm having trouble generating a response. Please try again later."
        
        # Fallback if both rule-based and LLM failed
        if not reply:
            reply = "I'm not sure how to respond to that. Could you rephrase or ask about your expenses, budget, or savings?"

        # Save conversation to history
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        try:
            chats_col.insert_many([
                {"user": current_user.email, "role": "user", "text": msg_raw, "date": now},
                {"user": current_user.email, "role": "ai", "text": reply, "date": now}
            ])
        except Exception as e:
            print("❌ Chat save error:", str(e))

        return jsonify({'reply': reply})
        
    except Exception as e:
        print("❌ Advice error:", str(e))
        return jsonify({'error': 'An error occurred while processing your request'}), 500
        return jsonify({'error': 'Unable to generate advice right now.'}), 500

@app.route('/advice/history', methods=['GET'])
@login_required
def advice_history():
    try:
        cursor = chats_col.find({"user": current_user.email}).sort("date", 1)
        msgs = [{"role": x.get("role"), "text": x.get("text"), "date": x.get("date")} for x in cursor]
        # Return only the last 50 messages
        msgs = msgs[-50:]
        return jsonify({"messages": msgs})
    except Exception:
        print("❌ History fetch error:", traceback.format_exc())
        return jsonify({"messages": []})

@app.route('/export/analysis.pdf', methods=['GET'])
@login_required
def export_analysis_pdf():
    try:
        # Fetch grouped totals
        grouped = list(expenses_col.aggregate([
            {"$match": {"user": current_user.email}},
            {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}},
            {"$sort": {"total": -1}}
        ]))

        # Last assessment from session
        last_ctx = session.get('last_receipt') or {}
        settings = _get_user_settings(current_user.email)

        buf = io.BytesIO()
        c = _pdf_canvas.Canvas(buf, pagesize=A4)
        width, height = A4
        x_margin = 20 * mm
        y = height - 25 * mm

        def line(txt, dy=8*mm, size=12, bold=False):
            nonlocal y
            c.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
            c.drawString(x_margin, y, str(txt))
            y -= dy

        # Title
        line('AI-Expenses Tracker — Analysis', size=16, bold=True)
        line(f'User: {current_user.email}', dy=6*mm)
        line('')

        # Budget/caps
        mb = settings.get('monthly_budget')
        if mb:
            line(f'Monthly Budget: ₹{float(mb):.0f}', dy=6*mm)
        caps = settings.get('caps') or {}
        if caps:
            line('Category Caps:', bold=True)
            for k, v in caps.items():
                line(f'- {k}: ₹{float(v or 0):.0f}', dy=6*mm)
            line('')

        # Summary
        line('Summary by Category:', bold=True)
        if grouped:
            for x in grouped:
                line(f"- {x.get('_id')}: ₹{float(x.get('total') or 0):.0f}", dy=6*mm)
        else:
            line('- No expenses yet', dy=6*mm)
        line('')

        # Last assessment
        if last_ctx:
            line('Last Receipt Assessment:', bold=True)
            line(f"- Category: {last_ctx.get('category')} · Amount: ₹{float(last_ctx.get('amount') or 0):.0f}", dy=6*mm)
            line(f"- Label: {last_ctx.get('assessment')} — {last_ctx.get('reason') or ''}", dy=6*mm)
            tips = last_ctx.get('tips') or []
            if tips:
                line('- Tips:', dy=6*mm)
                for t in tips[:5]:
                    line(f"  • {t}", dy=6*mm)

        c.showPage()
        c.save()
        pdf = buf.getvalue()
        buf.close()

        resp = make_response(pdf)
        resp.headers['Content-Type'] = 'application/pdf'
        resp.headers['Content-Disposition'] = 'attachment; filename=analysis.pdf'
        return resp
    except Exception:
        print('❌ Export PDF error:', traceback.format_exc())
        return ('', 500)

@app.route('/settings/budget', methods=['POST'])
@login_required
def set_budget():
    try:
        payload = request.get_json(silent=True) or request.form or {}
        raw = payload.get('budget')
        if raw is None or str(raw).strip() == '':
            return jsonify({'error': 'Missing budget value'}), 400
        try:
            val = float(str(raw).replace(',', '').strip())
        except Exception:
            return jsonify({'error': 'Invalid budget value'}), 400
        if val < 0:
            return jsonify({'error': 'Budget must be non-negative'}), 400

        settings = _get_user_settings(current_user.email)
        settings['monthly_budget'] = val
        _save_user_settings(current_user.email, settings)

        return jsonify({'message': 'Monthly budget updated', 'budget': val})
    except Exception:
        print('❌ Set budget error:', traceback.format_exc())
        return jsonify({'error': 'Failed to update budget'}), 500

@app.route('/clear_data', methods=['POST'])
@login_required
def clear_data():
    try:
        e_res = expenses_col.delete_many({"user": current_user.email})
        c_res = chats_col.delete_many({"user": current_user.email})
        return jsonify({
            "deleted_expenses": getattr(e_res, 'deleted_count', 0),
            "deleted_chats": getattr(c_res, 'deleted_count', 0),
            "message": "Your data has been cleared."
        })
    except Exception:
        print("❌ Clear data error:", traceback.format_exc())
        return jsonify({"error": "Failed to clear data"}), 500

@app.route('/delete_last', methods=['POST'])
@login_required
def delete_last():
    try:
        last = expenses_col.find_one({"user": current_user.email}, sort=[("_id", -1)])
        if not last:
            return jsonify({"message": "No expenses to delete.", "data": []})

        expenses_col.delete_one({"_id": last["_id"]})

        pipeline = [
            {"$match": {"user": current_user.email}},
            {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}}
        ]
        grouped = list(expenses_col.aggregate(pipeline))
        return jsonify({
            "message": "Last expense deleted.",
            "deleted": {
                "category": last.get("category"),
                "amount": last.get("amount"),
                "date": last.get("date"),
                "filename": last.get("filename")
            },
            "data": grouped
        })
    except Exception:
        print("❌ Delete last error:", traceback.format_exc())
        return jsonify({"error": "Failed to delete last expense"}), 500


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    return render_template('admin.html', user=current_user.username or current_user.email)

@app.route('/api/admin/updates', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_updates():
    if request.method == 'POST':
        data = request.get_json()
        title = data.get('title')
        content = data.get('content')
        
        if not title or not content:
            return jsonify({'error': 'Title and content are required'}), 400
            
        update_ref = db.collection(UPDATES_COLLECTION).document()
        update_ref.set({
            'title': title,
            'content': content,
            'created_at': firestore.SERVER_TIMESTAMP,
            'created_by': current_user.email,
            'is_active': True
        })
        
        return jsonify({'id': update_ref.id, 'message': 'Update created successfully'}), 201
    
    # GET request - list all updates
    updates_ref = db.collection(UPDATES_COLLECTION).order_by('created_at', direction='DESCENDING').stream()
    updates = [{'id': doc.id, **doc.to_dict()} for doc in updates_ref]
    
    # Convert Firestore timestamps to strings
    for update in updates:
        if 'created_at' in update and hasattr(update['created_at'], 'isoformat'):
            update['created_at'] = update['created_at'].isoformat()
    
    return jsonify(updates)

@app.route('/api/admin/updates/<update_id>', methods=['PUT', 'DELETE'])
@login_required
@admin_required
def manage_update(update_id):
    update_ref = db.collection(UPDATES_COLLECTION).document(update_id)
    update_doc = update_ref.get()
    
    if not update_doc.exists:
        return jsonify({'error': 'Update not found'}), 404
    
    if request.method == 'PUT':
        data = request.get_json()
        title = data.get('title')
        content = data.get('content')
        
        if not title or not content:
            return jsonify({'error': 'Title and content are required'}), 400
            
        update_ref.update({
            'title': title,
            'content': content,
            'updated_at': firestore.SERVER_TIMESTAMP
        })
        
        return jsonify({'message': 'Update updated successfully'})
    
    elif request.method == 'DELETE':
        update_ref.delete()
        return jsonify({'message': 'Update deleted successfully'})

@app.route('/api/admin/faqs', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_faqs():
    if request.method == 'POST':
        data = request.get_json()
        question = data.get('question')
        answer = data.get('answer')
        
        if not question or not answer:
            return jsonify({'error': 'Question and answer are required'}), 400
            
        # Get the highest order number
        last_faq = db.collection(FAQ_COLLECTION).order_by('order', direction='DESCENDING').limit(1).get()
        next_order = 1
        if last_faq and len(last_faq) > 0:
            next_order = last_faq[0].to_dict().get('order', 0) + 1
            
        faq_ref = db.collection(FAQ_COLLECTION).document()
        faq_ref.set({
            'question': question,
            'answer': answer,
            'order': next_order,
            'created_at': firestore.SERVER_TIMESTAMP,
            'created_by': current_user.email,
            'is_active': True
        })
        
        return jsonify({'id': faq_ref.id, 'message': 'FAQ created successfully'}), 201
    
    # GET request - list all FAQs
    faqs_ref = db.collection(FAQ_COLLECTION).order_by('order').stream()
    faqs = [{'id': doc.id, **doc.to_dict()} for doc in faqs_ref]
    
    # Convert Firestore timestamps to strings
    for faq in faqs:
        if 'created_at' in faq and hasattr(faq['created_at'], 'isoformat'):
            faq['created_at'] = faq['created_at'].isoformat()
    
    return jsonify(faqs)

@app.route('/api/admin/faqs/<faq_id>', methods=['PUT', 'DELETE'])
@login_required
@admin_required
def manage_faq(faq_id):
    faq_ref = db.collection(FAQ_COLLECTION).document(faq_id)
    faq_doc = faq_ref.get()
    
    if not faq_doc.exists:
        return jsonify({'error': 'FAQ not found'}), 404
    
    if request.method == 'PUT':
        data = request.get_json()
        question = data.get('question')
        answer = data.get('answer')
        
        if not question or not answer:
            return jsonify({'error': 'Question and answer are required'}), 400
            
        faq_ref.update({
            'question': question,
            'answer': answer,
            'updated_at': firestore.SERVER_TIMESTAMP
        })
        
        return jsonify({'message': 'FAQ updated successfully'})
    
    elif request.method == 'DELETE':
        faq_ref.delete()
        return jsonify({'message': 'FAQ deleted successfully'})

@app.route('/api/admin/faqs/reorder', methods=['POST'])
@login_required
@admin_required
def reorder_faqs():
    data = request.get_json()
    updates = data.get('updates')
    
    if not updates or not isinstance(updates, list):
        return jsonify({'error': 'Invalid update data'}), 400
    
    batch = db.batch()
    
    for update in updates:
        if not update.get('id') or not isinstance(update.get('order'), int):
            continue
            
        faq_ref = db.collection(FAQ_COLLECTION).document(update['id'])
        batch.update(faq_ref, {
            'order': update['order'],
            'updated_at': firestore.SERVER_TIMESTAMP
        })
    
    try:
        batch.commit()
        return jsonify({'message': 'FAQs reordered successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.after_request
def add_header(response):
    # Ensure JavaScript files are served with the correct MIME type
    if response.mimetype == 'application/javascript':
        response.headers['Content-Type'] = 'application/javascript'
    return response

@app.route('/api/announcements', methods=['GET', 'OPTIONS'])
@login_required
def get_announcements():
    """Fetch recent announcements"""
    if request.method == 'OPTIONS':
        # Handle preflight request
        response = make_response()
        response.headers.add('Access-Control-Allow-Origin', request.headers.get('Origin', '*'))
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET, OPTIONS')
        return response
        
    try:
        # Get the Firestore client from firestore_utils
        from firestore_utils import db
        
        # Query the updates_and_announcements collection
        announcements_ref = db.collection('updates_and_announcements')
        
        # Get all documents and process them
        announcements = announcements_ref.stream()
        
        # Convert to list of dicts
        result = []
        for ann in announcements:
            data = ann.to_dict()
            data['id'] = ann.id
            
            # Skip the _initial document
            if data.get('id') == '_initial':
                continue
                
            # Convert Firestore timestamp to string if it exists
            if 'created_at' in data and hasattr(data['created_at'], 'isoformat'):
                data['created_at'] = data['created_at'].isoformat()
                
            result.append(data)
        
        # Sort by created_at in descending order and limit to 5
        result = sorted(result, 
                       key=lambda x: x.get('created_at', ''), 
                       reverse=True)[:5]
        
        response = jsonify(result)
        response.headers.add('Access-Control-Allow-Origin', request.headers.get('Origin', '*'))
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response
        
    except Exception as e:
        print(f"Error fetching announcements: {str(e)}")
        import traceback
        traceback.print_exc()
        response = jsonify({
            "error": "Failed to fetch announcements",
            "details": str(e)
        })
        response.status_code = 500
        response.headers.add('Access-Control-Allow-Origin', request.headers.get('Origin', '*'))
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response

@app.route('/api/faqs', methods=['GET', 'OPTIONS'])
@login_required
def get_faqs():
    """Fetch all FAQs in order"""
    if request.method == 'OPTIONS':
        # Handle preflight request
        response = make_response()
        response.headers.add('Access-Control-Allow-Origin', request.headers.get('Origin', '*'))
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET, OPTIONS')
        return response
        
    try:
        # Get the Firestore client from firestore_utils
        from firestore_utils import db
        
        # Query the faq_content collection
        faqs_ref = db.collection('faq_content')
        
        # Get all documents and process them
        faqs = faqs_ref.stream()
        
        # Convert to list of dicts
        result = []
        for faq in faqs:
            data = faq.to_dict()
            data['id'] = faq.id
            
            # Skip the _initial document
            if data.get('id') == '_initial':
                continue
                
            result.append(data)
        
        # Sort by order field if it exists
        result = sorted(result, key=lambda x: x.get('order', 0))
        
        response = jsonify(result)
        response.headers.add('Access-Control-Allow-Origin', request.headers.get('Origin', '*'))
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response
        
    except Exception as e:
        print(f"Error fetching FAQs: {str(e)}")
        import traceback
        traceback.print_exc()
        response = jsonify({
            "error": "Failed to fetch FAQs",
            "details": str(e)
        })
        response.status_code = 500
        response.headers.add('Access-Control-Allow-Origin', request.headers.get('Origin', '*'))
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response

if __name__ == '__main__':
    app.run(debug=True, port=5001, host='0.0.0.0')
