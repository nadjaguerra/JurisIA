# Metodologia e relatório acadêmico (preencher com resultados reais)

## Pergunta de pesquisa

Em que medida busca semântica com RAG facilita a localização e síntese
rastreável de espelhos de acórdãos do STJ em comparação com uma busca simples
por palavras?

## Fonte e recorte

Os espelhos de acórdãos vêm do Portal de Dados Abertos do STJ. Anote aqui
data da coleta, datasets efetivamente baixados, licença indicada no portal,
arquivos, intervalos temporais e quantidades após deduplicação. O código
salva o catálogo usado em `data/raw/<dataset>/manifest.json`.

| Conjunto | Período | Recursos | Registros lidos | IDs únicos | Ementas vazias |
|---|---|---:|---:|---:|---:|
| Terceira Turma | 02/05/1989–24/08/2026 | 53 importados | Não contabilizados nesta auditoria | 68.308 | 37 |

## Preparação

Os JSONs e ZIPs originais ficam em `data/raw`. O `prepare` preserva o JSON
completo em SQLite, deduplica pelo campo `id` e registra dataset e recurso.
`ementa` é o texto principal de recuperação. Valores ausentes não são
inventados. Data e órgão permanecem como metadados para filtros.

## Recuperação

O `index` divide a ementa em fragmentos de 70 palavras com 15 de sobreposição.
O modelo local multilíngue transforma pergunta e fragmentos em vetores. A
busca por cosseno retorna candidatos; um reranking experimental soma 85% da
similaridade vetorial a 15% da proporção de termos da pergunta presentes no
trecho. A escolha dos pesos e do limiar exige avaliação, não é um resultado
científico pré-estabelecido. No ranking final, cada acórdão aparece uma vez.

Compare pelo menos: busca vetorial vs. reranking, k=3/5/10, tamanhos de
chunk e filtros por órgão/ano. Guarde ambiente, versões, tempo, memória e
quantidade indexada em cada execução.

## Geração

Somente ementas recuperadas e metadados selecionados entram no contexto do
Gemini. A instrução exige citações [D1] etc., distingue limites processuais e
pede abstinência quando as fontes não bastam. O software confere se as
etiquetas citadas existem na seleção; **isso não prova que cada afirmação
está realmente apoiada pela fonte**. Faça avaliação humana por sentença.

## Resultados técnicos (preencher)

| Configuração | n perguntas | P@5 | R@5 | MRR | Hit Rate | Tempo médio |
|---|---:|---:|---:|---:|---:|---:|
| Palavras (FTS5/BM25) | | | | | | |
| Vetorial | | | | | | |
| Reranking | | | | | | |

Inclua intervalos de confiança ou ao menos contagens e casos de erro. Para
perguntas sem resposta, relate proporção de abstinências corretas e falsas
respostas; não inclua essas perguntas no denominador de Recall@K.

## Avaliação da geração (preencher)

Para cada resposta, um avaliador consulta as ementas e marca: afirmações
suportadas/total, citações corretas/total, relevância (1–5), completude (1–5)
e erros factuais. Registre divergências entre avaliadores. Compare perguntas
amplas e específicas, recentes e antigas, ambiguidades e casos fora da base.

## Avaliação com pessoas (preencher)

Informe número de participantes, perfil geral, recrutamento, perguntas
propostas, procedimento, consentimento e anonimização. O formulário do app
registra clareza, relevância, confiança, usabilidade, satisfação, utilidade
percebida e intenção de reutilização. Publique médias, medianas, distribuição
e comentários agregados sem identificar participantes.

## Limitações

Espelhos selecionados não cobrem toda a jurisprudência; versões posteriores
podem alterar entendimento; os documentos podem mencionar teses sem decidir o
mérito; links de recurso não substituem o inteiro teor. Embeddings, limiar,
reranking e LLM podem falhar. O projeto é acadêmico, não presta assessoria
jurídica nem substitui análise profissional do acórdão original.

## Execução e rastreabilidade

Não há amostra fixa obrigatória nem exigência de dois avaliadores.
O comando audit exporta contagens, período, órgãos, recursos, versões e estado
do índice em reports/base_audit.json. Esse relatório descreve a instalação;
não substitui avaliação de qualidade. Métricas de recuperação dependem de IDs
rotulados; métricas de suporte dependem da revisão por afirmação.
Compare o baseline lexical, a busca vetorial e o reranking no mesmo corpus.
A abstinência automática avaliada é a ausência de resultados acima do limiar;
a abstinência do texto gerado deve ser conferida na revisão da síntese.

Auditoria local executada em 22/10/2026: 228.787 fragmentos no índice ativo,
com tamanho 70 e sobreposição 15 palavras. Fonte: reports/base_audit.json.
As contagens descrevem o estado local e não representam validação jurídica.
