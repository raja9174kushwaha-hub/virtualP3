# EcoStep - Gamified Sustainability & Cash Savings Platform

EcoStep is a single page app for carbon-footprint awareness, simple daily green habits, cash-savings estimates, geo-league challenges, and redeemable Eco-Perks. The app is designed for a Google-only deployment path: Cloud Run for hosting, Firebase Authentication for identity, and Cloud Firestore for persistence.

## Google-Only Stack

- Frontend: Vanilla HTML, CSS, and JavaScript
- Icons and fonts: Google Fonts and Google Material Symbols
- Runtime: Google Cloud Run
- Auth: Firebase Authentication with Email/Password and Google Sign-In
- Database: Cloud Firestore
- Local/demo mode: Browser `localStorage` when Firebase config is not supplied

No AWS, Azure, Supabase, MongoDB, S3, Redis, Kafka, third-party image CDN, or third-party icon CDN is required by this implementation.

## Free-Tier Posture

- Cloud Run can scale to zero when idle. Deploy with `--min-instances=0`.
- Firebase Authentication and Cloud Firestore can run on Firebase's free Spark plan for small demos and prototypes.
- The local fallback mode is free and works without Firebase credentials.
- Google Cloud billing rules can change, so set a budget alert in Google Cloud Billing before public traffic.

## Feature Check

- Fast onboarding with Google or email auth, archetype selection, region lookup, household size, and consent toggles
- Eco-Pulse dashboard with CO2e, savings, goals, footprint breakdown, equivalencies, insights, and action history
- Daily three-habit engine with archetype-aware habit rolls and completion tracking
- Manual eco-action logging with points, cash savings, and carbon impact updates
- Geo-league challenges and challenge enrollment
- Eco-Perks catalog, points wallet, redemption flow, and voucher wallet
- Profile, privacy consent controls, sign out, and account reset
- Admin console for regional emissions factors, habit catalog entries, challenges, and audit logs
- Diagnostics tab with client-side verification checks
- Firebase sync for authenticated users and offline/local sandbox fallback

## Project Files

- `index.html` - App shell, screens, modals, drawers, and templates
- `style.css` - Responsive UI, tokens, light/dark themes, and component styling
- `app.js` - State engine, Firebase auth, Firestore sync, habits, rewards, challenges, diagnostics, and UI rendering
- `server.py` - Flask app serving static assets and runtime Firebase config
- `Dockerfile` - Cloud Run container image definition
- `.dockerignore` - Keeps local secrets and bulky docs out of the image
- `requirements.txt` - Python runtime dependencies
- `.env` - Local-only Firebase config, ignored by Docker and Git

## Local Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Optional Firebase config:

Create a `.env` file for local Firebase mode:

```env
FIREBASE_API_KEY=your_key_here
FIREBASE_AUTH_DOMAIN=your_project.firebaseapp.com
FIREBASE_PROJECT_ID=your_project
FIREBASE_STORAGE_BUCKET=your_project.appspot.com
FIREBASE_MESSAGING_SENDER_ID=your_sender_id
FIREBASE_APP_ID=your_app_id
```

If the Firebase config is absent, the app automatically runs in local sandbox mode.

3. Run locally:

```bash
python server.py
```

Open `http://localhost:8000`.

## Firebase Setup

1. Create a Firebase project.
2. Add a Web App and copy the Firebase web config.
3. Enable Firebase Authentication providers:
   - Email/Password
   - Google
4. Enable Cloud Firestore.
5. Add every deployed app URL to Firebase Authentication authorized domains, including your Cloud Run domain.
6. For production, replace test Firestore rules with user-scoped rules before launch.

## Postal Code Resolution

EcoStep resolves known demo ZIP/PIN codes locally so it stays free and does not require a paid geocoding API. Supported built-ins include Austin, San Francisco, New York, New Delhi, Mumbai, Bengaluru, Chennai, Kolkata, Hyderabad, Pune, and Jaipur. Admin users can add more exact postal codes from the Admin Console; unsupported 6-digit postal codes use the India national-grid fallback, and other unsupported codes use the U.S. national-grid fallback.

## Cloud Run Deployment

Build and deploy from the project root:

```bash
gcloud run deploy ecostep \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --min-instances 0 \
  --set-env-vars FIREBASE_API_KEY=your_key_here,FIREBASE_AUTH_DOMAIN=your_project.firebaseapp.com,FIREBASE_PROJECT_ID=your_project,FIREBASE_STORAGE_BUCKET=your_project.appspot.com,FIREBASE_MESSAGING_SENDER_ID=your_sender_id,FIREBASE_APP_ID=your_app_id
```

For a no-Firebase public demo, omit the Firebase environment variables and Cloud Run will serve the local sandbox version.

## Cloud Run Runtime Notes

- Cloud Run injects `PORT`; the container listens on that port.
- Production runs with Gunicorn using `server:app`.
- Flask debug is off by default. Set `FLASK_DEBUG=true` only for local debugging.
- `.env` is excluded from the container image. Use Cloud Run environment variables for config.
