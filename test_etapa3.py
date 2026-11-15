import unittest
from etapa3 import SecureSystem
from simulador import FSError

class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.s = SecureSystem('strong-root-password')
        self.s.command('login --user root --password strong-root-password')
        self.s.command('groupadd devs')
        self.s.command('useradd carlos --group devs --password carlos123')
        self.s.command('mkdir /sistema')
        self.s.command('write_file /sistema/config.sys "configuração secreta"')
        self.s.command('chmod 750 /sistema/config.sys')

    def test_acl_and_audit(self):
        self.s.command('logout')
        self.s.command('login --user carlos --password carlos123')
        with self.assertRaises(FSError): self.s.command('read_file /sistema/config.sys')
        self.assertTrue(any('NEGADO' in x['result'] for x in self.s.audit))
        with self.assertRaises(FSError): self.s.command('groupadd invasores')

    def test_encrypt_and_decrypt(self):
        self.s.command('encrypt_file /sistema/config.sys --key MinhaChave123')
        raw = self.s.system.fs.nodes['/sistema/config.sys']['content']
        self.assertNotIn('configuração', raw)
        self.assertIn('criptografado', self.s.command('read_file /sistema/config.sys').lower())
        self.assertIn('configuração', self.s.command('read_file /sistema/config.sys --key MinhaChave123'))
        with self.assertRaises(FSError): self.s.command('decrypt_file /sistema/config.sys --key errada')
        self.s.command('decrypt_file /sistema/config.sys --key MinhaChave123')
        self.assertIn('configuração', self.s.command('read_file /sistema/config.sys'))

    def test_scan_tamper(self):
        self.assertNotIn('[ALERTA]', self.s.command('antivirus_scan /'))
        b = self.s.system.fs.nodes['/sistema/config.sys']['blocks'][0]
        self.s.command(f'tamper_block {b}')
        self.assertIn('HASH ALTERADO', self.s.command('antivirus_scan /'))

    def test_malware_signature(self):
        self.s.command('write_file /sistema/virus.txt SIMULATED_MALWARE')
        self.assertIn('ASSINATURA MALICIOSA', self.s.command('antivirus_scan /'))

    def test_owner_access(self):
        self.s.command('mkdir /home')
        self.s.command('chmod 777 /home')
        self.s.command('logout')
        self.s.command('login --user carlos --password carlos123')
        self.s.command('mkdir /home/carlos')
        self.s.command('write_file /home/carlos/teste.txt ola')
        self.assertIn('ola', self.s.command('read_file /home/carlos/teste.txt'))
        self.s.command('chmod 600 /home/carlos/teste.txt')
        self.assertIn('600', self.s.command('ls_acl /home/carlos/teste.txt'))

if __name__ == '__main__': unittest.main()
