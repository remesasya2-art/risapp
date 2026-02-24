import { initializeApp } from "firebase/app";
import { getAnalytics, isSupported } from "firebase/analytics";
import { Platform } from 'react-native';

// Firebase configuration for RIS app
const firebaseConfig = {
  apiKey: "AIzaSyCKptA0-ELAstjeQeLWWUHRMKt3RXRkD6w",
  authDomain: "remesas-ya-d2940.firebaseapp.com",
  projectId: "remesas-ya-d2940",
  storageBucket: "remesas-ya-d2940.firebasestorage.app",
  messagingSenderId: "237597893004",
  appId: "1:237597893004:web:6c4a838f555508faa936a9",
  measurementId: "G-MY372ZXSYL"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);

// Initialize Analytics only on web
let analytics = null;
if (Platform.OS === 'web') {
  isSupported().then(supported => {
    if (supported) {
      analytics = getAnalytics(app);
    }
  });
}

export { app, analytics };
export default firebaseConfig;
