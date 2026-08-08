
# Wise Part Number - Web App

Aplicativo web interno para pesquisar part numbers de peças de motocicletas e gerar títulos de Mercado Livre com até 60 caracteres.

## O colaborador precisa instalar alguma coisa?

Não.

Depois de publicado, ele acessa somente o link do aplicativo pelo Chrome, Edge ou celular.

## Publicação no Streamlit Community Cloud

1. Crie uma conta no GitHub, caso ainda não tenha.
2. Crie um repositório, por exemplo `wise-partnumber`.
3. Envie para o repositório:
   - `app.py`
   - `requirements.txt`
   - `.streamlit/config.toml`
   - `.gitignore`
4. NÃO envie `secrets.toml`.
5. Acesse Streamlit Community Cloud e crie um novo app apontando para o repositório.
6. Arquivo principal: `app.py`.
7. Em Advanced settings > Secrets, adicione:

```toml
OPENAI_API_KEY = "SUA_CHAVE_OPENAI"
OPENAI_MODEL = "gpt-5"
```

8. Clique em Deploy.

O Streamlit fornecerá uma URL pública para o aplicativo.

## Segurança

A chave OpenAI fica nos Secrets do servidor e não aparece para o colaborador.

## Fluxo

1. Colaborador abre o link.
2. Digita o part number.
3. Clica em PESQUISAR PEÇA.
4. O sistema pesquisa a aplicação na web.
5. Exibe peça, marca, modelos, anos e nível de confiança.
6. Gera título de até 60 caracteres.
7. Colaborador clica em COPIAR TÍTULO.

## Regra do título

Prioridade:
- peça;
- marca;
- modelo;
- anos.

Limite absoluto: 60 caracteres.
