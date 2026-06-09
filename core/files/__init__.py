"""files — versioned artifact store backed by files.db (SQLite).

files.db is NEVER-AUTHORITY: no canonical events, no gate decisions originate here.
It is a write-forward blob store for handoffs, evidence, release bundles, and exports.
"""
