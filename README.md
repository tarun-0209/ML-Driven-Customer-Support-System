# ML-Driven-Customer-Support-System

## Overview
The **Restaurant Sentiment Dashboard** is an ML-driven full-stack application designed to help restaurant managers monitor, analyze, and respond to customer feedback in real-time. By leveraging Natural Language Processing (NLP) and Machine Learning, the system automatically ingests reviews, predicts customer sentiment, and generates actionable support tickets to ensure no customer complaint gets ignored.

## Purpose
The primary purpose of this project is to transform raw customer feedback into measurable, actionable operational metrics. It helps businesses quickly identify unhappy customers, understand operational bottlenecks (like specific shifts causing issues), and calculate the financial impact ("Revenue at Risk") to prioritize customer recovery efforts.

## Key Use Cases & Features

* **Real-Time Sentiment Classification:** Uses a pre-trained Logistic Regression model and a spaCy NLP pipeline to clean text, handle negations, and categorize incoming reviews as Positive, Neutral, or Negative.
* **Smart Ticketing System (Action Desk):** Automatically opens support tickets for negative and neutral reviews. Staff can take actions such as "Send Giftcard" or "Start Conversation" directly from the dashboard UI to resolve issues.
* **Anomaly & Sarcasm Detection:** Cross-references the user's explicit star rating with the AI's predicted text sentiment to flag suspicious reviews (e.g., a 1-star rating with highly positive text, or a 5-star rating with a sarcastic complaint). This provides valuable edge-case data for future model training.
* **Operational Insights Dashboard:** Visualizes negative review hotspots using a shift-based heatmap (Lunch, Dinner, Off-Hours), calculates the Average Time to Resolution (TTR), and tracks total revenue at risk based on pending tickets.
* **Live Data Simulation Engine:** Includes a built-in, simulation engine (`simulate.py`) that seeds the database with historical data and streams live simulated reviews to demonstrate the platform's capabilities without needing an active production data feed.

## Tech Stack

* **Backend Framework:** FastAPI, Python
* **Database:** SQLite (`reputation.db`)
* **Machine Learning / NLP:** Scikit-learn (TF-IDF, Logistic Regression), spaCy (`en_core_web_sm`), Joblib
* **Frontend:** HTML5, Vanilla JavaScript, Tailwind CSS (via CDN), Chart.js (via CDN)

## Getting Started (Local Development)

1. Install the required Python dependencies:
   pip install -r requirements.txt
   python -m spacy download en_core_web_sm

2. Ensure your pre-trained ML models (`tfidf_vectorizer.joblib` and `logistic_regression_model.joblib`) are placed inside a `/models` directory in the root folder.

3. Start the FastAPI backend server:
   uvicorn main:app --reload

4. Launch the Dashboard:
   Simply open the `index.html` file in any web browser.

5. Run a Simulation:
   Click the "Simulate Reviews" button in the top right of the dashboard UI. This will wipe the database, seed historical reviews, and start streaming live mock reviews so you can interact with the Action Desk.
