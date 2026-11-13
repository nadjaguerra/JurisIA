# JurisIA

Ferramenta de pesquisa acadêmica de jurisprudência do Superior Tribunal de
Justiça (STJ), desenvolvida como projeto de Ciência de Dados na UFMS. O app
consulta ementas de espelhos de acórdãos publicados no Portal de Dados Abertos
do STJ.

- **Pesquisar:** busque por palavras ou por significado, filtre por órgão e
  ano e veja os acórdãos do julgamento mais recente ao mais antigo.
- **Explorar:** visualize os resultados por ano, relator e classe processual
  e compare as posições dos dois métodos de busca.
- **Conferir fontes:** gere uma síntese sob demanda com Gemini, abra os
  trechos citados e consulte o processo no portal do STJ.
- **Avaliar:** marque acórdãos como relevantes ou não, salve decisões no
  caderno e avalie a experiência de pesquisa.

## Executar localmente

Pré-requisitos: Git, Python 3.11 ou superior e espaço para a base e o índice.
Em um terminal PowerShell no Windows:

```powershell
git clone https://github.com/nadjaguerra/JurisIA.git
cd JurisIA
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\jurisia.exe sync --dataset espelhos-de-acordaos-terceira-turma
.\.venv\Scripts\jurisia.exe prepare
.\.venv\Scripts\python.exe -m streamlit run app\streamlit_app.py
```

Abra [localhost:8501](http://localhost:8501). Se já tiver os ZIPs ou JSONs
originais da Terceira Turma, coloque-os em `data/raw/` antes de rodar
`sync`. A primeira busca por palavras pode precisar criar o índice textual.

### Busca por significado e síntese

Para habilitar a busca semântica, rode:

```powershell
.\.venv\Scripts\jurisia.exe index --limit 2000
```

Esse recorte serve para testar o fluxo: limita o índice semântico a 2.000
documentos. Use `--limit 0` para indexar toda a base preparada e comparar os
métodos sobre o mesmo corpus. A primeira busca por significado carrega o
modelo local. O comando `sync` sem `--dataset` coleta todos os conjuntos
configurados e pode exigir várias horas e gigabytes.

Para gerar sínteses, copie `.env.example` para `.env` e configure
`GEMINI_API_KEY`. A chave é opcional para a pesquisa e fica fora do Git.
A pergunta e os trechos de apoio são enviados ao Gemini somente ao solicitar
a síntese.

## Organização do repositório

```text
JurisIA/
├── app/
│   └── streamlit_app.py          # Interface de pesquisa e exploração
├── src/
│   └── jurisia/                  # Coleta, preparação, busca, síntese e métricas
├── data/
│   └── sample/                   # Modelos CSV para avaliação
├── reports/                      # Auditoria e verificações locais
├── tests/                        # Testes automatizados
├── .env.example                  # Exemplo de configuração
├── AVALIACAO.md                  # Guia de avaliação
├── METODOLOGIA.md                # Recorte, procedimento e limites do estudo
├── LICENSE
├── README.md
├── pyproject.toml
└── requirements.txt
```

Consulte a [metodologia](METODOLOGIA.md) e o [guia de avaliação](AVALIACAO.md).

Os dados brutos, o SQLite, o índice vetorial, as anotações e as credenciais
ficam fora do Git. O comando `sync` registra a proveniência dos recursos,
e `prepare` importa os arquivos e deduplica por ID.

## Verificação e avaliação

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\jurisia.exe audit
```

O [relatório de auditoria](reports/base_audit.json) descreve a base local
medida na data da execução. Para comparar precisão, recall, MRR e taxa de
acerto, use uma amostra com IDs relevantes e execute `jurisia evaluate`
com `--mode lexical`, `--mode vector` ou `--mode rerank`. Use
`jurisia evaluate-synthesis` para agregar revisões por afirmação.
O CSV de exemplo é um modelo, e os testes automatizados não medem correção
jurídica.

## Fonte e limites

Os dados vêm dos [espelhos de acórdãos da Terceira Turma](https://dadosabertos.web.stj.jus.br/dataset/espelhos-de-acordaos-terceira-turma)
e de outros conjuntos configurados no [Portal de Dados Abertos do STJ](https://dadosabertos.web.stj.jus.br/dataset/?tags=jurisprudencia).
As ementas não representam todo o acervo ou o inteiro teor. A síntese pode
errar mesmo quando aponta para uma fonte existente; confira a decisão
original. O JurisIA é uma ferramenta acadêmica e não oferece assessoria
jurídica.

O código está sob a [licença MIT](LICENSE). Os dados seguem os termos do
respectivo conjunto publicado pelo STJ.
