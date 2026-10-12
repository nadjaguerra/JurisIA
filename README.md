# JurisIA — pesquisa acadêmica de jurisprudência do STJ

Projeto de Ciência de Dados com coleta de **espelhos de acórdãos** do portal
oficial do STJ, SQLite para documentos e proveniência, embeddings locais,
ChromaDB, recuperação com reranking, Gemini para síntese fundamentada,
Streamlit e avaliação humana. O projeto é executável localmente; resultados
jurídicos e desempenho **não foram validados** sem executar sobre os dados reais.

## 1. Instalação no Windows (PowerShell do VS Code)

Copie esta pasta para `C:\Users\nadja\OneDrive\Documents\UFMS\PROJETO 1\jurisia`
ou para outra pasta. Antes, renomeie sua pasta atual caso queira preservá-la:
`jurisia-antigo`; depois copie este projeto como `jurisia`. Mova seus arquivos
originais para `jurisia\data\raw\` (sem sobrescrever seu backup). O comando
`sync` também reutiliza automaticamente o ZIP e os JSONs da Terceira Turma
quando estão na raiz de `data\raw`.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Se `py -3.11` não existir, use uma versão instalada de Python >=3.11.
Coloque sua chave em `.env` como `GEMINI_API_KEY=...`. Nunca publique `.env`.
Os modelos de embeddings são baixados na primeira execução e o tempo de
indexação depende da CPU, memória e quantidade de acórdãos.

## 2. Fluxo de execução

```powershell
# Testar somente a Terceira Turma e aproveitar os arquivos já baixados
.\.venv\Scripts\jurisia.exe sync --dataset espelhos-de-acordaos-terceira-turma
.\.venv\Scripts\jurisia.exe prepare
.\.venv\Scripts\jurisia.exe index --limit 2000
.\.venv\Scripts\jurisia.exe ask "responsabilidade civil por erro médico" --no-gemini
.\.venv\Scripts\streamlit.exe run app\streamlit_app.py
```

**Atenção:** com `--limit 2000`, a busca vê somente os primeiros 2.000
documentos ordenados por ID, mesmo que o SQLite tenha todos. Esse modo serve
para verificar o fluxo, não para avaliar a cobertura do STJ. Para a base
completa da Terceira Turma:

```powershell
.\.venv\Scripts\jurisia.exe index --limit 0
```

Para adicionar todas as seis Turmas, três Seções e Corte Especial:

```powershell
.\.venv\Scripts\jurisia.exe sync
.\.venv\Scripts\jurisia.exe prepare
.\.venv\Scripts\jurisia.exe index --limit 0
```

Esse download e a indexação completa podem ocupar muitos gigabytes e levar
horas. Observe espaço livre antes de executar. Para gerar texto com Gemini:

```powershell
.\.venv\Scripts\jurisia.exe ask "O que a base apresenta sobre erro médico?"
```

`sync` consulta o catálogo CKAN do STJ, baixa apenas recursos que não existem
e registra `manifest.json` com a data de coleta e os URLs. `prepare` importa
ZIPs e JSONs para SQLite e substitui registros repetidos pelo `id`. Se o
download falhar, rode `sync` novamente. A coleta exclui documentos sigilosos
que não estejam na fonte aberta. O projeto usa os espelhos publicados, não o
inteiro teor dos votos.

## Estrutura

```text
app/streamlit_app.py         interface e métricas
src/jurisia/download.py      catálogo oficial e downloads
src/jurisia/prepare.py       deduplicação, metadados, SQLite
src/jurisia/chunking.py      fragmentos da ementa
src/jurisia/search.py        embeddings, Chroma e reranking
src/jurisia/rag.py           contexto, Gemini, abstinência, feedback
src/jurisia/evaluation.py    Precision@K, Recall@K, MRR, Hit Rate
src/jurisia/cli.py           comandos de execução
data/raw/                   arquivos originais; não alterar
data/processed/             SQLite gerado
vectorstore/chroma/          índice gerado
data/sample/                modelo de avaliação humana
tests/                      testes de formatos e lógica
```

## Avaliação acadêmica

1. Registre 20 perguntas simples, 20 intermediárias, 10 difíceis e 10 sem
   resposta em uma cópia de `data/sample/questions_template.csv`.
2. Para cada pergunta respondível, **dois avaliadores** devem identificar
   manualmente os IDs relevantes; `relevant_ids` separa IDs por `|`.
3. Compare configurações de chunk (`--size`, `--overlap`), `k` e reranking.
   O comando `index` recria o índice inteiro; guarde os parâmetros, resultados
   e a data antes de reindexar com outra configuração.
4. Execute:

```powershell
.\.venv\Scripts\jurisia.exe evaluate data\sample\questions_template.csv --k 5 --mode vector
.\.venv\Scripts\jurisia.exe evaluate data\sample\questions_template.csv --k 5 --mode rerank
```

O exemplo de CSV é **um formulário em branco**, não um padrão ouro. Preencha
`relevant_ids` com o campo `id` do documento, não com `numeroProcesso`, antes
de executar `evaluate`. Perguntas sem resposta
exigem avaliação separada da abstinência. Avalie cada síntese quanto a suporte
das afirmações nas fontes, relevância, completude e citações; os números de
processos sozinhos não provam fidelidade. O formulário no Streamlit registra
clareza, relevância, confiança, usabilidade e utilidade percebida. Apresente
taxas com tamanho da amostra e limitações, sem interpretar opinião como
correção jurídica.

## Limitações e transparência

- A fonte contém espelhos e ementas selecionados, não toda a jurisprudência
  nem o inteiro teor; documentos e assuntos podem faltar.
- A primeira indexação de 2.000 registros é apenas demonstração de execução.
- O link exibido para cada resultado aponta ao **recurso oficial que contém o
  registro**, não a uma URL individual de decisão. A interface mostra o
  número do processo e o endereço da pesquisa oficial para conferência.
- A similaridade e o limiar 0,30 são parâmetros experimentais, não medidas
  de certeza. Calibre com perguntas rotuladas.
- O modelo pode produzir afirmações não sustentadas mesmo com referências
  válidas. O código verifica a existência das etiquetas [D1], mas a
  conferência semântica permanece uma tarefa de avaliação humana.
- O modelo de embeddings processa janelas limitadas de texto; os fragmentos
  são medidos em **palavras**, não em tokens do modelo. A configuração
  `70/15` reduz truncamento, mas precisa de comparação empírica.
- A licença MIT abrange **o código deste projeto**, não redefine os termos
  de uso dos dados do STJ. Consulte cada conjunto no portal.
- O projeto não oferece aconselhamento jurídico.

## Fontes e bibliotecas

- [Portal de Dados Abertos do STJ](https://dadosabertos.web.stj.jus.br/dataset/?tags=jurisprudencia)
- [Espelhos da Terceira Turma](https://dadosabertos.web.stj.jus.br/dataset/espelhos-de-acordaos-terceira-turma)
- [CKAN API](https://docs.ckan.org/en/latest/api/)
- [Gemini generateContent](https://ai.google.dev/gemini-api/docs/generate-content/text-generation)
- [Chroma](https://docs.trychroma.com/docs/overview/getting-started)
- [Sentence Transformers](https://www.sbert.net/docs/quickstart.html)

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
