"""CLI da Etapa 4, preservando os comandos e a autenticação das Etapas 1-3."""
import argparse
import getpass
import os
import shlex
from pathlib import Path
from etapa3 import SecureSystem
from memory_manager import MemoryManager
from simulador import FSError, parse_size

class CompleteSystem:
    def __init__(self, root_password, reserved_kb=4096, dynamic_kb=64, page_kb=4, kernel_kb=1024, replacement='LRU', **kwargs):
        self.security = SecureSystem(root_password, **kwargs)
        self.memory = MemoryManager(reserved_kb, dynamic_kb, page_kb, kernel_kb, replacement, self.security.system)

    def command(self, line, password_prompt=None):
        args = shlex.split(line)
        if not args or line.lstrip().startswith('#'): return ''
        cmd, *a = args
        if cmd == 'help':
            return (self.security.command('help') if self.security.current else 'Faça login para acessar a ajuda.') + ('\nETAPA 4: create_process --name NOME --size 512KB --type critical|normal | terminate_process --name NOME | '
                 'translate_address --process NOME --page 0 | execute_step --process NOME --instruction "LOAD_DATA Página 2" | '
                 'memory_status [--reserved|--virtual] | memory_compact --reserved | memory_algorithm LRU|SECOND_CHANCE')
        if cmd not in ('create_process','terminate_process','translate_address','execute_step','memory_status','memory_compact','memory_algorithm'):
            return self.security.command(line, password_prompt=password_prompt)
        self.security._logged()
        def opt(flag, default=None):
            return a[a.index(flag)+1] if flag in a else default
        if cmd == 'create_process':
            kind = opt('--type','normal')
            if kind == 'critical': self.security._root(cmd)
            name = opt('--name')
            size = opt('--size')
            if not name or not size: raise FSError('Informe --name e --size')
            result = self.memory.create(name, parse_size(size), kind)
        elif cmd == 'terminate_process':
            name = opt('--name')
            if name not in self.memory.processes: raise FSError('Processo inexistente')
            if self.memory.processes[name].kind == 'critical': self.security._root(cmd)
            result = self.memory.terminate(name)
        elif cmd == 'translate_address':
            result = self.memory.translate(opt('--process'), int(opt('--page')))
        elif cmd == 'execute_step':
            import re
            instruction = opt('--instruction','')
            match = re.search(r'(?:página|pagina|page)\s+(\d+)', instruction, re.I)
            if not match: raise FSError('Instrução deve indicar Página N')
            result = '[CPU] '+instruction+'\n'+self.memory.translate(opt('--process'), int(match.group(1)))
        elif cmd == 'memory_status':
            result = self.memory.status('reserved' if '--reserved' in a else 'virtual' if '--virtual' in a else 'all')
        elif cmd == 'memory_compact':
            self.security._root(cmd)
            result = self.memory.compact()
        else:
            self.security._root(cmd)
            algorithm = a[0].upper()
            if algorithm not in ('LRU','SECOND_CHANCE'): raise FSError('Algoritmo deve ser LRU ou SECOND_CHANCE')
            self.memory.algorithm = algorithm
            result = f'Algoritmo de substituição: {algorithm}'
        self.security._log(cmd, ' '.join(a[:2]))
        return result

def main():
    parser = argparse.ArgumentParser(description='Simulador integrado das etapas 1 a 4')
    parser.add_argument('--root-password', help='Apenas testes; prefira prompt ou SIM_ROOT_PASSWORD')
    parser.add_argument('--script')
    parser.add_argument('--reserved-kb', type=int, default=4096)
    parser.add_argument('--dynamic-kb', type=int, default=64)
    parser.add_argument('--kernel-kb', type=int, default=1024)
    parser.add_argument('--page-kb', type=int, default=4)
    parser.add_argument('--replacement', choices=['LRU','SECOND_CHANCE'], default='LRU')
    parser.add_argument('--blocks', type=int, default=16)
    parser.add_argument('--block-size', type=int, default=4096)
    parser.add_argument('--strategy', choices=['indexed','contiguous'], default='indexed')
    parser.add_argument('--device', choices=['hdd','ssd'], default='hdd')
    parser.add_argument('--raid', type=int, choices=[0,1,5], default=5)
    parser.add_argument('--disks', type=int, default=3)
    opts = parser.parse_args()
    password = opts.root_password or os.environ.get('SIM_ROOT_PASSWORD') or getpass.getpass('Defina a senha inicial de root: ')
    system = CompleteSystem(password, reserved_kb=opts.reserved_kb, dynamic_kb=opts.dynamic_kb,
                            kernel_kb=opts.kernel_kb, page_kb=opts.page_kb, replacement=opts.replacement,
                            blocks=opts.blocks, block_size=opts.block_size, strategy=opts.strategy,
                            device=opts.device, raid=opts.raid, disks=opts.disks)
    commands = Path(opts.script).read_text(encoding='utf-8').splitlines() if opts.script else None
    while True:
        try:
            line = input(f'{system.security.current or "guest"}@fs> ') if commands is None else commands.pop(0) if commands else None
            if line is None or line.strip() in ('exit','quit'): break
            if commands is not None and line.strip() and not line.startswith('#'):
                print('> '+ ('[credenciais ocultadas]' if '--password' in line or '--key' in line else line))
            output = system.command(line)
            if output: print(output)
        except (FSError, ValueError, IndexError, KeyError, OSError, TypeError) as exc:
            print('ERRO:',exc)
        except (KeyboardInterrupt, EOFError):
            print()
            break

if __name__ == '__main__': main()
