"""Etapa 3: identidade, ACL POSIX, AES-GCM, auditoria e integração com E/S/RAID."""
import argparse
import base64
import getpass
import hashlib
import hmac
import json
import os
import secrets
import shlex
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from etapa2 import IntegratedSystem
from simulador import FSError, parse_size

ITERATIONS = 310_000


def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    value = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, ITERATIONS)
    return {'salt': salt.hex(), 'hash': value.hex(), 'iterations': ITERATIONS}


def verify_password(password, record):
    actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(record['salt']), record['iterations'])
    return hmac.compare_digest(actual, bytes.fromhex(record['hash']))


class SecureSystem:
    def __init__(self, root_password, **kwargs):
        if not root_password:
            raise ValueError('Senha inicial de root obrigatória')
        self.system = IntegratedSystem(**kwargs)
        self.users = {'root': {'password': hash_password(root_password), 'group': 'admin', 'groups': ['admin']}}
        self.groups = {'admin': ['root']}
        self.current = None  # sessão desautenticada ao iniciar
        self.meta = {'/': {'owner': 'root', 'group': 'admin', 'mode': 0o755}}
        self.encrypted = {}  # path -> salt, nonce; conteúdo no FS é ciphertext base64
        self.baseline = {}
        self.audit = []
        self._refresh_baseline()

    def _log(self, action, path='', result='OK'):
        self.audit.append({'time': datetime.now(timezone.utc).isoformat(), 'user': self.current or '(anônimo)',
                           'action': action, 'path': path, 'result': result})

    def _deny(self, action, path, reason):
        self._log(action, path, 'NEGADO: ' + reason)
        raise FSError('[NEGADO] ' + reason)

    def _root(self, action='operação crítica'):
        if self.current != 'root':
            self._deny(action, '', 'exige MODO_KERNEL (root)')

    def _logged(self):
        if self.current is None:
            self._deny('autorização', '', 'faça login antes de executar comandos')

    def _normalize(self, path):
        return self.system.fs.normalize(path)

    def _perm(self, path, flag, action):
        self._logged()
        p = self._normalize(path)
        if self.current == 'root':
            return
        m = self.meta.get(p)
        if m is None:
            self._deny(action, p, 'objeto inexistente')
        user = self.users[self.current]
        shift = 6 if m['owner'] == self.current else 3 if m['group'] in user['groups'] else 0
        bits = (m['mode'] >> shift) & 7
        if not bits & flag:
            self._deny(action, p, f"usuário '{self.current}' não tem permissão em '{p}'")

    def _traverse(self, path, include_target=False):
        p = self._normalize(path)
        segments = p.strip('/').split('/') if p != '/' else []
        self._perm('/', 1, 'TRAVESSIA')
        cur = ''
        for part in segments[:len(segments) if include_target else -1]:
            cur += '/' + part
            self._perm(cur, 1, 'TRAVESSIA')

    def _parent_write(self, path):
        p = self._normalize(path)
        self._traverse(p)
        parent = self.system.fs.parent(p)
        self._perm(parent, 3, 'ESCRITA DIRETÓRIO')

    def _check_read(self, path):
        self._traverse(path)
        self._perm(path, 4, 'LEITURA')

    def _check_write(self, path):
        self._traverse(path)
        self._perm(path, 2, 'ESCRITA')

    def _refresh_baseline(self):
        # Hash por bloco físico, obtido do arranjo RAID (não apenas do conteúdo lógico).
        self.baseline = {str(i): hashlib.sha256(self.system.raid.read_block(i)).hexdigest()
                         for i in range(self.system.fs.blocks)}

    def _write(self, path, content=None, size=None):
        p = self._normalize(path)
        if p in self.encrypted:
            self._deny('ESCRITA', p, 'arquivo criptografado; descriptografe antes de alterar')
        exists = p in self.system.fs.nodes
        if exists:
            self._check_write(p)
        else:
            self._parent_write(p)
        if size is not None:
            out = self.system._write(p, size=size)
        else:
            out = self.system._write(p, content=content)
        if not exists:
            self.meta[p] = {'owner': self.current, 'group': self.users[self.current]['group'], 'mode': 0o644}
        self._refresh_baseline()
        self._log('WRITE', p)
        return out

    def _derive_key(self, password, salt):
        return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=2**14, r=8, p=1, dklen=32)

    def _decrypt(self, path, key):
        entry = self.encrypted[path]
        node = self.system.fs.nodes[path]
        payload = base64.b64decode(node['content'], validate=True)
        try:
            return AESGCM(self._derive_key(key, bytes.fromhex(entry['salt']))).decrypt(
                bytes.fromhex(entry['nonce']), payload, path.encode())
        except (InvalidTag, ValueError) as exc:
            self._deny('DECRYPT', path, 'chave incorreta ou dados criptografados adulterados')
            raise exc

    def _scan(self, key=None):
        self._root('antivirus_scan')
        findings = []
        signatures = (b'EICAR-STANDARD-ANTIVIRUS-TEST-FILE', b'SIMULATED_MALWARE')
        for p, node in sorted(self.system.fs.nodes.items()):
            if node['type'] != 'file':
                continue
            problems = []
            for b in self.system._owned_blocks(p):
                try:
                    raw = self.system.raid.read_block(b)
                    if hashlib.sha256(raw).hexdigest() != self.baseline.get(str(b)):
                        problems.append(f'bloco {b}: HASH ALTERADO')
                except Exception as exc:
                    problems.append(f'bloco {b}: INDISPONÍVEL ({exc})')
            if p in self.encrypted:
                if key is not None:
                    try:
                        plaintext = self._decrypt(p, key)
                        if any(sig in plaintext for sig in signatures):
                            problems.append('ASSINATURA MALICIOSA')
                    except FSError:
                        problems.append('FALHA NA AUTENTICAÇÃO AES-GCM')
                status = 'Criptografado; conteúdo não inspecionado (use --key)' if key is None else 'Criptografado e autenticado'
            else:
                raw = (node['content'] or '').encode()
                if any(sig in raw for sig in signatures):
                    problems.append('ASSINATURA MALICIOSA')
                status = 'Íntegro'
            findings.append(f'{p}: ' + ('[ALERTA] ' + '; '.join(problems) if problems else '[OK] ' + status))
        self._log('ANTIVIRUS_SCAN', '/', 'ALERTA' if any('[ALERTA]' in f for f in findings) else 'OK')
        return f'[VARREDURA] {len(findings)} arquivo(s)\n' + '\n'.join(findings)

    def command(self, line, password_prompt=None):
        args = shlex.split(line)
        if not args or line.lstrip().startswith('#'):
            return ''
        cmd, *a = args
        if cmd == 'login':
            name = a[a.index('--user')+1] if '--user' in a else a[0]
            password = a[a.index('--password')+1] if '--password' in a else (password_prompt or getpass.getpass)('Senha: ')
            if name not in self.users or not verify_password(password, self.users[name]['password']):
                self._log('LOGIN', name, 'FALHA')
                raise FSError('Credenciais inválidas')
            self.current = name
            self._log('LOGIN', name)
            return f"Autenticado: {name} | Grupo: {self.users[name]['group']} | Modo: {'MODO_KERNEL' if name == 'root' else 'MODO_USUARIO'}"
        if cmd == 'logout':
            self._log('LOGOUT')
            self.current = None
            return 'Sessão encerrada.'
        self._logged()
        if cmd == 'whoami':
            return f"{self.current} | {'MODO_KERNEL' if self.current == 'root' else 'MODO_USUARIO'}"
        if cmd == 'groupadd':
            self._root(cmd)
            if a[0] in self.groups: raise FSError('Grupo já existe')
            self.groups[a[0]] = []
            self._log(cmd, a[0])
            return 'Grupo criado.'
        if cmd == 'useradd':
            self._root(cmd)
            name = a[0]
            group = a[a.index('--group')+1] if '--group' in a else 'admin'
            if name in self.users or group not in self.groups: raise FSError('Usuário existente ou grupo inválido')
            password = a[a.index('--password')+1] if '--password' in a else (password_prompt or getpass.getpass)('Nova senha: ')
            self.users[name] = {'password': hash_password(password), 'group': group, 'groups': [group]}
            self.groups[group].append(name)
            self._log(cmd, name)
            return 'Usuário criado.'
        if cmd == 'passwd':
            name = a[0] if a else self.current
            if name != self.current: self._root(cmd)
            password = a[a.index('--password')+1] if '--password' in a else (password_prompt or getpass.getpass)('Nova senha: ')
            self.users[name]['password'] = hash_password(password)
            self._log(cmd, name)
            return 'Senha atualizada.'
        if cmd == 'usermod':
            self._root(cmd)
            name, group = a[0], a[a.index('--group')+1]
            if name not in self.users or group not in self.groups: raise FSError('Usuário/grupo inexistente')
            if group not in self.users[name]['groups']:
                self.users[name]['groups'].append(group)
                self.groups[group].append(name)
            self._log(cmd, name)
            return 'Grupo secundário adicionado.'
        if cmd == 'chmod':
            p = self._normalize(a[1])
            if p not in self.meta: raise FSError('Objeto inexistente')
            if self.current != 'root' and self.meta[p]['owner'] != self.current:
                self._deny(cmd, p, 'somente proprietário ou root pode alterar permissões')
            mode = int(a[0], 8)
            if not 0 <= mode <= 0o777: raise FSError('Modo inválido')
            self.meta[p]['mode'] = mode
            self._log(cmd, p)
            return f'{p}: {mode:03o}'
        if cmd == 'chown':
            self._root(cmd)
            name, group = a[0].split(':') if ':' in a[0] else (a[0], self.users[a[0]]['group'])
            p = self._normalize(a[1])
            if name not in self.users or group not in self.groups or p not in self.meta:
                raise FSError('Usuário, grupo ou objeto inválido')
            self.meta[p]['owner'], self.meta[p]['group'] = name, group
            self._log(cmd, p)
            return 'Proprietário atualizado.'
        if cmd == 'ls_acl':
            p = self._normalize(a[0])
            self._traverse(p)
            self._perm(p, 4, cmd)
            m = self.meta[p]
            return f"{p}: proprietário={m['owner']} grupo={m['group']} modo={m['mode']:03o}"
        if cmd == 'mkdir':
            p = self._normalize(a[0])
            self._parent_write(p)
            self.system.command(line)
            self.meta[p] = {'owner': self.current, 'group': self.users[self.current]['group'], 'mode': 0o755}
            self._log(cmd, p)
            return 'Diretório criado.'
        if cmd in ('create', 'write_file', 'write', 'resize'):
            if cmd == 'resize':
                return self._write(a[0], size=parse_size(a[1]))
            if '--size' in a:
                return self._write(a[0], size=parse_size(a[a.index('--size')+1]))
            return self._write(a[0], content=' '.join(a[1:]))
        if cmd in ('cat', 'read_file'):
            p = self._normalize(a[0])
            self._check_read(p)
            if p in self.encrypted:
                if '--key' not in a:
                    return f'{p}: [CRIPTOGRAFADO] Informe --key para leitura.'
                result = self._decrypt(p, a[a.index('--key')+1]).decode('utf-8')
                self.system.command('read_file ' + shlex.quote(p))
                self._log('READ', p)
                return result
            result = self.system.command('read_file ' + shlex.quote(p))
            self._log('READ', p)
            return result
        if cmd == 'encrypt_file':
            p = self._normalize(a[0])
            self._check_read(p)
            self._check_write(p)
            if p in self.encrypted: raise FSError('Arquivo já criptografado')
            if self.system.fs.nodes[p]['content'] is None:
                raise FSError('Arquivo sem conteúdo materializado; use write_file CAMINHO TEXTO')
            key = a[a.index('--key')+1] if '--key' in a else (password_prompt or getpass.getpass)('Chave: ')
            salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
            raw = self.system.fs.nodes[p]['content'].encode('utf-8')
            ciphertext = AESGCM(self._derive_key(key, salt)).encrypt(nonce, raw, p.encode())
            self.system._write(p, content=base64.b64encode(ciphertext).decode('ascii'))
            self.encrypted[p] = {'salt': salt.hex(), 'nonce': nonce.hex()}
            self._refresh_baseline()
            self._log(cmd, p)
            return f'{p}: criptografado AES-256-GCM; dados físicos contêm ciphertext (base64).'
        if cmd == 'decrypt_file':
            p = self._normalize(a[0])
            self._check_read(p)
            self._check_write(p)
            if p not in self.encrypted: raise FSError('Arquivo não criptografado')
            key = a[a.index('--key')+1] if '--key' in a else (password_prompt or getpass.getpass)('Chave: ')
            raw = self._decrypt(p, key)
            self.system._write(p, content=raw.decode('utf-8'))
            del self.encrypted[p]
            self._refresh_baseline()
            self._log(cmd, p)
            return f'{p}: descriptografado.'
        if cmd == 'rm':
            p = self._normalize(a[0])
            self._parent_write(p)
            targets = [q for q in self.system.fs.nodes if q == p or q.startswith(p + '/')]
            if '--recursive' in a:
                for q in targets:
                    self._traverse(q)
                    if self.system.fs.nodes[q]['type'] == 'dir': self._perm(q, 3, cmd)
            self.system.command(line)
            for q in targets:
                self.meta.pop(q, None)
                self.encrypted.pop(q, None)
            self._refresh_baseline()
            self._log(cmd, p)
            return 'Excluído.'
        if cmd == 'mv':
            src, dst = self._normalize(a[0]), self._normalize(a[1])
            self._parent_write(src)
            self._parent_write(dst)
            targets = [q for q in self.system.fs.nodes if q == src or q.startswith(src + '/')]
            if any(q in self.encrypted for q in targets):
                raise FSError('Descriptografe arquivos antes de movê-los (AAD vinculado ao caminho)')
            self.system.command(line)
            for q in sorted(targets):
                new = dst + q[len(src):]
                self.meta[new] = self.meta.pop(q)
            self._refresh_baseline()
            self._log(cmd, src)
            return 'Movido.'
        if cmd == 'cd':
            self._traverse(a[0], include_target=True)
            return self.system.command(line)
        if cmd == 'tree':
            self._perm(self.system.fs.cwd, 5, cmd)
            # árvore só mostra caminhos que podem ser percorridos e lidos
            return self._safe_tree()
        if cmd == 'antivirus_scan':
            return self._scan(a[a.index('--key')+1] if '--key' in a else None)
        if cmd == 'audit_log':
            self._root(cmd)
            return '\n'.join(json.dumps(e, ensure_ascii=False) for e in self.audit[-50:]) or '(vazio)'
        if cmd == 'tamper_block':
            self._root(cmd)
            i = int(a[0])
            if not 0 <= i < self.system.fs.blocks: raise FSError('Bloco inválido')
            disk, row = self.system.raid._placement(i)
            if self.system.raid.level == 1: disk = 0
            self.system.raid.disks[disk][row] = b'ALTERACAO_NAO_AUTORIZADA'.ljust(self.system.fs.block_size, b'!')
            self._log(cmd, str(i))
            return f'Bloco {i} adulterado (teste de auditoria).'
        if cmd in ('raid_fail', 'raid_rebuild', 'compact', 'save', 'load'):
            self._root(cmd)
            if cmd in ('save', 'load'):
                raise FSError('Persistência integrada de credenciais/ACL não disponível; comando desabilitado para evitar bypass')
            result = self.system.command(line)
            if cmd == 'compact': self._refresh_baseline()
            self._log(cmd)
            return result
        if cmd in ('fs_status', 'pwd', 'help', 'io_queue', 'io_run', 'schedule_demo', 'ssd_status', 'raid_status', 'raid_read'):
            if cmd in ('raid_read', 'raid_status', 'io_queue', 'io_run', 'fs_status', 'ssd_status'):
                self._root(cmd)
            if cmd == 'help':
                return ('ETAPA 3: login --user NOME | logout | whoami | groupadd GRUPO | '
                        'useradd NOME --group GRUPO | usermod NOME --group GRUPO | passwd [NOME] | '
                        'chmod 750 CAMINHO | chown USER:GRUPO CAMINHO | ls_acl CAMINHO | '
                        'encrypt_file CAMINHO [--key CHAVE] | decrypt_file CAMINHO [--key CHAVE] | '
                        'antivirus_scan / [--key CHAVE] | audit_log | tamper_block BLOCO\n' + self.system.command('help'))
            return self.system.command(line)
        self._deny(cmd, '', 'comando desconhecido ou não permitido')

    def _safe_tree(self):
        fs = self.system.fs
        lines = [fs.cwd + ' [DIR]']
        def walk(parent, prefix=''):
            try:
                self._perm(parent, 5, 'LISTAGEM')
            except FSError:
                return
            children = sorted((p for p in fs.nodes if p != parent and fs.parent(p) == parent))
            for idx, p in enumerate(children):
                node = fs.nodes[p]
                last = idx == len(children)-1
                lines.append(prefix + ('└── ' if last else '├── ') + p.rsplit('/', 1)[-1] + ('/ [DIR]' if node['type']=='dir' else f" ({node['size']} B) [ARQ]"))
                if node['type'] == 'dir': walk(p, prefix + ('    ' if last else '│   '))
        walk(fs.cwd)
        return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Etapas 1+2+3: arquivos, E/S, RAID e segurança')
    parser.add_argument('--root-password', help='Somente para testes; prefira prompt ou variável SIM_ROOT_PASSWORD')
    parser.add_argument('--script')
    parser.add_argument('--blocks', type=int, default=16)
    parser.add_argument('--block-size', type=int, default=4096)
    parser.add_argument('--strategy', choices=['indexed', 'contiguous'], default='indexed')
    parser.add_argument('--device', choices=['hdd', 'ssd'], default='hdd')
    parser.add_argument('--raid', type=int, choices=[0, 1, 5], default=5)
    parser.add_argument('--disks', type=int, default=3)
    opts = parser.parse_args()
    root_password = opts.root_password or os.environ.get('SIM_ROOT_PASSWORD') or getpass.getpass('Defina a senha inicial de root: ')
    sys = SecureSystem(root_password, blocks=opts.blocks, block_size=opts.block_size,
                       strategy=opts.strategy, device=opts.device, raid=opts.raid, disks=opts.disks)
    commands = Path(opts.script).read_text(encoding='utf-8').splitlines() if opts.script else None
    while True:
        try:
            if commands is None: line = input(f'{sys.current or "guest"}@fs:{sys.system.fs.cwd}> ')
            elif commands: line = commands.pop(0)
            else: break
            if line.strip() in ('exit', 'quit'): break
            if commands is not None:
                print('> ' + ('[comando com credencial ocultada]' if '--password' in line or '--key' in line else line))
            result = sys.command(line)
            if result: print(result)
        except (FSError, ValueError, IndexError, OSError, RuntimeError, KeyError, UnicodeError) as exc:
            print('ERRO:', exc)
        except (KeyboardInterrupt, EOFError):
            print()
            break


if __name__ == '__main__':
    main()
