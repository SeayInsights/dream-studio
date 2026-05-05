"""
Context7Manager - Progressive context loading for large codebase analysis.

Three-phase loading strategy:
1. Skeleton: Extract imports, exports, function signatures
2. Rank: TF-IDF relevance scoring against query
3. Progressive: Load full details until token budget

Prevents context overflow on 10k+ file projects.
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import heapq
from sklearn.feature_extraction.text import CountVectorizer, TfidfTransformer


@dataclass
class FileSkeleton:
    """Lightweight representation of a source file."""
    path: Path
    imports: List[str]
    exports: List[str]
    functions: List[str]
    classes: List[str]
    estimated_tokens: int
    relevance_score: float = 0.0


@dataclass
class FileDetail:
    """Full file content with metadata."""
    path: Path
    content: str
    skeleton: FileSkeleton
    tokens: int


class Context7Manager:
    """
    Progressive context loader with token budget management.

    Usage:
        manager = Context7Manager(max_tokens=150000)
        result = manager.load_codebase(Path("./project"), "authentication logic")
        print(f"Loaded {result['coverage']:.1%} of codebase")
    """

    def __init__(self, max_tokens: int = 150000):
        """
        Initialize context manager with token budget.

        Args:
            max_tokens: Maximum tokens to load (default: 150k)
        """
        self.max_tokens = max_tokens
        self.supported_extensions = {'.py', '.js', '.ts', '.tsx', '.jsx'}

    def load_codebase(self, path: Path, query: str) -> Dict:
        """
        Load codebase progressively based on relevance to query.

        Args:
            path: Root directory to analyze
            query: Search query for relevance ranking

        Returns:
            Dict with keys:
                - skeleton: Dict[str, FileSkeleton] for all files
                - details: List[FileDetail] for loaded files
                - tokens_used: Total tokens consumed
                - coverage: Fraction of codebase loaded (0.0 to 1.0)
                - total_files: Number of files found
                - loaded_files: Number of files fully loaded
        """
        # Phase 1: Extract skeletons
        print(f"Phase 1: Scanning {path}...")
        skeletons = self._scan_directory(path)

        if not skeletons:
            return {
                "skeleton": {},
                "details": [],
                "tokens_used": 0,
                "coverage": 0.0,
                "total_files": 0,
                "loaded_files": 0
            }

        # Phase 2: Rank by relevance
        print(f"Phase 2: Ranking {len(skeletons)} files by relevance...")
        ranked = self._rank_relevance(skeletons, query)

        # Phase 3: Progressive loading
        print(f"Phase 3: Loading details (budget: {self.max_tokens:,} tokens)...")
        details, tokens_used = self._progressive_load(ranked)

        total_tokens = sum(s.estimated_tokens for s in skeletons)
        coverage = tokens_used / total_tokens if total_tokens > 0 else 0.0

        # Convert skeletons to dict
        skeleton_dict = {str(s.path): s for s in skeletons}

        return {
            "skeleton": skeleton_dict,
            "details": details,
            "tokens_used": tokens_used,
            "coverage": coverage,
            "total_files": len(skeletons),
            "loaded_files": len(details)
        }

    def _scan_directory(self, path: Path) -> List[FileSkeleton]:
        """
        Recursively scan directory for source files.

        Args:
            path: Directory to scan

        Returns:
            List of FileSkeleton objects
        """
        skeletons = []

        for file_path in path.rglob('*'):
            if file_path.is_file() and file_path.suffix in self.supported_extensions:
                # Skip node_modules, venv, etc.
                if any(part.startswith('.') or part in {'node_modules', 'venv', '__pycache__', 'dist', 'build'}
                       for part in file_path.parts):
                    continue

                skeleton = self._extract_skeleton(file_path)
                if skeleton:
                    skeletons.append(skeleton)

        return skeletons

    def _extract_skeleton(self, file_path: Path) -> Optional[FileSkeleton]:
        """
        Extract lightweight skeleton from source file.

        Args:
            file_path: Path to source file

        Returns:
            FileSkeleton or None if extraction fails
        """
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            print(f"Warning: Could not read {file_path}: {e}")
            return None

        ext = file_path.suffix

        if ext == '.py':
            return self._extract_python_skeleton(file_path, content)
        elif ext in {'.js', '.ts', '.tsx', '.jsx'}:
            return self._extract_js_skeleton(file_path, content)

        return None

    def _extract_python_skeleton(self, file_path: Path, content: str) -> FileSkeleton:
        """Extract skeleton from Python file."""
        imports = []
        exports = []
        functions = []
        classes = []

        # Extract imports
        import_pattern = r'^(?:from\s+[\w.]+\s+)?import\s+(.+)$'
        for match in re.finditer(import_pattern, content, re.MULTILINE):
            imports.append(match.group(0).strip())

        # Extract function definitions
        func_pattern = r'^(?:async\s+)?def\s+(\w+)\s*\('
        for match in re.finditer(func_pattern, content, re.MULTILINE):
            func_name = match.group(1)
            functions.append(func_name)
            # Public functions are exports
            if not func_name.startswith('_'):
                exports.append(func_name)

        # Extract class definitions
        class_pattern = r'^class\s+(\w+)[\s\(:]'
        for match in re.finditer(class_pattern, content, re.MULTILINE):
            class_name = match.group(1)
            classes.append(class_name)
            # Public classes are exports
            if not class_name.startswith('_'):
                exports.append(class_name)

        tokens = self._estimate_tokens(content)

        return FileSkeleton(
            path=file_path,
            imports=imports,
            exports=exports,
            functions=functions,
            classes=classes,
            estimated_tokens=tokens
        )

    def _extract_js_skeleton(self, file_path: Path, content: str) -> FileSkeleton:
        """Extract skeleton from JavaScript/TypeScript file."""
        imports = []
        exports = []
        functions = []
        classes = []

        # Extract imports
        import_patterns = [
            r'^import\s+.+\s+from\s+["\'].+["\']',
            r'^import\s+["\'].+["\']',
            r'^const\s+.+\s*=\s*require\(["\'].+["\']\)'
        ]
        for pattern in import_patterns:
            for match in re.finditer(pattern, content, re.MULTILINE):
                imports.append(match.group(0).strip())

        # Extract function declarations
        func_patterns = [
            r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(',
            r'(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>',
            r'(\w+)\s*:\s*(?:async\s+)?\([^)]*\)\s*=>',  # Object method
        ]
        for pattern in func_patterns:
            for match in re.finditer(pattern, content):
                func_name = match.group(1)
                if func_name:
                    functions.append(func_name)

        # Extract class definitions
        class_pattern = r'(?:export\s+)?class\s+(\w+)'
        for match in re.finditer(class_pattern, content):
            classes.append(match.group(1))

        # Extract exports
        export_patterns = [
            r'export\s+(?:default\s+)?(?:class|function|const|let|var)\s+(\w+)',
            r'export\s+\{([^}]+)\}',
            r'export\s+default\s+(\w+)'
        ]
        for pattern in export_patterns:
            for match in re.finditer(pattern, content):
                export_text = match.group(1)
                # Handle export { a, b, c }
                if ',' in export_text:
                    exports.extend([name.strip() for name in export_text.split(',')])
                else:
                    exports.append(export_text.strip())

        tokens = self._estimate_tokens(content)

        return FileSkeleton(
            path=file_path,
            imports=imports,
            exports=exports,
            functions=functions,
            classes=classes,
            estimated_tokens=tokens
        )

    def _rank_relevance(self, skeletons: List[FileSkeleton], query: str) -> List[FileSkeleton]:
        """
        Rank files by relevance to query using TF-IDF.

        Args:
            skeletons: List of file skeletons
            query: Search query

        Returns:
            Skeletons sorted by relevance (highest first)
        """
        if not query.strip():
            # No query: rank by estimated importance
            return sorted(skeletons, key=lambda s: len(s.exports) + len(s.classes), reverse=True)

        # Build corpus: file paths + exports + functions + classes
        corpus = []
        for skeleton in skeletons:
            doc_parts = [
                str(skeleton.path),
                ' '.join(skeleton.exports),
                ' '.join(skeleton.functions),
                ' '.join(skeleton.classes)
            ]
            corpus.append(' '.join(doc_parts))

        # Add query as last document
        corpus.append(query)

        try:
            # TF-IDF vectorization
            vectorizer = CountVectorizer(stop_words='english', max_features=1000)
            counts = vectorizer.fit_transform(corpus)

            tfidf_transformer = TfidfTransformer()
            tfidf_matrix = tfidf_transformer.fit_transform(counts)

            # Query is last row
            query_vector = tfidf_matrix[-1]

            # Compute cosine similarity
            from sklearn.metrics.pairwise import cosine_similarity
            similarities = cosine_similarity(query_vector, tfidf_matrix[:-1]).flatten()

            # Assign scores
            for i, skeleton in enumerate(skeletons):
                skeleton.relevance_score = similarities[i]

        except Exception as e:
            print(f"Warning: TF-IDF ranking failed ({e}), using keyword matching")
            # Fallback: simple keyword matching
            query_keywords = set(query.lower().split())
            for skeleton in skeletons:
                search_text = ' '.join([
                    str(skeleton.path).lower(),
                    ' '.join(skeleton.exports).lower(),
                    ' '.join(skeleton.functions).lower(),
                    ' '.join(skeleton.classes).lower()
                ])
                matches = sum(1 for kw in query_keywords if kw in search_text)
                skeleton.relevance_score = matches / len(query_keywords) if query_keywords else 0

        return sorted(skeletons, key=lambda s: s.relevance_score, reverse=True)

    def _progressive_load(self, ranked_skeletons: List[FileSkeleton]) -> Tuple[List[FileDetail], int]:
        """
        Load file details progressively until token budget exhausted.

        Args:
            ranked_skeletons: Skeletons sorted by relevance

        Returns:
            (list of FileDetail, total tokens used)
        """
        details = []
        tokens_used = 0

        for skeleton in ranked_skeletons:
            if tokens_used + skeleton.estimated_tokens > self.max_tokens:
                print(f"Token budget exhausted. Loaded {len(details)}/{len(ranked_skeletons)} files.")
                break

            try:
                content = skeleton.path.read_text(encoding='utf-8', errors='ignore')
                actual_tokens = self._estimate_tokens(content)

                detail = FileDetail(
                    path=skeleton.path,
                    content=content,
                    skeleton=skeleton,
                    tokens=actual_tokens
                )

                details.append(detail)
                tokens_used += actual_tokens

            except Exception as e:
                print(f"Warning: Could not load {skeleton.path}: {e}")
                continue

        return details, tokens_used

    def _estimate_tokens(self, content: str) -> int:
        """
        Estimate token count for content.

        Uses GPT approximation: ~4 chars per token.

        Args:
            content: Text content

        Returns:
            Estimated token count
        """
        return len(content) // 4


def main():
    """Test Context7Manager on dream-studio codebase."""
    manager = Context7Manager(max_tokens=150000)

    # Test with dream-studio root
    dream_studio_path = Path(__file__).parent.parent.parent.parent

    print(f"\n{'='*60}")
    print(f"Testing Context7Manager on: {dream_studio_path}")
    print(f"{'='*60}\n")

    # Test query
    query = "skill execution and pack routing"

    result = manager.load_codebase(dream_studio_path, query)

    print(f"\n{'='*60}")
    print("RESULTS")
    print(f"{'='*60}")
    print(f"Total files found: {result['total_files']}")
    print(f"Files loaded: {result['loaded_files']}")
    print(f"Tokens used: {result['tokens_used']:,} / {manager.max_tokens:,}")
    print(f"Coverage: {result['coverage']:.1%}")

    print(f"\n{'='*60}")
    print("TOP 10 LOADED FILES (by relevance)")
    print(f"{'='*60}")

    for i, detail in enumerate(result['details'][:10], 1):
        rel_path = detail.path.relative_to(dream_studio_path)
        print(f"{i:2d}. {rel_path}")
        print(f"    Score: {detail.skeleton.relevance_score:.3f} | Tokens: {detail.tokens:,}")
        print(f"    Exports: {', '.join(detail.skeleton.exports[:5])}")
        if len(detail.skeleton.exports) > 5:
            print(f"             ... and {len(detail.skeleton.exports) - 5} more")
        print()

    print(f"\n{'='*60}")
    print("SKELETON SUMMARY (all files)")
    print(f"{'='*60}")

    total_exports = sum(len(s.exports) for s in result['skeleton'].values())
    total_functions = sum(len(s.functions) for s in result['skeleton'].values())
    total_classes = sum(len(s.classes) for s in result['skeleton'].values())

    print(f"Total exports: {total_exports}")
    print(f"Total functions: {total_functions}")
    print(f"Total classes: {total_classes}")


if __name__ == "__main__":
    main()
