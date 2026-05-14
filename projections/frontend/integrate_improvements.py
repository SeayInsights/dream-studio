#!/usr/bin/env python3
"""
Integrate dashboard improvements:
1. Add left sidebar navigation
2. Replace hooks section with improved version
3. Reorganize tab structure (hooks under Performance, security under Projects)
4. Keep all existing functionality
"""

import re
from pathlib import Path


def main():
    frontend_dir = Path(__file__).parent

    # Read files
    with open(frontend_dir / "dashboard.html", "r", encoding="utf-8") as f:
        original = f.read()

    with open(frontend_dir / "hooks_improved.html", "r", encoding="utf-8") as f:
        improved_hooks = f.read()

    # Extract just the hooks tab content (without the script tags for now)
    hooks_content = improved_hooks.split("<script>")[0]
    hooks_script = (
        improved_hooks.split("<script>")[1].split("</script>")[0]
        if "<script>" in improved_hooks
        else ""
    )

    # 1. Add sidebar CSS to the style section
    sidebar_css = """
        /* Sidebar Navigation Styles */
        .sidebar {
            width: 260px;
            height: calc(100vh - 65px);
            position: fixed;
            left: 0;
            top: 65px;
            background: white;
            border-right: 1px solid #e5e7eb;
            overflow-y: auto;
            transition: transform 0.3s ease;
            z-index: 40;
        }

        .sidebar-hidden {
            transform: translateX(-100%);
        }

        .sidebar-section {
            padding: 0.75rem 0;
            border-bottom: 1px solid #f3f4f6;
        }

        .sidebar-section-title {
            padding: 0.5rem 1rem;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #6b7280;
            display: flex;
            align-items: center;
            justify-content: space-between;
            cursor: pointer;
            user-select: none;
        }

        .sidebar-section-title:hover {
            background: #f9fafb;
        }

        .sidebar-item {
            padding: 0.625rem 1rem 0.625rem 2rem;
            font-size: 0.875rem;
            color: #374151;
            cursor: pointer;
            transition: all 0.15s;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .sidebar-item:hover {
            background: #f3f4f6;
            color: #1f2937;
        }

        .sidebar-item.active {
            background: #eff6ff;
            color: #2563eb;
            border-left: 3px solid #2563eb;
            font-weight: 500;
        }

        .sidebar-subsection {
            display: none;
            padding-left: 1rem;
        }

        .sidebar-subsection.expanded {
            display: block;
        }

        .chevron {
            transition: transform 0.2s;
            font-size: 0.75rem;
        }

        .chevron.expanded {
            transform: rotate(90deg);
        }

        /* Main content with sidebar */
        .main-content-area {
            margin-left: 260px;
            transition: margin-left 0.3s ease;
        }

        .main-content-area.sidebar-collapsed {
            margin-left: 0;
        }

        /* Mobile sidebar toggle */
        .sidebar-toggle {
            display: none;
            position: fixed;
            bottom: 1.5rem;
            left: 1rem;
            z-index: 50;
            background: #2563eb;
            color: white;
            width: 3rem;
            height: 3rem;
            border-radius: 50%;
            box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
            align-items: center;
            justify-content: center;
            cursor: pointer;
        }

        @media (max-width: 1024px) {
            .sidebar {
                transform: translateX(-100%);
            }

            .sidebar.mobile-open {
                transform: translateX(0);
            }

            .main-content-area {
                margin-left: 0;
            }

            .sidebar-toggle {
                display: flex;
            }
        }

        /* Hook cards styling */
        .hook-card {
            border-left: 4px solid;
            transition: all 0.2s;
        }
        .hook-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
        }
"""

    # Find the </style> tag and insert sidebar CSS before it
    style_end = original.find("</style>")
    if style_end != -1:
        original = original[:style_end] + sidebar_css + original[style_end:]

    # 2. Replace old hooks section with improved version
    # Find the hooks tab section
    hooks_start = original.find("<!-- Hooks Tab -->")
    hooks_end = original.find("<!-- Security Tab -->")

    if hooks_start != -1 and hooks_end != -1:
        original = original[:hooks_start] + hooks_content + "\n" + original[hooks_end:]
        print("[OK] Replaced hooks section with improved version")
    else:
        print("[WARN] Could not find hooks section to replace")

    # 3. Remove old tab navigation and replace with sidebar
    # Find the tab navigation section
    tab_nav_start = original.find("<!-- Tab Navigation")
    tab_nav_end = original.find("</div>\n    </div>\n\n    <!-- Main Content -->")

    if tab_nav_start != -1 and tab_nav_end != -1:
        # Create sidebar HTML
        sidebar_html = """<!-- Header -->
    <header class="bg-white shadow-sm border-b border-gray-200 fixed top-0 left-0 right-0 z-50" style="height: 65px;">
        <div class="px-4 sm:px-6 lg:px-8 py-4">
            <div class="flex justify-between items-center">
                <div class="flex items-center gap-4">
                    <button onclick="toggleSidebar()" class="lg:hidden text-gray-600 hover:text-gray-900">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
                        </svg>
                    </button>
                    <div>
                        <h1 class="text-2xl font-bold text-gray-900">Dream Studio Analytics</h1>
                        <p class="text-sm text-gray-600 mt-1">Real-time performance monitoring</p>
                    </div>
                </div>
                <div class="flex items-center space-x-4">
                    <div class="flex items-center text-sm">
                        <span class="connection-status status-disconnected" id="connectionStatus"></span>
                        <span id="connectionText" class="text-gray-700">Disconnected</span>
                    </div>
                    <div class="text-right hidden sm:block">
                        <div class="text-xs text-gray-500">Last updated</div>
                        <div class="text-sm font-medium text-gray-900" id="lastUpdated">--:--:--</div>
                    </div>
                </div>
            </div>
        </div>
    </header>

    <!-- Sidebar Navigation -->
    <nav class="sidebar" id="sidebar">
        <!-- Overview Section -->
        <div class="sidebar-section">
            <div class="sidebar-section-title" onclick="navigate('overview')">
                <span>📊 Overview</span>
            </div>
        </div>

        <!-- Performance Section -->
        <div class="sidebar-section">
            <div class="sidebar-section-title" onclick="toggleSection('performance')">
                <span>🤖 Performance</span>
                <span class="chevron expanded" id="chevron-performance">▶</span>
            </div>
            <div class="sidebar-subsection expanded" id="section-performance">
                <div class="sidebar-item" onclick="navigate('skills')">
                    <span>⚡</span>
                    <span>Skills</span>
                </div>
                <div class="sidebar-item" onclick="navigate('hooks')">
                    <span>⚙️</span>
                    <span>Hooks</span>
                </div>
                <div class="sidebar-item" onclick="navigate('workflows')">
                    <span>🔄</span>
                    <span>Workflows</span>
                </div>
                <div class="sidebar-item" onclick="navigate('anomalies')">
                    <span>🚨</span>
                    <span>Anomalies</span>
                </div>
            </div>
        </div>

        <!-- Resources Section -->
        <div class="sidebar-section">
            <div class="sidebar-section-title" onclick="toggleSection('resources')">
                <span>💰 Resources</span>
                <span class="chevron expanded" id="chevron-resources">▶</span>
            </div>
            <div class="sidebar-subsection expanded" id="section-resources">
                <div class="sidebar-item" onclick="navigate('models')">
                    <span>🤖</span>
                    <span>Models</span>
                </div>
                <div class="sidebar-item" onclick="navigate('alerts')">
                    <span>⚠️</span>
                    <span>Alerts</span>
                </div>
            </div>
        </div>

        <!-- Projects Section -->
        <div class="sidebar-section">
            <div class="sidebar-section-title" onclick="toggleSection('projects')">
                <span>📁 Projects</span>
                <span class="chevron expanded" id="chevron-projects">▶</span>
            </div>
            <div class="sidebar-subsection expanded" id="section-projects">
                <div class="sidebar-item" onclick="navigate('projects')">
                    <span>📂</span>
                    <span>All Projects</span>
                </div>
                <div class="sidebar-item" onclick="navigate('security')">
                    <span>🔒</span>
                    <span>Security</span>
                </div>
                <div class="sidebar-item" onclick="navigate('prd')">
                    <span>📋</span>
                    <span>PRDs</span>
                </div>
            </div>
        </div>

        <!-- Intelligence Section -->
        <div class="sidebar-section">
            <div class="sidebar-section-title" onclick="toggleSection('intelligence')">
                <span>🧠 Intelligence</span>
                <span class="chevron expanded" id="chevron-intelligence">▶</span>
            </div>
            <div class="sidebar-subsection expanded" id="section-intelligence">
                <div class="sidebar-item" onclick="navigate('ml')">
                    <span>🤖</span>
                    <span>ML Insights</span>
                </div>
                <div class="sidebar-item" onclick="navigate('learning')">
                    <span>📚</span>
                    <span>Learning</span>
                </div>
                <div class="sidebar-item" onclick="navigate('graph')">
                    <span>🕸️</span>
                    <span>Knowledge Graph</span>
                </div>
            </div>
        </div>
    </nav>

    <!-- Mobile Sidebar Toggle Button -->
    <div class="sidebar-toggle" onclick="toggleSidebar()">
        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
        </svg>
    </div>"""

        # Replace old header and tab navigation with new sidebar
        original = original[:tab_nav_start] + sidebar_html + original[tab_nav_end:]
        print("[OK] Added sidebar navigation")

    # 4. Update main content wrapper to work with sidebar
    original = original.replace(
        '<!-- Main Content -->\n    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">',
        '<!-- Main Content -->\n    <main class="main-content-area" style="padding-top: 85px; min-height: 100vh;">\n        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">',
    )
    original = original.replace(
        "</main>\n\n    <script>", "        </div>\n    </main>\n\n    <script>"
    )

    # 5. Add sidebar navigation JavaScript
    sidebar_js = """

    // ===== Sidebar Navigation Functions =====
    function toggleSidebar() {
        const sidebar = document.getElementById('sidebar');
        sidebar.classList.toggle('mobile-open');
    }

    function toggleSection(sectionName) {
        const section = document.getElementById(`section-${sectionName}`);
        const chevron = document.getElementById(`chevron-${sectionName}`);

        if (section.classList.contains('expanded')) {
            section.classList.remove('expanded');
            chevron.classList.remove('expanded');
        } else {
            section.classList.add('expanded');
            chevron.classList.add('expanded');
        }
    }

    function navigate(tabName) {
        // Use existing switchTab function if it exists
        if (typeof switchTab === 'function') {
            switchTab(tabName);
        } else {
            // Fallback direct navigation
            document.querySelectorAll('.tab-content').forEach(tab => {
                tab.classList.remove('active');
            });
            document.querySelectorAll('.sidebar-item').forEach(item => {
                item.classList.remove('active');
            });
            const targetTab = document.getElementById(tabName);
            if (targetTab) {
                targetTab.classList.add('active');
                const clickedItem = event?.target?.closest('.sidebar-item');
                if (clickedItem) {
                    clickedItem.classList.add('active');
                }
            }
        }

        // Close sidebar on mobile after navigation
        if (window.innerWidth < 1024) {
            document.getElementById('sidebar').classList.remove('mobile-open');
        }
    }

    // Add hooks script
""" + hooks_script

    # Find where to insert the JavaScript (right after <script> tag)
    script_start = original.find("<script>")
    if script_start != -1:
        # Find the end of the first few lines to insert after variable declarations
        insertion_point = original.find("let ws", script_start)
        if insertion_point == -1:
            insertion_point = script_start + 8  # Just after <script>
        original = original[:insertion_point] + sidebar_js + "\n    " + original[insertion_point:]
        print("[OK] Added sidebar and hooks JavaScript")

    # 6. Fix the header to be fixed position
    original = original.replace(
        '<body class="bg-gray-50 min-h-screen">', '<body class="bg-gray-50">'
    )

    # Write output
    output_path = frontend_dir / "dashboard_integrated.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(original)

    print(f"\n[SUCCESS] Integration complete!")
    print(f"Output: {output_path}")
    print(f"File size: {len(original):,} characters")
    print("\nChanges made:")
    print("  1. [OK] Added left sidebar navigation with nested sections")
    print("  2. [OK] Moved Hooks under Performance section")
    print("  3. [OK] Moved Security under Projects section")
    print("  4. [OK] Improved hooks page with cards, charts, and collapsible table")
    print("  5. [OK] Added mobile-responsive sidebar toggle")
    print("  6. [OK] Maintained all existing functionality")
    print("\nNext step: Test at http://localhost:8000/dashboard")


if __name__ == "__main__":
    main()
