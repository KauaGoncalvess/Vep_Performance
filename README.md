# VEP Performance – Sistema de Agendamento

## Estrutura
```
vep-performance/
├── app.py              ← Backend Flask (rotas, lógica)
├── database.py         ← Conexão PostgreSQL
├── requirements.txt    ← Dependências
├── Procfile            ← Comando de start para Render/Railway
├── .env.example        ← Modelo das variáveis de ambiente
├── .gitignore          ← Arquivos que NÃO sobem pro GitHub
├── static/
│   └── logo.jpg        ← Logo da VEP
└── templates/
    ├── index.html      ← Site público
    ├── admin_login.html
    └── admin_painel.html
```

## Configuração local

1. Copie o arquivo de exemplo:
```
cp .env.example .env
```

2. Preencha o `.env` com seus dados reais

3. Instale dependências:
```
py -3.11 -m pip install -r requirements.txt
```

4. Rode:
```
py -3.11 app.py
```

## Variáveis de ambiente obrigatórias

| Variável | Descrição |
|---|---|
| DATABASE_URL | URL do PostgreSQL |
| SECRET_KEY | Chave secreta do Flask (string aleatória longa) |
| SETUP_KEY | Chave para criar o primeiro admin via /setup-admin (remover após uso) |
| EVOLUTION_API_URL | URL da Evolution API (WhatsApp) |
| EVOLUTION_API_KEY | Chave da Evolution API |
| EVOLUTION_INSTANCE | Nome da instância na Evolution API (padrão: vep_performance) |
| WHATSAPP_MECANICO | Número do mecânico com DDI (ex: 5531994572780) |

## Deploy na Render (gratuito)

1. Suba o código no GitHub (sem o .env)
2. Crie conta em render.com
3. New → Web Service → conecte o repositório
4. Em "Environment Variables" adicione todas as variáveis do .env
5. Crie um PostgreSQL gratuito na Render e copie a DATABASE_URL

## Painel Admin

1. Acesse `/setup-admin` e use a SETUP_KEY para criar o primeiro admin
2. Remova a variável SETUP_KEY do ambiente após criar o admin
3. Acesse `/admin` e faça login com email e senha cadastrados
