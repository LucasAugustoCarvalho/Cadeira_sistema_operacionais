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
