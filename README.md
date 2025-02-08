backup_manager/
│
├── backend/                    # Backend API (FastAPI)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── auth.py            # Rotas de autenticação
│   │   ├── jobs.py            # Rotas de gerenciamento de jobs
│   │   └── execution.py       # Rotas de execução e monitoramento
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py          # Configurações do projeto
│   │   ├── security.py        # Funções de segurança (JWT, hash)
│   │   └── database.py        # Configuração do banco de dados
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── job.py            # Modelo do Job
│   │   ├── execution.py      # Modelo da Execução
│   │   └── user.py           # Modelo do Usuário
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── job.py            # Schemas Pydantic do Job
│   │   ├── execution.py      # Schemas Pydantic da Execução
│   │   └── user.py           # Schemas Pydantic do Usuário
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── job_manager.py    # Gerenciamento dos Jobs
│   │   └── backup_runner.py  # Lógica de execução do backup
│   │
│   └── main.py               # Ponto de entrada da API
│
├── worker/                    # Serviço de execução dos Jobs
│   ├── __init__.py
│   ├── backup_worker.py      # Worker para executar backups
│   ├── file_utils.py         # Utilitários para manipulação de arquivos
│   └── progress_tracker.py   # Rastreamento de progresso
│
├── frontend/                  # Frontend (React/Next.js)
│   ├── components/
│   ├── pages/
│   └── ...
│
├── tests/                     # Testes
│   ├── __init__.py
│   ├── test_api/
│   ├── test_services/
│   └── test_worker/
│
├── alembic/                   # Migrações do banco de dados
│   └── versions/
│
├── logs/                      # Diretório de logs
├── .env                      # Variáveis de ambiente
├── requirements.txt          # Dependências Python
└── README.md                 # Documentação