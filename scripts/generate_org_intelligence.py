"""Generate organization-level engineering intelligence graph.

DETERMINISTIC. NO LLM. Pure graph analytics.
"""

from __future__ import annotations
import json
import yaml
from pathlib import Path

from core.org_intelligence import (
    MultiRepoIngestor,
    CapabilityNormalizer,
    OrganizationGraphBuilder,
    CrossRepoAnalyzer,
    RoleBasedInsightEngine,
)


def generate_org_intelligence(
    repo_paths: list[str],
    output_dir: str,
):
    """Generate complete organization intelligence.

    Args:
        repo_paths: List of repository paths or folder containing repos
        output_dir: Output directory for artifacts
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("ORGANIZATION INTELLIGENCE GRAPH")
    print("=" * 60)
    print()

    # Step 1: Ingest repositories
    print(">> Step 1: Ingesting repositories...")
    ingestor = MultiRepoIngestor()

    if len(repo_paths) == 1 and Path(repo_paths[0]).is_dir():
        folder_path = repo_paths[0]
        try:
            repo_ids = ingestor.ingest_folder(folder_path)
            print(f"   Ingested {len(repo_ids)} repositories from folder")
        except Exception:
            repo_ids = [ingestor.ingest_repository(folder_path)]
            print("   Ingested 1 repository")
    else:
        repo_ids = ingestor.ingest_multiple(repo_paths)
        print(f"   Ingested {len(repo_ids)} repositories")

    repositories, modules, edges = ingestor.get_results()
    print(f"   Total modules: {len(modules)}")
    print()

    # Step 2: Normalize capabilities
    print(">> Step 2: Normalizing capabilities...")
    normalizer = CapabilityNormalizer()
    capabilities = normalizer.normalize_modules(modules, repositories)
    print(f"   Identified {len(capabilities)} capabilities")
    print()

    # Step 3: Build organization graph
    print(">> Step 3: Building organization graph...")
    builder = OrganizationGraphBuilder()
    graph = builder.build_graph(repositories, modules, capabilities, edges)
    print(
        f"   Nodes: {len(graph.repositories)} repos, "
        f"{len(graph.modules)} modules, {len(graph.capabilities)} capabilities"
    )
    print(f"   Edges: {len(graph.edges)}")
    print()

    # Step 4: Cross-repository analysis
    print(">> Step 4: Analyzing cross-repository patterns...")
    cross_analyzer = CrossRepoAnalyzer(graph)
    cross_analysis = cross_analyzer.analyze()
    print(f"   Duplicates detected: {len(cross_analysis.duplicates)}")
    print(f"   Duplication rate: {cross_analysis.duplication_rate:.1%}")
    print(f"   Consolidation opportunities: {len(cross_analysis.consolidation_opportunities)}")
    print()

    # Step 5: Generate role-based insights
    print(">> Step 5: Generating role-based insights...")
    insight_engine = RoleBasedInsightEngine(graph, cross_analysis)

    vp_metrics = insight_engine.generate_vp_metrics()
    eng_debt = insight_engine.generate_engineering_debt_map()
    insight_engine.generate_security_compliance_view()
    insight_engine.generate_product_view()

    print(f"   System health: {vp_metrics.system_health_score:.1%}")
    print(f"   Risk hotspots: {len(vp_metrics.risk_hotspots)}")
    print()

    # Step 6: Generate output artifacts
    print(">> Step 6: Writing output artifacts...")

    graph_path = output_path / "org_graph.json"
    with open(graph_path, "w") as f:
        json.dump(graph.to_dict(), f, indent=2)
    print(f"   [1/6] {graph_path}")

    ontology_path = output_path / "capability_ontology.yaml"
    with open(ontology_path, "w") as f:
        yaml.dump(normalizer.get_capability_ontology(), f, default_flow_style=False)
    print(f"   [2/6] {ontology_path}")

    health_report_path = output_path / "org_health_report.md"
    with open(health_report_path, "w") as f:
        write_health_report(f, vp_metrics, cross_analysis, graph)
    print(f"   [3/6] {health_report_path}")

    vp_metrics_path = output_path / "vp_metrics.json"
    with open(vp_metrics_path, "w") as f:
        json.dump(
            {
                "system_health_score": vp_metrics.system_health_score,
                "risk_hotspots": vp_metrics.risk_hotspots,
                "duplication_rate": vp_metrics.duplication_rate,
                "consolidation_candidates": vp_metrics.consolidation_candidates,
                "total_repositories": vp_metrics.total_repositories,
                "total_modules": vp_metrics.total_modules,
                "total_capabilities": vp_metrics.total_capabilities,
                "total_loc": vp_metrics.total_loc,
            },
            f,
            indent=2,
        )
    print(f"   [4/6] {vp_metrics_path}")

    debt_map_path = output_path / "engineering_debt_map.json"
    with open(debt_map_path, "w") as f:
        json.dump(
            {
                "coupling_hotspots": eng_debt.coupling_hotspots,
                "refactor_targets": eng_debt.refactor_targets,
                "dependency_explosion_points": eng_debt.dependency_explosion_points,
            },
            f,
            indent=2,
        )
    print(f"   [5/6] {debt_map_path}")

    consolidation_path = output_path / "consolidation_opportunities.md"
    with open(consolidation_path, "w") as f:
        write_consolidation_report(f, cross_analysis)
    print(f"   [6/6] {consolidation_path}")

    print()
    print(">> Organization intelligence generation complete!")
    print()

    print("SUMMARY")
    print("-" * 60)
    print(f"System Health: {vp_metrics.system_health_score:.1%}")
    print(f"Duplication Rate: {cross_analysis.duplication_rate:.1%}")
    print(f"Risk Hotspots: {len(vp_metrics.risk_hotspots)}")
    print(f"Consolidation Opportunities: {len(cross_analysis.consolidation_opportunities)}")
    print()


def write_health_report(f, vp_metrics, cross_analysis, graph):
    """Write organization health report."""
    f.write("# Organization Health Report\n\n")
    f.write("## Executive Summary\n\n")
    f.write(f"**System Health Score:** {vp_metrics.system_health_score:.1%}\n\n")
    f.write("### Key Metrics\n\n")
    f.write(f"- **Repositories:** {vp_metrics.total_repositories}\n")
    f.write(f"- **Modules:** {vp_metrics.total_modules}\n")
    f.write(f"- **Capabilities:** {vp_metrics.total_capabilities}\n")
    f.write(f"- **Total LOC:** {vp_metrics.total_loc:,}\n")
    f.write(f"- **Duplication Rate:** {vp_metrics.duplication_rate:.1%}\n")
    f.write(f"- **Risk Hotspots:** {len(vp_metrics.risk_hotspots)}\n\n")
    f.write("## Risk Hotspots\n\n")
    if vp_metrics.risk_hotspots:
        for cap_id in vp_metrics.risk_hotspots[:10]:
            cap = graph.capabilities.get(cap_id)
            if cap:
                f.write(f"### {cap.normalized_name}\n\n")
                f.write(f"- **Risk Score:** {cap.risk_score:.2f}\n")
                f.write(f"- **Modules:** {cap.module_count}\n")
                f.write(f"- **LOC:** {cap.loc:,}\n")
                f.write(f"- **Repos:** {', '.join(cap.source_repos)}\n\n")
    else:
        f.write("No risk hotspots detected.\n\n")
    f.write("## Duplication Analysis\n\n")
    f.write(f"**Total Duplicated LOC:** {cross_analysis.total_duplication_loc:,}\n")
    f.write(f"**Duplication Rate:** {cross_analysis.duplication_rate:.1%}\n\n")
    if cross_analysis.duplicates:
        f.write("### Top Duplicates\n\n")
        for dup in cross_analysis.duplicates[:5]:
            f.write(f"#### {dup.capability_name}\n\n")
            f.write(f"- **Repos:** {', '.join(dup.repos)}\n")
            f.write(f"- **Total LOC:** {dup.total_loc:,}\n")
            f.write(f"- **Consolidation Score:** {dup.consolidation_score:.2f}\n\n")


def write_consolidation_report(f, cross_analysis):
    """Write consolidation opportunities report."""
    f.write("# Consolidation Opportunities\n\n")
    f.write(f"**Total Opportunities:** {len(cross_analysis.consolidation_opportunities)}\n\n")
    if not cross_analysis.consolidation_opportunities:
        f.write("No consolidation opportunities detected.\n")
        return
    f.write("## Ranked Opportunities\n\n")
    for opp in cross_analysis.consolidation_opportunities:
        f.write(f"### {opp.opportunity_id}\n\n")
        f.write(f"**Capability:** {opp.capability_name}\n\n")
        f.write(f"**Priority Score:** {opp.priority_score:.2f}\n\n")
        f.write("**Source Repos:**\n")
        for repo in opp.source_repos:
            f.write(f"- {repo}\n")
        f.write(f"\n**Target Repo:** {opp.target_repo}\n\n")
        f.write(f"**Estimated Effort:** {opp.estimated_effort}\n\n")
        f.write(f"**Reason:** {opp.reason}\n\n")
        f.write("---\n\n")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate organization intelligence graph")
    parser.add_argument(
        "repos",
        nargs="+",
        help="Repository paths or folder containing repositories",
    )
    parser.add_argument(
        "--output-dir",
        default="docs/org_intelligence",
        help="Output directory (default: docs/org_intelligence)",
    )
    args = parser.parse_args()
    generate_org_intelligence(args.repos, args.output_dir)


if __name__ == "__main__":
    main()
