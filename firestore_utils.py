from firebase_admin import credentials, firestore, initialize_app
import os

# Initialize Firestore
def init_firestore():
    # Use the service account key file if it exists
    service_account_path = os.path.join(os.path.dirname(__file__), 'serviceAccountKey.json')
    
    if os.path.exists(service_account_path):
        cred = credentials.Certificate(service_account_path)
        firebase_app = initialize_app(cred)
    else:
        # For development, you can use the default credentials if running in a GCP environment
        firebase_app = initialize_app()
    
    return firestore.client()

db = init_firestore()

# Collections
UPDATES_COLLECTION = 'updates_and_announcements'
FAQ_COLLECTION = 'faq_content'

def get_updates():
    """Get all updates and announcements"""
    return db.collection(UPDATES_COLLECTION).order_by('created_at', direction='DESCENDING').stream()

def add_update(title, content, user_id):
    """Add a new update or announcement"""
    update_ref = db.collection(UPDATES_COLLECTION).document()
    update_ref.set({
        'title': title,
        'content': content,
        'created_at': firestore.SERVER_TIMESTAMP,
        'created_by': user_id,
        'is_active': True
    })
    return update_ref.id

def update_update(update_id, title, content):
    """Update an existing update"""
    update_ref = db.collection(UPDATES_COLLECTION).document(update_id)
    update_ref.update({
        'title': title,
        'content': content,
        'updated_at': firestore.SERVER_TIMESTAMP
    })

def delete_update(update_id):
    """Delete an update"""
    db.collection(UPDATES_COLLECTION).document(update_id).delete()

def get_faqs():
    """Get all FAQs"""
    return db.collection(FAQ_COLLECTION).order_by('order', direction='ASCENDING').stream()

def add_faq(question, answer, user_id):
    """Add a new FAQ"""
    # Get the next order number
    last_faq = db.collection(FAQ_COLLECTION).order_by('order', direction='DESCENDING').limit(1).get()
    next_order = 1
    if last_faq:
        next_order = last_faq[0].to_dict().get('order', 0) + 1
    
    faq_ref = db.collection(FAQ_COLLECTION).document()
    faq_ref.set({
        'question': question,
        'answer': answer,
        'created_at': firestore.SERVER_TIMESTAMP,
        'created_by': user_id,
        'order': next_order,
        'is_active': True
    })
    return faq_ref.id

def update_faq(faq_id, question, answer):
    """Update an existing FAQ"""
    faq_ref = db.collection(FAQ_COLLECTION).document(faq_id)
    faq_ref.update({
        'question': question,
        'answer': answer,
        'updated_at': firestore.SERVER_TIMESTAMP
    })

def delete_faq(faq_id):
    """Delete an FAQ"""
    db.collection(FAQ_COLLECTION).document(faq_id).delete()

def reorder_faq(faq_id, new_order):
    """Reorder FAQs"""
    faq_ref = db.collection(FAQ_COLLECTION).document(faq_id)
    faq_ref.update({
        'order': new_order,
        'updated_at': firestore.SERVER_TIMESTAMP
    })
