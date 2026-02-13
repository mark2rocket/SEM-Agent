"""Google Ads API service."""

from google.ads.googleads.client import GoogleAdsClient
from datetime import date
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)


class GoogleAdsService:
    """Service for Google Ads API integration."""

    def __init__(
        self,
        developer_token: str,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        login_customer_id: str = None
    ):
        self.client = GoogleAdsClient.load_from_dict({
            "developer_token": developer_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "login_customer_id": login_customer_id,
            "use_proto_plus": True
        })

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
            # Remove hyphens from customer_id if present
            customer_id_clean = customer_id.replace("-", "")
            logger.info(f"Cleaned customer ID: {customer_id_clean}")

            ga_service = self.client.get_service("GoogleAdsService")

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
                # Build campaign ID filter: campaign.id IN (id1, id2, ...)
                campaign_id_list = ', '.join(campaign_ids)
                query += f" AND campaign.id IN ({campaign_id_list})"

            # Execute search request
            response = ga_service.search(customer_id=customer_id_clean, query=query)

            # Aggregate metrics
            total_cost_micros = 0
            total_conversions = 0.0
            total_conversion_value = 0.0
            total_clicks = 0
            total_impressions = 0

            for row in response:
                total_cost_micros += row.metrics.cost_micros
                total_conversions += row.metrics.conversions
                total_conversion_value += row.metrics.conversions_value
                total_clicks += row.metrics.clicks
                total_impressions += row.metrics.impressions

            # Convert micros to actual currency
            cost = total_cost_micros / 1_000_000

            # Calculate ROAS (avoid division by zero)
            roas = (total_conversion_value / cost * 100) if cost > 0 else 0.0

            return {
                "cost": cost,
                "conversions": total_conversions,
                "conversion_value": total_conversion_value,
                "clicks": total_clicks,
                "impressions": total_impressions,
                "roas": roas
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
        """Get search terms with performance data."""
        logger.info(f"Fetching search terms for {customer_id} from {date_from} to {date_to}")

        try:
            # Remove hyphens from customer_id if present
            customer_id_clean = customer_id.replace("-", "")

            ga_service = self.client.get_service("GoogleAdsService")

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
            response = ga_service.search(customer_id=customer_id_clean, query=query)

            # Build result list
            search_terms = []
            for row in response:
                search_terms.append({
                    "search_term": row.search_term_view.search_term,
                    "campaign_id": str(row.campaign.id),
                    "campaign_name": row.campaign.name,
                    "cost": row.metrics.cost_micros / 1_000_000,
                    "clicks": row.metrics.clicks,
                    "conversions": row.metrics.conversions
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
            ga_service = self.client.get_service("GoogleAdsService")

            # Use login_customer_id to query accessible accounts
            login_customer_id = self.client.login_customer_id
            if not login_customer_id:
                logger.error("No login_customer_id set, cannot list accounts")
                return []

            # Remove hyphens from login_customer_id if present
            login_customer_id_clean = str(login_customer_id).replace("-", "")
            logger.info(f"Using cleaned login_customer_id: {login_customer_id_clean}")

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

                client_response = ga_service.search(customer_id=login_customer_id_clean, query=client_query)

                for row in client_response:
                    accounts.append({
                        "customer_id": str(row.customer_client.id),
                        "account_name": row.customer_client.descriptive_name or f"Account {row.customer_client.id}",
                        "currency": row.customer_client.currency_code,
                        "timezone": row.customer_client.time_zone
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

                own_response = ga_service.search(customer_id=login_customer_id_clean, query=own_account_query)

                for row in own_response:
                    accounts.append({
                        "customer_id": str(row.customer.id),
                        "account_name": row.customer.descriptive_name or f"Account {row.customer.id}",
                        "currency": row.customer.currency_code,
                        "timezone": row.customer.time_zone
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
        logger.info(f"Login customer ID: {self.client.login_customer_id}")
        logger.info(f"Developer token: {self.client.developer_token[:10]}...")

        try:
            # Remove hyphens from customer_id if present
            customer_id_clean = customer_id.replace("-", "")
            logger.info(f"Cleaned customer ID: {customer_id_clean}")

            ga_service = self.client.get_service("GoogleAdsService")
            logger.info(f"GoogleAdsService retrieved successfully")

            # GAQL query to fetch campaign details
            query = """
                SELECT
                    campaign.id,
                    campaign.name,
                    campaign.status
                FROM campaign
                WHERE campaign.status IN ('ENABLED', 'PAUSED')
            """

            logger.info(f"Executing search query with customer_id={customer_id_clean}")
            response = ga_service.search(customer_id=customer_id_clean, query=query)

            campaigns = []
            for row in response:
                campaigns.append({
                    "id": str(row.campaign.id),
                    "name": row.campaign.name,
                    "status": row.campaign.status.name
                })

            logger.info(f"Found {len(campaigns)} campaigns")
            return campaigns

        except Exception as e:
            logger.error(f"Failed to list campaigns: {e}", exc_info=True)
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            raise

    def add_negative_keyword(
        self,
        customer_id: str,
        campaign_id: str,
        keyword_text: str,
        match_type: str = "EXACT"
    ) -> bool:
        """Add negative keyword to campaign."""
        logger.info(f"Adding negative keyword: {keyword_text} to campaign {campaign_id}")

        try:
            # Remove hyphens from customer_id if present
            customer_id_clean = customer_id.replace("-", "")

            # Get the CampaignCriterionService
            campaign_criterion_service = self.client.get_service("CampaignCriterionService")

            # Create campaign criterion operation
            campaign_criterion_operation = self.client.get_type("CampaignCriterionOperation")
            campaign_criterion = campaign_criterion_operation.create

            # Set campaign resource name
            campaign_criterion.campaign = self.client.get_service("CampaignService").campaign_path(
                customer_id_clean, campaign_id
            )

            # Mark as negative criterion
            campaign_criterion.negative = True

            # Set keyword criterion
            campaign_criterion.keyword.text = keyword_text

            # Map match type string to enum
            keyword_match_type_enum = self.client.enums.KeywordMatchTypeEnum
            if match_type.upper() == "EXACT":
                campaign_criterion.keyword.match_type = keyword_match_type_enum.EXACT
            elif match_type.upper() == "PHRASE":
                campaign_criterion.keyword.match_type = keyword_match_type_enum.PHRASE
            elif match_type.upper() == "BROAD":
                campaign_criterion.keyword.match_type = keyword_match_type_enum.BROAD
            else:
                logger.warning(f"Unknown match type '{match_type}', defaulting to EXACT")
                campaign_criterion.keyword.match_type = keyword_match_type_enum.EXACT

            # Execute the mutate request
            response = campaign_criterion_service.mutate_campaign_criteria(
                customer_id=customer_id_clean,
                operations=[campaign_criterion_operation]
            )

            logger.info(f"Successfully added negative keyword. Resource name: {response.results[0].resource_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to add negative keyword '{keyword_text}': {e}")
            return False
