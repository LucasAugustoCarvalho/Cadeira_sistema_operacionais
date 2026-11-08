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
