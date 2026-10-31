"""Simulador didático de sistema de arquivos com alocação contígua ou indexada."""
import argparse
import json
import math
import shlex
from pathlib import Path

class FSError(Exception):
    pass

class FileSystem:
    def __init__(self, blocks=16, block_size=4096, strategy="indexed"):
        if blocks < 1 or block_size < 1 or strategy not in ("indexed", "contiguous"):
            raise ValueError("Configuração inválida")
        self.blocks, self.block_size, self.strategy = blocks, block_size, strategy
        self.nodes = {"/": {"type": "dir"}}
        self.disk = [None] * blocks
        self.cwd = "/"

    def normalize(self, path):
        if not path:
            raise FSError("Caminho vazio")
        parts = [] if path.startswith("/") else self.cwd.strip("/").split("/") if self.cwd != "/" else []
        for p in path.split("/"):
            if p in ("", "."):
                continue
            if p == "..":
                if parts:
                    parts.pop()
            else:
                parts.append(p)
        return "/" + "/".join(parts)

    def parent(self, path):
        return path.rsplit("/", 1)[0] or "/"

    def require_parent(self, path):
        if path == "/" or self.parent(path) not in self.nodes or self.nodes[self.parent(path)]["type"] != "dir":
            raise FSError("Diretório pai inexistente ou caminho inválido")
        if path in self.nodes:
            raise FSError("Caminho já existe")

    def mkdir(self, path):
        p = self.normalize(path)
        self.require_parent(p)
        self.nodes[p] = {"type": "dir"}

    def cd(self, path):
        p = self.normalize(path)
        if p not in self.nodes or self.nodes[p]["type"] != "dir":
            raise FSError("Diretório inexistente")
        self.cwd = p

    def _allocate(self, count):
        if count == 0:
            return []
        if self.strategy == "indexed":
            found = [i for i, value in enumerate(self.disk) if value is None][:count]
            if len(found) != count:
                raise FSError("Espaço insuficiente")
            return found
        for start in range(self.blocks - count + 1):
            if all(self.disk[i] is None for i in range(start, start + count)):
                return list(range(start, start + count))
        free = self.disk.count(None)
        if free >= count:
            raise FSError("Fragmentação externa: espaço livre suficiente, mas não contíguo; execute compact")
        raise FSError("Espaço insuficiente")

    def create(self, path, size=0, content=None):
        p = self.normalize(path)
        self.require_parent(p)
        if size < 0:
            raise FSError("Tamanho negativo")
        if content is not None:
            size = len(content.encode("utf-8"))
        data_count = math.ceil(size / self.block_size)
        # Na estratégia indexada, um bloco de índice é reservado por arquivo.
        count = data_count + (1 if self.strategy == "indexed" else 0)
        indices = self._allocate(count)
        for i in indices:
            self.disk[i] = p
        self.nodes[p] = {"type": "file", "size": size, "content": content,
                         "blocks": indices[1:] if self.strategy == "indexed" else indices,
                         "index": indices[0] if self.strategy == "indexed" else None}

    def read(self, path):
        p = self.normalize(path)
        if p not in self.nodes or self.nodes[p]["type"] != "file":
            raise FSError("Arquivo inexistente")
        node = self.nodes[p]
        return node["content"] if node["content"] is not None else f"[Arquivo simulado: {node['size']} bytes, sem conteúdo materializado]"

    def delete(self, path, recursive=False):
        p = self.normalize(path)
        if p == "/" or p not in self.nodes:
            raise FSError("Não é possível excluir este caminho")
        targets = [n for n in self.nodes if n == p or n.startswith(p + "/")]
        if len(targets) > 1 and not recursive:
            raise FSError("Diretório não vazio; use --recursive")
        if self.cwd == p or self.cwd.startswith(p + "/"):
            self.cwd = "/"
        for n in targets:
            if self.nodes[n]["type"] == "file":
                for i in self.nodes[n]["blocks"] + ([self.nodes[n]["index"]] if self.nodes[n]["index"] is not None else []):
                    self.disk[i] = None
            del self.nodes[n]

    def update(self, path, size=None, content=None):
        p = self.normalize(path)
        if p not in self.nodes or self.nodes[p]["type"] != "file":
            raise FSError("Arquivo inexistente")
        old = dict(self.nodes[p])
        old_disk = self.disk[:]
        try:
            self.delete(p)
            self.create(p, old["size"] if size is None else size, old["content"] if content is None and size is None else content)
        except Exception:
            self.nodes[p] = old
            self.disk = old_disk
            raise

    def move(self, source, destination):
        src, dst = self.normalize(source), self.normalize(destination)
        if src == "/" or src not in self.nodes or dst == src or dst.startswith(src + "/"):
            raise FSError("Movimentação inválida")
        self.require_parent(dst)
        targets = sorted([p for p in self.nodes if p == src or p.startswith(src + "/")], key=len)
        for p in targets:
            new = dst + p[len(src):]
            self.nodes[new] = self.nodes.pop(p)
            if self.nodes[new]["type"] == "file":
                for i in self.nodes[new]["blocks"] + ([self.nodes[new]["index"]] if self.nodes[new]["index"] is not None else []):
                    self.disk[i] = new
        if self.cwd == src or self.cwd.startswith(src + "/"):
            self.cwd = dst + self.cwd[len(src):]

    def compact(self):
        if self.strategy != "contiguous":
            return "Compactação desnecessária na alocação indexada."
        files = sorted((p for p in self.nodes if self.nodes[p]["type"] == "file"), key=lambda p: self.nodes[p]["blocks"][0] if self.nodes[p]["blocks"] else -1)
        self.disk = [None] * self.blocks
        cursor = 0
        for p in files:
            count = len(self.nodes[p]["blocks"])
            indices = list(range(cursor, cursor + count))
            self.nodes[p]["blocks"] = indices
            for i in indices:
                self.disk[i] = p
            cursor += count
        return "Disco compactado."

    def tree(self):
        lines = ["/ [DIR]"]
        def walk(parent, prefix=""):
            children = sorted((p for p in self.nodes if p != parent and self.parent(p) == parent), key=lambda p: (self.nodes[p]["type"] != "dir", p))
            for j, p in enumerate(children):
                last = j == len(children) - 1
                node = self.nodes[p]
                name = p.rsplit("/", 1)[-1]
                lines.append(prefix + ("└── " if last else "├── ") + (name + "/ [DIR]" if node["type"] == "dir" else f"{name} ({node['size']} bytes) [ARQ]"))
                if node["type"] == "dir":
                    walk(p, prefix + ("    " if last else "│   "))
        walk("/")
        return "\n".join(lines)

    def status(self, details=False):
        free = self.disk.count(None)
        runs = []
        current = 0
        for owner in self.disk:
            if owner is None:
                current += 1
            elif current:
                runs.append(current)
                current = 0
        if current:
            runs.append(current)
        largest = max(runs, default=0)
        internal = sum((self.block_size - n["size"] % self.block_size) % self.block_size
                       for n in self.nodes.values() if n["type"] == "file")
        index_count = sum(1 for n in self.nodes.values() if n["type"] == "file" and n["index"] is not None)
        external = (free - largest) * self.block_size if self.strategy == "contiguous" else 0
        compact_needed = self.strategy == "contiguous" and len(runs) > 1
        lines = [f"Estratégia: {self.strategy} | Bloco: {self.block_size} B | Total: {self.blocks} blocos",
                 "[MAPA GRÁFICO]  . livre | D dados | I índice",
                 " ".join(f"{i:02d}:{'I' if any(n.get('index') == i for n in self.nodes.values()) else 'D' if owner else '.'}" for i, owner in enumerate(self.disk)),
                 f"Livres: {free} ({free*self.block_size} B) | Maior trecho livre: {largest} blocos",
                 f"Fragmentação interna: {internal} B | Fragmentação externa: {external} B",
                 f"Necessidade de compactação: {'SIM' if compact_needed else 'NÃO'}"]
        if details:
            lines.append("[DETALHES DOS BLOCOS]")
            for i, owner in enumerate(self.disk):
                if owner is None:
                    lines.append(f"Bloco {i:02d} [LIVRE]")
                    continue
                n = self.nodes[owner]
                if n["index"] == i:
                    lines.append(f"Bloco {i:02d} [ÍNDICE] {owner} -> {n['blocks']}")
                else:
                    order = n["blocks"].index(i)
                    used = min(self.block_size, max(0, n["size"] - order*self.block_size))
                    lines.append(f"Bloco {i:02d} [DADO] {owner} ({used} B usados, {self.block_size-used} B internos livres)")
            lines.append("[ARQUIVOS]")
            for p, n in sorted(self.nodes.items()):
                if n["type"] == "file":
                    wasted = (self.block_size - n["size"] % self.block_size) % self.block_size
                    lines.append(f"{p}: {n['size']} B, dados={n['blocks']}, índice={n['index']}, fragmentação interna={wasted} B")
        return "\n".join(lines)

    def save(self, path):
        Path(path).write_text(json.dumps({"blocks": self.blocks, "block_size": self.block_size, "strategy": self.strategy, "nodes": self.nodes, "disk": self.disk, "cwd": self.cwd}, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        fs = cls(data["blocks"], data["block_size"], data["strategy"])
        fs.nodes, fs.disk, fs.cwd = data["nodes"], data["disk"], data["cwd"]
        if len(fs.disk) != fs.blocks or fs.nodes.get("/", {}).get("type") != "dir":
            raise FSError("Imagem de disco inválida")
        return fs

def parse_size(s):
    s = s.upper().strip()
    for suffix, mult in (("KB", 1024), ("MB", 1024**2), ("B", 1)):
        if s.endswith(suffix):
            return int(s[:-len(suffix)]) * mult
    return int(s)

def execute(fs, command):
    args = shlex.split(command)
    if not args:
        return ""
    cmd, *a = args
    if cmd == "help":
        return "mkdir CAMINHO | cd CAMINHO | pwd | tree | create CAMINHO --size 10KB | write CAMINHO TEXTO | cat CAMINHO | resize CAMINHO 2KB | rm CAMINHO [--recursive] | mv ORIGEM DESTINO | fs_status [--details] | compact | save ARQUIVO | load ARQUIVO | exit"
    if cmd == "mkdir": fs.mkdir(a[0])
    elif cmd == "cd": fs.cd(a[0])
    elif cmd == "pwd": return fs.cwd
    elif cmd == "tree": return fs.tree()
    elif cmd == "create":
        size = parse_size(a[a.index("--size")+1]) if "--size" in a else 0
        fs.create(a[0], size)
    elif cmd == "write":
        p = a[0]
        content = " ".join(a[1:])
        if fs.normalize(p) in fs.nodes: fs.update(p, content=content)
        else: fs.create(p, content=content)
    elif cmd == "cat": return fs.read(a[0])
    elif cmd == "resize": fs.update(a[0], size=parse_size(a[1]))
    elif cmd == "rm": fs.delete(a[0], "--recursive" in a)
    elif cmd == "mv": fs.move(a[0], a[1])
    elif cmd == "fs_status": return fs.status("--details" in a)
    elif cmd == "compact": return fs.compact()
    elif cmd == "save": fs.save(a[0])
    elif cmd == "load": return FileSystem.load(a[0])
    else: raise FSError(f"Comando desconhecido: {cmd}")
    return "OK"

def main():
    parser = argparse.ArgumentParser(description="Simulador de sistema de arquivos")
    parser.add_argument("--strategy", choices=["indexed", "contiguous"], default="indexed")
    parser.add_argument("--blocks", type=int, default=16)
    parser.add_argument("--block-size", type=int, default=4096)
    parser.add_argument("--script", help="Arquivo de comandos, um por linha")
    options = parser.parse_args()
    fs = FileSystem(options.blocks, options.block_size, options.strategy)
    commands = Path(options.script).read_text(encoding="utf-8").splitlines() if options.script else None
    while True:
        try:
            line = next(commands_iter) if False else (input(f"fs:{fs.cwd}> ") if commands is None else commands.pop(0) if commands else None)
            if line is None or line.strip() in ("exit", "quit"):
                break
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if options.script:
                print("> " + line)
            result = execute(fs, line)
            if isinstance(result, FileSystem):
                fs = result
                print("Imagem carregada.")
            elif result:
                print(result)
        except (FSError, ValueError, IndexError, OSError) as e:
            print("ERRO:", e)
        except (EOFError, KeyboardInterrupt):
            print()
            break

if __name__ == "__main__":
    main()
