#!/usr/bin/env python3
"""
capture.py — Captura rápida de links, itens e ideias como tasks.

Preserva o texto original verbatim. Nenhum link ou item é perdido.
Quando encontrar URLs, pode também registrá-las no Karakeep e gravar
`note:: karakeep:BOOKMARK_ID` na task criada.

Uso:
  python3 capture.py "https://github.com/foo/bar - descrição"
  python3 capture.py "ideia ou nota" --area agents --priority medium
  python3 capture.py "link ou texto" --note "contexto adicional"
  python3 capture.py --batch arquivo.txt   # um item por linha
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

TASKS_SCRIPT = Path(__file__).parent / "tasks.py"
KARAKEEP_SCRIPT = Path(__file__).parent / "karakeep.py"
URL_PATTERN = re.compile(r"https?://[^\s]+")


def detect_area(text: str) -> str:
    """Sugere area baseado no conteúdo (pode ser sobrescrito pelo usuário)."""
    t = text.lower()
    if "github.com" in t:
        return "triage"
    if any(k in t for k in ["arxiv", "revistas.usp", "artigo", "paper", "psicologia"]):
        return "bibliography"
    if any(k in t for k in ["backup", "segurança", "security"]):
        return "backup"
    if any(k in t for k in ["mcp", "tool", "skill", "plugin"]):
        return "triage"
    if any(k in t for k in ["agente", "agent", "orchestr"]):
        return "agents"
    if any(k in t for k in ["model", "llm", "glm", "gpt", "qwen"]):
        return "models"
    return "inbox"


def extract_urls(text: str) -> list[str]:
    return URL_PATTERN.findall(text)


def slugify_task_ref(text: str) -> str:
    slug = re.sub(r"https?://\S+", "", text)
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", slug).strip("-").lower()
    return slug[:80] if slug else "captured-item"


def karakeep_list_name_for_area(area: str) -> str:
    return area.strip().lower().replace("_", "-").replace(" ", "-")


def run_json(cmd: list[str]) -> tuple[bool, dict | None, str]:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return False, None, result.stderr.strip() or result.stdout.strip()
    try:
        return True, json.loads(result.stdout), ""
    except json.JSONDecodeError as exc:
        return False, None, f"JSON decode error: {exc}"


def ensure_karakeep_list(list_name: str) -> str | None:
    ok, data, error = run_json([sys.executable, str(KARAKEEP_SCRIPT), "list-lists"])
    if not ok or not isinstance(data, dict) or not isinstance(data.get("lists"), list):
        print(f"⚠️ Karakeep: não foi possível listar listas ({error})")
        return None

    for item in data["lists"]:
        if item.get("name", "").strip().lower() == list_name.lower():
            return item.get("id")

    ok, created, error = run_json([
        sys.executable,
        str(KARAKEEP_SCRIPT),
        "create-list",
        list_name,
        "--icon",
        "📌",
    ])
    if not ok or not isinstance(created, dict):
        print(f"⚠️ Karakeep: não foi possível criar lista '{list_name}' ({error})")
        return None
    return created.get("id")


def attach_task_ref_to_bookmark(bookmark_id: str, task_ref: str) -> None:
    get_ok, bookmark, get_error = run_json([
        sys.executable,
        str(KARAKEEP_SCRIPT),
        "get-bookmark",
        bookmark_id,
    ])
    if not get_ok or not isinstance(bookmark, dict):
        print(f"⚠️ Karakeep: falha ao ler bookmark para atualizar note ({get_error})")
        return

    current_note = (bookmark.get("note") or "").strip()
    if task_ref in current_note:
        return

    merged_note = f"{current_note}\n\n{task_ref}".strip() if current_note else task_ref
    update_ok, _, update_error = run_json([
        sys.executable,
        str(KARAKEEP_SCRIPT),
        "update-note",
        bookmark_id,
        "--note",
        merged_note,
    ])
    if not update_ok:
        print(f"⚠️ Karakeep: falha ao atualizar note ({update_error})")


def save_url_to_karakeep(url: str, line: str, area: str) -> tuple[str | None, bool]:
    task_ref = f"task-ref: Work Tasks.md#{slugify_task_ref(line)}"
    ok, data, error = run_json([
        sys.executable,
        str(KARAKEEP_SCRIPT),
        "save-url",
        url,
        "--note",
        task_ref,
    ])
    if not ok or not isinstance(data, dict):
        print(f"⚠️ Karakeep: falha ao salvar URL ({url}) ({error})")
        return None, False

    bookmark_id = data.get("id")
    if not bookmark_id:
        print(f"⚠️ Karakeep: resposta sem bookmark id para {url}")
        return None, False

    already_exists = bool(data.get("alreadyExists"))

    if not already_exists:
        attach_task_ref_to_bookmark(bookmark_id, task_ref)

    if not already_exists:
        list_id = ensure_karakeep_list(karakeep_list_name_for_area(area))
        if list_id:
            assign_ok, _, assign_error = run_json([
                sys.executable,
                str(KARAKEEP_SCRIPT),
                "assign-list",
                bookmark_id,
                list_id,
            ])
            if not assign_ok:
                print(f"⚠️ Karakeep: falha ao associar lista ({assign_error})")

        tag_values = []
        if "github.com" in url:
            tag_values.append("github-repo")
        elif any(host in url for host in ["arxiv.org", "revistas.usp", "doi.org"]):
            tag_values.append("paper")
        else:
            tag_values.append("link")

        add_tags_ok, _, add_tags_error = run_json([
            sys.executable,
            str(KARAKEEP_SCRIPT),
            "add-tags",
            bookmark_id,
            "--tags",
            ",".join(tag_values),
        ])
        if not add_tags_ok:
            print(f"⚠️ Karakeep: falha ao adicionar tags ({add_tags_error})")

    return bookmark_id, already_exists


def add_task(text: str, area: str, priority: str, note: str | None, note_meta: list[str] | None = None) -> bool:
    """Adiciona uma task preservando o texto verbatim."""
    title = text.strip()
    if note:
        title = f"{title} — {note.strip()}"

    cmd = [
        sys.executable, str(TASKS_SCRIPT),
        "add", title,
        "--priority", priority,
        "--area", area,
    ]

    for meta in note_meta or []:
        cmd.extend(["--note-meta", meta])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✅ Capturado [{area}]: {title[:80]}{'...' if len(title) > 80 else ''}")
        return True
    else:
        print(f"❌ Erro ao capturar: {result.stderr.strip()}")
        print(f"   Tentou: {title[:80]}")
        return False


def process_line(
    line: str,
    area_override: str | None,
    priority: str,
    note: str | None,
    karakeep_enabled: bool,
) -> bool:
    """Processa uma linha/item."""
    line = line.strip()
    if not line or line.startswith("#"):
        return True  # skip vazios e comentários

    area = area_override if area_override else detect_area(line)
    note_meta: list[str] = []

    if karakeep_enabled:
        urls = extract_urls(line)
        if urls:
            task_ref = f"task-ref: Work Tasks.md#{slugify_task_ref(line)}"
            existing_bookmark_ids: list[str] = []
            new_bookmark_seen = False

            for url in urls:
                bookmark_id, already_exists = save_url_to_karakeep(url, line, area)
                if not bookmark_id:
                    continue
                note_meta.append(f"karakeep:{bookmark_id}")
                if already_exists:
                    existing_bookmark_ids.append(bookmark_id)
                else:
                    new_bookmark_seen = True

            if note_meta and not new_bookmark_seen:
                bookmark_list = ", ".join(meta.removeprefix("karakeep:") for meta in note_meta)
                print(
                    f"ℹ️ Karakeep: todas as URLs já existiam ({bookmark_list}); task duplicada não será criada."
                )
                return True

            if new_bookmark_seen:
                for bookmark_id in existing_bookmark_ids:
                    attach_task_ref_to_bookmark(bookmark_id, task_ref)

    return add_task(line, area, priority, note, note_meta=note_meta)


def main():
    parser = argparse.ArgumentParser(
        description="Captura rápida de links, itens e ideias como tasks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("text", nargs="?", help="Texto, link ou ideia a capturar")
    parser.add_argument("--area", "-a", help="Area (padrão: auto-detectado)")
    parser.add_argument(
        "--priority", "-p",
        choices=["high", "medium", "low"],
        default="low",
        help="Prioridade (padrão: low → Backlog)",
    )
    parser.add_argument("--note", "-n", help="Nota/contexto adicional")
    parser.add_argument(
        "--batch", "-b",
        type=Path,
        help="Arquivo com um item por linha",
    )
    parser.add_argument(
        "--no-karakeep",
        action="store_true",
        help="Não enviar URLs para o Karakeep",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostrar o que seria adicionado sem adicionar",
    )

    args = parser.parse_args()
    karakeep_enabled = not args.no_karakeep

    if not args.text and not args.batch:
        if not sys.stdin.isatty():
            lines = sys.stdin.read().strip().splitlines()
            ok = all(
                process_line(l, args.area, args.priority, args.note, karakeep_enabled)
                for l in lines if l.strip()
            )
            sys.exit(0 if ok else 1)
        parser.print_help()
        sys.exit(1)

    if args.dry_run:
        area = args.area or detect_area(args.text or "")
        urls = extract_urls(args.text or "")
        print(f"[DRY-RUN] Adicionaria: {args.text}")
        print(f"           area={area}, priority={args.priority}")
        print(f"           karakeep_enabled={karakeep_enabled}, urls={urls}")
        if args.note:
            print(f"           note={args.note}")
        sys.exit(0)

    if args.batch:
        if not args.batch.exists():
            print(f"❌ Arquivo não encontrado: {args.batch}")
            sys.exit(1)
        lines = args.batch.read_text().splitlines()
        results = [
            process_line(l, args.area, args.priority, args.note, karakeep_enabled)
            for l in lines
        ]
        ok_count = sum(results)
        print(f"\n📋 {ok_count}/{len([l for l in lines if l.strip()])} itens capturados.")
        sys.exit(0 if all(results) else 1)

    ok = process_line(args.text, args.area, args.priority, args.note, karakeep_enabled)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
