from sqlalchemy import select
from models import City,Provider, Resource, Segment, University, User
from pathlib import Path

ORIGINS = [("Riga", "Latvia"), ("Tallinn", "Estonia"), ("Vilnius", "Lithuania"),
           ("Warsaw", "Poland"), ("Berlin", "Germany"), ("Amsterdam", "Netherlands"),
           ("Brussels", "Belgium"), ("Prague", "Czechia"), ("Vienna", "Austria"), ("Paris", "France")]

DESTINATIONS = [("Madrid", "Spain"), ("Barcelona", "Spain"), ("Valencia", "Spain"),
                ("Seville", "Spain"), ("Paris", "France"), ("Lyon", "France"),
                ("Berlin", "Germany"), ("Munich", "Germany"), ("Rome", "Italy"), ("Milan", "Italy")]

UNIVERSITIES = [("University of Latvia", "Riga"),
                ("Universidad Politécnica de Madrid", "Madrid"),
                ("Freie Universität Berlin", "Berlin"),
                ("Sorbonne Université", "Paris"),
                ("University of Warsaw", "Warsaw")]

# from, to, mode, provider, minutes, km, price €, CO2 kg. Seeded in both directions.
EDGES = [
    ("Riga", "Tallinn", "bus", "LuxExpress (mock)", 270, 310, 15, 6),
    ("Riga", "Vilnius", "bus", "FlixBus (mock)", 270, 285, 12, 7),
    ("Riga", "Warsaw", "bus", "FlixBus (mock)", 765, 1000, 35, 18),
    ("Riga", "Berlin", "bus", "Eurolines (mock)", 1320, 1800, 60, 25),
    ("Vilnius", "Warsaw", "bus", "FlixBus (mock)", 420, 330, 25, 9),
    ("Warsaw", "Berlin", "train", "Intercity (mock)", 510, 570, 55, 12),
    ("Warsaw", "Prague", "train", "EuroCity (mock)", 480, 650, 50, 10),
    ("Prague", "Berlin", "train", "EuroCity (mock)", 270, 350, 40, 6),
    ("Prague", "Vienna", "train", "RailJet (mock)", 240, 330, 30, 4),
    ("Berlin", "Amsterdam", "train", "ICE (mock)", 360, 650, 70, 8),
    ("Berlin", "Paris", "train", "ICE (mock)", 510, 1050, 90, 9),
    ("Berlin", "Brussels", "train", "ICE (mock)", 420, 760, 75, 8),
    ("Berlin", "Munich", "train", "ICE (mock)", 360, 585, 65, 7),
    ("Berlin", "Madrid", "train", "ICE + TGV (mock)", 960, 2200, 140, 22),
    ("Brussels", "Amsterdam", "train", "Eurostar (mock)", 180, 210, 45, 3),
    ("Amsterdam", "Paris", "train", "Thalys (mock)", 210, 500, 60, 4),
    ("Paris", "Lyon", "train", "TGV (mock)", 120, 465, 50, 3),
    ("Paris", "Barcelona", "train", "TGV (mock)", 390, 830, 85, 10),
    ("Lyon", "Milan", "train", "TGV (mock)", 360, 470, 60, 5),
    ("Lyon", "Barcelona", "train", "TGV (mock)", 360, 520, 70, 6),
    ("Munich", "Milan", "train", "EuroCity (mock)", 360, 480, 55, 6),
    ("Munich", "Vienna", "train", "RailJet (mock)", 270, 435, 45, 5),
    ("Vienna", "Rome", "bus", "FlixBus (mock)", 780, 1100, 55, 15),
    ("Milan", "Rome", "train", "Italo (mock)", 210, 575, 60, 4),
    ("Barcelona", "Madrid", "train", "AVE (mock)", 150, 620, 45, 4),
    ("Barcelona", "Valencia", "train", "AVE (mock)", 180, 350, 40, 3),
    ("Valencia", "Madrid", "train", "AVE (mock)", 150, 355, 35, 3),
    ("Madrid", "Seville", "train", "AVE (mock)", 150, 535, 45, 4),
]

RESOURCES = [("Green Travel Grant Agreement", "agreement", True),
             ("Green Travel Requirements", "requirements", True),
             ("Mobility Guidelines", "other", False)]
PROVIDERS = [
    # name, mode, website, rating, review_count
    ("LuxExpress (mock)", "bus", "https://www.luxexpress.eu", 4.3, 1820),
    ("FlixBus (mock)", "bus", "https://www.flixbus.com", 4.1, 15400),
    ("Eurolines (mock)", "bus", "https://www.eurolines.eu", 3.9, 2300),
    ("Intercity (mock)", "train", "https://www.intercity.pl", 4.2, 5100),
    ("EuroCity (mock)", "train", "https://www.eurocity.example", 4.4, 3100),
    ("RailJet (mock)", "train", "https://www.railjet.com", 4.6, 4200),
    ("ICE (mock)", "train", "https://www.bahn.de", 4.4, 22000),
    ("ICE + TGV (mock)", "train", "https://www.bahn.de", 4.2, 3800),
    ("Eurostar (mock)", "train", "https://www.eurostar.com", 4.5, 9700),
    ("Thalys (mock)", "train", "https://www.eurostar.com", 4.0, 2500),
    ("TGV (mock)", "train", "https://www.sncf-connect.com", 4.4, 18600),
    ("Italo (mock)", "train", "https://www.italotreno.it", 4.5, 7300),
    ("AVE (mock)", "train", "https://www.renfe.com", 4.3, 11200),
]


def run(db):
    if db.scalar(select(City.id).limit(1)):
        return

    cities = {}
    for name, country in ORIGINS:
        cities[name] = City(name=name, country=country, is_origin=True, is_destination=False)
    for name, country in DESTINATIONS:
        if name in cities:
            cities[name].is_destination = True
        else:
            cities[name] = City(name=name, country=country, is_origin=False, is_destination=True)
    db.add_all(cities.values())
    db.flush()

    unis = {name: University(name=name, city=cities[city]) for name, city in UNIVERSITIES}
    db.add_all(unis.values())
    db.flush()

    providers = {}
    for name, mode, url, rating, reviews in PROVIDERS:
        providers[name] = Provider(name=name, mode=mode, website_url=url,
                                   rating=rating, review_count=reviews)
    db.add_all(providers.values())
    db.flush()

    lu = unis["University of Latvia"]
    upm = unis["Universidad Politécnica de Madrid"]
    db.add_all([
        User(email="dn24002@edu.lu.lv", username="Deepthi", role="student",
             home_university_id=lu.id, host_university_id=upm.id),
        User(email="erasmus_upm@ecorasmus.eu", username="UPM International Office",
             role="university", university_id=upm.id),
        User(email="erasmus_lu@ecorasmus.eu", username="University of Latvia Erasmus Office",
             role="university", university_id=lu.id),
    ])

    for a, b, mode, provider_name, mins, km, price, co2 in EDGES:
        p = providers[provider_name]
        for o, d in ((a, b), (b, a)):
            db.add(Segment(origin=cities[o], destination=cities[d], provider=p, mode=mode,
                           duration_min=mins, distance_km=km, price_eur=price, co2_kg=co2,
                           booking_url=f"{p.website_url}?from={o}&to={d}"))

    Path("uploads/resources").mkdir(parents=True, exist_ok=True)
    for title, type_, required in RESOURCES:
        fname = title.lower().replace(" ", "_") + ".txt"
        stored = f"resources/{fname}"
        Path("uploads", stored).write_text(
            f"{title}\n\nPlaceholder. The university replaces this with the real document.\n")
        db.add(Resource(university_id=upm.id, title=title, type=type_, required=required,
                        file_name=fname, stored_name=stored))

    db.commit()