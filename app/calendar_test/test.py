from datetime import datetime
from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/api/calendar")
def get_calendar(year: int = datetime.now().year, month: int = datetime.now().month):
    # Replace these with your actual functions from pm_calendar.py
    schedules = []  # get_schedule(year, month)
    activities = []  # get_activities(year, month)
    return schedules + activities

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8502)
