#!/usr/bin/env python3
"""
HLL Match Scraper - Extrai dados de partidas de Hell Let Loose via CRCON API.

Uso:
  python3 hll_scraper.py <url> [--json] [--csv] [--output DIR]

  <url>  URL do jogo, ex: http://95.111.238.42:7012/games/152
         ou URL base do servidor, ex: http://95.111.238.42:7012
         ou game ID direto, ex: 152 (requer --base-url)

Opções:
  --json          Salva JSON bruto da API
  --csv           Exporta scoreboard como CSV
  --output DIR    Diretório de saída (default: /tmp)
  --base-url URL  URL base do servidor (default: auto-detectado da URL)
  --list          Lista partidas recentes (usa --limit e --page)
  --limit N       Número de partidas por página (default: 20)
  --page N        Página (default: 1)
  --live          Mostra stats do jogo atual em tempo real
"""

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse, urljoin

try:
    import urllib.request
except ImportError:
    print("Erro: urllib não disponível")
    sys.exit(1)


def fetch_json(url: str, timeout: int = 15) -> dict:
    """Fetch JSON from URL."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def extract_game_id(url: str) -> int | None:
    """Extract game ID from URL like /games/152 or /games/152/charts."""
    match = re.search(r"/games/(\d+)", url)
    if match:
        return int(match.group(1))
    return None


def detect_base_url(url: str) -> str:
    """Detect base URL from any subpath."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def format_duration(seconds: int) -> str:
    """Format seconds to H:MM:SS."""
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def fmt_datetime(iso_str: str) -> str:
    """Format ISO datetime to readable string."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("+00:00", ""))
        dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(timezone(timedelta(hours=-3)))  # BRT
        return local.strftime("%d/%m/%Y %H:%M BRT")
    except Exception:
        return iso_str


def print_match_summary(data: dict):
    """Print a formatted match summary."""
    g = data["result"]
    result = g["result"]

    # Duration
    try:
        start = datetime.fromisoformat(g["start"].replace("+00:00", ""))
        end = datetime.fromisoformat(g["end"].replace("+00:00", ""))
        duration_secs = int((end - start).total_seconds())
    except Exception:
        duration_secs = 0

    players = g.get("player_stats", [])
    allies = [p for p in players if p.get("team", {}).get("side") == "allies"]
    axis = [p for p in players if p.get("team", {}).get("side") == "axis"]

    map_info = g.get("map", {})
    map_pretty = map_info.get("pretty_name", g["map_name"].replace("_", " ").title())

    print(f"\n{'='*70}")
    print(f"  PARTIDA #{g['id']} — {map_pretty}")
    print(f"{'='*70}")
    print(f"  Servidor: #{g['server_number']}")
    print(f"  Início:   {fmt_datetime(g['start'])}")
    print(f"  Fim:      {fmt_datetime(g['end'])}")
    print(f"  Duração:  {format_duration(duration_secs)}")
    print(f"  Resultado: Aliados {result['allied']} x {result['axis']} Eixo")
    print(f"  Jogadores: {len(players)} ({len(allies)} aliados, {len(axis)} eixo)")
    print(f"  Setores: {', '.join(g.get('game_layout', {}).get('set', []))}")
    print(f"{'='*70}\n")

    # Scoreboard sorted by kills
    players_sorted = sorted(players, key=lambda p: p["kills"], reverse=True)
    print(f"{'#':<3} {'Jogador':<28} {'Time':<8} {'Lvl':<5} {'K':<5} {'D':<5} "
          f"{'K/D':<6} {'KPM':<5} {'Streak':<7} {'Tempo'}")
    print("-" * 100)
    for i, p in enumerate(players_sorted, 1):
        side = p.get("team", {}).get("side", "?")[:6]
        name = p["player"][:26]
        mins = p["time_seconds"] // 60
        print(f"{i:<3} {name:<28} {side:<8} {p.get('level', '?'):<5} "
              f"{p['kills']:<5} {p['deaths']:<5} {p['kill_death_ratio']:<6.1f} "
              f"{p['kills_per_minute']:<5.2f} {p['kills_streak']:<7} {mins}m")

    # Kill types summary
    print(f"\n--- Kills por Categoria ---")
    kill_types = {}
    for p in players:
        for kt, kv in p.get("kills_by_type", {}).items():
            kill_types[kt] = kill_types.get(kt, 0) + kv
    for kt in sorted(kill_types, key=kill_types.get, reverse=True):
        print(f"  {kt:<30} {kill_types[kt]}")

    # Team summaries
    for team_name, team_players in [("ALIADOS", allies), ("EIXO", axis)]:
        if not team_players:
            continue
        total_k = sum(p["kills"] for p in team_players)
        total_d = sum(p["deaths"] for p in team_players)
        total_tk = sum(p["teamkills"] for p in team_players)
        avg_kd = sum(p["kill_death_ratio"] for p in team_players) / len(team_players)
        print(f"\n  {team_name}: {total_k} kills, {total_d} deaths, "
              f"{total_tk} TKs, K/D médio: {avg_kd:.2f}")


def print_games_list(data: dict):
    """Print a list of recent games."""
    games = data.get("result", [])
    if isinstance(games, dict):
        games = games.get("maps", [])

    if not games:
        print("Nenhuma partida encontrada.")
        return

    print(f"\n{'ID':<6} {'Mapa':<35} {'Início':<22} {'Duração':<10} {'Resultado'}")
    print("-" * 90)
    for g in games:
        gid = g.get("id", "?")
        map_info = g.get("map", {})
        if isinstance(map_info, dict):
            map_name = map_info.get("pretty_name", "")
            if not map_name:
                inner = map_info.get("map", {})
                if isinstance(inner, dict):
                    map_name = inner.get("pretty_name", str(map_info))
                else:
                    map_name = str(map_info)
        elif isinstance(map_info, str):
            map_name = map_info.replace("_", " ").title()
        else:
            map_name = g.get("map_name", "?").replace("_", " ").title()
        start = fmt_datetime(g.get("start", ""))

        try:
            s = datetime.fromisoformat(g["start"].replace("+00:00", ""))
            e = datetime.fromisoformat(g["end"].replace("+00:00", ""))
            dur = format_duration(int((e - s).total_seconds()))
        except Exception:
            dur = "?"

        result = g.get("result", {})
        score = f"{result.get('allied', '?')} x {result.get('axis', '?')}"
        print(f"{gid:<6} {map_name:<35} {start:<22} {dur:<10} {score}")


def print_live_stats(data: dict):
    """Print live game stats."""
    r = data.get("result", {})
    current = r.get("current_map", {})
    score = r.get("score", {})
    server_name = r.get("name", {}).get("name", "?")

    map_info = current.get("map", {})
    map_name = map_info.get("pretty_name", "?")

    print(f"\n{'='*50}")
    print(f"  SERVIDOR: {server_name}")
    print(f"  Mapa atual: {map_name}")
    print(f"  Placar: Aliados {score.get('allied', 0)} x {score.get('axis', 0)} Eixo")
    print(f"  Jogadores: {r.get('player_count', 0)}/{r.get('max_player_count', 100)}")
    print(f"{'='*50}")


def export_all_csv(data: dict, out_dir: Path, game_id: int):
    """Export 6 focused CSVs from match data."""
    g = data["result"]
    players = g.get("player_stats", [])
    allies = [p for p in players if p.get("team", {}).get("side") == "allies"]
    axis = [p for p in players if p.get("team", {}).get("side") == "axis"]
    prefix = f"hll_match_{game_id}"

    # --- 1. overview.csv (1 row = the match) ---
    try:
        s = datetime.fromisoformat(g["start"].replace("+00:00", ""))
        e = datetime.fromisoformat(g["end"].replace("+00:00", ""))
        dur = round((e - s).total_seconds() / 60)
    except Exception:
        dur = 0

    ak = sum(p["kills"] for p in allies)
    xk = sum(p["kills"] for p in axis)
    ad = sum(p["deaths"] for p in allies)
    xd = sum(p["deaths"] for p in axis)
    atk = sum(p["teamkills"] for p in allies)
    xtk = sum(p["teamkills"] for p in axis)

    fp = out_dir / f"{prefix}_overview.csv"
    with open(fp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["game_id", "map", "mode", "start", "end", "duration_min",
                     "server", "allied_score", "axis_score", "total_players",
                     "allies_count", "axis_count", "allied_kills", "axis_kills",
                     "allied_deaths", "axis_deaths", "allied_tk", "axis_tk"])
        w.writerow([g["id"], g["map_name"], g.get("map", {}).get("game_mode", ""),
                     g["start"], g["end"], dur, g["server_number"],
                     g["result"]["allied"], g["result"]["axis"],
                     len(players), len(allies), len(axis),
                     ak, xk, ad, xd, atk, xtk])
    print(f"  {fp.name}")

    # --- 2. scoreboard.csv (1 row = 1 player, with kills/deaths by type) ---
    kill_types = sorted(set(kt for p in players for kt in p.get("kills_by_type", {})))
    death_types = sorted(set(dt for p in players for dt in p.get("deaths_by_type", {})))
    fields = ["player", "player_id", "team", "level", "kills", "deaths", "kd", "kpm",
              "kills_streak", "time_min", "combat", "offense", "defense", "support",
              "teamkills", "deaths_by_tk"]
    fields += [f"kills_{t}" for t in kill_types]
    fields += [f"deaths_{t}" for t in death_types]

    fp = out_dir / f"{prefix}_scoreboard.csv"
    with open(fp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for p in sorted(players, key=lambda x: x["kills"], reverse=True):
            row = {
                "player": p["player"], "player_id": p["player_id"],
                "team": p.get("team", {}).get("side", "?"),
                "level": p.get("level", ""), "kills": p["kills"],
                "deaths": p["deaths"], "kd": round(p["kill_death_ratio"], 2),
                "kpm": round(p["kills_per_minute"], 2),
                "kills_streak": p["kills_streak"],
                "time_min": round(p["time_seconds"] / 60),
                "combat": p["combat"], "offense": p["offense"],
                "defense": p["defense"], "support": p["support"],
                "teamkills": p["teamkills"], "deaths_by_tk": p["deaths_by_tk"],
            }
            for t in kill_types:
                row[f"kills_{t}"] = p.get("kills_by_type", {}).get(t, 0)
            for t in death_types:
                row[f"deaths_{t}"] = p.get("deaths_by_type", {}).get(t, 0)
            w.writerow(row)
    print(f"  {fp.name}")

    # --- 3. weapons.csv (1 row = 1 player + 1 weapon) ---
    fp = out_dir / f"{prefix}_weapons.csv"
    with open(fp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["player", "team", "weapon", "kills"])
        for p in sorted(players, key=lambda x: x["kills"], reverse=True):
            for weapon, kills in sorted(p.get("weapons", {}).items(), key=lambda x: -x[1]):
                w.writerow([p["player"], p.get("team", {}).get("side", "?"), weapon, kills])
    print(f"  {fp.name}")

    # --- 4. teams.csv (1 row = 1 team) ---
    fp = out_dir / f"{prefix}_teams.csv"
    with open(fp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["team", "players", "kills", "deaths", "avg_kd", "teamkills",
                     "combat", "offense", "defense", "support"])
        for side, group in [("allies", allies), ("axis", axis)]:
            if not group:
                continue
            w.writerow([side, len(group),
                        sum(p["kills"] for p in group),
                        sum(p["deaths"] for p in group),
                        round(sum(p["kill_death_ratio"] for p in group) / len(group), 2),
                        sum(p["teamkills"] for p in group),
                        sum(p["combat"] for p in group),
                        sum(p["offense"] for p in group),
                        sum(p["defense"] for p in group),
                        sum(p["support"] for p in group)])
    print(f"  {fp.name}")

    # --- 5. classes.csv (kills by type per team — "classes" from charts page) ---
    all_types = sorted(
        set(kt for p in players for kt in p.get("kills_by_type", {})),
        key=lambda t: -sum(p.get("kills_by_type", {}).get(t, 0) for p in players)
    )
    fp = out_dir / f"{prefix}_classes.csv"
    with open(fp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["kill_type", "allies_kills", "axis_kills", "total"])
        for t in all_types:
            ak_t = sum(p.get("kills_by_type", {}).get(t, 0) for p in allies)
            xk_t = sum(p.get("kills_by_type", {}).get(t, 0) for p in axis)
            w.writerow([t, ak_t, xk_t, ak_t + xk_t])
    print(f"  {fp.name}")

    # --- 6. nemeses.csv (who each player kills most / dies to most) ---
    fp = out_dir / f"{prefix}_nemeses.csv"
    with open(fp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["player", "team", "killed_most", "times", "killed_by_most", "times_by"])
        for p in sorted(players, key=lambda x: x["kills"], reverse=True):
            mk = p.get("most_killed", {})
            db = p.get("death_by", {})
            top_killed = max(mk.items(), key=lambda x: x[1]) if mk else ("", 0)
            top_death = max(db.items(), key=lambda x: x[1]) if db else ("", 0)
            w.writerow([p["player"], p.get("team", {}).get("side", "?"),
                        top_killed[0], top_killed[1],
                        top_death[0], top_death[1]])
    print(f"  {fp.name}")


def main():
    parser = argparse.ArgumentParser(description="HLL Match Scraper via CRCON API")
    parser.add_argument("url", nargs="?", help="URL do jogo ou ID")
    parser.add_argument("--json", action="store_true", help="Salvar JSON bruto")
    parser.add_argument("--csv", action="store_true", help="Exportar CSV")
    parser.add_argument("--output", default="/tmp", help="Diretório de saída")
    parser.add_argument("--base-url", help="URL base do servidor CRCON")
    parser.add_argument("--list", action="store_true", help="Listar partidas recentes")
    parser.add_argument("--limit", type=int, default=20, help="Limite por página")
    parser.add_argument("--page", type=int, default=1, help="Página")
    parser.add_argument("--live", action="store_true", help="Stats em tempo real")
    args = parser.parse_args()

    if not args.url and not args.list and not args.live:
        parser.print_help()
        sys.exit(1)

    # Detect base URL
    if args.url and args.url.startswith("http"):
        base_url = args.base_url or detect_base_url(args.url)
        game_id = extract_game_id(args.url)
    elif args.url and args.url.isdigit():
        game_id = int(args.url)
        base_url = args.base_url or "http://95.111.238.42:7012"
    else:
        game_id = None
        base_url = args.base_url or "http://95.111.238.42:7012"

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        if args.live:
            print("Buscando stats em tempo real...")
            data = fetch_json(f"{base_url}/api/get_public_info")
            print_live_stats(data)
            if args.json:
                fpath = out_dir / "hll_live.json"
                fpath.write_text(json.dumps(data, indent=2, ensure_ascii=False))
                print(f"JSON salvo: {fpath}")

        elif args.list:
            print(f"Listando partidas (página {args.page}, limite {args.limit})...")
            data = fetch_json(
                f"{base_url}/api/get_scoreboard_maps?limit={args.limit}&page={args.page}"
            )
            print_games_list(data)
            if args.json:
                fpath = out_dir / f"hll_games_p{args.page}.json"
                fpath.write_text(json.dumps(data, indent=2, ensure_ascii=False))
                print(f"JSON salvo: {fpath}")

        elif game_id:
            print(f"Buscando partida #{game_id}...")
            data = fetch_json(f"{base_url}/api/get_map_scoreboard?map_id={game_id}")
            print_match_summary(data)

            if args.json:
                fpath = out_dir / f"hll_game_{game_id}.json"
                fpath.write_text(json.dumps(data, indent=2, ensure_ascii=False))
                print(f"JSON salvo: {fpath}")

            if args.csv:
                print(f"\nExportando CSVs para {out_dir}/:")
                export_all_csv(data, out_dir, game_id)

        else:
            print("Erro: Não foi possível detectar o game ID da URL.")
            print("Use formato: http://host:port/games/ID ou forneça --list ou --live")
            sys.exit(1)

    except urllib.error.HTTPError as e:
        print(f"Erro HTTP {e.code}: {e.reason}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Erro de conexão: {e.reason}")
        sys.exit(1)
    except json.JSONDecodeError:
        print("Erro: Resposta não é JSON válido")
        sys.exit(1)


if __name__ == "__main__":
    main()
