# Simulador de Sistema de Arquivos (Python)

Projeto didático com árvore de diretórios, CRUD, caminhos absolutos/relativos, disco de blocos fixos e duas estratégias de alocação: **contígua** e **indexada**.

## Executar

Requer Python 3.10+; nenhuma dependência externa.

```bash
python simulador.py --strategy indexed --blocks 16 --block-size 4096
python simulador.py --strategy contiguous --blocks 16 --block-size 4096
python simulador.py --script exemplo.txt
python -m unittest discover -s tests -v
```

## Comandos

```text
help
mkdir /sistema
mkdir /sistema/logs
create /sistema/logs/app.log --size 10KB
tree
fs_status --details
cd /sistema
pwd
write notas.txt "Olá mundo"
cat notas.txt
resize /sistema/logs/app.log 2KB
mv notas.txt notas2.txt
rm notas2.txt
rm /sistema --recursive
compact
save disco.json
load disco.json
exit
```

`create` reserva tamanho lógico sem gerar bytes reais. `write` armazena texto UTF-8. `resize` ajusta tamanho e descarta conteúdo materializado. `save`/`load` persistem a simulação em JSON.

## Fragmentação

- **Interna:** bytes não utilizados no último bloco de dados de cada arquivo.
- **Externa (contígua):** total de blocos livres fora do maior trecho livre, em bytes; métrica operacional de dispersão, não uma quantidade universal de bytes irrecuperáveis.
- **Compactação:** indicada quando existem múltiplos trechos livres na estratégia contígua; `compact` reorganiza arquivos. Na indexada, os blocos de dados podem ser dispersos e não exigem compactação.
- **Índice:** na estratégia indexada cada arquivo reserva um bloco de metadados/índice, inclusive arquivos vazios. Diretórios são metadados em memória e não ocupam blocos. O bloco índice não entra na fragmentação interna dos dados.

## Publicar no GitHub

```bash
git init
git add .
git commit -m "Implementa simulador de sistema de arquivos"
git branch -M main
git remote add origin https://github.com/SEU-USUARIO/simulador-sistema-arquivos.git
git push -u origin main
```

Crie antes um repositório vazio no GitHub. O projeto é uma simulação em memória, não um driver real de disco.

---

# Etapa 2 — E/S, escalonamento, SSD e RAID

A **entrada principal integrada** é `etapa2.py` (a entrada antiga `simulador.py` continua disponível para executar apenas a Etapa 1). Requer Python 3.10+ e não utiliza bibliotecas externas.

```bash
python etapa2.py --device hdd --algorithm SSTF --raid 5 --disks 3
python etapa2.py --device ssd --raid 1 --disks 2
python etapa2.py --script exemplo_etapa2.txt
python -m unittest discover -s tests -v
```

### Comandos interativos

```text
mkdir /sistema
mkdir /sistema/logs
write_file /sistema/logs/app.log "Novo Registro"
read_file /sistema/logs/app.log
io_queue
io_run SSTF
schedule_demo SSTF 53 98 183 37 122 14
fs_status --details
raid_status
raid_fail 2
raid_read 1
raid_rebuild 2
ssd_status
help
```

- `write_file` cria ou sobrescreve um arquivo, gerando requisições de E/S para os blocos físicos de índice e dados. Também aceita `--size 8KB` para conteúdo simulado preenchido com zeros. `read_file` lê e enfileira requisições. `rm` gera eventos de liberação; `mv` e `compact` atualizam a imagem RAID.
- `io_run [FCFS|SSTF|SCAN|C-SCAN]` consome a fila e mostra percurso e deslocamento. `schedule_demo` reproduz um conjunto de trilhas informado; com o exemplo do enunciado, o SSTF totaliza **208 trilhas**.
- Para HDD, cada bloco lógico é mapeado para `bloco % número_de_trilhas`, uma abstração didática. O SCAN percorre até a borda antes de inverter, quando há pedidos na outra direção. O C-SCAN contabiliza o retorno entre bordas.
- Para SSD, o FTL demonstra tradução de páginas lógicas em páginas físicas e uma política simplificada de wear leveling: grava na página disponível com menor número de gravações. Não simula blocos de apagamento reais, garbage collection ou amplificação de escrita.
- RAID 0: distribuição em faixas, sem redundância. RAID 1: espelhamento em todos os discos. RAID 5: paridade XOR rotativa; suporta a falha de **um disco**. `raid_fail N` marca o disco como indisponível, `raid_read BLOCO` demonstra a recuperação e `raid_rebuild N` reconstrói os dados do disco substituído.
- A imagem RAID armazena o conteúdo lógico dos blocos de dados; blocos de metadados e livres são representados por zeros. O comando `raid_status` lista a localização dos blocos e a paridade. Gravações em modo degradado são bloqueadas nesta versão para manter o exemplo simples.

**Limitações:** este é um simulador educacional, não um sistema de arquivos real. Os tempos de seek, a durabilidade física de SSDs, a sincronização persistente entre processos e a tolerância a falhas reais não são modelados. A fila representa solicitações geradas por operações, não paralelismo de hardware. O arquivo JSON da Etapa 1 salva a árvore e o mapa lógico, mas não persiste o estado de falhas RAID nem a contagem de desgaste do SSD.

---

# Etapa 3 — Segurança, identidade, ACL, criptografia e antivírus simulado

## Instalação e execução

Python 3.10+:

```bash
python -m pip install -r requirements.txt
python etapa3.py
```

Defina a senha de root no prompt inicial. O simulador inicia **sem sessão autenticada**. Faça `login --user root` e informe a senha no prompt oculto. Para testar com um script didático (senhas de demonstração, não use senhas reais):

```bash
# Linux/macOS
SIM_ROOT_PASSWORD=demo-root python etapa3.py --script exemplo_etapa3.txt
# PowerShell
$env:SIM_ROOT_PASSWORD="demo-root"; python etapa3.py --script exemplo_etapa3.txt
```

## Comandos novos

```text
login --user root
logout
whoami
groupadd devs
useradd carlos --group devs
usermod carlos --group admin
passwd carlos
chmod 750 /sistema/config.sys
chown root:admin /sistema/config.sys
ls_acl /sistema/config.sys
encrypt_file /home/carlos/segredo.txt
read_file /home/carlos/segredo.txt --key MinhaChave123
decrypt_file /home/carlos/segredo.txt
antivirus_scan /
antivirus_scan / --key MinhaChave123
tamper_block 3
audit_log
```

**Importante:** `--password` e `--key` expõem segredos no histórico do shell e nos arquivos de script. Prefira os prompts ocultos para operações interativas. Não versionar senhas reais.

### Regras de segurança

- **Modo Usuário:** usuários autenticados não-root; criação e leitura condicionadas às permissões POSIX `rwx` de proprietário/grupo/outros. É necessário `x` para atravessar diretórios e `wx` no pai para criar/remover arquivos.
- **Modo Kernel:** sessão autenticada como root; permite gerenciar usuários/grupos, alterar proprietário, compactar, simular falhas e adulterações e executar auditoria. Não é o kernel real do sistema operacional.
- **Senhas:** PBKDF2-HMAC-SHA256 com sal aleatório e 310.000 iterações; comparação em tempo constante. A senha não é armazenada em texto puro.
- **Criptografia:** AES-256-GCM autenticado, chave derivada de senha com scrypt e sal aleatório; nonce aleatório por arquivo. Conteúdo criptografado (base64) é o conteúdo efetivamente passado à camada de blocos e RAID. Somente arquivos com texto materializado podem ser criptografados; arquivos criados apenas com `--size` são reservas simuladas.
- **Integridade:** hashes SHA-256 dos blocos lidos do RAID são comparados com o baseline confiável da sessão. Assinaturas didáticas `SIMULATED_MALWARE` e `EICAR-STANDARD-ANTIVIRUS-TEST-FILE` são procuradas em arquivos legíveis; conteúdo criptografado só pode ser inspecionado se uma chave for fornecida. O comando `tamper_block` altera diretamente um bloco do RAID sem atualizar o baseline, simulando adulteração.
- **Auditoria:** operações negadas e eventos críticos registrados em memória. Logs não incluem senhas ou chaves.

### Limitações didáticas

- Usuários, ACL, baseline e logs permanecem **somente em memória** durante a execução. `save`/`load` estão desabilitados na Etapa 3 para evitar salvar um disco sem metadados de segurança.
- O modelo é de **bits POSIX rwx**, não ACLs estendidas com regras por usuário.
- Os hashes de referência ficam em memória, não em armazenamento externo imutável; não resistem a um atacante com controle total do processo Python.
- A varredura não é antivírus real e não substitui ferramentas de proteção.
- O texto cifrado é representado por base64 no sistema de arquivos, com overhead de armazenamento; os dados cifrados são gravados na simulação RAID.
- Não use este simulador para armazenar dados sensíveis de produção.

## Testes

```bash
python -m unittest discover -s tests -v
```

O conjunto inclui testes das três etapas: arquivos, E/S/RAID e segurança.

---

## Etapa 4 — Gerenciamento de memória híbrida

O executável `etapa4.py` preserva os comandos das Etapas 1, 2 e 3 e acrescenta memória RAM simulada.

### Executar

```bash
pip install -r requirements.txt
python etapa4.py
python etapa4.py --script exemplo_etapa4.txt
python etapa4.py --dynamic-kb 8 --page-kb 4 --replacement SECOND_CHANCE
python -m unittest discover -s tests -v
```

A senha inicial de root é solicitada no terminal. Para executar scripts de exemplo sem prompts, configure a variável de ambiente `SIM_ROOT_PASSWORD` e use a mesma senha no comando `login` do script. **Não publique senhas reais**.

### Comandos de memória

```text
create_process --name Kernel_DiskDriver --size 512KB --type critical
create_process --name App_Navegador --size 10KB --type normal
terminate_process --name Kernel_DiskDriver
memory_status --reserved
memory_status --virtual
memory_status
memory_compact --reserved
translate_address --process App_Navegador --page 1
execute_step --process App_Navegador --instruction "LOAD_DATA Página 2"
memory_algorithm LRU
memory_algorithm SECOND_CHANCE
```

- Região reservada: 4 MB, dos quais 1 MB para o núcleo base; alocação contígua de processos críticos; compactação controlada por root.
- Região dinâmica: 64 KB por padrão, molduras de 4 KB, páginas sob demanda. Ajuste as capacidades na linha de comando.
- O endereço físico exibido é um offset na RAM simulada, após a região reservada.
- Fragmentação interna: bytes inutilizados na última página lógica do processo; fragmentação externa: soma das lacunas livres fora da maior lacuna contígua da região reservada.
- `LRU` escolhe a página residente menos recentemente utilizada; `SECOND_CHANCE` usa bits de referência e ponteiro circular.
- `SWAP_IN` e `SWAP_OUT` são eventos didáticos registrados na fila de E/S integrada da Etapa 2; não são gravados bytes de memória reais em um arquivo de swap persistente. A política não simula páginas sujas ou tempos reais.
- A tabela de páginas é criada sem reservar molduras; a primeira referência gera um page fault. O estado é mantido em memória enquanto o programa estiver em execução.
- Comandos críticos de memória exigem login root. Os demais comandos seguem a política de autenticação da Etapa 3.
