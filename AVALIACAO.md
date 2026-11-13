# Protocolo de rotulagem e teste com usuários

## Benchmark de recuperação

Selecione perguntas representativas do recorte e inclua casos sem resposta.
Não há quantidade fixa obrigatória de perguntas nem exigência de dois
avaliadores. Documente os critérios de relevância, os IDs julgados relevantes
e eventuais divergências de revisão. Separe perguntas usadas para ajustar
parâmetros das usadas para medir o resultado final.

CSV: `question,relevant_ids,category,notes`. Em `relevant_ids`, use **IDs
do campo `id`**, separados por `|`. Número de processo é outro campo.

Exemplo de rótulo após revisão: `000815869|000815874`. Não trate esse
exemplo como referência jurídica ou como par de documentos relevantes.

## Critério de síntese

Para cada frase jurídica, aponte [D1] etc. e destaque o trecho exato da
ementa que a sustenta. Classifique: suportada; parcialmente suportada;
contradita; sem evidência. Avalie separadamente a precisão de processo,
relator, data e órgão. Uma referência existente pode acompanhar uma afirmação
incorreta, então verifique o conteúdo, não apenas o formato da citação.

## Questionário de participantes

Após 3 a 5 perguntas reais, peça notas de 1 a 5:

1. A resposta foi fácil de compreender? (clareza)
2. A resposta atendeu à pergunta? (relevância)
3. As fontes apresentadas transmitiram confiança? (confiança)
4. Foi fácil usar a ferramenta? (usabilidade)
5. A ferramenta foi útil para pesquisar jurisprudência? (utilidade)
6. Como avalia a experiência geral? (satisfação)

Pergunte também se utilizaria novamente (Sim/Talvez/Não) e “O que você
melhoraria?”. O app registra uma medida binária de utilidade; complemente a
análise com escala de 1 a 5 em estudo formal, se desejado.

## Cuidados metodológicos

Evite coletar nomes, documentos pessoais ou dados sensíveis no comentário
livre. Explique aos participantes que as respostas podem estar erradas e que
devem conferir o processo na fonte oficial. Reporte tamanho amostral e taxa
de não resposta. Não faça afirmações de qualidade antes da avaliação.
