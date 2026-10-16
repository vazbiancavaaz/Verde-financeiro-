# Verde Financeiro 🌿

Aplicativo **web local** de gerenciamento financeiro pessoal, desenvolvido em **Python + Flask + SQLite**. O navegador (Chrome, Edge ou Firefox) mostra a interface, mas os cálculos e o armazenamento acontecem no Python do seu próprio computador. **Não é um site publicado na internet** e não precisa de conta, API paga ou conexão com a internet depois da instalação inicial.

## Funcionalidades

- **Visão geral:** saldo acumulado até hoje, receitas, despesas, resultado do período, movimentações recentes, barras por categoria e gráfico dos últimos seis meses.
- **Movimentações:** cadastrar, editar, consultar detalhes, excluir com confirmação, pesquisar, filtrar por tipo, categoria e período, ordenar e exportar CSV.
- **Categorias:** categorias iniciais de receitas e despesas, criar, renomear e desativar/reativar preservando os lançamentos antigos.
- **Relatórios:** este mês, mês anterior, últimos 30 dias, ano, período personalizado e todo o histórico; comparação dos últimos seis meses e resultado do mês anterior.
- **Metas:** cadastrar, editar, excluir e registrar aportes explícitos; progresso visual. Aportes não alteram automaticamente o saldo.
- **Contas previstas:** cadastrar, editar, excluir, vencimento, periodicidade informativa e marcar paga/pendente. Marcar como paga não gera movimentação automaticamente.
- **Configurações:** apelido, saldo inicial, ocultar valores, exportar CSV e baixar backup completo do banco.
- **Persistência:** SQLite mantém tudo salvo ao fechar e reabrir.

## Passo a passo para Windows + VS Code + Chrome

1. Instale o **Python 3.10 ou mais recente** em https://www.python.org/downloads/ . No instalador, marque **Add Python to PATH**.
2. Extraia o ZIP e abra a pasta `verde-financeiro-web` no VS Code em **Arquivo > Abrir Pasta**.
3. No VS Code, clique em **Terminal > Novo Terminal**.
4. Digite `py -m pip install -r requirements.txt` e pressione Enter. Esta etapa instala o Flask (precisa de internet na primeira vez).
5. Digite `py app.py` e pressione Enter.
6. O navegador padrão abre automaticamente. Se não abrir, entre no **Google Chrome** e digite **http://127.0.0.1:5000** na barra de endereços.
7. **Mantenha o terminal aberto** enquanto estiver usando o aplicativo. Para encerrar, volte ao terminal e pressione `Ctrl + C`.
8. Nas próximas vezes, você pode abrir a pasta e dar dois cliques em **`ABRIR_NO_CHROME.bat`** (ele verifica se o Flask está instalado).

> **Importante:** não abra `app.py` ou `index.html` diretamente no Chrome. O servidor Python precisa estar rodando para que os botões e os dados funcionem.

## Tecnologias

- Python 3.10+
- Flask 3.x (servidor web local)
- SQLite (banco de dados, incluído no Python)
- HTML5, CSS3, JavaScript sem dependências de front-end
- `unittest` para testes automatizados

## Estrutura

```text
verde-financeiro-web/
├── app.py                  # Servidor, rotas, regras e banco SQLite
├── templates/index.html    # Interface web
├── static/style.css        # Visual verde militar, responsivo
├── static/app.js           # Modais, edição e interações
├── tests/test_app.py       # Testes automatizados
├── docs/ENTREGA.md         # Checklist para o GitHub
├── requirements.txt        # Flask
├── .gitignore              # Exclui dados pessoais
├── ABRIR_NO_CHROME.bat     # Inicialização Windows
└── README.md
```

## Regras financeiras

- Valores são armazenados como **centavos inteiros**; não são somados com `float`.
- **Resultado do período** = receitas menos despesas dentro das datas escolhidas.
- **Saldo acumulado até hoje** = saldo inicial + receitas − despesas registradas até hoje (não inclui movimentações futuras).
- Uma meta só avança quando você informa o valor guardado ou registra um aporte. O valor da meta não é automaticamente retirado do saldo.
- Contas previstas são separadas das despesas efetivamente lançadas.
- Categorias desativadas deixam de aparecer para novos registros, mas continuam nos registros antigos.
- A periodicidade das contas é **informativa**. A próxima ocorrência deve ser cadastrada ou ter a data atualizada manualmente.

## Onde os dados ficam

No Windows: `C:\Users\SEU_USUARIO\.verde_financeiro\web.db`. O banco **não fica dentro do ZIP nem da pasta do projeto**. O `.gitignore` impede o envio acidental de arquivos `.db` comuns, mas confira o que será publicado.

**Backup:** em Configurações, clique em **Baixar backup**. Para restaurar, feche o servidor, faça uma cópia do banco atual e substitua `web.db` pelo arquivo de backup renomeado para `web.db` na pasta `.verde_financeiro`.

**Privacidade:** o servidor escuta apenas em `127.0.0.1` (seu computador). Não configure `0.0.0.0` nem publique esse servidor diretamente na internet. Não cadastre senhas bancárias, cartões ou dados sigilosos.

## Testes

No terminal da pasta do projeto:

```bash
py -m unittest discover -s tests -v
```

## Publicação no GitHub

Crie um repositório chamado `projeto-verde-financeiro` e, dentro da pasta, execute:

```bash
git init
git add .
git status
git commit -m "Cria aplicativo web Verde Financeiro"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/projeto-verde-financeiro.git
git push -u origin main
```

Substitua `SEU_USUARIO` e confirme que **nenhum banco pessoal, segredo, token ou senha** está incluído. O projeto não foi publicado automaticamente.

## Integrantes

- [Nome do estudante]
- [Nome de outro integrante, se houver]

## Limitações conhecidas

- É um aplicativo local para um único computador, não um serviço online hospedado.
- O Flask precisa ser instalado na primeira execução.
- Não há sincronização automática entre computadores, autenticação multiusuário ou backup automático.
- A recorrência de contas não cria lançamentos futuros automaticamente.
- O progresso de metas não é sincronizado com transações: a pessoa registra o valor guardado explicitamente.
