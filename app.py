import streamlit as st

# ============================================================================
# PAGE CONFIGURATION - MUST BE FIRST STREAMLIT COMMAND
# ============================================================================
st.set_page_config(
    page_title="DAV Project Form",
    page_icon="🎓",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ============================================================================
# IMPORTS
# ============================================================================
import re
from firebase_admin import credentials, firestore, initialize_app
import firebase_admin
from typing import Dict, Optional, Tuple
import json
import time
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ============================================================================
# FIREBASE INITIALIZATION
# ============================================================================

@st.cache_resource
def init_firebase():
    """
    Initialize Firebase and return the Firestore client.
    Prioritizes Streamlit secrets, then falls back to environment variables.
    """
    if not firebase_admin._apps:
        try:
            # Try Streamlit secrets first (recommended for Streamlit Cloud)
            if hasattr(st, 'secrets') and 'firebase' in st.secrets:
                fb_creds = st.secrets["firebase"]
                private_key = fb_creds["private_key"].replace("\\n", "\n")
                
                cred_dict = {
                    "type": fb_creds["type"],
                    "project_id": fb_creds["project_id"],
                    "private_key_id": fb_creds["private_key_id"],
                    "private_key": private_key,
                    "client_email": fb_creds["client_email"],
                    "client_id": fb_creds["client_id"],
                    "auth_uri": fb_creds.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
                    "token_uri": fb_creds.get("token_uri", "https://oauth2.googleapis.com/token"),
                    "auth_provider_x509_cert_url": fb_creds.get("auth_provider_x509_cert_url", "https://www.googleapis.com/oauth2/v1/certs"),
                    "client_x509_cert_url": fb_creds["client_x509_cert_url"]
                }
            else:
                # Fall back to environment variables
                private_key = os.getenv("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n")
                
                cred_dict = {
                    "type": os.getenv("FIREBASE_TYPE", "service_account"),
                    "project_id": os.getenv("FIREBASE_PROJECT_ID"),
                    "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
                    "private_key": private_key,
                    "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
                    "client_id": os.getenv("FIREBASE_CLIENT_ID"),
                    "auth_uri": os.getenv("FIREBASE_AUTH_URI", "https://accounts.google.com/o/oauth2/auth"),
                    "token_uri": os.getenv("FIREBASE_TOKEN_URI", "https://oauth2.googleapis.com/token"),
                    "auth_provider_x509_cert_url": os.getenv("FIREBASE_AUTH_PROVIDER_X509_CERT_URL", "https://www.googleapis.com/oauth2/v1/certs"),
                    "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_X509_CERT_URL")
                }
            
            # Validate required fields
            if not cred_dict.get("project_id") or not cred_dict.get("private_key"):
                raise ValueError("Missing required Firebase credentials. Please configure secrets in Streamlit Cloud.")
            
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            
        except Exception as e:
            st.error(f"❌ Firebase initialization failed: {str(e)}")
            st.info("Please configure Firebase credentials in Streamlit Cloud secrets.")
            st.stop()
    
    return firestore.client()

# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

def validate_email(email: str) -> Tuple[bool, str]:
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not email:
        return False, "Email ID is required"
    if not re.match(pattern, email):
        return False, "Invalid email format (e.g., user@example.com)"
    return True, ""

def validate_enrollment(enrollment: str) -> Tuple[bool, str]:
    pattern = r'^\d{12}$'
    if not enrollment:
        return False, "Enrollment Number is required"
    if not re.match(pattern, enrollment):
        return False, "Enrollment Number must be exactly 12 digits"
    return True, ""

def validate_name(name: str) -> Tuple[bool, str]:
    pattern = r'^[a-zA-Z\s]+$'
    if not name:
        return False, "Full Name is required"
    if not re.match(pattern, name.strip()):
        return False, "Full Name can only contain letters and spaces"
    return True, ""

def validate_contact(contact: str) -> Tuple[bool, str]:
    pattern = r'^\d{10}$'
    if not contact:
        return False, "Contact Number is required"
    if not re.match(pattern, contact):
        return False, "Contact Number must be exactly 10 digits"
    return True, ""

def validate_project_name(project_name: str) -> Tuple[bool, str]:
    if not project_name:
        return False, "Project Name is required"
    if len(project_name.strip()) < 3:
        return False, "Project Name must be at least 3 characters"
    return True, ""

def validate_url(url: str) -> Tuple[bool, str]:
    pattern = r'^https?://[^\s/$.?#].[^\s]*$'
    if not url:
        return False, "Source URL is required"
    if not re.match(pattern, url, re.IGNORECASE):
        return False, "URL must start with http:// or https://"
    return True, ""

# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

def save_submission(db, data: Dict) -> Tuple[bool, str]:
    try:
        # Use Enrollment Number as the Document ID
        doc_ref = db.collection('project_submissions').document(data['enrollment_number'])
        
        # 'create' fails if the document already exists (atomic check)
        doc_ref.create(data) 
        return True, ""
        
    except Exception as e:
        # Check if error is due to document already existing
        if "409" in str(e) or "already exists" in str(e).lower():
            return False, "This Enrollment Number has already been submitted."
        return False, f"Database error: {str(e)}"

def send_confirmation_email(recipient_email: str, full_name: str, project_name: str) -> bool:
    """
    Send confirmation email optimized for Streamlit Cloud
    """
    try:
        # Get email credentials from Streamlit secrets or environment variables
        if hasattr(st, 'secrets') and 'email' in st.secrets:
            sender_email = st.secrets["email"]["sender"]
            sender_password = st.secrets["email"]["password"]
            smtp_server = st.secrets["email"].get("smtp_server", "smtp.gmail.com")
            smtp_port = int(st.secrets["email"].get("smtp_port", 587))
        else:
            sender_email = os.getenv("EMAIL_SENDER")
            sender_password = os.getenv("EMAIL_PASSWORD")
            smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
            smtp_port = int(os.getenv("SMTP_PORT", "587"))
        
        # Check if credentials exist
        if not sender_email or not sender_password:
            print("⚠️ Email credentials not configured")
            return False
        
        # Create email message
        message = MIMEMultipart("alternative")
        message["Subject"] = "🎉 Project Submission Confirmation - DAV Subject"
        message["From"] = sender_email
        message["To"] = recipient_email
        
        # Email body
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                    border-radius: 10px 10px 0 0;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 28px;
                }}
                .content {{
                    background: #ffffff;
                    padding: 30px;
                    border: 1px solid #e0e0e0;
                }}
                .info-box {{
                    background: #f8f9fa;
                    border-left: 4px solid #667eea;
                    padding: 15px;
                    margin: 20px 0;
                    border-radius: 4px;
                }}
                .info-box strong {{
                    color: #667eea;
                }}
                .footer {{
                    background: #f8f9fa;
                    padding: 20px;
                    text-align: center;
                    border-radius: 0 0 10px 10px;
                    border: 1px solid #e0e0e0;
                    border-top: none;
                }}
                .checkmark {{
                    font-size: 48px;
                    color: #28a745;
                    margin: 20px 0;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <div class="checkmark">✅</div>
                <h1>Submission Successful!</h1>
            </div>
            
            <div class="content">
                <p>Dear <strong>{full_name}</strong>,</p>
                
                <p>Your project has been successfully submitted! We have received your submission and it's now under review.</p>
                
                <div class="info-box">
                    <strong>📁 Project Name:</strong> {project_name}<br>
                    <strong>📧 Email:</strong> {recipient_email}
                </div>
                
                <p><strong>What happens next?</strong></p>
                <ul>
                    <li>Our team will review your project submission</li>
                    <li>You'll receive updates via this email address</li>
                    <li>Keep an eye on your inbox for further communications</li>
                </ul>
                
                <p>Thank you for your submission!</p>
            </div>
            
            <div class="footer">
                <p style="margin: 0; color: #666;">This is an automated confirmation email.</p>
                <p style="margin: 5px 0 0 0; color: #999; font-size: 12px;">
                    DAV Project Submission System
                </p>
            </div>
        </body>
        </html>
        """
        
        # Attach HTML content
        html_part = MIMEText(html_body, "html")
        message.attach(html_part)
        
        # Send email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(message)
        
        return True
        
    except Exception as e:
        print(f"Email error: {str(e)}")
        return False

# ============================================================================
# CUSTOM CSS
# ============================================================================

def apply_custom_css():
    st.markdown("""
    <style>
        /* Form styling */
        .stForm {
            background: white;
            padding: 2rem;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        /* Input labels */
        .input-label {
            font-weight: 600;
            color: #1f2937;
            margin-bottom: 0.5rem;
            display: block;
            font-size: 0.95rem;
        }
        
        .required {
            color: #ef4444;
            margin-left: 2px;
        }
        
        /* Section headers */
        .section-header {
            font-size: 1.25rem;
            font-weight: 700;
            color: #1f2937;
            margin-bottom: 1.5rem;
            padding-bottom: 0.5rem;
            border-bottom: 2px solid #e5e7eb;
        }
        
        /* Success card */
        .success-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 2rem;
            border-radius: 15px;
            text-align: center;
            margin: 2rem 0;
        }
        
        .success-card h2 {
            margin: 1rem 0;
            font-size: 2rem;
        }
        
        .info-grid {
            background: rgba(255,255,255,0.1);
            padding: 1.5rem;
            border-radius: 10px;
            margin: 1.5rem 0;
            text-align: left;
        }
        
        .info-item {
            margin: 0.75rem 0;
            padding: 0.5rem 0;
            border-bottom: 1px solid rgba(255,255,255,0.2);
        }
        
        .info-item:last-child {
            border-bottom: none;
        }
        
        /* Buttons */
        .stButton>button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            font-weight: 600;
            border: none;
            padding: 0.75rem 2rem;
            border-radius: 8px;
            transition: all 0.3s ease;
        }
        
        .stButton>button:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }
    </style>
    """, unsafe_allow_html=True)

# ============================================================================
# SESSION STATE INITIALIZATION
# ============================================================================

def init_session_state():
    if 'submission_complete' not in st.session_state:
        st.session_state.submission_complete = False
    if 'submitted_data' not in st.session_state:
        st.session_state.submitted_data = None
    if 'is_submitting' not in st.session_state:
        st.session_state.is_submitting = False
    if 'last_submission_time' not in st.session_state:
        st.session_state.last_submission_time = 0

# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    apply_custom_css()
    init_session_state()
    
    # Initialize Firebase
    try:
        db = init_firebase()
    except Exception as e:
        st.error("Unable to connect to database. Please try again later.")
        return
    
    # Show success page if submission is complete
    if st.session_state.submission_complete and st.session_state.submitted_data:
        data = st.session_state.submitted_data
        
        st.markdown(f"""
        <div class="success-card">
            <div style="font-size: 4rem;">✅</div>
            <h2>Submission Successful!</h2>
            <p style="font-size: 1.1rem; margin: 1rem 0;">
                Your project has been submitted successfully.
            </p>
            
            <div class="info-grid">
                <div class="info-item">
                    <strong>📧 Email:</strong> {data['email']}
                </div>
                <div class="info-item">
                    <strong>🎓 Enrollment:</strong> {data['enrollment_number']}
                </div>
                <div class="info-item">
                    <strong>👤 Name:</strong> {data['full_name']}
                </div>
                <div class="info-item">
                    <strong>📱 Contact:</strong> {data['contact_number']}
                </div>
                <div class="info-item">
                    <strong>📁 Project:</strong> {data['project_name']}
                </div>
                <div class="info-item">
                    <strong>🔗 URL:</strong> {data['source_url']}
                </div>
            </div>
            
            <p style="margin-top: 1.5rem; font-size: 0.95rem;">
                A confirmation email has been sent to <strong>{data['email']}</strong>
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("✨ Submit Another Project", use_container_width=True):
            st.session_state.submission_complete = False
            st.session_state.submitted_data = None
            st.session_state.is_submitting = False
            st.rerun()
        return
    
    # Display form
    st.title("🎓 DAV Project Form")
    st.markdown("### Submit your project details below")
    st.markdown("Please fill Original Email ID for Getting Confirmation Email after Submission.")
    st.markdown("---")
    
    with st.form("project_submission_form", clear_on_submit=True):
        # Personal Information Section
        st.markdown('<div class="section-header">📋 Personal Information</div>', unsafe_allow_html=True)
        
        st.markdown('<label class="input-label">Email ID <span class="required">*</span></label>', unsafe_allow_html=True)
        email = st.text_input(
            "email_input",
            placeholder="student@university.edu",
            help="Your university email address",
            label_visibility="collapsed"
        )
        
        st.markdown('<label class="input-label">Enrollment Number <span class="required">*</span></label>', unsafe_allow_html=True)
        enrollment = st.text_input(
            "enrollment_input",
            placeholder="123456789012",
            max_chars=12,
            help="12-digit enrollment number",
            label_visibility="collapsed"
        )
        
        st.markdown('<label class="input-label">Full Name <span class="required">*</span></label>', unsafe_allow_html=True)
        full_name = st.text_input(
            "name_input",
            placeholder="Your Full Name",
            help="Your complete name as per university records",
            label_visibility="collapsed"
        )
        
        st.markdown('<label class="input-label">Contact Number <span class="required">*</span></label>', unsafe_allow_html=True)
        contact = st.text_input(
            "contact_input",
            placeholder="9876543210",
            max_chars=10,
            help="10-digit mobile number",
            label_visibility="collapsed"
        )
        
        st.markdown("---")
        
        # Project Details Section
        st.markdown('<div class="section-header">💻 Project Details</div>', unsafe_allow_html=True)
        
        st.markdown('<label class="input-label">Project Name <span class="required">*</span></label>', unsafe_allow_html=True)
        project_name = st.text_input(
            "project_input",
            placeholder="Project Name",
            help="Descriptive name for your project (minimum 3 characters)",
            label_visibility="collapsed"
        )
        
        st.markdown('<label class="input-label">Source URL <span class="required">*</span></label>', unsafe_allow_html=True)
        source_url = st.text_input(
            "url_input",
            placeholder="https://xyz.com/project-name",
            help="GitHub, GitLab, or other repository link",
            label_visibility="collapsed"
        )
        
        st.markdown("---")
        
        # Submit Button
        submitted = st.form_submit_button(
            "🚀 Submit Project",
            use_container_width=True,
            disabled=st.session_state.is_submitting
        )
        
        if submitted:
            # Prevent rapid double-clicks
            current_time = time.time()
            if current_time - st.session_state.last_submission_time < 3:
                st.warning("⏳ Please wait a moment before submitting again.")
                st.stop()
            
            # Set submitting state immediately
            st.session_state.is_submitting = True
            st.session_state.last_submission_time = current_time
            
            with st.spinner("🔄 Processing your submission... Please wait."):
                # Validation
                validations = [
                    validate_email(email),
                    validate_enrollment(enrollment),
                    validate_name(full_name),
                    validate_contact(contact),
                    validate_project_name(project_name),
                    validate_url(source_url)
                ]
                
                all_valid = all(valid for valid, _ in validations)
                
                if not all_valid:
                    st.error("❌ Please correct the following errors:")
                    for valid, error_msg in validations:
                        if not valid and error_msg:
                            st.warning(f"• {error_msg}")
                    st.session_state.is_submitting = False
                else:
                    # Prepare submission data
                    submission_data = {
                        'email': email.strip().lower(),
                        'enrollment_number': enrollment.strip(),
                        'full_name': full_name.strip(),
                        'contact_number': contact.strip(),
                        'project_name': project_name.strip(),
                        'source_url': source_url.strip(),
                        'submitted_at': firestore.SERVER_TIMESTAMP
                    }
                    
                    # Try to save to database
                    success, error_msg = save_submission(db, submission_data)
                    
                    if success:
                        # Data saved successfully, now try to send email
                        try:
                            email_sent = send_confirmation_email(
                                submission_data['email'],
                                submission_data['full_name'],
                                submission_data['project_name']
                            )
                            
                            if not email_sent:
                                st.info("📝 Submission saved! Email notification could not be sent.")
                                
                        except Exception as e:
                            st.info("📝 Your submission was saved successfully!")
                        
                        # Show success page regardless of email status
                        st.session_state.submitted_data = submission_data
                        st.session_state.submission_complete = True
                        time.sleep(0.5)
                        st.rerun()
                        
                    else:
                        # Database save failed
                        st.error(f"❌ {error_msg}")
                        st.session_state.is_submitting = False
    
    # Validation hints
    with st.expander("ℹ️ Submission Guidelines & Requirements", expanded=False):
        st.markdown("""
        **📋 Field Requirements:**
        
        **Personal Information:**
        - **Email ID:** Valid email format (e.g., student@university.edu)
        - **Enrollment Number:** Exactly 12 numeric digits
        - **Full Name:** Letters and spaces only, no special characters
        - **Contact Number:** Exactly 10 numeric digits
        
        **Project Information:**
        - **Project Name:** Minimum 3 characters, be descriptive
        - **Source URL:** Must start with http:// or https://
        
        **⚠️ Important Notes:**
        - All fields marked with * are mandatory
        - Each enrollment number can only be submitted once
        - Double-check all information before submitting
        - You will receive a confirmation email upon successful submission
        """)

if __name__ == "__main__":
    main()
