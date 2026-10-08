"""FitClub API — FastAPI.

Endpoints:
  POST /api/auth/register | /api/auth/login | GET /api/me
  POST /api/activities | POST /api/activities/bulk
  GET  /api/activities | DELETE /api/activities/{id}
  POST /api/metrics
  GET  /api/leaderboard?period=week|month|alltime&metric=km|activities|duration|longest|streak
  GET  /api/me/stats
  POST /api/ingest/files   (multipart: varios CSVs de Fitbit/Google Health)

Convención de timezone: start_utc siempre se guarda como UTC naive.
Si el cliente manda ISO con offset, se convierte a UTC; si es naive,
se interpreta como UTC (documentado en el README).
"""
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import List, Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, field_validator
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from db import Activity, DailyMetric, User, engine, init_db
from ingest import detect_and_parse

SECRET_KEY = os.environ.get("SECRET_KEY", "cambieme-en-produccion")
ALGORITHM = "HS256"

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="FitClub API", lifespan=lifespan)


# ---------- Schemas ----------
class UserIn(BaseModel):
    email: str
    display_name: str
    password: str


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    tz: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ActivityIn(BaseModel):
    external_id: Optional[str] = None
    name: str
    type: str = "other"
    start_utc: datetime
    duration_min: Optional[float] = None
    distance_km: Optional[float] = None
    calories: Optional[int] = None
    steps: Optional[int] = None
    avg_hr: Optional[int] = None
    max_hr: Optional[int] = None
    rpe: Optional[int] = None
    source: str = "manual"

    @field_validator("start_utc", mode="before")
    @classmethod
    def _norm_start(cls, v):
        """Normaliza a UTC naive: con offset → convierte; naive → asume UTC."""
        if isinstance(v, str):
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        elif isinstance(v, datetime):
            dt = v
        else:
            return v
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return dt.replace(tzinfo=None)


class ActivityOut(ActivityIn):
    id: int
    user_id: int


class BulkIn(BaseModel):
    activities: List[ActivityIn]


class MetricIn(BaseModel):
    date: date
    steps: Optional[int] = None
    resting_hr: Optional[int] = None
    sleep_hours: Optional[float] = None
    sleep_score: Optional[int] = None
    deep_sleep_min: Optional[int] = None
    stress: Optional[int] = None
    vo2max: Optional[float] = None
    weight_kg: Optional[float] = None


# ---------- Helpers de timezone ----------
def to_local_date(utc_naive: datetime, tz: str) -> date:
    """Fecha local de un timestamp UTC naive."""
    return utc_naive.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz)).date()


def _today_local(tz: str) -> date:
    return datetime.now(ZoneInfo(tz)).date()


# ---------- Auth ----------
def _pub(u: User) -> dict:
    return {"id": u.id, "email": u.email, "display_name": u.display_name, "tz": u.tz}


def create_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=7)
    return jwt.encode({"sub": str(user.id), "exp": exp}, SECRET_KEY, ALGORITHM)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Falta el token")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        uid = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Token inválido")
    with Session(engine) as s:
        u = s.get(User, uid)
    if not u:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return u


@app.post("/api/auth/register", status_code=201, response_model=TokenOut)
def register(body: UserIn):
    with Session(engine) as s:
        if s.exec(select(User).where(col(User.email) == body.email.lower())).first():
            raise HTTPException(status_code=409, detail="Ese email ya está registrado")
        u = User(
            email=body.email.lower(),
            display_name=body.display_name,
            password_hash=pwd.hash(body.password),
        )
        s.add(u)
        try:
            s.commit()
        except IntegrityError:
            s.rollback()
            raise HTTPException(status_code=409, detail="Ese email ya está registrado")
        s.refresh(u)
        return TokenOut(access_token=create_token(u), user=_pub(u))


@app.post("/api/auth/login", response_model=TokenOut)
def login(body: LoginIn):
    with Session(engine) as s:
        u = s.exec(select(User).where(col(User.email) == body.email.lower())).first()
    if not u or not pwd.verify(body.password, u.password_hash):
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
    return TokenOut(access_token=create_token(u), user=_pub(u))


@app.get("/api/me", response_model=UserOut)
def me(me: User = Depends(get_current_user)):
    return _pub(me)


# ---------- Actividades ----------
@app.post("/api/activities", status_code=201, response_model=ActivityOut)
def create_activity(body: ActivityIn, me: User = Depends(get_current_user)):
    with Session(engine) as s:
        a = Activity(**body.model_dump(), user_id=me.id)
        s.add(a)
        try:
            s.commit()
        except IntegrityError:
            s.rollback()
            raise HTTPException(
                status_code=409, detail="external_id ya existe para este usuario"
            )
        s.refresh(a)
        return a


@app.post("/api/activities/bulk")
def create_activities_bulk(body: BulkIn, me: User = Depends(get_current_user)):
    added = skipped = 0
    with Session(engine) as s:
        for a in body.activities:
            if a.external_id:
                exists = s.exec(
                    select(Activity).where(
                        Activity.user_id == me.id, Activity.external_id == a.external_id
                    )
                ).first()
                if exists:
                    skipped += 1
                    continue
            s.add(Activity(**a.model_dump(), user_id=me.id))
            added += 1
        s.commit()
    return {"added": added, "skipped": skipped}


@app.get("/api/activities", response_model=List[ActivityOut])
def list_activities(
    limit: int = Query(50, ge=1, le=500),
    me: User = Depends(get_current_user),
):
    with Session(engine) as s:
        return (
            s.exec(
                select(Activity)
                .where(Activity.user_id == me.id)
                .order_by(col(Activity.start_utc).desc())
                .limit(limit)
            )
            .all()
        )


@app.delete("/api/activities/{activity_id}")
def delete_activity(activity_id: int, me: User = Depends(get_current_user)):
    with Session(engine) as s:
        a = s.exec(
            select(Activity).where(Activity.id == activity_id, Activity.user_id == me.id)
        ).first()
        if not a:
            raise HTTPException(status_code=404, detail="Actividad no encontrada")
        s.delete(a)
        s.commit()
    return {"ok": True}


# ---------- Métricas diarias ----------
@app.post("/api/metrics")
def upsert_metric(body: MetricIn, me: User = Depends(get_current_user)):
    with Session(engine) as s:
        m = s.exec(
            select(DailyMetric).where(
                DailyMetric.user_id == me.id, col(DailyMetric.date) == body.date
            )
        ).first()
        if m:
            for k, v in body.model_dump().items():
                if k != "date" and v is not None:
                    setattr(m, k, v)
        else:
            s.add(DailyMetric(user_id=me.id, **body.model_dump()))
        s.commit()
    return {"ok": True}


# ---------- Leaderboard ----------
def period_start(period: Literal["week", "month", "alltime"], tz: str) -> datetime:
    """Inicio del período, en UTC naive, según la tz del usuario."""
    now = datetime.now(ZoneInfo(tz))
    if period == "week":
        local = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    elif period == "month":
        local = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        return datetime(2000, 1, 1)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def calc_streak(dates, tz: str) -> int:
    """Días consecutivos con actividad (hoy sin entrenar no rompe)."""
    today = _today_local(tz)
    ds = set(dates)
    if today not in ds:
        today -= timedelta(days=1)
    n = 0
    while today in ds:
        n += 1
        today -= timedelta(days=1)
    return n


METRICS = ("km", "activities", "duration", "longest", "streak")


@app.get("/api/leaderboard")
def leaderboard(
    period: Literal["week", "month", "alltime"] = "week",
    metric: str = "km",
    me: User = Depends(get_current_user),
):
    if metric not in METRICS:
        raise HTTPException(status_code=400, detail="Métrica inválida")
    since = period_start(period, me.tz)

    with Session(engine) as s:
        users = s.exec(select(User)).all()
        # Una sola query: todas las actividades (streak es global,
        # el resto se filtra por período en Python)
        acts = s.exec(select(Activity)).all()

    by_user: dict[int, list] = {}
    for a in acts:
        by_user.setdefault(a.user_id, []).append(a)

    rows = []
    for u in users:
        user_acts = by_user.get(u.id, [])
        period_acts = [a for a in user_acts if a.start_utc >= since]
        dists = [a.distance_km or 0.0 for a in period_acts]
        local_dates = {to_local_date(a.start_utc, u.tz) for a in user_acts}
        rows.append(
            {
                "user_id": u.id,
                "name": u.display_name,
                "km": round(sum(dists), 1),
                "activities": len(period_acts),
                "duration": int(round(sum(a.duration_min or 0 for a in period_acts))),
                "longest": round(max(dists), 1) if dists else 0.0,
                "streak": calc_streak(local_dates, u.tz),
            }
        )

    rows.sort(key=lambda r: r[metric], reverse=True)
    return [{"rank": i + 1, **r, "you": r["user_id"] == me.id} for i, r in enumerate(rows[:20])]


# ---------- Stats del dashboard ----------
@app.get("/api/me/stats")
def my_stats(me: User = Depends(get_current_user)):
    with Session(engine) as s:
        acts = s.exec(
            select(Activity)
            .where(Activity.user_id == me.id)
            .order_by(col(Activity.start_utc).desc())
        ).all()
        metrics = s.exec(
            select(DailyMetric)
            .where(DailyMetric.user_id == me.id)
            .order_by(col(DailyMetric.date).desc())
        ).all()

    # km por semana (lunes a domingo, en la tz del usuario), últimas 8 semanas
    today = _today_local(me.tz)
    first_monday = today - timedelta(days=today.weekday()) - timedelta(weeks=7)
    weekly = []
    for w in range(8):
        monday = first_monday + timedelta(weeks=w)
        km = sum(
            a.distance_km or 0.0
            for a in acts
            if to_local_date(a.start_utc, me.tz) - timedelta(
                days=to_local_date(a.start_utc, me.tz).weekday()
            ) == monday
        )
        weekly.append({"week": monday.isoformat(), "km": round(km, 1)})

    runs = [a for a in acts if a.type == "run"]
    return {
        "weekly_km": weekly,
        "streak": calc_streak(
            {to_local_date(a.start_utc, me.tz) for a in acts}, me.tz
        ),
        "total_km": round(sum(a.distance_km or 0.0 for a in acts), 1),
        "total_activities": len(acts),
        "total_runs": len(runs),
        "longest_run_km": round(max((a.distance_km or 0 for a in runs)), 1) if runs else 0,
        "last_activity": acts[0] if acts else None,
        "recent": acts[:10],
        "metrics": [
            {
                "date": m.date.isoformat(),
                "resting_hr": m.resting_hr,
                "sleep_hours": m.sleep_hours,
                "sleep_score": m.sleep_score,
                "stress": m.stress,
                "vo2max": m.vo2max,
            }
            for m in metrics[:60]
        ],
    }


# ---------- Ingestión de CSVs de Fitbit ----------
@app.post("/api/ingest/files")
def ingest_files(
    files: List[UploadFile] = File(...),
    me: User = Depends(get_current_user),
):
    """Sync (FastAPI la corre en threadpool): no bloquea el event loop."""
    activities, workouts, metrics = [], [], []
    errors = []
    for f in files:
        content = f.file.read()
        try:
            text = content.decode("utf-8-sig")
            kind, items = detect_and_parse(text, me.tz)
        except (ValueError, UnicodeDecodeError) as e:
            errors.append(f"{f.filename}: {e}")
            continue
        if kind == "activities":
            activities.extend(items)
        elif kind == "workouts":
            workouts.extend(items)
        else:
            metrics.extend(items)

    # Unir RPE del WorkoutSummaries por proximidad de horario (±3 min)
    for a in activities:
        best = None
        for w in workouts:
            diff = abs((a["start_utc"] - w["start_utc"]).total_seconds())
            if diff <= 180 and (best is None or diff < best[0]):
                best = (diff, w)
        if best:
            a["rpe"] = best[1]["rpe"]

    a_added = a_skipped = 0
    m_added = m_updated = 0
    with Session(engine) as s:
        for a in activities:
            if a.get("external_id"):
                exists = s.exec(
                    select(Activity).where(
                        Activity.user_id == me.id,
                        Activity.external_id == a["external_id"],
                    )
                ).first()
                if exists:
                    a_skipped += 1
                    continue
            s.add(Activity(user_id=me.id, **a))
            a_added += 1

        for m in metrics:
            row = s.exec(
                select(DailyMetric).where(
                    DailyMetric.user_id == me.id, col(DailyMetric.date) == m["date"]
                )
            ).first()
            if row:
                for k, v in m.items():
                    if k != "date" and v is not None:
                        setattr(row, k, v)
                m_updated += 1
            else:
                s.add(DailyMetric(user_id=me.id, **m))
                m_added += 1
        s.commit()

    return {
        "activities_added": a_added,
        "activities_skipped": a_skipped,
        "metrics_added": m_added,
        "metrics_updated": m_updated,
        "errors": errors,
    }


# ---------- Frontend estático ----------
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web")
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
