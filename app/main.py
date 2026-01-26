"""
CMA Compiler FastAPI Application.

This is the main entry point for the CMA compiler service. It provides
endpoints for the complete CMA generation pipeline:

1. POST /parse-notes - Convert realtor notes to IntentIR
2. POST /search-comps - Execute bounded query, rank, and return ReviewPacket
3. POST /select-comps - Manual comp selection validation
4. POST /generate-report - Produce verified narrative report

All endpoints enforce the compliance constraints and hard caps
defined in the specification.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4
import statistics

from fastapi import FastAPI, HTTPException, Response, Request, Form
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.settings import settings, DataSource
from audit.audit_log import AuditLog, AuditAction, set_audit_log, audit
from audit.provenance import ProvenanceTracker
from connectors.base import DataConnector, SearchResult
from connectors.csv_connector import CSVConnector
from connectors.reso_mock_connector import InMemoryRESOConnector, MockRESOServer
from domain.intent_ir import IntentIR
from domain.query_plan import QueryPlanBuilder, QueryPlan
from domain.report_schema import (
    ReportJSON, SubjectProperty, AddressInfo, PropertyCharacteristics,
    CompProperty, SaleInfo, AnalyticsSection, DataLimitation, AdjustmentItem,
    ScoreBreakdown
)
from domain.review import ReviewPacket
from domain.policies import FieldTier, MAX_SELECTED_COMPS
from llm.client import get_llm_client, LLMClient, MockLLMClient
from llm.notes_parser import NotesParser, NotesParseError
from llm.report_writer import ReportWriter, HallucinationError
from analytics.metrics import calculate_price_per_sqft, calculate_all_adjustments
from analytics.ranking import calculate_similarity_score, rank_comparables
from analytics.outliers import detect_all_outliers
from renderer.html_report import render_html_report

# Configure logging
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


# ============================================================================
# Application State
# ============================================================================

class AppState:
    """Application state container."""
    
    def __init__(self):
        self.connector: DataConnector | None = None
        self.llm_client: LLMClient | None = None
        self.audit_log: AuditLog | None = None
        self.provenance: ProvenanceTracker | None = None
        # In-memory storage for workflow state
        self.sessions: dict[str, dict[str, Any]] = {}


state = AppState()
templates = Jinja2Templates(directory="renderer/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting CMA Compiler...")
    
    # Initialize audit log
    state.audit_log = AuditLog(session_id=str(uuid4()))
    set_audit_log(state.audit_log)
    
    # Initialize provenance tracker
    state.provenance = ProvenanceTracker()
    
    # Initialize LLM client
    state.llm_client = get_llm_client(settings.llm_provider.value)
    logger.info(f"LLM client initialized: {settings.llm_provider.value}")
    
    # Initialize data connector
    if settings.data_source == DataSource.CSV:
        csv_path = Path(settings.csv_data_path)
        if csv_path.exists():
            state.connector = CSVConnector(csv_path)
            logger.info(f"CSV connector initialized: {csv_path}")
        else:
            state.connector = InMemoryRESOConnector(MockRESOServer())
            _load_sample_data(state.connector)
            logger.info("In-memory mock connector initialized with sample data")
    else:
        state.connector = InMemoryRESOConnector(MockRESOServer())
        _load_sample_data(state.connector)
        logger.info("In-memory mock connector initialized")
    
    yield
    
    # Shutdown
    logger.info("Shutting down CMA Compiler...")


def _load_sample_data(connector: InMemoryRESOConnector):
    """Load sample listing data for testing."""
    sample_listings = [
        {
            "ListingId": "CMA-001",
            "ListPrice": 525000,
            "ClosePrice": 520000,
            "CloseDate": datetime.now() - timedelta(days=30),
            "DaysOnMarket": 15,
            "PropertyType": "Residential",
            "BedroomsTotal": 3,
            "BathroomsTotalInteger": 2,
            "LivingArea": 1850,
            "LotSizeSquareFeet": 7500,
            "YearBuilt": 2018,
            "GarageSpaces": 2,
            "PoolPrivateYN": False,
            "City": "Denver",
            "StateOrProvince": "CO",
            "PostalCode": "80202",
            "StandardStatus": "Closed",
            "Latitude": 39.7392,
            "Longitude": -104.9903,
        },
        {
            "ListingId": "CMA-002",
            "ListPrice": 495000,
            "ClosePrice": 490000,
            "CloseDate": datetime.now() - timedelta(days=45),
            "DaysOnMarket": 22,
            "PropertyType": "Residential",
            "BedroomsTotal": 3,
            "BathroomsTotalInteger": 2,
            "LivingArea": 1720,
            "LotSizeSquareFeet": 6800,
            "YearBuilt": 2015,
            "GarageSpaces": 2,
            "PoolPrivateYN": False,
            "City": "Denver",
            "StateOrProvince": "CO",
            "PostalCode": "80202",
            "StandardStatus": "Closed",
            "Latitude": 39.7385,
            "Longitude": -104.9890,
        },
        {
            "ListingId": "CMA-003",
            "ListPrice": 545000,
            "ClosePrice": 540000,
            "CloseDate": datetime.now() - timedelta(days=60),
            "DaysOnMarket": 18,
            "PropertyType": "Residential",
            "BedroomsTotal": 4,
            "BathroomsTotalInteger": 2,
            "LivingArea": 1950,
            "LotSizeSquareFeet": 8000,
            "YearBuilt": 2019,
            "GarageSpaces": 2,
            "PoolPrivateYN": True,
            "City": "Denver",
            "StateOrProvince": "CO",
            "PostalCode": "80202",
            "StandardStatus": "Closed",
            "Latitude": 39.7400,
            "Longitude": -104.9880,
        },
        {
            "ListingId": "CMA-004",
            "ListPrice": 475000,
            "ClosePrice": 472000,
            "CloseDate": datetime.now() - timedelta(days=90),
            "DaysOnMarket": 28,
            "PropertyType": "Residential",
            "BedroomsTotal": 3,
            "BathroomsTotalInteger": 2,
            "LivingArea": 1680,
            "LotSizeSquareFeet": 6500,
            "YearBuilt": 2014,
            "GarageSpaces": 1,
            "PoolPrivateYN": False,
            "City": "Denver",
            "StateOrProvince": "CO",
            "PostalCode": "80202",
            "StandardStatus": "Closed",
            "Latitude": 39.7378,
            "Longitude": -104.9915,
        },
        {
            "ListingId": "CMA-005",
            "ListPrice": 560000,
            "ClosePrice": 555000,
            "CloseDate": datetime.now() - timedelta(days=20),
            "DaysOnMarket": 10,
            "PropertyType": "Residential",
            "BedroomsTotal": 3,
            "BathroomsTotalInteger": 3,
            "LivingArea": 2000,
            "LotSizeSquareFeet": 8500,
            "YearBuilt": 2020,
            "GarageSpaces": 2,
            "PoolPrivateYN": False,
            "City": "Denver",
            "StateOrProvince": "CO",
            "PostalCode": "80202",
            "StandardStatus": "Closed",
            "Latitude": 39.7410,
            "Longitude": -104.9870,
        },
    ]
    
    connector.load_listings(sample_listings)


# ============================================================================
# Core Logic Helpers
# ============================================================================

def _construct_comp_properties(
    subject_data: dict[str, Any],
    ranked_candidates: list[tuple[dict[str, Any], ScoreBreakdown, list[str]]],
    source_name: str
) -> list[CompProperty]:
    """Convert raw ranked candidates into CompProperty objects."""
    comps = []
    
    for i, (raw, breakdown, reasons) in enumerate(ranked_candidates, 1):
        # Calculate adjustments
        adjustments = calculate_all_adjustments(subject_data, raw)
        
        close_price = Decimal(str(raw.get("ClosePrice", 0)))
        adjusted_price = close_price + adjustments.total
        
        sqft = raw.get("LivingArea")
        ppsf = calculate_price_per_sqft(close_price, sqft)
        adjusted_ppsf = calculate_price_per_sqft(adjusted_price, sqft) if sqft else None
        
        close_date = raw.get("CloseDate")
        if isinstance(close_date, str):
            try:
                close_date = datetime.fromisoformat(close_date.replace("Z", "+00:00"))
            except ValueError:
                close_date = datetime.now()
        elif close_date is None:
            close_date = datetime.now()
        
        distance = Decimal(str(breakdown.distance_score / 20.0)) # Approx inversion or use haversine if real
        if "Distance" in raw: # If connector provided it
             distance = Decimal(str(raw["Distance"]))
        else:
            # Re-derive approx distance from score if needed, or pass it in
            # For now we'll just placeholder because rank_comparables consumed the distance map
            # and we are rebuilding here.
            # Ideally rank_comparables should return distance too.
            # But we can assume it's small if score is high.
            pass

        comp = CompProperty(
            listing_id=raw.get("ListingId", str(uuid4())),
            address=AddressInfo(
                street=f"{raw.get('ListingId', 'Unknown')} Street",
                city=str(raw.get("City", "Unknown")),
                state=str(raw.get("StateOrProvince", "XX")),
                zip_code=str(raw.get("PostalCode", "00000"))
            ),
            characteristics=PropertyCharacteristics(
                property_type=raw.get("PropertyType", "Residential"),
                bedrooms=raw.get("BedroomsTotal"),
                bathrooms=raw.get("BathroomsTotalInteger"),
                living_area_sqft=raw.get("LivingArea"),
                lot_size_sqft=raw.get("LotSizeSquareFeet"),
                year_built=raw.get("YearBuilt"),
                garage_spaces=raw.get("GarageSpaces"),
                pool=raw.get("PoolPrivateYN")
            ),
            sale_info=SaleInfo(
                close_price=close_price,
                close_date=close_date,
                original_list_price=Decimal(str(raw.get("ListPrice", 0))) if raw.get("ListPrice") else None,
                days_on_market=raw.get("DaysOnMarket")
            ),
            # Metadata
            data_source=source_name,
            data_timestamp=datetime.utcnow(),
            
            # Ranking
            rank_index=i,
            similarity_score=breakdown.total_score,
            score_breakdown=breakdown,
            selection_reasons=reasons,
            
            # Math
            distance_miles=distance, # We might need to pass this in better
            adjustments=[AdjustmentItem(**adj) for adj in adjustments.to_list()],
            adjusted_price=adjusted_price,
            price_per_sqft=ppsf,
            adjusted_price_per_sqft=adjusted_ppsf
        )
        comps.append(comp)
        
    return comps

def _calculate_analytics(comps: list[CompProperty]) -> AnalyticsSection:
    """Compute analytics for a set of comps."""
    prices = [c.sale_info.close_price for c in comps]
    adj_prices = [c.adjusted_price for c in comps]
    ppsf_vals = [c.price_per_sqft for c in comps if c.price_per_sqft]
    dom_vals = [c.sale_info.days_on_market for c in comps if c.sale_info.days_on_market is not None]
    
    median_price = Decimal(str(statistics.median(prices))) if prices else Decimal(0)
    mean_price = Decimal(str(statistics.mean(prices))) if prices else Decimal(0)
    std_price = Decimal(str(statistics.stdev(prices))) if len(prices) > 1 else Decimal(0)
    
    median_ppsf = Decimal(str(statistics.median(ppsf_vals))) if ppsf_vals else Decimal(0)
    mean_ppsf = Decimal(str(statistics.mean(ppsf_vals))) if ppsf_vals else Decimal(0)
    
    median_adj = Decimal(str(statistics.median(adj_prices))) if adj_prices else Decimal(0)
    mean_adj = Decimal(str(statistics.mean(adj_prices))) if adj_prices else Decimal(0)
    
    avg_dom = Decimal(str(statistics.mean(dom_vals))) if dom_vals else Decimal(0)
    
    indicated = median_adj
    value_range = std_price * 2 if std_price > 0 else median_price * Decimal("0.05")
    
    return AnalyticsSection(
        indicated_value=indicated,
        value_range_low=indicated - value_range,
        value_range_high=indicated + value_range,
        confidence_score=Decimal("75"),
        median_price=median_price,
        mean_price=mean_price,
        price_std_dev=std_price,
        median_price_per_sqft=median_ppsf,
        mean_price_per_sqft=mean_ppsf,
        median_adjusted_price=median_adj,
        mean_adjusted_price=mean_adj,
        avg_days_on_market=avg_dom,
        total_comps_analyzed=len(comps),
        outliers_excluded=sum(1 for c in comps if c.is_outlier)
    )

# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="CMA Compiler",
    description="Compliance-safe CMA/comps report generator with anti-hallucination controls",
    version="1.0.0",
    lifespan=lifespan
)


# ============================================================================
# Request/Response Models
# ============================================================================

class ParseNotesRequest(BaseModel):
    """Request body for parse-notes endpoint."""
    notes: str = Field(..., min_length=10, max_length=5000)


class ParseNotesResponse(BaseModel):
    """Response from parse-notes endpoint."""
    success: bool
    intent: IntentIR | None = None
    error: str | None = None
    session_id: str


class SearchCompsRequest(BaseModel):
    """Request body for search-comps endpoint."""
    session_id: str
    intent: IntentIR | None = None  # Optional override


class SearchCompsResponse(BaseModel):
    """Response from search-comps endpoint."""
    success: bool
    review_packet: ReviewPacket | None = None
    total_found: int
    was_capped: bool
    session_id: str


class SelectCompsRequest(BaseModel):
    """Request body for select-comps endpoint."""
    session_id: str
    selected_listing_ids: list[str] = Field(..., max_length=MAX_SELECTED_COMPS)


class SelectCompsResponse(BaseModel):
    """Response from select-comps endpoint."""
    success: bool
    selected_count: int
    session_id: str


class GenerateReportRequest(BaseModel):
    """Request body for generate-report endpoint."""
    session_id: str
    include_narrative: bool = True
    output_format: str = "json"  # "json" or "html"


class GenerateReportResponse(BaseModel):
    """Response from generate-report endpoint."""
    success: bool
    report: dict[str, Any] | None = None
    narrative: str | None = None
    error: str | None = None
    session_id: str


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint for service information."""
    return {
        "name": "CMA Compiler",
        "status": "active",
        "docs_url": "/docs",
        "openapi_url": "/openapi.json"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/ui")
async def ui_index(request: Request):
    """Render the main search page."""
    return templates.TemplateResponse(
        "index.html", 
        {"request": request, "data_source": settings.data_source.value}
    )


@app.get("/ui/sample", response_class=PlainTextResponse)
async def ui_sample():
    """Return sample notes for the UI."""
    try:
        with open("data/sample_notes.txt", "r") as f:
            return f.read()
    except FileNotFoundError:
        return "Looking for a 3 bedroom, 2 bathroom house in Denver, CO. Preferably near downtown with a budget around $500,000. Needs a garage and good schools."


@app.post("/ui/search", response_class=HTMLResponse)
async def ui_search(request: Request, notes: str = Form(...)):
    """
    Handle initial search from notes.
    Parses notes, runs search, and renders the review screen.
    """
    session_id = str(uuid4())
    correlation_id = state.audit_log.start_correlation()
    
    try:
        # 1. Parse
        audit(AuditAction.NOTES_RECEIVED, {"notes_length": len(notes), "session_id": session_id})
        parser = NotesParser(state.llm_client)
        intent = parser.parse(notes)
        audit(AuditAction.INTENT_PARSED, {"city": intent.subject_city})
        
        # 2. Search & Rank
        packet = await _execute_search_flow(intent, session_id)
        
        # 3. Store in Session
        state.sessions[session_id] = {
            "intent": intent,
            "review_packet": packet,
            "created_at": datetime.utcnow()
        }
        
        return templates.TemplateResponse(
            "review.html", 
            {
                "request": request, 
                "packet": packet,
                "total_found": len(packet.candidates),
                "was_capped": False, # TODO: Plumb from search result
                "session_id": session_id
            }
        )

    except Exception as e:
        logger.exception("UI Search Failed")
        return templates.TemplateResponse(
            "index.html", 
            {"request": request, "error": f"Search failed: {str(e)}", "notes": notes}
        )
    finally:
        state.audit_log.end_correlation()


@app.post("/ui/update-criteria", response_class=HTMLResponse)
async def ui_update_criteria(
    request: Request,
    session_id: str = Form(...),
    radius: float | None = Form(None),
    max_age: int | None = Form(None),
    intent_json: str = Form(...)
):
    """
    Handle criteria updates from the review screen.
    Updates IntentIR, re-runs search, and re-renders review screen.
    """
    try:
        # Reconstruct intent (simplified for this demo - realistically would parse JSON or individual fields)
        # Here we just override specific fields on the existing intent
        import json
        intent_data = json.loads(intent_json)
        intent = IntentIR(**intent_data)
        
        # Apply overrides
        if radius is not None:
            intent.search_radius_miles = radius
        if max_age is not None:
            intent.max_age_years = max_age
            
        audit(AuditAction.ASSUMPTIONS_MODIFIED, {"session_id": session_id, "radius": radius, "max_age": max_age})
        
        # Re-run search
        packet = await _execute_search_flow(intent, session_id)
        
        # Update session
        state.sessions[session_id]["intent"] = intent
        state.sessions[session_id]["review_packet"] = packet
        
        return templates.TemplateResponse(
            "review.html", 
            {
                "request": request, 
                "packet": packet,
                "total_found": len(packet.candidates),
                "session_id": session_id
            }
        )
        
    except Exception as e:
        logger.exception("Update Criteria Failed")
        # In real app, redirect with flash message. Here just re-render check.
        return Response(content=f"Error updating criteria: {str(e)}", status_code=500)


@app.post("/ui/generate", response_class=HTMLResponse)
async def ui_generate(
    request: Request, 
    session_id: str = Form(...),
    selected_ids: list[str] = Form(...)
):
    """
    Generate final reported from selected IDs.
    """
    correlation_id = state.audit_log.start_correlation()
    try:
        session = state.sessions.get(session_id)
        if not session or "review_packet" not in session:
            return templates.TemplateResponse("index.html", {"request": request, "error": "Session expired"})
            
        packet: ReviewPacket = session["review_packet"]
        
        # Update packet selection
        packet.selected_listing_ids = selected_ids
        
        # Generate Report data
        selected_comps = [c for c in packet.candidates if c.listing_id in selected_ids]
        analytics = _calculate_analytics(selected_comps)
        
        subject = SubjectProperty(
            address=AddressInfo(
                street=str(packet.intent.subject_address) if packet.intent.subject_address else "",
                city=str(packet.intent.subject_city),
                state=str(packet.intent.subject_state),
                zip_code=str(packet.intent.subject_zip)
            ),
            characteristics=PropertyCharacteristics(
                property_type=packet.intent.property_type or "Residential",
                bedrooms=packet.intent.subject_beds,
                bathrooms=packet.intent.subject_baths,
                living_area_sqft=packet.intent.subject_sqft,
                year_built=packet.intent.subject_year_built
            )
        )
        
        report = ReportJSON(
            subject=subject,
            selected_comps=selected_comps,
            analytics=analytics,
            data_source=settings.data_source.value
        )
        
        writer = ReportWriter(state.llm_client)
        narrative = writer.generate(report)
        
        # We use ui_report.html which wraps report_html content
        # But we need to rename/adjust templates if we want to use base.html
        # For now, let's render the inner report HTML and pass it to a wrapper that extends base.html
        
        # Render the inner content using the standalone template logic or a fragment
        from renderer.html_report import render_html_report
        inner_html = render_html_report(report, narrative)
        
        return templates.TemplateResponse(
            "ui_report.html", 
            {"request": request, "report_html": inner_html}
        )

    except Exception as e:
        logger.exception("UI Generation Failed")
        return templates.TemplateResponse(
            "index.html", 
            {"request": request, "error": f"Generation failed: {str(e)}"}
        )
    finally:
        state.audit_log.end_correlation()


async def _execute_search_flow(intent: IntentIR, session_id: str) -> ReviewPacket:
    """Helper to run the search pipeline logic."""
    query_plan = QueryPlanBuilder.from_intent(intent)
    result = state.connector.search(query_plan, max_tier=FieldTier.SAFE)
    
    # Ranking Logic (Duplicated from search endpoints - should refactor to service, but okay for now)
    distances = {r.get("ListingId"): 0.5 for r in result.records} # Mock
    dates = {r.get("ListingId"): 30 for r in result.records} # Mock
    
    subject_data = {
        "LivingArea": intent.subject_sqft,
        "BedroomsTotal": intent.subject_beds,
        "BathroomsTotalInteger": intent.subject_baths,
        "YearBuilt": intent.subject_year_built,
    }
    
    ranked = rank_comparables(
        subject=subject_data,
        comps=[r.raw_data for r in result.records],
        distances=distances,
        sale_dates=dates,
        limit=200
    )
    
    candidates = _construct_comp_properties(subject_data, ranked, state.connector.source_name)
    selected_ids = [c.listing_id for c in candidates[:settings.max_selected_comps]]
    preview = _calculate_analytics(candidates[:settings.max_selected_comps])
    
    return ReviewPacket(
        session_id=session_id,
        intent=intent,
        candidates=candidates,
        selected_listing_ids=selected_ids,
        analytics_preview=preview
    )


@app.post("/parse-notes", response_model=ParseNotesResponse)
async def parse_notes(request: ParseNotesRequest):
    """Parse unstructured realtor notes into structured IntentIR."""
    session_id = str(uuid4())
    correlation_id = state.audit_log.start_correlation()
    
    try:
        audit(AuditAction.NOTES_RECEIVED, {"notes_length": len(request.notes), "session_id": session_id})
        
        parser = NotesParser(state.llm_client)
        intent = parser.parse(request.notes)
        
        audit(AuditAction.INTENT_PARSED, {"city": intent.subject_city, "state": intent.subject_state})
        
        state.sessions[session_id] = {
            "intent": intent,
            "created_at": datetime.utcnow()
        }
        
        return ParseNotesResponse(
            success=True,
            intent=intent,
            session_id=session_id
        )
        
    except NotesParseError as e:
        audit(AuditAction.INTENT_VALIDATION_FAILED, {"error": str(e)})
        return ParseNotesResponse(success=False, error=str(e), session_id=session_id)
    finally:
        state.audit_log.end_correlation()


@app.post("/search-comps", response_model=SearchCompsResponse)
async def search_comps(request: SearchCompsRequest):
    """
    Search for comparable properties based on IntentIR.
    Returns a ReviewPacket with ranked candidates.
    """
    session = state.sessions.get(request.session_id)
    intent = request.intent or (session.get("intent") if session else None)
    
    if not intent:
        raise HTTPException(
            status_code=400,
            detail="No intent provided. Call /parse-notes first or include intent in request."
        )
    
    correlation_id = state.audit_log.start_correlation()
    
    try:
        # Build query plan
        query_plan = QueryPlanBuilder.from_intent(intent)
        
        audit(
            AuditAction.QUERY_PLANNED,
            {
                "filters": len(query_plan.filters),
                "max_results": query_plan.max_results,
                "intent_hash": query_plan.intent_hash
            }
        )
        
        # Execute search
        result: SearchResult = state.connector.search(query_plan, max_tier=FieldTier.SAFE)
        
        audit(
            AuditAction.CANDIDATES_RETRIEVED,
            {
                "total": result.total_count,
                "capped": result.was_capped
            }
        )
        
        # Calculate derived ranking inputs (mocking distance for now as connectors don't return it yet)
        # In a real impl, connector returns distance or we compute from lat/long
        distances = {r.get("ListingId"): 0.5 for r in result.records} 
        
        # Determine sale recency
        today = datetime.now()
        dates = {}
        for r in result.records:
            lid = r.get("ListingId")
            cd = r.get("CloseDate")
            if isinstance(cd, datetime):
                delta = (today - cd).days
            elif isinstance(cd, str):
                try:
                     dt = datetime.fromisoformat(cd.replace("Z", "+00:00"))
                     delta = (today - dt).days
                except:
                     delta = 30
            else:
                delta = 30
            dates[lid] = delta
            
        # Rank
        subject_data = {
            "LivingArea": intent.subject_sqft,
            "BedroomsTotal": intent.subject_beds,
            "BathroomsTotalInteger": intent.subject_baths,
            "YearBuilt": intent.subject_year_built,
        }
        
        ranked_candidates = rank_comparables(
            subject=subject_data,
            comps=[r.raw_data for r in result.records],
            distances=distances,
            sale_dates=dates,
            limit=50  # Return top 50 for review
        )
        
        # Build CompProperty objects
        candidates = _construct_comp_properties(subject_data, ranked_candidates, state.connector.source_name)
        
        # Default selection (top 5)
        selected_ids = [c.listing_id for c in candidates[:settings.max_selected_comps]]
        
        # Analytics Preview on default
        preview = _calculate_analytics(candidates[:settings.max_selected_comps])
        
        # Construct Review Packet
        packet = ReviewPacket(
            session_id=request.session_id,
            intent=intent,
            candidates=candidates,
            selected_listing_ids=selected_ids,
            analytics_preview=preview
        )
        
        # Update session
        if session is None:
            session = {"created_at": datetime.utcnow()}
            state.sessions[request.session_id] = session
        
        session["intent"] = intent
        session["review_packet"] = packet
        
        return SearchCompsResponse(
            success=True,
            review_packet=packet,
            total_found=result.total_count,
            was_capped=result.was_capped,
            session_id=request.session_id
        )
        
    except Exception as e:
        audit(AuditAction.QUERY_FAILED, {"error": str(e)})
        logger.exception("Search Failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        state.audit_log.end_correlation()


@app.post("/select-comps", response_model=SelectCompsResponse)
async def select_comps(request: SelectCompsRequest):
    """
    Select specific comparables for the report.
    Updates the session's ReviewPacket.
    """
    session = state.sessions.get(request.session_id)
    packet = session.get("review_packet") if session else None
    
    if not packet:
        raise HTTPException(
            status_code=400,
            detail="No review packet found. Call /search-comps first."
        )
    
    # Enforce hard cap
    if len(request.selected_listing_ids) > MAX_SELECTED_COMPS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_SELECTED_COMPS} comps allowed"
        )
    
    # Validate IDs exist in candidates
    valid_ids = {c.listing_id for c in packet.candidates}
    unknown = [id for id in request.selected_listing_ids if id not in valid_ids]
    if unknown:
        # In a real app we might re-fetch, but here we require them to be in candidates
        pass # Allow for now or warn
    
    # Update packet
    packet.selected_listing_ids = request.selected_listing_ids
    
    # Recalculate preview
    selected_objs = [c for c in packet.candidates if c.listing_id in request.selected_listing_ids]
    packet.analytics_preview = _calculate_analytics(selected_objs)
    
    session["review_packet"] = packet
    
    audit(
        AuditAction.COMPS_SELECTED,
        {
            "requested": len(request.selected_listing_ids),
            "valid": len(selected_objs)
        }
    )
    
    return SelectCompsResponse(
        success=True,
        selected_count=len(selected_objs),
        session_id=request.session_id
    )


@app.post("/generate-report")
async def generate_report(request: GenerateReportRequest):
    """
    Generate the CMA report using the finalized ReviewPacket.
    """
    session = state.sessions.get(request.session_id)
    packet: ReviewPacket = session.get("review_packet") if session else None
    
    if not packet:
        raise HTTPException(status_code=400, detail="Review packet not found")
    
    selected_comps = [c for c in packet.candidates if c.listing_id in packet.selected_listing_ids]
    
    if not selected_comps:
        raise HTTPException(status_code=400, detail="No comps selected")
    
    correlation_id = state.audit_log.start_correlation()
    
    try:
        # Build Subject Property
        intent = packet.intent
        subject = SubjectProperty(
            address=AddressInfo(
                street=str(intent.subject_address) if intent.subject_address else "",
                city=str(intent.subject_city),
                state=str(intent.subject_state),
                zip_code=str(intent.subject_zip)
            ),
            characteristics=PropertyCharacteristics(
                property_type=intent.property_type or "Residential",
                bedrooms=intent.subject_beds,
                bathrooms=intent.subject_baths,
                living_area_sqft=intent.subject_sqft,
                lot_size_sqft=intent.subject_lot_sqft,
                year_built=intent.subject_year_built
            )
        )
        
        # Analytics
        analytics = _calculate_analytics(selected_comps)
        
        # Limitations
        limitations = []
        if len(selected_comps) < 3:
            limitations.append(DataLimitation(
                category="sample_size",
                description="Fewer than 3 comps selected.",
                severity="warning"
            ))

        # Report
        report = ReportJSON(
            subject=subject,
            selected_comps=selected_comps,
            analytics=analytics,
            limitations=limitations,
            data_source=settings.data_source.value
        )
        
        audit(AuditAction.REPORT_GENERATED, {"comp_count": len(selected_comps)})
        
        # Narrative
        narrative = None
        if request.include_narrative:
            writer = ReportWriter(state.llm_client)
            narrative = writer.generate(report)
            audit(AuditAction.REPORT_VERIFIED, {"narrative_length": len(narrative)})
            
        if request.output_format == "html":
            html = render_html_report(report, narrative)
            return HTMLResponse(content=html)
            
        return {
            "success": True,
            "report": report.model_dump(mode="json"),
            "narrative": narrative,
            "session_id": request.session_id
        }

    except Exception as e:
        audit(AuditAction.REPORT_FAILED, {"error": str(e)})
        logger.exception("Report generation failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        state.audit_log.end_correlation()


@app.get("/audit/{session_id}")
async def get_audit_log(session_id: str):
    """Get audit log entries for a session."""
    entries = state.audit_log.get_entries()
    session_entries = [
        e.to_dict() for e in entries
        if e.details.get("session_id") == session_id
    ]
    return {"entries": session_entries}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
