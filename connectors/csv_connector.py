"""
CSV Connector: Reads MLS data from CSV exports.

This connector provides a way to work with MLS data exported as CSV files.
It maps CSV columns to RESO field names and applies filters using pandas.

This is useful for:
- Offline development without API access
- Processing historical data exports
- Testing with known datasets
"""

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from connectors.base import DataConnector, ListingRecord
from domain.policies import BackendCapability, BACKEND_CAPABILITIES
from domain.query_plan import QueryPlan, FilterOperator


# Column mapping from common CSV formats to RESO field names
DEFAULT_COLUMN_MAP: dict[str, str] = {
    # Common variations -> RESO standard
    "listing_id": "ListingId",
    "mls_number": "ListingId",
    "mls_id": "ListingId",
    "list_price": "ListPrice",
    "listprice": "ListPrice",
    "close_price": "ClosePrice",
    "sold_price": "ClosePrice",
    "closeprice": "ClosePrice",
    "original_list_price": "OriginalListPrice",
    "close_date": "CloseDate",
    "sold_date": "CloseDate",
    "closedate": "CloseDate",
    "days_on_market": "DaysOnMarket",
    "dom": "DaysOnMarket",
    "property_type": "PropertyType",
    "propertytype": "PropertyType",
    "type": "PropertyType",
    "bedrooms": "BedroomsTotal",
    "beds": "BedroomsTotal",
    "br": "BedroomsTotal",
    "bathrooms": "BathroomsTotalInteger",
    "baths": "BathroomsTotalInteger",
    "ba": "BathroomsTotalInteger",
    "bathrooms_full": "BathroomsFull",
    "bathrooms_half": "BathroomsHalf",
    "living_area": "LivingArea",
    "sqft": "LivingArea",
    "square_feet": "LivingArea",
    "living_area_sqft": "LivingArea",
    "gla": "LivingArea",
    "lot_size": "LotSizeSquareFeet",
    "lot_sqft": "LotSizeSquareFeet",
    "lot_size_sqft": "LotSizeSquareFeet",
    "year_built": "YearBuilt",
    "yearbuilt": "YearBuilt",
    "built": "YearBuilt",
    "stories": "StoriesTotal",
    "levels": "StoriesTotal",
    "garage": "GarageSpaces",
    "garage_spaces": "GarageSpaces",
    "pool": "PoolPrivateYN",
    "has_pool": "PoolPrivateYN",
    "city": "City",
    "state": "StateOrProvince",
    "zip": "PostalCode",
    "zip_code": "PostalCode",
    "postal_code": "PostalCode",
    "latitude": "Latitude",
    "lat": "Latitude",
    "longitude": "Longitude",
    "lng": "Longitude",
    "lon": "Longitude",
    "status": "StandardStatus",
    "public_remarks": "PublicRemarks",
    "remarks": "PublicRemarks",
    "description": "PublicRemarks",
}


class CSVConnector(DataConnector):
    """
    Connector that reads listing data from CSV files.
    
    Features:
    - Automatic column name mapping to RESO fields
    - Pandas-based filtering
    - Works completely offline
    """
    
    def __init__(
        self,
        csv_path: str | Path,
        column_map: dict[str, str] | None = None,
        encoding: str = "utf-8"
    ):
        super().__init__(source_name="csv")
        self.csv_path = Path(csv_path)
        self.column_map = {**DEFAULT_COLUMN_MAP, **(column_map or {})}
        self.encoding = encoding
        self._df: pd.DataFrame | None = None
        self._load_data()
    
    @property
    def capability(self) -> BackendCapability:
        """Return CSV backend capabilities."""
        cap = BACKEND_CAPABILITIES["csv"]
        # Set available fields based on loaded data
        if self._df is not None:
            cap.available_fields = set(self._df.columns)
        return cap
    
    def _load_data(self):
        """Load and normalize the CSV data."""
        if not self.csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self.csv_path}")
        
        # Read CSV
        self._df = pd.read_csv(self.csv_path, encoding=self.encoding)
        
        # Normalize column names
        self._df = self._normalize_columns(self._df)
        
        # Convert date columns
        date_columns = ["CloseDate", "ListingContractDate", "OnMarketDate"]
        for col in date_columns:
            if col in self._df.columns:
                self._df[col] = pd.to_datetime(self._df[col], errors="coerce")
    
    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map CSV column names to RESO standard names."""
        rename_map = {}
        
        for col in df.columns:
            # Try lowercase lookup
            normalized = col.lower().strip().replace(" ", "_")
            if normalized in self.column_map:
                rename_map[col] = self.column_map[normalized]
            # If already RESO name, keep it
            elif col in self.column_map.values():
                pass
        
        return df.rename(columns=rename_map)
    
    def _execute_search(self, query_plan: QueryPlan) -> list[dict[str, Any]]:
        """
        Execute search by filtering the DataFrame.
        """
        if self._df is None or self._df.empty:
            return []
        
        # Start with all data
        result = self._df.copy()
        
        # Apply filters
        for f in query_plan.filters:
            if f.field not in result.columns:
                # Skip filters for fields not in data
                continue
            
            try:
                if f.operator == FilterOperator.EQ:
                    result = result[result[f.field] == f.value]
                elif f.operator == FilterOperator.NE:
                    result = result[result[f.field] != f.value]
                elif f.operator == FilterOperator.GT:
                    result = result[result[f.field] > f.value]
                elif f.operator == FilterOperator.GE:
                    result = result[result[f.field] >= f.value]
                elif f.operator == FilterOperator.LT:
                    result = result[result[f.field] < f.value]
                elif f.operator == FilterOperator.LE:
                    result = result[result[f.field] <= f.value]
                elif f.operator == FilterOperator.CONTAINS:
                    result = result[
                        result[f.field].astype(str).str.contains(
                            str(f.value), case=False, na=False
                        )
                    ]
                elif f.operator == FilterOperator.STARTSWITH:
                    result = result[
                        result[f.field].astype(str).str.startswith(
                            str(f.value), na=False
                        )
                    ]
            except (TypeError, ValueError):
                # Skip problematic filter
                continue
        
        # Apply ordering
        if query_plan.order_by:
            sort_cols = [o.field for o in query_plan.order_by if o.field in result.columns]
            sort_asc = [o.direction.value == "asc" for o in query_plan.order_by if o.field in result.columns]
            if sort_cols:
                result = result.sort_values(by=sort_cols, ascending=sort_asc)
        
        # Apply limit
        result = result.head(query_plan.max_results)
        
        # Select only requested fields if specified
        if query_plan.select_fields:
            available_fields = [f for f in query_plan.select_fields if f in result.columns]
            if available_fields:
                result = result[available_fields]
        
        # Convert to list of dicts
        return result.to_dict(orient="records")
    
    def get_by_id(self, listing_id: str) -> ListingRecord | None:
        """Get a listing by its ListingId."""
        if self._df is None:
            return None
        
        matches = self._df[self._df["ListingId"] == listing_id]
        if matches.empty:
            return None
        
        return ListingRecord(
            raw_data=matches.iloc[0].to_dict(),
            source=self.source_name,
            retrieved_at=datetime.utcnow()
        )
    
    def health_check(self) -> bool:
        """Check if CSV data is loaded and valid."""
        return self._df is not None and not self._df.empty
    
    def get_stats(self) -> dict[str, Any]:
        """Return statistics about the loaded data."""
        if self._df is None:
            return {"status": "not_loaded"}
        
        return {
            "status": "loaded",
            "record_count": len(self._df),
            "columns": list(self._df.columns),
            "file_path": str(self.csv_path),
        }
    
    def reload(self):
        """Reload data from CSV file."""
        self._load_data()
