"""CLI integrado das etapas 1 e 2. Execute: python etapa2.py --help"""
import argparse
import shlex
from pathlib import Path
from simulador import FileSystem, FSError, execute, parse_size
from io_subsystem import Request, schedule, SSD, RAID


class IntegratedSystem:
    def __init__(self, blocks=16, block_size=4096, strategy='indexed', device='hdd',
                 algorithm='SSTF', head=53, tracks=200, raid=5, disks=3):
        self.fs = FileSystem(blocks, block_size, strategy)
        self.device = device
        self.algorithm = algorithm.upper()
        self.head = head
        self.tracks = tracks
        self.queue = []
        self.history = []
        self.ssd = SSD(max(2, blocks * 2)) if device == 'ssd' else None
        self.raid = RAID(raid, disks, block_size)
        self._sync_raid()

    def _block_bytes(self, path, number):
        node = self.fs.nodes[path]
        content = (node['content'] or '').encode('utf-8')
        start = number * self.fs.block_size
        return content[start:start+self.fs.block_size].ljust(self.fs.block_size, b'\0')

    def _sync_raid(self):
        # Espelha a imagem lógica inteira: cada bloco de dados tem um endereço lógico estável.
        data = [bytes(self.fs.block_size) for _ in range(self.fs.blocks)]
        for path, node in self.fs.nodes.items():
            if node['type'] == 'file':
                for number, block in enumerate(node['blocks']):
                    data[block] = self._block_bytes(path, number)
        self.raid.write_blocks(data)

    def _record(self, operation, path, blocks):
        for block in blocks:
            track = block % self.tracks
            req = Request(operation, path, block, track)
            self.queue.append(req)
            self.history.append(req)
            if self.ssd:
                if operation == 'READ':
                    if block in self.ssd.mapping:
                        self.ssd.read(block)
                elif operation == 'DELETE':
                    self.ssd.trim(block)
                else:
                    self.ssd.write(block)

    def _owned_blocks(self, path):
        node = self.fs.nodes.get(path)
        if not node or node['type'] != 'file':
            return []
        return ([node['index']] if node['index'] is not None else []) + node['blocks']

    def _write(self, path, content=None, size=None):
        p = self.fs.normalize(path)
        before = self._owned_blocks(p)
        if p in self.fs.nodes:
            if self.fs.nodes[p]['type'] != 'file':
                raise FSError('O caminho é um diretório')
            self.fs.update(p, content=content, size=size)
        else:
            self.fs.create(p, content=content, size=size if size is not None else 0)
        after = self._owned_blocks(p)
        for b in set(before) - set(after):
            self._record('DELETE', p, [b])
        self._record('WRITE', p, after)
        self._sync_raid()
        return f'Gravação concluída: {p}; {len(after)} solicitações de E/S geradas.'

    def command(self, line):
        a = shlex.split(line)
        if not a or line.lstrip().startswith('#'):
            return ''
        cmd, *args = a
        if cmd in ('write_file', 'write'):
            if not args:
                raise FSError('Informe o caminho')
            if '--size' in args:
                i = args.index('--size')
                return self._write(args[0], size=parse_size(args[i+1]))
            return self._write(args[0], content=' '.join(args[1:]))
        if cmd == 'create':
            size = parse_size(args[args.index('--size')+1]) if '--size' in args else 0
            return self._write(args[0], size=size)
        if cmd in ('read_file', 'cat'):
            p = self.fs.normalize(args[0])
            value = self.fs.read(p)
            blocks = self._owned_blocks(p)
            # Leitura passa também pelo arranjo RAID, validando disponibilidade.
            for b in self.fs.nodes[p]['blocks']:
                self.raid.read_block(b)
            self._record('READ', p, blocks)
            return f'{value}\n[E/S] {len(blocks)} solicitações de leitura geradas.'
        if cmd == 'resize':
            return self._write(args[0], size=parse_size(args[1]))
        if cmd == 'rm':
            p = self.fs.normalize(args[0])
            targets = [q for q in self.fs.nodes if q == p or q.startswith(p + '/')]
            before = [(q, self._owned_blocks(q)) for q in targets]
            self.fs.delete(p, '--recursive' in args)
            for q, blocks in before:
                self._record('DELETE', q, blocks)
            self._sync_raid()
            return 'OK'
        if cmd == 'compact':
            result = self.fs.compact()
            self._sync_raid()
            return result
        if cmd == 'mv':
            result = execute(self.fs, line)
            self._sync_raid()
            return result
        if cmd == 'io_queue':
            return '[FILA E/S]\n' + ('\n'.join(f'{i+1}. {r.operation} {r.path} bloco={r.block} trilha={r.track}'
                                                        for i,r in enumerate(self.queue)) or '(vazia)')
        if cmd == 'io_run':
            algo = args[0].upper() if args else self.algorithm
            if self.device == 'ssd':
                count = len(self.queue)
                self.queue.clear()
                return f'SSD: {count} operações atendidas sem movimento mecânico.\n{self.ssd.status()}'
            result = schedule([r.track for r in self.queue], self.head, algo, self.tracks - 1)
            self.head = result['path'][-1]
            self.queue.clear()
            return (f'[ESCALONAMENTO {algo}]\nOrdem/caminho: ' + ' -> '.join(map(str, result['path'])) +
                    '\nDeslocamentos: ' + ' + '.join(map(str, result['segments'])) +
                    f'\nTotal de movimento: {result["movement"]} trilhas\nRequisições atendidas: {len(result["serviced"])}')
        if cmd == 'schedule_demo':
            algo = args[0].upper() if args else 'SSTF'
            head = int(args[1]) if len(args) > 1 else 53
            tracks = [int(x) for x in args[2:]] if len(args) > 2 else [98,183,37,122,14]
            result = schedule(tracks, head, algo, self.tracks-1)
            return (f'[{algo}] Caminho: ' + ' -> '.join(map(str, result['path'])) +
                    '\nDeslocamentos: ' + ' + '.join(map(str, result['segments'])) +
                    f' = {result["movement"]} trilhas')
        if cmd == 'ssd_status':
            return self.ssd.status() if self.ssd else 'Dispositivo atual: HDD'
        if cmd == 'raid_status':
            return self.raid.status() + '\n' + '\n'.join(self.raid.log)
        if cmd == 'raid_fail':
            return self.raid.fail(int(args[0]))
        if cmd == 'raid_rebuild':
            return self.raid.rebuild(int(args[0]))
        if cmd == 'raid_read':
            logical = int(args[0])
            data = self.raid.read_block(logical)
            return f'Bloco lógico {logical}: leitura/recuperação [OK], {len(data)} bytes, amostra hex={data[:16].hex()}'
        if cmd == 'help':
            return (execute(self.fs, 'help') + '\nETAPA 2: write_file CAMINHO TEXTO | write_file CAMINHO --size 8KB | '
                    'read_file CAMINHO | io_queue | io_run [FCFS|SSTF|SCAN|C-SCAN] | '
                    'schedule_demo [ALGORITMO] [CABEÇA] [TRILHAS...] | ssd_status | '
                    'raid_status | raid_fail N | raid_read BLOCO | raid_rebuild N')
        result = execute(self.fs, line)
        if isinstance(result, FileSystem):
            self.fs = result
            self.queue.clear()
            if self.ssd:
                self.ssd = SSD(max(2, self.fs.blocks * 2))
                for p,n in self.fs.nodes.items():
                    if n['type'] == 'file':
                        self._record('WRITE', p, self._owned_blocks(p))
            self.raid = RAID(self.raid.level, self.raid.count, self.fs.block_size)
            self._sync_raid()
            return 'Imagem carregada; E/S e RAID reconstruídos.'
        return result


def main():
    parser = argparse.ArgumentParser(description='Simulador integrado de sistema de arquivos, E/S, SSD e RAID')
    parser.add_argument('--strategy', choices=['indexed','contiguous'], default='indexed')
    parser.add_argument('--blocks', type=int, default=16)
    parser.add_argument('--block-size', type=int, default=4096)
    parser.add_argument('--device', choices=['hdd','ssd'], default='hdd')
    parser.add_argument('--algorithm', choices=['FCFS','SSTF','SCAN','C-SCAN'], default='SSTF')
    parser.add_argument('--head', type=int, default=53)
    parser.add_argument('--tracks', type=int, default=200)
    parser.add_argument('--raid', type=int, choices=[0,1,5], default=5)
    parser.add_argument('--disks', type=int, default=3)
    parser.add_argument('--script')
    opts = parser.parse_args()
    system = IntegratedSystem(opts.blocks, opts.block_size, opts.strategy, opts.device,
                              opts.algorithm, opts.head, opts.tracks, opts.raid, opts.disks)
    commands = Path(opts.script).read_text(encoding='utf-8').splitlines() if opts.script else None
    while True:
        try:
            if commands is None:
                line = input(f'fs:{system.fs.cwd}> ')
            elif commands:
                line = commands.pop(0)
                print('> ' + line)
            else:
                break
            if line.strip() in ('exit','quit'):
                break
            result = system.command(line)
            if result:
                print(result)
        except (ValueError, IndexError, FSError, OSError, RuntimeError) as exc:
            print('ERRO:', exc)
        except (EOFError, KeyboardInterrupt):
            print()
            break

if __name__ == '__main__':
    main()
