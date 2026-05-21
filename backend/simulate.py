import requests
import random
import time
import sqlite3
from datetime import datetime, timedelta

API_URL = "http://127.0.0.1:8000/api/reviews"
DB_PATH = "reputation.db"

REVIEWS_POOL = {
    "positive": [
        {"text": "Absolutely incredible burger! The staff was super friendly.", "stars": 5},
        {"text": "Best spot in downtown! Fast service and great atmosphere.", "stars": 5},
        {"text": "Loved it. The fries were perfectly crispy. Will be coming back.", "stars": 5},
        {"text": "Consistently excellent. My go-to place for a quick lunch.", "stars": 4},
        {"text": "Great value for the money. The new menu items are fantastic.", "stars": 4},
        {"text": "Clean tables, fast service, and the food was hot. 10/10.", "stars": 5},
        {"text": "The spicy chicken sandwich is out of this world.", "stars": 5},
        {"text": "Always fresh, always fast. Management runs a tight ship here.", "stars": 5},
        {"text": "Perfectly cooked patties. Definitely the best burger chain in the city.", "stars": 5},
        {"text": "I appreciate the vegetarian options! Really tasty and well prepared.", "stars": 4},
        {"text": "Cashier was incredibly polite and helpful with my allergies.", "stars": 5},
        {"text": "The milkshakes are thick and amazing. Great stop after work.", "stars": 4},
        {"text": "Mobile order was ready exactly on time. Flawless execution.", "stars": 5},
        {"text": "Prices are unbeatable for the quality of ingredients they use.", "stars": 5},
        {"text": "Store was spotless, even during the lunch rush.", "stars": 4},
        {"text": "Generous portion sizes! I always leave completely stuffed.", "stars": 5},
        {"text": "They actually get the custom orders right every single time.", "stars": 5},
        {"text": "The new manager has really turned this location around. Great job.", "stars": 4},
        {"text": "Drive-thru was blazing fast today. Impressed.", "stars": 5},
        {"text": "Fresh lettuce and tomatoes, nothing looked wilted. Great quality control.", "stars": 4},
        {"text": "My kids love the meals here. Very family-friendly environment.", "stars": 5},
        {"text": "Honestly, the best fast-casual experience I've had in months.", "stars": 5},
        {"text": "Sauce selection is top tier. Keep it up!", "stars": 4},
        {"text": "Parking is easy, ordering is fast, food is great. Zero complaints.", "stars": 5},
        {"text": "They gave me extra fries at the bottom of the bag. Legends.", "stars": 5}
    ],
    "neutral": [
        {"text": "Standard fast food. Nothing special but hits the spot.", "stars": 3},
        {"text": "Food was okay, but the line was way too long.", "stars": 3},
        {"text": "Decent prices, but the tables were a bit messy.", "stars": 3},
        {"text": "It's alright. They forgot my extra sauce, but the burger was fine.", "stars": 3},
        {"text": "Average experience. Good for a quick bite if you're in a rush.", "stars": 3},
        {"text": "Burger was good, fries were a bit soggy today.", "stars": 3},
        {"text": "Gets the job done when you don't want to cook.", "stars": 3},
        {"text": "Loud music, but the food came out reasonably fast.", "stars": 3},
        {"text": "A bit overpriced for what you get, but convenient location.", "stars": 3},
        {"text": "Drive-thru line moves slowly, but the order was correct.", "stars": 3},
        {"text": "Nothing to write home about, just your standard burger joint.", "stars": 3},
        {"text": "They were out of ketchup in the lobby, otherwise fine.", "stars": 3},
        {"text": "Food is decent, but the parking lot is a nightmare to get out of.", "stars": 3},
        {"text": "Bathroom needed paper towels. Burger was fresh though.", "stars": 3},
        {"text": "Hit or miss. Today was just okay.", "stars": 3},
        {"text": "I wish they had more drink options, but the food is passable.", "stars": 3},
        {"text": "Not bad, not great. Perfectly mediocre.", "stars": 3},
        {"text": "Staff seemed a bit stressed, but they got my food out.", "stars": 3},
        {"text": "Tastes exactly like every other location. Predictable.", "stars": 3},
        {"text": "Wait was about 15 minutes, slightly longer than expected.", "stars": 3},
        {"text": "The app crashed when I ordered, but ordering inside was fine.", "stars": 3},
        {"text": "Meat was slightly dry, but the toppings made up for it.", "stars": 3},
        {"text": "Fine for a road trip stop, wouldn't go out of my way for it.", "stars": 3},
        {"text": "The seasonal item isn't that great, stick to the classics.", "stars": 3},
        {"text": "Adequate. I have no strong feelings about this meal.", "stars": 3}
    ],
    "negative": [
        {"text": "Terrible experience. The fries were cold and the meat was raw.", "stars": 1},
        {"text": "Waited 45 minutes for my order. Management didn't even apologize.", "stars": 1},
        {"text": "I found a hair in my food. Disgusting. I demand a refund.", "stars": 1},
        {"text": "Rude cashier. Got my order completely wrong. Never coming back.", "stars": 1},
        {"text": "The bun was soggy and the restaurant smelled terrible.", "stars": 2},
        {"text": "Overpriced garbage. Save your money and go somewhere else.", "stars": 1},
        {"text": "The manager ignored us when we complained about the cold food.", "stars": 1},
        {"text": "Completely messed up my allergy request. This is dangerous!", "stars": 1},
        {"text": "Trash cans were overflowing and tables were sticky. Gross.", "stars": 1},
        {"text": "Burger was completely burnt. Unedible.", "stars": 1},
        {"text": "Watched the cook handle raw meat and then touch the buns. Health hazard.", "stars": 1},
        {"text": "Sat in the drive-thru for 25 minutes just to be told their system is down.", "stars": 2},
        {"text": "The soda machine was broken and they refused to give me a refund.", "stars": 1},
        {"text": "Found plastic wrap baked into my cheese.", "stars": 1},
        {"text": "Order was missing three items. Check your bags before leaving!", "stars": 2},
        {"text": "Staff was literally yelling at each other in the kitchen. Very unprofessional.", "stars": 1},
        {"text": "Worst meal I've had in years. Everything was stale.", "stars": 1},
        {"text": "The place is infested with flies. Couldn't even eat in peace.", "stars": 1},
        {"text": "They charge extra for every little thing now. Total ripoff.", "stars": 2},
        {"text": "Given someone else's half-eaten order. I am horrified.", "stars": 1},
        {"text": "They closed 20 minutes early and locked the doors while I was walking up.", "stars": 1},
        {"text": "Food was dripping in grease, completely ruined my shirt.", "stars": 2},
        {"text": "Manager was incredibly condescending when I asked for a napkin.", "stars": 1},
        {"text": "Chicken was completely raw in the middle. Reporting to health inspector.", "stars": 1},
        {"text": "Avoid this location at all costs. The one across town is much better.", "stars": 1},
        {"text": "Oh absolutely stunning. Waited 40 minutes for a cold burger. Five stars, truly.", "stars": 5},
        {"text": "Amazing how they manage to get my order wrong every single time. Talent.", "stars": 4},
        {"text": "Love finding mystery ingredients in my food. Keeps life exciting. Highly recommend.", "stars": 5},
        {"text": "Phenomenal experience. The staff ignored us for 20 minutes straight. World class service.", "stars": 5},
        {"text": "Brilliant. Ordered a chicken sandwich, received what I can only describe as a science experiment.", "stars": 4},
        {"text": "Truly a gem. The bathroom hasn't been cleaned since the location opened, I'm sure of it.", "stars": 3},
        {"text": "Outstanding. Got home to find half my order missing. The surprise really adds to the experience.", "stars": 2},
        {"text": "Really impressive how the fries were simultaneously burnt on the outside and frozen in the middle. Skill.", "stars": 2},
        {"text": "Would absolutely recommend if you enjoy being spoken to like an inconvenience. Ten out of ten.", "stars": 1},
        {"text": "Incredible value. Paid premium price for a bun with a rumor of a patty inside. Worth every penny.", "stars": 1},
    ]
}

# --- DATABASE HELPERS ---
def wipe_database():
    print(" Wiping old database records...")
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM reviews")
        conn.execute("UPDATE sqlite_sequence SET seq = 0 WHERE name = 'reviews'")

def resolve_historical_tickets():
    print(" Backdating 'Time to Resolution' for historical tickets...")
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT review_id, review_timestamp FROM reviews WHERE ticket_status = 'Open'")
        open_tickets = cursor.fetchall()
        
        resolved_count = 0
        for ticket in open_tickets:
            if random.random() < 0.75: # 75% auto-resolve rate
                t1 = datetime.strptime(ticket["review_timestamp"], "%Y-%m-%d %H:%M:%S")
                resolution_time = t1 + timedelta(hours=random.randint(1, 14), minutes=random.randint(0, 59))
                
                cursor.execute(
                    "UPDATE reviews SET ticket_status = 'Resolved', resolved_at = ? WHERE review_id = ?", 
                    (resolution_time.strftime("%Y-%m-%d %H:%M:%S"), ticket["review_id"])
                )
                resolved_count += 1
                
        print(f" Realistically resolved {resolved_count} out of {len(open_tickets)} historical issues.\n")

# --- SIMULATION HELPERS ---
def generate_random_time_in_week(weeks_ago):
    start_of_week = datetime.now() - timedelta(days=(weeks_ago * 7))
    random_days = random.randint(0, 6)
    hour = random.choice([11, 12, 13, 14, 17, 18, 19, 20, 21, 22, 10, 23])
    minute = random.randint(0, 59)
    past_date = start_of_week + timedelta(days=random_days)
    return past_date.replace(hour=hour, minute=minute, second=0).strftime("%Y-%m-%d %H:%M:%S")

# --- CORE EXECUTION ---
def run_enterprise_seed(target_restaurants):
    wipe_database()
    print(f"\n Seeding historical data for Restaurants: {target_restaurants}")
    
    total_expected = len(target_restaurants) * 4 * 8
    total_sent = 0
    
    # Using a Session makes 180 sequential API calls significantly faster
    with requests.Session() as session:
        # session.proxies = {"http": None, "https": None}
        session.trust_env = False
        
        for rest_id in target_restaurants:
            for weeks_ago in [4, 3, 2, 1]:
                for _ in range(8):
                    sentiment_category = random.choices(["positive", "neutral", "negative"], weights=[35, 20, 45], k=1)[0]
                    review_data = random.choice(REVIEWS_POOL[sentiment_category])
                    
                    payload = {
                        "restaurant_id": rest_id,
                        "review_text": review_data["text"],
                        "star_rating": review_data["stars"],
                        "review_timestamp": generate_random_time_in_week(weeks_ago)
                    }
                    
                    try:
                        res = session.post(API_URL, json=payload)
                        if res.status_code == 200:
                            total_sent += 1
                            if total_sent % 30 == 0:
                                print(f"   ... Processed {total_sent}/{total_expected} reviews")
                        else:
                            print(f" Seed rejected (HTTP {res.status_code}): {res.text}")
                    except Exception as e:
                        print(f" API Error: {e}")
                    
    print("ML Ingestion Complete!")
    resolve_historical_tickets()

# --- COMBINED SIMULATION SERVICE ---
def run_combined_simulation(state):
    """
    Backend-triggered simulation service called from main.py in a background thread.
    Orchestrates: seeding phase -> live stream phase -> idle.
    Accepts a mutable 'state' dict owned by main.py and updates it throughout.
    """
    MAX_RUNTIME = 150  # 120s live stream + 30s safety buffer
    wall_start = time.time()

    try:
        # Dynamically fetch real restaurant IDs from the DB — never assume [1, 2, 3]
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            rows = conn.execute("SELECT restaurant_id FROM restaurants ORDER BY restaurant_id").fetchall()
        restaurant_ids = [row[0] for row in rows]
        if not restaurant_ids:
            raise RuntimeError("No restaurants found in DB. Cannot run simulation.")
        print(f" Found restaurants: {restaurant_ids}")

        # Phase 1 — Historical Seed (phase already set to 'seeding' by main.py)
        run_enterprise_seed(restaurant_ids)

        # Phase 2 — Live Stream
        state["phase"] = "live"
        state["live_start_time"] = time.time()

        with requests.Session() as session:
            # session.proxies = {"http": None, "https": None}
            session.trust_env = False
            for i in range(12):
                # Hard timeout: abort if total wall-clock time is exceeded
                if time.time() - wall_start > MAX_RUNTIME:
                    break

                rest_id = random.choice(restaurant_ids)
                category = random.choices(["negative", "neutral"], weights=[70, 30])[0]
                review = random.choice(REVIEWS_POOL[category])
                payload = {
                    "restaurant_id": rest_id,
                    "review_text": review["text"],
                    "star_rating": review["stars"],
                    "review_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                try:
                    res = session.post(API_URL, json=payload)
                    if res.status_code == 200:
                        state["reviews_sent"] = i + 1
                    else:
                        print(f" Live review rejected (HTTP {res.status_code}): {res.text}")
                except Exception as e:
                    print(f" Live review API error: {e}")

                if i < 11:  # No sleep after the final review
                    time.sleep(10)

    except Exception as e:
        state["error"] = str(e)
        state["phase"] = "error"
    finally:
        state["running"] = False
        # Preserve 'error' phase so the UI can display it; otherwise reset to idle
        if state.get("phase") != "error":
            state["phase"] = "idle"