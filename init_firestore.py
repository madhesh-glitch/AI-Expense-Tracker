from firestore_utils import db, UPDATES_COLLECTION, FAQ_COLLECTION

def initialize_collections():
    # Collections to create
    collections = {
        'users': {
            'indexes': [
                {'field': 'email', 'unique': True},
                {'field': 'created_at', 'order': 'DESCENDING'}
            ]
        },
        'expenses': {
            'indexes': [
                {'field': 'user_id'},
                {'field': 'date', 'order': 'DESCENDING'},
                {'field': 'category'}
            ]
        },
        UPDATES_COLLECTION: {
            'indexes': [
                {'field': 'created_at', 'order': 'DESCENDING'}
            ]
        },
        FAQ_COLLECTION: {
            'indexes': [
                {'field': 'order'},
                {'field': 'created_at', 'order': 'DESCENDING'}
            ]
        },
        'settings': {
            'indexes': [
                {'field': 'user_id', 'unique': True}
            ]
        }
    }

    # Create collections and indexes
    for collection_name, config in collections.items():
        print(f"Checking/creating collection: {collection_name}")
        
        # The collection will be created automatically when we add a document
        doc_ref = db.collection(collection_name).document('_initial')
        try:
            doc_ref.set({'created': True})
            print(f"✅ Created collection: {collection_name}")
        except Exception as e:
            print(f"ℹ️ Collection {collection_name} already exists or error: {str(e)}")
        
        # Note: Firestore creates single-field indexes automatically for most queries
        # Composite indexes need to be created manually in the Firebase Console
        print(f"   Note: For optimal performance, create these indexes in Firebase Console:")
        for idx in config.get('indexes', []):
            print(f"   - Index on: {idx['field']}" + 
                  (f" ({idx['order']} order)" if 'order' in idx else '') +
                  (" (unique)" if idx.get('unique', False) else ''))

if __name__ == '__main__':
    print("Initializing Firestore collections...")
    initialize_collections()
    print("✅ Done! Please check the Firebase Console to create any required composite indexes.")
