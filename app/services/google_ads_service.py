"""Google Ads API service - REST API implementation."""

import requests
from datetime import date
from typing import List, Dict, Optional
import logging
import time

logger = logging.getLogger(__name__)


class GoogleAdsService:
    """Service for Google Ads API integration using REST API."""

    # API 버전
    API_VERSION = "v21"
    BASE_URL = f"https://googleads.googleapis.com/{API_VERSION}"

    # Access token 캐시
    _access_token: Optional[str] = None
    _token_expiry: float = 0

    def __init__(
        self,
        developer_token: str,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        login_customer_id: str = None
    ):
        """Initialize Google Ads service with OAuth credentials.

        Args:
            developer_token: Google Ads Developer Token
            client_id: OAuth Client ID
            client_secret: OAuth Client Secret
            refresh_token: OAuth Refresh Token
            login_customer_id: Manager account ID (optional)
        """
        self.developer_token = developer_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.login_customer_id = login_customer_id

    def _get_access_token(self) -> str:
        """Get access token (cached or refresh).

        Returns:
            Access token string
        """
        # 캐시된 토큰이 유효하면 재사용
        if self._access_token and time.time() < self._token_expiry - 60:
            return self._access_token

        logger.info("Refreshing access token")

        token_url = "https://oauth2.googleapis.com/token"
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }

        try:
            response = requests.post(token_url, data=payload, timeout=10)
            response.raise_for_status()

            token_data = response.json()
            self._access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 3600)
            self._token_expiry = time.time() + expires_in

            logger.info("Access token refreshed successfully")
            return self._access_token

        except Exception as e:
            logger.error(f"Failed to refresh access token: {e}")
            raise

    def _build_headers(self) -> Dict[str, str]:
        """Build headers for Google Ads API requests.

        Returns:
            Headers dictionary
        """
        access_token = self._get_access_token()

        headers = {
            "Authorization": f"Bearer {access_token}",
            "developer-token": self.developer_token,
            "Content-Type": "application/json",
        }

        # Manager account로 접근하는 경우
        if self.login_customer_id:
            headers["login-customer-id"] = str(self.login_customer_id).replace("-", "")

        return headers

    def _call_search_stream(
        self,
        customer_id: str,
        query: str
    ) -> List[Dict]:
        """Call Google Ads searchStream API.

        Args:
            customer_id: Google Ads customer ID
            query: GAQL query string

        Returns:
            List of result rows
        """
        customer_id_clean = customer_id.replace("-", "")
        endpoint = f"{self.BASE_URL}/customers/{customer_id_clean}/googleAds:searchStream"

        headers = self._build_headers()
        payload = {"query": query}

        try:
            logger.debug(f"Calling searchStream for customer {customer_id_clean}")
            logger.debug(f"Query: {query.strip()}")

            response = requests.post(endpoint, headers=headers, json=payload, timeout=30)

            if response.status_code != 200:
                logger.error(f"API error ({response.status_code}): {response.text}")
                response.raise_for_status()

            # searchStream returns array of chunks
            data = response.json()
            results = []

            if isinstance(data, list):
                for chunk in data:
                    chunk_results = chunk.get("results", [])
                    results.extend(chunk_results)

            logger.debug(f"Received {len(results)} results")
            return results

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to call searchStream: {e}")
            raise

    def get_performance_metrics(
        self,
        customer_id: str,
        date_from: date,
        date_to: date,
        campaign_ids: List[str] = None
    ) -> Dict:
        """Fetch performance metrics for date range.

        Args:
            customer_id: Google Ads customer ID
            date_from: Start date
            date_to: End date
            campaign_ids: Optional list of campaign IDs to filter by

        Returns:
            Dict with aggregated metrics
        """
        logger.info(f"Fetching metrics for {customer_id} from {date_from} to {date_to}")
        if campaign_ids:
            logger.info(f"Filtering by {len(campaign_ids)} campaigns: {campaign_ids}")

        try:
            # GAQL query for campaign metrics
            query = f"""
                SELECT
                    metrics.cost_micros,
                    metrics.conversions,
                    metrics.conversions_value,
                    metrics.clicks,
                    metrics.impressions
                FROM campaign
                WHERE segments.date BETWEEN '{date_from.strftime('%Y-%m-%d')}'
                    AND '{date_to.strftime('%Y-%m-%d')}'
            """

            # Add campaign filter if campaign_ids provided
            if campaign_ids:
                campaign_id_list = ', '.join(campaign_ids)
                query += f" AND campaign.id IN ({campaign_id_list})"

            # Execute search request
            results = self._call_search_stream(customer_id, query)

            # Aggregate metrics
            total_cost_micros = 0
            total_conversions = 0.0
            total_conversion_value = 0.0
            total_clicks = 0
            total_impressions = 0

            for row in results:
                metrics = row.get("metrics", {})
                total_cost_micros += int(metrics.get("costMicros", 0))
                total_conversions += float(metrics.get("conversions", 0))
                total_conversion_value += float(metrics.get("conversionsValue", 0))
                total_clicks += int(metrics.get("clicks", 0))
                total_impressions += int(metrics.get("impressions", 0))

            # Convert micros to actual currency
            cost = total_cost_micros / 1_000_000

            # Calculate derived metrics (avoid division by zero)
            cpc = (cost / total_clicks) if total_clicks > 0 else 0.0
            cpa = (cost / total_conversions) if total_conversions > 0 else 0.0

            return {
                "cost": cost,
                "conversions": total_conversions,
                "conversion_value": total_conversion_value,
                "clicks": total_clicks,
                "impressions": total_impressions,
                "cpc": cpc,
                "cpa": cpa
            }

        except Exception as e:
            logger.error(f"Failed to fetch performance metrics: {e}")
            raise

    async def get_campaign_metrics(
        self,
        customer_id: str,
        date_from: date,
        date_to: date,
        metrics: List[str] = None
    ) -> Dict:
        """Async wrapper for get_performance_metrics with CTR calculation.

        Args:
            customer_id: Google Ads customer ID
            date_from: Start date for metrics
            date_to: End date for metrics
            metrics: List of metric names to include (unused, kept for signature compatibility)

        Returns:
            Dict with cost, impressions, clicks, conversions, ctr, conversion_value, roas
        """
        if metrics is None:
            metrics = ["cost", "impressions", "clicks", "conversions", "ctr"]

        try:
            # Call sync method (get_performance_metrics is synchronous)
            result = self.get_performance_metrics(customer_id, date_from, date_to)

            # Add CTR calculation
            impressions = result.get("impressions", 0)
            clicks = result.get("clicks", 0)
            result["ctr"] = (clicks / impressions * 100) if impressions > 0 else 0.0

            return result

        except Exception as e:
            logger.error(f"Failed to fetch campaign metrics: {e}")
            raise

    def get_search_terms(
        self,
        customer_id: str,
        date_from: date,
        date_to: date,
        min_cost: float = 0
    ) -> List[Dict]:
        """Get search terms with performance data.

        Args:
            customer_id: Google Ads customer ID
            date_from: Start date
            date_to: End date
            min_cost: Minimum cost filter (in currency units)

        Returns:
            List of search term dicts
        """
        logger.info(f"Fetching search terms for {customer_id} from {date_from} to {date_to}")

        try:
            # GAQL query for search term report
            query = f"""
                SELECT
                    search_term_view.search_term,
                    campaign.id,
                    campaign.name,
                    metrics.cost_micros,
                    metrics.clicks,
                    metrics.conversions
                FROM search_term_view
                WHERE segments.date BETWEEN '{date_from.strftime('%Y-%m-%d')}'
                    AND '{date_to.strftime('%Y-%m-%d')}'
                    AND metrics.cost_micros >= {int(min_cost * 1_000_000)}
            """

            # Execute search request
            results = self._call_search_stream(customer_id, query)

            # Build result list
            search_terms = []
            for row in results:
                search_term_view = row.get("searchTermView", {})
                campaign = row.get("campaign", {})
                metrics = row.get("metrics", {})

                search_terms.append({
                    "search_term": search_term_view.get("searchTerm", ""),
                    "campaign_id": str(campaign.get("id", "")),
                    "campaign_name": campaign.get("name", ""),
                    "cost": int(metrics.get("costMicros", 0)) / 1_000_000,
                    "clicks": int(metrics.get("clicks", 0)),
                    "conversions": float(metrics.get("conversions", 0))
                })

            logger.info(f"Found {len(search_terms)} search terms")
            return search_terms

        except Exception as e:
            logger.error(f"Failed to fetch search terms: {e}")
            raise

    def list_accessible_accounts(self) -> List[Dict]:
        """List all Google Ads accounts accessible to the authenticated user.

        Handles both single accounts and manager accounts (MCC).

        Returns:
            List of dicts with customer_id, account_name, currency, timezone
        """
        logger.info("Listing accessible Google Ads accounts")

        try:
            if not self.login_customer_id:
                logger.error("No login_customer_id set, cannot list accounts")
                return []

            login_customer_id_clean = str(self.login_customer_id).replace("-", "")
            logger.info(f"Using login_customer_id: {login_customer_id_clean}")

            accounts = []

            # Strategy 1: Try to get client accounts (for Manager/MCC accounts)
            try:
                logger.info("Attempting to list client accounts (Manager account mode)")
                client_query = """
                    SELECT
                        customer_client.id,
                        customer_client.descriptive_name,
                        customer_client.currency_code,
                        customer_client.time_zone
                    FROM customer_client
                    WHERE customer_client.manager = FALSE
                """

                results = self._call_search_stream(login_customer_id_clean, client_query)

                for row in results:
                    customer_client = row.get("customerClient", {})
                    customer_id = str(customer_client.get("id", ""))
                    accounts.append({
                        "customer_id": customer_id,
                        "account_name": customer_client.get("descriptiveName") or f"Account {customer_id}",
                        "currency": customer_client.get("currencyCode", ""),
                        "timezone": customer_client.get("timeZone", "")
                    })

                if accounts:
                    logger.info(f"Found {len(accounts)} client accounts via Manager account")
                    return accounts
                else:
                    logger.info("No client accounts found, trying single account mode")

            except Exception as e:
                logger.warning(f"Failed to list client accounts: {e}")

            # Strategy 2: Get own account info (for single advertising accounts)
            try:
                logger.info("Attempting to get own account info (single account mode)")
                own_account_query = """
                    SELECT
                        customer.id,
                        customer.descriptive_name,
                        customer.currency_code,
                        customer.time_zone
                    FROM customer
                """

                results = self._call_search_stream(login_customer_id_clean, own_account_query)

                for row in results:
                    customer = row.get("customer", {})
                    customer_id = str(customer.get("id", ""))
                    accounts.append({
                        "customer_id": customer_id,
                        "account_name": customer.get("descriptiveName") or f"Account {customer_id}",
                        "currency": customer.get("currencyCode", ""),
                        "timezone": customer.get("timeZone", "")
                    })

                if accounts:
                    logger.info(f"Found own account: {accounts[0]['account_name']}")
                    return accounts
                else:
                    logger.warning("No own account found either")

            except Exception as e:
                logger.warning(f"Failed to get own account info: {e}")

            logger.warning(f"No accessible accounts found for login_customer_id: {login_customer_id_clean}")
            return []

        except Exception as e:
            logger.error(f"Failed to list accessible accounts: {e}", exc_info=True)
            return []

    def list_campaigns(self, customer_id: str) -> List[Dict]:
        """List all campaigns for a customer account.

        Args:
            customer_id: Google Ads customer ID

        Returns:
            List of dicts with id, name, status (only ENABLED and PAUSED campaigns)
        """
        logger.info(f"Listing campaigns for customer {customer_id}")

        try:
            # GAQL query to fetch campaign details
            query = """
                SELECT
                    campaign.id,
                    campaign.name,
                    campaign.status
                FROM campaign
                WHERE campaign.status IN ('ENABLED', 'PAUSED')
            """

            results = self._call_search_stream(customer_id, query)

            campaigns = []
            for row in results:
                campaign = row.get("campaign", {})
                campaigns.append({
                    "id": str(campaign.get("id", "")),
                    "name": campaign.get("name", ""),
                    "status": campaign.get("status", "UNKNOWN")
                })

            logger.info(f"Found {len(campaigns)} campaigns")
            return campaigns

        except Exception as e:
            logger.error(f"Failed to list campaigns: {e}", exc_info=True)
            raise

    def generate_keyword_ideas(
        self,
        customer_id: str,
        seed_keywords: List[str],
        language_id: str = "1012",   # 한국어
        geo_target_id: str = "2410", # 대한민국
        limit: int = 10
    ) -> List[Dict]:
        """Fetch keyword ideas from Google Ads Keyword Planner.

        Args:
            customer_id: Google Ads customer ID
            seed_keywords: Seed keyword list
            language_id: Google language constant ID (1012=Korean)
            geo_target_id: Geo target constant ID (2410=South Korea)
            limit: Max number of results to return

        Returns:
            List of keyword idea dicts with metrics
        """
        customer_id_clean = customer_id.replace("-", "")
        endpoint = f"{self.BASE_URL}/customers/{customer_id_clean}:generateKeywordIdeas"
        headers = self._build_headers()

        payload = {
            "keywordSeed": {"keywords": seed_keywords},
            "language": f"languageConstants/{language_id}",
            "geoTargetConstants": [f"geoTargetConstants/{geo_target_id}"],
            "keywordPlanNetwork": "GOOGLE_SEARCH_AND_PARTNERS",
            "includeAdultKeywords": False,
            "pageSize": limit
        }

        logger.info(f"Generating keyword ideas for: {seed_keywords}")
        try:
            response = requests.post(endpoint, headers=headers, json=payload, timeout=30)
            if response.status_code != 200:
                logger.error(f"Keyword Planner API error ({response.status_code}): {response.text}")
                return []

            results = response.json().get("results", [])
            ideas = []
            for row in results:
                m = row.get("keywordIdeaMetrics", {})
                low_bid = int(m.get("lowTopOfPageBidMicros", 0)) // 1_000_000
                high_bid = int(m.get("highTopOfPageBidMicros", 0)) // 1_000_000
                ideas.append({
                    "keyword": row.get("text", ""),
                    "avg_monthly_searches": m.get("avgMonthlySearches", "N/A"),
                    "competition": m.get("competition", "UNKNOWN"),
                    "competition_index": m.get("competitionIndex", 0),
                    "low_bid_krw": low_bid,
                    "high_bid_krw": high_bid,
                })
            logger.info(f"Returned {len(ideas)} keyword ideas")
            return ideas

        except Exception as e:
            logger.error(f"generate_keyword_ideas error: {e}", exc_info=True)
            return []

    def add_negative_keyword(
        self,
        customer_id: str,
        campaign_id: str,
        keyword_text: str,
        match_type: str = "EXACT"
    ) -> bool:
        """Add negative keyword to campaign.

        Args:
            customer_id: Google Ads customer ID
            campaign_id: Campaign ID
            keyword_text: Keyword text to add as negative
            match_type: Match type (EXACT, PHRASE, BROAD)

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Adding negative keyword: {keyword_text} to campaign {campaign_id}")

        try:
            customer_id_clean = customer_id.replace("-", "")

            # Build campaign resource name
            campaign_resource = f"customers/{customer_id_clean}/campaigns/{campaign_id}"

            # Build criterion operation
            operation = {
                "create": {
                    "campaign": campaign_resource,
                    "negative": True,
                    "keyword": {
                        "text": keyword_text,
                        "matchType": match_type.upper()
                    }
                }
            }

            # Call mutate API
            endpoint = f"{self.BASE_URL}/customers/{customer_id_clean}/campaignCriteria:mutate"
            headers = self._build_headers()
            payload = {"operations": [operation]}

            response = requests.post(endpoint, headers=headers, json=payload, timeout=30)

            if response.status_code == 200:
                result = response.json()
                resource_name = result.get("results", [{}])[0].get("resourceName", "")
                logger.info(f"Successfully added negative keyword. Resource: {resource_name}")
                return True
            else:
                logger.error(f"Failed to add negative keyword ({response.status_code}): {response.text}")
                return False

        except Exception as e:
            logger.error(f"Failed to add negative keyword '{keyword_text}': {e}")
            return False
