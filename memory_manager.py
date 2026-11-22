"""Etapa 4: RAM híbrida, paginação por demanda, LRU e Segunda Chance."""
from dataclasses import dataclass, field
from math import ceil
from simulador import FSError

@dataclass
class Process:
    pid: int
    name: str
    size: int
    kind: str
    start: int | None = None
    pages: dict = field(default_factory=dict)

class MemoryManager:
    def __init__(self, reserved_kb=4096, dynamic_kb=64, page_kb=4, kernel_kb=1024, algorithm='LRU', io=None):
        if min(reserved_kb, dynamic_kb, page_kb) <= 0 or not 0 <= kernel_kb <= reserved_kb:
            raise ValueError('Capacidades inválidas')
        if dynamic_kb % page_kb: raise ValueError('RAM dinâmica deve ser múltipla da página')
        if algorithm.upper() not in ('LRU', 'SECOND_CHANCE'): raise ValueError('Algoritmo inválido')
        self.reserved = reserved_kb * 1024
        self.dynamic = dynamic_kb * 1024
        self.page_size = page_kb * 1024
        self.kernel = kernel_kb * 1024
        self.algorithm = algorithm.upper()
        self.io = io
        self.processes = {}
        self.next_pid = 101
        self.frames = [None] * (self.dynamic // self.page_size)
        self.last_used = {}
        self.refbits = {}
        self.clock_hand = 0
        self.tick = 0
        self.faults = 0
        self.hits = 0
        self.swap = set()
        self.events = []

    def _emit(self, operation, pid, page):
        event = f'{operation}: PID {pid}, página {page}'
        self.events.append(event)
        if self.io is not None:
            # Eventos de swap na mesma trilha de auditoria de E/S das etapas anteriores.
            self.io._record(operation, f'[SWAP]/pid{pid}/page{page}', [page])
        return event

    def _holes(self):
        segments = sorted((p.start, p.start+p.size) for p in self.processes.values() if p.kind == 'critical')
        cursor = self.kernel
        holes = []
        for start, end in segments:
            if start > cursor: holes.append((cursor, start))
            cursor = max(cursor, end)
        if cursor < self.reserved: holes.append((cursor, self.reserved))
        return holes

    def create(self, name, size, kind='normal'):
        if not name or name in self.processes or size <= 0 or kind not in ('normal','critical'):
            raise FSError('Nome, tipo ou tamanho inválido (ou processo já existe)')
        pid = self.next_pid
        p = Process(pid, name, size, kind)
        if kind == 'critical':
            hole = next(((a,b) for a,b in self._holes() if b-a >= size), None)
            if hole is None:
                free = sum(b-a for a,b in self._holes())
                raise FSError('Fragmentação externa: execute memory_compact --reserved' if free >= size else 'Área reservada insuficiente')
            p.start = hole[0]
        else:
            p.pages = {i: None for i in range(ceil(size/self.page_size))}
        self.processes[name] = p
        self.next_pid += 1
        if kind == 'critical':
            return f'PID {pid}: {name} [CRÍTICO] alocado contiguamente em [{p.start/1048576:.3f}, {(p.start+size)/1048576:.3f}) MB'
        wasted = len(p.pages)*self.page_size-size
        return f'PID {pid}: {name} [NORMAL] {len(p.pages)} páginas lógicas, {wasted} B de fragmentação interna; carregamento por demanda.'

    def terminate(self, name):
        p = self.processes.pop(name, None)
        if p is None: raise FSError('Processo inexistente')
        if p.kind == 'normal':
            for page, frame in p.pages.items():
                key = (p.pid,page)
                if frame is not None:
                    self.frames[frame] = None
                self.last_used.pop(key, None)
                self.refbits.pop(key, None)
                self.swap.discard(key)
        return f'PID {p.pid} ({name}) encerrado; memória liberada.'

    def compact(self):
        cursor = self.kernel
        moves = []
        for p in sorted((p for p in self.processes.values() if p.kind == 'critical'), key=lambda p:p.start):
            if p.start != cursor:
                moves.append(f'{p.name}: {p.start/1048576:.3f} MB -> {cursor/1048576:.3f} MB')
                p.start = cursor
            cursor += p.size
        return 'Compactação concluída.\n' + ('\n'.join(moves) if moves else 'Nenhuma movimentação necessária.')

    def _victim(self):
        if self.algorithm == 'LRU':
            return min(range(len(self.frames)), key=lambda i:self.last_used[self.frames[i]])
        while True:
            i = self.clock_hand
            self.clock_hand = (i+1) % len(self.frames)
            key = self.frames[i]
            if not self.refbits.get(key, False): return i
            self.refbits[key] = False

    def translate(self, name, page):
        p = self.processes.get(name)
        if p is None or p.kind != 'normal': raise FSError('Processo normal inexistente')
        if page not in p.pages: raise FSError('Página lógica fora do intervalo')
        self.tick += 1
        key = (p.pid, page)
        frame = p.pages[page]
        lines = [f'PID {p.pid} | {name} | página lógica {page}']
        if frame is None:
            self.faults += 1
            lines.append('[PAGE FAULT] Página ausente na RAM')
            try:
                frame = self.frames.index(None)
                lines.append(f'Moldura livre encontrada: {frame}')
            except ValueError:
                frame = self._victim()
                victim = self.frames[frame]
                vp = next(x for x in self.processes.values() if x.pid == victim[0])
                vp.pages[victim[1]] = None
                self.swap.add(victim)
                lines.append(f'[{self.algorithm}] Vítima: PID {victim[0]}, página {victim[1]}, moldura {frame}')
                lines.append(self._emit('SWAP_OUT', *victim))
                self.last_used.pop(victim, None)
                self.refbits.pop(victim, None)
            lines.append(self._emit('SWAP_IN', p.pid, page))
            self.frames[frame] = key
            p.pages[page] = frame
            self.swap.discard(key)
        else:
            self.hits += 1
            lines.append('[HIT] Página presente na RAM')
        self.last_used[key] = self.tick
        self.refbits[key] = True
        lines.append(f'Tradução: página lógica {page} -> moldura física {frame} (offset físico {self.reserved + frame*self.page_size} B)')
        return '\n'.join(lines)

    def status(self, area='all'):
        lines = []
        if area in ('all','reserved'):
            lines.append(f'[RAM RESERVADA] {self.reserved//1024} KB; núcleo base {self.kernel//1024} KB')
            segments = [(0,self.kernel,'Núcleo Base do SO')]
            segments += [(p.start,p.start+p.size,p.name) for p in self.processes.values() if p.kind=='critical']
            cursor = 0
            for a,b,name in sorted(segments):
                if a>cursor: lines.append(f'[{cursor/1048576:.3f} - {a/1048576:.3f} MB] LIVRE')
                if b>a: lines.append(f'[{a/1048576:.3f} - {b/1048576:.3f} MB] {name} [OCUPADO]')
                cursor=b
            if cursor<self.reserved: lines.append(f'[{cursor/1048576:.3f} - {self.reserved/1048576:.3f} MB] LIVRE')
            holes=self._holes()
            total=sum(b-a for a,b in holes)
            largest=max((b-a for a,b in holes),default=0)
            lines.append(f'Livre: {total//1024} KB | Maior lacuna: {largest//1024} KB | Fragmentação externa (livre fora da maior lacuna): {(total-largest)//1024} KB | Compactação: {"SIM" if len(holes)>1 else "NÃO"}')
        if area in ('all','virtual'):
            lines.append(f'[RAM DINÂMICA] {self.dynamic//1024} KB | página/moldura {self.page_size} B')
            for i,owner in enumerate(self.frames): lines.append(f'Moldura {i:02d}: '+(f'PID {owner[0]}, página {owner[1]}' if owner else 'LIVRE'))
            for p in self.processes.values():
                if p.kind=='normal':
                    lines.append(f'{p.name} (PID {p.pid}): {p.size} B, tabela={p.pages}, fragmentação interna={len(p.pages)*self.page_size-p.size} B')
            lines.append(f'Page faults: {self.faults} | Hits: {self.hits} | Páginas no swap: {len(self.swap)} | Algoritmo: {self.algorithm}')
        return '\n'.join(lines)
