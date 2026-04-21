---
description: Rules for multiplayer/networking code — RPCs, replication, server authority
globs:
  - "**/scripts/networking/**"
  - "**/scripts/multiplayer/**"
  - "**/scripts/net/**"
  - "**/scripts/network/**"
  - "**/scripts/online/**"
  - "**/networking/**/*.gd"
  - "**/multiplayer/**/*.gd"
  - "**/src/networking/**"
  - "**/src/multiplayer/**"
  - "**/src/net/**"
---

# Networking Code Rules

## Authority Model
- Server-authoritative for all game state. Clients send inputs via RPC; server validates and applies.
- Never trust client-sent state (position, health, inventory). Validate server-side.
- Use `@rpc("any_peer", "call_remote", "reliable")` for input RPCs, `@rpc("authority", "call_local", "unreliable")` for state sync.

## Message Design
- Keep RPC payloads small: IDs and deltas, not full objects.
- Version your network messages if the game will be updated post-launch.
- Batch frequent updates (position sync) into ticks, don't send per-frame.

## Robustness
- Handle disconnect at every point: mid-RPC, mid-sync, mid-handshake.
- Implement reconnection logic — don't assume persistent connections.
- Test with simulated latency (200ms+) and packet loss (5%+).

## Security
- Rate-limit RPCs per peer — a client flooding the server is a DoS.
- Sanitize all string data from peers (player names, chat).
- Never expose server-only state (other players' hidden info, fog-of-war data) in RPCs to unauthorized peers.

## Godot Specifics
- Use MultiplayerAPI with ENet transport for most games.
- `multiplayer.get_unique_id()` for peer identification.
- `multiplayer.is_server()` guards for server-only logic.
- MultiplayerSpawner + MultiplayerSynchronizer for scene replication.
