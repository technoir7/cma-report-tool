"""
CMA Compiler FastAPI Application.

This is the main entry point for the CMA compiler service. It provides
endpoints for the complete CMA generation pipeline:

1. POST /parse-notes - Convert realtor notes to IntentIR
2. POST /search-comps - Execute bounded query, return candidates  
3. POST /select-comps - Manual comp selection (max 20)
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
    CompProperty, SaleInfo, AnalyticsSection, DataLimitation, AdjustmentItem
)
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
            # Create mock in-memory connector for testing
            state.connector = InMemoryRESOConnector(MockRESOServer())
            # Load sample data
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
    intent: IntentIR | None = None  # Optional if session has previous intent


class SearchCompsResponse(BaseModel):
    """Response from search-comps endpoint."""
    success: bool
    candidates: list[dict[str, Any]]
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
    """Render the main UI page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/ui/sample", response_class=PlainTextResponse)
async def ui_sample():
    """Return sample notes for the UI."""
    try:
        with open("data/sample_notes.txt", "r") as f:
            return f.read()
    except FileNotFoundError:
        return "Looking for a 3 bedroom, 2 bathroom house in Denver, CO. Preferably near downtown with a budget around $500,000. Needs a garage and good schools."


@app.post("/ui/generate", response_class=HTMLResponse)
async def ui_generate(request: Request, notes: str = Form(...)):
    """Handle UI form submission and render report."""
    session_id = str(uuid4())
    correlation_id = state.audit_log.start_correlation()
    
    try:
        # 1. Parse Notes
        audit(AuditAction.NOTES_RECEIVED, {"notes_length": len(notes), "session_id": session_id})
        parser = NotesParser(state.llm_client)
        intent = parser.parse(notes)
        audit(AuditAction.INTENT_PARSED, {"city": intent.subject_city, "state": intent.subject_state})
        
        # 2. Search Candidates
        query_plan = QueryPlanBuilder.from_intent(intent)
        result: SearchResult = state.connector.search(query_plan, max_tier=FieldTier.SAFE)
        candidates = [r.raw_data for r in result.records]
        
        # 3. Select Comps (Auto-select top N)
        # In a real app, we'd rank them. Here we just take the first few
        selected = candidates[:settings.max_selected_comps]
        if not selected:
             return templates.TemplateResponse(
                "index.html", 
                {"request": request, "error": "No comparable properties found."}
            )

        # 4. Generate Report
        # Build subject property
        subject = SubjectProperty(
            address=AddressInfo(
                street=intent.subject_address,
                city=intent.subject_city,
                state=intent.subject_state,
                zip_code=intent.subject_zip
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
        
        # Build subject data for analytics
        subject_data = {
            "LivingArea": intent.subject_sqft,
            "BedroomsTotal": intent.subject_beds,
            "BathroomsTotalInteger": intent.subject_baths,
            "YearBuilt": intent.subject_year_built,
            "LotSizeSquareFeet": intent.subject_lot_sqft,
            "GarageSpaces": None,
            "PoolPrivateYN": None
        }

        # Process comps & analytics (reuse logic from generate_report endpoint)
        comps = []
        prices = []
        adjusted_prices = []
        ppsf_values = []
        dom_values = []

        for raw in selected:
            adjustments = calculate_all_adjustments(subject_data, raw)
            close_price = Decimal(str(raw.get("ClosePrice", 0)))
            adjusted_price = close_price + adjustments.total
            sqft = raw.get("LivingArea")
            ppsf = calculate_price_per_sqft(close_price, sqft)
            adjusted_ppsf = calculate_price_per_sqft(adjusted_price, sqft) if sqft else None
            
            close_date = raw.get("CloseDate")
            if isinstance(close_date, str):
                close_date = datetime.fromisoformat(close_date.replace("Z", "+00:00"))
            elif close_date is None:
                close_date = datetime.now()
            
            days_since = (datetime.now() - close_date).days if close_date else 0
            distance = Decimal("0.5")
            
            similarity = calculate_similarity_score(subject_data, raw, float(distance), days_since)
            
            comp = CompProperty(
                listing_id=raw.get("ListingId", str(uuid4())),
                address=AddressInfo(
                    street=f"{raw.get('ListingId', 'Unknown')} Street",
                    city=raw.get("City", "Unknown"),
                    state=raw.get("StateOrProvince", "XX"),
                    zip_code=raw.get("PostalCode", "00000")
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
                distance_miles=distance,
                similarity_score=similarity.total_score,
                adjustments=[AdjustmentItem(**adj) for adj in adjustments.to_list()],
                adjusted_price=adjusted_price,
                price_per_sqft=ppsf,
                adjusted_price_per_sqft=adjusted_ppsf
            )
            comps.append(comp)
            prices.append(float(close_price))
            adjusted_prices.append(float(adjusted_price))
            if ppsf: ppsf_values.append(float(ppsf))
            if raw.get("DaysOnMarket"): dom_values.append(raw["DaysOnMarket"])

        # Detect outliers
        outliers = detect_all_outliers(subject_data, selected)
        for comp in comps:
            if comp.listing_id in outliers:
                outlier = outliers[comp.listing_id]
                comp.is_outlier = outlier.is_outlier
                if outlier.is_outlier:
                    comp.outlier_reason = ", ".join(r.value for r in outlier.reasons)

        # Analytics
        import statistics
        median_price = Decimal(str(statistics.median(prices))) if prices else Decimal(0)
        mean_price = Decimal(str(statistics.mean(prices))) if prices else Decimal(0)
        std_price = Decimal(str(statistics.stdev(prices))) if len(prices) > 1 else Decimal(0)
        median_ppsf = Decimal(str(statistics.median(ppsf_values))) if ppsf_values else Decimal(0)
        mean_ppsf = Decimal(str(statistics.mean(ppsf_values))) if ppsf_values else Decimal(0)
        median_adj = Decimal(str(statistics.median(adjusted_prices))) if adjusted_prices else Decimal(0)
        mean_adj = Decimal(str(statistics.mean(adjusted_prices))) if adjusted_prices else Decimal(0)
        avg_dom = Decimal(str(statistics.mean(dom_values))) if dom_values else Decimal(0)
        
        indicated = median_adj
        value_range = std_price * 2 if std_price > 0 else median_price * Decimal("0.05")
        
        analytics = AnalyticsSection(
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

        limitations = []
        if len(comps) < 3:
            limitations.append(DataLimitation(category="sample_size", description="Fewer than 3 comps found.", severity="warning"))

        report = ReportJSON(
            subject=subject,
            selected_comps=comps,
            analytics=analytics,
            limitations=limitations,
            data_source=settings.data_source.value
        )
        
        # Generate narrative (using default include_narrative=True behavior for UI)
        writer = ReportWriter(state.llm_client)
        narrative = writer.generate(report)
        
        # Render HTML
        report_html = render_html_report(report, narrative)
        
        return templates.TemplateResponse("ui_report.html", {"request": request, "report_html": report_html})

    except Exception as e:
        logger.exception("UI Generation Failed")
        return templates.TemplateResponse(
            "index.html", 
            {"request": request, "error": f"Generation failed: {str(e)}"}
        )
    finally:
        state.audit_log.end_correlation()


@app.post("/parse-notes", response_model=ParseNotesResponse)
async def parse_notes(request: ParseNotesRequest):
    """
    Parse unstructured realtor notes into structured IntentIR.
    
    The LLM extracts structured data from free-form notes.
    Missing information is represented as null - NEVER invented.
    """
    session_id = str(uuid4())
    correlation_id = state.audit_log.start_correlation()
    
    try:
        audit(
            AuditAction.NOTES_RECEIVED,
            {"notes_length": len(request.notes), "session_id": session_id}
        )
        
        parser = NotesParser(state.llm_client)
        intent = parser.parse(request.notes)
        
        audit(
            AuditAction.INTENT_PARSED,
            {"city": intent.subject_city, "state": intent.subject_state}
        )
        
        # Store in session
        state.sessions[session_id] = {
            "intent": intent,
            "candidates": None,
            "selected_comps": None,
            "created_at": datetime.utcnow()
        }
        
        return ParseNotesResponse(
            success=True,
            intent=intent,
            session_id=session_id
        )
        
    except NotesParseError as e:
        audit(
            AuditAction.INTENT_VALIDATION_FAILED,
            {"error": str(e)}
        )
        return ParseNotesResponse(
            success=False,
            error=str(e),
            session_id=session_id
        )
    finally:
        state.audit_log.end_correlation()


@app.post("/search-comps", response_model=SearchCompsResponse)
async def search_comps(request: SearchCompsRequest):
    """
    Search for comparable properties based on IntentIR.
    
    Returns candidate comps (max 200) that match the criteria.
    All queries are bounded and deterministic.
    """
    session = state.sessions.get(request.session_id)
    
    # Get intent from request or session
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
        result: SearchResult = state.connector.search(
            query_plan,
            max_tier=FieldTier.SAFE
        )
        
        audit(
            AuditAction.CANDIDATES_RETRIEVED,
            {
                "total": result.total_count,
                "capped": result.was_capped
            }
        )
        
        if result.was_capped:
            audit(
                AuditAction.CANDIDATES_CAPPED,
                {"cap": result.cap_applied}
            )
        
        # Store candidates in session
        candidates = [r.raw_data for r in result.records]
        
        if session is None:
            session = {"created_at": datetime.utcnow()}
            state.sessions[request.session_id] = session
        
        session["intent"] = intent
        session["candidates"] = candidates
        session["query_plan"] = query_plan
        
        return SearchCompsResponse(
            success=True,
            candidates=candidates,
            total_found=result.total_count,
            was_capped=result.was_capped,
            session_id=request.session_id
        )
        
    except Exception as e:
        audit(AuditAction.QUERY_FAILED, {"error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        state.audit_log.end_correlation()


@app.post("/select-comps", response_model=SelectCompsResponse)
async def select_comps(request: SelectCompsRequest):
    """
    Select specific comparables for the report.
    
    Enforces hard cap of 20 selected comps.
    """
    session = state.sessions.get(request.session_id)
    
    if not session or not session.get("candidates"):
        raise HTTPException(
            status_code=400,
            detail="No candidates found. Call /search-comps first."
        )
    
    # Enforce hard cap
    if len(request.selected_listing_ids) > MAX_SELECTED_COMPS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_SELECTED_COMPS} comps allowed"
        )
    
    # Filter candidates to selected
    candidates = session["candidates"]
    selected = [
        c for c in candidates
        if c.get("ListingId") in request.selected_listing_ids
    ]
    
    audit(
        AuditAction.COMPS_SELECTED,
        {
            "requested": len(request.selected_listing_ids),
            "found": len(selected)
        }
    )
    
    session["selected_comps"] = selected
    
    return SelectCompsResponse(
        success=True,
        selected_count=len(selected),
        session_id=request.session_id
    )


@app.post("/generate-report")
async def generate_report(request: GenerateReportRequest):
    """
    Generate the CMA report with optional narrative.
    
    If narrative is requested, runs hallucination verification.
    Returns JSON or HTML based on output_format.
    """
    session = state.sessions.get(request.session_id)
    
    if not session:
        raise HTTPException(status_code=400, detail="Session not found")
    
    intent = session.get("intent")
    selected_raw = session.get("selected_comps") or session.get("candidates", [])[:5]
    
    if not intent:
        raise HTTPException(status_code=400, detail="No intent in session")
    
    if not selected_raw:
        raise HTTPException(status_code=400, detail="No comps selected")
    
    correlation_id = state.audit_log.start_correlation()
    
    try:
        # Build subject property from intent
        subject = SubjectProperty(
            address=AddressInfo(
                street=intent.subject_address,
                city=intent.subject_city,
                state=intent.subject_state,
                zip_code=intent.subject_zip
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
        
        # Build subject data dict for analytics
        subject_data = {
            "LivingArea": intent.subject_sqft,
            "BedroomsTotal": intent.subject_beds,
            "BathroomsTotalInteger": intent.subject_baths,
            "YearBuilt": intent.subject_year_built,
            "LotSizeSquareFeet": intent.subject_lot_sqft,
            "GarageSpaces": None,
            "PoolPrivateYN": None
        }
        
        # Process comps
        comps = []
        prices = []
        adjusted_prices = []
        ppsf_values = []
        dom_values = []
        
        for raw in selected_raw[:MAX_SELECTED_COMPS]:
            # Calculate adjustments
            adjustments = calculate_all_adjustments(subject_data, raw)
            
            close_price = Decimal(str(raw.get("ClosePrice", 0)))
            adjusted_price = close_price + adjustments.total
            
            sqft = raw.get("LivingArea")
            ppsf = calculate_price_per_sqft(close_price, sqft)
            adjusted_ppsf = calculate_price_per_sqft(adjusted_price, sqft) if sqft else None
            
            # Get close date
            close_date = raw.get("CloseDate")
            if isinstance(close_date, str):
                close_date = datetime.fromisoformat(close_date.replace("Z", "+00:00"))
            elif close_date is None:
                close_date = datetime.now()
            
            days_since = (datetime.now() - close_date).days if close_date else 0
            
            # Calculate distance (simplified - would use haversine in production)
            distance = Decimal("0.5")  # Placeholder
            
            # Calculate similarity
            similarity = calculate_similarity_score(
                subject_data, raw, float(distance), days_since
            )
            
            comp = CompProperty(
                listing_id=raw.get("ListingId", str(uuid4())),
                address=AddressInfo(
                    street=f"{raw.get('ListingId', 'Unknown')} Street",
                    city=raw.get("City", "Unknown"),
                    state=raw.get("StateOrProvince", "XX"),
                    zip_code=raw.get("PostalCode", "00000")
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
                distance_miles=distance,
                similarity_score=similarity.total_score,
                adjustments=[
                    AdjustmentItem(**adj) for adj in adjustments.to_list()
                ],
                adjusted_price=adjusted_price,
                price_per_sqft=ppsf,
                adjusted_price_per_sqft=adjusted_ppsf
            )
            
            comps.append(comp)
            prices.append(float(close_price))
            adjusted_prices.append(float(adjusted_price))
            if ppsf:
                ppsf_values.append(float(ppsf))
            if raw.get("DaysOnMarket"):
                dom_values.append(raw["DaysOnMarket"])
        
        # Detect outliers
        outliers = detect_all_outliers(subject_data, selected_raw[:MAX_SELECTED_COMPS])
        for comp in comps:
            if comp.listing_id in outliers:
                outlier = outliers[comp.listing_id]
                comp.is_outlier = outlier.is_outlier
                if outlier.is_outlier:
                    comp.outlier_reason = ", ".join(r.value for r in outlier.reasons)
        
        audit(
            AuditAction.OUTLIERS_DETECTED,
            {"count": sum(1 for o in outliers.values() if o.is_outlier)}
        )
        
        # Calculate analytics
        import statistics
        
        median_price = Decimal(str(statistics.median(prices))) if prices else Decimal(0)
        mean_price = Decimal(str(statistics.mean(prices))) if prices else Decimal(0)
        std_price = Decimal(str(statistics.stdev(prices))) if len(prices) > 1 else Decimal(0)
        median_ppsf = Decimal(str(statistics.median(ppsf_values))) if ppsf_values else Decimal(0)
        mean_ppsf = Decimal(str(statistics.mean(ppsf_values))) if ppsf_values else Decimal(0)
        median_adj = Decimal(str(statistics.median(adjusted_prices))) if adjusted_prices else Decimal(0)
        mean_adj = Decimal(str(statistics.mean(adjusted_prices))) if adjusted_prices else Decimal(0)
        avg_dom = Decimal(str(statistics.mean(dom_values))) if dom_values else Decimal(0)
        
        # Indicated value from adjusted prices
        indicated = median_adj
        value_range = std_price * 2 if std_price > 0 else median_price * Decimal("0.05")
        
        analytics = AnalyticsSection(
            indicated_value=indicated,
            value_range_low=indicated - value_range,
            value_range_high=indicated + value_range,
            confidence_score=Decimal("75"),  # Would be calculated based on comp quality
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
        
        audit(
            AuditAction.VALUE_ESTIMATED,
            {
                "indicated_value": float(indicated),
                "range_low": float(analytics.value_range_low),
                "range_high": float(analytics.value_range_high)
            }
        )
        
        # Build limitations
        limitations = []
        if len(comps) < 3:
            limitations.append(DataLimitation(
                category="sample_size",
                description="Fewer than 3 comparable sales found. Results may be less reliable.",
                severity="warning"
            ))
        
        # Create report
        report = ReportJSON(
            subject=subject,
            selected_comps=comps,
            analytics=analytics,
            limitations=limitations,
            data_source=settings.data_source.value
        )
        
        audit(AuditAction.REPORT_GENERATED, {"comp_count": len(comps)})
        
        # Generate narrative if requested
        narrative = None
        if request.include_narrative:
            try:
                writer = ReportWriter(state.llm_client)
                narrative = writer.generate(report)
                audit(AuditAction.REPORT_VERIFIED, {"narrative_length": len(narrative)})
            except HallucinationError as e:
                audit(
                    AuditAction.HALLUCINATION_DETECTED,
                    {"values": [str(v) for v in e.hallucinated_values[:5]]}
                )
                audit(AuditAction.REPORT_FAILED, {"reason": "hallucination"})
                raise HTTPException(
                    status_code=500,
                    detail=f"Report generation failed due to hallucination: {e.message}"
                )
        
        # Return based on format
        if request.output_format == "html":
            html = render_html_report(report, narrative)
            return HTMLResponse(content=html)
        
        return {
            "success": True,
            "report": report.model_dump(mode="json"),
            "narrative": narrative,
            "session_id": request.session_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        audit(AuditAction.REPORT_FAILED, {"error": str(e)})
        logger.exception("Report generation failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        state.audit_log.end_correlation()


@app.get("/audit/{session_id}")
async def get_audit_log(session_id: str):
    """Get audit log entries for a session (for debugging/compliance)."""
    entries = state.audit_log.get_entries()
    session_entries = [
        e.to_dict() for e in entries
        if e.details.get("session_id") == session_id
    ]
    return {"entries": session_entries}


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
