---
name: hll-match-scraper
description: "Extrai dados completos de partidas de Hell Let Loose (HLL) via CRCON API a partir de uma URL. Inclui scoreboard, kills por tipo, armas, times, e estatísticas detalhadas por jogador."
category: data-extraction
risk: safe
source: community
tags: "[hll, hell-let-loose, crcon, game-stats, scraper]"
date_added: "2026-04-13"
---

# hll-match-scraper

## Purpose

Extrair dados completos de partidas de Hell Let Loose (HLL) de servidores que usam CRCON (Community RCON). A partir de uma URL de jogo, obtém via API REST todos os dados da partida: scoreboard completo, kills por tipo, armas usadas, nemeses, times, scores de combate/ofensiva/defesa/suporte.

## When to Use This Skill

- O usuário fornece uma URL de partida HLL (ex: `http://host:7012/games/152`)
- O usuário pede para extrair/analyzar dados de uma partida de HLL
- O usuário menciona "CRCON", "HLL stats", "scoreboard", "Hell Let Loose"
- O usuário quer comparar jogadores, times ou performance em partidas

## CRCON API Endpoints

O servidor CRCON expõe uma API REST pública (quando `lock_stats_api = false`):

| Endpoint                                  | Descrição                      |
| ----------------------------------------- | ------------------------------ |
| `/api/get_map_scoreboard?map_id=N`        | Dados completos de uma partida |
| `/api/get_scoreboard_maps?limit=N&page=N` | Lista de partidas              |
| `/api/get_public_info`                    | Estado atual do servidor       |
| `/api/get_live_game_stats`                | Stats em tempo real            |
| `/api/get_live_scoreboard`                | Scoreboard ao vivo             |

Resposta de `get_map_scoreboard` contém por jogador:

- kills, deaths, K/D, kills_per_minute, kills_streak
- kills_by_type (infantry, armor, sniper, machine_gun, etc.)
- weapons (dict arma → kills), death_by_weapons
- most_killed, death_by (nêmeses)
- combat, offense, defense, support (scores)
- team (side/confidence/ratio), level, time_seconds

## Step 1: Parse the URL

Extract the game ID and base URL from the user-provided link.

```
URL patterns:
  http://host:port/games/152        → game_id=152, base_url=http://host:port
  http://host:port/games/152/charts → game_id=152, base_url=http://host:port
  http://host:port                  → no game_id, use --list or --live
```

Use the helper script:

```bash
python3 /home/ozp/clawd/skills/hll-match-scraper/scripts/hll_scraper.py "<URL>"
```

Or directly via curl:

```bash
curl -s "<BASE_URL>/api/get_map_scoreboard?map_id=<ID>" | python3 -m json.tool
```

## Step 2: Fetch Match Data

Run the scraper script with the URL:

```bash
# Match details + formatted output
python3 ~/clawd/skills/hll-match-scraper/scripts/hll_scraper.py "http://95.111.238.42:7012/games/152"

# Also save JSON
python3 ~/clawd/skills/hll-match-scraper/scripts/hll_scraper.py "http://95.111.238.42:7012/games/152" --json

# Also export CSV
python3 ~/clawd/skills/hll-match-scraper/scripts/hll_scraper.py "http://95.111.238.42:7012/games/152" --csv

# List recent games
python3 ~/clawd/skills/hll-match-scraper/scripts/hll_scraper.py --list --base-url "http://95.111.238.42:7012"

# Live stats
python3 ~/clawd/skills/hll-match-scraper/scripts/hll_scraper.py --live --base-url "http://95.111.238.42:7012"
```

## CSV Exports (`--csv`)

When `--csv` is passed, the script generates 6 focused CSV files:

| File | Rows | Description |
|------|------|-------------|
| `hll_match_{ID}_overview.csv` | 1 | Match summary: map, score, duration, totals |
| `hll_match_{ID}_teams.csv` | 2 | Team-level: kills, deaths, avg K/D, scores |
| `hll_match_{ID}_classes.csv` | ~9 | Kills by type per team (infantry, MG, armor, sniper, etc.) |
| `hll_match_{ID}_scoreboard.csv` | 75 | Full player stats with kills/deaths by type columns |
| `hll_match_{ID}_weapons.csv` | ~200 | Player + weapon + kills (granular weapon breakdown) |
| `hll_match_{ID}_nemeses.csv` | 75 | Each player's most killed victim and most frequent killer |

### Scoreboard CSV columns (34 total)

`player`, `player_id`, `team`, `level`, `kills`, `deaths`, `kd`, `kpm`,
`kills_streak`, `time_min`, `combat`, `offense`, `defense`, `support`,
`teamkills`, `deaths_by_tk`, `kills_infantry`, `kills_machine_gun`,
`kills_armor`, `kills_sniper`, `kills_commander`, `kills_grenade`,
`kills_bazooka`, `kills_self_propelled_artillery`, `kills_pak`,
`deaths_infantry`, `deaths_machine_gun`, `deaths_armor`, `deaths_sniper`,
`deaths_commander`, `deaths_grenade`, `deaths_bazooka`,
`deaths_self_propelled_artillery`, `deaths_pak`

### Classes CSV — maps to charts page categories

The `kill_type` column maps to the "Kills by type" chart on the `/charts` page:
`infantry`, `machine_gun`, `armor`, `sniper`, `commander`, `grenade`,
`bazooka`, `self_propelled_artillery`, `pak`

## Step 3: Present Results

Present the data to the user in a clear format:

1. Match summary (map, duration, score, sectors)
2. Top players table (sorted by kills)
3. Kill type breakdown
4. Team summaries (kills, deaths, TKs, avg K/D)
5. Notable highlights (highest streak, best K/D, top weapons)

## Step 4: Advanced Analysis (optional)

If the user wants deeper analysis, use the JSON data to:

- Compare two players head-to-head
- Show weapon usage distribution
- Analyze nêmesis relationships (most_killed / death_by)
- Team balance analysis
- Score breakdown (combat vs offense vs defense vs support)

## Script Location

```
/home/ozp/clawd/skills/hll-match-scraper/scripts/hll_scraper.py
```

Self-contained Python 3 script (stdlib only, no pip dependencies).

## Notes

- CRCON is the standard RCON tool for HLL community servers (GitHub: MarechJ/hll_rcon_tool)
- API works without authentication when stats are unlocked on the server
- All endpoints return JSON with structure: `{"result": ..., "command": "...", "failed": false}`
- Player IDs are Steam64 IDs (7656119...)
- Times are UTC in ISO format
