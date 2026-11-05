from datetime import date, datetime

from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Integer,
                        String, Text, UniqueConstraint, create_engine)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

engine = create_engine("sqlite:///./ecorasmus.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class City(Base):
    __tablename__ = "cities"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    country: Mapped[str] = mapped_column(String(80))
    is_origin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_destination: Mapped[bool] = mapped_column(Boolean, default=False)


class University(Base):
    __tablename__ = "universities"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"))
    city: Mapped[City] = relationship()


class User(Base):
    """role = 'student' or 'university'. Students have home/host uni, university admins have university_id."""
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    username: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))
    home_university_id: Mapped[int | None] = mapped_column(ForeignKey("universities.id"))
    host_university_id: Mapped[int | None] = mapped_column(ForeignKey("universities.id"))
    university_id: Mapped[int | None] = mapped_column(ForeignKey("universities.id"))

class Provider(Base):
    """A bus or train company. Rating is shown to students when they compare legs."""
    __tablename__ = "providers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    mode: Mapped[str] = mapped_column(String(10))  # train | bus
    website_url: Mapped[str] = mapped_column(String(300))
    rating: Mapped[float] = mapped_column(Float)   # out of 5
    review_count: Mapped[int] = mapped_column(Integer, default=0)

class Segment(Base):
    """One bus or train leg between two cities, operated by a provider."""
    __tablename__ = "segments"
    id: Mapped[int] = mapped_column(primary_key=True)
    origin_city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"))
    destination_city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"))
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"))
    mode: Mapped[str] = mapped_column(String(10))  # train | bus
    duration_min: Mapped[int] = mapped_column(Integer)
    distance_km: Mapped[float] = mapped_column(Float)
    price_eur: Mapped[float] = mapped_column(Float)
    co2_kg: Mapped[float] = mapped_column(Float)
    booking_url: Mapped[str] = mapped_column(String(300))  # route-specific link on the provider site
    origin: Mapped[City] = relationship(foreign_keys=[origin_city_id])
    destination: Mapped[City] = relationship(foreign_keys=[destination_city_id])
    provider: Mapped[Provider] = relationship()


class Journey(Base):
    """A saved journey built by a student. status: just_saved | sent_to_uni."""
    __tablename__ = "journeys"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    origin_city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"))
    destination_city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"))
    travel_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="just_saved")
    notes: Mapped[str | None] = mapped_column(Text)
    total_distance_km: Mapped[float] = mapped_column(Float, default=0)
    total_duration_min: Mapped[int] = mapped_column(Integer, default=0)
    total_price_eur: Mapped[float] = mapped_column(Float, default=0)
    total_co2_kg: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    origin: Mapped[City] = relationship(foreign_keys=[origin_city_id])
    destination: Mapped[City] = relationship(foreign_keys=[destination_city_id])
    legs: Mapped[list["JourneyLeg"]] = relationship(
        back_populates="journey", order_by="JourneyLeg.position", cascade="all, delete-orphan")


class JourneyLeg(Base):
    """
    One leg of a saved journey. Details are copied when the leg is added, so later
    price changes don't change the student's plan. Custom legs have segment_id = None.
    """
    __tablename__ = "journey_legs"
    id: Mapped[int] = mapped_column(primary_key=True)
    journey_id: Mapped[int] = mapped_column(ForeignKey("journeys.id"))
    position: Mapped[int] = mapped_column(Integer)
    segment_id: Mapped[int | None] = mapped_column(ForeignKey("segments.id"))
    from_city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"))
    to_city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"))
    mode: Mapped[str] = mapped_column(String(10))
    provider_id: Mapped[int | None] = mapped_column(ForeignKey("providers.id"))
    provider_name: Mapped[str] = mapped_column(String(120))
    departure_at: Mapped[datetime] = mapped_column(DateTime)
    duration_min: Mapped[int] = mapped_column(Integer)
    distance_km: Mapped[float] = mapped_column(Float, default=0)
    price_eur: Mapped[float] = mapped_column(Float)
    co2_kg: Mapped[float] = mapped_column(Float)
    booking_url: Mapped[str | None] = mapped_column(String(300))
    note: Mapped[str | None] = mapped_column(Text)
    journey: Mapped[Journey] = relationship(back_populates="legs")
    from_city: Mapped[City] = relationship(foreign_keys=[from_city_id])
    to_city: Mapped[City] = relationship(foreign_keys=[to_city_id])
    provider: Mapped[Provider | None] = relationship()
    documents: Mapped[list["Document"]] = relationship(back_populates="leg")

class Ticket(Base):
    """One ticket per student, university and destination. Journeys and reports for that pair stay on it."""
    __tablename__ = "tickets"
    __table_args__ = (UniqueConstraint("student_id", "university_id", "destination_city_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id"))
    destination_city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"))
    status: Mapped[str] = mapped_column(String(25), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    destination: Mapped[City] = relationship()


class SentJourney(Base):
    """
    A journey sent to a university.
    stage: journey (journey request) | grant (final report, parent_id points to the approved journey).
    status: pending | approved | rejected | need_edits (need_edits = changes requested / documents requested).
    """
    __tablename__ = "sent_journeys"
    id: Mapped[int] = mapped_column(primary_key=True)
    journey_id: Mapped[int] = mapped_column(ForeignKey("journeys.id"))
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id"))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("sent_journeys.id"))
    stage: Mapped[str] = mapped_column(String(10), default="journey")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    student_summary: Mapped[str | None] = mapped_column(Text)
    university_notes: Mapped[str | None] = mapped_column(Text)
    extra_travel_days: Mapped[int | None] = mapped_column(Integer)
    repayment_amount_eur: Mapped[float | None] = mapped_column(Float)
    repayment_deadline: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    submitted_snapshot: Mapped[str | None] = mapped_column(Text)  # JSON: what was last sent
    journey: Mapped[Journey] = relationship()


class Document(Base):
    """Tickets and travel proof attached to a leg, or extra documents attached to a final report."""
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    leg_id: Mapped[int | None] = mapped_column(ForeignKey("journey_legs.id"))
    sent_journey_id: Mapped[int | None] = mapped_column(ForeignKey("sent_journeys.id"))
    doc_type: Mapped[str] = mapped_column(String(30))  # ticket | boarding_pass | stamped_ticket | other
    file_name: Mapped[str] = mapped_column(String(255))   # original name shown to users
    stored_name: Mapped[str | None] = mapped_column(String(300))  # name on disk in uploads/
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    leg: Mapped[JourneyLeg | None] = relationship(back_populates="documents")

class Resource(Base):
    """Files a university publishes. Archived versions are hidden from students but kept on record."""
    __tablename__ = "resources"
    id: Mapped[int] = mapped_column(primary_key=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id"))
    title: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(20))
    file_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str | None] = mapped_column(String(300))
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Signature(Base):
    __tablename__ = "signatures"
    __table_args__ = (UniqueConstraint("student_id", "resource_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"))
    signed_name: Mapped[str] = mapped_column(String(120))
    signed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ResourceSubmission(Base):
    """The filled and signed copy a student uploads for a resource. One per student and resource."""
    __tablename__ = "resource_submissions"
    __table_args__ = (UniqueConstraint("student_id", "resource_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"))
    file_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(300))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(engine)