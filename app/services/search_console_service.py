"""Google Search Console service."""

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from typing import Dict, List
from datetime import date
import logging

logger = logging.getLogger(__name__)

GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


class SearchConsoleService:
    """Service for Google Search Console API."""

    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self._service = None

    def _get_service(self):
        """Build and return authenticated GSC service."""
        if self._service is None:
            credentials = Credentials(
                token=None,
                refresh_token=self.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=GSC_SCOPES
            )
            credentials.refresh(Request())
            self._service = build("searchconsole", "v1", credentials=credentials)
        return self._service

    def list_sites(self) -> List[Dict]:
        """List all verified Search Console sites."""
        try:
            service = self._get_service()
            result = service.sites().list().execute()
            return result.get("siteEntry", [])
        except Exception as e:
            logger.error(f"GSC list_sites error: {e}", exc_info=True)
            raise

    def get_search_analytics(self, site_url: str, date_from: date, date_to: date) -> Dict:
        """Get overall search analytics (clicks, impressions, CTR, avg position)."""
        try:
            service = self._get_service()
            request_body = {
                "startDate": date_from.isoformat(),
                "endDate": date_to.isoformat(),
                "dimensions": [],
                "rowLimit": 1
            }
            result = service.searchanalytics().query(
                siteUrl=site_url, body=request_body
            ).execute()
            rows = result.get("rows", [])
            if not rows:
                return {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}
            row = rows[0]
            return {
                "clicks": int(row.get("clicks", 0)),
                "impressions": int(row.get("impressions", 0)),
                "ctr": round(row.get("ctr", 0.0) * 100, 2),
                "position": round(row.get("position", 0.0), 1)
            }
        except Exception as e:
            logger.error(f"GSC get_search_analytics error: {e}", exc_info=True)
            raise

    def get_top_queries(
        self, site_url: str, date_from: date, date_to: date, limit: int = 5
    ) -> List[Dict]:
        """Get top queries by clicks for the period."""
        try:
            service = self._get_service()
            request_body = {
                "startDate": date_from.isoformat(),
                "endDate": date_to.isoformat(),
                "dimensions": ["query"],
                "rowLimit": limit,
                "orderBy": [{"fieldName": "clicks", "sortOrder": "DESCENDING"}]
            }
            result = service.searchanalytics().query(
                siteUrl=site_url, body=request_body
            ).execute()
            rows = result.get("rows", [])
            queries = []
            for row in rows:
                queries.append({
                    "query": row["keys"][0],
                    "clicks": int(row.get("clicks", 0)),
                    "impressions": int(row.get("impressions", 0)),
                    "ctr": round(row.get("ctr", 0.0) * 100, 2),
                    "position": round(row.get("position", 0.0), 1)
                })
            return queries
        except Exception as e:
            logger.error(f"GSC get_top_queries error: {e}", exc_info=True)
            raise
