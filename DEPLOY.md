# Publicação em nuvem

1. Em [GitHub Actions](https://github.com/nadjaguerra/JurisIA/actions/workflows/cloud-data.yml),
   selecione **Run workflow**, branch **main**. O runner hospedado baixa a Terceira Turma do STJ,
   prepara SQLite e indexa todas as ementas. Não usa arquivos do computador local.
2. Aguarde a execução terminar. Uma GitHub Release disponibiliza o ZIP e o
   manifesto SHA-256 somente após a validação. Se uma geração falhar, a
   release pública anterior continua disponível. A atualização está programada
   para segunda-feira, 04:23 UTC. Reinicie o app para carregar uma nova versão.
3. No [Streamlit Community Cloud](https://share.streamlit.io/), escolha
   **Create app** → **Yup, I have an app**. Use `nadjaguerra/JurisIA`, branch
   `main`, arquivo `app/cloud_app.py` e Python 3.12 em **Advanced settings**.
4. Gemini é opcional. Para habilitá-lo, configure em **Secrets**:
   `GEMINI_API_KEY = "sua_chave"`. Não inclua essa chave no GitHub.
5. Abra o link em uma janela privada e teste busca por palavras, paginação,
   busca por significado e comparação. Verifique a síntese se estiver habilitada.

O app baixa a base e o índice da mesma release e verifica o ZIP antes de
ativar. Feedback e caderno usam armazenamento temporário do servidor; não
publique informações pessoais e não conte com a persistência desses dados
após reinícios. O app pode hibernar no plano gratuito.
