
from app.main import _load_sample_data
from connectors.reso_mock_connector import InMemoryRESOConnector, MockRESOServer

def verify():
    connector = InMemoryRESOConnector(MockRESOServer())
    _load_sample_data(connector)
    print(f"Total listings: {len(connector.listings)}")
    
    # Check for CMA-006
    cma006 = next((x for x in connector.listings if x["ListingId"] == "CMA-006"), None)
    if cma006:
        print("Found CMA-006")
        print(f"Beds: {cma006['BedroomsTotal']}")
        print(f"Baths: {cma006['BathroomsTotalInteger']}")
        print(f"Year: {cma006['YearBuilt']}")
    else:
        print("CMA-006 NOT FOUND")

if __name__ == "__main__":
    verify()
