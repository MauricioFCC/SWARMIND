#!/usr/bin/env python3
"""
Codegen — Generacion rapida de codigo boilerplate para stacks comunes.

Reduce el tiempo de escritura de codigo repetitivo en Rust, Go, Python, TypeScript.
NO es un generador completo, es una herramienta TEMPORAL para prototipado rapido.

Uso:
    python harness/scripts/codegen.py rust-cli --name mytool
    python harness/scripts/codegen.py go-api --name users --dir ./api
    python harness/scripts/codegen.py python-fastapi --name orders
    python harness/scripts/codegen.py ts-react --name dashboard
    python harness/scripts/codegen.py list                          # Listar templates
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

TEMPLATES: Dict[str, Dict] = {
    "rust-cli": {
        "desc": "Rust CLI tool with clap",
        "ext": "rs",
        "files": {
            "src/main.rs": """use clap::Parser;

#[derive(Parser)]
#[command(name = "{name}", version = "0.1.0", about = "{description}")]
struct Cli {{
    /// Input file
    #[arg(short, long)]
    input: Option<String>,

    /// Verbose output
    #[arg(short, long, action = clap::ArgAction::Count)]
    verbose: u8,
}}

fn main() {{
    let cli = Cli::parse();
    println!("{name} v0.1.0");
    if let Some(input) = cli.input {{
        println!("Processing: {{}}", input);
    }}
}}
""",
            "Cargo.toml": """[package]
name = "{name}"
version = "0.1.0"
edition = "2021"

[dependencies]
clap = {{ version = "4", features = ["derive"] }}
""",
        },
    },
    "go-api": {
        "desc": "Go HTTP API with standard library",
        "ext": "go",
        "files": {
            "main.go": """package main

import (
    "encoding/json"
    "log"
    "net/http"
    "os"
)

type {Name} struct {{
    ID   string `json:"id"`
    Name string `json:"name"`
}}

var items = []{Name}{{}}

func main() {{
    port := os.Getenv("PORT")
    if port == "" {{
        port = "8080"
    }}

    http.HandleFunc("GET /api/{name}", handleList)
    http.HandleFunc("POST /api/{name}", handleCreate)

    log.Printf("{name} API listening on :%s", port)
    log.Fatal(http.ListenAndServe(":"+port, nil))
}}

func handleList(w http.ResponseWriter, r *http.Request) {{
    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(items)
}}

func handleCreate(w http.ResponseWriter, r *http.Request) {{
    var item {Name}
    if err := json.NewDecoder(r.Body).Decode(&item); err != nil {{
        http.Error(w, err.Error(), http.StatusBadRequest)
        return
    }}
    items = append(items, item)
    w.WriteHeader(http.StatusCreated)
    json.NewEncoder(w).Encode(item)
}}
""",
            "go.mod": "module {name}\n\ngo 1.22\n",
        },
    },
    "python-fastapi": {
        "desc": "Python FastAPI with Pydantic",
        "ext": "py",
        "files": {
            "main.py": """from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

app = FastAPI(title="{title}", version="0.1.0")


class {Name}Base(BaseModel):
    name: str
    description: Optional[str] = None


class {Name}Create({Name}Base):
    pass


class {Name}({Name}Base):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


_items: List[dict] = []
_counter: int = 0


@app.get("/api/{name}", response_model=List[{Name}])
def list_items():
    return [{Name}(**item) for item in _items]


@app.post("/api/{name}", response_model={Name}, status_code=201)
def create_item(item: {Name}Create):
    global _counter
    _counter += 1
    new = {{"id": _counter, **item.model_dump(), "created_at": datetime.utcnow()}}
    _items.append(new)
    return {Name}(**new)


@app.get("/api/{name}/{{item_id}}", response_model={Name})
def get_item(item_id: int):
    for item in _items:
        if item["id"] == item_id:
            return {Name}(**item)
    raise HTTPException(404, "Item not found")
""",
            "requirements.txt": "fastapi\nuvicorn\npydantic\n",
        },
    },
    "ts-react": {
        "desc": "TypeScript React component",
        "ext": "tsx",
        "files": {
            "{name}.tsx": """import React, {{ useState, useEffect }} from 'react';

interface {Name}Props {{
    title?: string;
}}

interface {Name}Item {{
    id: number;
    name: string;
}}

export const {Name}: React.FC<{Name}Props> = ({{ title = "{title}" }}) => {{
    const [items, setItems] = useState<{Name}Item[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {{
        fetchItems();
    }}, []);

    const fetchItems = async () => {{
        try {{
            const res = await fetch('/api/{name}');
            const data = await res.json();
            setItems(data);
        }} catch (err) {{
            console.error('Failed to fetch:', err);
        }} finally {{
            setLoading(false);
        }}
    }};

    if (loading) return <div>Loading...</div>;

    return (
        <div className="{name}-container">
            <h2>{{title}}</h2>
            <ul>
                {{items.map(item => (
                    <li key={{item.id}}>{{item.name}}</li>
                ))}}
            </ul>
        </div>
    );
}};

export default {Name};
""",
        },
    },
}


def cmd_list() -> None:
    """List available templates."""
    print("Available templates:")
    for name, tmpl in sorted(TEMPLATES.items()):
        print("  %-20s %s" % (name, tmpl["desc"]))


def cmd_generate(args: argparse.Namespace) -> None:
    """Generate code from template."""
    template_name = args.template
    if template_name not in TEMPLATES:
        logger.error("Unknown template '%s'. Use 'list' to see available.", template_name)
        sys.exit(1)

    tmpl = TEMPLATES[template_name]
    name = args.name or "example"
    out_dir = Path(args.dir or name)

    # Convert name variants
    Name = name[0].upper() + name[1:] if name else "Example"
    title = args.title or Name

    out_dir.mkdir(parents=True, exist_ok=True)

    generated = 0
    for relpath, content in tmpl["files"].items():
        filepath = out_dir / relpath.format(name=name, Name=Name, title=title, description=args.description or Name)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        formatted = content.format(
            name=name.lower(),
            Name=Name,
            title=title,
            description=args.description or Name,
        )

        filepath.write_text(formatted)
        generated += 1
        logger.info("  Created %s", filepath)

    logger.info("Generated %d files for '%s' in %s/", generated, template_name, out_dir)


def main():
    parser = argparse.ArgumentParser(description="Codegen — quick boilerplate generation")
    parser.add_argument("template", nargs="?", help="Template name (rust-cli, go-api, python-fastapi, ts-react)")
    parser.add_argument("--name", "-n", default="example", help="Project/component name")
    parser.add_argument("--title", "-t", help="Display title (default: same as name)")
    parser.add_argument("--description", "-d", default="", help="Description")
    parser.add_argument("--dir", help="Output directory (default: ./<name>)")

    args = parser.parse_args()

    if not args.template or args.template == "list":
        cmd_list()
        return

    cmd_generate(args)


if __name__ == "__main__":
    main()
