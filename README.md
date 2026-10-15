# Office Face + GPS Attendance

A single-service FastAPI web app for Render with employee/admin login, browser face enrollment, GPS geofence validation, check-in/out, lunch break actions, and CSV export.

## Local run (Python 3.12 recommended)
1. Extract this ZIP and open a terminal in the project folder.
2. Create a virtual environment and install dependencies:
   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   Copy-Item .env.example .env
   ```
3. Edit `.env`. Set a strong `SECRET_KEY`, `ADMIN_PASSWORD`, and the actual office coordinates.
4. Run `uvicorn app.main:app --reload`
5. Open http://127.0.0.1:8000. If the `uvicorn` command is not recognized, run `python -m uvicorn app.main:app --reload`.

## Render deployment
1. Push the project folder to GitHub.
2. Create a PostgreSQL database in Render.
3. Create a Render Web Service from the repository.
4. Build command: `pip install -r requirements.txt`
5. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
6. Configure these environment variables in Render:
   - `DATABASE_URL`: Render PostgreSQL Internal Database URL
   - `SECRET_KEY`: long random secret
   - `ADMIN_EMAIL`, `ADMIN_PASSWORD`
   - `OFFICE_LATITUDE`, `OFFICE_LONGITUDE`: exact office pin coordinates from Google Maps
   - `OFFICE_RADIUS_METERS`: for example `100`
   - `FACE_MATCH_THRESHOLD`: start at `0.50`, tune after testing
   - `SESSION_HTTPS_ONLY`: `true`
7. Deploy. The admin account is created on first startup from the configured admin credentials.

## Employee attendance: exact steps
1. Sign in as admin and use **Add employee** to create an employee account (password must be at least 10 characters).
2. Share the employee login URL `http://127.0.0.1:8000/login` and their credentials privately. There is no public employee self-registration; this prevents unknown people creating accounts.
3. Employee signs in with their own email/password. The app automatically opens `/employee` (Employee Workspace).
4. Employee clicks **Enable camera** and allows camera access. Wait for face models to load, then click **Enroll face** once.
5. Allow location permission in the browser. While physically at the configured office, click **Check in**. The server validates the reported GPS distance and compares the live face descriptor against the enrolled descriptor.
6. Use **Start lunch break**, **End lunch break**, and **Check out** on the same Employee Workspace page.
7. Admin can review today's attendance, disable employee access, and export CSV from the admin dashboard.

Admin and employees use the same `/login` page; the role determines which dashboard opens. If you sign in with admin credentials, you will see the admin panel. To see attendance marking, sign in with an employee account created by the admin.

## Security limitations (read before production)
- Browser GPS is not proof of physical presence and can be spoofed. The backend validates distance, but cannot guarantee that the device reported genuine GPS.
- Face matching uses face-api.js descriptors and does not include strong liveness / anti-spoofing. A photo/video spoof may bypass it. For high-assurance use, add a tested liveness service or a dedicated office device.
- Face descriptors are biometric data. Get informed employee consent, restrict access, and define deletion/retention policies.
- Face-api.js and its model files load from public CDNs. Bundle pinned assets locally for production reliability.
- Render free services can sleep and local disks are ephemeral. Use Render PostgreSQL and an always-on service for dependable attendance.
- This is a starter MVP; test thoroughly before using for payroll or disciplinary decisions.


## Admin Settings (added)
After signing in as admin, use the **Settings** link on the dashboard to update the admin email, optional password, office latitude/longitude, allowed GPS radius, and face-match threshold. You must enter your current password to save changes. These settings are stored in the database, so they persist across restarts and take precedence over the matching `.env` values. Existing attendance records are not deleted. Keep `.env` values as initial defaults for a new database.

For local testing, use the actual office coordinates before marking attendance. Use a strong secret key and a strong admin password before deploying. Face matching is a starter implementation and GPS can be spoofed; do not treat it as production-grade identity verification without liveness/anti-spoofing tests.


## Face enrollment loading fix

This build updates `app/static/employee.js` to try the browser bundle from the
Vladmandic face-api distribution and its model repository. The duplicate CDN
script tag was removed from `employee.html` so the loader is controlled in one
place. An internet connection is still required for these CDN-hosted files.
If your network blocks both CDNs, the library and model files must be downloaded
and served locally before face enrollment can work.

After extracting, keep your existing `.env` and `attendance.db` backed up.
Install dependencies with `python -m pip install -r requirements.txt`, then run
`python -m uvicorn app.main:app --reload`.
