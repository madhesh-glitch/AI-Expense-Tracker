// Firebase configuration
// For Firebase JS SDK v7.20.0 and later, measurementId is optional
const firebaseConfig = {
  apiKey: "AIzaSyDDjpV9y82muXh1LNu6vTf6u1AVhj2q9j4",
  authDomain: "ai-expense-tracker-32a6b.firebaseapp.com",
  projectId: "ai-expense-tracker-32a6b",
  storageBucket: "ai-expense-tracker-32a6b.firebasestorage.app",
  messagingSenderId: "585250811885",
  appId: "1:585250811885:web:986a5d7cca6ba2d71381e4",
  measurementId: "G-HPS894YBQC"
};

// Initialize Firebase when the script loads
function initializeFirebase() {
  let app, db, auth, analytics;
  
  try {
    // Try to get existing app
    app = firebase.app();
    console.log('Using existing Firebase app');
  } catch (e) {
    // Initialize a new one if it doesn't exist
    console.log('Initializing new Firebase app');
    app = firebase.initializeApp(firebaseConfig);
  }
  
  // Initialize services
  db = firebase.firestore();
  auth = firebase.auth();
  
  // Initialize Analytics if available
  if (firebase.analytics) {
    try {
      analytics = firebase.analytics();
    } catch (e) {
      console.warn('Firebase Analytics could not be initialized', e);
    }
  }
  
  console.log('Firebase initialized successfully');
  return { app, db, auth, analytics };
}

// Initialize Firebase and make it globally available
window.firebaseApp = initializeFirebase();
