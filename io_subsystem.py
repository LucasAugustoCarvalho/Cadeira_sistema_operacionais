"""Etapa 2: escalonamento HDD, SSD wear leveling e RAID didático."""
from dataclasses import dataclass


@dataclass
class Request:
    operation: str
    path: str
    block: int
    track: int


def schedule(tracks, head=53, algorithm='SSTF', max_track=199, direction='up'):
    """Retorna caminho da cabeça, deslocamento total e trilhas atendidas.

    SCAN vai até a borda apenas se há pedidos no sentido oposto.
    C-SCAN inclui deslocamento de retorno da borda superior para zero.
    """
    if not 0 <= head <= max_track or any(not 0 <= t <= max_track for t in tracks):
        raise ValueError('Trilhas fora do intervalo do disco')
    algorithm = algorithm.upper()
    if algorithm not in ('FCFS', 'SSTF', 'SCAN', 'C-SCAN'):
        raise ValueError('Algoritmo desconhecido')
    if direction not in ('up', 'down'):
        raise ValueError('Direção inválida')
    pending = list(tracks)
    path = [head]
    serviced = []
    if algorithm == 'FCFS':
        serviced = pending[:]
        path += serviced
    elif algorithm == 'SSTF':
        current = head
        while pending:
            nxt = min(pending, key=lambda t: (abs(t-current), t))
            pending.remove(nxt)
            serviced.append(nxt)
            path.append(nxt)
            current = nxt
    else:
        # Solicitações na posição atual são atendidas imediatamente.
        equal = [t for t in pending if t == head]
        serviced += equal
        path += equal
        low = sorted(t for t in pending if t < head)
        high = sorted(t for t in pending if t > head)
        if algorithm == 'SCAN':
            first, second = (high, low[::-1]) if direction == 'up' else (low[::-1], high)
            serviced += first + second
            path += first
            if second:
                boundary = max_track if direction == 'up' else 0
                if path[-1] != boundary:
                    path.append(boundary)
                path += second
        else:
            # C-SCAN convencional ascendente ou descendente.
            first, second = (high, low) if direction == 'up' else (low[::-1], high[::-1])
            serviced += first + second
            path += first
            if second:
                boundary = max_track if direction == 'up' else 0
                opposite = 0 if direction == 'up' else max_track
                if path[-1] != boundary:
                    path.append(boundary)
                path.append(opposite)
                path += second
    movement = sum(abs(b-a) for a,b in zip(path, path[1:]))
    return {'algorithm': algorithm, 'path': path, 'serviced': serviced, 'movement': movement,
            'segments': [abs(b-a) for a,b in zip(path, path[1:])]}


class SSD:
    """FTL simples: gravações copy-on-write na página física menos desgastada."""
    def __init__(self, physical_pages=64):
        if physical_pages < 2:
            raise ValueError('SSD requer pelo menos duas páginas físicas')
        self.wear = [0] * physical_pages
        self.mapping = {}
        self.free = set(range(physical_pages))
        self.events = []

    def write(self, logical):
        if not self.free and logical not in self.mapping:
            raise RuntimeError('SSD sem páginas livres')
        old = self.mapping.get(logical)
        candidates = self.free if self.free else {old}
        physical = min(candidates, key=lambda p: (self.wear[p], p))
        self.free.discard(physical)
        self.mapping[logical] = physical
        self.wear[physical] += 1
        if old is not None and old != physical:
            self.free.add(old)
        self.events.append(f'WRITE página lógica {logical} -> física {physical}, desgaste={self.wear[physical]}')
        return physical

    def read(self, logical):
        if logical not in self.mapping:
            raise RuntimeError('Página lógica não mapeada')
        physical = self.mapping[logical]
        self.events.append(f'READ página lógica {logical} -> física {physical}')
        return physical

    def trim(self, logical):
        old = self.mapping.pop(logical, None)
        if old is not None:
            self.free.add(old)
            self.events.append(f'TRIM página lógica {logical} (física {old})')

    def status(self):
        return ('[SSD / WEAR LEVELING]\n' +
                f'Mapeamento lógico/físico: {dict(sorted(self.mapping.items()))}\n' +
                f'Desgaste por página: {self.wear}\n' +
                f'Mín/Máx gravações: {min(self.wear)}/{max(self.wear)}')


def xor_bytes(*chunks):
    if not chunks:
        return b''
    size = len(chunks[0])
    if any(len(c) != size for c in chunks):
        raise ValueError('Tamanhos incompatíveis para XOR')
    out = bytearray(size)
    for chunk in chunks:
        for i, value in enumerate(chunk):
            out[i] ^= value
    return bytes(out)


class RAID:
    """RAID 0, 1, 5 em blocos de bytes, paridade rotativa no RAID 5."""
    def __init__(self, level=5, disks=3, block_size=4096):
        if level not in (0, 1, 5) or disks < (3 if level == 5 else 2) or block_size < 1:
            raise ValueError('Configuração RAID inválida')
        self.level, self.count, self.block_size = level, disks, block_size
        self.disks = [{} for _ in range(disks)]
        self.failed = set()
        self.logical_count = 0
        self.log = []

    def _placement(self, logical):
        if self.level == 0:
            return logical % self.count, logical // self.count
        if self.level == 1:
            return None, logical
        stripe = logical // (self.count - 1)
        slot = logical % (self.count - 1)
        parity = (self.count - 1 - stripe % self.count)
        data_disks = [d for d in range(self.count) if d != parity]
        return data_disks[slot], stripe

    def _padded(self, chunk):
        if len(chunk) > self.block_size:
            raise ValueError('Bloco excede o tamanho do RAID')
        return chunk.ljust(self.block_size, b'\0')

    def write_blocks(self, blocks):
        if self.failed:
            raise RuntimeError('Gravação em modo degradado não suportada; recupere o disco antes')
        self.disks = [{} for _ in range(self.count)]
        self.logical_count = len(blocks)
        self.log = []
        for logical, raw in enumerate(blocks):
            data = self._padded(raw)
            disk, row = self._placement(logical)
            if self.level == 1:
                for d in range(self.count):
                    self.disks[d][row] = data
                    self.log.append(f'Disco {d+1} bloco {row}: espelho do bloco lógico {logical}')
            else:
                self.disks[disk][row] = data
                self.log.append(f'Disco {disk+1} bloco {row}: dados lógicos {logical}')
        if self.level == 5:
            stripes = (len(blocks) + self.count - 2) // (self.count - 1)
            for row in range(stripes):
                parity = self.count - 1 - row % self.count
                chunks = [self.disks[d].get(row, bytes(self.block_size)) for d in range(self.count) if d != parity]
                self.disks[parity][row] = xor_bytes(*chunks)
                self.log.append(f'Disco {parity+1} bloco {row}: PARIDADE XOR (faixa {row})')

    def fail(self, disk):
        idx = disk - 1
        if idx not in range(self.count):
            raise ValueError('Disco inválido')
        self.failed.add(idx)
        return f'Falha forçada no Disco {disk}'

    def read_block(self, logical):
        if logical < 0 or logical >= self.logical_count:
            raise IndexError('Bloco lógico inexistente')
        disk, row = self._placement(logical)
        if self.level == 0:
            if disk in self.failed:
                raise RuntimeError('RAID 0: perda de dados (sem redundância)')
            return self.disks[disk][row]
        if self.level == 1:
            healthy = next((d for d in range(self.count) if d not in self.failed), None)
            if healthy is None:
                raise RuntimeError('RAID 1: todas as cópias indisponíveis')
            return self.disks[healthy][row]
        if len(self.failed) > 1:
            raise RuntimeError('RAID 5: mais de um disco falhou')
        if disk not in self.failed:
            return self.disks[disk][row]
        # Reconstrução XOR: paridade + demais blocos da faixa.
        parts = [self.disks[d].get(row, bytes(self.block_size)) for d in range(self.count) if d != disk]
        return xor_bytes(*parts)

    def rebuild(self, disk):
        idx = disk - 1
        if idx not in self.failed:
            raise ValueError('Este disco não está com falha')
        if self.level == 0:
            raise RuntimeError('RAID 0 não permite reconstrução')
        if self.level == 1:
            healthy = next((d for d in range(self.count) if d not in self.failed), None)
            if healthy is None:
                raise RuntimeError('Nenhuma cópia disponível')
            self.disks[idx] = dict(self.disks[healthy])
        else:
            if len(self.failed) != 1:
                raise RuntimeError('RAID 5 suporta apenas uma falha')
            rows = set().union(*(set(d.keys()) for d in self.disks))
            self.disks[idx] = {row: xor_bytes(*(self.disks[d].get(row, bytes(self.block_size))
                                               for d in range(self.count) if d != idx)) for row in rows}
        self.failed.remove(idx)
        return f'Disco {disk} reconstruído via {"espelhamento" if self.level == 1 else "XOR"} [OK]'

    def status(self):
        lines = [f'[RAID {self.level}] {self.count} discos | bloco={self.block_size} B | falhas={[d+1 for d in sorted(self.failed)]}']
        for d, blocks in enumerate(self.disks):
            label = 'FALHOU' if d in self.failed else 'OK'
            for row in sorted(blocks):
                parity = self.level == 5 and d == self.count - 1 - row % self.count
                lines.append(f'Disco {d+1} [{label}] bloco {row}: {"PARIDADE XOR" if parity else "DADOS"}')
        return '\n'.join(lines)
