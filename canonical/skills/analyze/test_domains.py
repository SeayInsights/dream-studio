#!/usr/bin/env python3
"""Test script to verify all domain analyzers are registered"""

import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from domains.registry import DomainAnalyzerRegistry

# List registered domains
domains = DomainAnalyzerRegistry.list_domains()
print(f"Registered domains: {', '.join(domains)}")

# Get detailed info
info = DomainAnalyzerRegistry.get_domain_info()

print("\nDomain Details:")
for domain in domains:
    domain_info = info[domain]
    print(f"\n{domain}:")
    print(f"  Class: {domain_info['class']}")
    print(f"  Capabilities: {domain_info['capabilities_count']}")
    print(f"  Markers: {len(domain_info['markers'])}")
    print(f"  Capabilities list: {', '.join(domain_info['capabilities'][:3])}...")
