#!/usr/bin/env python3
"""
Career Skill Analyzer

Analyzes career skill repositories for 10 key capabilities:
- Resume templates
- Job search strategies
- Interview preparation
- Cover letter generation
- Salary negotiation
- Portfolio building
- ATS optimization
- Career progression planning
- Networking strategies
- Skill assessment
"""

from pathlib import Path
from typing import Dict, List, Any
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.base_analyzer import BaseAnalyzer


class CareerSkillAnalyzer(BaseAnalyzer):
    """
    Analyzes career skill repositories

    Evaluates 10 career capabilities with weighted scoring:
    - Resume templates (15%)
    - Job search strategies (12%)
    - Interview preparation (15%)
    - Cover letter generation (10%)
    - Salary negotiation (10%)
    - Portfolio building (10%)
    - ATS optimization (10%)
    - Career progression (8%)
    - Networking strategies (5%)
    - Skill assessment (5%)
    """

    WEIGHTS = {
        "resume_templates": 0.15,
        "job_search": 0.12,
        "interview_prep": 0.15,
        "cover_letters": 0.10,
        "salary_negotiation": 0.10,
        "portfolio": 0.10,
        "ats_optimization": 0.10,
        "career_progression": 0.08,
        "networking": 0.05,
        "skill_assessment": 0.05,
    }

    def get_domain_name(self) -> str:
        return "career"

    def get_capabilities(self) -> List[str]:
        return [
            "resume_templates",
            "job_search",
            "interview_prep",
            "cover_letters",
            "salary_negotiation",
            "portfolio",
            "ats_optimization",
            "career_progression",
            "networking",
            "skill_assessment",
        ]

    def analyze_capability(self, capability: str) -> Dict[str, Any]:
        """Route capability analysis to specific method"""
        method_map = {
            "resume_templates": self._analyze_resume_templates,
            "job_search": self._analyze_job_search,
            "interview_prep": self._analyze_interview_prep,
            "cover_letters": self._analyze_cover_letters,
            "salary_negotiation": self._analyze_salary_negotiation,
            "portfolio": self._analyze_portfolio,
            "ats_optimization": self._analyze_ats_optimization,
            "career_progression": self._analyze_career_progression,
            "networking": self._analyze_networking,
            "skill_assessment": self._analyze_skill_assessment,
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

    def _analyze_resume_templates(self) -> Dict[str, Any]:
        """
        Analyze resume template capabilities

        Looks for:
        - Resume template files (JSON, YAML, MD)
        - Multi-format support (PDF, DOCX, HTML)
        - Template variations (technical, creative, executive)
        - Customization engines
        - Template documentation
        """
        evidence = []
        count = 0

        # Check for resume directories
        resume_dirs = ["resume", "resumes", "cv", "templates"]
        for rdir in resume_dirs:
            if self.has_directory(rdir):
                evidence.append(f"{rdir}/ directory")
                count += 2
                break

        # Check for template files
        template_files = self.find_files("**/*resume*.{json,yaml,yml,md}")
        template_files.extend(self.find_files("**/*cv*.{json,yaml,yml,md}"))
        if template_files:
            evidence.append(f"{len(template_files)} template files")
            count += min(len(template_files), 5)

        # Check for PDF generation
        pdf_matches = self.search_content(
            r"pdf.*generate|puppeteer|playwright|latex|pandoc",
            file_extensions=[".py", ".js", ".ts"],
            max_results=3,
        )
        if pdf_matches:
            evidence.append("PDF generation capability")
            count += 2

        # Check for template variations
        variation_matches = self.search_content(
            r"technical.*resume|creative.*resume|executive.*resume|template.*type", max_results=5
        )
        if variation_matches:
            evidence.append(f"Template variations ({len(variation_matches)} types)")
            count += len(variation_matches)

        thresholds = {"excellent": 10, "good": 6, "adequate": 3}
        score, quality = self.calculate_quality_score(count, thresholds)

        return {
            "detected": count > 0,
            "score": score,
            "evidence": evidence,
            "count": count,
            "quality": quality,
        }

    def _analyze_job_search(self) -> Dict[str, Any]:
        """
        Analyze job search strategy capabilities

        Looks for:
        - Job board integrations (LinkedIn, Indeed, etc.)
        - Search automation
        - Job matching algorithms
        - Application tracking
        - Company research tools
        """
        evidence = []
        count = 0

        # Check for job search files
        job_files = self.find_files("**/*job*.{py,js,ts}")
        if job_files:
            evidence.append(f"{len(job_files)} job search files")
            count += min(len(job_files), 3)

        # Check for API integrations
        api_matches = self.search_content(
            r"linkedin.*api|indeed.*api|glassdoor.*api|job.*board.*api", max_results=5
        )
        if api_matches:
            evidence.append(f"Job board integrations ({len(api_matches)} platforms)")
            count += len(api_matches) * 2

        # Check for search automation
        automation_matches = self.search_content(
            r"auto.*apply|job.*scraper|search.*automation",
            file_extensions=[".py", ".js", ".ts"],
            max_results=3,
        )
        if automation_matches:
            evidence.append("Search automation")
            count += 2

        # Check for matching algorithms
        matching_matches = self.search_content(
            r"match.*score|job.*match|skill.*match|recommendation", max_results=3
        )
        if matching_matches:
            evidence.append("Job matching algorithms")
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

    def _analyze_interview_prep(self) -> Dict[str, Any]:
        """
        Analyze interview preparation capabilities

        Looks for:
        - Question banks
        - Mock interview tools
        - STAR method frameworks
        - Behavioral question prep
        - Technical interview prep
        """
        evidence = []
        count = 0

        # Check for interview directories
        if self.has_directory("interview") or self.has_directory("interviews"):
            evidence.append("interview/ directory")
            count += 2

        # Check for question banks
        question_files = self.find_files("**/*question*.{json,yaml,yml,md,csv}")
        if question_files:
            evidence.append(f"{len(question_files)} question bank files")
            count += min(len(question_files), 5)

        # Check for STAR method
        star_matches = self.search_content(
            r"STAR.*method|situation.*task.*action.*result", max_results=3
        )
        if star_matches:
            evidence.append("STAR method framework")
            count += 2

        # Check for technical interview prep
        tech_matches = self.search_content(
            r"coding.*interview|algorithm.*practice|leetcode|hackerrank", max_results=5
        )
        if tech_matches:
            evidence.append(f"Technical interview prep ({len(tech_matches)} resources)")
            count += len(tech_matches)

        # Check for mock interview tools
        mock_matches = self.search_content(
            r"mock.*interview|practice.*interview|interview.*simulation", max_results=3
        )
        if mock_matches:
            evidence.append("Mock interview tools")
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

    def _analyze_cover_letters(self) -> Dict[str, Any]:
        """
        Analyze cover letter generation capabilities

        Looks for:
        - Cover letter templates
        - AI generation tools
        - Company-specific customization
        - Tone/style variations
        - Quality scoring
        """
        evidence = []
        count = 0

        # Check for cover letter files
        cover_files = self.find_files("**/*cover*.{md,json,yaml,txt}")
        if cover_files:
            evidence.append(f"{len(cover_files)} cover letter files")
            count += min(len(cover_files), 3)

        # Check for generation tools
        gen_matches = self.search_content(
            r"generate.*cover|cover.*letter.*generation|ai.*cover",
            file_extensions=[".py", ".js", ".ts"],
            max_results=3,
        )
        if gen_matches:
            evidence.append("Cover letter generation tools")
            count += 2

        # Check for customization
        custom_matches = self.search_content(r"customize|personalize|tailor.*cover", max_results=3)
        if custom_matches:
            evidence.append("Customization capabilities")
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

    def _analyze_salary_negotiation(self) -> Dict[str, Any]:
        """
        Analyze salary negotiation capabilities

        Looks for:
        - Salary data/benchmarks
        - Negotiation scripts/templates
        - Offer evaluation tools
        - Compensation calculators
        - Market research integration
        """
        evidence = []
        count = 0

        # Check for salary-related files
        salary_files = self.find_files("**/*salary*.{json,csv,md}")
        salary_files.extend(self.find_files("**/*compensation*.{json,csv,md}"))
        if salary_files:
            evidence.append(f"{len(salary_files)} salary data files")
            count += min(len(salary_files), 3)

        # Check for negotiation content
        negotiation_matches = self.search_content(
            r"negotiat.*salary|negotiate.*offer|compensation.*negotiation", max_results=5
        )
        if negotiation_matches:
            evidence.append(f"Negotiation guidance ({len(negotiation_matches)} resources)")
            count += len(negotiation_matches)

        # Check for calculators
        calc_matches = self.search_content(
            r"salary.*calculator|compensation.*calculator|total.*comp", max_results=3
        )
        if calc_matches:
            evidence.append("Compensation calculators")
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

    def _analyze_portfolio(self) -> Dict[str, Any]:
        """
        Analyze portfolio building capabilities

        Looks for:
        - Portfolio templates
        - Project showcase formats
        - GitHub integration
        - Case study frameworks
        - Portfolio hosting/deployment
        """
        evidence = []
        count = 0

        # Check for portfolio directories
        if self.has_directory("portfolio") or self.has_directory("portfolios"):
            evidence.append("portfolio/ directory")
            count += 2

        # Check for showcase formats
        showcase_files = self.find_files("**/*portfolio*.{html,md,json}")
        if showcase_files:
            evidence.append(f"{len(showcase_files)} portfolio files")
            count += min(len(showcase_files), 3)

        # Check for case study frameworks
        case_matches = self.search_content(
            r"case.*study|project.*showcase|portfolio.*item", max_results=3
        )
        if case_matches:
            evidence.append("Case study frameworks")
            count += 1

        # Check for GitHub integration
        github_matches = self.search_content(
            r"github.*api|github.*portfolio|github.*projects", max_results=3
        )
        if github_matches:
            evidence.append("GitHub integration")
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

    def _analyze_ats_optimization(self) -> Dict[str, Any]:
        """
        Analyze ATS optimization capabilities

        Looks for:
        - ATS keyword analysis
        - Resume parsing/scoring
        - Format compliance checking
        - Keyword extraction
        - ATS testing tools
        """
        evidence = []
        count = 0

        # Check for ATS-related files
        ats_files = self.find_files("**/*ats*.{py,js,ts}")
        if ats_files:
            evidence.append(f"{len(ats_files)} ATS optimization files")
            count += min(len(ats_files), 3)

        # Check for keyword analysis
        keyword_matches = self.search_content(
            r"keyword.*extract|keyword.*match|ats.*keyword",
            file_extensions=[".py", ".js", ".ts"],
            max_results=5,
        )
        if keyword_matches:
            evidence.append(f"Keyword analysis ({len(keyword_matches)} implementations)")
            count += len(keyword_matches)

        # Check for parsing/scoring
        parse_matches = self.search_content(
            r"resume.*parse|ats.*score|parse.*resume|applicant.*tracking", max_results=3
        )
        if parse_matches:
            evidence.append("Resume parsing/scoring")
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

    def _analyze_career_progression(self) -> Dict[str, Any]:
        """
        Analyze career progression planning capabilities

        Looks for:
        - Career path frameworks
        - Skill gap analysis
        - Goal setting tools
        - Promotion strategies
        - Career timeline planning
        """
        evidence = []
        count = 0

        # Check for career progression content
        progression_matches = self.search_content(
            r"career.*path|career.*progression|career.*ladder|career.*growth", max_results=5
        )
        if progression_matches:
            evidence.append(f"Career progression content ({len(progression_matches)} resources)")
            count += len(progression_matches)

        # Check for skill gap analysis
        gap_matches = self.search_content(
            r"skill.*gap|gap.*analysis|skill.*assessment", max_results=3
        )
        if gap_matches:
            evidence.append("Skill gap analysis")
            count += 1

        # Check for goal setting
        goal_matches = self.search_content(r"goal.*setting|career.*goal|smart.*goal", max_results=3)
        if goal_matches:
            evidence.append("Goal setting frameworks")
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

    def _analyze_networking(self) -> Dict[str, Any]:
        """
        Analyze networking strategy capabilities

        Looks for:
        - LinkedIn optimization
        - Networking templates
        - Cold outreach strategies
        - Informational interview guides
        - Network building frameworks
        """
        evidence = []
        count = 0

        # Check for networking content
        network_matches = self.search_content(
            r"networking|linkedin.*strategy|professional.*network", max_results=5
        )
        if network_matches:
            evidence.append(f"Networking content ({len(network_matches)} resources)")
            count += len(network_matches)

        # Check for outreach templates
        outreach_matches = self.search_content(
            r"cold.*outreach|reach.*out|informational.*interview", max_results=3
        )
        if outreach_matches:
            evidence.append("Outreach strategies")
            count += 1

        thresholds = {"excellent": 4, "good": 2, "adequate": 1}
        score, quality = self.calculate_quality_score(count, thresholds)

        return {
            "detected": count > 0,
            "score": score,
            "evidence": evidence,
            "count": count,
            "quality": quality,
        }

    def _analyze_skill_assessment(self) -> Dict[str, Any]:
        """
        Analyze skill assessment capabilities

        Looks for:
        - Skill evaluation frameworks
        - Technical assessments
        - Skill tracking systems
        - Certification guidance
        - Learning path recommendations
        """
        evidence = []
        count = 0

        # Check for skill assessment content
        skill_matches = self.search_content(
            r"skill.*assessment|skill.*evaluation|skill.*test", max_results=5
        )
        if skill_matches:
            evidence.append(f"Skill assessment content ({len(skill_matches)} resources)")
            count += len(skill_matches)

        # Check for certification guidance
        cert_matches = self.search_content(r"certification|certificate|credential", max_results=3)
        if cert_matches:
            evidence.append("Certification guidance")
            count += 1

        thresholds = {"excellent": 4, "good": 2, "adequate": 1}
        score, quality = self.calculate_quality_score(count, thresholds)

        return {
            "detected": count > 0,
            "score": score,
            "evidence": evidence,
            "count": count,
            "quality": quality,
        }

    def get_unique_features(self) -> List[str]:
        """Identify unique career features this repo has"""
        unique = []

        # Check for AI-powered generation
        if len(self.search_content(r"gpt|openai|llm|ai.*generate", max_results=1)) > 0:
            unique.append("AI-powered content generation")

        # Check for comprehensive ATS optimization
        if self.count_files("**/*ats*.{py,js,ts}") > 2:
            unique.append("Advanced ATS optimization suite")

        # Check for salary data integration
        if self.count_files("**/*salary*.{json,csv}") > 0:
            unique.append("Integrated salary data/benchmarks")

        # Check for mock interview automation
        if len(self.search_content(r"mock.*interview.*auto|interview.*bot", max_results=1)) > 0:
            unique.append("Automated mock interview system")

        return unique
