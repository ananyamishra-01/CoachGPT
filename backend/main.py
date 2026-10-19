"""
CoachGPT - AI fitness and nutrition coach (API server).

Run from this folder:   uvicorn main:app --reload --port 8000
Then open:              http://localhost:8000
(The API also serves the ../frontend folder, so one terminal is enough.)
"""

import os
import json
from datetime import date
from typing import Optional, Literal

from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

import config
import db
import chat
import planner

db.init_db()
print(f"CoachGPT starting with LLM_PROVIDER={config.LLM_PROVIDER}")
print(f"Database file: {db.DB_PATH}")

app = FastAPI(title="CoachGPT API")

# CORS lets the frontend (served from another port during development) call
# the API. If you ever host this publicly, restrict allow_origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """Turn Pydantic's error list into one readable sentence for the UI."""
    parts = []
    for e in exc.errors():
        field = ".".join(str(x) for x in e["loc"] if x != "body")
        parts.append(f"{field}: {e['msg']}" if field else e["msg"])
    return JSONResponse(status_code=422, content={"detail": "; ".join(parts)})


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
Goal = Literal["weight_loss", "weight_gain", "maintenance"]
Diet = Literal["vegan", "vegetarian", "eggetarian", "non_vegetarian"]


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("username")
    @classmethod
    def clean_username(cls, v: str) -> str:
        v = v.strip()
        if not all(ch.isalnum() or ch in "_.-" for ch in v):
            raise ValueError("use only letters, numbers, dots, dashes and underscores")
        return v


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=30)
    password: str = Field(min_length=1, max_length=128)


class ProfileIn(BaseModel):
    goal: Goal
    diet: Diet
    experience: Literal["beginner", "intermediate", "advanced"]
    equipment: Literal["none", "home_basic", "full_gym"]
    height_cm: float = Field(ge=120, le=230)
    current_weight_kg: float = Field(ge=35, le=250)
    goal_weight_kg: float = Field(ge=35, le=250)
    daily_budget: float = Field(ge=40, le=20000)
    daily_calorie_target: Optional[int] = Field(default=None, ge=1200, le=5000)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)


class MealPlanRequest(BaseModel):
    diet: Optional[Diet] = None
    goal: Optional[Goal] = None
    daily_budget: Optional[float] = Field(default=None, ge=40, le=20000)


class ProgressEntry(BaseModel):
    entry_date: Optional[str] = None
    weight_kg: Optional[float] = Field(default=None, ge=35, le=250)
    goal_percent_complete: int = Field(ge=0, le=100)
    workout_done: bool = False
    workout_type: Optional[Literal[
        "strength", "cardio", "hiit", "yoga_mobility", "sports", "walk", "other"
    ]] = None
    workout_minutes: Optional[int] = Field(default=None, ge=0, le=300)
    protein_g: Optional[int] = Field(default=None, ge=0, le=500)
    water_glasses: Optional[int] = Field(default=None, ge=0, le=30)
    meal_plan_followed: bool = False
    mood_note: Optional[str] = Field(default=None, max_length=300)


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------
def current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Please log in.")
    token = authorization[7:].strip()
    user = db.user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Your session has expired. Please log in again.")
    user["token"] = token
    return user


def _profile_bundle(user_id: int) -> dict:
    profile = db.get_profile(user_id)
    return {"profile": profile, "targets": planner.compute_targets(profile) if profile else None}


# ---------------------------------------------------------------------------
# Routes: health and accounts
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok", "provider": config.LLM_PROVIDER}


@app.post("/api/auth/register")
def register(body: RegisterIn):
    user_id = db.create_user(body.username, body.password)
    if user_id is None:
        raise HTTPException(status_code=409, detail="That username is already taken.")
    return {"token": db.create_token(user_id), "username": body.username, "profile": None, "targets": None}


@app.post("/api/auth/login")
def login(body: LoginIn):
    user = db.verify_user(body.username.strip(), body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password.")
    return {"token": db.create_token(user["id"]), "username": user["username"], **_profile_bundle(user["id"])}


@app.post("/api/auth/logout")
def logout(user: dict = Depends(current_user)):
    db.delete_token(user["token"])
    return {"ok": True}


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return {"username": user["username"], **_profile_bundle(user["id"])}


# ---------------------------------------------------------------------------
# Routes: profile
# ---------------------------------------------------------------------------
@app.put("/api/profile")
def save_profile(body: ProfileIn, user: dict = Depends(current_user)):
    data = body.model_dump()
    try:
        planner.validate_profile(data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    existing = db.get_profile(user["id"])
    same_goal = existing and existing.get("goal") == data["goal"]
    data["start_weight_kg"] = (
        existing.get("start_weight_kg", data["current_weight_kg"]) if same_goal else data["current_weight_kg"]
    )
    db.save_profile(user["id"], data)
    return {"profile": data, "targets": planner.compute_targets(data)}


# ---------------------------------------------------------------------------
# Routes: chat (streamed)
# ---------------------------------------------------------------------------
@app.post("/api/chat")
def chat_route(req: ChatRequest, user: dict = Depends(current_user)):
    if config.LLM_PROVIDER == "gemini" and not config.API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured on server")

    profile = db.get_profile(user["id"])
    targets = planner.compute_targets(profile) if profile else None
    system_prompt = chat.build_system_prompt(profile, targets)
    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    def event_stream():
        try:
            if config.LLM_PROVIDER == "mock":
                source = chat.mock_chat_stream(profile, targets, messages)
            else:
                source = chat.gemini_chat_stream(system_prompt, messages)
            for text in source:
                yield f"data: {json.dumps({'delta': text})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Routes: meal plan
# ---------------------------------------------------------------------------
@app.post("/api/meal-plan")
def meal_plan(req: MealPlanRequest, user: dict = Depends(current_user)):
    profile = db.get_profile(user["id"])
    if not profile:
        raise HTTPException(status_code=400, detail="Please complete your profile first.")

    plan_profile = {
        **profile,
        "diet": req.diet or profile["diet"],
        "goal": req.goal or profile["goal"],
    }
    budget = req.daily_budget or profile["daily_budget"]
    targets = planner.compute_targets(plan_profile)

    plan = planner.generate_meal_plan(plan_profile, targets, budget)
    plan["coach_note"], plan["note_source"] = chat.coach_note(plan, plan_profile, targets)
    plan["targets"] = targets
    return plan


# ---------------------------------------------------------------------------
# Routes: daily progress
# ---------------------------------------------------------------------------
def _progress_payload(user_id: int) -> dict:
    profile = db.get_profile(user_id)
    entries = db.get_progress(user_id)
    listing = [{"date": d, **e} for d, e in sorted(entries.items(), reverse=True)]
    payload = {"entries": listing, "profile": profile, "targets": None, "summary": None}
    if profile:
        payload["targets"] = planner.compute_targets(profile)
        payload["summary"] = planner.progress_summary(profile, entries, date.today())
    return payload


@app.get("/api/progress")
def get_progress(user: dict = Depends(current_user)):
    return _progress_payload(user["id"])


@app.post("/api/progress")
def log_progress(entry: ProgressEntry, user: dict = Depends(current_user)):
    try:
        entry_date = date.fromisoformat(entry.entry_date) if entry.entry_date else date.today()
    except ValueError:
        raise HTTPException(status_code=422, detail="entry_date must look like 2026-10-14.")
    if entry_date > date.today():
        raise HTTPException(status_code=422, detail="You can't log a day in the future.")

    data = entry.model_dump(exclude={"entry_date"})
    if not data["workout_done"]:
        data["workout_type"], data["workout_minutes"] = None, None
    db.upsert_progress(user["id"], entry_date.isoformat(), data)

    # Keep the profile's current weight in sync with the newest weigh-in, so
    # calorie and protein targets follow the user's real weight.
    profile = db.get_profile(user["id"])
    if profile:
        weighed = {d: e["weight_kg"] for d, e in db.get_progress(user["id"]).items() if e.get("weight_kg")}
        if weighed:
            profile["current_weight_kg"] = weighed[max(weighed)]
            db.save_profile(user["id"], profile)

    return {"saved": True, "date": entry_date.isoformat(), **_progress_payload(user["id"])}


# ---------------------------------------------------------------------------
# Serve the frontend from the same server (no second terminal needed).
# ---------------------------------------------------------------------------
_here = os.path.dirname(os.path.abspath(__file__))
for _candidate in (os.path.join(_here, "static"), os.path.join(_here, "..", "frontend")):
    if os.path.isdir(_candidate):
        app.mount("/", StaticFiles(directory=_candidate, html=True), name="frontend")
        break
