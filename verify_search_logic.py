
import asyncio
from datetime import datetime, timedelta
from app.main import _load_sample_data
from connectors.reso_mock_connector import InMemoryRESOConnector, MockRESOServer
from domain.intent_ir import IntentIR
from domain.query_plan import QueryPlanBuilder

async def verify_search():
    # 1. Setup Data
    connector = InMemoryRESOConnector(MockRESOServer())
    _load_sample_data(connector)
    print(f"Total listings loaded: {len(connector._server.listings)}")
    
    # 2. Simulate User Intent (Older home, 1940s)
    # The parser yields subject_year_built but sold_within_years=2 (default)
    intent = IntentIR(
        subject_city="Denver",
        subject_state="CO",
        subject_beds=2,
        subject_baths=1.0,
        subject_sqft=980,
        subject_year_built=None, # User said "1940s" -> parser might output None or a year? 
                                 # If parser outputs 1940, does that filter?
                                 # Let's simple case: subject_year_built=None first.
        sold_within_years=2
    )
    
    # query_plan = QueryPlanBuilder.from_intent(intent)
    # print("\n--- Query Plan ---")
    # for f in query_plan.filters:
    #     print(f"Filter: {f.field} {f.operator} {f.value}")
    
    # result = connector.search(query_plan)
    # print(f"\nSearch Results (Intent 1): {len(result.records)}")
    
    # 3. Simulate specific case: 2 bed 1 bath
    intent2 = IntentIR(
        subject_city="Denver",
        subject_beds=2,
        subject_baths=1.0,
        subject_sqft=980,
        sold_within_years=2
    )
    
    plan2 = QueryPlanBuilder.from_intent(intent2)
    print("\n--- Query Plan 2 (2bd/1ba) ---")
    for f in plan2.filters:
        print(f"Filter: {f.field} {f.operator} {f.value}")
        
    result2 = connector.search(plan2)
    print(f"Search Results (Intent 2): {len(result2.records)}")
    
    for r in result2.records:
        print(f" - Found: {r.raw_data.get('ListingId')} | {r.raw_data.get('BedroomsTotal')}bd {r.raw_data.get('BathroomsTotalInteger')}ba | {r.raw_data.get('YearBuilt')}")

if __name__ == "__main__":
    asyncio.run(verify_search())
