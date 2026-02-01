"""Keyword detection and approval service."""

from datetime import datetime, timedelta
from typing import List, Dict
from sqlalchemy.orm import Session
import logging

from ..models.keyword import KeywordCandidate, ApprovalRequest, KeywordStatus, ApprovalAction
from ..models.google_ads import PerformanceThreshold, GoogleAdsAccount

logger = logging.getLogger(__name__)


class KeywordService:
    """Service for keyword automation."""

    def __init__(self, db: Session, google_ads_service, slack_service):
        self.db = db
        self.google_ads = google_ads_service
        self.slack = slack_service

    def detect_inefficient_keywords(self, tenant_id: int) -> List[Dict]:
        """Detect search terms with poor performance."""
        logger.info(f"Detecting inefficient keywords for tenant {tenant_id}")

        # 1. Get performance thresholds from database
        threshold = self.db.query(PerformanceThreshold).filter_by(
            tenant_id=tenant_id
        ).first()

        # Use defaults if not found
        min_cost = threshold.min_cost_for_detection if threshold else 10000.0
        min_clicks = threshold.min_clicks_for_detection if threshold else 5
        lookback_days = threshold.lookback_days if threshold else 7

        logger.info(f"Using thresholds - cost: {min_cost}, clicks: {min_clicks}, lookback: {lookback_days} days")

        # 2. Calculate date range
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=lookback_days)

        # 3. Fetch search terms from Google Ads
        # Get customer_id from GoogleAdsAccount
        google_ads_account = self.db.query(GoogleAdsAccount).filter_by(tenant_id=tenant_id).first()
        customer_id = google_ads_account.customer_id if google_ads_account else None

        search_terms = self.google_ads.get_search_terms(
            customer_id=customer_id,
            date_from=start_date,
            date_to=end_date
        )

        logger.info(f"Retrieved {len(search_terms)} search terms from Google Ads")

        # 4. Filter inefficient keywords and save to database
        detected_keywords = []

        for term in search_terms:
            # Check inefficiency criteria
            if (term['cost'] >= min_cost and
                term['clicks'] >= min_clicks and
                term['conversions'] == 0):

                # 5. Check if keyword already exists
                exists = self.db.query(KeywordCandidate).filter_by(
                    tenant_id=tenant_id,
                    search_term=term['search_term'],
                    campaign_id=term['campaign_id']
                ).first()

                if not exists:
                    # Create new KeywordCandidate record
                    candidate = KeywordCandidate(
                        tenant_id=tenant_id,
                        campaign_id=term['campaign_id'],
                        campaign_name=term['campaign_name'],
                        search_term=term['search_term'],
                        cost=term['cost'],
                        clicks=term['clicks'],
                        conversions=0,
                        detected_at=datetime.utcnow(),
                        status=KeywordStatus.PENDING
                    )
                    self.db.add(candidate)

                    detected_keywords.append({
                        "search_term": term['search_term'],
                        "campaign_id": term['campaign_id'],
                        "campaign_name": term['campaign_name'],
                        "cost": term['cost'],
                        "clicks": term['clicks'],
                        "conversions": 0
                    })

                    logger.info(f"Detected inefficient keyword: {term['search_term']} (cost: {term['cost']}, clicks: {term['clicks']})")

        # 6. Filter out recently ignored keywords (within 24 hours)
        if detected_keywords:
            recently_ignored_keywords = (
                self.db.query(KeywordCandidate.search_term)
                .join(ApprovalRequest, ApprovalRequest.keyword_candidate_id == KeywordCandidate.id)
                .filter(
                    KeywordCandidate.tenant_id == tenant_id,
                    ApprovalRequest.action == ApprovalAction.IGNORE,
                    ApprovalRequest.responded_at.isnot(None),
                    ApprovalRequest.responded_at > datetime.utcnow() - timedelta(hours=24)
                )
                .all()
            )

            ignored_terms = {row[0] for row in recently_ignored_keywords}

            if ignored_terms:
                logger.info(f"Filtering out {len(ignored_terms)} recently ignored keywords: {ignored_terms}")

            # Filter out ignored keywords from detected_keywords list
            detected_keywords = [
                kw for kw in detected_keywords
                if kw["search_term"] not in ignored_terms
            ]

            logger.info(f"After filtering ignores: {len(detected_keywords)} keywords remain")

        # 7. Commit to database
        if detected_keywords:
            self.db.commit()
            logger.info(f"Saved {len(detected_keywords)} new keyword candidates")
        else:
            logger.info("No new inefficient keywords detected")

        # 8. Return list of detected keywords
        return detected_keywords

    def create_approval_request(self, tenant_id: int, keyword_data: Dict) -> int:
        """Create approval request and send Slack alert."""
        logger.info(f"Creating approval request for keyword: {keyword_data.get('search_term')}")

        try:
            # 1. Create or get KeywordCandidate record
            keyword = self.db.query(KeywordCandidate).filter_by(
                tenant_id=tenant_id,
                search_term=keyword_data['search_term'],
                campaign_id=keyword_data['campaign_id']
            ).first()

            if not keyword:
                keyword = KeywordCandidate(
                    tenant_id=tenant_id,
                    campaign_id=keyword_data['campaign_id'],
                    campaign_name=keyword_data['campaign_name'],
                    search_term=keyword_data['search_term'],
                    cost=keyword_data['cost'],
                    clicks=keyword_data['clicks'],
                    conversions=keyword_data.get('conversions', 0),
                    detected_at=datetime.utcnow(),
                    status=KeywordStatus.PENDING
                )
                self.db.add(keyword)
                self.db.flush()

            # 2. Create ApprovalRequest record first (to get ID)
            expires_at = datetime.utcnow() + timedelta(hours=24)
            approval = ApprovalRequest(
                keyword_candidate_id=keyword.id,
                slack_message_ts="",  # Will update after sending
                expires_at=expires_at
            )
            self.db.add(approval)
            self.db.flush()  # Get approval.id

            # 3. Build Slack alert message with approval_request_id
            message = self.slack.build_keyword_alert_message(keyword_data, approval.id)

            # 4. Send message to Slack channel
            response = self.slack.send_message(message)

            # 5. Update approval with slack_message_ts
            approval.slack_message_ts = response['ts']

            # 6. Commit to database
            self.db.commit()

            logger.info(f"Created approval request {approval.id} for keyword: {keyword_data.get('search_term')}")
            return approval.id

        except Exception as e:
            logger.error(f"Failed to create approval request: {e}")
            self.db.rollback()
            raise

    def approve_keyword(self, approval_request_id: int, slack_user_id: str) -> bool:
        """Approve and add negative keyword to Google Ads."""
        logger.info(f"Approving keyword request {approval_request_id}")

        try:
            # 1. Query ApprovalRequest and related KeywordCandidate
            approval = self.db.query(ApprovalRequest).filter_by(
                id=approval_request_id
            ).first()

            if not approval:
                logger.warning(f"Approval request {approval_request_id} not found")
                return False

            # 2. Check if already responded
            if approval.responded_at:
                logger.warning(f"Approval request {approval_request_id} already responded to")
                return False

            # 3. Validate request hasn't expired
            if approval.expires_at < datetime.utcnow():
                logger.warning(f"Approval request {approval_request_id} has expired")
                return False

            keyword = approval.keyword_candidate

            # 4. Update ApprovalRequest
            approval.responded_at = datetime.utcnow()
            approval.approved_by = slack_user_id
            approval.action = ApprovalAction.APPROVE

            # 5. Call Google Ads API to add negative keyword
            try:
                # Get customer_id from GoogleAdsAccount
                google_ads_account = self.db.query(GoogleAdsAccount).filter_by(tenant_id=keyword.tenant_id).first()
                customer_id = google_ads_account.customer_id if google_ads_account else None

                self.google_ads.add_negative_keyword(
                    customer_id=customer_id,
                    campaign_id=keyword.campaign_id,
                    keyword_text=keyword.search_term
                )
            except Exception as ads_error:
                logger.error(f"Failed to add negative keyword to Google Ads: {ads_error}")
                self.db.rollback()
                return False

            # 6. Update KeywordCandidate status
            keyword.status = KeywordStatus.APPROVED

            # 7. Commit to database
            self.db.commit()

            logger.info(f"Successfully approved keyword: {keyword.search_term}")
            return True

        except Exception as e:
            logger.error(f"Failed to approve keyword: {e}")
            self.db.rollback()
            return False
