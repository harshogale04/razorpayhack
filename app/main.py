from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app import audit, catalog
from app.intent import router as intent_router
from app.checkout import router as checkout_router

app = FastAPI(title="AI-Buyer Transactable Checkout (Razorpay test-mode)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    audit.init_db()


@app.get("/ai-catalog.json")
def ai_catalog():
    return {"products": catalog.get_catalog()}


@app.get("/audit-log")
def audit_log(limit: int = 50):
    return {"events": audit.get_recent_events(limit)}


app.include_router(intent_router)
app.include_router(checkout_router)

base_dir = os.path.join(os.path.dirname(__file__), "..")

dashboard_dir = os.path.join(base_dir, "dashboard")
if os.path.isdir(dashboard_dir):
    app.mount("/dashboard", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")

storefront_dir = os.path.join(base_dir, "storefront")
if os.path.isdir(storefront_dir):
    app.mount("/storefront", StaticFiles(directory=storefront_dir, html=True), name="storefront")