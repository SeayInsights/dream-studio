#!/usr/bin/env python3
"""
Finance Skill Analyzer

Analyzes finance skill repositories for 10 key capabilities:
- Accounting systems
- Invoice management
- Ledger systems
- Tax preparation
- Budget planning
- Financial reporting
- Expense tracking
- Reconciliation
- Integration (QuickBooks, Xero)
- Compliance/audit support
"""

from pathlib import Path
from typing import Dict, List, Any
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.base_analyzer import BaseAnalyzer


class FinanceSkillAnalyzer(BaseAnalyzer):
    """
    Analyzes finance skill repositories

    Evaluates 10 finance capabilities with weighted scoring:
    - Accounting systems (15%)
    - Invoice management (12%)
    - Ledger systems (15%)
    - Tax preparation (10%)
    - Budget planning (10%)
    - Financial reporting (12%)
    - Expense tracking (8%)
    - Reconciliation (8%)
    - Platform integration (5%)
    - Compliance/audit (5%)
    """

    WEIGHTS = {
        "accounting": 0.15,
        "invoicing": 0.12,
        "ledger": 0.15,
        "tax": 0.10,
        "budgeting": 0.10,
        "reporting": 0.12,
        "expenses": 0.08,
        "reconciliation": 0.08,
        "integration": 0.05,
        "compliance": 0.05,
    }

    def get_domain_name(self) -> str:
        return "finance"

    def get_capabilities(self) -> List[str]:
        return [
            "accounting",
            "invoicing",
            "ledger",
            "tax",
            "budgeting",
            "reporting",
            "expenses",
            "reconciliation",
            "integration",
            "compliance",
        ]

    def analyze_capability(self, capability: str) -> Dict[str, Any]:
        """Route capability analysis to specific method"""
        method_map = {
            "accounting": self._analyze_accounting,
            "invoicing": self._analyze_invoicing,
            "ledger": self._analyze_ledger,
            "tax": self._analyze_tax,
            "budgeting": self._analyze_budgeting,
            "reporting": self._analyze_reporting,
            "expenses": self._analyze_expenses,
            "reconciliation": self._analyze_reconciliation,
            "integration": self._analyze_integration,
            "compliance": self._analyze_compliance,
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

        overall = sum(scores[cap] * self.WEIGHTS[cap] for cap in scores)
        scores["overall_score"] = round(overall, 1)

        return scores

    def _analyze_accounting(self) -> Dict[str, Any]:
        """
        Analyze accounting system capabilities

        Looks for:
        - Chart of accounts
        - Double-entry bookkeeping
        - Journal entries
        - Trial balance
        - Account types (asset, liability, equity, revenue, expense)
        """
        evidence = []
        count = 0

        # Check for accounting directories
        accounting_dirs = ["accounting", "accounts", "bookkeeping", "general-ledger"]
        for adir in accounting_dirs:
            if self.has_directory(adir):
                evidence.append(f"{adir}/ directory")
                count += 2
                break

        # Check for chart of accounts
        coa_matches = self.search_content(
            r"chart.*of.*accounts|coa|account.*type|asset.*liability", max_results=5
        )
        if coa_matches:
            evidence.append(f"Chart of accounts ({len(coa_matches)} references)")
            count += len(coa_matches)

        # Check for double-entry
        double_entry_matches = self.search_content(
            r"double.*entry|debit.*credit|journal.*entry",
            file_extensions=[".py", ".js", ".ts"],
            max_results=5,
        )
        if double_entry_matches:
            evidence.append(
                f"Double-entry bookkeeping ({len(double_entry_matches)} implementations)"
            )
            count += len(double_entry_matches)

        # Check for trial balance
        trial_matches = self.search_content(r"trial.*balance|balance.*sheet", max_results=3)
        if trial_matches:
            evidence.append("Trial balance support")
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

    def _analyze_invoicing(self) -> Dict[str, Any]:
        """
        Analyze invoice management capabilities

        Looks for:
        - Invoice generation
        - Invoice templates
        - Payment tracking
        - Invoice numbering
        - Multi-currency support
        """
        evidence = []
        count = 0

        # Check for invoice directories/files
        invoice_files = self.find_files("**/*invoice*.{py,js,ts,json,md}")
        if invoice_files:
            evidence.append(f"{len(invoice_files)} invoice-related files")
            count += min(len(invoice_files), 5)

        # Check for invoice generation
        gen_matches = self.search_content(
            r"generate.*invoice|create.*invoice|invoice.*generation",
            file_extensions=[".py", ".js", ".ts"],
            max_results=5,
        )
        if gen_matches:
            evidence.append(f"Invoice generation ({len(gen_matches)} implementations)")
            count += len(gen_matches)

        # Check for payment tracking
        payment_matches = self.search_content(
            r"payment.*status|invoice.*paid|payment.*tracking", max_results=3
        )
        if payment_matches:
            evidence.append("Payment tracking")
            count += 1

        # Check for templates
        template_files = self.find_files("**/*invoice*template*.{html,pdf,json}")
        if template_files:
            evidence.append(f"{len(template_files)} invoice templates")
            count += len(template_files)

        thresholds = {"excellent": 10, "good": 6, "adequate": 3}
        score, quality = self.calculate_quality_score(count, thresholds)

        return {
            "detected": count > 0,
            "score": score,
            "evidence": evidence,
            "count": count,
            "quality": quality,
        }

    def _analyze_ledger(self) -> Dict[str, Any]:
        """
        Analyze ledger system capabilities

        Looks for:
        - General ledger
        - Subsidiary ledgers
        - Transaction logging
        - Ledger queries
        - Historical tracking
        """
        evidence = []
        count = 0

        # Check for ledger files
        ledger_files = self.find_files("**/*ledger*.{py,js,ts}")
        if ledger_files:
            evidence.append(f"{len(ledger_files)} ledger files")
            count += min(len(ledger_files), 5)

        # Check for transaction logging
        transaction_matches = self.search_content(
            r"transaction.*log|ledger.*entry|post.*transaction",
            file_extensions=[".py", ".js", ".ts"],
            max_results=5,
        )
        if transaction_matches:
            evidence.append(f"Transaction logging ({len(transaction_matches)} implementations)")
            count += len(transaction_matches)

        # Check for queries
        query_matches = self.search_content(
            r"ledger.*query|query.*transaction|search.*ledger", max_results=3
        )
        if query_matches:
            evidence.append("Ledger query capabilities")
            count += 1

        # Check for audit trail
        audit_matches = self.search_content(r"audit.*trail|transaction.*history", max_results=3)
        if audit_matches:
            evidence.append("Audit trail support")
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

    def _analyze_tax(self) -> Dict[str, Any]:
        """
        Analyze tax preparation capabilities

        Looks for:
        - Tax calculation
        - Tax forms (1099, W-2, etc.)
        - Tax reporting
        - Deduction tracking
        - Multi-jurisdiction support
        """
        evidence = []
        count = 0

        # Check for tax-related files
        tax_files = self.find_files("**/*tax*.{py,js,ts}")
        if tax_files:
            evidence.append(f"{len(tax_files)} tax files")
            count += min(len(tax_files), 3)

        # Check for tax calculation
        calc_matches = self.search_content(
            r"tax.*calculation|calculate.*tax|tax.*rate",
            file_extensions=[".py", ".js", ".ts"],
            max_results=5,
        )
        if calc_matches:
            evidence.append(f"Tax calculation ({len(calc_matches)} implementations)")
            count += len(calc_matches)

        # Check for tax forms
        form_matches = self.search_content(r"1099|W-2|tax.*form|schedule.*C", max_results=5)
        if form_matches:
            evidence.append(f"Tax form support ({len(form_matches)} forms)")
            count += len(form_matches)

        # Check for deduction tracking
        deduction_matches = self.search_content(
            r"deduction|tax.*deductible|write.*off", max_results=3
        )
        if deduction_matches:
            evidence.append("Deduction tracking")
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

    def _analyze_budgeting(self) -> Dict[str, Any]:
        """
        Analyze budget planning capabilities

        Looks for:
        - Budget creation
        - Budget tracking
        - Variance analysis
        - Forecasting
        - Budget categories
        """
        evidence = []
        count = 0

        # Check for budget files
        budget_files = self.find_files("**/*budget*.{py,js,ts,json,csv}")
        if budget_files:
            evidence.append(f"{len(budget_files)} budget files")
            count += min(len(budget_files), 3)

        # Check for budget tracking
        tracking_matches = self.search_content(
            r"budget.*track|track.*spending|budget.*vs.*actual", max_results=5
        )
        if tracking_matches:
            evidence.append(f"Budget tracking ({len(tracking_matches)} implementations)")
            count += len(tracking_matches)

        # Check for variance analysis
        variance_matches = self.search_content(
            r"variance|budget.*variance|over.*budget|under.*budget", max_results=3
        )
        if variance_matches:
            evidence.append("Variance analysis")
            count += 1

        # Check for forecasting
        forecast_matches = self.search_content(
            r"forecast|budget.*forecast|financial.*projection", max_results=3
        )
        if forecast_matches:
            evidence.append("Forecasting capabilities")
            count += 1

        thresholds = {"excellent": 6, "good": 4, "adequate": 2}
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
        Analyze financial reporting capabilities

        Looks for:
        - Income statement
        - Balance sheet
        - Cash flow statement
        - Financial ratios
        - Report generation
        """
        evidence = []
        count = 0

        # Check for report files
        report_files = self.find_files("**/*report*.{py,js,ts}")
        financial_reports = [
            f
            for f in report_files
            if "financial" in str(f).lower()
            or "income" in str(f).lower()
            or "balance" in str(f).lower()
        ]
        if financial_reports:
            evidence.append(f"{len(financial_reports)} financial report files")
            count += min(len(financial_reports), 5)

        # Check for standard financial statements
        statement_matches = self.search_content(
            r"income.*statement|balance.*sheet|cash.*flow.*statement|P&L|profit.*loss",
            max_results=5,
        )
        if statement_matches:
            evidence.append(f"Standard financial statements ({len(statement_matches)} types)")
            count += len(statement_matches)

        # Check for financial ratios
        ratio_matches = self.search_content(
            r"financial.*ratio|liquidity.*ratio|profitability.*ratio", max_results=3
        )
        if ratio_matches:
            evidence.append("Financial ratio analysis")
            count += 1

        # Check for report generation
        gen_matches = self.search_content(
            r"generate.*report|report.*generation|export.*report",
            file_extensions=[".py", ".js", ".ts"],
            max_results=3,
        )
        if gen_matches:
            evidence.append("Report generation tools")
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

    def _analyze_expenses(self) -> Dict[str, Any]:
        """
        Analyze expense tracking capabilities

        Looks for:
        - Expense entry
        - Receipt management
        - Category classification
        - Expense approval workflows
        - Reimbursement tracking
        """
        evidence = []
        count = 0

        # Check for expense files
        expense_files = self.find_files("**/*expense*.{py,js,ts}")
        if expense_files:
            evidence.append(f"{len(expense_files)} expense files")
            count += min(len(expense_files), 3)

        # Check for receipt management
        receipt_matches = self.search_content(
            r"receipt|expense.*image|scan.*receipt", max_results=5
        )
        if receipt_matches:
            evidence.append(f"Receipt management ({len(receipt_matches)} references)")
            count += len(receipt_matches)

        # Check for categorization
        category_matches = self.search_content(
            r"expense.*category|categorize.*expense|expense.*type", max_results=3
        )
        if category_matches:
            evidence.append("Expense categorization")
            count += 1

        # Check for approval workflows
        approval_matches = self.search_content(
            r"expense.*approval|approve.*expense|expense.*workflow", max_results=3
        )
        if approval_matches:
            evidence.append("Approval workflows")
            count += 1

        thresholds = {"excellent": 6, "good": 4, "adequate": 2}
        score, quality = self.calculate_quality_score(count, thresholds)

        return {
            "detected": count > 0,
            "score": score,
            "evidence": evidence,
            "count": count,
            "quality": quality,
        }

    def _analyze_reconciliation(self) -> Dict[str, Any]:
        """
        Analyze reconciliation capabilities

        Looks for:
        - Bank reconciliation
        - Account matching
        - Discrepancy detection
        - Automated reconciliation
        - Reconciliation reports
        """
        evidence = []
        count = 0

        # Check for reconciliation files
        recon_files = self.find_files("**/*reconcil*.{py,js,ts}")
        if recon_files:
            evidence.append(f"{len(recon_files)} reconciliation files")
            count += min(len(recon_files), 3)

        # Check for bank reconciliation
        bank_matches = self.search_content(
            r"bank.*reconcil|reconcile.*bank|bank.*statement.*match",
            file_extensions=[".py", ".js", ".ts"],
            max_results=5,
        )
        if bank_matches:
            evidence.append(f"Bank reconciliation ({len(bank_matches)} implementations)")
            count += len(bank_matches)

        # Check for matching algorithms
        match_matches = self.search_content(
            r"transaction.*match|fuzzy.*match|reconciliation.*algorithm", max_results=3
        )
        if match_matches:
            evidence.append("Matching algorithms")
            count += 1

        # Check for automation
        auto_matches = self.search_content(r"auto.*reconcil|automated.*reconcil", max_results=3)
        if auto_matches:
            evidence.append("Automated reconciliation")
            count += 1

        thresholds = {"excellent": 6, "good": 4, "adequate": 2}
        score, quality = self.calculate_quality_score(count, thresholds)

        return {
            "detected": count > 0,
            "score": score,
            "evidence": evidence,
            "count": count,
            "quality": quality,
        }

    def _analyze_integration(self) -> Dict[str, Any]:
        """
        Analyze platform integration capabilities

        Looks for:
        - QuickBooks integration
        - Xero integration
        - Banking API integration
        - Payment gateway integration
        - Import/export capabilities
        """
        evidence = []
        count = 0

        # Check for QuickBooks
        qb_matches = self.search_content(r"quickbooks|qbo|intuit.*api", max_results=5)
        if qb_matches:
            evidence.append(f"QuickBooks integration ({len(qb_matches)} references)")
            count += len(qb_matches)

        # Check for Xero
        xero_matches = self.search_content(r"xero|xero.*api", max_results=3)
        if xero_matches:
            evidence.append(f"Xero integration")
            count += 2

        # Check for banking APIs
        bank_api_matches = self.search_content(
            r"plaid|yodlee|bank.*api|open.*banking", max_results=3
        )
        if bank_api_matches:
            evidence.append("Banking API integration")
            count += 2

        # Check for payment gateways
        payment_matches = self.search_content(
            r"stripe|paypal|square|payment.*gateway", max_results=3
        )
        if payment_matches:
            evidence.append("Payment gateway integration")
            count += 1

        thresholds = {"excellent": 6, "good": 4, "adequate": 2}
        score, quality = self.calculate_quality_score(count, thresholds)

        return {
            "detected": count > 0,
            "score": score,
            "evidence": evidence,
            "count": count,
            "quality": quality,
        }

    def _analyze_compliance(self) -> Dict[str, Any]:
        """
        Analyze compliance/audit support capabilities

        Looks for:
        - Audit trails
        - Compliance reporting
        - Financial controls
        - Data retention policies
        - Regulatory support (GAAP, IFRS)
        """
        evidence = []
        count = 0

        # Check for audit trail
        audit_matches = self.search_content(
            r"audit.*trail|audit.*log|transaction.*history", max_results=5
        )
        if audit_matches:
            evidence.append(f"Audit trail ({len(audit_matches)} implementations)")
            count += len(audit_matches)

        # Check for compliance reporting
        compliance_matches = self.search_content(
            r"compliance.*report|regulatory.*report|sox|sarbanes", max_results=3
        )
        if compliance_matches:
            evidence.append("Compliance reporting")
            count += 2

        # Check for GAAP/IFRS
        gaap_matches = self.search_content(r"gaap|ifrs|accounting.*standard", max_results=3)
        if gaap_matches:
            evidence.append("Accounting standards support")
            count += 1

        # Check for controls
        control_matches = self.search_content(
            r"financial.*control|internal.*control|segregation.*duties", max_results=3
        )
        if control_matches:
            evidence.append("Financial controls")
            count += 1

        thresholds = {"excellent": 6, "good": 4, "adequate": 2}
        score, quality = self.calculate_quality_score(count, thresholds)

        return {
            "detected": count > 0,
            "score": score,
            "evidence": evidence,
            "count": count,
            "quality": quality,
        }

    def get_unique_features(self) -> List[str]:
        """Identify unique finance features this repo has"""
        unique = []

        # Check for cryptocurrency support
        if len(self.search_content(r"crypto|bitcoin|ethereum|blockchain", max_results=1)) > 0:
            unique.append("Cryptocurrency accounting support")

        # Check for multi-currency
        if len(self.search_content(r"multi.*currency|forex|exchange.*rate", max_results=1)) > 0:
            unique.append("Multi-currency support")

        # Check for AI-powered features
        if (
            len(self.search_content(r"machine.*learning|ai.*categoriz|ml.*model", max_results=1))
            > 0
        ):
            unique.append("AI-powered transaction categorization")

        # Check for OCR
        if len(self.search_content(r"ocr|receipt.*scan|document.*recognition", max_results=1)) > 0:
            unique.append("OCR receipt scanning")

        return unique
