from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import threading
import time
from database import get_db
import joblib
from datetime import datetime
from typing import Optional
import re
import spacy

# 1. APP INITIALIZATION
app = FastAPI(title="Sentiment Dashboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])


# 2. SIMULATION STATE 
# Mutable dict shared between main.py endpoints and the background simulation thread.
sim_state = {
    "running": False,
    "phase": "idle",        # "idle", "seeding", "live", "error"
    "reviews_sent": 0,
    "total_reviews": 12,
    "error": None,
    "live_start_time": None,
    "stop_requested": False,
}
simulation_thread = None


# 3. ML & NLP SETUP
try:
    # Load the pre-trained TF-IDF vectorizer to convert text into numbers
    vectorizer = joblib.load("models/tfidf_vectorizer.joblib")

    # Load the trained Logistic Regression model for classification
    classifier = joblib.load("models/logistic_regression_model.joblib")
    
    # Load spaCy's English model for advanced language processing (like grammar tagging)
    nlp = spacy.load("en_core_web_sm")
except Exception as e:
    print(f"ML models failed to Load: {e}")

def clean_and_negate_pipeline(text: str) -> str:
    """
    Cleans text and attaches 'not_' to negated words for better feature extraction 
    and contextual negation handling.
    """
    # return an empty string if the input isn't text.
    if not isinstance(text, str): 
        return ""
        
    # Remove URLs (http/https) and social media tags (@usernames) using Regex.
    text = re.sub(r"http\S+|@[\w]+", "", text)
    
    # Process text through spaCy to analyze grammar, parts of speech, and sentence structure.
    doc = nlp(text)
    
    # Track which words are negative words (e.g., 'not') and which words are being negated.
    negated_tokens, negation_words = set(), set()
    
    # Step 1: Find negations and the specific words they modify.
    for token in doc:
        # Check if the word dependency is a negation (like 'not' or 'never').
        if token.dep_ == "neg":
            negation_words.add(token)       # Save the negation word itself to remove later.
            negated_tokens.add(token.head)  # Save the parent word being negated (e.g., 'good' in 'not good').
            
            # Also catch any adjectives or adverbs modifying that same parent word (e.g., 'very' in 'not very good').
            for child in token.head.children:
                if child.pos_ in ["ADJ", "ADV"] and child != token:
                    negated_tokens.add(child)
                    
    # Step 2: Filter out noise and format the remaining words.
    cleaned_tokens = []
    for token in doc:
        # Skip negation words, punctuation, numbers, and standard stop words (unless the stop word is negated).
        if token in negation_words or token.is_punct or token.is_digit or (token.is_stop and token not in negated_tokens):
            continue
            
        # Strip out any remaining special characters, leaving only pure letters.
        pure_word = re.sub(r"[^a-zA-Z]", "", token.text).strip()
        if not pure_word: 
            continue
        
        # Convert word to its base form (lemmatization) and lowercase it (e.g., 'running' -> 'run').
        lemma = token.lemma_.lower()
        
        # Prefix the word with 'not_' if it was flagged in Step 1, otherwise keep it normal.
        cleaned_tokens.append(f"not_{lemma}" if token in negated_tokens else lemma)
        
    # Recombine the cleaned tokens back into a single string
    return " ".join(cleaned_tokens)


# 4. HELPER FUNCTIONS
def parse_timestamp(ts_str: str) -> Optional[datetime]:
    """Safely converts DB timestamp strings into Python datetime objects."""
    try:
        # Convert to string and clean formatting: replace 'T' separation with a space,
        # drop milliseconds (everything after the '.'), and strip trailing spaces.
        # Example: "2026-05-22T12:00:00.123Z" -> "2026-05-22 12:00:00"
        clean_time = str(ts_str).replace('T', ' ').split('.')[0].strip()
        
        # Turn the cleaned string into a proper, timezone-naive Python datetime object.
        return datetime.strptime(clean_time, "%Y-%m-%d %H:%M:%S")
    except Exception:
        # If the input format is corrupted or unexpected, fail softly by returning None.
        return None


# 5. API SCHEMAS
class ReviewIngest(BaseModel):
    """Defines the expected data structure and validation rules for incoming API reviews."""
    restaurant_id: int       # Database ID of the restaurant (must be a whole number).
    review_text: str         # The actual raw text comment written by the customer.
    star_rating: int         # The score given by the customer (e.g., 1 to 5).
    review_timestamp: str    # The original date/time string from the database payload.


# 6. API ENDPOINTS
@app.get("/api/dashboard")
def get_dashboard_metrics(restaurant_id: Optional[int] = None, db: sqlite3.Connection = Depends(get_db)):
    """
    Computes key performance indicators (KPIs) for the frontend dashboard.
    These metrics include Revenue at Risk, Shift Bottlenecks (Heatmap Data),
    and Average Time to Resolution (TTR).
    """
    cursor = db.cursor()
    
    # Base filtering logic to optionally restrict metrics to a specific restaurant
    filter_query = " AND restaurant_id = ?" if restaurant_id else ""
    params = (restaurant_id,) if restaurant_id else ()

    # 1. Revenue at Risk Calculation
    # Counts the total number of unresolved ('Open') tickets. 
    # Assumes an average potential loss of $50 per negative/unresolved review.
    cursor.execute(f"SELECT COUNT(*) FROM reviews WHERE ticket_status = 'Open'{filter_query}", params)
    revenue_at_risk = cursor.fetchone()[0] * 50
    
    # 2. Shift Bottleneck (Heatmap Data) Calculation
    # Identifies when negative reviews occur to pinpoint underperforming shifts.
    cursor.execute(f"SELECT review_timestamp FROM reviews WHERE predicted_sentiment = 'negative'{filter_query}", params)
    heatmap_data = {"Lunch": 0, "Dinner": 0, "Off-Hours": 0}
    
    for row in cursor.fetchall():
        dt = parse_timestamp(row["review_timestamp"])
        if not dt: 
            continue
            
        # Categorize the review time into specific operational shifts
        if 11 <= dt.hour <= 15: 
            heatmap_data["Lunch"] += 1
        elif 16 <= dt.hour <= 22: 
            heatmap_data["Dinner"] += 1
        else: 
            heatmap_data["Off-Hours"] += 1

    # 3. Average Time To Resolution (TTR) Calculation
    # Measures how quickly the support team is closing tickets.
    cursor.execute(f"SELECT review_timestamp, resolved_at FROM reviews WHERE ticket_status = 'Resolved' AND resolved_at IS NOT NULL{filter_query}", params)
    total_hours, valid_resolutions = 0, 0
    
    for row in cursor.fetchall():
        t1, t2 = parse_timestamp(row["review_timestamp"]), parse_timestamp(row["resolved_at"])
        if t1 and t2:
            # Calculate the difference in hours between when the ticket was created and resolved
            diff_hours = (t2 - t1).total_seconds() / 3600
            if diff_hours >= 0:
                total_hours += diff_hours
                valid_resolutions += 1

    # Return the compiled metrics as a structured JSON object for the frontend UI
    return {
        "open_tickets": revenue_at_risk // 50,
        "revenue_at_risk": revenue_at_risk,
        "heatmap_data": heatmap_data,
        "avg_ttr_hours": round(total_hours / valid_resolutions, 1) if valid_resolutions > 0 else 0
    }


@app.post("/api/reviews")
def ingest_review(review: ReviewIngest, db: sqlite3.Connection = Depends(get_db)):
    """
    Receives an incoming customer review, analyzes its sentiment using ML, 
    determines if a support ticket is needed, and saves everything to the database.
    """
    # 1. Clean the incoming text and convert it into numerical features for the model
    vectorized_text = vectorizer.transform([clean_and_negate_pipeline(review.review_text)])
    
    # 2. Predict the numerical class (0, 1, or 2) and extract it as a standard Python integer
    prediction_raw = classifier.predict(vectorized_text)[0].item()
    
    # 3. Get the model's confidence percentage (e.g., 0.85 means 85% confident in its choice)
    confidence = float(max(classifier.predict_proba(vectorized_text)[0]))
    
    # 4. Map the model's numerical guess to a human-readable text label (default to 'neutral')
    prediction_text = {0: 'negative', 1: 'neutral', 2: 'positive'}.get(prediction_raw, 'neutral')

    # 5. Flag anomalies where the stars don't match the written sentiment
    # (e.g., 5-star rating but the model thinks the text is 'negative', or vice-versa)
    is_anomaly = (review.star_rating >= 4 and prediction_text != 'positive') or \
                 (review.star_rating <= 2 and prediction_text == 'positive')
                 
    # 6. Business Logic: Automatically flag a support ticket if it's a bad review, 
    # neutral feedback, or if there's a weird mismatch (anomaly) that humans should check.
    ticket_status = 'Open' if prediction_text in ['negative', 'neutral'] or is_anomaly else 'None'

    # 7. Database Operations
    cursor = db.cursor()
    try:
        # Securely insert the clean data, model results, and ticket status into the DB
        cursor.execute(
            """INSERT INTO reviews (
                restaurant_id, review_text, star_rating, review_timestamp, 
                predicted_sentiment, confidence_score, ticket_status
            ) VALUES (?,?,?,?,?,?,?)""",
            (
                review.restaurant_id, review.review_text, review.star_rating, 
                review.review_timestamp, prediction_text, confidence, ticket_status
            )
        )
        # Commit changes to make them permanent in the database
        db.commit()
    
        # Return a clean JSON response back to the API client
        return {
            "status": "success", 
            "review_id": cursor.lastrowid, 
            "sentiment": prediction_text, 
            "ticket": ticket_status
        }
        
    except sqlite3.IntegrityError:
        # If database constraints fail (like a foreign key checking if the restaurant actually exists)
        raise HTTPException(status_code=400, detail="Invalid restaurant_id or DB Integrity Error")

@app.get("/api/tickets")
def get_all_tickets(restaurant_id: Optional[int] = None, db: sqlite3.Connection = Depends(get_db)):
    """
    Retrieves all open or resolved support tickets. 
    Can optionally filter results for a specific restaurant.
    """
    # Base SQL query: Joins reviews with restaurant names to get a complete picture
    query = """
        SELECT r.review_id, rest.name as restaurant_name, r.review_text, r.review_timestamp, 
               r.ticket_status, r.resolved_at, r.predicted_sentiment, r.confidence_score, r.star_rating
        FROM reviews r JOIN restaurants rest ON r.restaurant_id = rest.restaurant_id
        WHERE r.ticket_status IN ('Open', 'Resolved')
    """
    params = ()
    
    # Dynamic Filtering: If a restaurant ID is provided, append a safety placeholder (?) to the query
    if restaurant_id:
        query += " AND r.restaurant_id = ?"
        params = (restaurant_id,)  # Save the actual ID in a tuple to prevent SQL injection
        
    cursor = db.cursor()
    # Sort the final results so the newest reviews/tickets appear first
    cursor.execute(query + " ORDER BY r.review_timestamp DESC", params)
    
    # Convert sqlite3.Row objects into standard Python dictionaries for clean JSON output
    return {"tickets": [dict(row) for row in cursor.fetchall()]}


@app.get("/api/restaurants")
def get_restaurants(db: sqlite3.Connection = Depends(get_db)):
    """Fetches a simple directory list of all available restaurants."""
    cursor = db.cursor()
    cursor.execute("SELECT restaurant_id, name, location_tag FROM restaurants ORDER BY restaurant_id")
    
    # Return the list of restaurants formatted as a list of dictionaries
    return {"restaurants": [dict(row) for row in cursor.fetchall()]}


@app.post("/api/reset")
def reset_database(db: sqlite3.Connection = Depends(get_db)):
    """Wipes all review data so a new visitor gets a fresh demo."""
    global simulation_thread
    
    # Safe Shutdown: If a background data simulator is currently running, tell it to stop
    if simulation_thread and simulation_thread.is_alive():
        sim_state["stop_requested"] = True
        simulation_thread.join(timeout=5)  # Wait up to 5 seconds for it to clean up and exit
        
    cursor = db.cursor()
    # Delete all rows from the reviews table
    cursor.execute("DELETE FROM reviews")
    # Reset the auto-increment primary key counter back to 1 for the reviews table
    cursor.execute("DELETE FROM sqlite_sequence WHERE name = 'reviews'")
    
    db.commit()
    return {"status": "reset_complete"}


@app.patch("/api/tickets/{review_id}/resolve")
def resolve_ticket_endpoint(review_id: int, db: sqlite3.Connection = Depends(get_db)):
    """Marks an active 'Open' ticket as 'Resolved' and stamps it with the current time."""
    # Capture the exact current timestamp formatted as a clean string
    resolved_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor = db.cursor()
    # Try to update the matching open ticket in the database
    cursor.execute(
        "UPDATE reviews SET ticket_status = 'Resolved', resolved_at = ? WHERE review_id = ? AND ticket_status = 'Open'", 
        (resolved_time, review_id)
    )
    db.commit()
    
    # Safety Check: If no rows were changed, the ticket either didn't exist or was already closed
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Ticket not found or already resolved")
        
    return {"status": "success", "resolved_at": resolved_time}



# 7. SIMULATION ENDPOINTS
@app.post("/api/simulation/start")
def start_simulation():
    """Launches the combined simulation in a background thread. Non-blocking."""
    global simulation_thread, sim_state

    # 1. Clean up any old simulation that might still be running in the background
    if simulation_thread and simulation_thread.is_alive():
        sim_state["stop_requested"] = True
        simulation_thread.join(timeout=5)  # Give it 5 seconds to finish up safely

    # 2. Reset the tracking variables back to their baseline before starting a fresh run
    sim_state.update({
        "running": True,
        "phase": "seeding",
        "reviews_sent": 0,
        "error": None,
        "live_start_time": None,
        "stop_requested": False,
    })

    # 3. Import the heavy logic here to keep initial app startup fast and light
    from simulate import run_combined_simulation
    
    # 4. Create a worker thread to handle the long-running task in the background. 
    # daemon=True means if the main app stops, this background thread will close automatically.
    simulation_thread = threading.Thread(
        target=run_combined_simulation,
        args=(sim_state,),
        daemon=True
    )
    
    # 5. Fire off the thread immediately and return control back to the user right away
    simulation_thread.start()
    return {"status": "started"}


@app.get("/api/simulation/status")
def get_simulation_status():
    """Returns a live snapshot of the simulation state for the frontend to poll."""
    remaining = 0
    
    # Calculate countdown: If we are in the real-time 'live' phase, track how many 
    # seconds are left of the total 120-second simulation limit.
    if sim_state["phase"] == "live" and sim_state["live_start_time"]:
        # max(0, ...) guarantees the timer stops at 0 and doesn't tick down into negative numbers
        remaining = max(0, 120 - int(time.time() - sim_state["live_start_time"]))

    # Return a complete progress update for the frontend UI to display
    return {
        "running": sim_state["running"],
        "phase": sim_state["phase"],
        "remaining_seconds": remaining,
        "reviews_sent": sim_state["reviews_sent"],
        "total_reviews": sim_state["total_reviews"],
        "error": sim_state["error"],
    }