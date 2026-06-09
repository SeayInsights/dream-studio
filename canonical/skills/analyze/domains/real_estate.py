#!/usr/bin/env python3
"""
Real Estate Skill Analyzer

Analyzes real estate skill repositories for 10 key capabilities:
- Property listings
- MLS integration
- Comparative market analysis (CMA)
- Property valuation/appraisal
- Market data aggregation
- Property search/filtering
- Investment analysis
- Document generation
- Client management
- Market reporting
"""

from pathlib import Path
from typing import Dict, List, Any
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.base_analyzer import BaseAnalyzer


class RealEstateSkillAnalyzer(BaseAnalyzer):
    """
    Analyzes real estate skill repositories

    Evaluates 10 real estate capabilities with weighted scoring:
    - Property listings (12%)
    - MLS integration (15%)
    - Comparative market analysis (15%)
    - Property valuation (12%)
    - Market data aggregation (10%)
    - Property search (8%)
    - Investment analysis (10%)
    - Document generation (8%)
    - Client management (5%)
    - Market reporting (5%)
    """

    WEIGHTS = {
        "listings": 0.12,
        "mls_integration": 0.15,
        "cma": 0.15,
        "valuation": 0.12,
        "market_data": 0.10,
        "search": 0.08,
        "investment_analysis": 0.10,
        "documents": 0.08,
        "crm": 0.05,
        "reporting": 0.05,
    }

    def get_domain_name(self) -> str:
        return "real_estate"

    def get_capabilities(self) -> List[str]:
        return [
            "listings",
            "mls_integration",
            "cma",
            "valuation",
            "market_data",
            "search",
            "investment_analysis",
            "documents",
            "crm",
            "reporting",
        ]

    def analyze_capability(self, capability: str) -> Dict[str, Any]:
        """Route capability analysis to specific method"""
        method_map = {
            "listings": self._analyze_listings,
            "mls_integration": self._analyze_mls,
            "cma": self._analyze_cma,
            "valuation": self._analyze_valuation,
            "market_data": self._analyze_market_data,
            "search": self._analyze_search,
            "investment_analysis": self._analyze_investment,
            "documents": self._analyze_documents,
            "crm": self._analyze_crm,
            "reporting": self._analyze_reporting,
        }

        if capability not in method_map:
            return {"detected": False, "score": 0.0, "evidence": [], "count": 0, "quality": "weak"}

        return method_map[capability]()

    def score_repository(self) -> Dict[str, float]:
        """Calculate weighted overall score"""
        scores = {}

        for capability in self.get_capabilities():
            result = self.analyze_capability(capability)
            scores[capability] = result["score"]

        overall = sum(scores[cap] * self.WEIGHTS[cap] for cap in scores.keys())
        scores["overall_score"] = round(overall, 1)

        return scores

    def _analyze_listings(self) -> Dict[str, Any]:
        """
        Analyze property listing capabilities

        Looks for:
        - Listing data structures
        - Listing templates
        - Property details schemas
        - Photo/media management
        - Listing syndication
        """
        evidence = []
        count = 0

        # Check for listing directories/files
        listing_files = self.find_files("**/*listing*.{py,js,ts,json}")
        listing_files.extend(self.find_files("**/*property*.{py,js,ts,json}"))
        if listing_files:
            evidence.append(f"{len(listing_files)} listing-related files")
            count += min(len(listing_files), 5)

        # Check for property schemas
        schema_matches = self.search_content(
            r"property.*schema|listing.*schema|property.*model", max_results=5
        )
        if schema_matches:
            evidence.append(f"Property data schemas ({len(schema_matches)} definitions)")
            count += len(schema_matches)

        # Check for photo management
        photo_matches = self.search_content(
            r"photo.*upload|image.*gallery|property.*photo", max_results=3
        )
        if photo_matches:
            evidence.append("Photo/media management")
            count += 1

        # Check for syndication
        syndication_matches = self.search_content(
            r"syndicate|zillow.*api|realtor.*api|trulia", max_results=3
        )
        if syndication_matches:
            evidence.append("Listing syndication")
            count += 2

        thresholds = {"excellent": 10, "good": 6, "adequate": 3}
        score, quality = self.calculate_quality_score(count, thresholds)

        return {
            "detected": count > 0,
            "score": score,
            "evidence": evidence,
            "count": count,
            "quality": quality,
        }

    def _analyze_mls(self) -> Dict[str, Any]:
        """
        Analyze MLS integration capabilities

        Looks for:
        - MLS API integration
        - RETS/WebAPI support
        - IDX compliance
        - MLS data sync
        - Multiple MLS support
        """
        evidence = []
        count = 0

        # Check for MLS files
        mls_files = self.find_files("**/*mls*.{py,js,ts}")
        if mls_files:
            evidence.append(f"{len(mls_files)} MLS integration files")
            count += min(len(mls_files), 5)

        # Check for RETS/WebAPI
        rets_matches = self.search_content(r"rets|web.*api.*mls|mls.*api|idx", max_results=5)
        if rets_matches:
            evidence.append(f"MLS API integration ({len(rets_matches)} references)")
            count += len(rets_matches) * 2  # Weight heavily

        # Check for data sync
        sync_matches = self.search_content(
            r"mls.*sync|sync.*mls|mls.*update|mls.*import", max_results=3
        )
        if sync_matches:
            evidence.append("MLS data synchronization")
            count += 1

        # Check for IDX compliance
        idx_matches = self.search_content(r"idx|internet.*data.*exchange", max_results=3)
        if idx_matches:
            evidence.append("IDX compliance")
            count += 1

        thresholds = {"excellent": 12, "good": 7, "adequate": 3}
        score, quality = self.calculate_quality_score(count, thresholds)

        return {
            "detected": count > 0,
            "score": score,
            "evidence": evidence,
            "count": count,
            "quality": quality,
        }

    def _analyze_cma(self) -> Dict[str, Any]:
        """
        Analyze comparative market analysis capabilities

        Looks for:
        - Comp selection algorithms
        - CMA report generation
        - Property comparison
        - Market adjustment factors
        - CMA templates
        """
        evidence = []
        count = 0

        # Check for CMA files
        cma_files = self.find_files("**/*cma*.{py,js,ts}")
        cma_files.extend(self.find_files("**/*comp*.{py,js,ts}"))
        if cma_files:
            evidence.append(f"{len(cma_files)} CMA files")
            count += min(len(cma_files), 5)

        # Check for comp selection
        comp_matches = self.search_content(
            r"comp.*selection|comparable.*property|find.*comps|comp.*analysis",
            file_extensions=[".py", ".js", ".ts"],
            max_results=5,
        )
        if comp_matches:
            evidence.append(f"Comp selection algorithms ({len(comp_matches)} implementations)")
            count += len(comp_matches) * 2  # Weight heavily

        # Check for CMA reports
        report_matches = self.search_content(
            r"cma.*report|market.*analysis.*report|generate.*cma", max_results=3
        )
        if report_matches:
            evidence.append("CMA report generation")
            count += 2

        # Check for adjustment factors
        adjustment_matches = self.search_content(
            r"adjustment.*factor|price.*adjustment|comp.*adjustment", max_results=3
        )
        if adjustment_matches:
            evidence.append("Market adjustment factors")
            count += 1

        thresholds = {"excellent": 12, "good": 7, "adequate": 3}
        score, quality = self.calculate_quality_score(count, thresholds)

        return {
            "detected": count > 0,
            "score": score,
            "evidence": evidence,
            "count": count,
            "quality": quality,
        }

    def _analyze_valuation(self) -> Dict[str, Any]:
        """
        Analyze property valuation/appraisal capabilities

        Looks for:
        - Valuation models
        - Automated valuation (AVM)
        - Appraisal methodologies
        - Price estimation
        - Valuation reports
        """
        evidence = []
        count = 0

        # Check for valuation files
        val_files = self.find_files("**/*valuation*.{py,js,ts}")
        val_files.extend(self.find_files("**/*appraisal*.{py,js,ts}"))
        if val_files:
            evidence.append(f"{len(val_files)} valuation files")
            count += min(len(val_files), 5)

        # Check for AVM
        avm_matches = self.search_content(
            r"avm|automated.*valuation|valuation.*model|price.*estimate",
            file_extensions=[".py", ".js", ".ts"],
            max_results=5,
        )
        if avm_matches:
            evidence.append(f"Automated valuation ({len(avm_matches)} implementations)")
            count += len(avm_matches) * 2

        # Check for methodologies
        method_matches = self.search_content(
            r"sales.*comparison|cost.*approach|income.*approach|appraisal.*method", max_results=5
        )
        if method_matches:
            evidence.append(f"Appraisal methodologies ({len(method_matches)} methods)")
            count += len(method_matches)

        thresholds = {"excellent": 10, "good": 6, "adequate": 3}
        score, quality = self.calculate_quality_score(count, thresholds)

        return {
            "detected": count > 0,
            "score": score,
            "evidence": evidence,
            "count": count,
            "quality": quality,
        }

    def _analyze_market_data(self) -> Dict[str, Any]:
        """
        Analyze market data aggregation capabilities

        Looks for:
        - Market trend analysis
        - Price history tracking
        - Neighborhood statistics
        - Market indicators
        - Data sources integration
        """
        evidence = []
        count = 0

        # Check for market data files
        market_files = self.find_files("**/*market*.{py,js,ts}")
        if market_files:
            evidence.append(f"{len(market_files)} market data files")
            count += min(len(market_files), 3)

        # Check for trend analysis
        trend_matches = self.search_content(
            r"market.*trend|trend.*analysis|price.*trend", max_results=5
        )
        if trend_matches:
            evidence.append(f"Market trend analysis ({len(trend_matches)} implementations)")
            count += len(trend_matches)

        # Check for neighborhood data
        neighborhood_matches = self.search_content(
            r"neighborhood.*data|neighborhood.*stats|area.*statistics", max_results=3
        )
        if neighborhood_matches:
            evidence.append("Neighborhood statistics")
            count += 1

        # Check for data sources
        source_matches = self.search_content(
            r"zillow.*api|realtor.*api|redfin.*api|census.*data", max_results=5
        )
        if source_matches:
            evidence.append(f"Data source integrations ({len(source_matches)} sources)")
            count += len(source_matches)

        thresholds = {"excellent": 8, "good": 5, "adequate": 2}
        score, quality = self.calculate_quality_score(count, thresholds)

        return {
            "detected": count > 0,
            "score": score,
            "evidence": evidence,
            "count": count,
            "quality": quality,
        }

    def _analyze_search(self) -> Dict[str, Any]:
        """
        Analyze property search/filtering capabilities

        Looks for:
        - Search algorithms
        - Advanced filters
        - Geospatial search
        - Saved searches
        - Search result ranking
        """
        evidence = []
        count = 0

        # Check for search files
        search_files = self.find_files("**/*search*.{py,js,ts}")
        if search_files:
            evidence.append(f"{len(search_files)} search files")
            count += min(len(search_files), 3)

        # Check for filter capabilities
        filter_matches = self.search_content(
            r"filter.*property|search.*filter|filter.*criteria",
            file_extensions=[".py", ".js", ".ts"],
            max_results=5,
        )
        if filter_matches:
            evidence.append(f"Advanced filters ({len(filter_matches)} implementations)")
            count += len(filter_matches)

        # Check for geospatial
        geo_matches = self.search_content(
            r"geospatial|geocode|map.*search|radius.*search|lat.*lng", max_results=5
        )
        if geo_matches:
            evidence.append(f"Geospatial search ({len(geo_matches)} features)")
            count += len(geo_matches)

        # Check for saved searches
        saved_matches = self.search_content(
            r"saved.*search|search.*alert|favorite.*search", max_results=3
        )
        if saved_matches:
            evidence.append("Saved search functionality")
            count += 1

        thresholds = {"excellent": 8, "good": 5, "adequate": 2}
        score, quality = self.calculate_quality_score(count, thresholds)

        return {
            "detected": count > 0,
            "score": score,
            "evidence": evidence,
            "count": count,
            "quality": quality,
        }

    def _analyze_investment(self) -> Dict[str, Any]:
        """
        Analyze investment analysis capabilities

        Looks for:
        - ROI calculations
        - Cash flow analysis
        - Cap rate calculations
        - Investment property scoring
        - Rental analysis
        """
        evidence = []
        count = 0

        # Check for investment files
        investment_files = self.find_files("**/*investment*.{py,js,ts}")
        investment_files.extend(self.find_files("**/*roi*.{py,js,ts}"))
        if investment_files:
            evidence.append(f"{len(investment_files)} investment analysis files")
            count += min(len(investment_files), 3)

        # Check for ROI calculations
        roi_matches = self.search_content(
            r"roi|return.*on.*investment|irr|internal.*rate.*of.*return",
            file_extensions=[".py", ".js", ".ts"],
            max_results=5,
        )
        if roi_matches:
            evidence.append(f"ROI calculations ({len(roi_matches)} implementations)")
            count += len(roi_matches)

        # Check for cash flow
        cashflow_matches = self.search_content(
            r"cash.*flow|cashflow|net.*operating.*income|noi", max_results=5
        )
        if cashflow_matches:
            evidence.append(f"Cash flow analysis ({len(cashflow_matches)} implementations)")
            count += len(cashflow_matches)

        # Check for cap rate
        cap_matches = self.search_content(r"cap.*rate|capitalization.*rate", max_results=3)
        if cap_matches:
            evidence.append("Cap rate calculations")
            count += 1

        # Check for rental analysis
        rental_matches = self.search_content(
            r"rental.*analysis|rent.*estimate|rental.*income", max_results=3
        )
        if rental_matches:
            evidence.append("Rental analysis")
            count += 1

        thresholds = {"excellent": 10, "good": 6, "adequate": 3}
        score, quality = self.calculate_quality_score(count, thresholds)

        return {
            "detected": count > 0,
            "score": score,
            "evidence": evidence,
            "count": count,
            "quality": quality,
        }

    def _analyze_documents(self) -> Dict[str, Any]:
        """
        Analyze document generation capabilities

        Looks for:
        - Contract templates
        - Agreement generation
        - Disclosure forms
        - PDF generation
        - Document signing integration
        """
        evidence = []
        count = 0

        # Check for document files
        doc_files = self.find_files("**/*contract*.{py,js,ts}")
        doc_files.extend(self.find_files("**/*agreement*.{py,js,ts}"))
        if doc_files:
            evidence.append(f"{len(doc_files)} document files")
            count += min(len(doc_files), 3)

        # Check for templates
        template_files = self.find_files("**/*template*.{html,pdf,docx}")
        if template_files:
            evidence.append(f"{len(template_files)} document templates")
            count += len(template_files)

        # Check for PDF generation
        pdf_matches = self.search_content(
            r"pdf.*generate|puppeteer|playwright|pdfkit", max_results=3
        )
        if pdf_matches:
            evidence.append("PDF generation")
            count += 1

        # Check for e-signature
        esign_matches = self.search_content(
            r"docusign|hellosign|adobe.*sign|e-signature", max_results=3
        )
        if esign_matches:
            evidence.append("E-signature integration")
            count += 2

        thresholds = {"excellent": 6, "good": 4, "adequate": 2}
        score, quality = self.calculate_quality_score(count, thresholds)

        return {
            "detected": count > 0,
            "score": score,
            "evidence": evidence,
            "count": count,
            "quality": quality,
        }

    def _analyze_crm(self) -> Dict[str, Any]:
        """
        Analyze client management capabilities

        Looks for:
        - Contact management
        - Lead tracking
        - Client communication
        - Transaction management
        - CRM integration
        """
        evidence = []
        count = 0

        # Check for CRM files
        crm_files = self.find_files("**/*client*.{py,js,ts}")
        crm_files.extend(self.find_files("**/*contact*.{py,js,ts}"))
        if crm_files:
            evidence.append(f"{len(crm_files)} CRM files")
            count += min(len(crm_files), 3)

        # Check for lead tracking
        lead_matches = self.search_content(
            r"lead.*track|lead.*management|lead.*pipeline", max_results=3
        )
        if lead_matches:
            evidence.append("Lead tracking")
            count += 1

        # Check for communication
        comm_matches = self.search_content(
            r"email.*client|sms.*client|client.*communication", max_results=3
        )
        if comm_matches:
            evidence.append("Client communication")
            count += 1

        # Check for CRM integrations
        integration_matches = self.search_content(
            r"salesforce|hubspot|zoho.*crm|crm.*api", max_results=3
        )
        if integration_matches:
            evidence.append("CRM platform integration")
            count += 2

        thresholds = {"excellent": 5, "good": 3, "adequate": 1}
        score, quality = self.calculate_quality_score(count, thresholds)

        return {
            "detected": count > 0,
            "score": score,
            "evidence": evidence,
            "count": count,
            "quality": quality,
        }

    def _analyze_reporting(self) -> Dict[str, Any]:
        """
        Analyze market reporting capabilities

        Looks for:
        - Market report generation
        - Custom reports
        - Data visualization
        - Export capabilities
        - Scheduled reports
        """
        evidence = []
        count = 0

        # Check for report files
        report_files = self.find_files("**/*report*.{py,js,ts}")
        if report_files:
            evidence.append(f"{len(report_files)} report files")
            count += min(len(report_files), 3)

        # Check for market reports
        market_report_matches = self.search_content(
            r"market.*report|generate.*report|report.*generation", max_results=3
        )
        if market_report_matches:
            evidence.append("Market report generation")
            count += 1

        # Check for visualization
        viz_matches = self.search_content(
            r"chart|graph|visualization|plot|highcharts|d3", max_results=3
        )
        if viz_matches:
            evidence.append("Data visualization")
            count += 1

        # Check for export
        export_matches = self.search_content(
            r"export.*pdf|export.*excel|export.*csv|report.*export", max_results=3
        )
        if export_matches:
            evidence.append("Export capabilities")
            count += 1

        thresholds = {"excellent": 5, "good": 3, "adequate": 1}
        score, quality = self.calculate_quality_score(count, thresholds)

        return {
            "detected": count > 0,
            "score": score,
            "evidence": evidence,
            "count": count,
            "quality": quality,
        }

    def get_unique_features(self) -> List[str]:
        """Identify unique real estate features this repo has"""
        unique = []

        # Check for 3D tours
        if len(self.search_content(r"3d.*tour|matterport|virtual.*tour", max_results=1)) > 0:
            unique.append("3D virtual tour integration")

        # Check for AI valuation
        if (
            len(
                self.search_content(
                    r"machine.*learning.*valuation|ai.*valuation|ml.*price", max_results=1
                )
            )
            > 0
        ):
            unique.append("AI-powered property valuation")

        # Check for blockchain
        if len(self.search_content(r"blockchain|smart.*contract|nft.*property", max_results=1)) > 0:
            unique.append("Blockchain/smart contract support")

        # Check for drone imagery
        if len(self.search_content(r"drone|aerial.*photo|aerial.*imagery", max_results=1)) > 0:
            unique.append("Drone/aerial imagery integration")

        return unique
