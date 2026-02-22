from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import re
import io
import os  # ✅ Added for Render port handling
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
import secrets
import string

app = Flask(__name__)
CORS(app, origins=["https://cybglo.onrender.com"])

# ✅ Root endpoint for Render health check
@app.route("/")
def home():
    return "Welcome to CYBGLO API"

# Connect to MongoDB Atlas
client = MongoClient("mongodb+srv://harshavardhansss567:MJTq6vqF6H5dZcQY@cluster0.b1drhgu.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0") 
db = client["cybglo"]
users = db["users"]
reset_tokens = db["reset_tokens"]  # New collection for password reset tokens. update this code if the 

# Validation functions
def is_valid_email(email):
    return re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email)

def is_valid_password(password):
    return len(password) >= 6

def generate_reset_token():
    """Generate a secure random token for password reset"""
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))

# Routes
@app.route("/signup", methods=["POST"])
def signup():
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    city = data.get("city", "").strip()
    country = data.get("country", "").strip()
    
    if not (email and password and city and country):
        return jsonify({"message": "All fields are required"}), 400
    
    if not is_valid_email(email):
        return jsonify({"message": "Invalid email format"}), 400
    
    if not is_valid_password(password):
        return jsonify({"message": "Password must be at least 6 characters"}), 400
    
    if users.find_one({"email": email}):
        return jsonify({"message": "Email already exists"}), 409
    
    hashed = generate_password_hash(password)
    users.insert_one({
        "email": email,
        "password": hashed,
        "city": city,
        "country": country,
        "created_at": datetime.utcnow()
    })
    
    return jsonify({"message": "Signup successful"}), 201

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    
    if not (email and password):
        return jsonify({"message": "Email and password are required"}), 400
    
    user = users.find_one({"email": email})
    if user and check_password_hash(user["password"], password):
        return jsonify({
            "message": "Login successful", 
            "email": email,
            "city": user.get("city"),
            "country": user.get("country")
        }), 200
    
    return jsonify({"message": "Invalid credentials"}), 401

@app.route("/forgot-password", methods=["POST"])
def forgot_password():
    """Step 1: Request password reset - generates token"""
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    
    if not email:
        return jsonify({"message": "Email is required"}), 400
    
    if not is_valid_email(email):
        return jsonify({"message": "Invalid email format"}), 400
    
    user = users.find_one({"email": email})
    if not user:
        # For security, don't reveal if email exists or not
        return jsonify({"message": "If the email exists, a reset token has been sent"}), 200
    
    # Generate reset token
    token = generate_reset_token()
    
    # Store token in database (expires in 1 hour)
    reset_tokens.insert_one({
        "email": email,
        "token": token,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow().timestamp() + 3600  # 1 hour
    })
    
    # In a real application, you would send this token via email
    # For now, we'll return it in the response (remove this in production)
    return jsonify({
        "message": "Reset token generated",
        "token": token  # Remove this line in production
    }), 200

@app.route("/reset-password", methods=["POST"])
def reset_password_direct():
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    new_password = data.get("newPassword", "").strip()

    if not (email and new_password):
        return jsonify({"message": "Email and new password are required"}), 400

    if not is_valid_email(email):
        return jsonify({"message": "Invalid email format"}), 400

    if not is_valid_password(new_password):
        return jsonify({"message": "Password must be at least 6 characters"}), 400

    user = users.find_one({"email": email})
    if not user:
        return jsonify({"message": "User not found"}), 404

    users.update_one(
        {"email": email},
        {"$set": {"password": generate_password_hash(new_password)}}
    )

    return jsonify({"message": "Password reset successful"}), 200

@app.route("/generate-report", methods=["POST"])
def generate_report():
    """Generate PDF report for a specific section"""
    data = request.get_json()
    section = data.get("section")
    email = data.get("email")
    
    if not (section and email):
        return jsonify({"message": "Section and email are required"}), 400
    
    # Verify user exists
    user = users.find_one({"email": email})
    if not user:
        return jsonify({"message": "User not found"}), 404
    
    try:
        # Create PDF in memory
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        title = Paragraph(f"CybGlo Report - {section.title()}", styles['Title'])
        story.append(title)
        story.append(Spacer(1, 12))
        
        # User info
        user_info = Paragraph(f"Generated for: {email}", styles['Normal'])
        story.append(user_info)
        
        date_info = Paragraph(f"Generated on: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC", styles['Normal'])
        story.append(date_info)
        story.append(Spacer(1, 20))
        
        # Section content (customize based on your sections)
        section_content = get_section_content(section)
        for paragraph in section_content:
            story.append(Paragraph(paragraph, styles['Normal']))
            story.append(Spacer(1, 12))
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        
        # Log the download
        print(f"[PDF Generated] {email} generated {section} report at {datetime.utcnow()}")
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"{section}_report_{datetime.utcnow().strftime('%Y%m%d')}.pdf",
            mimetype='application/pdf'
        )
        
    except Exception as e:
        print(f"Error generating PDF: {str(e)}")
        return jsonify({"message": "Error generating report"}), 500

def get_section_content(section):
    """Get content for different sections - customize this based on your needs"""
    content_map = {
        "cybersecurity": [
            "Cybersecurity Overview",
            "This section covers essential cybersecurity practices and guidelines.",
            "Key topics include network security, data protection, and threat assessment.",
            "Regular security audits and updates are crucial for maintaining system integrity."
        ],
        "privacy": [
            "Privacy Protection Guidelines",
            "Understanding data privacy laws and regulations.",
            "Best practices for handling personal and sensitive information.",
            "Compliance requirements and implementation strategies."
        ],
        "compliance": [
            "Regulatory Compliance Framework",
            "Overview of relevant compliance standards and requirements.",
            "Implementation guidelines and audit procedures.",
            "Documentation and reporting requirements."
        ],
        "incident_response": [
            "Incident Response Procedures",
            "Step-by-step guide for handling security incidents.",
            "Communication protocols and escalation procedures.",
            "Post-incident analysis and improvement processes."
        ]
    }
    
    return content_map.get(section.lower(), [
        f"{section.title()} Section",
        f"Content for {section} section would be displayed here.",
        "This is a sample report generated by the CybGlo system.",
        "Contact your administrator for more detailed information."
    ])

@app.route("/user-profile", methods=["GET"])
def get_user_profile():
    """Get user profile information"""
    email = request.args.get("email")
    
    if not email:
        return jsonify({"message": "Email parameter is required"}), 400
    
    user = users.find_one({"email": email}, {"password": 0})  # Exclude password
    if not user:
        return jsonify({"message": "User not found"}), 404
    
    # Convert ObjectId to string for JSON serialization
    user["_id"] = str(user["_id"])
    user["created_at"] = user["created_at"].isoformat()
    
    return jsonify(user), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
