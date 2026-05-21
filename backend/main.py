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

# --- 1. APP INITIALIZATION ---
app = FastAPI(title="Sentiment Dashboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

# --- 2. SIMULATION STATE ---
# Mutable dict shared between main.py endpoints and the background simulation thread.
sim_state = {
    "running": False,
    "phase": "idle",        # "idle" | "seeding" | "live" | "error"
    "reviews_sent": 0,
    "total_reviews": 12,
    "error": None,
    "live_start_time": None,
}
simulation_thread = None

# --- 3. ML & NLP SETUP ---
try:
    vectorizer = joblib.load("models/tfidf_vectorizer.joblib")
    classifier = joblib.load("models/logistic_regression_model.joblib")
    nlp = spacy.load("en_core_web_sm")
except Exception as e:
    print(f" ML models failed to Load: {e}")

def clean_and_negate_pipeline(text: str) -> str:
    """Cleans text and attaches 'not_' to negated words for better ML inference."""
    if not isinstance(text, str): return ""
    text = re.sub(r"http\S+|@[\w]+", "", text)
    doc = nlp(text)
    
    negated_tokens, negation_words = set(), set()
    for token in doc:
        if token.dep_ == "neg":
            negation_words.add(token)
            negated_tokens.add(token.head)
            for child in token.head.children:
                if child.pos_ in ["ADJ", "ADV"] and child != token:
                    negated_tokens.add(child)
                    
    cleaned_tokens = []
    for token in doc:
        if token in negation_words or token.is_punct or token.is_digit or (token.is_stop and token not in negated_tokens):
            continue
        pure_word = re.sub(r"[^a-zA-Z]", "", token.text).strip()
        if not pure_word: continue
        
        lemma = token.lemma_.lower()
        cleaned_tokens.append(f"not_{lemma}" if token in negated_tokens else lemma)
        
    return " ".join(cleaned_tokens)

# --- 3. HELPER FUNCTIONS ---
def parse_timestamp(ts_str: str) -> Optional[datetime]:
    """Safely converts DB timestamp strings into Python datetime objects."""
    try:
        clean_time = str(ts_str).replace('T', ' ').split('.')[0].strip()
        return datetime.strptime(clean_time, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None

# --- 4. API SCHEMAS ---
class ReviewIngest(BaseModel):
    restaurant_id: int
    review_text: str
    star_rating: int
    review_timestamp: str

# --- 5. API ENDPOINTS ---

@app.post("/api/reviews")
def ingest_review(review: ReviewIngest, db: sqlite3.Connection = Depends(get_db)):
    vectorized_text = vectorizer.transform([clean_and_negate_pipeline(review.review_text)])
    prediction_raw = classifier.predict(vectorized_text)[0].item()
    confidence = float(max(classifier.predict_proba(vectorized_text)[0]))
    
    prediction_text = {0: 'negative', 1: 'neutral', 2: 'positive'}.get(prediction_raw, 'neutral')

    # Business Logic: Open tickets for Negatives, Neutrals, and Anomalies
    is_anomaly = (review.star_rating >= 4 and prediction_text != 'positive') or \
                 (review.star_rating <= 2 and prediction_text == 'positive')
                 
    ticket_status = 'Open' if prediction_text in ['negative', 'neutral'] or is_anomaly else 'None'

    cursor = db.cursor()
    try:
        cursor.execute(
            "INSERT INTO reviews(restaurant_id, review_text, star_rating, review_timestamp, predicted_sentiment, confidence_score, ticket_status) VALUES (?,?,?,?,?,?,?)",
            (review.restaurant_id, review.review_text, review.star_rating, review.review_timestamp, prediction_text, confidence, ticket_status)
        )
        db.commit()
        return {"status": "success", "review_id": cursor.lastrowid, "sentiment": prediction_text, "ticket": ticket_status}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Invalid restaurant_id or DB Integrity Error")

@app.get("/api/dashboard")
def get_dashboard_metrics(restaurant_id: Optional[int] = None, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    filter_query = " AND restaurant_id = ?" if restaurant_id else ""
    params = (restaurant_id,) if restaurant_id else ()

    # 1. Revenue at Risk
    cursor.execute(f"SELECT COUNT(*) FROM reviews WHERE ticket_status = 'Open'{filter_query}", params)
    revenue_at_risk = cursor.fetchone()[0] * 50
    
    # 2. Heatmap Data
    cursor.execute(f"SELECT review_timestamp FROM reviews WHERE predicted_sentiment = 'negative'{filter_query}", params)
    heatmap_data = {"Lunch": 0, "Dinner": 0, "Off-Hours": 0}
    for row in cursor.fetchall():
        dt = parse_timestamp(row["review_timestamp"])
        if not dt: continue
        if 11 <= dt.hour <= 15: heatmap_data["Lunch"] += 1
        elif 16 <= dt.hour <= 22: heatmap_data["Dinner"] += 1
        else: heatmap_data["Off-Hours"] += 1

    # 3. Average TTR
    cursor.execute(f"SELECT review_timestamp, resolved_at FROM reviews WHERE ticket_status = 'Resolved' AND resolved_at IS NOT NULL{filter_query}", params)
    total_hours, valid_resolutions = 0, 0
    
    for row in cursor.fetchall():
        t1, t2 = parse_timestamp(row["review_timestamp"]), parse_timestamp(row["resolved_at"])
        if t1 and t2:
            diff_hours = (t2 - t1).total_seconds() / 3600
            if diff_hours >= 0:
                total_hours += diff_hours
                valid_resolutions += 1

    return {
        "open_tickets": revenue_at_risk // 50,
        "revenue_at_risk": revenue_at_risk,
        "heatmap_data": heatmap_data,
        "avg_ttr_hours": round(total_hours / valid_resolutions, 1) if valid_resolutions > 0 else 0
    }

@app.get("/api/tickets")
def get_all_tickets(restaurant_id: Optional[int] = None, db: sqlite3.Connection = Depends(get_db)):
    query = """
        SELECT r.review_id, rest.name as restaurant_name, r.review_text, r.review_timestamp, 
               r.ticket_status, r.resolved_at, r.predicted_sentiment, r.confidence_score, r.star_rating
        FROM reviews r JOIN restaurants rest ON r.restaurant_id = rest.restaurant_id
        WHERE r.ticket_status IN ('Open', 'Resolved')
    """
    params = ()
    if restaurant_id:
        query += " AND r.restaurant_id = ?"
        params = (restaurant_id,)
        
    cursor = db.cursor()
    cursor.execute(query + " ORDER BY r.review_timestamp DESC", params)
    return {"tickets": [dict(row) for row in cursor.fetchall()]}

@app.get("/api/restaurants")
def get_restaurants(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT restaurant_id, name, location_tag FROM restaurants ORDER BY restaurant_id")
    return {"restaurants": [dict(row) for row in cursor.fetchall()]}

@app.post("/api/reset")
def reset_database(db: sqlite3.Connection = Depends(get_db)):
    """Wipes all review data so a new visitor gets a fresh demo."""
    cursor = db.cursor()
    cursor.execute("DELETE FROM reviews")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name = 'reviews'")
    db.commit()
    return {"status": "reset_complete"}

@app.patch("/api/tickets/{review_id}/resolve")
def resolve_ticket_endpoint(review_id: int, db: sqlite3.Connection = Depends(get_db)):
    resolved_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor = db.cursor()
    cursor.execute("UPDATE reviews SET ticket_status = 'Resolved', resolved_at = ? WHERE review_id = ? AND ticket_status = 'Open'", (resolved_time, review_id))
    db.commit()
    
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Ticket not found or already resolved")
    return {"status": "success", "resolved_at": resolved_time}


# --- 6. SIMULATION ENDPOINTS ---

@app.post("/api/simulation/start")
def start_simulation():
    """Launches the combined simulation in a background thread. Non-blocking."""
    global simulation_thread, sim_state

    if simulation_thread and simulation_thread.is_alive():
        return {"status": "already_running"}

    # Reset state before launch
    sim_state.update({
        "running": True,
        "phase": "seeding",
        "reviews_sent": 0,
        "error": None,
        "live_start_time": None,
    })

    from simulate import run_combined_simulation
    simulation_thread = threading.Thread(
        target=run_combined_simulation,
        args=(sim_state,),
        daemon=True
    )
    simulation_thread.start()
    return {"status": "started"}


@app.get("/api/simulation/status")
def get_simulation_status():
    """Returns a live snapshot of the simulation state for the frontend to poll."""
    remaining = 0
    if sim_state["phase"] == "live" and sim_state["live_start_time"]:
        remaining = max(0, 120 - int(time.time() - sim_state["live_start_time"]))

    return {
        "running": sim_state["running"],
        "phase": sim_state["phase"],
        "remaining_seconds": remaining,
        "reviews_sent": sim_state["reviews_sent"],
        "total_reviews": sim_state["total_reviews"],
        "error": sim_state["error"],
    }