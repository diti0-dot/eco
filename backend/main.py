from datetime import date, datetime, time, timedelta
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi.responses import FileResponse
import uuid
import json
from pathlib import Path
from fastapi import File, Form, UploadFile
import seed
from models import (City, Document, Provider, Journey, JourneyLeg, Resource, SentJourney,
                    Segment, SessionLocal, Signature, University, User, Base, engine,ResourceSubmission,Ticket)

Base.metadata.create_all(engine)
with SessionLocal() as _db:
    seed.run(_db)

app = FastAPI(title="Ecorasmus API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
LAYOVER_MIN = 90  
DOC_TYPES = {"ticket", "boarding_pass", "stamped_ticket", "other"}
PROOF_TYPES = {"boarding_pass", "stamped_ticket", "other"}
DECISIONS = {"approved", "rejected", "need_edits"}


# ---------- schemas ----------
class LoginIn(BaseModel):
    email: str

class LegIn(BaseModel):
    segment_id: int | None = None          # set for legs from the segments table
    # Custom legs (segment_id = None) need these fields:
    from_city_id: int | None = None
    to_city_id: int | None = None
    mode: str | None = None
    provider_id: int | None = None
    provider_name: str | None = None
    duration_min: int | None = None
    price_eur: float | None = None
    co2_kg: float | None = None
    distance_km: float | None = None
    departure_at: datetime | None = None   # if missing, the leg starts after the previous one
    note: str | None = None

class JourneyIn(BaseModel):
    student_id: int
    origin_city_id: int
    destination_city_id: int
    travel_date: date
    start_time: time = time(8, 0)          # start of the first leg when no departure is given
    legs: list[LegIn]
    notes: str | None = None

class DocIn(BaseModel):
    doc_type: str
    file_name: str

class ReviewIn(BaseModel):
    decision: str  # approved | rejected | need_edits
    notes: str | None = None
    extra_travel_days: int | None = None          # journey approvals
    repayment_amount_eur: float | None = None     # grant rejections
    repayment_deadline: date | None = None        # grant rejections

class ReportIn(BaseModel):
    summary: str
    extra_docs: list[DocIn] = []

class ResourceIn(BaseModel):
    title: str
    type: str
    file_name: str
    required: bool = True

class SignIn(BaseModel):
    signed_name: str


# ---------- helpers ----------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_or_404(db: Session, model, obj_id: int):
    obj = db.get(model, obj_id)
    if not obj:
        raise HTTPException(404, f"{model.__name__} {obj_id} not found")
    return obj

def uni_of(db: Session, user_id: int) -> int:
    user = get_or_404(db, User, user_id)
    if user.role != "university":
        raise HTTPException(403, "Not a university account")
    return user.university_id

# def load_segments(db: Session, ids: list[int]) -> list[Segment]:
#     segs = [db.get(Segment, i) for i in ids]
#     if not segs or any(s is None for s in segs):
#         raise HTTPException(400, "Unknown or empty segment list")
#     return segs


def build_legs(db: Session, items: list[LegIn], travel_date: date, start_time: time) -> list[JourneyLeg]:
    if not items:
        raise HTTPException(400, "A journey needs at least one leg")
    legs: list[JourneyLeg] = []
    cursor = datetime.combine(travel_date, start_time)
    for i, item in enumerate(items):
        if item.segment_id is not None:
            s = db.get(Segment, item.segment_id)
            if not s:
                raise HTTPException(400, f"Unknown segment {item.segment_id}")
            fields = dict(segment_id=s.id, from_city_id=s.origin_city_id,
                          to_city_id=s.destination_city_id, mode=s.mode,
                          provider_id=s.provider_id, provider_name=s.provider.name,
                          duration_min=s.duration_min, distance_km=s.distance_km,
                          price_eur=s.price_eur, co2_kg=s.co2_kg, booking_url=s.booking_url)
        else:
            provider_id, provider_name = item.provider_id, item.provider_name
            if provider_id is not None:
                p = db.get(Provider, provider_id)
                if not p:
                    raise HTTPException(400, f"Unknown provider {provider_id}")
                provider_name = p.name
            needed = (item.from_city_id, item.to_city_id, item.mode, provider_name,
                      item.duration_min, item.price_eur, item.co2_kg)
            if any(v is None for v in needed):
                raise HTTPException(400, "Custom legs need from, to, mode, provider, duration, price and CO2")
            fields = dict(segment_id=None, from_city_id=item.from_city_id,
                          to_city_id=item.to_city_id, mode=item.mode,
                          provider_id=provider_id, provider_name=provider_name,
                          duration_min=item.duration_min, distance_km=item.distance_km or 0,
                          price_eur=item.price_eur, co2_kg=item.co2_kg, booking_url=None)
        departure = item.departure_at or cursor
        legs.append(JourneyLeg(position=i, note=item.note, departure_at=departure, **fields))
        cursor = departure + timedelta(minutes=fields["duration_min"] + LAYOVER_MIN)
    return legs

def validate_chain(legs: list[JourneyLeg], origin_id: int, dest_id: int):
    if legs[0].from_city_id != origin_id or legs[-1].to_city_id != dest_id:
        raise HTTPException(400, "Legs must start at origin and end at destination")
    for a, b in zip(legs, legs[1:]):
        if a.to_city_id != b.from_city_id:
            raise HTTPException(400, f"Leg {b.position + 1} doesn't start where the previous leg ends")

def provider_out(l: JourneyLeg) -> dict:
    if l.provider:
        p = l.provider
        return {"id": p.id, "name": p.name, "rating": p.rating,
                "review_count": p.review_count, "website_url": p.website_url}
    return {"id": None, "name": l.provider_name, "rating": None,
            "review_count": None, "website_url": None}

# def make_legs(legs: list[LegIn]) -> list[JourneyLeg]:
#     return [JourneyLeg(segment_id=l.segment_id, position=i, note=l.note) for i, l in enumerate(legs)]

def totals(segs) -> dict:
    return {
        "total_distance_km": round(sum(s.distance_km for s in segs), 1),
        "total_duration_min": sum(s.duration_min for s in segs),
        "total_price_eur": round(sum(s.price_eur for s in segs), 2),
        "total_co2_kg": round(sum(s.co2_kg for s in segs), 1),
    }

def grade(co2_kg: float, distance_km: float) -> str:
    """A-E badge from kg CO2 per km (mock thresholds)."""
    per_km = co2_kg / distance_km if distance_km else 0
    for limit, letter in [(0.015, "A"), (0.02, "B"), (0.025, "C"), (0.03, "D")]:
        if per_km <= limit:
            return letter
    return "E"

def find_routes(db: Session, origin_id: int, dest_id: int, max_legs=6, limit=10):
    graph: dict[int, list[Segment]] = {}
    for s in db.scalars(select(Segment)):
        graph.setdefault(s.origin_city_id, []).append(s)

    routes: list[list[Segment]] = []

    def dfs(city, path, visited):
        if len(path) >= max_legs:
            return
        for seg in graph.get(city, []):
            if seg.destination_city_id in visited:
                continue
            path.append(seg)
            if seg.destination_city_id == dest_id:
                routes.append(list(path))
            else:
                visited.add(seg.destination_city_id)
                dfs(seg.destination_city_id, path, visited)
                visited.remove(seg.destination_city_id)
            path.pop()

    dfs(origin_id, [], {origin_id})
    routes.sort(key=lambda r: (sum(s.co2_kg for s in r), sum(s.price_eur for s in r)))
    return routes[:limit]

def leg_out(l: JourneyLeg) -> dict:
    """A leg inside a saved journey, with its times and documents."""
    return {"leg_id": l.id, "position": l.position, "note": l.note,
            "segment_id": l.segment_id,
            "from_city_id": l.from_city_id, "to_city_id": l.to_city_id,
            "from": l.from_city.name, "to": l.to_city.name, "mode": l.mode,
            "provider_id": l.provider_id, "provider": provider_out(l),
            "departure_at": l.departure_at,
            "arrival_at": l.departure_at + timedelta(minutes=l.duration_min),
            "duration_min": l.duration_min, "distance_km": l.distance_km,
            "price_eur": l.price_eur, "co2_kg": l.co2_kg, "booking_url": l.booking_url,
            "documents": [doc_out(d) for d in l.documents]}

def segment_out(s: Segment) -> dict:
    """A segment shown in search results. No times yet, since the student hasn't chosen them."""
    p = s.provider
    return {"segment_id": s.id, "from_city_id": s.origin_city_id, "to_city_id": s.destination_city_id,
            "from": s.origin.name, "to": s.destination.name, "mode": s.mode,
            "provider_id": p.id,
            "provider": {"id": p.id, "name": p.name, "rating": p.rating,
                         "review_count": p.review_count, "website_url": p.website_url},
            "duration_min": s.duration_min, "distance_km": s.distance_km,
            "price_eur": s.price_eur, "co2_kg": s.co2_kg, "booking_url": s.booking_url}

def doc_out(d: Document) -> dict:
    return {"id": d.id, "doc_type": d.doc_type, "file_name": d.file_name,
            "uploaded_at": d.uploaded_at, "has_file": bool(d.stored_name)}

def journey_out(j: Journey) -> dict:
    return {
        "id": j.id, "status": j.status,
        "origin_city_id": j.origin_city_id, "destination_city_id": j.destination_city_id,
        "origin": j.origin.name, "destination": j.destination.name,
        "travel_date": j.travel_date, "notes": j.notes,
        **{k: getattr(j, k) for k in ("total_distance_km", "total_duration_min",
                                      "total_price_eur", "total_co2_kg")},
        "green_grade": grade(j.total_co2_kg, j.total_distance_km),
        "legs": [leg_out(l) for l in j.legs],
    }

def sent_out(sj: SentJourney) -> dict:
    return {"id": sj.id, "journey_id": sj.journey_id, "stage": sj.stage, "status": sj.status,
            "parent_id": sj.parent_id, "student_summary": sj.student_summary,
            "university_notes": sj.university_notes, "extra_travel_days": sj.extra_travel_days,
            "repayment_amount_eur": sj.repayment_amount_eur,
            "repayment_deadline": sj.repayment_deadline,
            "created_at": sj.created_at, "updated_at": sj.updated_at}

def request_out(db: Session, sj: SentJourney) -> dict:
    student = db.get(User, sj.student_id)
    extras = db.scalars(select(Document).where(Document.sent_journey_id == sj.id)).all()
    return {**sent_out(sj), "student": student.username,
            "journey": journey_out(sj.journey),
            "extra_documents": [doc_out(d) for d in extras],
            "changes": report_changes(db, sj)}

def active_request(db: Session, journey_id: int):
    return db.scalar(select(SentJourney).where(
        SentJourney.journey_id == journey_id, SentJourney.stage == "journey",
        SentJourney.status.in_(["pending", "approved"])))

def approved_request(db: Session, journey_id: int):
    return db.scalar(select(SentJourney).where(
        SentJourney.journey_id == journey_id, SentJourney.stage == "journey",
        SentJourney.status == "approved"))


def report_snapshot(db: Session, report: SentJourney) -> dict:
    """What the grant report contains right now: the summary and every document ID."""
    parent = db.get(SentJourney, report.parent_id)
    leg_docs = [d.id for leg in parent.journey.legs for d in leg.documents]
    extra_docs = [d.id for d in db.scalars(select(Document).where(
        Document.sent_journey_id == report.id))]
    return {"summary": report.student_summary or "",
            "leg_docs": sorted(leg_docs), "extra_docs": sorted(extra_docs)}

def report_changes(db: Session, report: SentJourney) -> dict | None:
    """Compares the report with the snapshot taken at the last submission."""
    if report.stage != "grant" or not report.submitted_snapshot:
        return None
    old = json.loads(report.submitted_snapshot)
    new = report_snapshot(db, report)
    added = (len(set(new["leg_docs"]) - set(old["leg_docs"]))
             + len(set(new["extra_docs"]) - set(old["extra_docs"])))
    removed = (len(set(old["leg_docs"]) - set(new["leg_docs"]))
               + len(set(old["extra_docs"]) - set(new["extra_docs"])))
    summary_changed = new["summary"] != old["summary"]
    return {"added_docs": added, "removed_docs": removed, "summary_changed": summary_changed,
            "has_changes": bool(added or removed or summary_changed)}

def get_or_create_ticket(db: Session, student_id: int, university_id: int, destination_id: int) -> Ticket:
    t = db.scalar(select(Ticket).where(Ticket.student_id == student_id,
                                       Ticket.university_id == university_id,
                                       Ticket.destination_city_id == destination_id))
    if not t:
        t = Ticket(student_id=student_id, university_id=university_id,
                   destination_city_id=destination_id, status="open")
        db.add(t)
        db.flush()
    return t

def refresh_ticket(db: Session, t: Ticket):
    """Recalculates the ticket status from its journey request and grant report."""
    db.flush()
    sent = db.scalars(select(SentJourney).where(SentJourney.ticket_id == t.id)
                      .order_by(SentJourney.created_at.desc())).all()
    journey = next((s for s in sent if s.stage == "journey"), None)
    grant = next((s for s in sent if s.stage == "grant"), None)
    if grant and grant.status in ("approved", "rejected"):
        t.status = "closed"
    elif any(s.status == "pending" for s in sent):
        t.status = "open"
    elif any(s.status == "need_edits" for s in sent) or (journey and journey.status == "rejected"):
        t.status = "awaiting_response"
    elif journey and journey.status == "approved":
        t.status = "no_response_required"
    else:
        t.status = "open"
    t.updated_at = datetime.utcnow()

def ticket_sent(db: Session, t: Ticket):
    sent = db.scalars(select(SentJourney).where(SentJourney.ticket_id == t.id)
                      .order_by(SentJourney.created_at.desc())).all()
    journey = next((s for s in sent if s.stage == "journey"), None)
    grant = next((s for s in sent if s.stage == "grant"), None)
    return journey, grant

def signed_documents(db: Session, student_id: int) -> list[dict]:
    out = []
    for sub in db.scalars(select(ResourceSubmission).where(ResourceSubmission.student_id == student_id)):
        sig = db.scalar(select(Signature).where(Signature.student_id == student_id,
                                                Signature.resource_id == sub.resource_id))
        if sig:
            res = db.get(Resource, sub.resource_id)
            out.append({"resource_id": res.id, "title": res.title, "file_name": sub.file_name,
                        "signed_name": sig.signed_name, "signed_at": sig.signed_at})
    return out

def ticket_row(db: Session, t: Ticket) -> dict:
    journey, grant = ticket_sent(db, t)
    student = db.get(User, t.student_id)
    proof_count = sum(len(l.documents) for l in journey.journey.legs) if journey else 0
    return {
        "id": t.id, "ticket_code": f"ECO-{t.id:04d}", "status": t.status,
        "student_id": t.student_id, "student": student.username, "email": student.email,
        "destination": t.destination.name, "updated_at": t.updated_at,
        "journey": {"id": journey.id, "status": journey.status,
                    "travel_date": journey.journey.travel_date} if journey else None,
        "report": {"id": grant.id, "status": grant.status} if grant else None,
        "proof_count": proof_count,
        "signed_documents": signed_documents(db, t.student_id),
    }


# ---------- auth and reference data ----------
@app.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email))
    if not user:
        raise HTTPException(404, "No account with that email")
    return {"id": user.id, "email": user.email, "username": user.username, "role": user.role,
            "home_university_id": user.home_university_id,
            "host_university_id": user.host_university_id, "university_id": user.university_id}

@app.get("/cities")
def list_cities(kind: str | None = None, db: Session = Depends(get_db)):
    q = select(City).order_by(City.name)
    if kind == "origin":
        q = q.where(City.is_origin.is_(True))
    elif kind == "destination":
        q = q.where(City.is_destination.is_(True))
    return [{"id": c.id, "name": c.name, "country": c.country} for c in db.scalars(q)]

@app.get("/universities")
def list_universities(db: Session = Depends(get_db)):
    return [{"id": u.id, "name": u.name, "city": u.city.name}
            for u in db.scalars(select(University).order_by(University.name))]

@app.get("/providers")
def list_providers(mode: str | None = None, db: Session = Depends(get_db)):
    q = select(Provider).order_by(Provider.rating.desc())
    if mode in ("train", "bus"):
        q = q.where(Provider.mode == mode)
    return [{"id": p.id, "name": p.name, "mode": p.mode, "rating": p.rating,
             "review_count": p.review_count, "website_url": p.website_url}
            for p in db.scalars(q)]


# ---------- search and saved journeys (student) ----------
@app.get("/search")
def search(origin_id: int, destination_id: int, travel_date: date, db: Session = Depends(get_db)):
    plans = []
    for segs in find_routes(db, origin_id, destination_id):
        t = totals(segs)
        plans.append({"legs": [segment_out(s) for s in segs], **t,
                      "green_grade": grade(t["total_co2_kg"], t["total_distance_km"])})
    return {"travel_date": travel_date, "plans": plans}

@app.post("/journeys")
def save_journey(body: JourneyIn, db: Session = Depends(get_db)):
    legs = build_legs(db, body.legs, body.travel_date, body.start_time)
    validate_chain(legs, body.origin_city_id, body.destination_city_id)
    j = Journey(student_id=body.student_id, origin_city_id=body.origin_city_id,
                destination_city_id=body.destination_city_id, travel_date=body.travel_date,
                notes=body.notes, status="just_saved", legs=legs, **totals(legs))
    db.add(j)
    db.commit()
    return journey_out(j)

@app.get("/students/{student_id}/journeys")
def student_journeys(student_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(select(Journey).where(Journey.student_id == student_id)).all()
    return [journey_out(j) for j in rows]

@app.get("/journeys/{journey_id}")
def get_journey(journey_id: int, db: Session = Depends(get_db)):
    return journey_out(get_or_404(db, Journey, journey_id))

@app.put("/journeys/{journey_id}")
def edit_journey(journey_id: int, body: JourneyIn, db: Session = Depends(get_db)):
    j = get_or_404(db, Journey, journey_id)
    if active_request(db, j.id):
        raise HTTPException(409, "Journey is pending or approved and can't be edited")
    legs = build_legs(db, body.legs, body.travel_date, body.start_time)
    validate_chain(legs, body.origin_city_id, body.destination_city_id)
    j.origin_city_id = body.origin_city_id
    j.destination_city_id = body.destination_city_id
    j.travel_date = body.travel_date
    j.notes = body.notes
    j.legs = legs  # old legs are removed by delete-orphan
    for k, v in totals(legs).items():
        setattr(j, k, v)
    db.commit()
    db.refresh(j)
    return journey_out(j)

@app.post("/journeys/{journey_id}/send")
def send_journey(journey_id: int, db: Session = Depends(get_db)):
    j = get_or_404(db, Journey, journey_id)
    if active_request(db, j.id):
        raise HTTPException(409, "Journey is already sent")
    student = get_or_404(db, User, j.student_id)
    if not student.home_university_id:
        raise HTTPException(400, "Student has no home university set")
    ticket = get_or_create_ticket(db, student.id, student.home_university_id, j.destination_city_id)
    sj = SentJourney(journey_id=j.id, student_id=j.student_id, stage="journey", status="pending",
                     university_id=student.home_university_id, ticket_id=ticket.id)
    j.status = "sent_to_uni"
    db.add(sj)
    refresh_ticket(db, ticket)
    db.commit()
    return sent_out(sj)


# ---------- tickets and proof (student) ----------
@app.post("/journey-legs/{leg_id}/documents")
def upload_leg_document(leg_id: int, body: DocIn, db: Session = Depends(get_db)):
    leg = get_or_404(db, JourneyLeg, leg_id)
    if body.doc_type not in DOC_TYPES:
        raise HTTPException(400, f"doc_type must be one of {sorted(DOC_TYPES)}")
    if not approved_request(db, leg.journey_id):
        raise HTTPException(409, "Journey must be approved before uploading documents")
    doc = Document(student_id=leg.journey.student_id, leg_id=leg.id,
                   doc_type=body.doc_type, file_name=body.file_name)
    db.add(doc)
    db.commit()
    return doc_out(doc)

@app.post("/journey-legs/{leg_id}/upload")
async def upload_leg_file(leg_id: int, doc_type: str = Form(...),
                          file: UploadFile = File(...), db: Session = Depends(get_db)):
    leg = get_or_404(db, JourneyLeg, leg_id)
    if doc_type not in DOC_TYPES:
        raise HTTPException(400, f"doc_type must be one of {sorted(DOC_TYPES)}")
    if not approved_request(db, leg.journey_id):
        raise HTTPException(409, "Journey must be approved before uploading documents")

    original = Path(file.filename or "upload").name
    stored = f"{uuid.uuid4().hex}_{original}"
    (UPLOAD_DIR / stored).write_bytes(await file.read())

    doc = Document(student_id=leg.journey.student_id, leg_id=leg.id, doc_type=doc_type,
                   file_name=original, stored_name=stored)
    db.add(doc)
    db.commit()
    return doc_out(doc)

@app.get("/documents/{doc_id}/file")
def view_document(doc_id: int, db: Session = Depends(get_db)):
    doc = get_or_404(db, Document, doc_id)
    path = UPLOAD_DIR / doc.stored_name if doc.stored_name else None
    if not path or not path.exists():
        raise HTTPException(404, "No file stored for this document")
    # No filename argument, so the browser displays the file instead of downloading it.
    return FileResponse(path)

@app.delete("/documents/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    doc = get_or_404(db, Document, doc_id)

    if doc.sent_journey_id:
        report = get_or_404(db, SentJourney, doc.sent_journey_id)
        if report.status != "need_edits":
            raise HTTPException(409, "Report documents can only be removed when the university has requested documents")
    if doc.leg_id:
        approved = approved_request(db, doc.leg.journey_id)
        if not approved:
            raise HTTPException(409, "Documents can only be changed on an approved journey")
        locked = db.scalar(select(SentJourney.id).where(
            SentJourney.parent_id == approved.id,
            SentJourney.status.in_(["pending", "approved"])))
        if locked:
            raise HTTPException(409, "The final report is already submitted, so documents are locked")
    if doc.stored_name:
        (UPLOAD_DIR / doc.stored_name).unlink(missing_ok=True)
    db.delete(doc)
    db.commit()
    return {"deleted": doc_id}


def file_response(stored: str | None, name: str, download: bool):
    path = UPLOAD_DIR / stored if stored else None
    if not path or not path.exists():
        raise HTTPException(404, "No file stored")
    return FileResponse(path, filename=name if download else None)

def submission_out(s: ResourceSubmission) -> dict:
    return {"id": s.id, "file_name": s.file_name, "uploaded_at": s.uploaded_at}

@app.get("/resources/{resource_id}/file")
def view_resource(resource_id: int, download: bool = False, db: Session = Depends(get_db)):
    r = get_or_404(db, Resource, resource_id)
    return file_response(r.stored_name, r.file_name, download)

@app.post("/students/{student_id}/resources/{resource_id}/submission")
async def upload_submission(student_id: int, resource_id: int,
                            file: UploadFile = File(...), db: Session = Depends(get_db)):
    student = get_or_404(db, User, student_id)
    res = get_or_404(db, Resource, resource_id)
    if res.university_id != student.home_university_id:
        raise HTTPException(403, "Resource is not from this student's home university")
    if res.archived:
        raise HTTPException(409, "This document was replaced. Upload the current version.")
    if db.scalar(select(Signature.id).where(Signature.student_id == student_id,
                                            Signature.resource_id == resource_id)):
        raise HTTPException(409, "Already signed and sent. The document can't be changed.")

    old = db.scalar(select(ResourceSubmission).where(ResourceSubmission.student_id == student_id,
                                                     ResourceSubmission.resource_id == resource_id))
    if old:
        (UPLOAD_DIR / old.stored_name).unlink(missing_ok=True)
        db.delete(old)
        db.flush()

    original = Path(file.filename or "upload").name
    stored = f"submissions/{uuid.uuid4().hex}_{original}"
    path = UPLOAD_DIR / stored
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(await file.read())

    sub = ResourceSubmission(student_id=student_id, resource_id=resource_id,
                             file_name=original, stored_name=stored)
    db.add(sub)
    db.commit()
    return submission_out(sub)

@app.get("/students/{student_id}/resources/{resource_id}/submission/file")
def view_submission(student_id: int, resource_id: int, download: bool = False,
                    db: Session = Depends(get_db)):
    sub = db.scalar(select(ResourceSubmission).where(ResourceSubmission.student_id == student_id,
                                                     ResourceSubmission.resource_id == resource_id))
    if not sub:
        raise HTTPException(404, "No upload for this resource")
    return file_response(sub.stored_name, sub.file_name, download)

# ---------- final report (student) ----------
@app.get("/students/{student_id}/sent-journeys")
def student_sent(student_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(select(SentJourney).where(SentJourney.student_id == student_id)
                      .order_by(SentJourney.created_at.desc())).all()
    return [request_out(db, r) for r in rows]

@app.post("/sent-journeys/{sj_id}/final-report")
def submit_report(sj_id: int, body: ReportIn, db: Session = Depends(get_db)):
    parent = get_or_404(db, SentJourney, sj_id)
    if parent.stage != "journey" or parent.status != "approved":
        raise HTTPException(409, "Journey must be approved before submitting a report")
    existing = db.scalar(select(SentJourney).where(
        SentJourney.parent_id == parent.id,
        SentJourney.status.in_(["pending", "approved", "rejected", "need_edits"])))
    if existing:
        raise HTTPException(409, "A final report already exists. Resubmit it if documents were requested.")
    for d in body.extra_docs:
        if d.doc_type not in DOC_TYPES:
            raise HTTPException(400, f"doc_type must be one of {sorted(DOC_TYPES)}")
    report = SentJourney(journey_id=parent.journey_id, student_id=parent.student_id,
                         university_id=parent.university_id, parent_id=parent.id,
                         ticket_id=parent.ticket_id, stage="grant", status="pending",
                         student_summary=body.summary)
    db.add(report)
    db.flush()
    for d in body.extra_docs:
        db.add(Document(student_id=parent.student_id, sent_journey_id=report.id,
                        doc_type=d.doc_type, file_name=d.file_name))
    db.flush()
    report.submitted_snapshot = json.dumps(report_snapshot(db, report))
    if parent.ticket_id:
        refresh_ticket(db, db.get(Ticket, parent.ticket_id))
    db.commit()
    return request_out(db, report)


# ---------- university inbox and review ----------
def inbox(db: Session, user_id: int, stage: str):
    uni_id = uni_of(db, user_id)
    rows = db.scalars(select(SentJourney).where(
        SentJourney.university_id == uni_id, SentJourney.stage == stage)
        .order_by(SentJourney.created_at.desc())).all()
    return [request_out(db, r) for r in rows]

@app.get("/university/{user_id}/journey-requests")
def journey_requests(user_id: int, db: Session = Depends(get_db)):
    return inbox(db, user_id, "journey")

@app.get("/university/{user_id}/grant-requests")
def grant_requests(user_id: int, db: Session = Depends(get_db)):
    return inbox(db, user_id, "grant")

@app.patch("/sent-journeys/{sj_id}/review")
def review(sj_id: int, body: ReviewIn, db: Session = Depends(get_db)):
    sj = get_or_404(db, SentJourney, sj_id)
    if sj.status != "pending":
        raise HTTPException(409, "Only pending requests can be reviewed")
    if body.decision not in DECISIONS:
        raise HTTPException(400, f"decision must be one of {sorted(DECISIONS)}")
    sj.status = body.decision
    sj.university_notes = body.notes
    sj.updated_at = datetime.utcnow()
    if sj.stage == "journey":
        if body.decision == "approved":
            sj.extra_travel_days = body.extra_travel_days or 0
        if body.decision == "rejected":
            sj.journey.status = "just_saved"
    elif body.decision == "rejected":
        sj.repayment_amount_eur = body.repayment_amount_eur
        sj.repayment_deadline = body.repayment_deadline

    if sj.ticket_id:
        refresh_ticket(db, db.get(Ticket, sj.ticket_id))
    db.commit()
    return request_out(db, sj)

class ResubmitIn(BaseModel):
    summary: str

@app.post("/sent-journeys/{sj_id}/resubmit")
def resubmit_report(sj_id: int, body: ResubmitIn, db: Session = Depends(get_db)):
    report = get_or_404(db, SentJourney, sj_id)
    if report.stage != "grant" or report.status != "need_edits":
        raise HTTPException(409, "Only reports with requested documents can be resubmitted")
    if not body.summary.strip():
        raise HTTPException(400, "Write a short summary")
    report.student_summary = body.summary.strip()
    db.flush()
    if not report_changes(db, report)["has_changes"]:
        raise HTTPException(409, "Nothing has changed since the last submission")
    report.submitted_snapshot = json.dumps(report_snapshot(db, report))
    report.status = "pending"
    report.updated_at = datetime.utcnow()
    if report.ticket_id:
        refresh_ticket(db, db.get(Ticket, report.ticket_id))
    db.commit()
    return request_out(db, report)

@app.post("/sent-journeys/{sj_id}/report-documents")
async def upload_report_file(sj_id: int, doc_type: str = Form(...),
                             file: UploadFile = File(...), db: Session = Depends(get_db)):
    report = get_or_404(db, SentJourney, sj_id)
    if report.stage != "grant" or report.status != "need_edits":
        raise HTTPException(409, "Documents can only be added when the university has requested them")
    if doc_type not in DOC_TYPES:
        raise HTTPException(400, f"doc_type must be one of {sorted(DOC_TYPES)}")
    original = Path(file.filename or "upload").name
    stored = f"reports/{uuid.uuid4().hex}_{original}"
    path = UPLOAD_DIR / stored
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(await file.read())
    doc = Document(student_id=report.student_id, sent_journey_id=report.id,
                   doc_type=doc_type, file_name=original, stored_name=stored)
    db.add(doc)
    db.commit()
    return doc_out(doc)

@app.get("/sent-journeys/{sj_id}")
def get_sent_journey(sj_id: int, db: Session = Depends(get_db)):
    return request_out(db, get_or_404(db, SentJourney, sj_id))

@app.get("/university/{user_id}/tickets")
def university_tickets(user_id: int, db: Session = Depends(get_db)):
    uni_id = uni_of(db, user_id)
    rows = db.scalars(select(Ticket).where(Ticket.university_id == uni_id)
                      .order_by(Ticket.updated_at.desc())).all()
    return [ticket_row(db, t) for t in rows]

@app.get("/tickets/{ticket_id}")
def ticket_detail(ticket_id: int, db: Session = Depends(get_db)):
    t = get_or_404(db, Ticket, ticket_id)
    journey, grant = ticket_sent(db, t)
    return {**ticket_row(db, t),
            "journey_request": request_out(db, journey) if journey else None,
            "grant_report": request_out(db, grant) if grant else None}


# ---------- resources and signing ----------
@app.get("/universities/{uni_id}/resources")
def public_resources(uni_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(select(Resource).where(Resource.university_id == uni_id,
                                             Resource.archived.is_(False))).all()
    return [{"id": r.id, "title": r.title, "type": r.type, "file_name": r.file_name,
             "required": r.required, "has_file": bool(r.stored_name)} for r in rows]

@app.post("/university/{user_id}/resources")
def upload_resource(user_id: int, body: ResourceIn, db: Session = Depends(get_db)):
    uni_id = uni_of(db, user_id)
    r = Resource(university_id=uni_id, title=body.title, type=body.type,
                 file_name=body.file_name, required=body.required)
    db.add(r)
    db.commit()
    return {"id": r.id, "title": r.title, "type": r.type, "required": r.required}


@app.post("/university/{user_id}/resources/upload")
async def upload_resource_file(user_id: int, title: str = Form(...), type: str = Form(...),
                               required: bool = Form(True), file: UploadFile = File(...),
                               db: Session = Depends(get_db)):
    uni_id = uni_of(db, user_id)
    if type not in {"agreement", "requirements", "other"}:
        raise HTTPException(400, "type must be agreement, requirements or other")
    if not title.strip():
        raise HTTPException(400, "Title is required")
    original = Path(file.filename or "upload").name
    stored = f"resources/{uuid.uuid4().hex}_{original}"
    path = UPLOAD_DIR / stored
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(await file.read())
    r = Resource(university_id=uni_id, title=title.strip(), type=type,
                 file_name=original, stored_name=stored, required=required)
    db.add(r)
    db.commit()
    return {"id": r.id, "title": r.title, "type": r.type, "required": r.required,
            "has_file": True}
def resource_for_uni(db: Session, user_id: int, resource_id: int) -> Resource:
    uni_id = uni_of(db, user_id)
    r = get_or_404(db, Resource, resource_id)
    if r.university_id != uni_id:
        raise HTTPException(403, "This resource belongs to another university")
    if r.archived:
        raise HTTPException(409, "This resource has been replaced or archived")
    return r

def retire_resource(db: Session, r: Resource) -> str:
    """Deletes a resource nobody has signed. Archives one that has signatures. Returns what happened."""
    signed = db.scalar(select(Signature.id).where(Signature.resource_id == r.id))
    if signed:
        r.archived = True
        return "archived"
    for sub in db.scalars(select(ResourceSubmission).where(ResourceSubmission.resource_id == r.id)).all():
        (UPLOAD_DIR / sub.stored_name).unlink(missing_ok=True)
        db.delete(sub)
    if r.stored_name:
        (UPLOAD_DIR / r.stored_name).unlink(missing_ok=True)
    db.delete(r)
    return "deleted"

@app.delete("/university/{user_id}/resources/{resource_id}")
def delete_resource(user_id: int, resource_id: int, db: Session = Depends(get_db)):
    r = resource_for_uni(db, user_id, resource_id)
    result = retire_resource(db, r)
    db.commit()
    message = ("Students have signed this document, so it was removed from their lists "
               "and kept on record." if result == "archived" else "Resource deleted.")
    return {"result": result, "message": message}

@app.post("/university/{user_id}/resources/{resource_id}/replace")
async def replace_resource(user_id: int, resource_id: int,
                           file: UploadFile = File(...), db: Session = Depends(get_db)):
    old = resource_for_uni(db, user_id, resource_id)
    original = Path(file.filename or "upload").name
    stored = f"resources/{uuid.uuid4().hex}_{original}"
    path = UPLOAD_DIR / stored
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(await file.read())

    new = Resource(university_id=old.university_id, title=old.title, type=old.type,
                   required=old.required, file_name=original, stored_name=stored)
    db.add(new)
    db.flush()
    old_result = retire_resource(db, old)
    db.commit()
    return {"id": new.id, "title": new.title, "type": new.type, "required": new.required,
            "has_file": True, "replaced": resource_id, "old_version": old_result,
            "message": "Students who signed the previous version must sign this new one."}

@app.get("/students/{student_id}/resources")
def student_resources(student_id: int, db: Session = Depends(get_db)):
    student = get_or_404(db, User, student_id)
    rows = db.scalars(select(Resource).where(
        Resource.university_id == student.home_university_id,
        Resource.archived.is_(False))).all()
    signed = {s.resource_id: s.signed_at for s in db.scalars(
        select(Signature).where(Signature.student_id == student_id))}
    subs = {s.resource_id: s for s in db.scalars(
        select(ResourceSubmission).where(ResourceSubmission.student_id == student_id))}
    return [{"id": r.id, "title": r.title, "type": r.type, "file_name": r.file_name,
             "required": r.required, "has_file": bool(r.stored_name),
             "signed_at": signed.get(r.id),
             "submission": submission_out(subs[r.id]) if r.id in subs else None}
            for r in rows]

@app.post("/students/{student_id}/resources/{resource_id}/sign")
def sign_resource(student_id: int, resource_id: int, body: SignIn, db: Session = Depends(get_db)):
    student = get_or_404(db, User, student_id)
    res = get_or_404(db, Resource, resource_id)
    if res.university_id != student.home_university_id:
        raise HTTPException(403, "Resource is not from this student's home university")
    if res.archived:
        raise HTTPException(409, "This document was replaced. Sign the current version.")
    if not body.signed_name.strip():
        raise HTTPException(400, "Full name is required")
    if not db.scalar(select(ResourceSubmission.id).where(
            ResourceSubmission.student_id == student_id,
            ResourceSubmission.resource_id == resource_id)):
        raise HTTPException(409, "Upload the signed document before signing")
    if db.scalar(select(Signature).where(Signature.student_id == student_id,
                                         Signature.resource_id == resource_id)):
        raise HTTPException(409, "Already signed")
    sig = Signature(student_id=student_id, resource_id=resource_id,
                    signed_name=body.signed_name.strip())
    db.add(sig)
    db.commit()
    return {"resource_id": resource_id, "signed_name": sig.signed_name, "signed_at": sig.signed_at}

@app.delete("/journeys/{journey_id}")
def delete_journey(journey_id: int, db: Session = Depends(get_db)):
    j = get_or_404(db, Journey, journey_id)
    if db.scalar(select(SentJourney.id).where(SentJourney.journey_id == j.id)):
        raise HTTPException(409, "Journey was sent to the university and can't be removed")
    db.delete(j)
    db.commit()
    return {"deleted": journey_id}

# ---------- student to-do list ----------
@app.get("/students/{student_id}/todo")
def todo(student_id: int, db: Session = Depends(get_db)):
    student = get_or_404(db, User, student_id)
    sent = db.scalars(select(SentJourney).where(SentJourney.student_id == student_id)).all()
    journey_reqs = [s for s in sent if s.stage == "journey"]
    approved = next((s for s in journey_reqs if s.status == "approved"), None)

    required_ids = set(db.scalars(select(Resource.id).where(
        Resource.university_id == student.home_university_id,
        Resource.required.is_(True), Resource.archived.is_(False))).all())
    signed_ids = set(db.scalars(select(Signature.resource_id).where(
        Signature.student_id == student_id)).all())

    

    tickets_done = proof_done = False
    if approved:
        legs = approved.journey.legs
        docs = [d for l in legs for d in l.documents]
        tickets_done = all(any(d.leg_id == l.id and d.doc_type == "ticket" for d in docs) for l in legs)
        proof_done = any(d.doc_type in PROOF_TYPES for d in docs)

    steps = [
        ("send_journey", "Send journey to university", bool(journey_reqs)),
        ("wait_review", "Wait for university review", approved is not None),
        ("sign", "Sign grant agreement and required resources", required_ids <= signed_ids),
        ("book_tickets", "Book tickets on provider sites", approved is not None),
        ("upload_tickets", "Upload tickets for each leg", tickets_done),
        ("upload_proof", "Upload travel proof", proof_done),
        ("submit_report", "Submit final report", any(s.stage == "grant" for s in sent)),
    ]
    result, previous_done = [], True
    for key, label, done in steps:
        result.append({"key": key, "label": label, "done": done, "locked": not previous_done})
        previous_done = done
    return result