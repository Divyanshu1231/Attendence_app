import csv, io, json, math, os, secrets
from datetime import datetime, date, timezone
from pathlib import Path
from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, desc
from .database import Base, engine, get_db, SessionLocal
from .models import User, Attendance, AppSetting
from .security import hash_password, verify_password, make_session, read_session

BASE = Path(__file__).resolve().parent
app = FastAPI(title="Office Face + GPS Attendance")
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))
Base.metadata.create_all(bind=engine)

HTTPS_ONLY = os.getenv("SESSION_HTTPS_ONLY", "false").lower() == "true"

def get_setting(db: Session, key: str, env_key: str, default: str) -> str:
    saved = db.get(AppSetting, key)
    return saved.value if saved else os.getenv(env_key, default)

def set_setting(db: Session, key: str, value: str):
    setting = db.get(AppSetting, key)
    if setting is None:
        setting = AppSetting(key=key, value=value)
        db.add(setting)
    else:
        setting.value = value

def office_config(db: Session):
    return {
        "latitude": float(get_setting(db, "office_latitude", "OFFICE_LATITUDE", "28.5355")),
        "longitude": float(get_setting(db, "office_longitude", "OFFICE_LONGITUDE", "77.3910")),
        "radius": max(20.0, float(get_setting(db, "office_radius_meters", "OFFICE_RADIUS_METERS", "100"))),
        "face_threshold": float(get_setting(db, "face_match_threshold", "FACE_MATCH_THRESHOLD", "0.50")),
    }

def now_utc():
    return datetime.now(timezone.utc)

def current_user(request: Request, db: Session):
    uid = read_session(request.cookies.get("attendance_session"))
    user = db.get(User, uid) if uid else None
    return user if user and user.active else None

def require_user(request: Request, db: Session):
    user = current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in again.")
    return user

def require_admin(request: Request, db: Session):
    user = require_user(request, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user

def haversine_m(lat1, lon1, lat2, lon2):
    radius = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0, 1-a)))

def valid_descriptor(value):
    return isinstance(value, list) and len(value) == 128 and all(isinstance(x, (int, float)) and math.isfinite(float(x)) for x in value)

def local_time(value):
    if not value:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone().strftime("%I:%M %p")

def page(request, template, **context):
    return templates.TemplateResponse(request=request, name=template, context={"request": request, **context})

def ensure_admin():
    """Create the first admin ONLY if no admin exists yet.

    Never overwrite or re-create an admin afterwards, so a password/email changed
    from the Settings page is never replaced by the ADMIN_* env defaults.
    """
    with SessionLocal() as db:
        existing_admin = db.scalar(select(User).where(User.role == "admin").order_by(User.id))
        if existing_admin:
            return
        email = os.getenv("ADMIN_EMAIL", "admin@example.com").strip().lower()
        password = os.getenv("ADMIN_PASSWORD", "").strip()
        if not password:
            password = secrets.token_urlsafe(16)
            print(f"[ensure_admin] ADMIN_PASSWORD not set. Temporary admin password: {password}", flush=True)
        # If this email already belongs to a non-admin user, promote it instead of crashing.
        user = db.scalar(select(User).where(User.email == email))
        if user:
            user.role = "admin"
            user.active = True
        else:
            db.add(User(name="Administrator", email=email, password_hash=hash_password(password), role="admin"))
        db.commit()
ensure_admin()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/admin" if user.role == "admin" else "/employee", status_code=303)

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return page(request, "login.html", error=None)

@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not user or not user.active or not verify_password(password, user.password_hash):
        return page(request, "login.html", error="Email or password is incorrect.")
    response = RedirectResponse("/admin" if user.role == "admin" else "/employee", status_code=303)
    response.set_cookie("attendance_session", make_session(user.id), httponly=True, secure=HTTPS_ONLY, samesite="lax", max_age=604800)
    return response

@app.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("attendance_session")
    return response

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, db: Session = Depends(get_db)):
    try:
        admin = require_admin(request, db)
    except HTTPException:
        return RedirectResponse("/login", status_code=303)
    employees = db.scalars(select(User).where(User.role == "employee").order_by(User.name)).all()
    today = date.today().isoformat()
    cfg = office_config(db)
    records = db.scalars(select(Attendance).where(Attendance.work_date == today).order_by(desc(Attendance.check_in))).all()
    rows = [{"name": a.employee.name, "email": a.employee.email, "check_in": local_time(a.check_in), "check_out": local_time(a.check_out), "status": a.status} for a in records]
    settings = {**cfg, "admin_email": admin.email, "message": request.query_params.get("saved"), "error_code": request.query_params.get("settings_error")}
    return page(request, "admin.html", user=admin, employees=employees, rows=rows, today=today, radius=int(cfg["radius"]), settings=settings, error=None)

@app.post("/admin/employees")
def create_employee(request: Request, name: str = Form(...), email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    require_admin(request, db)
    name, email = name.strip(), email.strip().lower()
    if len(name) < 2 or "@" not in email or len(password) < 10:
        raise HTTPException(status_code=400, detail="Use a valid name/email and password of at least 10 characters.")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="This email already exists.")
    db.add(User(name=name, email=email, password_hash=hash_password(password), role="employee"))
    db.commit()
    return RedirectResponse("/admin?created=1", status_code=303)

@app.post("/admin/employees/{uid}/toggle")
def toggle_employee(uid: int, request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    employee = db.get(User, uid)
    if not employee or employee.role != "employee":
        raise HTTPException(status_code=404, detail="Employee not found.")
    employee.active = not employee.active
    db.commit()
    return RedirectResponse("/admin", status_code=303)

@app.post("/admin/settings")
def save_admin_settings(
    request: Request,
    email: str = Form(...),
    current_password: str = Form(...),
    new_password: str = Form(""),
    office_latitude: str = Form(...),
    office_longitude: str = Form(...),
    office_radius_meters: int = Form(...),
    face_match_threshold: float = Form(...),
    db: Session = Depends(get_db),
):
    admin = require_admin(request, db)
    if not verify_password(current_password, admin.password_hash):
        return RedirectResponse("/admin?settings_error=current_password", status_code=303)
    email = email.strip().lower()
    if "@" not in email or len(email) > 255:
        return RedirectResponse("/admin?settings_error=email", status_code=303)
    other = db.scalar(select(User).where(User.email == email, User.id != admin.id))
    if other:
        return RedirectResponse("/admin?settings_error=email_exists", status_code=303)
    if new_password and len(new_password) < 10:
        return RedirectResponse("/admin?settings_error=password", status_code=303)
    try:
        lat, lon = float(office_latitude), float(office_longitude)
        radius = int(office_radius_meters)
        threshold = float(face_match_threshold)
    except (TypeError, ValueError):
        return RedirectResponse("/admin?settings_error=coordinates", status_code=303)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180 and 20 <= radius <= 5000 and 0.2 <= threshold <= 0.8):
        return RedirectResponse("/admin?settings_error=range", status_code=303)
    admin.email = email
    if new_password:
        admin.password_hash = hash_password(new_password)
    set_setting(db, "office_latitude", str(lat))
    set_setting(db, "office_longitude", str(lon))
    set_setting(db, "office_radius_meters", str(radius))
    set_setting(db, "face_match_threshold", str(threshold))
    db.commit()
    return RedirectResponse("/admin?saved=1", status_code=303)

@app.get("/employee", response_class=HTMLResponse)
def employee_page(request: Request, db: Session = Depends(get_db)):
    try:
        user = require_user(request, db)
    except HTTPException:
        return RedirectResponse("/login", status_code=303)
    today = date.today().isoformat()
    cfg = office_config(db)
    record = db.scalar(select(Attendance).where(Attendance.user_id == user.id, Attendance.work_date == today))
    return page(request, "employee.html", user=user, record=record, today=today, radius=int(cfg["radius"]), has_face=bool(user.face_descriptor))

@app.post("/api/face/enroll")
async def enroll_face(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    # Allow both admin and employee accounts to enroll their own face / mark attendance.
    if user.role not in {"admin", "employee"}:
        raise HTTPException(status_code=403, detail="Unsupported account role.")
    body = await request.json()
    descriptor = body.get("descriptor")
    if not valid_descriptor(descriptor):
        raise HTTPException(status_code=400, detail="Face not detected. Try again in good lighting.")
    user.face_descriptor = json.dumps([float(x) for x in descriptor])
    db.commit()
    return {"ok": True, "message": "Face enrollment saved."}

@app.post("/api/attendance/{action}")
async def attendance_action(action: str, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    # Allow both admin and employee accounts to enroll their own face / mark attendance.
    if user.role not in {"admin", "employee"}:
        raise HTTPException(status_code=403, detail="Unsupported account role.")
    if action not in {"check-in", "check-out", "lunch-start", "lunch-end"}:
        raise HTTPException(status_code=404, detail="Unknown attendance action.")
    body = await request.json()
    lat, lon, descriptor = body.get("latitude"), body.get("longitude"), body.get("descriptor")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise HTTPException(status_code=400, detail="Valid GPS location is required.")
    cfg = office_config(db)
    distance = haversine_m(float(lat), float(lon), cfg["latitude"], cfg["longitude"])
    if distance > cfg["radius"]:
        raise HTTPException(status_code=403, detail=f"Attendance blocked: reported location is {int(distance)}m from office; allowed radius is {int(cfg['radius'])}m.")
    if not user.face_descriptor:
        raise HTTPException(status_code=400, detail="Enroll your face first.")
    if not valid_descriptor(descriptor):
        raise HTTPException(status_code=400, detail="Face verification data is missing.")
    saved = json.loads(user.face_descriptor)
    score = math.sqrt(sum((float(a)-float(b))**2 for a,b in zip(saved, descriptor)) / len(saved))
    if score > cfg["face_threshold"]:
        raise HTTPException(status_code=403, detail="Face verification failed. Try again in good lighting.")
    today = date.today().isoformat()
    record = db.scalar(select(Attendance).where(Attendance.user_id == user.id, Attendance.work_date == today))
    now = now_utc()
    if action == "check-in":
        if record and record.check_in:
            raise HTTPException(status_code=409, detail="You have already checked in today.")
        if not record:
            record = Attendance(user_id=user.id, work_date=today, status="present")
            db.add(record)
        record.check_in, record.check_in_lat, record.check_in_lon, record.check_in_distance_m = now, float(lat), float(lon), distance
    elif action == "check-out":
        if not record or not record.check_in or record.check_out:
            raise HTTPException(status_code=400, detail="No open check-in found.")
        if record.lunch_start and not record.lunch_end:
            raise HTTPException(status_code=400, detail="End lunch break before checking out.")
        record.check_out = now
    elif action == "lunch-start":
        if not record or not record.check_in or record.check_out:
            raise HTTPException(status_code=400, detail="Check in before starting lunch.")
        if record.lunch_start and not record.lunch_end:
            raise HTTPException(status_code=409, detail="Lunch break is already active.")
        record.lunch_start, record.lunch_end = now, None
    elif action == "lunch-end":
        if not record or not record.lunch_start or record.lunch_end:
            raise HTTPException(status_code=400, detail="No active lunch break.")
        record.lunch_end = now
    db.commit()
    return {"ok": True, "message": {"check-in":"Attendance checked in successfully.","check-out":"Checked out successfully.","lunch-start":"Lunch break started.","lunch-end":"Lunch break ended."}[action], "record":{"check_in":local_time(record.check_in),"check_out":local_time(record.check_out)}}

@app.get("/admin/export.csv")
def export_csv(request: Request, db: Session = Depends(get_db), start: str = "", end: str = ""):
    require_admin(request, db)
    query = select(Attendance).order_by(Attendance.work_date.desc())
    if start: query = query.where(Attendance.work_date >= start)
    if end: query = query.where(Attendance.work_date <= end)
    rows = db.scalars(query).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Employee","Email","Date","Check In","Lunch Start","Lunch End","Check Out","Status","Check-in Distance (m)"])
    for a in rows:
        writer.writerow([a.employee.name,a.employee.email,a.work_date,local_time(a.check_in),local_time(a.lunch_start),local_time(a.lunch_end),local_time(a.check_out),a.status,round(a.check_in_distance_m or 0)])
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition":"attachment; filename=attendance-report.csv"})

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=exc.status_code, content={"detail":exc.detail})
    return JSONResponse(status_code=exc.status_code, content={"detail":exc.detail})
