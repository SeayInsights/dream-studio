#!/usr/bin/env python3
"""
Design Skill Analyzer

Analyzes design skill repositories for 10 key capabilities:
- Color systems
- Typography
- Components
- Design systems
- Brand protocols
- Reasoning systems
- Anti-patterns
- Export formats
- Quality gates
- Register systems
"""

from pathlib import Path
from typing import Dict, List, Any
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.base_analyzer import BaseAnalyzer


class DesignSkillAnalyzer(BaseAnalyzer):
    """
    Analyzes design skill repositories

    Evaluates 10 design capabilities with weighted scoring:
    - Color systems (15%)
    - Typography (12%)
    - Components (15%)
    - Design systems (12%)
    - Brand protocols (10%)
    - Reasoning systems (12%)
    - Anti-patterns (8%)
    - Export formats (6%)
    - Quality gates (5%)
    - Register systems (5%)
    """

    # Scoring weights for overall calculation
    WEIGHTS = {
        "color_systems": 0.15,
        "typography": 0.12,
        "components": 0.15,
        "design_systems": 0.12,
        "brand_protocols": 0.10,
        "reasoning": 0.12,
        "anti_patterns": 0.08,
        "export_formats": 0.06,
        "quality_gates": 0.05,
        "register_system": 0.05,
    }

    def get_domain_name(self) -> str:
        return "design"

    def get_capabilities(self) -> List[str]:
        return [
            "color_systems",
            "typography",
            "components",
            "design_systems",
            "brand_protocols",
            "reasoning",
            "anti_patterns",
            "export_formats",
            "quality_gates",
            "register_system",
        ]

    def analyze_capability(self, capability: str) -> Dict[str, Any]:
        """Route capability analysis to specific method"""
        method_map = {
            "color_systems": self._analyze_color_systems,
            "typography": self._analyze_typography,
            "components": self._analyze_components,
            "design_systems": self._analyze_design_systems,
            "brand_protocols": self._analyze_brand_protocols,
            "reasoning": self._analyze_reasoning,
            "anti_patterns": self._analyze_anti_patterns,
            "export_formats": self._analyze_export_formats,
            "quality_gates": self._analyze_quality_gates,
            "register_system": self._analyze_register_system,
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

        # Calculate weighted overall score
        overall = sum(scores[cap] * self.WEIGHTS[cap] for cap in scores)
        scores["overall_score"] = round(overall, 1)

        return scores

    # Capability analysis methods

    def _analyze_color_systems(self) -> Dict[str, Any]:
        """
        Analyze color system capabilities

        Looks for:
        - colors.csv files (quantitative color definitions)
        - OKLCH color space usage
        - DESIGN.md color documentation
        - Contrast checking tools
        - Color palette generators
        """
        evidence = []
        count = 0

        # Check for CSV color files
        csv_files = self.find_files("**/colors*.csv")
        if csv_files:
            evidence.extend([str(f.relative_to(self.repo_path)) for f in csv_files[:3]])
            count += len(csv_files)

        # Check for OKLCH usage
        oklch_matches = self.search_content(r"oklch|OKLCH|color-space.*oklch", max_results=5)
        if oklch_matches:
            evidence.append(f"OKLCH usage found in {len(oklch_matches)} files")
            count += len(oklch_matches)

        # Check for DESIGN.md with color sections
        design_md = self.find_files("**/DESIGN.md")
        for dm in design_md:
            content = self.read_file(str(dm.relative_to(self.repo_path)))
            if content and "color" in content.lower():
                evidence.append(f"Color documentation in {dm.name}")
                count += 1

        # Check for contrast checking
        contrast_files = self.find_files("**/*contrast*.{py,js,ts}")
        if contrast_files:
            evidence.append(f"Contrast checking tools ({len(contrast_files)} files)")
            count += len(contrast_files)

        # Check for color-and-contrast.md
        if self.has_file("color-and-contrast.md"):
            evidence.append("color-and-contrast.md")
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

    def _analyze_typography(self) -> Dict[str, Any]:
        """
        Analyze typography capabilities

        Looks for:
        - typography.csv or typography.md
        - Font pairing definitions
        - Modular scale configurations
        - Type ramp documentation
        - Web font loading strategies
        """
        evidence = []
        count = 0

        # Check for typography files
        typo_files = self.find_files("**/*typography*.*")
        if typo_files:
            evidence.extend([str(f.relative_to(self.repo_path)) for f in typo_files[:3]])
            count += len(typo_files)

        # Check for font pairing content
        font_matches = self.search_content(
            r"font.*pair|font.*family|type.*scale|modular.*scale",
            file_extensions=[".md", ".csv", ".json"],
            max_results=5,
        )
        if font_matches:
            evidence.append(f"Font/scale definitions found in {len(font_matches)} locations")
            count += len(font_matches)

        # Check for type ramp
        ramp_matches = self.search_content(r"type.*ramp|font.*size.*scale", max_results=3)
        if ramp_matches:
            evidence.append(f"Type ramp definitions ({len(ramp_matches)} files)")
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

    def _analyze_components(self) -> Dict[str, Any]:
        """
        Analyze component library capabilities

        Looks for:
        - Device frames
        - UI kits
        - Component libraries
        - Figma/Sketch files
        - Design tokens
        """
        evidence = []
        count = 0

        # Check for device frames
        if self.has_directory("device-frames") or self.has_directory("devices"):
            evidence.append("Device frames directory")
            count += 1
            frame_count = self.count_files("**/device-frames/**/*")
            if frame_count > 0:
                evidence.append(f"{frame_count} device frame files")
                count += frame_count // 5  # Weight frames less

        # Check for UI kit references
        uikit_matches = self.search_content(
            r"ui.*kit|component.*library|design.*component", max_results=5
        )
        if uikit_matches:
            evidence.append(f"UI kit references ({len(uikit_matches)} mentions)")
            count += 1

        # Check for design token files
        token_files = self.find_files("**/*token*.{json,js,ts}")
        if token_files:
            evidence.append(f"Design tokens ({len(token_files)} files)")
            count += len(token_files)

        # Check for Figma/Sketch references
        design_tool_matches = self.search_content(r"figma|sketch|adobe.*xd", max_results=3)
        if design_tool_matches:
            evidence.append(f"Design tool integration")
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

    def _analyze_design_systems(self) -> Dict[str, Any]:
        """
        Analyze design system documentation

        Looks for:
        - DESIGN.md files
        - design-systems/ directories
        - Style guides
        - Pattern libraries
        - Design principles documentation
        """
        evidence = []
        count = 0

        # Check for DESIGN.md files
        design_md_files = self.find_files("**/DESIGN.md")
        if design_md_files:
            evidence.extend([str(f.relative_to(self.repo_path)) for f in design_md_files[:3]])
            count += len(design_md_files)

            # Check size/depth of DESIGN.md files
            for dm in design_md_files:
                lines = self.count_lines_in_file(str(dm.relative_to(self.repo_path)))
                if lines > 100:
                    count += 1  # Bonus for comprehensive documentation

        # Check for design-systems directory
        if self.has_directory("design-systems"):
            evidence.append("design-systems/ directory")
            count += 2

        # Check for style guide references
        style_matches = self.search_content(
            r"style.*guide|design.*system|pattern.*library", max_results=5
        )
        if style_matches:
            evidence.append(f"Style guide references ({len(style_matches)} mentions)")
            count += 1

        # Check for design principles
        principles_matches = self.search_content(
            r"design.*principle|design.*philosophy|design.*approach",
            file_extensions=[".md"],
            max_results=3,
        )
        if principles_matches:
            evidence.append(f"Design principles documented")
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

    def _analyze_brand_protocols(self) -> Dict[str, Any]:
        """
        Analyze brand protocol capabilities

        Looks for:
        - core-asset-protocol references
        - brand-spec.md
        - Logo management systems
        - Brand guidelines
        - Asset versioning
        """
        evidence = []
        count = 0

        # Check for brand-spec.md
        if self.has_file("brand-spec.md"):
            evidence.append("brand-spec.md")
            count += 2

        # Check for core-asset-protocol
        asset_protocol_matches = self.search_content(
            r"core.*asset.*protocol|asset.*management|brand.*asset", max_results=5
        )
        if asset_protocol_matches:
            evidence.append(f"Asset protocol references ({len(asset_protocol_matches)} mentions)")
            count += len(asset_protocol_matches)

        # Check for logo directories
        logo_dirs = ["logos", "logo", "brand", "assets"]
        for logo_dir in logo_dirs:
            if self.has_directory(logo_dir):
                evidence.append(f"{logo_dir}/ directory")
                count += 1
                break

        # Check for brand guidelines
        brand_files = self.find_files("**/*brand*.md")
        if brand_files:
            evidence.extend([str(f.relative_to(self.repo_path)) for f in brand_files[:2]])
            count += len(brand_files)

        thresholds = {"excellent": 6, "good": 4, "adequate": 2}
        score, quality = self.calculate_quality_score(count, thresholds)

        return {
            "detected": count > 0,
            "score": score,
            "evidence": evidence,
            "count": count,
            "quality": quality,
        }

    def _analyze_reasoning(self) -> Dict[str, Any]:
        """
        Analyze design reasoning capabilities

        Looks for:
        - ui-reasoning.csv
        - Search engines (BM25, vector search)
        - Decision logs
        - Design rationale documentation
        - Critique systems
        """
        evidence = []
        count = 0

        # Check for ui-reasoning.csv
        reasoning_files = self.find_files("**/*reasoning*.csv")
        if reasoning_files:
            evidence.extend([str(f.relative_to(self.repo_path)) for f in reasoning_files[:3]])
            count += len(reasoning_files) * 2  # Weight reasoning highly

        # Check for search engine implementation
        search_matches = self.search_content(
            r"bm25|vector.*search|embedding.*search|semantic.*search",
            file_extensions=[".py", ".js", ".ts"],
            max_results=5,
        )
        if search_matches:
            evidence.append(f"Search engine implementation ({len(search_matches)} files)")
            count += len(search_matches)

        # Check for decision logs
        decision_files = self.find_files("**/decision*.md")
        if decision_files:
            evidence.append(f"Decision logs ({len(decision_files)} files)")
            count += len(decision_files)

        # Check for critique systems
        critique_matches = self.search_content(
            r"critique|design.*review|design.*feedback", max_results=3
        )
        if critique_matches:
            evidence.append(f"Critique system references")
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

    def _analyze_anti_patterns(self) -> Dict[str, Any]:
        """
        Analyze anti-pattern detection capabilities

        Looks for:
        - anti-pattern directories
        - Rule files
        - CLI tools for checking
        - jsdom for validation
        - Linting configurations
        """
        evidence = []
        count = 0

        # Check for anti-pattern directories
        if self.has_directory("anti-pattern") or self.has_directory("anti-patterns"):
            evidence.append("anti-pattern/ directory")
            count += 2

            # Count rule files
            rule_count = self.count_files("**/anti-pattern*/**/*")
            if rule_count > 0:
                evidence.append(f"{rule_count} anti-pattern files")
                count += rule_count // 3

        # Check for CLI tools
        cli_files = self.find_files("**/cli*.{py,js,ts}")
        for cli_file in cli_files:
            content = self.read_file(str(cli_file.relative_to(self.repo_path)))
            if content and "anti-pattern" in content.lower():
                evidence.append(f"Anti-pattern CLI tool")
                count += 2
                break

        # Check for jsdom usage (for HTML validation)
        jsdom_matches = self.search_content(r"jsdom|JSDOM", max_results=3)
        if jsdom_matches:
            evidence.append(f"jsdom validation")
            count += 1

        # Check for linting configs
        lint_files = self.find_files("**/.eslintrc*") + self.find_files("**/.stylelintrc*")
        if lint_files:
            evidence.append(f"Linting configurations")
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

    def _analyze_export_formats(self) -> Dict[str, Any]:
        """
        Analyze export format capabilities

        Looks for:
        - html2pptx
        - Video export (ffmpeg)
        - PDF generation
        - Image export pipelines
        - Multi-format support
        """
        evidence = []
        count = 0

        # Check for html2pptx
        pptx_matches = self.search_content(r"html2pptx|pptxgenjs|officegen", max_results=3)
        if pptx_matches:
            evidence.append(f"PowerPoint export capability")
            count += 2

        # Check for video export
        video_matches = self.search_content(
            r"ffmpeg|video.*export|canvas.*record|media.*recorder",
            file_extensions=[".py", ".js", ".ts"],
            max_results=3,
        )
        if video_matches:
            evidence.append(f"Video export capability")
            count += 2

        # Check for PDF generation
        pdf_matches = self.search_content(r"puppeteer|playwright|pdfkit|weasyprint", max_results=3)
        if pdf_matches:
            evidence.append(f"PDF generation")
            count += 1

        # Check for image export
        image_matches = self.search_content(
            r"canvas.*toBlob|sharp|pillow|imagemagick", max_results=3
        )
        if image_matches:
            evidence.append(f"Image export pipelines")
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

    def _analyze_quality_gates(self) -> Dict[str, Any]:
        """
        Analyze quality gate capabilities

        Looks for:
        - Critique systems
        - Accessibility checks
        - Contrast validation
        - Design validation pipelines
        - CI/CD integration
        """
        evidence = []
        count = 0

        # Check for critique systems
        critique_files = self.find_files("**/*critique*.{py,js,ts}")
        if critique_files:
            evidence.append(f"Critique system ({len(critique_files)} files)")
            count += len(critique_files)

        # Check for accessibility tools
        a11y_matches = self.search_content(r"a11y|accessibility|aria|wcag|axe-core", max_results=5)
        if a11y_matches:
            evidence.append(f"Accessibility checks")
            count += 1

        # Check for validation pipelines
        ci_files = self.find_files("**/.github/workflows/*.{yml,yaml}")
        for ci_file in ci_files:
            content = self.read_file(str(ci_file.relative_to(self.repo_path)))
            if content and ("design" in content.lower() or "validate" in content.lower()):
                evidence.append(f"CI design validation")
                count += 1
                break

        thresholds = {"excellent": 4, "good": 2, "adequate": 1}
        score, quality = self.calculate_quality_score(count, thresholds)

        return {
            "detected": count > 0,
            "score": score,
            "evidence": evidence,
            "count": count,
            "quality": quality,
        }

    def _analyze_register_system(self) -> Dict[str, Any]:
        """
        Analyze register system capabilities

        Looks for:
        - brand.md
        - product.md
        - Register references
        - Multi-register support
        - Context-aware design
        """
        evidence = []
        count = 0

        # Check for brand.md
        if self.has_file("brand.md"):
            evidence.append("brand.md")
            count += 1

        # Check for product.md
        if self.has_file("product.md"):
            evidence.append("product.md")
            count += 1

        # Check for register references
        register_matches = self.search_content(
            r"register.*system|design.*register|brand.*register", max_results=5
        )
        if register_matches:
            evidence.append(f"Register system references ({len(register_matches)} mentions)")
            count += len(register_matches)

        # Check for context-aware design
        context_matches = self.search_content(
            r"context.*aware|adaptive.*design|dynamic.*brand", max_results=3
        )
        if context_matches:
            evidence.append(f"Context-aware design")
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
        """
        Identify unique features this design repo has

        Returns:
            List of unique feature descriptions
        """
        unique = []

        # Check for advanced color features
        if self.count_files("**/*oklch*.{py,js,ts}") > 0:
            unique.append("OKLCH color space implementation")

        # Check for advanced reasoning
        if self.count_files("**/*reasoning*.csv") > 0:
            unique.append("Structured design reasoning database")

        # Check for anti-pattern CLI
        cli_files = self.find_files("**/cli*.{py,js,ts}")
        for cli_file in cli_files:
            content = self.read_file(str(cli_file.relative_to(self.repo_path)))
            if content and "anti-pattern" in content.lower():
                unique.append("CLI-based anti-pattern detection")
                break

        # Check for video export
        if len(self.search_content(r"ffmpeg|video.*export", max_results=1)) > 0:
            unique.append("Video export pipeline")

        # Check for device frame library
        if self.has_directory("device-frames"):
            frame_count = self.count_files("**/device-frames/**/*")
            if frame_count > 20:
                unique.append(f"Extensive device frame library ({frame_count}+ frames)")

        return unique
