# v_agent/tools/__init__.py
import re
from pathlib import Path

from .base import run_bash, run_read, run_write, run_edit, run_list_dir
from .http import run_http_request


class SkillLoader:
    def __init__(self, skills_dir: Path):
        self.skills = {}
        if skills_dir.exists():
            for f in sorted(skills_dir.rglob("*.md")):
                text = f.read_text()
                match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
                meta, body = {}, text
                if match:
                    for line in match.group(1).strip().splitlines():
                        if ":" in line:
                            k, v = line.split(":", 1)
                            meta[k.strip()] = v.strip()
                    body = match.group(2).strip()
                name = meta.get("name", f.stem)
                self.skills[name] = {"meta": meta, "body": body}

    def descriptions(self) -> str:
        if not self.skills:
            return "(no skills available)"
        return "\n".join(f"  - {n}: {s['meta'].get('description', '-')}"
                         for n, s in self.skills.items())

    def load(self, name: str) -> str:
        s = self.skills.get(name)
        if not s:
            return f"Error: Unknown skill '{name}'. Available: {', '.join(self.skills.keys())}"
        return f"<skill name=\"{name}\">\n{s['body']}\n</skill>"

    def list_names(self) -> list:
        return list(self.skills.keys())

TOOL_HANDLERS = {
    "bash":       lambda **kw: run_bash(kw["command"]),
    "read_file":  lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file":  lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    "list_dir":   lambda **kw: run_list_dir(kw.get("path", ".")),
    "http_request": lambda **kw: run_http_request(
        kw["method"], kw["url"], kw.get("headers"), kw.get("body"), kw.get("timeout", 30)
    ),
}

TOOLS = [
    {"name": "bash", "description": "Run a shell command.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string", "description": "The shell command to run"}}, "required": ["command"]}},
    {"name": "read_file", "description": "Read file contents.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer", "description": "Max lines to read"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write content to file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace exact text in file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
    {"name": "list_dir", "description": "List directory contents.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string", "description": "Directory path, defaults to current dir"}}}},
    {"name": "http_request", "description": "Make an HTTP request.",
     "input_schema": {"type": "object", "properties": {
         "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"]},
         "url": {"type": "string"},
         "headers": {"type": "object", "description": "Request headers"},
         "body": {"type": "string", "description": "Request body"},
         "timeout": {"type": "integer", "description": "Timeout in seconds, default 30"}
     }, "required": ["method", "url"]}},
    {"name": "load_skill", "description": "Load specialized knowledge by skill name.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string", "description": "Skill name to load"}}, "required": ["name"]}},
    {"name": "rag_query", "description": "Query the RAG knowledge base for relevant information.",
     "input_schema": {"type": "object", "properties": {"question": {"type": "string", "description": "The question to search for"}, "top_k": {"type": "integer", "description": "Number of results, default 3"}}, "required": ["question"]}},
]
